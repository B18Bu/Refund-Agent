import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse(self.payload)


class TimeoutHttpClient:
    def post(self, _url, _json, _timeout):
        import httpx

        raise httpx.ReadTimeout("embedding timeout")


def test_embedding_client_uses_fixed_internal_url_and_rejects_wrong_dimension():
    from app.rag.embeddings import EMBEDDING_SERVICE_URL, EmbeddingClient, EmbeddingUnavailable

    transport = FakeHttpClient({"vectors": [[0.1] * 511]})
    client = EmbeddingClient(http_client=transport)

    with pytest.raises(EmbeddingUnavailable, match="512"):
        client.embed(["退款政策"])

    assert transport.calls[0][0] == f"{EMBEDDING_SERVICE_URL}/embed"


def test_embedding_http_timeout_becomes_unavailable():
    from app.rag.embeddings import EmbeddingClient, EmbeddingUnavailable

    with pytest.raises(EmbeddingUnavailable, match="不可用"):
        EmbeddingClient(http_client=TimeoutHttpClient()).embed(["退款政策"])


def test_embedding_service_health_fails_when_local_model_directory_is_missing(tmp_path):
    import rag_embedding_service
    from rag_embedding_service import LocalEmbeddingModel

    model = LocalEmbeddingModel(tmp_path / "missing")

    assert model.health() is False
    previous = rag_embedding_service.model
    rag_embedding_service.model = model
    try:
        assert TestClient(rag_embedding_service.app).get("/healthz").status_code == 503
    finally:
        rag_embedding_service.model = previous


def test_embedding_service_health_fails_without_weights_or_when_model_load_fails(tmp_path):
    import rag_embedding_service
    from rag_embedding_service import LocalEmbeddingModel

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    no_weights = LocalEmbeddingModel(model_dir)
    assert no_weights.health() is False

    broken_loader = LocalEmbeddingModel(model_dir, loader=lambda _path: (_ for _ in ()).throw(RuntimeError("损坏")))
    (model_dir / "model.safetensors").write_bytes(b"not-a-model")

    previous = rag_embedding_service.model
    rag_embedding_service.model = broken_loader
    try:
        assert TestClient(rag_embedding_service.app).get("/healthz").status_code == 503
    finally:
        rag_embedding_service.model = previous


def test_embedding_client_rejects_any_non_512_dimension(monkeypatch):
    from app.rag.embeddings import EmbeddingClient

    with pytest.raises(ValueError, match="512"):
        EmbeddingClient(dimension=511)


def test_settings_rejects_non_512_embedding_dimension_from_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "511")
    with pytest.raises(ValidationError, match="512"):
        Settings()


def test_embedding_client_rejects_invalid_runtime_setting(monkeypatch):
    from app.config import settings
    from app.rag.embeddings import EmbeddingClient

    monkeypatch.setattr(settings, "RAG_EMBEDDING_DIMENSION", 511)
    with pytest.raises(ValueError, match="512"):
        EmbeddingClient(http_client=FakeHttpClient({"vectors": []}))


@pytest.mark.parametrize("failure", ["missing_directory", "missing_config", "missing_weights", "load_failure"])
def test_embedding_service_returns_503_for_each_model_failure(failure, tmp_path):
    import rag_embedding_service
    from rag_embedding_service import LocalEmbeddingModel

    model_dir = tmp_path / "model"
    if failure != "missing_directory":
        model_dir.mkdir()
    if failure in {"missing_weights", "load_failure"}:
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
    if failure == "load_failure":
        (model_dir / "model.safetensors").write_bytes(b"not-a-model")
        model = LocalEmbeddingModel(
            model_dir, loader=lambda _path: (_ for _ in ()).throw(RuntimeError("损坏"))
        )
    else:
        model = LocalEmbeddingModel(model_dir)

    previous = rag_embedding_service.model
    rag_embedding_service.model = model
    try:
        client = TestClient(rag_embedding_service.app)
        assert client.get("/healthz").status_code == 503
        assert client.post("/embed", json={"texts": ["退款政策"]}).status_code == 503
    finally:
        rag_embedding_service.model = previous


def test_embedding_service_embed_hides_internal_exception_details():
    import rag_embedding_service

    class BrokenModel:
        def embed(self, _texts):
            raise RuntimeError(r"D:\\private\\model 权重损坏")

    previous = rag_embedding_service.model
    rag_embedding_service.model = BrokenModel()
    try:
        response = TestClient(rag_embedding_service.app).post("/embed", json={"texts": ["退款政策"]})
    finally:
        rag_embedding_service.model = previous

    assert response.status_code == 503
    assert response.json() == {"detail": "本地 embedding 服务不可用"}
