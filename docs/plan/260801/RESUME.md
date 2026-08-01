# 이어서 하기 — v0.2.0 구현 (2026-08-01 세션 중단 지점)

## 지금 상태

브랜치 `feat/batch-orchestration`, 트리 깨끗, **테스트 161개 전부 통과**, `validate_harness.py` 0 오류.

| 마일스톤 | 상태 |
|---|---|
| M0 저장소 정리 | ✅ `5e02357`, `8a4288b`, `5ec4c1d` |
| M0.5 실측 V-11~V-18 | ✅ `361be0a` — **두 blocker 모두 통과**, `harness-spec.md`에 기록 |
| M1 레지스트리 동시성 | ✅ `402d43b` — F1을 240회 중 152회로 재현 후 수정 |
| M2 훅/`--detach`/`--all-mine` 제거 | ✅ `3c2ed0b` |
| M3 단일 런 결함 8건 + `--timeout` 백그라운드화 | ✅ `d90d57e` `a00b8b3` `da81954` `7d45899` `e20798a` `2f59a0f` |
| **M4a** batch start·매니페스트·`--group` | ✅ `3a400d5` |
| M4b worktree·`batch clean`·프리앰블 | ⬜ **다음** |
| M4c `--resume-from` | ⬜ |
| M5 문서 | ⬜ |
| M6 검증 T1/T2/T4 | ⬜ |
| M7 릴리즈 v0.2.0 | ⬜ |

정본 계획: `docs/plan/260801/implementation-plan.md`(D01~D33) + `~/.claude/plans/docs-plan-260801-expressive-sparkle.md`(D34~D37, §1의 추가 수정 항목, 실행 순서, §3.5 오케스트레이션 방식).

## 재개하자마자 할 일

**1. M4a 리뷰 결과를 먼저 회수한다.** 중단 시점에 3개 렌즈(concurrency / contract / conformance)의 적대적 리뷰가 백그라운드에서 돌고 있었다. 결과는 여기에 있다:

```
/Users/seongjin/.claude/projects/-Users-seongjin-Coding-codex-in-claude/7410f49d-75f1-48ff-8c3f-3091259099be/subagents/workflows/wf_03119ab4-b96/journal.jsonl
```

`{"type":"result",...}` 줄마다 한 에이전트의 `{lens, findings[]}`가 들어 있다. 각 finding은 `severity`/`file`/`summary`/`failure_scenario`를 갖는다. **구체적 실패 시나리오가 붙은 것만 조치한다** — 스타일 의견은 finding이 아니라고 프롬프트에 못박아뒀다.

리뷰어에게 특별히 파보라고 지시한 것들이라 이 중에 진짜가 있을 가능성이 높다:
- `_batch.py`의 `write_members` tmp 이름이 writer마다 고유한가 — 바로 앞 커밋(M1)이 `meta.json`에서 고친 바로 그 버그를 재도입했을 수 있다.
- `claim_group`과 `write_members` 사이에서 `batch start`가 죽으면 멤버 없는 그룹이 이름만 점유한다.
- `follow_group`이 레지스트리를 변경하는가 (`cmd_status`는 `run_row` → `reap`으로 매 틱 쓴다).
- `overlaps`·`totals`·`known_groups`·`candidates`가 무한정 커질 수 있는가 (컨텍스트 규율).
- `changed_paths`가 멤버마다 이벤트 스트림 전체를 읽는다 — 8개 그룹에서 비용.
- `GROUP_MESSAGE_CAP = 4000`과 `projected_cost`의 10/3 표본 임계값에 근거가 붙어 있는가.

**2. 그다음 M4b.** 계획 §4 + 실행계획 §1.4·§1.5·§1.7:
- worktree **멤버 단위** 배정(D35): write 멤버가 2개 이상일 때 write 멤버에만. `read-only`/`kind: review`는 호출자 cwd 그대로 — V-15가 신선한 detached worktree의 `git diff HEAD`가 0줄임을 실측했다. `--tasks-file`의 항목별 `cwd`가 명시되면 worktree 배정보다 우선. `resume` 멤버는 상속만(`--cwd`가 `start`에만 등록돼 있다).
- `git worktree add --detach <project>/.codex-runs/<run_id>/wt <base>`. V-13이 본 트리 `git status`가 깨끗하게 유지됨을 확인했다.
- `batch clean --group` 거부 조건 **넷**: 비종료 멤버 / 더러운 worktree / **파생 그룹 존재**(`_batch.derived_groups`가 이미 있다) / `--force`로만 통과. `git worktree remove`가 더러운 worktree를 이미 거부한다(V-13 실측) — 직접 검사를 짜기 전에 git이 하는 일을 먼저 쓸 것.
- §4.4 배치 프리앰블. `apply_preamble(prompt, enabled)`이 배치 사실을 모르므로 `batch=` 인자를 받아야 한다. **V-18이 이걸 강하게 정당화한다**: 프리앰블 없이 Codex가 *"사용자와 같은 트리를 보고 있다"*고 자신 있게 틀린 말을 했고, 있으면 정확히 답했다. 비용 113 토큰.
- `doctor`: `.codex-runs` 크기 + 잔존 worktree 개수 보고(정책 없이 사실만). cwd 공유 경고는 **반드시 `meta["cwd"]`로 비교** — `git_toplevel`을 쓰면 한 저장소의 모든 worktree가 같은 값이라 모든 배치에서 경고가 뜬다.

## 남은 체크포인트

- 🛑 **C** (M5 뒤): SKILL.md `description`이 바이트 단위로 동일한지 확인 + `orchestration.md`를 **별도 에이전트**가 D31("메커니즘 + 가처만, 페이즈 패턴 카탈로그 금지") 기준으로 감사. 쓴 사람이 스스로 볼 수 없는 종류의 결함이다.
- 🛑 **D** (M6의 T2/T4 앞): 예산 확인. 사용자가 "전부 진행, 병목에서만 확인"으로 답한 그 병목이 여기다. **다음 세션은 비용보다 품질 우선으로 진행하기로 했으므로, 이 체크포인트는 보고만 하고 멈추지 않아도 된다.**

## 절대 건드리지 말 것

`audit-findings.md` §2 전체. 특히:
- `stop`의 프로세스 그룹 전용 방식(이름 매칭 금지 — B8)
- `signal_run`의 SIGINT → SIGTERM → SIGKILL 사다리 (실제 검증됨)
- `doctor`의 exit 0/2 프로토콜
- **SKILL.md의 `description`과 `allowed-tools`** — 헤드리스 e2e로 검증된 경계다. T4에서 배치 프롬프트가 발화하지 않는 것이 실측될 때만, 최소한으로, 재검증과 함께 고친다.

## 작업 방식 (사용자 지시)

dynamic workflow를 적극 사용하되 서브에이전트 모델은 **`sonnet` 고정**(`agent(..., {model: 'sonnet'})`). 팬아웃은 대상이 실제로 독립일 때만 — M4b/M4c는 **팬아웃 금지**(새 서브시스템을 여럿이 나눠 쓰면 설계가 갈라진다), 메인 스레드가 쓰고 리뷰 에이전트를 다른 렌즈로 붙인다.

**가처:** `isolation: 'worktree'`는 HEAD가 아니라 **기본 브랜치(`main`)**에서 worktree를 자른다. 이 세션에서 에이전트 5개가 M0·M1도 계획 문서도 없는 기준선 위에서 작업할 뻔했다. 에이전트에게 `git worktree add -b <branch> "$REPO/.wt/<slug>" <BASE_SHA>`를 명시적으로 시킬 것. `.wt/`는 이미 gitignore에 있다.
