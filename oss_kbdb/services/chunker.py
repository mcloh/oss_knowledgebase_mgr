from __future__ import annotations

import re

from oss_kbdb.domain.models import Chunk

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_WORDS = re.compile(r"\S+")


def _windows(words: list[str], maximum: int, overlap: int) -> list[str]:
    stride = maximum - overlap
    return [" ".join(words[i:i + maximum]) for i in range(0, len(words), stride) if words[i:i + maximum]]


def hierarchical_chunks(text: str, *, max_tokens: int, overlap_tokens: int, min_tokens: int) -> list[Chunk]:
    """Cria pais por seção e filhos com sobreposição, preservando a hierarquia Markdown.

    Texto sem headings torna-se uma seção raiz. A unidade pai não recebe embedding: ela serve
    para reconstruir contexto; filhos são as unidades recuperáveis e indexáveis.
    """
    sections: list[tuple[tuple[str, ...], list[str]]] = []
    path: list[str] = []
    body: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        found = _HEADING.match(line)
        if found:
            if body:
                sections.append((tuple(path), body)); body = []
            level, title = len(found.group(1)), found.group(2).strip()
            path[level - 1:] = [title]
        else:
            body.append(line)
    if body:
        sections.append((tuple(path), body))
    if not sections:
        return []
    result: list[Chunk] = []
    ordinal = 0
    for path, lines in sections:
        section_text = "\n".join(lines).strip()
        words = _WORDS.findall(section_text)
        if len(words) < min_tokens:
            continue
        parent = ordinal
        result.append(Chunk(ordinal=parent, content=section_text, heading_path=path or ("Documento",), kind="section"))
        ordinal += 1
        for window in _windows(words, max_tokens, overlap_tokens):
            if len(_WORDS.findall(window)) >= min_tokens:
                result.append(Chunk(ordinal=ordinal, content=window, heading_path=path or ("Documento",),
                                    kind="chunk", parent_ordinal=parent))
                ordinal += 1
    return result
