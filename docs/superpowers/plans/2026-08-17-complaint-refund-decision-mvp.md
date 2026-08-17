# 客诉舆情退赔决策系统 MVP 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建「多 Agent 协同客诉舆情退赔决策系统」MVP 最小闭环——客服/主管 JWT 登录、LangGraph 多 Agent 决策流（OCR/风控/舆情/金额决策）、三态流转（挂起时 Redis 序列化上下文）、提交/审批防重、React 大屏、Docker Compose + Locust 压测。

**架构：** FastAPI 作为生产者接收申请并写入 Redis Streams，独立 Worker 消费并执行 LangGraph 决策流（Redis Checkpointer 持久化）；命中人工审批时 `interrupt()` 挂起，主管审批后 `Command(resume=...)` 唤醒。OCR 走本地 PaddleOCR，风控/舆情/金额决策走云端 DeepSeek LLM。PostgreSQL 持久化用户/工单/审批/轨迹，前端 React+AntD+ECharts 实时展示流转。

**技术栈：** Python 3.12 + FastAPI + SQLAlchemy 2.0 + LangGraph(`langgraph-checkpoint-redis`) + Redis 7 + PostgreSQL 15 + PaddleOCR(本地) + DeepSeek(OpenAI 兼容) + React 18/Vite/TS/AntD/ECharts + Docker Compose + Locust。

**规格文档：** `docs/superpowers/specs/2026-08-17-complaint-refund-decision-mvp-design.md`

---

## 文件结构（锁定分解决策）

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py              # pydantic-settings 配置（DB/Redis/JWT/DeepSeek/阈值）
│   ├── db.py                  # SQLAlchemy engine + SessionLocal + Base
│   ├── models.py              # User/Ticket/Approval/AgentTrace 模型
│   ├── schemas.py             # Pydantic 请求/响应模型
│   ├── security.py            # bcrypt 密码哈希 + PyJWT 签发/解码 + require_role 依赖
│   ├── deps.py                # get_db / get_current_user 依赖
│   ├── redis_client.py        # Redis 连接（fakeredis 可替换）
│   ├── idempotency.py         # 提交幂等键
│   ├── locks.py               # 审批/状态分布式锁
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py           # GraphState TypedDict
│   │   ├── decision_rules.py  # 纯决策规则（可单测）
│   │   ├── llm.py             # DeepSeek OpenAI 兼容客户端
│   │   ├── ocr.py             # PaddleOCR 封装
│   │   ├── nodes.py           # intake/ocr/fraud/sentiment/decision/human_review 节点
│   │   └── graph.py           # StateGraph 组装 + 条件边
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py            # POST /api/auth/login
│   │   └── tickets.py         # 工单 CRUD + 审批 + SSE
│   ├── worker/
│   │   ├── __init__.py
│   │   └── consumer.py        # Redis Streams 消费者，执行图
│   └── main.py                # FastAPI 入口，挂路由 + 启动建表
├── tests/
│   ├── conftest.py            # 测试夹具（SQLite + fakeredis + TestClient）
│   ├── test_decision_rules.py
│   ├── test_security.py
│   ├── test_idempotency.py
│   ├── test_locks.py
│   ├── test_graph.py          # MemorySaver 跑图，mock LLM/OCR
│   ├── test_auth_api.py
│   └── test_tickets_api.py
├── requirements.txt
└── Dockerfile
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── Dockerfile
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/client.ts          # axios 封装 + token 注入
    ├── pages/
    │   ├── Login.tsx
    │   ├── Dashboard.tsx      # 工单列表 + 新建申请
    │   └── TicketDetail.tsx   # OCR/风控/舆情/审批面板
    └── components/
        ├── FlowCanvas.tsx     # ECharts Agent 流转图
        └── ApprovePanel.tsx   # 主管一键审批/拒绝
docker-compose.yml
locustfile.py
```

**关键边界：**
- `decision_rules.py` 是纯函数，不依赖 I/O，是决策正确性的唯一来源（单测覆盖）。
- `nodes.py` 只做「调 OCR/LLM + 组装 state」，业务判断全部下沉到 `decision_rules.decide`。
- `graph.py` 只负责编排，不含业务规则。
- Worker 与 API 通过 Redis Streams 解耦，各自可独立重启。

---

## 任务 0：项目脚手架与依赖

**文件：**
- 创建：`backend/requirements.txt`
- 创建：`backend/app/__init__.py`、`backend/app/config.py`、`backend/app/db.py`、`backend/app/redis_client.py`
- 创建：`backend/tests/conftest.py`

- [ ] **步骤 1：写 requirements.txt**

```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30
sqlalchemy>=2.0
psycopg[binary]>=3.2
pydantic>=2.7
pydantic-settings>=2.3
PyJWT>=2.8
bcrypt>=4.1
redis>=5.0
fakeredis>=2.23
python-multipart>=0.0.9
sse-starlette>=2.1
langgraph>=0.2
langgraph-checkpoint-redis>=2.0
openai>=1.40
paddlepaddle==3.0.0
paddleocr>=2.9
pillow>=10.0
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27
```

- [ ] **步骤 2：写 config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/refund"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 120

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    AUTO_REFUND_MAX_AMOUNT: float = 300.0
    FRAUD_SCORE_THRESHOLD: int = 50
    OCR_CONFIDENCE_THRESHOLD: float = 0.6

    STREAM_KEY: str = "stream:tickets"
    CONSUMER_GROUP: str = "worker-group"


settings = Settings()
```

- [ ] **步骤 3：写 db.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
```

- [ ] **步骤 4：写 redis_client.py**

```python
import redis

from app.config import settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
```

- [ ] **步骤 5：写 tests/conftest.py（SQLite + fakeredis）**

```python
import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.deps import get_db, get_redis


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(db_engine, redis_client):
    Session = sessionmaker(bind=db_engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **步骤 6：Commit**

```bash
git add backend/requirements.txt backend/app/config.py backend/app/db.py backend/app/redis_client.py backend/tests/conftest.py
git commit -m "chore: scaffold backend config, db, redis"
```

---

## 任务 1：纯决策规则（TDD）

**文件：**
- 创建：`backend/app/agents/decision_rules.py`
- 测试：`backend/tests/test_decision_rules.py`

- [ ] **步骤 1：编写失败的测试**

```python
from app.agents.decision_rules import decide


def test_auto_refund_low_risk():
    assert decide(128.0, 20, "LOW") == "AUTO_REFUND"


def test_human_review_over_limit():
    assert decide(350.0, 20, "LOW") == "HUMAN_REVIEW"


def test_human_review_high_fraud():
    assert decide(128.0, 80, "LOW") == "HUMAN_REVIEW"


def test_human_review_high_sentiment():
    assert decide(128.0, 20, "HIGH") == "HUMAN_REVIEW"


def test_human_review_high_fraud_high_sentiment():
    assert decide(128.0, 80, "HIGH") == "HUMAN_REVIEW"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_decision_rules.py -v`
预期：FAIL，`ModuleNotFoundError: app.agents.decision_rules`

- [ ] **步骤 3：写最少实现**

```python
from app.config import settings


def decide(amount: float, fraud_score: int, sentiment: str) -> str:
    """纯决策规则：金额/欺诈分/舆情 → 路由决策。"""
    if amount > settings.AUTO_REFUND_MAX_AMOUNT:
        return "HUMAN_REVIEW"
    if fraud_score < settings.FRAUD_SCORE_THRESHOLD and sentiment == "LOW":
        return "AUTO_REFUND"
    return "HUMAN_REVIEW"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_decision_rules.py -v`
预期：PASS（5 passed）

- [ ] **步骤 5：Commit**

```bash
git add backend/app/agents/decision_rules.py backend/tests/test_decision_rules.py
git commit -m "feat: pure decision rule (300/50/LOW)"
```

---

## 任务 2：用户模块 —— JWT 鉴权与 RBAC（TDD）

**文件：**
- 创建：`backend/app/security.py`
- 测试：`backend/tests/test_security.py`

- [ ] **步骤 1：编写失败的测试**

```python
import pytest

from app.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip():
    token = create_access_token(1, "sv")
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "sv"


def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("not-a-token")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_security.py -v`
预期：FAIL，`ModuleNotFoundError: app.security`

- [ ] **步骤 3：写最少实现**

```python
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_security.py -v`
预期：PASS（3 passed）

- [ ] **步骤 5：Commit**

```bash
git add backend/app/security.py backend/tests/test_security.py
git commit -m "feat: JWT + bcrypt security primitives"
```

---

## 任务 3：数据模型（SQLAlchemy）

**文件：**
- 创建：`backend/app/models.py`

- [ ] **步骤 1：写 models.py**

```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    CS = "cs"
    SV = "sv"


class TicketStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"


class Decision(str, enum.Enum):
    PENDING = "PENDING"
    AUTO_REFUNDED = "AUTO_REFUNDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CS)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    image_paths: Mapped[list] = mapped_column(JSON, default=list)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    fraud_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.RUNNING)
    decision: Mapped[Decision] = mapped_column(Enum(Decision), default=Decision.PENDING)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    agent_name: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **步骤 2：跑一次建表冒烟验证**

运行：`cd backend && python -c "from app.models import User, Ticket, Approval, AgentTrace; print('ok')"`
预期：`ok`（无导入错误）

- [ ] **步骤 3：Commit**

```bash
git add backend/app/models.py
git commit -m "feat: SQLAlchemy models (users/tickets/approvals/agent_traces)"
```

---

## 任务 4：幂等与分布式锁（TDD）

**文件：**
- 创建：`backend/app/idempotency.py`
- 创建：`backend/app/locks.py`
- 测试：`backend/tests/test_idempotency.py`、`backend/tests/test_locks.py`

- [ ] **步骤 1：编写失败的测试（idempotency + locks）**

```python
from app.idempotency import resolve_idempotency


def test_idempotency_first_submit_creates(redis_client):
    existing = resolve_idempotency(redis_client, "idem:1:k1", "T-001")
    assert existing is None          # 首次，创建成功
    assert redis_client.get("idem:1:k1") == "T-001"


def test_idempotency_duplicate_returns_original(redis_client):
    redis_client.set("idem:1:k1", "T-001", ex=86400)
    existing = resolve_idempotency(redis_client, "idem:1:k1", "T-002")
    assert existing == "T-001"       # 重复，返回首次工单 ID
```

```python
from app.locks import acquire_approve_lock, release_approve_lock


def test_approve_lock_exclusive(redis_client):
    assert acquire_approve_lock(redis_client, "T-001") is True
    assert acquire_approve_lock(redis_client, "T-001") is False  # 第二把拿不到
    release_approve_lock(redis_client, "T-001")
    assert acquire_approve_lock(redis_client, "T-001") is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest tests/test_idempotency.py tests/test_locks.py -v`
预期：FAIL，模块未定义

- [ ] **步骤 3：写最少实现**

```python
def resolve_idempotency(redis, key: str, ticket_id: str) -> str | None:
    """SET NX：首次返回 None，重复返回已存的工单 ID。"""
    ok = redis.set(key, ticket_id, nx=True, ex=86400)
    if ok:
        return None
    return redis.get(key)
```

```python
def acquire_approve_lock(redis, ticket_id: str) -> bool:
    return bool(redis.set(f"lock:approve:{ticket_id}", "1", nx=True, px=10000))


def release_approve_lock(redis, ticket_id: str) -> None:
    redis.delete(f"lock:approve:{ticket_id}")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_idempotency.py tests/test_locks.py -v`
预期：PASS（4 passed）

- [ ] **步骤 5：Commit**

```bash
git add backend/app/idempotency.py backend/app/locks.py backend/tests/test_idempotency.py backend/tests/test_locks.py
git commit -m "feat: idempotency + approve distributed lock"
```

---

## 任务 5：LangGraph 决策流（图 + 节点，MemorySaver 单测）

**文件：**
- 创建：`backend/app/agents/state.py`
- 创建：`backend/app/agents/llm.py`
- 创建：`backend/app/agents/ocr.py`
- 创建：`backend/app/agents/nodes.py`
- 创建：`backend/app/agents/graph.py`
- 测试：`backend/tests/test_graph.py`

- [ ] **步骤 1：写 state.py**

```python
from typing import TypedDict


class GraphState(TypedDict, total=False):
    ticket_id: str
    amount: float
    image_paths: list[str]
    ocr_text: str
    ocr_confidence: float
    fraud_score: int
    sentiment: str
    decision: str          # AUTO_REFUND / HUMAN_REVIEW / REJECT
    final_decision: str    # AUTO_REFUNDED / APPROVED / REJECTED / PENDING
    approval_action: str
```

- [ ] **步骤 2：写 llm.py（DeepSeek OpenAI 兼容）**

```python
from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
    return _client


def call_llm(system: str, user: str) -> str:
    resp = get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
    )
    return resp.choices[0].message.content or ""
```

- [ ] **步骤 3：写 ocr.py（PaddleOCR 封装）**

```python
from paddleocr import PaddleOCR

_ocr: PaddleOCR | None = None


def get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(use_angle_cls=True, lang="ch")
    return _ocr


def extract_text(image_path: str) -> tuple[str, float]:
    """返回 (识别文字, 平均置信度)。"""
    results = get_ocr().ocr(image_path, cls=True)
    texts: list[str] = []
    scores: list[float] = []
    for line in results or []:
        for box in line or []:
            text, score = box[1][0], box[1][1]
            texts.append(text)
            scores.append(score)
    joined = "\n".join(texts)
    avg = sum(scores) / len(scores) if scores else 0.0
    return joined, avg
```

- [ ] **步骤 4：写 nodes.py**

```python
import json

from langgraph.types import interrupt

from app.agents.decision_rules import decide
from app.agents.llm import call_llm
from app.agents.ocr import extract_text
from app.agents.state import GraphState
from app.config import settings


def intake(state: GraphState) -> GraphState:
    state["ocr_text"] = ""
    state["ocr_confidence"] = 0.0
    state["fraud_score"] = 0
    state["sentiment"] = "LOW"
    state["final_decision"] = "PENDING"
    return state


def ocr_node(state: GraphState) -> GraphState:
    paths = state.get("image_paths", [])
    texts, scores = [], []
    for p in paths:
        t, s = extract_text(p)
        texts.append(t)
        scores.append(s)
    state["ocr_text"] = "\n".join(texts)
    state["ocr_confidence"] = min(scores) if scores else 0.0
    return state


def fraud_node(state: GraphState) -> GraphState:
    prompt = (
        "你是电商退款风控专家。根据以下凭证 OCR 文本与退款金额，"
        "评估恶意退款/薅羊毛欺诈分（0-100 整数，越高越可疑）。"
        "只输出 JSON：{\"fraud_score\": <int>}\n"
        f"金额：{state['amount']}\nOCR 文本：{state['ocr_text']}"
    )
    raw = call_llm("你是风控专家。", prompt)
    try:
        state["fraud_score"] = int(json.loads(raw)["fraud_score"])
    except Exception:
        # Output Parse 失败兜底：转人工（宁挂勿错退）
        state["fraud_score"] = 100
    return state


def sentiment_node(state: GraphState) -> GraphState:
    prompt = (
        "你是舆情分析专家。根据以下客诉内容评估舆情等级，"
        "只输出 LOW / MEDIUM / HIGH 之一。\n" + state["ocr_text"]
    )
    raw = call_llm("你是舆情专家。", prompt).strip().upper()
    state["sentiment"] = raw if raw in ("LOW", "MEDIUM", "HIGH") else "HIGH"
    return state


def decision_node(state: GraphState) -> GraphState:
    d = decide(state["amount"], state["fraud_score"], state["sentiment"])
    if state.get("ocr_confidence", 1.0) < settings.OCR_CONFIDENCE_THRESHOLD:
        d = "HUMAN_REVIEW"          # OCR 低置信度强制人工
    state["decision"] = d
    if d == "AUTO_REFUND":
        state["final_decision"] = "AUTO_REFUNDED"
    elif d == "REJECT":
        state["final_decision"] = "REJECTED"
    return state


def route_after_decision(state: GraphState) -> str:
    return state["decision"]


def human_review_node(state: GraphState) -> GraphState:
    resp = interrupt({"ticket_id": state["ticket_id"], "message": "需要人工审批"})
    action = resp["action"]
    state["approval_action"] = action
    state["final_decision"] = "APPROVED" if action == "APPROVE" else "REJECTED"
    return state
```

- [ ] **步骤 5：写 graph.py**

```python
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import GraphState


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("intake", nodes.intake)
    g.add_node("ocr", nodes.ocr_node)
    g.add_node("fraud", nodes.fraud_node)
    g.add_node("sentiment", nodes.sentiment_node)
    g.add_node("decision", nodes.decision_node)
    g.add_node("human_review", nodes.human_review_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "ocr")
    g.add_edge("ocr", "fraud")
    g.add_edge("fraud", "sentiment")
    g.add_edge("sentiment", "decision")
    g.add_conditional_edges(
        "decision",
        nodes.route_after_decision,
        {"AUTO_REFUND": END, "HUMAN_REVIEW": "human_review", "REJECT": END},
    )
    g.add_edge("human_review", END)
    return g.compile()
```

- [ ] **步骤 6：编写测试（mock LLM/OCR，用 MemorySaver）**

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents import nodes
from app.agents.graph import build_graph


def test_auto_refund_path(monkeypatch):
    monkeypatch.setattr(nodes, "extract_text", lambda p: ("清晰商品图", 0.95))
    monkeypatch.setattr(nodes, "call_llm", lambda s, u: '{"fraud_score": 20}')

    graph = build_graph()
    # 覆盖 sentiment 节点：让舆情直接 LOW（第二段 LLM 调用返回 LOW）
    def fake_sentiment(state):
        state["sentiment"] = "LOW"
        return state
    monkeypatch.setattr(nodes, "sentiment_node", fake_sentiment)

    graph = build_graph()
    state = graph.invoke({"ticket_id": "T-1", "amount": 128.0, "image_paths": ["a.png"]},
                         config={"configurable": {"thread_id": "t1"}})
    assert state["decision"] == "AUTO_REFUND"
    assert state["final_decision"] == "AUTO_REFUNDED"


def test_human_review_suspend_and_resume(monkeypatch):
    monkeypatch.setattr(nodes, "extract_text", lambda p: ("发票", 0.95))
    monkeypatch.setattr(nodes, "call_llm", lambda s, u: '{"fraud_score": 20}')

    def fake_sentiment(state):
        state["sentiment"] = "LOW"
        return state
    monkeypatch.setattr(nodes, "sentiment_node", fake_sentiment)

    graph = build_graph()
    cfg = {"configurable": {"thread_id": "t2"}}
    # 350 元 → 命中 human_review，图在人工节点 interrupt（stream 遇 interrupt 不抛异常）
    for _ in graph.stream({"ticket_id": "T-2", "amount": 350.0, "image_paths": ["a.png"]}, config=cfg):
        pass
    snap = graph.get_state(cfg)
    assert snap.next == ("human_review",)   # 挂起在人工节点

    # 主管审批 APPROVE 唤醒
    resumed = graph.invoke(Command(resume={"action": "APPROVE"}), config=cfg)
    assert resumed["final_decision"] == "APPROVED"
```

> 注意：`interrupt()` 挂起时，`graph.invoke` 会抛 `GraphInterrupt`（或返回含 `__interrupt__` 的状态，取决于 langgraph 版本）。为避免版本差异，测试与 Worker 统一用 `graph.stream()` 执行初跑（stream 遇 interrupt 不抛异常），再以 `graph.get_state(cfg).next` 判定是否挂起在 `human_review`。

- [ ] **步骤 7：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_graph.py -v`
预期：PASS（2 passed）

- [ ] **步骤 8：Commit**

```bash
git add backend/app/agents/state.py backend/app/agents/llm.py backend/app/agents/ocr.py backend/app/agents/nodes.py backend/app/agents/graph.py backend/tests/test_graph.py
git commit -m "feat: LangGraph multi-agent decision flow"
```

---

## 任务 6：API 接口（认证 + 工单 + 审批）

**文件：**
- 创建：`backend/app/schemas.py`
- 创建：`backend/app/deps.py`
- 创建：`backend/app/routers/__init__.py`、`backend/app/routers/auth.py`、`backend/app/routers/tickets.py`
- 修改：`backend/app/main.py`
- 测试：`backend/tests/test_auth_api.py`、`backend/tests/test_tickets_api.py`

- [ ] **步骤 1：写 schemas.py**

```python
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TicketCreate(BaseModel):
    amount: float
    image_paths: list[str] = []


class ApproveRequest(BaseModel):
    action: str      # APPROVE / REJECT
    comment: str | None = None
```

- [ ] **步骤 2：写 deps.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Role, User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少 token")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def require_role(role: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权限")
        return user
    return checker
```

- [ ] **步骤 3：写 routers/auth.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return TokenResponse(access_token=create_access_token(user.id, user.role.value))
```

- [ ] **步骤 4：写 routers/tickets.py**

```python
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.deps import get_current_user, get_db, require_role
from app.idempotency import resolve_idempotency
from app.locks import acquire_approve_lock, release_approve_lock
from app.models import Approval, Decision, Role, Ticket, TicketStatus
from app.redis_client import get_redis
from app.schemas import ApproveRequest, TicketCreate

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("")
def create_ticket(
    body: TicketCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
    x_idempotency_key: str | None = Header(None),
):
    idem_key = x_idempotency_key or uuid.uuid4().hex
    ticket_no = uuid.uuid4().hex
    redis_key = f"idem:{user.id}:{idem_key}"
    existing = resolve_idempotency(redis, redis_key, ticket_no)   # SET NX，值=ticket_no
    if existing is not None:
        # 幂等命中：返回首次创建的工单
        ticket = db.query(Ticket).filter(Ticket.ticket_no == existing).first()
        if ticket:
            return {"ticket_id": ticket.id, "ticket_no": ticket.ticket_no, "status": ticket.status.value}

    ticket = Ticket(
        ticket_no=ticket_no,
        user_id=user.id,
        amount=body.amount,
        image_paths=body.image_paths,
        status=TicketStatus.RUNNING,
        decision=Decision.PENDING,
        thread_id=uuid.uuid4().hex,
        idempotency_key=idem_key,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    # 写入 Streams 交给 Worker
    redis.xadd(settings.STREAM_KEY, {"ticket_id": str(ticket.id), "thread_id": ticket.thread_id})
    return {"ticket_id": ticket.id, "ticket_no": ticket.ticket_no, "status": ticket.status.value}


@router.get("")
def list_tickets(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Ticket).order_by(Ticket.id.desc()).all()
    return [{"id": t.id, "ticket_no": t.ticket_no, "amount": float(t.amount),
             "status": t.status.value, "decision": t.decision.value,
             "fraud_score": t.fraud_score, "sentiment": t.sentiment} for t in rows]


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, "工单不存在")
    return {"id": t.id, "ticket_no": t.ticket_no, "amount": float(t.amount),
            "ocr_text": t.ocr_text, "ocr_confidence": float(t.ocr_confidence) if t.ocr_confidence else None,
            "fraud_score": t.fraud_score, "sentiment": t.sentiment,
            "status": t.status.value, "decision": t.decision.value}


@router.post("/{ticket_id}/approve")
def approve_ticket(
    ticket_id: int,
    body: ApproveRequest,
    user=Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
):
    if body.action not in ("APPROVE", "REJECT"):
        raise HTTPException(400, "action 必须是 APPROVE 或 REJECT")
    if not acquire_approve_lock(redis, str(ticket_id)):
        raise HTTPException(409, "该工单正在被其他主管审批")
    try:
        t = db.get(Ticket, ticket_id)
        if t is None:
            raise HTTPException(404, "工单不存在")
        if t.status != TicketStatus.SUSPENDED:
            raise HTTPException(409, "工单不在挂起状态，无法审批")
        db.add(Approval(ticket_id=t.id, reviewer_id=user.id, action=body.action, comment=body.comment))
        db.commit()
    finally:
        release_approve_lock(redis, str(ticket_id))

    # 唤醒挂起的图（由 Worker 异步执行 resume，这里入队 resume 消息）
    redis.xadd(settings.STREAM_KEY, {"ticket_id": str(ticket_id), "thread_id": t.thread_id,
                                     "resume_action": body.action})
    return {"ok": True}
```

> 说明：审批唤醒采用「再写一条 Stream 消息，Worker 消费后调用 `Command(resume=...)`」的方式，保证 resume 与初次执行都在 Worker 内串行发生，避免 FastAPI 进程直接 resume 导致与 Worker 抢状态。Worker 侧见任务 7。

- [ ] **步骤 5：写 main.py**

```python
from fastapi import FastAPI

from app.db import Base, engine
from app.routers import auth, tickets

Base.metadata.create_all(bind=engine)

app = FastAPI(title="客诉舆情退赔决策系统")
app.include_router(auth.router)
app.include_router(tickets.router)
```

- [ ] **步骤 6：写测试**

```python
from app.models import User, Role
from app.security import hash_password


def _make_user(db, username, role):
    u = User(username=username, password_hash=hash_password("secret123"), role=role)
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_login_success(client, db_session):
    _make_user(db_session, "sv1", Role.SV)
    r = client.post("/api/auth/login", json={"username": "sv1", "password": "secret123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password(client, db_session):
    _make_user(db_session, "sv1", Role.SV)
    r = client.post("/api/auth/login", json={"username": "sv1", "password": "bad"})
    assert r.status_code == 401
```

```python
def _token(client, db_session, username, role):
    from app.models import Role, User
    from app.security import hash_password
    u = User(username=username, password_hash=hash_password("secret123"), role=role)
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    r = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return r.json()["access_token"]


def test_create_ticket(client, db_session, redis_client):
    tok = _token(client, db_session, "cs1", Role.CS)
    r = client.post("/api/tickets", json={"amount": 350.0, "image_paths": ["a.png"]},
                    headers={"Authorization": f"Bearer {tok}", "X-Idempotency-Key": "k1"})
    assert r.status_code == 200
    assert r.json()["status"] == "RUNNING"


def test_create_ticket_idempotent(client, db_session, redis_client):
    tok = _token(client, db_session, "cs1", Role.CS)
    h = {"Authorization": f"Bearer {tok}", "X-Idempotency-Key": "k2"}
    r1 = client.post("/api/tickets", json={"amount": 128.0}, headers=h)
    r2 = client.post("/api/tickets", json={"amount": 128.0}, headers=h)
    assert r1.json()["ticket_id"] == r2.json()["ticket_id"]


def test_approve_requires_supervisor(client, db_session, redis_client):
    cs_tok = _token(client, db_session, "cs2", Role.CS)
    r = client.post("/api/tickets/1/approve", json={"action": "APPROVE"},
                    headers={"Authorization": f"Bearer {cs_tok}"})
    assert r.status_code == 403
```

- [ ] **步骤 7：运行测试验证通过**

运行：`cd backend && python -m pytest tests/test_auth_api.py tests/test_tickets_api.py -v`
预期：PASS

- [ ] **步骤 8：Commit**

```bash
git add backend/app/schemas.py backend/app/deps.py backend/app/routers backend/app/main.py backend/tests/test_auth_api.py backend/tests/test_tickets_api.py
git commit -m "feat: auth + tickets + approve API with RBAC and idempotency"
```

---

## 任务 7：Worker 消费者（Redis Streams + Redis Checkpointer）

**文件：**
- 创建：`backend/app/worker/consumer.py`

- [ ] **步骤 1：写 consumer.py**

```python
import time

from langgraph.checkpoint.redis import RedisSaver
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.config import settings
from app.db import SessionLocal
from app.models import AgentTrace, Decision, Ticket, TicketStatus
from app.redis_client import get_redis


def update_ticket(thread_id: str, **fields):
    with SessionLocal() as db:
        t = db.query(Ticket).filter(Ticket.thread_id == thread_id).first()
        if t:
            for k, v in fields.items():
                setattr(t, k, v)
            db.commit()


def run_once():
    redis = get_redis()
    # 确保消费组存在
    try:
        redis.xgroup_create(settings.STREAM_KEY, settings.CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:
        pass

    msgs = redis.xreadgroup(settings.CONSUMER_GROUP, "worker-1",
                            {settings.STREAM_KEY: ">"}, count=1, block=5000)
    if not msgs:
        return

    for _stream, entries in msgs:
        for msg_id, fields in entries:
            try:
                process(fields)
                redis.xack(settings.STREAM_KEY, settings.CONSUMER_GROUP, msg_id)
            except Exception as e:
                print("process error", e)


def process(fields: dict):
    ticket_id = int(fields["ticket_id"])
    thread_id = fields["thread_id"]
    resume_action = fields.get("resume_action")

    with RedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph = build_graph().compile(checkpointer=checkpointer)
        cfg = {"configurable": {"thread_id": thread_id}}

        if resume_action:
            update_ticket(thread_id, status=TicketStatus.RUNNING)
            graph.invoke(Command(resume={"action": resume_action}), config=cfg)
        else:
            with SessionLocal() as db:
                t = db.get(Ticket, ticket_id)
                initial = {"ticket_id": str(ticket_id), "amount": float(t.amount),
                           "image_paths": t.image_paths or []}
            update_ticket(thread_id, status=TicketStatus.RUNNING)
            for _ in graph.stream(initial, config=cfg):
                pass  # stream 遇 interrupt 不抛异常，挂起判定见下

        # 判断是否挂起
        snapshot = graph.get_state(cfg)
        if snapshot.next and "human_review" in snapshot.next:
            update_ticket(thread_id, status=TicketStatus.SUSPENDED)
            return

        # 未挂起 → 读取最终 state 落库
        state = snapshot.values or {}
        update_ticket(
            thread_id,
            status=TicketStatus.COMPLETED,
            decision=Decision(state.get("final_decision", "REJECTED")),
            ocr_text=state.get("ocr_text"),
            ocr_confidence=state.get("ocr_confidence"),
            fraud_score=state.get("fraud_score"),
            sentiment=state.get("sentiment"),
        )


if __name__ == "__main__":
    print("worker started")
    while True:
        run_once()
```

- [ ] **步骤 2：手动冒烟验证 Worker 可导入**

运行：`cd backend && python -c "from app.worker.consumer import process; print('ok')"`
预期：`ok`

- [ ] **步骤 3：Commit**

```bash
git add backend/app/worker/consumer.py
git commit -m "feat: redis streams worker with checkpointer"
```

---

## 任务 8：前端 Dashboard（React + AntD + ECharts）

**文件：**
- 创建：`frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`
- 创建：`frontend/src/main.tsx`、`frontend/src/App.tsx`、`frontend/src/api/client.ts`
- 创建：`frontend/src/pages/Login.tsx`、`frontend/src/pages/Dashboard.tsx`、`frontend/src/pages/TicketDetail.tsx`
- 创建：`frontend/src/components/FlowCanvas.tsx`、`frontend/src/components/ApprovePanel.tsx`

- [ ] **步骤 1：写 package.json**

```json
{
  "name": "refund-dashboard",
  "private": true,
  "scripts": { "dev": "vite", "build": "tsc && vite build", "preview": "vite preview" },
  "dependencies": {
    "antd": "^5.20.0",
    "axios": "^1.7.0",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **步骤 2：写 vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
```

- [ ] **步骤 3：写 api/client.ts**

```typescript
import axios from 'axios'

const client = axios.create({ baseURL: '/api' })
client.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})
export default client
```

- [ ] **步骤 4：写 Login.tsx**

```tsx
import { Form, Input, Button, message } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const nav = useNavigate()
  const onFinish = async (v: any) => {
    const { data } = await client.post('/auth/login', v)
    localStorage.setItem('token', data.access_token)
    nav('/')
  }
  return (
    <Form onFinish={onFinish} style={{ width: 300, margin: '100px auto' }}>
      <Form.Item name="username" rules={[{ required: true }]}><Input placeholder="用户名" /></Form.Item>
      <Form.Item name="password" rules={[{ required: true }]}><Input.Password placeholder="密码" /></Form.Item>
      <Button type="primary" htmlType="submit" block>登录</Button>
    </Form>
  )
}
```

- [ ] **步骤 5：写 Dashboard.tsx（工单列表 + 新建申请）**

```tsx
import { useEffect, useState } from 'react'
import { Table, Button, InputNumber, Modal, message } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [rows, setRows] = useState([])
  const [amount, setAmount] = useState(0)
  const nav = useNavigate()
  const load = () => client.get('/tickets').then(r => setRows(r.data))
  useEffect(() => { load() }, [])
  const create = async () => {
    await client.post('/tickets', { amount, image_paths: [] }, {
      headers: { 'X-Idempotency-Key': crypto.randomUUID() },
    })
    message.success('已提交')
    load()
  }
  const cols = [
    { title: '工单号', dataIndex: 'ticket_no' },
    { title: '金额', dataIndex: 'amount' },
    { title: '状态', dataIndex: 'status' },
    { title: '决策', dataIndex: 'decision' },
    { title: '欺诈分', dataIndex: 'fraud_score' },
    { title: '舆情', dataIndex: 'sentiment' },
  ]
  return (
    <div style={{ padding: 24 }}>
      <Button onClick={create}>新建退款申请</Button>
      <InputNumber value={amount} onChange={setAmount} style={{ marginLeft: 8 }} />
      <Table rowKey="id" dataSource={rows} columns={cols}
             onRow={(r: any) => ({ onClick: () => nav(`/ticket/${r.id}`) })} />
    </div>
  )
}
```

- [ ] **步骤 6：写 FlowCanvas.tsx（ECharts Agent 流转图）**

```tsx
import ReactECharts from 'echarts-for-react'

export default function FlowCanvas({ agents }: { agents: { name: string; status: string }[] }) {
  const nodes = agents.map((a, i) => ({ name: a.name, x: i * 200, y: 0 }))
  const links = nodes.slice(0, -1).map((n, i) => ({ source: n.name, target: nodes[i + 1].name }))
  const option = {
    series: [{
      type: 'graph', layout: 'none',
      data: nodes.map(n => ({
        name: n.name, x: n.x, y: n.y,
        itemStyle: { color: aColor(agents.find(a => a.name === n.name)!.status) },
      })),
      links, roam: true, label: { show: true, position: 'bottom' },
    }],
  }
  return <ReactECharts option={option} style={{ height: 300 }} />
}

function aColor(s: string) {
  return s === 'SUCCESS' ? '#52c41a' : s === 'RUNNING' ? '#1890ff' : s === 'SUSPENDED' ? '#faad14' : '#d9d9d9'
}
```

- [ ] **步骤 7：写 ApprovePanel.tsx（主管审批）**

```tsx
import { Button, Input, Space } from 'antd'
import { useState } from 'react'
import client from '../api/client'

export default function ApprovePanel({ ticketId, onDone }: { ticketId: number; onDone: () => void }) {
  const [comment, setComment] = useState('')
  const act = async (action: 'APPROVE' | 'REJECT') => {
    await client.post(`/tickets/${ticketId}/approve`, { action, comment })
    onDone()
  }
  return (
    <Space>
      <Input value={comment} onChange={e => setComment(e.target.value)} placeholder="审批意见" />
      <Button type="primary" onClick={() => act('APPROVE')}>APPROVE 同意</Button>
      <Button danger onClick={() => act('REJECT')}>REJECT 拒绝</Button>
    </Space>
  )
}
```

- [ ] **步骤 8：写 TicketDetail.tsx + App.tsx + main.tsx**

```tsx
// TicketDetail.tsx
import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag } from 'antd'
import { useParams } from 'react-router-dom'
import client from '../api/client'
import FlowCanvas from '../components/FlowCanvas'
import ApprovePanel from '../components/ApprovePanel'

export default function TicketDetail() {
  const { id } = useParams()
  const [t, setT] = useState<any>(null)
  const load = () => client.get(`/tickets/${id}`).then(r => setT(r.data))
  useEffect(() => { load() }, [id])
  if (!t) return null
  return (
    <div style={{ padding: 24 }}>
      <Descriptions title="客诉详情" bordered>
        <Descriptions.Item label="金额">{t.amount}</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag>{t.status}</Tag></Descriptions.Item>
        <Descriptions.Item label="欺诈分">{t.fraud_score}</Descriptions.Item>
        <Descriptions.Item label="舆情">{t.sentiment}</Descriptions.Item>
      </Descriptions>
      <Card title="OCR 识别结果" style={{ marginTop: 16 }}>{t.ocr_text}</Card>
      <Card title="Agent 流转" style={{ marginTop: 16 }}>
        <FlowCanvas agents={[{ name: 'Intake', status: 'SUCCESS' }, { name: 'OCR', status: 'SUCCESS' },
                            { name: 'Fraud', status: 'SUCCESS' }, { name: 'Sentiment', status: 'SUCCESS' },
                            { name: 'Decision', status: t.status === 'SUSPENDED' ? 'SUSPENDED' : 'SUCCESS' }]} />
      </Card>
      {t.status === 'SUSPENDED' && (
        <Card title="人工审批" style={{ marginTop: 16 }}>
          <ApprovePanel ticketId={Number(id)} onDone={load} />
        </Card>
      )}
    </div>
  )
}
```

```tsx
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import TicketDetail from './pages/TicketDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/ticket/:id" element={<TicketDetail />} />
      </Routes>
    </BrowserRouter>
  )
}
```

```tsx
// main.tsx
import ReactDOM from 'react-dom/client'
import App from './App'
import 'antd/dist/reset.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<App />)
```

- [ ] **步骤 9：写 index.html + 前端 Dockerfile**

```html
<!doctype html>
<html><head><meta charset="utf-8" /><title>退赔决策系统</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>
```

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

- [ ] **步骤 10：Commit**

```bash
git add frontend
git commit -m "feat: react dashboard (list/create/detail/flow/approve)"
```

---

## 任务 9：Docker Compose 容器化

**文件：**
- 创建：`docker-compose.yml`
- 创建：`backend/Dockerfile`
- 创建：`frontend/nginx.conf`

- [ ] **步骤 1：写 backend/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **步骤 2：写 frontend/nginx.conf**

```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
    location /api/ {
        proxy_pass http://api:8000;
    }
}
```

- [ ] **步骤 3：写 docker-compose.yml**

```yaml
services:
  api:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/refund
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=change-me
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
    depends_on: [postgres, redis]
    ports: ["8000:8000"]

  worker:
    build: ./backend
    command: python -m app.worker.consumer
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/refund
      - REDIS_URL=redis://redis:6379/0
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
    depends_on: [postgres, redis]

  frontend:
    build: ./frontend
    depends_on: [api]
    ports: ["3000:80"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=refund
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

volumes:
  pgdata:
```

- [ ] **步骤 4：启动冒烟验证**

运行：`docker compose up -d --build`
预期：`api`、`worker`、`frontend`、`redis`、`postgres` 全部 `Up`

- [ ] **步骤 5：Commit**

```bash
git add docker-compose.yml backend/Dockerfile frontend/nginx.conf
git commit -m "chore: docker compose orchestration"
```

---

## 任务 10：Locust 压测脚本

**文件：**
- 创建：`locustfile.py`

- [ ] **步骤 1：写 locustfile.py**

```python
from locust import HttpUser, between, task


class RefundUser(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self):
        r = self.client.post("/api/auth/login", json={"username": "sv1", "password": "secret123"})
        self.token = r.json()["access_token"]

    @task(3)
    def submit_ticket(self):
        self.client.post(
            "/api/tickets",
            json={"amount": 128.0, "image_paths": []},
            headers={"Authorization": f"Bearer {self.token}",
                     "X-Idempotency-Key": str(self._n := getattr(self, "_n", 0) + 1)},
        )

    @task(1)
    def list_tickets(self):
        self.client.get("/api/tickets", headers={"Authorization": f"Bearer {self.token}"})
```

- [ ] **步骤 2：运行压测**

运行：`locust -f locustfile.py --headless -u 100 -r 20 -t 60s --host http://localhost:8000`
预期：生成 QPS / P95 / 错误率 报告，验收 QPS≥200、P95<300ms、错误率<0.1%

- [ ] **步骤 3：Commit**

```bash
git add locustfile.py
git commit -m "test: locust load test"
```

---

## 任务 11：两大场景端到端联调

- [ ] **步骤 1：场景一（超 300 元挂起转人工）**

1. 登录主管 → 前端 Dashboard 点击「新建退款申请」，金额 `350.00`，上传破损发票图片。
2. 观察：Intake/OCR/Fraud/Sentiment 节点依次变绿，`HumanReview` 节点黄灯，工单状态 `SUSPENDED`。
3. 主管在审批面板输入「情况属实，批准退款」，点击 `APPROVE`。
4. 观察：1 秒内 `HumanReview` 变绿，案件终态 `APPROVED` / `COMPLETED`。

- [ ] **步骤 2：场景二（低金额无风险秒退）**

1. 金额 `128.00`，上传清晰商品图。
2. 观察：风控欺诈分 20、舆情 LOW，所有 Agent 节点 2 秒内全绿，终态 `COMPLETED`，无需主管介入。

- [ ] **步骤 3：记录联调截图/录屏**

对两大场景各截取核心运行状态图，作为任务二验收证据（工单要求自己录屏自证）。

- [ ] **步骤 4：Commit 联调说明**

```bash
git add docs
git commit -m "docs: 两大场景联调记录"
```

---

## 自检记录

- **规格覆盖度**：用户模块（任务 2/3/6）✓；决策流（任务 1/5）✓；三态流转 + Redis 序列化（任务 5/7）✓；防重（任务 4/6）✓；大屏（任务 8）✓；Docker + Locust（任务 9/10）✓；两大场景联调（任务 11）✓。
- **占位符**：无 TODO/待定；每个代码步骤含完整代码。
- **类型一致性**：`GraphState` 字段（`decision`/`final_decision`/`fraud_score`/`sentiment`/`ocr_confidence`）在 nodes.py、graph.py、test_graph.py、worker/consumer.py 中命名一致；`Decision`/`TicketStatus` 枚举在 models.py 与 routers/tickets.py、worker 中一致。
