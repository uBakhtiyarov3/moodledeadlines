"""Tiny in-process retrieval over the admin-managed knowledge base (BM25).

Language-agnostic (works for Uzbek Latin/Cyrillic, Russian, English) and has no external
dependencies. The index is rebuilt whenever an admin edits the knowledge base.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select

from app.db import Session
from app.models import KnowledgeDoc

TOKEN = re.compile(r"[\w'ʻʼ‘’]+", re.U)


def tokenize(text: str) -> list[str]:
    toks = []
    for raw in TOKEN.findall(text.lower()):
        w = re.sub(r"['ʻʼ‘’]", "", raw)
        if len(w) < 2:
            continue
        # crude stemming: Uzbek/Russian are heavily suffixed, a 6-char prefix matches most forms
        toks.append(w[:6])
    return toks


def chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            chunks.append(cur)
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap :]
        cur = p
    if cur:
        chunks.append(cur)
    return chunks


@dataclass
class Chunk:
    doc_title: str
    text: str
    tf: Counter
    length: int


class Index:
    def __init__(self, docs: list[tuple[str, str]]):
        self.chunks: list[Chunk] = []
        for title, content in docs:
            for c in chunk(content):
                toks = tokenize(f"{title} {c}")
                self.chunks.append(Chunk(title, c, Counter(toks), len(toks)))
        n = len(self.chunks) or 1
        df = Counter(t for c in self.chunks for t in c.tf)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.avg = sum(c.length for c in self.chunks) / n if self.chunks else 1

    def search(self, query: str, k: int = 4, k1: float = 1.4, b: float = 0.75) -> list[Chunk]:
        q = set(tokenize(query))
        scored = []
        for c in self.chunks:
            score = 0.0
            for t in q:
                f = c.tf.get(t)
                if f:
                    score += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * c.length / self.avg))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:k]]


_index = Index([])


async def rebuild() -> None:
    global _index
    async with Session() as s:
        docs = (await s.execute(select(KnowledgeDoc).where(KnowledgeDoc.enabled.is_(True)))).scalars().all()
    _index = Index([(d.title, d.content) for d in docs])


def search(query: str, k: int = 4) -> list[Chunk]:
    return _index.search(query, k)


def stats() -> dict:
    return {"chunks": len(_index.chunks)}
