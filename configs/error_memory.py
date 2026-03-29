# -*- coding: utf-8 -*-
# filename: configs/error_memory.py
# 职责：纠错记录系统 — 错误模式记录、升级、规则注入
# 存储：SQLite，数据库文件在项目根目录 naxuye_memory.db

import os
import sqlite3
import hashlib
import json
import time
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger("Naxuye.ErrorMemory")

# ============================================================
# 枚举定义（替代 error_type_dict 表）
# ============================================================

class ErrorType(Enum):
    ENV_FABRICATION = "ENV_FABRICATION"          # 编造不存在的环境变量
    IMPORT_FAILURE = "IMPORT_FAILURE"            # import 失败
    SYNTAX_ERROR = "SYNTAX_ERROR"                # 语法错误
    MISSING_ENTRY = "MISSING_ENTRY"              # 缺少 run() 或 health()
    HARDCODED_SECRET = "HARDCODED_SECRET"        # 硬编码密钥
    INTERNAL_IMPORT = "INTERNAL_IMPORT"          # 函数内部 import
    SMOKE_CRASH = "SMOKE_CRASH"                  # 冒烟测试崩溃
    LOGIC_ERROR = "LOGIC_ERROR"                  # 逻辑错误（Reviewer 发现）
    TIMEOUT = "TIMEOUT"                          # API 调用超时
    EMPTY_RESPONSE = "EMPTY_RESPONSE"            # LLM 返回空内容
    OTHER = "OTHER"


class ErrorLevel(Enum):
    NOTICE = "NOTICE"          # 1-2 次，仅记录
    WARNING = "WARNING"        # 3-4 次，日志警告
    SEVERE = "SEVERE"          # 5-9 次，注入 Pillow prompt
    HARDCODED = "HARDCODED"    # 10+ 次，写入 PostChecker 硬拦截


class ErrorSource(Enum):
    POSTCHECKER = "POSTCHECKER"
    SMOKETEST = "SMOKETEST"
    REVIEWER = "REVIEWER"
    PILLOW = "PILLOW"


class RelatedTier(Enum):
    LLM_CALL = "LLM_CALL"
    API_INTEGRATION = "API_INTEGRATION"
    DATA_PROCESSING = "DATA_PROCESSING"
    TOOL = "TOOL"
    GENERAL = "GENERAL"


# ============================================================
# 数据库初始化
# ============================================================

def _get_db_path() -> str:
    """数据库文件放在项目根目录"""
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(workspace, "naxuye_memory.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表和索引"""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS error_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_hash TEXT UNIQUE NOT NULL,
                pattern_type TEXT NOT NULL,
                pattern_detail TEXT NOT NULL,
                source TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                level TEXT DEFAULT 'NOTICE',
                injected_rule TEXT,
                related_tier TEXT DEFAULT 'GENERAL',
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                -- P1 预留字段
                resolved_at REAL,
                resolved_by TEXT,
                trace_id TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS production_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                status TEXT NOT NULL,
                components TEXT,
                planner_output TEXT,
                score INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS production_error_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                production_id INTEGER NOT NULL,
                error_id INTEGER NOT NULL,
                FOREIGN KEY (production_id) REFERENCES production_history(id),
                FOREIGN KEY (error_id) REFERENCES error_patterns(id)
            );

            -- P1 预留：规则注入记录
            CREATE TABLE IF NOT EXISTS rule_injection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_id INTEGER NOT NULL,
                rule_text TEXT NOT NULL,
                injected_at REAL NOT NULL,
                target TEXT NOT NULL,
                FOREIGN KEY (error_id) REFERENCES error_patterns(id)
            );

            -- P0 索引
            CREATE INDEX IF NOT EXISTS idx_error_hash ON error_patterns(error_hash);
            CREATE INDEX IF NOT EXISTS idx_pattern_type ON error_patterns(pattern_type);
            CREATE INDEX IF NOT EXISTS idx_count ON error_patterns(count);
            CREATE INDEX IF NOT EXISTS idx_level ON error_patterns(level);
            CREATE INDEX IF NOT EXISTS idx_related_tier ON error_patterns(related_tier);
            CREATE INDEX IF NOT EXISTS idx_prod_agent ON production_history(agent_name);
            CREATE INDEX IF NOT EXISTS idx_prod_link ON production_error_link(production_id, error_id);
        """)
        conn.commit()
        logger.info("[ErrorMemory] 数据库初始化完成")
    finally:
        conn.close()


# ============================================================
# 错误记录核心
# ============================================================

def _compute_hash(pattern_type: str, pattern_detail: str) -> str:
    """基于错误类型+简化描述生成去重 hash"""
    # 去掉具体的变量名，保留模式
    # 例如 "编造环境变量 AGENT_TIMEOUT" 和 "编造环境变量 YOUR_API_KEY" 
    # 归为同一模式 "ENV_FABRICATION"
    raw = f"{pattern_type}:{pattern_detail}"
    return hashlib.md5(raw.encode()).hexdigest()


def _determine_level(count: int) -> str:
    """根据计数确定错误级别"""
    if count >= 10:
        return ErrorLevel.HARDCODED.value
    elif count >= 5:
        return ErrorLevel.SEVERE.value
    elif count >= 3:
        return ErrorLevel.WARNING.value
    else:
        return ErrorLevel.NOTICE.value


def record_error(
    pattern_type: str,
    pattern_detail: str,
    source: str,
    related_tier: str = "GENERAL"
) -> Dict[str, Any]:
    """
    记录一条错误。如果已存在则 count+1 并升级 level。
    返回当前错误状态。
    """
    init_db()
    conn = _get_conn()
    now = time.time()
    error_hash = _compute_hash(pattern_type, pattern_detail)

    try:
        # 查找是否已存在
        row = conn.execute(
            "SELECT * FROM error_patterns WHERE error_hash = ?",
            (error_hash,)
        ).fetchone()

        if row:
            new_count = row["count"] + 1
            new_level = _determine_level(new_count)
            old_level = row["level"]

            conn.execute("""
                UPDATE error_patterns 
                SET count = ?, level = ?, last_seen = ?, updated_at = ?
                WHERE error_hash = ?
            """, (new_count, new_level, now, now, error_hash))
            conn.commit()

            # 级别升级时打日志
            if new_level != old_level:
                logger.warning(
                    f"[ErrorMemory] 错误升级: {pattern_type} | "
                    f"{old_level} → {new_level} | 累计 {new_count} 次"
                )
                print(
                    f"⚠️ [ErrorMemory] 错误模式升级: {pattern_detail[:50]} | "
                    f"{old_level} → {new_level} ({new_count}次)"
                )

            return {
                "error_hash": error_hash,
                "count": new_count,
                "level": new_level,
                "is_new": False,
                "upgraded": new_level != old_level
            }
        else:
            conn.execute("""
                INSERT INTO error_patterns 
                (error_hash, pattern_type, pattern_detail, source, count, level,
                 related_tier, first_seen, last_seen, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 'NOTICE', ?, ?, ?, ?, ?)
            """, (error_hash, pattern_type, pattern_detail, source,
                  related_tier, now, now, now, now))
            conn.commit()

            return {
                "error_hash": error_hash,
                "count": 1,
                "level": "NOTICE",
                "is_new": True,
                "upgraded": False
            }
    finally:
        conn.close()


def record_production(
    agent_name: str,
    status: str,
    components: list = None,
    planner_output: str = "",
    score: int = 0,
    error_ids: list = None
) -> int:
    """记录一次生产历史，返回 production_id"""
    init_db()
    conn = _get_conn()
    now = time.time()

    try:
        cursor = conn.execute("""
            INSERT INTO production_history 
            (agent_name, timestamp, status, components, planner_output, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (agent_name, now, status, 
              json.dumps(components or [], ensure_ascii=False),
              planner_output, score, now))

        production_id = cursor.lastrowid

        # 关联错误
        if error_ids:
            for eid in error_ids:
                conn.execute("""
                    INSERT INTO production_error_link (production_id, error_id)
                    VALUES (?, ?)
                """, (production_id, eid))

        conn.commit()
        logger.info(f"[ErrorMemory] 生产记录: {agent_name} | {status} | score={score}")
        return production_id
    finally:
        conn.close()


# ============================================================
# 规则查询（供 Pillow 使用）
# ============================================================

def get_injection_rules(related_tier: str = None, min_level: str = "SEVERE") -> List[str]:
    """
    获取需要注入到 Pillow prompt 的规则列表。
    只返回 SEVERE 及以上级别的错误模式生成的规则。
    只注入代码生成相关错误（POSTCHECKER/REVIEWER），过滤掉环境类错误（SMOKETEST/PILLOW）。
    可按 related_tier 过滤，只注入和当前任务相关的规则。
    """
    CODE_SOURCES = "('POSTCHECKER', 'REVIEWER')"
    ENV_TYPES = "('TIMEOUT', 'EMPTY_RESPONSE', 'OTHER')"

    init_db()
    conn = _get_conn()

    try:
        if related_tier:
            rows = conn.execute(f"""
                SELECT pattern_type, pattern_detail, count, level 
                FROM error_patterns 
                WHERE level IN ('SEVERE', 'HARDCODED')
                AND (related_tier = ? OR related_tier = 'GENERAL')
                AND source IN {CODE_SOURCES}
                AND pattern_type NOT IN {ENV_TYPES}
                ORDER BY count DESC
                LIMIT 10
            """, (related_tier,)).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT pattern_type, pattern_detail, count, level
                FROM error_patterns 
                WHERE level IN ('SEVERE', 'HARDCODED')
                AND source IN {CODE_SOURCES}
                AND pattern_type NOT IN {ENV_TYPES}
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()

        rules = []
        for row in rows:
            level_tag = "🔴 严禁" if row["level"] == "HARDCODED" else "⚠️ 避免"
            rules.append(f"{level_tag}: {row['pattern_detail']} (已出现{row['count']}次)")

        return rules
    finally:
        conn.close()


def get_hardcoded_rules() -> List[str]:
    """获取所有 HARDCODED 级别的规则，供 PostChecker 硬拦截用"""
    init_db()
    conn = _get_conn()

    try:
        rows = conn.execute("""
            SELECT pattern_type, pattern_detail 
            FROM error_patterns 
            WHERE level = 'HARDCODED'
        """).fetchall()

        return [f"{row['pattern_type']}:{row['pattern_detail']}" for row in rows]
    finally:
        conn.close()


# ============================================================
# 统计查询
# ============================================================

def get_error_summary() -> Dict[str, Any]:
    """获取错误统计概览"""
    init_db()
    conn = _get_conn()

    try:
        total = conn.execute("SELECT COUNT(*) FROM error_patterns").fetchone()[0]
        by_level = {}
        for level in ErrorLevel:
            count = conn.execute(
                "SELECT COUNT(*) FROM error_patterns WHERE level = ?",
                (level.value,)
            ).fetchone()[0]
            if count > 0:
                by_level[level.value] = count

        top_errors = conn.execute("""
            SELECT pattern_type, pattern_detail, count, level
            FROM error_patterns 
            ORDER BY count DESC 
            LIMIT 5
        """).fetchall()

        productions = conn.execute("SELECT COUNT(*) FROM production_history").fetchone()[0]
        success = conn.execute(
            "SELECT COUNT(*) FROM production_history WHERE status = 'SUCCESS'"
        ).fetchone()[0]

        return {
            "total_patterns": total,
            "by_level": by_level,
            "top_errors": [dict(r) for r in top_errors],
            "total_productions": productions,
            "success_productions": success,
            "success_rate": f"{success/productions*100:.1f}%" if productions > 0 else "N/A"
        }
    finally:
        conn.close()


# ============================================================
# 工厂级记忆（供 Planner 使用）
# ============================================================

def get_similar_productions(keywords: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    根据关键词搜索历史成功案例，供 Planner 参考。
    搜索 agent_name 和 planner_output 字段。
    只返回成功的案例。
    """
    init_db()
    conn = _get_conn()

    try:
        # 拆分关键词
        words = [w.strip().lower() for w in keywords.split() if w.strip()]
        if not words:
            return []

        # 构造模糊匹配条件
        conditions = []
        params = []
        for word in words[:5]:  # 最多取5个关键词
            conditions.append(
                "(LOWER(agent_name) LIKE ? OR LOWER(planner_output) LIKE ? OR LOWER(components) LIKE ?)"
            )
            params.extend([f"%{word}%", f"%{word}%", f"%{word}%"])

        where_clause = " OR ".join(conditions)

        rows = conn.execute(f"""
            SELECT agent_name, components, planner_output, score, timestamp
            FROM production_history 
            WHERE status = 'SUCCESS' AND ({where_clause})
            ORDER BY score DESC, timestamp DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        results = []
        for row in rows:
            results.append({
                "agent_name": row["agent_name"],
                "components": row["components"],
                "planner_output": row["planner_output"],
                "score": row["score"]
            })

        return results
    finally:
        conn.close()