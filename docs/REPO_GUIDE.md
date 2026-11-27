# 레포 구성 가이드 — CU-LawBot

팀원 모두가 같은 방식으로 작업하기 위한 GitHub 운영 규칙입니다. 처음 합류하면 이 문서부터 읽어 주세요.

---

## 1. 기본 원칙

- **레포는 하나만 씁니다.** 데이터, 백엔드, 화면을 모두 `qna-bot` 레포 하나에서 관리합니다.
- **역할별로 폴더를 나눕니다.** 각자 자기 폴더만 수정하면 충돌이 거의 생기지 않습니다.
- **`master`에는 직접 push하지 않습니다.** 모든 변경은 브랜치 → PR → 리뷰 → 병합 순서로 들어갑니다.
- **API 키와 실제 개인정보는 절대 올리지 않습니다.** 공개 레포이므로 한 번 올라가면 지워도 기록이 남습니다.

---

## 2. 올가니제이션과 레포

```
privacybot20261127/
└─ qna-bot     (Public)   ← 프로젝트 레포 (제출용)
```

| 항목 | 설정 |
|---|---|
| 레포 이름 | `qna-bot` |
| 공개 여부 | Public (과제 요구사항) |
| 기본 브랜치 | `master` |
| 팀 | `lawbot-dev` 팀 생성 후 레포에 **Write** 권한으로 연결 |
| 관리자 | PM 1~2명만 **Admin** |

> 회사 공식 GitHub 조직에 공개 레포를 만들 때는 사내 보안·대외공개 규정을 먼저 확인합니다.

---

## 3. 폴더 구조와 담당자

| 폴더 / 파일 | 내용 | 담당 | 작업 브랜치 |
|---|---|---|---|
| `docs/`, `README.md` | 작업계획서, 레포 가이드, 평가 결과, 발표 자료 | ① PM / 기획 | `docs/*` |
| `data/raw/` | 법령 원문 4종 (국가법령정보센터) | ② 데이터 | `feat/data-qna` |
| `data/processed/`, `data/qna/` | 조문 JSONL, 가상 QnA JSONL | ② 데이터 | `feat/data-qna` |
| `scripts/01_parse_law.py`, `02_generate_qna.py` | 조문 파싱, QnA 생성 | ② 데이터 | `feat/data-qna` |
| `scripts/03_build_index.py` | 임베딩, 벡터DB 구축 | ③ AI / 백엔드 | `feat/rag-api` |
| `app/main.py`, `app/rag.py` | 답변 API, 검색·프롬프트 | ③ AI / 백엔드 | `feat/rag-api` |
| `app/static/` | 채팅 웹 화면 | ④ 프론트 / QA | `feat/web-ui` |
| `docs/eval.md` | 테스트 질문 20개 평가 결과 | ④ 프론트 / QA | `feat/web-ui` |
| `.github/` | PR·이슈 템플릿 | ① PM | `docs/*` |
| `vectordb/`, `.env` | 로컬 전용 (**git 제외**) | — | — |

다른 사람의 폴더를 고쳐야 하면 PR에서 그 담당자를 리뷰어로 지정합니다.

---

## 4. 브랜치 전략

```
master  (보호됨, PR로만 병합)
 ├─ feat/data-qna    ② 데이터
 ├─ feat/rag-api     ③ AI / 백엔드
 ├─ feat/web-ui      ④ 프론트 / QA
 ├─ docs/readme      ① PM
 └─ fix/<내용>        버그 수정 (누구나)
```

- 브랜치 이름: `종류/짧은-설명` (영문 소문자, 하이픈)
- 작업 시작 전 항상 최신 `master`를 받습니다.
- 하루짜리 프로젝트이므로 브랜치는 오래 두지 말고 **작은 단위로 자주 병합**합니다.

---

## 5. 커밋 메시지 규칙

```
<종류>: <한 줄 요약>
```

| 종류 | 언제 | 예시 |
|---|---|---|
| `feat` | 기능 추가 | `feat: 근거 조문 펼쳐보기 추가` |
| `fix` | 버그 수정 | `fix: 삭제된 조문이 파싱되는 문제 수정` |
| `data` | 데이터 추가·수정 | `data: 신용정보법 QnA 210건 추가` |
| `docs` | 문서 | `docs: 실행 방법 보완` |
| `chore` | 설정, 기타 | `chore: requirements 정리` |

---

## 6. 작업 흐름 (이슈 → PR → 병합)

1. **이슈 등록:** 작업계획서 일정표의 각 행을 이슈로 만듭니다. "작업" 템플릿을 쓰고, 담당자와 라벨을 지정합니다.
2. **브랜치 생성:** 최신 `master`에서 자기 브랜치를 만듭니다.
3. **작업 및 커밋:** 커밋 전에 `git status`로 `.env`가 들어가지 않았는지 확인합니다.
4. **PR 생성:** PR 템플릿을 채우고 본문에 `Closes #이슈번호`를 적습니다.
5. **리뷰:** 1명 이상이 승인해야 병합할 수 있습니다.
6. **병합:** Squash merge로 합친 뒤 브랜치를 삭제합니다.

**이슈 라벨:** `data` · `backend` · `frontend` · `docs` · `bug`

**Projects 보드:** Todo → In Progress → Review → Done

---

## 7. 레포 설정 체크리스트 (PM이 처음 한 번)

- [x] 올가니제이션에 Public 레포 `qna-bot` 생성 (완료)
- [ ] 로컬 프로젝트 첫 커밋 후 push
- [ ] Settings → Branches → `master` 보호 규칙
  - [ ] Require a pull request before merging (승인 1명)
  - [ ] Block force pushes
- [ ] Settings → Code security → **Secret scanning**, **Push protection** 켜기
- [ ] Settings → Collaborators and teams → `lawbot-dev` 팀에 Write 권한
- [ ] Issues 라벨 5개 생성
- [ ] Projects 보드 생성, 일정표 작업을 이슈로 등록
- [ ] (선택) 팀원 GitHub 아이디가 정해지면 `.github/CODEOWNERS` 추가

---

## 8. 자주 쓰는 명령

처음 한 번 (PM):
```powershell
git add .
git commit -m "chore: 프로젝트 초기 구조 및 작업계획서"
git remote add origin https://github.com/privacybot20261127/qna-bot.git
git push -u origin master
```

팀원 처음 한 번:
```powershell
git clone https://github.com/privacybot20261127/qna-bot.git
cd qna-bot
copy .env.example .env      # 각자 API 키 입력
```

작업할 때마다:
```powershell
git switch master
git pull
git switch -c feat/web-ui   # 이미 있으면: git switch feat/web-ui
# ... 작업 ...
git status                  # .env가 목록에 없는지 확인
git add <파일>
git commit -m "feat: 채팅 화면 기본 레이아웃"
git push -u origin feat/web-ui
```
push 후 GitHub에서 **Compare & pull request**를 눌러 PR을 만듭니다.

---

## 9. 보안 규칙

| 하지 말 것 | 대신 할 것 |
|---|---|
| `.env` 커밋, 코드에 API 키 직접 입력 | `.env`에만 저장하고 `os.getenv()`로 읽기 |
| 실제 조합원 정보, 내부 문서 사용 | 공개 법령 원문과 LLM으로 만든 가상 QnA만 사용 |
| `git add .` 후 확인 없이 커밋 | 커밋 전 `git status`로 파일 목록 확인 |

**키가 실수로 올라갔다면**
1. 즉시 Anthropic Console에서 해당 키를 **폐기(revoke)** 하고 새 키를 발급합니다.
2. PM에게 알립니다.

커밋을 지워도 공개 레포에서는 이미 노출된 것으로 봐야 하므로, 키 폐기가 먼저입니다.

---

## 10. 당일 병합 체크포인트 (11/27)

| 시각 | `master`에 들어와 있어야 할 것 |
|---|---|
| 09:30 | 초기 구조, 작업계획서, 레포 가이드 |
| 12:00 | 법령 원문, 조문 JSONL, QnA 일부 (`feat/data-qna`) |
| 15:30 | 벡터DB 스크립트, 답변 API (`feat/rag-api`) |
| 16:30 | 채팅 화면 (`feat/web-ui`) |
| 17:00 | 평가 결과, README 최종본 — **이후 `master` 동결, 시연은 `master` 기준** |
