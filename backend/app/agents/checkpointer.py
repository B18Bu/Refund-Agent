"""LangGraph Checkpointer 工厂。

三方对齐 P0（A-04）：挂起与恢复采用 LangGraph 原生 interrupt() + Checkpointer + Command(resume)，
禁止手工 pickle。Checkpointer 实现可选：
- CHECKPOINTER_BACKEND=redis    → Redis Checkpointer（需 RedisJSON 模块，redis-stack）
- CHECKPOINTER_BACKEND=postgres → PostgreSQL Checkpointer（默认，零额外依赖）

默认 postgres：在 RedisJSON 不可用的环境仍保证「原生 interrupt + Checkpointer」语义。
"""
import logging
from contextlib import contextmanager
from typing import Iterator

from app.config import settings

logger = logging.getLogger(__name__)


@contextmanager
def get_checkpointer() -> Iterator:
    """按配置返回 Checkpointer 上下文管理器。"""
    backend = settings.CHECKPOINTER_BACKEND
    if backend == "redis":
        from langgraph.checkpoint.redis import RedisSaver

        with RedisSaver.from_conn_string(settings.REDIS_URL) as saver:
            yield saver
    elif backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        # PostgresSaver 需要原生 psycopg 连接串（无 SQLAlchemy 方言前缀）
        conn = settings.DATABASE_URL
        if conn.startswith("postgresql+psycopg://"):
            conn = "postgresql://" + conn[len("postgresql+psycopg://"):]
        elif conn.startswith("postgresql+psycopg2://"):
            conn = "postgresql://" + conn[len("postgresql+psycopg2://"):]

        with PostgresSaver.from_conn_string(conn) as saver:
            saver.setup()  # 建表（幂等）
            yield saver
    else:
        raise ValueError(f"不支持的 Checkpointer 后端: {backend}")
