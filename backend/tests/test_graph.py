from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents import nodes
from app.agents.graph import build_graph


def test_auto_refund_path(monkeypatch):
    """低金额 + 低欺诈 + LOW 舆情 + 高 OCR 置信度 → AUTO_REFUND。"""
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="清晰商品图", conf=0.95))
    monkeypatch.setattr(nodes, "_risk_client", FakeRisk(fraud=20, sentiment="LOW"))

    graph = build_graph().compile(checkpointer=MemorySaver())
    state = graph.invoke(
        {"ticket_id": "T-1", "amount": 128.0, "image_paths": ["a.png"]},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert state["decision"] == "AUTO_REFUND"
    assert state["final_decision"] == "AUTO_REFUNDED"


def test_human_review_suspend_and_resume(monkeypatch):
    """350 元 → 命中 human_review → interrupt 挂起 → Command(resume=APPROVE) 恢复。"""
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="发票", conf=0.95))
    monkeypatch.setattr(nodes, "_risk_client", FakeRisk(fraud=20, sentiment="LOW"))

    graph = build_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}
    # 初跑用 stream：遇 interrupt 不抛异常
    for _ in graph.stream(
        {"ticket_id": "T-2", "amount": 350.0, "image_paths": ["a.png"]}, config=cfg
    ):
        pass
    snap = graph.get_state(cfg)
    assert snap.next == ("human_review",)   # 挂起在人工节点

    # 主管审批 APPROVE 唤醒
    resumed = graph.invoke(Command(resume={"action": "APPROVE"}), config=cfg)
    assert resumed["final_decision"] == "APPROVED"


def test_human_review_reject(monkeypatch):
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="发票", conf=0.95))
    monkeypatch.setattr(nodes, "_risk_client", FakeRisk(fraud=20, sentiment="LOW"))

    graph = build_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t3"}}
    for _ in graph.stream(
        {"ticket_id": "T-3", "amount": 350.0, "image_paths": ["a.png"]}, config=cfg
    ):
        pass
    assert graph.get_state(cfg).next == ("human_review",)

    resumed = graph.invoke(Command(resume={"action": "REJECT"}), config=cfg)
    assert resumed["final_decision"] == "REJECTED"


def test_low_ocr_confidence_forces_human_review(monkeypatch):
    """OCR 低置信度 → 强制人工（即便金额/欺诈/舆情均低风险）。"""
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="模糊图片", conf=0.3))
    monkeypatch.setattr(nodes, "_risk_client", FakeRisk(fraud=20, sentiment="LOW"))

    graph = build_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t4"}}
    for _ in graph.stream(
        {"ticket_id": "T-4", "amount": 128.0, "image_paths": ["a.png"]}, config=cfg
    ):
        pass
    snap = graph.get_state(cfg)
    assert snap.next == ("human_review",)


def test_ocr_node_resolves_uploaded_storage_key(monkeypatch):
    """上传 storage_key 必须先解析为绝对路径，再交给 OCR 客户端。"""
    calls = []
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="上传图片", conf=0.9))
    monkeypatch.setattr(
        nodes, "resolve_abs_path", lambda key: calls.append(key) or "/data/name.png", raising=False
    )

    result = nodes.ocr_node({"image_paths": ["uploads/name.png"]})

    assert calls == ["uploads/name.png"]
    assert nodes._ocr_client.paths == ["/data/name.png"]
    assert result["ocr_text"] == "上传图片"
    assert result["ocr_confidence"] == 0.9


def test_ocr_node_keeps_legacy_image_path_unchanged(monkeypatch):
    """既有测试用的普通文件名不是 storage_key，不得重写为上传路径。"""
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="本地图片", conf=0.9))
    monkeypatch.setattr(nodes, "resolve_abs_path", lambda key: "/data/name.png")

    nodes.ocr_node({"image_paths": ["a.png"]})

    assert nodes._ocr_client.paths == ["a.png"]


def test_ocr_node_resolves_windows_uploaded_storage_key(monkeypatch):
    """Windows 生成的反斜杠 storage_key 也必须先解析为绝对路径。"""
    monkeypatch.setattr(nodes, "_ocr_client", FakeOcr(text="上传图片", conf=0.9))
    monkeypatch.setattr(
        nodes, "resolve_abs_path", lambda key: "/data/name.png", raising=False
    )

    nodes.ocr_node({"image_paths": [r"uploads\name.png"]})

    assert nodes._ocr_client.paths == ["/data/name.png"]


def test_ocr_client_exception_falls_back_to_empty_result(monkeypatch):
    """OCR 客户端异常时回退为空文本和零置信度，避免阻断决策流。"""
    from app.agents import ocr

    def raise_ocr():
        raise RuntimeError("OCR unavailable")

    monkeypatch.setattr(ocr, "_get_ocr", raise_ocr)

    result = ocr.OcrClient().extract("a.png")

    assert result.text == ""
    assert result.confidence == 0.0


class FakeOcr:
    def __init__(self, text, conf):
        self._text = text
        self._conf = conf
        self.paths = []

    def extract(self, image_path):
        from app.agents.ocr import OcrResult

        self.paths.append(image_path)
        return OcrResult(text=self._text, confidence=self._conf)


class FakeRisk:
    def __init__(self, fraud, sentiment):
        self._fraud = fraud
        self._sentiment = sentiment

    def score_fraud(self, material):
        return self._fraud

    def classify_sentiment(self, material):
        return self._sentiment
