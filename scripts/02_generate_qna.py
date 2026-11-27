"""조문별로 Claude를 호출해 가상의 QnA 데이터를 생성한다.

사용법
  python scripts/02_generate_qna.py               # 전체 조문
  python scripts/02_generate_qna.py --limit 5     # 앞 5개 조문만 (테스트용)
  python scripts/02_generate_qna.py --per-article 3 --workers 8

- 입력: data/processed/articles.jsonl  (01_parse_law.py 결과)
- 출력: data/qna/qna.jsonl  (이어쓰기: 이미 생성된 조문은 건너뜀)
- 필요: .env 의 ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "processed" / "articles.jsonl"
OUT_PATH = ROOT / "data" / "qna" / "qna.jsonl"

load_dotenv(ROOT / ".env")
MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("QNA_EFFORT", "low")  # QnA 생성은 단순 작업이라 low로 속도·비용 절약

CATEGORIES = [
    "수집·이용", "제공·위탁", "동의", "파기·보유기간", "안전조치", "정보주체 권리",
    "민감·고유식별정보", "신용정보 조회·제공", "신용정보 관리·보호", "마케팅",
    "유출·침해 대응", "벌칙·과징금", "정의·총칙", "기타",
]

SYSTEM_PROMPT = f"""당신은 신용협동조합중앙회 준법감시부의 직원 교육 담당자입니다.
주어진 법령 조문 하나를 읽고, 신협 직원이 실제 업무에서 물어볼 만한 질문과 그에 대한 정확한 답변을 만듭니다.

규칙
- 답변은 반드시 주어진 조문 내용에만 근거합니다. 조문에 없는 내용(다른 조문, 판례, 수치)을 지어내지 마세요.
- 질문은 신협 업무 상황을 반영합니다. 예: 조합원 가입, 예탁금·적금, 대출 심사, 공제 가입, 연체 관리,
  신용정보 조회 동의, 마케팅 활용 동의, 영업점 CCTV, 위탁업체 관리, 개인정보 유출 대응.
  조문이 정의·총칙처럼 업무 상황과 거리가 멀면 개념을 묻는 질문으로 만듭니다.
- 질문은 직원이 말하듯 자연스러운 한국어 한 문장으로 쓰고, 서로 다른 관점을 다룹니다.
- 답변은 2~4문장으로 결론을 먼저 말하고, 끝에 근거를 "(근거: <법령명> <조문>)" 형식으로 적습니다.
- 실존 인물·실제 개인정보는 쓰지 말고 필요하면 "조합원 A"처럼 씁니다.
- category는 다음 중 하나를 고릅니다: {", ".join(CATEGORIES)}"""


class QnAItem(BaseModel):
    question: str = Field(description="신협 직원의 질문")
    answer: str = Field(description="조문에 근거한 답변, 끝에 (근거: ...) 표기")
    category: str = Field(description="분류")


class QnASet(BaseModel):
    items: list[QnAItem]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def generate_for_article(client: anthropic.Anthropic, art: dict, n: int) -> list[dict]:
    user_msg = (
        f"법령: {art['law']}\n조문: {art['article']}({art['title']})\n\n"
        f"<조문>\n{art['text']}\n</조문>\n\n"
        f"이 조문으로 QnA {n}개를 만들어 주세요."
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": user_msg}],
        output_format=QnASet,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        print(f"[건너뜀] {art['id']}: stop_reason={response.stop_reason}", file=sys.stderr)
        return []

    rows = []
    for i, item in enumerate(response.parsed_output.items[:n], start=1):
        rows.append({
            "id": f"{art['id']}-Q{i:02d}",
            "article_id": art["id"],
            "law": art["law"],
            "law_type": art["law_type"],
            "article": art["article"],
            "title": art["title"],
            "question": item.question.strip(),
            "answer": item.answer.strip(),
            "category": item.category if item.category in CATEGORIES else "기타",
            "effective_date": art.get("effective_date"),
            "source": "synthetic",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="처리할 조문 수 (0=전체)")
    parser.add_argument("--per-article", type=int, default=3, help="조문당 QnA 개수")
    parser.add_argument("--workers", type=int, default=4, help="동시 요청 수")
    args = parser.parse_args()

    articles = load_jsonl(IN_PATH)
    if not articles:
        print("articles.jsonl이 없습니다. 먼저 01_parse_law.py를 실행하세요.", file=sys.stderr)
        return 1

    done = {row["article_id"] for row in load_jsonl(OUT_PATH)}
    todo = [a for a in articles if a["id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"전체 {len(articles)}개 조문 중 완료 {len(done)}개, 이번에 처리할 조문 {len(todo)}개 (모델 {MODEL})")
    if not todo:
        return 0

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY를 환경변수(.env)에서 읽음
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    created = failed = 0

    with OUT_PATH.open("a", encoding="utf-8") as out, ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(generate_for_article, client, a, args.per_article): a for a in todo}
        for idx, fut in enumerate(as_completed(futures), start=1):
            art = futures[fut]
            try:
                rows = fut.result()
            except anthropic.AuthenticationError:
                print("API 키가 올바르지 않습니다. .env의 ANTHROPIC_API_KEY를 확인하세요.", file=sys.stderr)
                pool.shutdown(cancel_futures=True)
                return 1
            except anthropic.APIError as e:
                failed += 1
                print(f"[실패] {art['id']}: {e}", file=sys.stderr)
                continue
            with lock:
                for row in rows:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
            created += len(rows)
            print(f"[{idx}/{len(todo)}] {art['law']} {art['article']} → {len(rows)}개")

    print(f"완료: QnA {created}개 생성, 실패 {failed}개 조문 → {OUT_PATH.relative_to(ROOT)}")
    if failed:
        print("실패한 조문은 같은 명령을 다시 실행하면 이어서 처리됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
