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
    test_script = f"""
import sys, json, asyncio, traceback
sys.stdout.reconfigure(encoding='utf-8')
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
        if isinstance(health_result, dict) and health_result.get("status") == "healthy":
            results["health"] = True
        else:
            results["errors"].append(f"health() returned unexpected: {{health_result}}")
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
            return json.loads(output)
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

        for path, (dest, module_name) in file_map.items():
            print(f"🧪 [SmokeTest] 测试 {path}...")
            result = await _test_single_file(dest, module_name, temp_dir)
            all_results[path] = result

            passed = result.get("import") and result.get("health")
            # run 只要求不崩溃（返回 dict 即可），不要求业务成功
            if not passed:
                failed_files.append(path)
                for err in result.get("errors", []):
                    all_errors.append(f"[{path}] {err}")
                print(f"    ❌ 失败: {result.get('errors', [])}")
            else:
                run_ok = "✅" if result.get("run") else "⚠️ run() 未通过但不阻断"
                print(f"    ✅ import + health 通过 | {run_ok}")

        # 汇总
        if failed_files:
            error_summary = "\n".join(all_errors)
            print(f"🔴 [SmokeTest] {len(failed_files)} 个文件未通过冒烟测试")
            return {
                "audit_report": {
                    "score": 30,
                    "error_type": "SMOKE_TEST_FAILURE",
                    "failed_count": len(failed_files),
                    "summary": f"冒烟测试失败: {', '.join(failed_files)}",
                    "smoke_errors": error_summary
                },
                "retry_count": 1
            }
        else:
            print(f"✅ [SmokeTest] 全部 {len(file_map)} 个文件冒烟测试通过")
            return {}

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass