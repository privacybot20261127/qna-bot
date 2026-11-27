"""조문과 가상 QnA를 임베딩해서 ChromaDB(로컬)에 저장한다.

사용법
  python scripts/03_build_index.py

- 입력: data/processed/articles.jsonl, data/qna/qna.jsonl
- 출력: vectordb/ (git에 올리지 않음, 실행할 때마다 새로 만듦)
- 임베딩 모델: .env의 EMBEDDING_MODEL (기본 BAAI/bge-m3, 처음 실행 시 약 2GB 다운로드)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_PATH = ROOT / "data" / "processed" / "articles.jsonl"
QNA_PATH = ROOT / "data" / "qna" / "qna.jsonl"

load_dotenv(ROOT / ".env")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
CHROMA_DIR = ROOT / os.getenv("CHROMA_DIR", "vectordb")
COLLECTION = "law_kb"
BATCH = 64


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def clean_meta(d: dict) -> dict:
    # Chroma 메타데이터는 None을 허용하지 않음
    return {k: v for k, v in d.items() if v is not None}


def build_records() -> tuple[list[str], list[str], list[dict]]:
    ids, docs, metas = [], [], []

    for a in load_jsonl(ARTICLES_PATH):
        ids.append(f"ART::{a['id']}")
        docs.append(f"{a['law']} {a['article']}({a['title']})\n{a['text']}")
        metas.append(clean_meta({
            "doc_type": "article",
            "law": a["law"],
            "article": a["article"],
            "title": a["title"],
            "effective_date": a.get("effective_date"),
            "text": a["text"],
        }))

    for q in load_jsonl(QNA_PATH):
        ids.append(f"QNA::{q['id']}")
        docs.append(f"질문: {q['question']}\n답변: {q['answer']}")
        metas.append(clean_meta({
            "doc_type": "qna",
            "law": q["law"],
            "article": q["article"],
            "title": q["title"],
            "article_id": q["article_id"],
            "category": q.get("category"),
            "question": q["question"],
            "answer": q["answer"],
            "effective_date": q.get("effective_date"),
        }))

    return ids, docs, metas


def main() -> int:
    ids, docs, metas = build_records()
    if not ids:
        print("임베딩할 데이터가 없습니다. 01, 02 스크립트를 먼저 실행하세요.", file=sys.stderr)
        return 1
    n_art = sum(m["doc_type"] == "article" for m in metas)
    print(f"조문 {n_art}개 + QnA {len(ids) - n_art}개 임베딩 (모델: {EMBEDDING_MODEL})")

    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # 처음 만들 때는 컬렉션이 없음
    col = client.create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL},
    )

    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        vectors = model.encode(
            docs[start:end], normalize_embeddings=True, show_progress_bar=False
        ).tolist()
        col.add(ids=ids[start:end], documents=docs[start:end],
                metadatas=metas[start:end], embeddings=vectors)
        print(f"  {min(end, len(ids))}/{len(ids)}")

    print(f"완료: {col.count()}건 → {CHROMA_DIR.relative_to(ROOT)}/ (컬렉션 '{COLLECTION}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
