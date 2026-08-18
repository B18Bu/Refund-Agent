from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# 连接池：默认 pool_size=5 在压测/并发下不足。按 API 进程并发适当放大，
# max_overflow 允许瞬时峰值借出连接，pre_ping 避免失效连接。
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_timeout=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
