"""국가법령정보센터에서 내려받은 법령 파일(.doc, 실제 형식은 RTF)을 텍스트로 바꿔 data/raw/에 저장한다.

사용법
  python scripts/00_convert_law_doc.py "C:\\Users\\<사용자>\\Downloads\\개인정보 보호법(법률)(...).doc" ...
  python scripts/00_convert_law_doc.py C:\\Users\\<사용자>\\Downloads   # 폴더를 주면 그 안의 .doc/.rtf 전부

파일명에 들어 있는 법령명을 보고 01_parse_law.py가 읽는 이름으로 저장한다.
  개인정보 보호법          → 개인정보보호법.txt
  개인정보 보호법 시행령   → 개인정보보호법_시행령.txt
  신용정보의 이용 및 ...   → 신용정보법.txt
  신용정보의 ... 시행령    → 신용정보법_시행령.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"


def target_name(filename: str) -> str | None:
    decree = "시행령" in filename
    if "신용정보" in filename:
        return "신용정보법_시행령.txt" if decree else "신용정보법.txt"
    if "개인정보" in filename:
        return "개인정보보호법_시행령.txt" if decree else "개인정보보호법.txt"
    return None


# 내용이 아닌 그룹(글꼴표, 색상표, 그림 등)은 통째로 건너뛴다
SKIP_DESTINATIONS = {
    b"fonttbl", b"colortbl", b"stylesheet", b"info", b"pict", b"fldinst",
    b"header", b"footer", b"headerl", b"headerr", b"footerl", b"footerr",
    b"object", b"themedata", b"datastore", b"latentstyles", b"listtable", b"listoverridetable",
}
NEWLINE_WORDS = {b"par", b"line", b"row", b"sect", b"page"}
CONTROL_RE = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?")


def rtf_to_text(data: bytes) -> str:
    """국가법령정보센터 RTF 전용의 간단한 변환기.
    그림이 \\binN 원시 바이트로 들어 있어 일반 RTF 라이브러리가 본문을 놓치는 문제를 피한다."""
    out: list[str] = []
    stack: list[bool] = []  # 그룹별 '건너뛰기' 여부
    skip = False
    uc_skip = 1  # \uN 뒤에 오는 대체 문자 수
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == 0x7B:  # {
            stack.append(skip)
            i += 1
            if data.startswith(b"\\*", i):
                skip = True
            continue
        if c == 0x7D:  # }
            skip = stack.pop() if stack else False
            i += 1
            continue
        if c == 0x5C:  # backslash
            nxt = data[i + 1:i + 2]
            if nxt in (b"\\", b"{", b"}"):
                if not skip:
                    out.append(nxt.decode())
                i += 2
                continue
            if nxt == b"'":  # \'hh
                if not skip:
                    out.append(bytes([int(data[i + 2:i + 4], 16)]).decode("cp1252", "ignore"))
                i += 4
                continue
            m = CONTROL_RE.match(data, i)
            if not m:
                i += 2
                continue
            word, arg = m.group(1), m.group(2)
            i = m.end()
            if word == b"bin" and arg:
                i += int(arg)  # 원시 바이너리(그림) 건너뛰기
            elif word in SKIP_DESTINATIONS:
                skip = True
            elif word == b"uc" and arg:
                uc_skip = int(arg)
            elif word == b"u" and arg:
                if not skip:
                    code = int(arg)
                    out.append(chr(code + 65536 if code < 0 else code))
                i += uc_skip  # 대체 문자('?') 건너뛰기
            elif not skip:
                if word in NEWLINE_WORDS:
                    out.append("\n")
                elif word in (b"tab", b"cell"):
                    out.append(" ")
            continue
        if c in (0x0D, 0x0A):
            i += 1
            continue
        if not skip:
            out.append(chr(c))
        i += 1
    return "".join(out)


def convert(path: Path) -> str:
    raw = path.read_bytes()
    if not raw.lstrip().startswith(b"{\\rtf"):
        raise ValueError("RTF 형식이 아닙니다 (국가법령정보센터의 '저장 > 한글/워드' 파일을 사용하세요)")
    text = rtf_to_text(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip() + "\n"


def main(args: list[str]) -> int:
    paths: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            paths += [f for f in p.iterdir() if f.suffix.lower() in (".doc", ".rtf")]
        else:
            paths.append(p)
    if not paths:
        print(__doc__)
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for p in paths:
        name = target_name(p.name)
        if name is None:
            print(f"[건너뜀] 법령명을 알 수 없음: {p.name}")
            continue
        try:
            text = convert(p)
        except Exception as e:
            print(f"[실패] {p.name}: {e}")
            continue
        (RAW_DIR / name).write_text(text, encoding="utf-8")
        print(f"[OK] {p.name} → data/raw/{name} ({len(text):,}자)")
        ok += 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
