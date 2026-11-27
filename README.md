# CU-LawBot — 개인정보·신용정보 법령 QnA 챗봇

개인정보 보호법·신용정보법(법률 및 시행령)을 바탕으로 만든 **RAG 기반 QnA 챗봇**입니다.
신협 직원이 업무 중에 개인정보·신용정보 처리 기준을 빠르게 확인할 수 있도록 근거 조문과 함께 답변합니다.

> ⚠️ 본 답변은 참고용이며 법률 자문이 아닙니다. 최신 법령과 준법감시부서 확인이 필요합니다.

## 구조
```
├─ app/              # FastAPI 서버 + 웹 UI
│  ├─ main.py
│  ├─ rag.py
│  └─ static/index.html
├─ scripts/          # 데이터 파이프라인 (번호 순서대로 실행)
│  ├─ 01_parse_law.py      # 법령 원문 → 조문 JSONL
│  ├─ 02_generate_qna.py   # 조문 → 가상 QnA JSONL
│  └─ 03_build_index.py    # 임베딩 → ChromaDB
├─ data/
│  ├─ raw/           # 법령 원문 (국가법령정보센터)
│  ├─ processed/     # 조문 단위 청크
│  └─ qna/           # 생성된 가상 QnA
├─ docs/
│  ├─ WORK_PLAN.md   # 작업계획서
│  └─ REPO_GUIDE.md  # 레포 구성·협업 규칙 (팀원 필독)
└─ vectordb/         # 로컬 벡터DB (git 제외)
```

## 실행 방법

### 1. 환경 준비
```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # .env에 API 키 입력 (절대 커밋 금지)
```

### 2. 법령 원문 준비
[국가법령정보센터](https://www.law.go.kr)에서 아래 4개 법령의 본문을 복사해 `data/raw/`에 txt 파일로 저장합니다.
파일 맨 위에 `[시행 2025. 3. 13.]` 같은 시행일 줄을 같이 넣어 두면 시행일도 함께 저장됩니다.

| 파일명 | 법령 |
|---|---|
| `개인정보보호법.txt` | 개인정보 보호법 |
| `개인정보보호법_시행령.txt` | 개인정보 보호법 시행령 |
| `신용정보법.txt` | 신용정보의 이용 및 보호에 관한 법률 |
| `신용정보법_시행령.txt` | 신용정보의 이용 및 보호에 관한 법률 시행령 |

### 3. 데이터 파이프라인
```powershell
python scripts/01_parse_law.py                 # 조문 단위 파싱 → data/processed/articles.jsonl
python scripts/02_generate_qna.py --limit 3    # 먼저 3개 조문만 생성해서 품질 확인
python scripts/02_generate_qna.py              # 나머지 전체 생성 (이어쓰기 지원) → data/qna/qna.jsonl
python scripts/03_build_index.py               # 임베딩 → vectordb/
```
- `02`는 이미 생성된 조문을 건너뛰므로, 중간에 멈추거나 실패해도 다시 실행하면 이어서 처리합니다.
- `03`을 처음 실행하면 임베딩 모델(bge-m3, 약 2GB)을 내려받습니다.

### 4. 웹 서버 실행
```powershell
uvicorn app.main:app --reload
```
브라우저에서 http://localhost:8000 접속

### 문제 해결
- **`OSError: [WinError 126] ... torch\lib\shm.dll`**: PC의 Visual C++ 런타임이 오래돼서 생깁니다. [Visual C++ 재배포 패키지(x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)를 설치한 뒤 터미널을 새로 열고 다시 실행하세요.
- **`Failed to parse URL from /api/chat`**: `index.html`을 파일로 직접 연 경우입니다. 서버를 실행한 뒤 http://localhost:8000 으로 접속하세요.

## API (사내 시스템 연동)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 채팅 화면 (사내 포털에 `<iframe>`으로 삽입 가능) |
| GET | `/api/health` | 준비 상태, 벡터DB 문서 수 |
| POST | `/api/chat` | 질문 → 답변 (스트리밍) |

`POST /api/chat` 요청:
```json
{"question": "대출 상담 시 신용조회 동의가 필요한가요?", "history": []}
```
응답은 한 줄에 JSON 하나씩 오는 NDJSON 스트림입니다.
```
{"type": "sources", "sources": [{"law": "...", "article": "제32조", "title": "...", "text": "...", "score": 0.81, ...}]}
{"type": "delta", "text": "네, "}
{"type": "delta", "text": "미리 개별적으로 동의를 받아야 합니다..."}
{"type": "done"}
```
오류가 나면 `{"type": "error", "message": "..."}`가 옵니다.

**답변 방식**: 질문과 비슷한 조문·가상 QnA를 검색한 뒤, 가상 QnA는 조문을 찾는 데만 쓰고 LLM에게는 **조문 원문**만 근거로 줍니다. 유사도가 `MIN_SCORE`보다 낮으면 LLM을 호출하지 않고 "관련 조문 없음"으로 답합니다.

## QnA 데이터 형식 (`data/qna/qna.jsonl`)
```json
{"id": "PIPA-15-001", "law": "개인정보 보호법", "article": "제15조", "title": "개인정보의 수집·이용",
 "question": "조합원 가입 시 휴대전화번호를 받으려면 동의가 필요한가요?",
 "answer": "...", "category": "수집·이용", "effective_date": "YYYY-MM-DD"}
```

## 기술 스택
Python 3.11 · FastAPI · ChromaDB · bge-m3 (임베딩) · Claude API (LLM) · HTML/JS

## 데이터 출처
- 국가법령정보센터 (https://www.law.go.kr) — 개인정보 보호법, 같은 법 시행령, 신용정보의 이용 및 보호에 관한 법률, 같은 법 시행령
- QnA 데이터는 모두 LLM으로 생성한 **가상 데이터**이며 실제 개인정보를 포함하지 않습니다.
