# filename: skills/base.py
# version: v1.0, python>=3.11
# 职责：Skill 基类，定义统一接口规范
# ============================================================

import time
import logging
from typing import Dict, Any

logger = logging.getLogger("Skills.Base")


class SkillBase:
    """
    所有 Skill 的基类。
    子类必须实现 execute() 方法。
    对外统一暴露 call() 接口，内部处理所有异常。
    """

    name: str = "base"
    description: str = "基类，不可直接使用"
    version: str = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """子类实现具体逻辑，允许抛异常"""
        raise NotImplementedError("子类必须实现 execute()")

    async def call(self, **kwargs) -> Dict[str, Any]:
        """
        统一调用入口，包装 execute()。
        永远返回 dict，永远不抛异常。
        """
        try:
            result = await self.execute(**kwargs)
            if not isinstance(result, dict):
                result = {"data": result}
            result.setdefault("status", "success")
            result.setdefault("timestamp", time.time())
            return result
        except Exception as e:
            logger.error(f"[Skill:{self.name}] 执行失败: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "skill": self.name,
                "timestamp": time.time()
            }

    def info(self) -> Dict[str, str]:
        """返回 skill 元信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version
        }