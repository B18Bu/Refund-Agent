"""仅供内部 RAG 索引使用的本地 embedding HTTP 服务。"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import settings


class EmbedRequest(BaseModel):
    texts: list[str]


class LocalEmbeddingModel:
    _WEIGHT_FILENAMES = ("model.safetensors", "pytorch_model.bin", "tf_model.h5")

    def __init__(
        self,
        model_dir: Path | str = settings.RAG_EMBEDDING_MODEL_DIR,
        loader: Callable[[Path], object] | None = None,
    ):
        self._model_dir = Path(model_dir)
        self._model = None
        self._loader = loader or self._load_model

    def health(self) -> bool:
        if settings.RAG_EMBEDDING_DIMENSION != 512 or not self._has_required_files():
            return False
        try:
            self._get_model()
        except Exception:
            return False
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        if settings.RAG_EMBEDDING_DIMENSION != 512 or not self._has_required_files():
            raise RuntimeError("本地 embedding 模型目录不存在或不完整")
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        result = [list(map(float, vector)) for vector in vectors]
        if any(len(vector) != settings.RAG_EMBEDDING_DIMENSION for vector in result):
            raise RuntimeError("本地 embedding 模型维度与配置不一致")
        return result

    def _has_required_files(self) -> bool:
        return self._model_dir.is_dir() and (self._model_dir / "config.json").is_file() and any(
            (self._model_dir / filename).is_file() for filename in self._WEIGHT_FILENAMES
        )

    def _get_model(self):
        if self._model is None:
            self._model = self._loader(self._model_dir)
        return self._model

    @staticmethod
    def _load_model(model_dir: Path):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(str(model_dir), local_files_only=True)


model = LocalEmbeddingModel()
app = FastAPI()


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    if not model.health():
        raise HTTPException(status_code=503, detail="本地 embedding 模型不可用")
    return {"ok": True}


@app.post("/embed")
def embed(request: EmbedRequest) -> dict[str, list[list[float]]]:
    try:
        return {"vectors": model.embed(request.texts)}
    except Exception:
        raise HTTPException(status_code=503, detail="本地 embedding 服务不可用")
