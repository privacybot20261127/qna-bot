"""검색(Retrieval) + 답변 생성(Generation) 로직.

흐름
  질문 → 임베딩 → 벡터DB에서 조문·QnA 검색 → 조문 단위로 묶기 → 조문 원문을 근거로 Claude가 답변

가상 QnA는 "어떤 조문을 볼지 찾는 용도"로만 쓰고,
LLM에게 근거로 주는 것은 항상 조문 원문이다 (QnA 답변의 오류가 그대로 전달되지 않도록).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

import chromadb
from dotenv import load_dotenv

from app import llm

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CHAT_EFFORT = os.getenv("CHAT_EFFORT", "low")  # Claude 사용 시 응답 속도 조절
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
CHROMA_DIR = ROOT / os.getenv("CHROMA_DIR", "vectordb")
TOP_K = int(os.getenv("TOP_K", "5"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.45"))  # 이 유사도보다 낮으면 "근거 없음"으로 처리
COLLECTION = "law_kb"
MAX_HISTORY = 6

NO_SOURCE_MESSAGE = (
    "질문과 관련된 조문을 찾지 못했습니다. "
    "이 챗봇은 개인정보 보호법·신용정보법(법률 및 시행령)만 다룹니다. "
    "질문을 더 구체적으로 바꿔 보시거나 준법감시부서에 문의해 주세요."
)

SYSTEM_PROMPT = """당신은 신용협동조합 직원을 돕는 개인정보·신용정보 법령 안내 도우미입니다.
다루는 법령: 개인정보 보호법, 같은 법 시행령, 신용정보의 이용 및 보호에 관한 법률, 같은 법 시행령.

답변 규칙
- <참고 조문>에 있는 내용만 근거로 답합니다. 조문에 없는 내용은 추측하지 말고 "제공된 조문만으로는 확인하기 어렵습니다"라고 말한 뒤 준법감시부서 확인을 권합니다.
- 첫 문장에 결론을 말하고, 이어서 이유를 짧게 설명합니다. 필요하면 업무에서 지켜야 할 사항을 목록으로 정리합니다.
- 근거로 쓴 조문은 본문에 「법령명」 제N조처럼 표시하고, 마지막 줄에 "근거:" 뒤에 사용한 조문을 나열합니다.
- 법률 용어는 쉬운 말로 풀어 쓰되 의미를 바꾸지 않습니다.
- 한국어로, 신협 직원에게 말하듯 정중하고 간결하게 답합니다."""


@dataclass
class Source:
    law: str
    article: str
    title: str
    text: str
    score: float
    effective_date: str | None = None
    matched_questions: list[str] = field(default_factory=list)

    def label(self) -> str:
        return f"「{self.law}」 {self.article}({self.title})"


class LawRAG:
    def __init__(self) -> None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            self.collection = client.get_collection(COLLECTION)
        except Exception as e:
            raise RuntimeError(
                "벡터DB가 없습니다. scripts/03_build_index.py를 먼저 실행하세요."
            ) from e

        index_model = (self.collection.metadata or {}).get("embedding_model")
        if index_model and index_model != EMBEDDING_MODEL:
            raise RuntimeError(
                f"벡터DB는 '{index_model}'로 만들어졌는데 현재 설정은 '{EMBEDDING_MODEL}'입니다. "
                ".env의 EMBEDDING_MODEL을 맞추거나 03_build_index.py를 다시 실행하세요."
            )

        try:
            # 무거운 라이브러리(torch)라서 여기서 불러온다: 실패해도 서버는 켜지고 화면에 원인이 표시됨
            from sentence_transformers import SentenceTransformer
        except OSError as e:
            raise RuntimeError(
                "임베딩 라이브러리(PyTorch)를 불러오지 못했습니다. "
                "최신 Visual C++ 재배포 패키지를 설치하세요: https://aka.ms/vs/17/release/vc_redist.x64.exe"
            ) from e
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)

    @property
    def size(self) -> int:
        return self.collection.count()

    # ---------- 검색 ----------
    def retrieve(self, question: str, top_k: int = TOP_K) -> list[Source]:
        vec = self.embedder.encode([question], normalize_embeddings=True).tolist()
        res = self.collection.query(
            query_embeddings=vec,
            n_results=min(top_k * 3, max(self.size, 1)),
            include=["metadatas", "distances"],
        )

        # 조문 ID 기준으로 묶는다: QnA가 검색돼도 그 QnA의 원래 조문을 근거로 쓴다.
        best: dict[str, float] = {}
        questions: dict[str, list[str]] = {}
        for hit_id, meta, dist in zip(res["ids"][0], res["metadatas"][0], res["distances"][0]):
            score = 1.0 - dist  # cosine distance → similarity
            if meta["doc_type"] == "article":
                art_key = hit_id
            else:
                art_key = f"ART::{meta['article_id']}"
                questions.setdefault(art_key, []).append(meta["question"])
            best[art_key] = max(best.get(art_key, -1.0), score)

        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        ranked = [(k, s) for k, s in ranked if s >= MIN_SCORE][:top_k]
        if not ranked:
            return []

        got = self.collection.get(ids=[k for k, _ in ranked], include=["metadatas"])
        meta_by_id = dict(zip(got["ids"], got["metadatas"]))

        sources = []
        for key, score in ranked:
            meta = meta_by_id.get(key)
            if meta is None:  # QnA는 있는데 조문이 인덱스에 없는 경우
                continue
            sources.append(Source(
                law=meta["law"],
                article=meta["article"],
                title=meta["title"],
                text=meta["text"],
                score=round(score, 3),
                effective_date=meta.get("effective_date"),
                matched_questions=questions.get(key, [])[:3],
            ))
        return sources

    # ---------- 답변 생성 (스트리밍) ----------
    def stream_answer(self, question: str, history: list[dict] | None = None) -> Iterator[dict]:
        """이벤트를 순서대로 내보낸다: sources → delta(여러 번) → done  (실패 시 error)"""
        sources = self.retrieve(question)
        yield {"type": "sources", "sources": [asdict(s) for s in sources]}

        if not sources:
            yield {"type": "delta", "text": NO_SOURCE_MESSAGE}
            yield {"type": "done"}
            return

        context = "\n\n".join(
            f"[{i}] {s.label()}\n{s.text}" for i, s in enumerate(sources, start=1)
        )
        messages = _clean_history(history) + [{
            "role": "user",
            "content": f"<참고 조문>\n{context}\n</참고 조문>\n\n질문: {question}",
        }]

        try:
            for text in llm.stream_text(SYSTEM_PROMPT, messages, effort=CHAT_EFFORT):
                yield {"type": "delta", "text": text}
            yield {"type": "done"}
        except llm.LLMError as e:
            yield {"type": "error", "message": str(e)}


def _clean_history(history: list[dict] | None) -> list[dict]:
    """화면에서 받은 이전 대화를 API 형식으로 정리 (최근 N개, user로 시작)."""
    if not history:
        return []
    msgs = [
        {"role": m["role"], "content": str(m["content"])}
        for m in history
        if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
    ][-MAX_HISTORY:]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs
