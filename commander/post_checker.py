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

def check_no_internal_imports(tree: ast.AST) -> bool:
    """检查是否没有函数内部 import（返回 True 表示干净）"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    return False
    return True

def check_no_bad_timestamp(content: str) -> bool:
    """检查是否没有危险时间戳用法（返回 True 表示干净）"""
    return 'get_event_loop().time()' not in content and 'loop.time()' not in content

ALLOWED_ENV_KEYS = {
    "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "ZHIPUAI_API_KEY",
    "CHAOSUAN_API_KEY", "TAVILY_API_KEY", "NAXUYE_WORKSPACE", "SANDBOX_PATH",
}

def check_env_var_names(content: str) -> List[str]:
    """
    扫描 os.getenv() 调用，返回不在白名单里的变量名列表。
    空列表表示全部合规。
    """
    pattern = r'os\.getenv\(\s*["\']([^"\']+)["\']'
    found = re.findall(pattern, content)
    bad = [k for k in found if k not in ALLOWED_ENV_KEYS]
    return bad

def check_has_error_handling(tree: ast.AST) -> bool:
    """检查 run() 函数里是否有 try/except 异常处理"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            for child in ast.walk(node):
                if isinstance(child, ast.Try):
                    return True
    return False

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
    if not check_no_internal_imports(tree):
        issues.append("存在函数内部 import，所有依赖必须在顶部显式导入")
        score -= 5

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
    批量校验所有资产。
    Returns:
        {
            "all_passed": bool,
            "total_score": int,      # 平均分
            "results": List[dict],   # 每个文件的检查结果
            "failed_files": List[str],
            "all_issues": List[str]  # 汇总所有问题，供 reviewer 使用
        }
    """
    results = []
    all_issues = []
    failed_files = []

    for asset in assets:
        path = asset.get("path", "unknown")
        content = asset.get("content", "")
        result = check_file(path, content)
        results.append(result)
        if not result["passed"]:
            failed_files.append(path)
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