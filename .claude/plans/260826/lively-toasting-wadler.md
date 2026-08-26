# `docs/plan/`을 `.claude/plans/` 아래 날짜 폴더로 옮긴다

## Context

이 레포의 설계 기록은 지금 두 군데로 갈라져 있다. `docs/plan/`에 9개 문서(2026-07-25 ~ 08-25, 2,113줄)가 있고, `.claude/plans/`에 2개(08-25, 307줄)가 있다. 갈라진 이유는 내용이 달라서가 아니라 **작성된 경로가 달라서**다 — 앞의 것들은 손으로 쓴 계획 문서고, 뒤의 것들은 Claude Code 플랜 모드가 자동으로 떨군 파일이다. 둘 다 "이 변경을 왜 이렇게 했나"의 기록이고, 실제로 `260825_마찰면 목록.md`(docs/plan)와 `codex-validated-blum.md`(.claude/plans)는 **같은 PR #11의 산출물과 계획**이다.

한쪽으로 모으는 방향은 `.claude/`가 맞다. 이 레포의 설계 계약서인 `.claude/harness-spec.md`(149KB)가 이미 거기 있고, `docs/`는 사용자용 문서(`wiki/`)와 측정 데이터(`measurements/`)가 사는 곳이다. 계획 문서는 사용자가 읽을 것이 아니라 다음 세션이 읽을 것이다.

결과로 원하는 것: 라운드 하나가 남긴 문서들이 한 폴더에 모여 있고, 폴더 이름만 보고 시간 순서를 알 수 있는 상태.

## 폴더 구조

날짜(`YYMMDD`) 폴더로 나눈다. `docs/plan/`이 이미 `260801/`, `260802/`를 벌써 폴더로 쓰고 있었으므로 새 규칙이 아니라 기존 규칙의 완성이다.

**파일명은 바꾸지 않는다.** 옮기기만 한다.

```
.claude/plans/
├── README.md                                  ← 새로 씀 (아래 참조)
├── 260725/
│   └── codex-skill-implementation-plan.md
├── 260801/
│   ├── implementation-plan.md
│   ├── audit-findings.md
│   └── RESUME.md
├── 260802/
│   └── README.md
├── 260823/
│   ├── 260823_스킬 재작성.md
│   ├── skill-rewrite-inventory.md
│   └── help-audit-manifest.md
└── 260825/
    ├── 260825_마찰면 목록.md
    ├── codex-validated-blum.md                ← PR #11의 계획
    └── codex-fast-cuddly-fern.md              ← PR #13의 계획
```

날짜는 짐작이 아니라 `git log --diff-filter=A`로 확인한 최초 커밋 날짜다. `codex-validated-blum.md`는 PR #11(`60c235c`, 08-25), `codex-fast-cuddly-fern.md`는 PR #13(`b1e6bd3`, 08-25).

### 루트는 비우지 않는다 — 비울 수 없다

**Claude Code 플랜 모드는 새 플랜을 `.claude/plans/` 루트에 자동 생성된 이름으로 떨군다.** 이 세션에서 직접 관찰한 사실이다 — 하네스가 이 파일을 `lively-toasting-wadler.md`로 쓰라고 지정했다. 그래서 "모든 플랜은 날짜 폴더 안에"라는 규칙은 만든 순간부터 자동으로 깨진다.

규칙을 그 사실에 맞춘다:

- **루트 = 인박스.** 진행 중인 플랜이 자동 생성된 이름으로 떨어지는 자리.
- **`YYMMDD/` = 정리된 기록.** 작업이 머지되면 그 라운드의 문서들과 함께 날짜 폴더로 옮긴다.

이 플랜 파일 자신이 첫 사례가 된다. 지금은 루트에 있고, 이 작업이 머지될 때 `260826/`으로 들어간다.

`.claude/plans/README.md`에 이 두 줄 규칙만 적는다. 규칙이 어디에도 안 적혀 있으면 다음 세션에서 사라진다.

## 참조 갱신 — 이게 작업의 실체다

옮기는 것 자체는 `git mv` 11번이다. 실제 작업량은 `docs/plan` 문자열 **24곳**을 고치는 쪽에 있다.

**먼저 정정.** 이 세션 앞부분에서 "테스트는 docs/plan을 읽지 않는다"고 말했는데 틀렸다. 테스트가 경로를 조각으로 조립해서(`REPO / "docs" / "plan" / ...`) 문자열 grep에 안 걸렸을 뿐이다. 아래 두 줄을 안 고치면 스위트가 깨진다.

| 파일 | 곳 | 비고 |
|---|---|---|
| `tests/260823/test_help_audit_manifest.py` | 30 | `REPO / "docs" / "plan" / "help-audit-manifest.md"` → `REPO / ".claude" / "plans" / "260823" / ...` |
| `tests/260823/test_inventory_coverage.py` | 36 | `skill-rewrite-inventory.md`, 위와 같은 형태 |
| `.claude/harness-spec.md` | 11곳 | 14, 58, 188, 196, 409, 446, 450, 571, 578, 580, 582 |
| `.claude/plans/codex-validated-blum.md` | 4곳 | 18, 64, 79, 181 |
| `CHANGELOG.md` | 2곳 | 13, 15 |
| `docs/wiki/Architecture.md` | 2곳 | 70(산문), 61(레포 트리 다이어그램의 `├── plan/` 줄) |
| 옮겨지는 문서 내부 상호참조 | 6곳 | `260801/implementation-plan.md` 9·83, `260823_스킬 재작성.md` 40·48, `260802/README.md` 5, `260801/RESUME.md` 23 |

치환 규칙:

- `docs/plan/codex-skill-implementation-plan.md` → `.claude/plans/260725/codex-skill-implementation-plan.md`
- `docs/plan/260801/…` → `.claude/plans/260801/…` (`260802`도 동일)
- `docs/plan/260823_스킬 재작성.md` → `.claude/plans/260823/260823_스킬 재작성.md`
- `docs/plan/skill-rewrite-inventory.md`, `docs/plan/help-audit-manifest.md` → `.claude/plans/260823/…`
- `docs/plan/260825_마찰면 목록.md` → `.claude/plans/260825/260825_마찰면 목록.md`

일부 참조는 `implementation-plan.md:189`처럼 줄 앵커를 달고 있다. 내용은 안 바뀌므로 앵커는 그대로 유효하다.

`docs/wiki/Architecture.md:61`의 트리 다이어그램은 경로 치환이 아니라 구조 수정이다 — `docs/` 아래 `plan/` 줄을 지우고, `.claude/skills/codex/` 블록 근처에 `.claude/plans/`를 설계 기록 자리로 넣는다.

`CHANGELOG.md`는 과거 기록이라 손대는 게 망설여지는 자리인데, 여기 적힌 경로는 *지금 살아 있는 파일*을 가리키는 포인터다. 깨진 채 두는 쪽이 더 나쁘므로 고친다.

## 전달

**열려 있는 PR #14(`docs/track-claude-session-plans`)에 얹는다.** #14는 지금 `.claude/plans/`에 두 파일을 추가하는 것뿐인데, 그 두 파일이 이 이동의 대상이다. 따로 머지했다가 바로 옮기면 이력에 왕복이 남는다. 제목과 본문을 이 변경에 맞게 다시 쓴다.

새 제목: `docs: 설계 기록을 .claude/plans/ 아래 날짜 폴더로 모은다`

커밋은 두 개로 나눈다 — `git mv`만 한 커밋, 참조 갱신 한 커밋. 이동 커밋에 내용 변경이 섞이지 않아야 git이 rename으로 감지한다.

## 검증

1. `python3 -m unittest discover -s tests -p 'test_*.py'` — 이동 전 베이스라인을 먼저 잡고, 이동 후 같은 수치가 나오는지 본다. 두 테스트 파일의 경로를 고쳤으므로 여기서 걸리면 갱신이 빠진 것이다.
2. `grep -rn "docs/plan" . --include='*.md' --include='*.py'`(`.git`, `.claude/histories` 제외) — 결과가 **0줄**이어야 한다.
3. `ls docs/` — `measurements/`와 `wiki/`만 남고 `plan/`은 없어야 한다.
4. `git log --follow -- '.claude/plans/260801/implementation-plan.md'` — 2026-08-01 최초 커밋까지 이력이 이어지는지 확인한다. 안 이어지면 rename 감지가 실패한 것이고, 이동 커밋에 내용이 섞였다는 뜻이다.
5. `.claude/plans/260823/help-audit-manifest.md` 본문이 가리키는 `tests/260823/test_help_audit_manifest.py`는 안 움직이므로 그대로 유효한지 눈으로 한 번 확인.
