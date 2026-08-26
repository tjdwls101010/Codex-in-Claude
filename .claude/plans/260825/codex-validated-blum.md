# 코덱스 런 대기를 "무장된 대기"로 만든다

## Context

`codex` 스킬은 Codex를 **관리형 서브에이전트**로 부리는 것이 목표다. Claude가 서브에이전트를 띄우면 "완료되면 자동으로 알림이 간다"가 계약인 것처럼, Codex 위임도 같은 감각이어야 한다. 그런데 관찰된 실제 행동은 다르다 — 백그라운드로 띄워놓고 Claude가 잠자코 있는다.

원인은 "스킬이 그렇게 말하지 않아서"가 아니다. 세 겹이다.

1. **대기 교리가 잘못된 제목 아래 있다.** `SKILL.md`의 *"how you wait depends on whether you get another turn"* / *"never end a turn on a promise"*는 정확히 필요한 문장인데, **`## Collecting a batch` 절 안에만** 있다. 단일 `start` 위임은 저 문단을 읽을 이유가 없다. `--help`도 같은 비대칭이다 — `batch start`에는 *"Waiting for it, and collecting it"* epilog이 있고, `start`/`resume`/`review`에는 epilog이 아예 없다.

2. **유일한 구체 예시가 반대 행동을 가르친다.** `SKILL.md:53-60`의 흐름 예시는 `log --since 0` → `log --since 4213`, 즉 **손으로 폴링하는 그림**이다. 문서에서 제일 모방하기 쉬운 블록이 문제의 행동을 시연하고 있다.

3. **처방된 메커니즘 자체가 틀렸을 가능성이 높다.** `SKILL.md`는 *"pair it with the **Monitor** tool"*이라고 말하는데, Monitor 자신의 계약은 이렇다.
   - *"**One** ('tell me when the build finishes') → use **Bash with `run_in_background`**"* / *"**Don't use an unbounded command for a single notification.**"* → "코덱스 끝나면 알려줘"는 알림 1개짜리라 Monitor가 아니라 백그라운드 Bash가 맞는 도구다.
   - `timeout_ms` **기본값 300,000ms(5분)**, `persistent: true`가 없으면 거기서 죽는다. 코덱스 런은 5분을 넘긴다. `SKILL.md`는 `persistent`도 `timeout_ms`도 언급하지 않는다 — **5분 뒤 워처가 죽고 완료 알림이 영영 안 오는 것**이 관찰된 침묵의 유력한 정체다.
   - *"Monitors that produce too many events are automatically stopped"* — `log --follow`는 이벤트마다 한 줄을 뱉는다.

   원 설계 근거(`docs/plan/260801/implementation-plan.md:189`)는 *"Bash 600초 상한을 블로킹으로 못 넘어서 Monitor"*였다. **600초 상한은 포그라운드 Bash의 것**이고, `run_in_background`는 턴을 넘겨 살아남으며 종료 시 알림을 보낸다. 전제가 틀렸고, 필요 없는 도구를 집었다.

**결과물**: 단일 런이든 배치든, `start` 직후 워처를 무장하는 것이 기본 관용구가 되고, 도구가 말할 수 있는 반환 계약은 `--help`가, 호스트 의존 사실은 프로즈가 갖는 스킬.

### 합격 기준

목표는 "대기 절을 고친다"가 아니라 **Codex가 네이티브 통합 도구처럼 쓰인다**는 것이다. 그러려면 (1) 잘 작동하고 (2) 쓰는 데 헷갈림도 병목도 없어야 한다. 이 계획의 합격선은 그래서 문서가 고쳐졌는지가 아니라 **Phase 6의 e2e (b) 시나리오** — 병렬할 일이 없는 평범한 위임에서, Claude가 멈추지도 지어내지도 약속하지도 않는지 — 다. 지금 결함이 정확히 거기서 난다.

"병목이 일체 없어야 한다"는 기준은 대기 하나로 끝나지 않으므로, 나머지 마찰면도 **추정하지 말고 목록으로 만들어** 성진에게 판단을 넘긴다 (Phase 0b). 이번 패스에서 전부 고치지는 않는다 — 근거 없이 넓히는 것은 이 레포가 R-기록으로 남겨온 실패 방식이다.

## 결정된 것

- **실측 후 확정.** Monitor→백그라운드 Bash 정정은 e2e로 검증된 결정(V-17/R15)을 뒤집는다. 이 레포의 R10~R55는 전부 "돌려서 알았다"이므로 같은 바를 지킨다.
- **범위**: 프로즈 + `start`/`resume`/`review` epilog + `tests/260823` 관례의 기계 검사 + `harness-spec.md`.
- **교리 강도**: 기본 관용구 하나 + 예외 둘. 레일이 아니라 원칙 — 이유를 붙여 예상 못 한 경우도 재도출 가능하게.
- **구현은 `tdd` 스킬로 — 단, 테스트가 있는 부분에만.** 아래 "TDD를 어디에 적용하나" 참조. 테스트는 `tests/260823/`(기존 파일 확장 우선).
- 진행은 `TaskCreate` 트래커로 (파일 바꾸는 단계 5개).

---

## Phase 0 — 실측 (코드 변경 전, 결과가 문장을 정한다)

세 프로브 중 실제 Codex 런이 필요한 건 하나뿐이다. 나머지는 호스트 동작이라 `sleep`으로 싸게 잡는다.

| 프로브 | 무엇을 묻나 | 방법 | 이게 정하는 문장 |
|---|---|---|---|
| **P1** | 백그라운드 Bash `log --follow`가 런 종료 시 정말 Claude를 깨우나? 지연은? 출력은 어디서 읽나? | 짧은 Codex 런 1회 `start` → 즉시 `log --run <id> --follow --level compact`를 `run_in_background: true`로. 알림 도착 여부·시각·터미널 줄 확인 | 기본 관용구 전체. 실패하면 Monitor로 되돌아가고 계획 전면 재검토 |
| **P2** | Bash의 `timeout`(기본 120s/최대 600s)이 `run_in_background`에도 걸리나? | `run_in_background`로 `sleep 200; echo done`. 200초 뒤 알림이 오는지, 120초에 죽는지 | 걸린다면 백그라운드 Bash는 긴 런에 못 쓰고 `--follow-timeout` 재무장 루프 또는 Monitor가 필요해진다 — **계획의 최대 리스크** |
| **P3** | Monitor 기본 5분 만료가 호출자에게 어떻게 보이나? 완료와 구별되나? | Monitor(`command: sleep 400; echo done`, 기본 `timeout_ms`). 5분 시점 관찰 | "5분 만료가 침묵의 정체"라는 주장을 사실로 확정하거나 철회 |
| **P4** | `log --follow --level compact`가 한 런에서 뱉는 줄 수 — Monitor 자동중단 임계에 걸리나? | 기존 `.codex-runs/*/events.jsonl`에 compact 필터를 오프라인 적용해 줄 수 분포. 새 런 불필요 | Monitor 예외 절에 붙일 경고의 유무 |
| **P5** | 이미 terminal인 런에 `log --follow`를 걸면 즉시 터미널 줄 찍고 나오나? | 기존 완료 런에 실행 | "무장은 언제 걸어도 안전하다"를 말할 수 있는지 |

**P2가 이 계획의 급소다.** `timeout`이 백그라운드에도 적용되면 관용구가 바뀐다. P2를 P1보다 먼저 돌린다 (더 싸고, P1의 해석을 좌우한다).

측정 결과는 `harness-spec.md`의 V-표에 V-19~V-23으로 기록한다.

### Phase 0b — 나머지 마찰면 목록 (고치지 않고 적기만)

대기는 관찰된 병목 하나일 뿐이다. "헷갈림·병목 일체 없음"이 기준이면 나머지도 봐야 하는데, 근거 없이 고치면 이 레포가 R-기록으로 남겨온 실패를 반복한다. 그래서 **한 번의 T5식 통과**(실제 CLI를 평범하게 써 보기)로 마찰 지점만 적고, 무엇을 고칠지는 성진이 정한다.

이미 눈에 띈 후보 셋 — 목록의 시작점이지 결론이 아니다:

- **`--help` 왕복 비용.** `SKILL.md`는 옵션 표면을 전부 `$CODEX <command> --help`로 미룬다. 정확성 면에서는 옳은 결정(#9)이지만, 쓰는 시점마다 왕복이 하나 붙는다. 실제로 무는지, 무는다면 최상위 `--help`의 한 줄 요약으로 흡수 가능한지.
- **첫 호출의 경로·권한 gotcha.** 절대 경로 + 한 줄 명령이라는 제약은 문서 맨 앞 두 문단을 차지한다. 어기면 매 호출 승인 프롬프트 — 정의상 병목이다. 기계로 잡히는지(훅 등) 볼 가치가 있다.
- **`thread_id: null`.** 정상 반환인데 호출자가 실패로 읽기 쉽다. Phase 1이 epilog으로 옮기는 것으로 충분한지, 아니면 출력 자체가 말해야 하는지.

산출물은 `docs/plan/`의 짧은 목록 하나. 그 이상 진행하지 않는다.

---

## Phase 1 — `--help`: `start`/`resume`/`review` epilog

`codex_bridge.py`의 세 파서에 epilog 추가. `batch start` epilog과 대칭.

**들어가는 것 (전부 도구 소유 사실):**
- 반환 시점 — 핸들이 생겼을 때이지 턴이 끝났을 때가 아니다.
- `thread_id: null`이 정상 반환이라는 것 (`_run.py`의 `THREAD_ID_WAIT` 루프는 thread id 없이도 빠져나온다). 기존 gotcha 목록에 이미 있는 항목이니 **여기로 이동**하고 프로즈에서는 뺀다.
- **끝남을 알려주는 것이 아무것도 없다** — 콜백도 파일 감시도 없고, `supervise()`는 `meta.json`에 쓸 뿐이다. 물어봐야만 안다.
- 끝날 때 같이 끝나는 표면은 `log --run <id> --follow` 하나이고, 모든 terminal state에 줄이 있다.
- `result --run <id>`는 별도 호출 — *"a run that finished is not a run you have read"* (배치 epilog의 문장과 대칭).

**들어가지 않는 것**: Monitor, 백그라운드 Bash, 턴 수명, 600초. 전부 호스트 의존 → 프로즈. `docs/plan/260823_스킬 재작성.md:73`의 결정("`status --follow`의 Monitor/Bash 600초 안내는 호스트 의존 → 프로즈")을 그대로 지킨다.

**검증 규율 (260823의 교훈, R55)**: epilog의 모든 문장은 "검증 전 주장"이다. 초안을 쓴 뒤 `_run.py:create_run`·`_codex.py:supervise`/`spawn_supervised`·`_events.py`와 대조하고, 대조된 문장만 넣는다. 1차 이전 때 10문장 중 7개가 코드와 달랐다.

파일: `.claude/skills/codex/scripts/codex_bridge.py`

---

## Phase 2 — `SKILL.md`: 대기 절을 런 수준으로 승격

### 2a. `## Collecting a batch` → 런 수준 절로 재작성

현재 배치 전용인 절을 **모든 런**을 덮게 다시 쓴다. 배치는 N-케이스로 안에 들어간다.

**원칙 한 줄**: 금지 대상은 기다림이 아니라 **아무것도 깨워주지 않는 침묵**이다. 대기는 무장돼 있어야 한다.

**기본 관용구 (이유와 함께)**: `start`가 돌아오면 곧바로 `log --run <id> --follow`를 백그라운드 Bash로 건다. 이게 Agent 도구의 자동 완료 알림과 등가물이고, Codex를 서브에이전트처럼 부린다는 게 실제로 뜻하는 것이다. 그러고 나서 — 병렬할 일이 **있으면** 한다, **없으면** 무장된 채로 턴을 돌려준다. 없는 일을 지어내지 않는다: 요청받지 않은 토큰을 쓰고, 같은 디렉터리 동시 writer gotcha를 밟는다.

**예외 1 — 턴이 하나뿐이면 (헤드리스)**: 무장은 소용없다. 팔로워가 턴과 함께 죽는다. 포그라운드 `--follow`로 블로킹하고 `--follow-timeout`으로 경계를 준다. (R15가 측정한 실패. 유지.)

**예외 2 — 런 *도중에* 깨어나야 하면**: 조기 실패 감지처럼 이벤트마다 알림이 필요할 때만 Monitor. 그때는 **`persistent: true`가 필수** — 기본 `timeout_ms`는 5분이고 코덱스 런은 그걸 넘긴다. (P3이 확정하면 실측 문장으로, 아니면 계약 인용으로.)

**정정을 명시한다**: 완료 알림 하나면 Monitor가 아니라 백그라운드 Bash. Monitor 자신의 계약이 그렇게 말한다. 이건 이전 문서가 틀렸던 자리이므로 조용히 고치지 않고 이유를 남긴다.

### 2b. 흐름 예시 교체 (`SKILL.md:53-60`)

폴링 그림을 무장 그림으로 바꾼다. `--since`는 없애지 않되 **중간에 확인할 때** 쓰는 것으로 자리를 옮긴다 — 주된 그림이 아니라.

```bash
$CODEX start --label refactor "…"              # → run_id, thread_id, 즉시
# ↓ 곧바로 무장한다 (백그라운드 Bash). 끝나면 알림이 온다.
$CODEX log --run <id> --follow --level compact
$CODEX log --run <id> --since <cursor>         # 중간에 들여다볼 때만
$CODEX stop --run <id>                         # 잘못 가고 있으면
$CODEX resume <id> "Stop rewriting tests — …"  # 같은 스레드에서 교정
$CODEX result --run <id>                       # 결론
```

### 2c. 프로즈에서 빼는 것

`thread_id: null` gotcha는 Phase 1에서 epilog으로 이동 → 프로즈에서 삭제 (두 벌은 포크다).

### 2d. 팔로워 출력을 어디서 읽나

이 환경에 `TaskOutput`/`TaskList` 도구는 없다. 백그라운드 작업의 출력은 하네스가 알려주는 파일 경로를 `Read`로 읽는다. **P1이 확인해주면** 한 줄 넣고, 아니면 넣지 않는다.

**줄 수 예산**: 현재 107줄, 260823 목표값 ~120줄. 이 절은 7줄 → ~20줄로 늘고 2c가 조금 줄이므로 ~120줄 안. 완료 기준은 아니다.

파일: `.claude/skills/codex/SKILL.md`

---

## Phase 3 — 위키 동기화

같은 틀린 문장이 두 곳에 더 있다. 프로즈 정정과 **같은 커밋**에서 고친다.

- `docs/wiki/Orchestration.md:110` — *"Pair it with Claude Code's **Monitor** tool rather than a foreground Bash call: Bash caps out at 600 seconds"* ← 정확히 그 틀린 전제.
- `docs/wiki/Orchestration.md:114` — 대기 방식 문단. 단일 런까지 덮게.
- `docs/wiki/CLI-Reference.md:98` — `--follow` 행의 *"Pair with the Monitor tool"*.

---

## Phase 4 — 기계 검사

`tests/260823/` 기존 파일 확장 (새 파일 최소화). 공개 경계만 — 실제 subprocess `--help` 텍스트와 문서 텍스트.

1. **`test_help_owns_its_facts.py`** — `FACTS`에 세 행 추가: `start`/`resume`/`review` epilog이 반환 계약을 담고 있는가 (필수 부분문자열 몇 개씩, 문구는 편집 가능하게 느슨히).
2. **`test_prose_does_not_restate.py`** — `RESTATEMENTS`에 한 행 추가: 반환 계약·`thread_id: null`을 프로즈가 다시 말하지 않는가.
3. **새 검사 — Monitor 언급은 `persistent`를 동반한다.** `SKILL.md`·`docs/wiki/**`에서 Monitor 도구를 언급하는 곳에 `persistent`가 같은 절 안에 없으면 실패. 이게 이번 라운드의 진짜 gotcha이고, 기계로 잡히는 것이므로 잡는다. 위치는 `test_prose_does_not_restate.py`가 아니라 `test_help_owns_its_facts.py`도 아니다 — 성격이 달라서 `tests/260823/test_waiting_is_armed.py` 하나를 새로 만드는 게 맞다.
4. 기존 `tests/260813/test_docs_match_the_cli.py`가 여전히 통과하는지 확인 (epilog 추가가 표 대조를 깨지 않아야).

---

## Phase 5 — `harness-spec.md`

1. **컴포넌트 스펙 수정** — `### .claude/skills/codex/SKILL.md`의 본문 목록: *"how to wait for a **batch** inside a host turn"* → **run**. 배치 한정 표현이 스펙 자체에 박혀 있는 것이 이 결함의 뿌리다.
2. **B21 개정** — *"`log --follow`, paired with the Monitor tool"* → 백그라운드 Bash가 기본, Monitor는 이벤트별 알림이 필요할 때의 상위 수단.
3. **새 R-행** — Monitor 오선택과 600초 거짓 전제를 기록. R15가 "Monitor는 다음 턴이 올 때만 옳다"까지 갔지만 **애초에 Monitor가 맞는 도구인지**를 묻지 않았다는 것, 그리고 원 근거가 포그라운드 상한을 백그라운드에 잘못 적용한 것이라는 것.
4. **V-19~V-23** — Phase 0 측정치.
5. **Change history** — 이번 패스 한 행.

---

## Phase 6 — 마무리

1. `python3 "/Users/seongjin/.claude/skills/harness-creator/scripts/validate_harness.py" --path .` → 0 errors.
2. `python3 -m unittest discover -s tests -p 'test_*.py'` 전체 통과.
3. `feat/armed-waiting` 브랜치 → 논리 단위 커밋 → PR → squash 머지.

---

## 검증

- **Phase 0 프로브 P1~P5** — 위 표. 결과가 문장을 정하므로 이게 1차 검증이다.
- **회귀**: `python3 -m unittest discover -s tests -p 'test_*.py'` (현재 통과 상태 유지 + 신규 검사).
- **최종 e2e (성진 승인 시)**: 헤드리스 시나리오 두 개 — (a) *"코덱스에 긴 작업 맡기고 그동안 README 정리해줘"*(E5 재현: 무장 + 병렬 작업 + 수거), (b) *"코덱스한테 이거 시켜줘"*처럼 **병렬할 일이 없는** 위임. (b)가 새 시나리오다: 없는 일을 지어내지 않고, 무장한 채로, 약속이 아니라 사실을 말하고 턴을 돌려주는지 본다. 지금 결함이 정확히 여기서 나온다.
- `validate_harness.py` 0 errors.

---

## 계획 밖으로 보고만 하는 것

- **루트 `CLAUDE.md`가 0바이트다.** `AGENTS.md → CLAUDE.md` 심링크로 Codex 런에 주입되는 브리핑 채널이 비어 있다. `docs/plan/260823_스킬 재작성.md`는 이 비움을 *"성진의 의도"*로 기록하고 있지만, 내 메모리(`claude-md-feeds-codex-runs`)는 *"비우지 말 것"*이라고 반대로 적혀 있다. 둘 중 하나가 낡았다. **이번 변경에서는 건드리지 않는다** — 어느 쪽이 맞는지 알려주면 메모리를 고치거나 파일을 되살린다.
- `audit_harness.py`가 보고한 harness-spec "드리프트" 31건은 오탐이다. B-표의 *메커니즘* 칸(`codex_bridge.py start` 등)을 파일명으로 파싱한 결과. 조치 불필요.
