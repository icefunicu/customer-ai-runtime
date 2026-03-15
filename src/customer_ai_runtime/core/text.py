from __future__ import annotations

import hashlib
import math
import re

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]")
EMBEDDING_DIMENSIONS = 128


def tokenize_text(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def chunk_text(text: str, max_tokens: int = 120, overlap: int = 20) -> list[str]:
    tokens = tokenize_text(text)
    if not tokens:
        return []
    chunks: list[str] = []
    cursor = 0
    step = max(1, max_tokens - overlap)
    while cursor < len(tokens):
        chunk_tokens = tokens[cursor : cursor + max_tokens]
        chunks.append(" ".join(chunk_tokens))
        cursor += step
    return chunks


def build_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    tokens = tokenize_text(text)
    vector = [0.0] * dimensions
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def safe_excerpt(text: str, max_length: int = 140) -> str:
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3]}..."
