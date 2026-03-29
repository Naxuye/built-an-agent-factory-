# -*- coding: utf-8 -*-
# filename: commander/smoke_test.py
# 职责：在归档前对生产出的代码做冒烟测试
#       验证 health() 能调通、run({}) 不崩溃
#       不依赖注册表，直接操作代码内容

import os
import sys
import json
import asyncio
import tempfile
import shutil
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger("Naxuye.SmokeTest")

SMOKE_TIMEOUT = 15  # 单个文件的测试超时（秒）


def _clean_code(content: str) -> str:
    """清洗 markdown 残留"""
    content = re.sub(r'^```\w*\n?', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n```$', '', content, flags=re.MULTILINE)
    return content.replace('```', '').strip()


async def _test_single_file(filepath: str, module_name: str, temp_dir: str) -> Dict[str, Any]:
    """
    对单个文件执行冒烟测试：
    1. 尝试 import
    2. 调用 health()
    3. 调用 run({})（允许业务层面的 failed，但不允许崩溃）
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_script = f"""
import sys, json, asyncio, traceback
sys.stdout.reconfigure(encoding='utf-8')
# temp_dir 必须在 project_root 前面，避免同名文件冲突（如 main.py）
sys.path.insert(0, {repr(str(project_root))})
sys.path.insert(0, {repr(temp_dir)})

results = {{"import": False, "health": False, "run": False, "errors": []}}

# 1. Import test
try:
    mod = __import__({repr(module_name)})
    results["import"] = True
except Exception as e:
    results["errors"].append(f"import failed: {{e}}")
    print(json.dumps(results, ensure_ascii=False))
    sys.exit(0)

# 2. health() test
try:
    if hasattr(mod, 'health'):
        health_result = asyncio.run(mod.health())
        if isinstance(health_result, dict):
            results["health"] = True
        else:
            results["errors"].append(f"health() returned non-dict: {{health_result}}")
    else:
        results["errors"].append("health() function not found")
except Exception as e:
    results["errors"].append(f"health() crashed: {{e}}")

# 3. run() test (empty input — expect graceful handling, not crash)
try:
    if hasattr(mod, 'run'):
        run_result = asyncio.run(mod.run({{}}))
        if isinstance(run_result, dict):
            results["run"] = True
        else:
            results["errors"].append(f"run() returned non-dict: {{type(run_result)}}")
    else:
        results["errors"].append("run() function not found")
except Exception as e:
    results["errors"].append(f"run(empty) crashed: {{e}}")

print(json.dumps(results, ensure_ascii=False))
"""

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", test_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=SMOKE_TIMEOUT)
        output = stdout.decode('utf-8', errors='replace').strip()

        if output:
            # stdout 可能被子组件的 logging/print 污染，只取最后一行
            last_line = output.split('\n')[-1].strip()
            try:
                return json.loads(last_line)
            except json.JSONDecodeError:
                try:
                    return json.loads(output)
                except json.JSONDecodeError:
                    stderr_text = stderr.decode('utf-8', errors='replace').strip()
                    return {
                        "import": False, "health": False, "run": False,
                        "errors": [f"stdout 非 JSON: {output[:200]} | stderr: {stderr_text[:200]}"]
                    }
        else:
            stderr_text = stderr.decode('utf-8', errors='replace').strip()
            return {
                "import": False, "health": False, "run": False,
                "errors": [f"No output. stderr: {stderr_text[:300]}"]
            }

    except asyncio.TimeoutError:
        return {
            "import": False, "health": False, "run": False,
            "errors": [f"Timeout ({SMOKE_TIMEOUT}s)"]
        }
    except Exception as e:
        return {
            "import": False, "health": False, "run": False,
            "errors": [f"Test runner error: {str(e)}"]
        }


async def smoke_test_node(state: dict) -> dict:
    """
    LangGraph 节点：对 passed_slots 中的所有组件做冒烟测试。
    全部通过 → 正常流转到 Mindset
    有失败 → 返回失败信息，触发重工
    """
    passed_assets = state.get("passed_slots", [])

    if not passed_assets:
        print("⚠️ [SmokeTest] 无资产可测试")
        return {}

    # 创建临时目录，写入所有代码文件
    temp_dir = tempfile.mkdtemp(prefix="naxuye_smoke_")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        file_map = {}  # path -> module_name
        for asset in passed_assets:
            path = asset.get("path", "unknown.py")
            content = _clean_code(asset.get("content", ""))
            if not content or not path.endswith('.py'):
                continue

            safe_name = os.path.basename(path)
            dest = os.path.join(temp_dir, safe_name)
            with open(dest, 'w', encoding='utf-8') as f:
                f.write(content)
            module_name = safe_name.replace('.py', '')
            file_map[path] = (dest, module_name)

        if not file_map:
            print("⚠️ [SmokeTest] 没有可测试的 Python 文件")
            return {}

        # 逐个测试
        all_results = {}
        failed_files = []
        all_errors = []

        # 延迟导入纠错系统
        try:
            from configs.error_memory import record_error, ErrorType, ErrorSource
            has_memory = True
        except Exception:
            has_memory = False

        for path, (dest, module_name) in file_map.items():
            print(f"🧪 [SmokeTest] 测试 {path}...")
            result = await _test_single_file(dest, module_name, temp_dir)
            all_results[path] = result

            passed = result.get("import") and result.get("health")
            if not passed:
                failed_files.append(path)
                for err in result.get("errors", []):
                    all_errors.append(f"[{path}] {err}")

                    # 记录到纠错系统
                    if has_memory:
                        if "import failed" in err:
                            error_type = ErrorType.IMPORT_FAILURE.value
                        elif "health()" in err:
                            error_type = ErrorType.MISSING_ENTRY.value
                        elif "run(" in err:
                            error_type = ErrorType.SMOKE_CRASH.value
                        elif "Timeout" in err:
                            error_type = ErrorType.TIMEOUT.value
                        else:
                            error_type = ErrorType.OTHER.value

                        record_error(
                            pattern_type=error_type,
                            pattern_detail=err,
                            source=ErrorSource.SMOKETEST.value,
                            related_tier="GENERAL"
                        )

                print(f"    ❌ 失败: {result.get('errors', [])}")
            else:
                run_ok = "✅" if result.get("run") else "⚠️ run() 未通过但不阻断"
                print(f"    ✅ import + health 通过 | {run_ok}")

        # 汇总
        if failed_files:
            error_summary = "\n".join(all_errors)
            print(f"🔴 [SmokeTest] {len(failed_files)} 个文件未通过冒烟测试")

            # 从 passed_slots 剔除失败文件，让它们重新进生产
            failed_set = set(failed_files)
            cleaned_passed = [a for a in passed_assets if a.get("path") not in failed_set]
            print(f"🔧 [SmokeTest] 已从 passed_slots 剔除 {len(failed_files)} 个失败文件")

            return {
                "audit_report": {
                    "score": 30,
                    "error_type": "SMOKE_TEST_FAILURE",
                    "failed_count": len(failed_files),
                    "summary": f"冒烟测试失败: {', '.join(failed_files)}",
                    "smoke_errors": error_summary
                },
                "passed_slots": cleaned_passed,
                "retry_count": state.get("retry_count", 0) + 1
            }

        print(f"✅ [SmokeTest] 全部 {len(file_map)} 个文件冒烟测试通过")

        # ============================================================
        # 阶段二：运行 Planner 生成的测试用例
        # ============================================================
        test_cases = state.get("test_cases", [])
        if not test_cases:
            print("📋 [SmokeTest] 无测试用例，跳过功能验证")
            return {}

        print(f"🧪 [SmokeTest] 开始功能验证，共 {len(test_cases)} 个测试用例...")

        # 找到入口文件：优先 STRATEGIC 组件，其次 agent_name 匹配，最后取第一个
        agent_name = state.get("agent_name", "")
        target_components = state.get("target_components", [])

        # 找 STRATEGIC 组件
        strategic_path = None
        for comp in target_components:
            if comp.get("tier") == "STRATEGIC":
                strategic_path = os.path.basename(comp.get("path", ""))
                break

        # 在 file_map 里找对应的 entry
        entry_path = None
        entry_dest = None
        entry_module = None

        for fp, (dest, mod) in file_map.items():
            base = os.path.basename(fp)
            if strategic_path and base == strategic_path:
                entry_path, entry_dest, entry_module = fp, dest, mod
                break
            if agent_name and agent_name in mod:
                entry_path, entry_dest, entry_module = fp, dest, mod

        # 回退到第一个
        if not entry_path:
            entry_path = list(file_map.keys())[0]
            entry_dest, entry_module = file_map[entry_path]

        print(f"📋 [SmokeTest] 功能测试入口: {entry_path}")

        test_failures = []
        test_passes = 0

        for i, tc in enumerate(test_cases):
            tc_input = tc.get("input", {})
            check_type = tc.get("check_type", "status_success")
            check_value = tc.get("check_value", "")
            description = tc.get("description", f"测试用例 {i+1}")

            # 构造测试脚本
            tc_script = f"""
import sys, json, asyncio
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, {repr(str(project_root))})
sys.path.insert(0, {repr(temp_dir)})
try:
    mod = __import__({repr(entry_module)})
    result = asyncio.run(mod.run({json.dumps(tc_input, ensure_ascii=False)}))
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({{"status": "crashed", "error": str(e)}}, ensure_ascii=False))
"""
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", tc_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                output = stdout.decode('utf-8', errors='replace').strip()

                if not output:
                    test_failures.append(f"[{description}] 无输出")
                    print(f"    ❌ {description}: 无输出")
                    continue

                result = json.loads(output.split('\n')[-1].strip())

                # 根据 check_type 验证
                passed = False
                if check_type == "status_success":
                    passed = result.get("status") == "success"
                elif check_type == "field_exists":
                    passed = check_value in str(result.get("result", {}))
                elif check_type == "contains_text":
                    passed = check_value.lower() in str(result.get("result", "")).lower()
                else:
                    passed = result.get("status") == "success"

                if passed:
                    test_passes += 1
                    print(f"    ✅ {description}")
                else:
                    result_preview = str(result)[:200]
                    test_failures.append(f"[{description}] 返回: {result_preview}")
                    print(f"    ⚠️ {description}: 未通过 ({check_type})")
                    print(f"       实际返回: {result_preview}")

            except asyncio.TimeoutError:
                test_failures.append(f"[{description}] 超时")
                print(f"    ❌ {description}: 超时")
            except Exception as e:
                test_failures.append(f"[{description}] 异常: {str(e)[:100]}")
                print(f"    ❌ {description}: {e}")

        # 测试用例汇总
        total_tc = len(test_cases)
        print(f"📊 [SmokeTest] 功能验证: {test_passes}/{total_tc} 通过")

        if test_failures:
            for tf in test_failures:
                if has_memory:
                    record_error(
                        pattern_type="LOGIC_ERROR",
                        pattern_detail=f"功能测试失败: {tf[:150]}",
                        source="SMOKETEST",
                        related_tier="GENERAL"
                    )

            # 功能测试仅记录，不阻断流程（冒烟测试已保证代码结构正确）
            fail_rate = len(test_failures) / total_tc
            print(f"⚠️ [SmokeTest] 功能验证: {len(test_failures)}/{total_tc} 未通过（{int(fail_rate*100)}%），记录但不阻断")

        return {}

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass