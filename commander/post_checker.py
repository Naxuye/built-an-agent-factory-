# filename: commander/post_checker.py
# version: v1.0, python>=3.11
# ============================================================
# NAXUYE 工厂后处理校验器
# 职责：对生成代码进行 AST + 正则静态分析，输出问题清单
# ============================================================

import ast
import re
import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger("Naxuye.PostChecker")

# ============================================================
# 检查项定义
# ============================================================

def check_has_run_function(tree: ast.AST) -> bool:
    """检查是否有 async def run(input: dict) -> dict"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            args = [a.arg for a in node.args.args]
            if "input" in args:
                return True
    return False

def check_has_health_function(tree: ast.AST) -> bool:
    """检查是否有 async def health()"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "health":
            return True
    return False

def check_has_logger(tree: ast.AST) -> bool:
    """检查是否有 logger 定义"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "logger":
                    return True
    return False

def check_no_main_block(content: str) -> bool:
    """检查是否没有 if __name__ == '__main__'（返回 True 表示干净）"""
    return '__name__' not in content or '__main__' not in content

def check_no_event_loop_time(content: str) -> bool:
    """检查是否没有 asyncio.get_event_loop().time()（返回 True 表示干净）"""
    return 'get_event_loop().time()' not in content

def check_no_hardcoded_secrets(content: str) -> bool:
    """检查是否没有硬编码密钥（返回 True 表示干净）"""
    # 扫描常见硬编码密钥模式
    patterns = [
        r'(?i)(api_key|secret|password|token|passwd)\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)Authorization\s*=\s*["\']Bearer\s+[A-Za-z0-9\-_\.]{20,}["\']',
    ]
    for pattern in patterns:
        # 排除 os.getenv() 调用
        matches = re.findall(pattern, content)
        if matches:
            # 进一步确认不是 os.getenv
            lines = content.split('\n')
            for line in lines:
                if re.search(pattern, line) and 'os.getenv' not in line and 'getenv' not in line:
                    return False
    return True

def check_has_filename_header(content: str) -> bool:
    """检查第一行是否有 # filename:"""
    lines = content.strip().split('\n')
    return lines[0].strip().startswith('# filename:') if lines else False

def check_has_version_header(content: str) -> bool:
    """检查前5行是否有 # version:"""
    lines = content.strip().split('\n')[:5]
    return any(line.strip().startswith('# version:') for line in lines)

def check_no_internal_imports(tree: ast.AST, content: str = "") -> bool:
    """
    检查是否没有函数内部 import（返回 True 表示干净）
    豁免：延迟导入（error_memory、configs.* 等避免循环依赖的合法写法）
    """
    EXEMPT_MODULES = {"error_memory", "configs", "skills"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is node:
                    continue
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    module = ""
                    if isinstance(child, ast.Import):
                        module = child.names[0].name if child.names else ""
                    elif isinstance(child, ast.ImportFrom):
                        module = child.module or ""
                    pkg = module.split('.')[0]
                    if pkg in EXEMPT_MODULES:
                        continue
                    return False
    return True

def check_no_bad_timestamp(content: str) -> bool:
    """检查是否没有危险时间戳用法（返回 True 表示干净）"""
    return 'get_event_loop().time()' not in content and 'loop.time()' not in content

ALLOWED_API_KEYS = {
    "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "ZHIPUAI_API_KEY",
    "CHAOSUAN_API_KEY", "TAVILY_API_KEY",
}

def check_env_var_names(content: str) -> List[str]:
    """
    扫描 os.getenv() 调用，只检查含 API_KEY 字样的变量名是否在白名单里。
    其他配置变量（超时、路径等）不做限制。
    """
    pattern = r'os\.getenv\(\s*["\']([^"\']+)["\']'
    found = re.findall(pattern, content)
    bad = [k for k in found if 'API_KEY' in k and k not in ALLOWED_API_KEYS]
    return bad

def check_requests_has_timeout(content: str) -> bool:
    """检查 requests.get/post 是否都有 timeout 参数（返回 True 表示干净）"""
    pattern = r'requests\.(get|post|put|delete|patch)\s*\([^)]*\)'
    for match in re.finditer(pattern, content):
        if 'timeout' not in match.group(0):
            return False
    return True

def check_except_has_logging(tree: ast.AST) -> bool:
    """检查 except 块里是否有日志输出（返回 True 表示干净）"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            has_log = False
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Attribute) and func.attr in ('error', 'warning', 'info', 'exception', 'debug'):
                        has_log = True
                        break
                    if isinstance(func, ast.Name) and func.id == 'print':
                        has_log = True
                        break
            if not has_log:
                return False
    return True

def check_run_has_return(tree: ast.AST) -> bool:
    """检查 run() 函数是否有 return 语句"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value is not None:
                    return True
    return False

def check_has_error_handling(tree: ast.AST) -> bool:
    """检查 run() 函数里是否有 try/except 异常处理"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            for child in ast.walk(node):
                if isinstance(child, ast.Try):
                    return True
    return False


# Skill 体系：第三方库 → 对应 skill 的映射
SKILL_REPLACEMENTS = {
    "requests": "skills.http_request",
    "aiohttp": "skills.http_request",
    "httpx": "skills.http_request",
    "urllib3": "skills.http_request",
    "bs4": "skills.web_scraper",
    "beautifulsoup4": "skills.web_scraper",
    "scrapy": "skills.web_scraper",
    "lxml": "skills.web_scraper",
    "openai": "skills.llm_call",
    "anthropic": "skills.llm_call",
    "dashscope": "skills.llm_call",
}

def check_direct_third_party_imports(tree: ast.AST) -> List[str]:
    """
    检查是否直接 import 了有 skill 替代的第三方库。
    返回警告列表（不打回，只建议）。
    跳过 skills 目录自身的 import。
    """
    warnings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                pkg = alias.name.split('.')[0]
                if pkg in SKILL_REPLACEMENTS:
                    skill = SKILL_REPLACEMENTS[pkg]
                    warnings.append(f"建议使用 {skill} 替代直接 import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                pkg = node.module.split('.')[0]
                # 跳过 skills 自身的 import
                if pkg == "skills":
                    continue
                if pkg in SKILL_REPLACEMENTS:
                    skill = SKILL_REPLACEMENTS[pkg]
                    warnings.append(f"建议使用 {skill} 替代 from {node.module} import ...")
    return warnings

# ============================================================
# 主校验函数
# ============================================================

def check_file(path: str, content: str) -> Dict[str, Any]:
    """
    对单个文件进行完整校验。
    Returns:
        {
            "path": str,
            "passed": bool,
            "score": int,          # 0-100
            "issues": List[str],   # 问题列表
            "timestamp": float
        }
    """
    issues = []
    score = 100

    # 非 Python 文件直接通过
    if not path.endswith('.py'):
        return {
            "path": path,
            "passed": True,
            "score": 100,
            "issues": [],
            "timestamp": time.time()
        }

    # AST 解析
    try:
        clean_content = re.sub(r'```(python|py)?', '', content, flags=re.IGNORECASE)
        clean_content = clean_content.replace('```', '').strip()
        tree = ast.parse(clean_content)
    except SyntaxError as e:
        return {
            "path": path,
            "passed": False,
            "score": 0,
            "issues": [f"语法错误: Line {e.lineno}: {e.msg}"],
            "timestamp": time.time()
        }

    # --- 检查项逐一执行 ---

    # 1. async def run(input: dict)
    if not check_has_run_function(tree):
        issues.append("缺少标准入口函数: async def run(input: dict) -> dict")
        score -= 20

    # 2. async def health()
    if not check_has_health_function(tree):
        issues.append("缺少健康检查函数: async def health() -> dict")
        score -= 10

    # 3. logger
    if not check_has_logger(tree):
        issues.append("缺少 logger 日志定义")
        score -= 10

    # 4. if __name__ == '__main__'
    if not check_no_main_block(clean_content):
        issues.append("存在测试代码: if __name__ == '__main__'")
        score -= 15

    # 5. 危险时间戳用法
    if not check_no_bad_timestamp(clean_content):
        issues.append("危险时间戳用法: get_event_loop().time()，请改用 time.time()")
        score -= 10

    # 6. 硬编码密钥
    if not check_no_hardcoded_secrets(clean_content):
        issues.append("检测到硬编码密钥，必须改为 os.getenv()")
        score -= 20

    # 7. 环境变量名合规
    bad_env_keys = check_env_var_names(clean_content)
    if bad_env_keys:
        issues.append(f"非标准环境变量名: {bad_env_keys}，请使用白名单变量名")
        score -= 10

    # 8. run() 异常处理
    if not check_has_error_handling(tree):
        issues.append("run() 缺少 try/except 异常处理")
        score -= 10

    # 9. # version: 版本信息
    if not check_has_version_header(clean_content):
        issues.append("缺少版本信息: # version: v1.0, python>=3.11")
        score -= 5

    # 10. 函数内部 import
    if not check_no_internal_imports(tree, clean_content):
        issues.append("存在函数内部 import，所有依赖必须在顶部显式导入")
        score -= 5

    # 11. requests 调用必须有 timeout
    if not check_requests_has_timeout(clean_content):
        issues.append("requests 调用缺少 timeout 参数，容易挂死")
        score -= 15

    # 12. except 块必须有日志
    if not check_except_has_logging(tree):
        issues.append("存在无日志的 except 块，异常会被静默吞掉")
        score -= 10

    # 13. run() 必须有返回值
    if not check_run_has_return(tree):
        issues.append("run() 缺少 return 语句，无法返回结果")
        score -= 20

    # 14. 第三方库 import 检查（建议使用 skill 替代，警告不扣分）
    skill_warnings = check_direct_third_party_imports(tree)
    if skill_warnings:
        for w in skill_warnings:
            issues.append(f"[Skill建议] {w}")
        # 不扣分，只是建议

    score = max(0, score)
    passed = score >= 80 and len([i for i in issues if "缺少标准入口" in i or "硬编码密钥" in i]) == 0

    if issues:
        logger.warning(f"[PostChecker] {path} 得分: {score} | 问题: {issues}")
    else:
        logger.info(f"[PostChecker] {path} 校验通过，得分: {score}")

    return {
        "path": path,
        "passed": passed,
        "score": score,
        "issues": issues,
        "timestamp": time.time()
    }


def check_assets(assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    批量校验所有资产，并将发现的问题记录到纠错系统。
    """
    # 延迟导入，避免循环依赖
    try:
        from configs.error_memory import record_error, ErrorType, ErrorSource
        has_memory = True
    except Exception:
        has_memory = False

    results = []
    all_issues = []
    failed_files = []
    recorded_error_ids = []

    # 错误关键词 → ErrorType 映射
    issue_type_map = {
        "缺少标准入口": ErrorType.MISSING_ENTRY.value,
        "缺少健康检查": ErrorType.MISSING_ENTRY.value,
        "硬编码密钥": ErrorType.HARDCODED_SECRET.value,
        "语法错误": ErrorType.SYNTAX_ERROR.value,
        "函数内部 import": ErrorType.INTERNAL_IMPORT.value,
        "非标准环境变量": ErrorType.ENV_FABRICATION.value,
        "缺少 try/except": ErrorType.LOGIC_ERROR.value,
        "requests 调用缺少 timeout": ErrorType.LOGIC_ERROR.value,
        "无日志的 except": ErrorType.LOGIC_ERROR.value,
        "run() 缺少 return": ErrorType.MISSING_ENTRY.value,
    }

    for asset in assets:
        path = asset.get("path", "unknown")
        content = asset.get("content", "")
        result = check_file(path, content)
        results.append(result)
        if not result["passed"]:
            failed_files.append(path)

        # 记录每个问题到纠错系统
        if has_memory:
            for issue in result.get("issues", []):
                # 匹配错误类型
                error_type = ErrorType.OTHER.value
                for keyword, etype in issue_type_map.items():
                    if keyword in issue:
                        error_type = etype
                        break

                record_error(
                    pattern_type=error_type,
                    pattern_detail=issue,
                    source=ErrorSource.POSTCHECKER.value,
                    related_tier="GENERAL"
                )

        all_issues.extend([f"[{path}] {issue}" for issue in result["issues"]])

    total_score = int(sum(r["score"] for r in results) / len(results)) if results else 0
    all_passed = len(failed_files) == 0

    print(f"🔍 [PostChecker] 校验完成 | 平均分: {total_score} | 失败文件: {failed_files or '无'}")

    return {
        "all_passed": all_passed,
        "total_score": total_score,
        "results": results,
        "failed_files": failed_files,
        "all_issues": all_issues
    }