from __future__ import annotations

import json
import re
from collections import Counter
from urllib import request

from oss_kbdb.domain.models import Chunk, Enrichment

_WORD = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9_-]{2,}")
_STOPWORDS = frozenset("para como que uma uns umas dos das com por seu sua sobre entre nao não nos nas este esta isso aquilo quando onde qual quais".split())
PROMPT_VERSION = "enrich-v1"


def _keywords(text: str, limit: int = 12) -> tuple[str, ...]:
    counts = Counter(w.lower() for w in _WORD.findall(text) if w.lower() not in _STOPWORDS)
    return tuple(word for word, _ in counts.most_common(limit))


class DeterministicEnricher:
    """Fallback local, auditável e sem dependência de LLM para a primeira indexação."""
    def __init__(self, model: str = "deterministic-v1") -> None:
        self.model = model

    def enrich(self, chunk: Chunk) -> Enrichment:
        title = chunk.heading_path[-1] if chunk.heading_path else "Documento"
        summary = " ".join(chunk.content.split()[:80])
        keywords = _keywords(f"{title} {chunk.content}")
        questions = (f"Como funciona {title}?",) if title != "Documento" else ()
        hypothetical = f"Informações sobre {title}: {summary}"
        search_text = "\n".join((title, " > ".join(chunk.heading_path), summary,
                                  " ".join(keywords), " ".join(questions), hypothetical))
        return Enrichment(title, summary, keywords, questions, hypothetical, search_text, self.model, PROMPT_VERSION)


class OpenAICompatibleEnricher:
    """Adapter para LLMs auto-hospedados expostos pela API Chat Completions."""
    def __init__(self, base_url: str, api_key: str | None, model: str) -> None:
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model

    def enrich(self, chunk: Chunk) -> Enrichment:
        prompt = ("Extraia JSON com title, summary, keywords (lista), questions (lista) e hypothetical_answer. "
                  "Não invente fatos; use somente o trecho. Responda JSON puro.\n"
                  f"Hierarquia: {' > '.join(chunk.heading_path)}\nTrecho:\n{chunk.content}")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps({"model": self.model, "temperature": 0, "messages": [{"role": "user", "content": prompt}],
                           "response_format": {"type": "json_object"}}).encode()
        req = request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=90) as response:
            raw = json.load(response)["choices"][0]["message"]["content"]
        data = json.loads(raw)
        title = str(data.get("title") or (chunk.heading_path[-1] if chunk.heading_path else "Documento"))
        summary = str(data.get("summary") or chunk.content)
        keywords = tuple(map(str, data.get("keywords") or _keywords(chunk.content)))
        questions = tuple(map(str, data.get("questions") or ()))
        hypothetical = str(data.get("hypothetical_answer") or "")
        search_text = "\n".join((title, " > ".join(chunk.heading_path), summary, " ".join(keywords),
                                  " ".join(questions), hypothetical))
        return Enrichment(title, summary, keywords, questions, hypothetical, search_text, self.model, PROMPT_VERSION)
