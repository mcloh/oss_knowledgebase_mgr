from __future__ import annotations

import json
from urllib import request


class LocalEmbedder:
    def __init__(self, model: str, dimensions: int) -> None:
        from sentence_transformers import SentenceTransformer
        self._model, self.dimensions = SentenceTransformer(model), dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True).tolist()
        if vectors and len(vectors[0]) != self.dimensions:
            raise ValueError(f"modelo devolveu dimensão {len(vectors[0])}; esperado {self.dimensions}")
        return vectors


class OpenAICompatibleEmbedder:
    def __init__(self, base_url: str, api_key: str | None, model: str, dimensions: int) -> None:
        self.base_url, self.api_key, self.model, self.dimensions = base_url.rstrip("/"), api_key, model, dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(f"{self.base_url}/embeddings", data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=60) as response:
            data = json.load(response)
        vectors = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        if vectors and len(vectors[0]) != self.dimensions:
            raise ValueError(f"endpoint devolveu dimensão {len(vectors[0])}; esperado {self.dimensions}")
        return vectors
