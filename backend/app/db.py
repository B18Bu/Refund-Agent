from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# 连接池：必须与 PostgreSQL max_connections 匹配。
# 多 worker 下各进程独立持有连接池，pool 若过大（如 20）会被 4 个 worker 累计吃满
# PG 默认 100 上限，压测时触发 "too many clients already" → 全接口 500。
# 收紧为 pool_size=10 + max_overflow=5（单进程 ≤15，4 进程 ≤60），并为 PG 预留余量。
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5,
    pool_timeout=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
