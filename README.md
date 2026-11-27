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
