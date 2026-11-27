"""FastAPI 서버: 채팅 화면(/)과 답변 API(/api/chat)를 제공한다.

실행: uvicorn app.main:app --reload   →  http://localhost:8000

사내 시스템 연동
  - 화면만 붙일 때: 사내 포털에 <iframe src="http://<서버>:8000/"> 로 삽입
  - 기능만 쓸 때:  POST /api/chat 을 직접 호출 (응답은 한 줄에 JSON 하나씩 오는 NDJSON 스트림)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.rag import LawRAG

STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("uvicorn.error")

state: dict = {"rag": None, "error": None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state["rag"] = LawRAG()
        log.info("RAG 준비 완료: 벡터DB %d건", state["rag"].size)
    except Exception as e:  # 인덱스가 없어도 서버는 켜고, 화면에 원인을 보여준다
        state["error"] = str(e)
        log.error("RAG 초기화 실패: %s", e)
    yield


app = FastAPI(title="CU-LawBot", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class HistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryItem] = []


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    rag: LawRAG | None = state["rag"]
    return {"ready": rag is not None, "documents": rag.size if rag else 0, "error": state["error"]}


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    rag: LawRAG | None = state["rag"]
    if rag is None:
        raise HTTPException(status_code=503, detail=state["error"] or "서버 준비 중입니다.")

    def events():
        for event in rag.stream_answer(req.question.strip(), [h.model_dump() for h in req.history]):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
