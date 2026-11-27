"""법령 원문(txt)을 조문 단위로 나눠 JSONL로 저장한다.

사용법
  1) 국가법령정보센터(law.go.kr)에서 아래 4개 법령 본문을 복사하거나 저장해서
     data/raw/ 아래에 다음 파일명으로 저장한다 (UTF-8 또는 CP949).
       - 개인정보보호법.txt
       - 개인정보보호법_시행령.txt
       - 신용정보법.txt
       - 신용정보법_시행령.txt
  2) python scripts/01_parse_law.py
  3) 결과: data/processed/articles.jsonl (한 줄 = 조문 1개)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "articles.jsonl"

# 파일명(확장자 제외) → (정식 법령명, ID 접두어, 구분)
LAWS: dict[str, tuple[str, str, str]] = {
    "개인정보보호법": ("개인정보 보호법", "PIPA", "법률"),
    "개인정보보호법_시행령": ("개인정보 보호법 시행령", "PIPA-ED", "시행령"),
    "신용정보법": ("신용정보의 이용 및 보호에 관한 법률", "CIPA", "법률"),
    "신용정보법_시행령": ("신용정보의 이용 및 보호에 관한 법률 시행령", "CIPA-ED", "시행령"),
}

# 제15조(개인정보의 수집ㆍ이용) ① ...   /   제39조의3(손해배상의 보장) ...
ARTICLE_RE = re.compile(r"^\s*제(\d+)조(?:의(\d+))?\s*\(([^)]+)\)\s*(.*)$")
# 제11조의2 삭제 <2020. 2. 4.>
DELETED_RE = re.compile(r"^\s*제\d+조(?:의\d+)?\s*삭제")
# 제1장 총칙 / 제2절 ... (장·절 제목은 본문이 아니므로 건너뜀)
HEADING_RE = re.compile(r"^\s*제\d+(?:장|절|관)(?:의\d+)?\s")
# 부칙이 시작되면 본문 파싱 종료
ADDENDA_RE = re.compile(r"^\s*부\s*칙")
# [시행 2025. 3. 13.]
EFFECTIVE_RE = re.compile(r"\[시행\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\]")
# 개정됐지만 아직 시행 전인 조문: 본문 끝에 "[시행일: 2027. 3. 9.] 제2조" 줄이 붙어 있음
FUTURE_RE = re.compile(r"\[시행일\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\]")


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"인코딩을 알 수 없음: {path}")


def find_effective_date(text: str) -> str | None:
    m = EFFECTIVE_RE.search(text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def parse_law(text: str, law_name: str, prefix: str, law_type: str) -> list[dict]:
    effective_date = find_effective_date(text)
    articles: list[dict] = []
    seen_ids: set[str] = set()
    current: dict | None = None

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(line for line in current.pop("_lines") if line).strip()
        if not body:
            return
        current["text"] = body
        # 시행 예정 조문은 현행 조문과 구분: ID에 -F, 제목에 시행 예정일 표시
        m = FUTURE_RE.search(body)
        if m:
            y, mo, d = m.groups()
            current["effective_date"] = f"{y}-{int(mo):02d}-{int(d):02d}"
            current["status"] = "시행예정"
            current["title"] += f" [{y}. {int(mo)}. {int(d)}. 시행 예정]"
            current["id"] += "-F"
        else:
            current["status"] = "현행"
        base_id, n = current["id"], 2
        while current["id"] in seen_ids:  # 그래도 겹치면 번호를 붙임
            current["id"] = f"{base_id}-{n}"
            n += 1
        seen_ids.add(current["id"])
        articles.append(current)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ADDENDA_RE.match(line):
            break
        if DELETED_RE.match(line):
            flush()
            current = None
            continue
        m = ARTICLE_RE.match(line)
        if m:
            flush()
            no, sub, title, rest = m.groups()
            article_no = f"제{no}조" + (f"의{sub}" if sub else "")
            art_id = f"{prefix}-{no}" + (f"-{sub}" if sub else "")
            current = {
                "id": art_id,
                "law": law_name,
                "law_type": law_type,
                "article": article_no,
                "title": title.strip(),
                "effective_date": effective_date,
                "_lines": [rest.strip()],
            }
            continue
        if current is None or HEADING_RE.match(line):
            continue
        current["_lines"].append(line)

    flush()
    return articles


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    missing = []
    with OUT_PATH.open("w", encoding="utf-8") as out:
        for stem, (law_name, prefix, law_type) in LAWS.items():
            path = RAW_DIR / f"{stem}.txt"
            if not path.exists():
                missing.append(path.name)
                continue
            articles = parse_law(read_text(path), law_name, prefix, law_type)
            for art in articles:
                out.write(json.dumps(art, ensure_ascii=False) + "\n")
            total += len(articles)
            print(f"[OK] {law_name}: 조문 {len(articles)}개")

    if missing:
        print(f"[경고] data/raw에 없는 파일: {', '.join(missing)}", file=sys.stderr)
    print(f"총 {total}개 조문 → {OUT_PATH.relative_to(ROOT)}")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
