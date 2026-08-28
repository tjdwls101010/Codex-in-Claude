# `review`를 없애고, 검증이 안 끝나는 이유를 스킬이 말하게 한다

## Context

이 스킬은 클로드가 자기 작업을 코덱스에 검증시키는 데 많이 쓰인다. 그 검증이 라운드를 거듭하며 안 끝나는 일이 있다 — 종료 조건이 도달 불가능하거나, 세는 양이 사용자가 신경 쓰는 양과 다르거나, 새 라운드가 이전 라운드가 닫은 질문을 다시 여는 식으로.

**이건 인상이 아니라 이 레포에 실측으로 남아 있는 사실이다.** `harness-spec.md:237`:

> *A sufficiently new lens finds something in any codebase; **counting findings is a stopping rule that never stops.*** … 19건 중 평범한 단일 세션 사용에서 도달 가능한 것은 **3건**.

`.claude/plans/260802/README.md:13`:

> *결함 발견은 **한 번도 0으로 수렴하지 않았다.** … 멈춘 이유는 결함이 소진돼서가 아니라 컨텍스트가 찼기 때문이다.*

이 학습이 `harness-spec.md`(감사 기록)와 `plans/`(지난 계획)에만 있다. 둘 다 위임 시점에 읽히지 않으므로 다음 세션의 클로드는 같은 루프를 처음부터 다시 돈다.

**그리고 원인을 찾다가 더 큰 것이 나왔다: 문서가 그 루프로 안내하고 있었고, 그 안내가 가리키는 명령이 값을 한다는 증거가 없다.** 이 라운드는 명령을 없애고 문단을 다시 쓴다.

## 왜 `review`를 없애는가

**브리지는 `review`에 아무것도 더하지 않는다.** `_codex.py:302-375`가 만드는 최종 argv는 `codex exec review [셀렉터] [-- 프롬프트]`이고, 샌드박스·모델·effort·`--output-schema`·`-o`·`--` 처리는 전부 `start`와 **같은 코드**를 지난다. 다른 건 `review` 서브워드와 셀렉터 플래그뿐이다.

그 위에 불리한 증거가 넷 있다.

1. **아무도 안 쓴다.** `.codex-runs/*/meta.json` 46런: `start` 27 · `resume` 6 · `review` 13. 그런데 review 13개는 2026-08-03의 4개(T5 Mode D의 플래그 표면 걷기 — 테스트)와 2026-08-26의 9개(`rev-<sha>`, 0.6.0 라운드의 커밋별 스윕 규율 하나)가 전부다. **애드혹 검증에 쓴 런은 0개.**
2. **검증 비용이 회계에서 사라진다.** review 런은 실제 작업 후에도 토큰 사용량을 전부 0으로 보고한다(`_run.py:688-691`). `start`에는 없는 결함이고, 세 파일이 그걸 감싸는 `review_zero`/`usage_note` 코드를 들고 있다.
3. **렌즈와 범위를 동시에 못 준다.** `review --help`: *"Exactly one of `--uncommitted`, `--base`, `--commit` **or this** is required; a combination is refused."* `review --uncommitted "레이스 컨디션만"`은 스폰 전에 거부된다. 그래서 검증에 쓰면 일반 스윕이 될 수밖에 없고, **일반 스윕에는 만족시킬 술어가 없으니 findings 말고 돌려줄 것이 없다.** 즉 이 명령의 존재가 호출자를 종료 불가능한 도구 쪽으로 라우팅한다 — 이 라운드가 고치려는 바로 그 실패다.
4. **레포 자신의 원칙과 어긋난다.** 260825 라운드가 `--fast`를 거절한 근거는 *"one config key, one tier — a second name, not a second switch"*였다. 측정된 차이 없이 `start`와 겹치는 서브커맨드는 그 대칭 사례다.

**남길 근거는 하나뿐이었다** — `codex exec review`가 코덱스 쪽에서 다른 스캐폴드를 가질 가능성. 이 레포에 그 비교 측정이 없다. 초안은 런 두 개로 재는 게이트를 뒀고, **사용자가 측정을 생략하고 제거를 선택했다**(2026-08-28). 그 판단을 기록해 둔다: 제거는 측정이 아니라 위 넷과 "값을 한다는 증거의 부재" 위에 선다.

**대체 수단은 이미 있고 새로 만들지 않는다.** `review --commit <sha>` 자리에는 `start --sandbox read-only "이 커밋을 리뷰해라: git show <sha>"`가 들어간다. 셀렉터를 대신하는 헬퍼나 프롬프트 프리셋은 만들지 않는다 — *"Why no instruction-injection presets"*가 명시적으로 거부한 것이고, 애초에 프롬프트를 클로드가 쓴다는 것이 제거 논거의 절반이다.

## 그 다음에 SKILL.md가 말해야 할 것

`review`가 사라지면 `## Which mode`의 첫 문단(*"`review` … when you want a **verdict** *you* will act on"*)이 통째로 사라진다. 그 자리에 들어갈 것은 "종료 조건을 명확히 하라"가 **아니다** — 클로드가 이미 아는 말이고, 어떤 사례도 재유도해 주지 못하는 rail이다. 재유도 가능한 사실 셋만 적는다.

| # | 사실 | 왜 파생 불가능한가 |
|---|---|---|
| 1 | 종료 술어의 주어가 리뷰어면 바닥이 없다. 리뷰어의 출력은 유한 집합이 아니라 렌즈가 생성하는 것 | 순진한 사전확률은 "좋은 코드베이스는 언젠가 깨끗하게 리뷰된다"이다. 이 레포는 그 반대를 네 라운드로 측정했다 |
| 2 | 이 레포가 실제로 쓴 교정은 "0을 더 명확히 정의"가 아니라 **다른 양을 센 것**이었다 — `findings 0` → `도달 가능한 findings 0`, 19 → 3 | 술어를 산출물로 옮기면 유한해진다는 것, 그리고 그 양이 사용자가 신경 쓰던 양과 일치한다는 것 |
| 3 | 새 런은 네가 기각한 것을 모른다. 라운드 2는 라운드 1이 닫은 질문을 다시 연다 — "아직 틀렸다"와 "다시 물었다"가 같은 모양의 목록으로 도착한다 | 직관은 "리뷰는 fresh eyes가 낫다"이고, 그건 *새 것을 찾는 데*만 맞다. *종료하는 데*는 정반대다 |

인터페이스 쪽 절반은 **툴이 이미 갖고 있다** — `--schema`의 help가 이미 *"`result --run`이 파싱된 객체를 돌려주고, 최종 메시지가 JSON이 아니면 크게 실패한다"*고 말한다. SKILL.md는 다시 쓰지 않고 가리키기만 한다.

**후보였다가 뺀 것 — "환경이 막은 검사가 진짜 실패와 같은 모양이다".** 2026-08-26 라운드가 배치 worktree 기본값을 공유 트리로 뒤집으면서 이미 해결됐다. 그 기본값을 움직인 세 측정 중 하나가 정확히 *"two field reports of runs that could not execute the verification they were asked for"*였다(`Orchestration.md:50`). 지금은 `--worktree`를 일부러 켰을 때만 나오고 `batch start`가 `missing_ignored`를 스폰 시점에 보고한다. 사고로 걸리는 경로가 아니므로 원인 목록에 올리면 과대평가다. `## Gotchas`는 건드리지 않는다.

**왜 SKILL.md 본문이고 `--help`가 아닌가** (D45/R55: 툴에 관한 사실은 툴이, **호스트**나 **명령 간 비교**는 SKILL.md가 소유한다): 정지 규칙은 "런 하나"가 아니라 **런 N개로 이어지는 호출자의 루프**에 관한 사실이다. 어떤 명령도 자기가 한 번 더 불릴 걸 모르므로 구조적으로 못 담는다. `log --help`가 아니라 `## Arming a wait`이 사는 자리와 같은 부류다. `references/`도 아니다(D45의 40줄 기준에 한참 못 미친다). 프로젝트 `CLAUDE.md`는 **절대 아니다** — 의도적으로 0줄이고, `AGENTS.md`가 심링크이며, 스킬 자신의 gotcha대로 프로젝트 `AGENTS.md`는 모든 격리 런에 주입되므로 한 줄이 모든 코덱스 런의 프롬프트 비용이 된다.

## 변경할 파일

### 1. 브리지에서 `review` 제거 — 순 감소

| 파일 | 지울 것 |
|---|---|
| `_codex.py` | `REVIEW_SELECTORS`, `review_argv()` 전체; `build_argv`의 `elif kind == "review"`와 `if kind == "review": argv += review_args` |
| `codex_bridge.py` | `cmd_review`, `review` 서브파서와 그 6개 플래그, `metavar`의 `review`, `review_zero`/`usage_note`(619-629), `--add-dir` help의 "or review run", `add_run_options(kind="review")` 분기, 763행 help의 `codex exec review` 언급, 1011·1013·1474-1475·1488행의 배치 설명 |
| `_run.py` | `create_run`/`build_argv`의 `review_args` 파라미터, `review_zero`/`usage_note`(688-691, 712, 754-755); `if kind != "review" and not prompt.strip()` → 프롬프트 무조건 필수; 6행·194행 주석 |
| `_batch.py` | `REVIEW_FIELDS`와 중첩 `review` 객체 검증(297-303), `kind` 허용집합에서 `review` 제거(305-306), worktree 자격 예외 `("review","resume")` → `("resume",)`(470)와 그 사유 문자열(518-519), `--resume-from`의 review 거부(714-719), `start_member`의 review 분기(967-972), `review_zero` 블록(1527-1565) |
| `_worktree.py` | 22행 주석의 reviewer 예시 |

**`kind: review`인 tasks 파일은 조용히 무시되지 않는다** — `kind`는 이미 허용집합 검증을 거치므로 *"kind must be start or resume"*로 거부된다. 이번 릴리스에 한해 그 메시지에 "`review` was removed in 0.7.0; use `start --sandbox read-only`"를 덧붙인다. 사라진 필드를 아무 말 없이 거절하는 것이 이 레포가 `load_tasks`에서 이미 거부한 모양이기 때문이다.

### 2. `.claude/skills/codex/SKILL.md` — `## Which mode` 한 절

- `review`/`start` 문단 **삭제**. "verdict"라는 단어가 함께 사라진다.
- 그 자리에 위 표의 사실 1·2를 넣고, `--schema`를 한 절로 가리킨다.
- `resume`/fresh `start` 문단에 사실 3을 한 문장 잇는다(축은 이미 있다; 더할 것은 검증 2회차에서 그것이 **비용이 아니라 종료 실패**로 나타난다는 연결).
- 호스트 대응표의 `Agent` 행에서 `review` 언급이 있으면 제거.
- `description`·`allowed-tools`는 **손대지 않는다**(스펙이 U-02 실패 외에는 금지). `description`에 `review`가 없으므로 트리거 경계 재검증 불필요.
- 문체: 하드랩 금지(문단 = 한 줄), 기존 어조 유지, use-case 목록·방법론 금지(R55).

### 3. 테스트

- **삭제/축소**: `tests/legacy/test_worktree.py`(17건 — review 멤버 자격 규칙), `test_argv.py`(14 — review argv), `test_lifecycle.py`(5), `test_faults.py`(5), `test_batch.py`(2), `tests/260813/test_wait_chain_edges.py`(4), `tests/260823/test_help_owns_its_facts.py`(4) 및 `test_help_audit_manifest.py`·`test_prose_does_not_restate.py`의 review 행, 픽스처 `review-clean-tree.jsonl` 삭제 및 `inherit-config-errors.jsonl`의 review 항목 정리.
- **신규 `tests/260828/test_review_is_gone.py`** — `tdd` 스킬을 열고 **제거 전에** 쓴다. seam은 CLI 표면이다: `codex_bridge.py --help`에 `review`가 없고, `review` 호출이 argparse 오류이며, `kind: review` tasks 항목이 안내 문구와 함께 거부되는지. `review_argv`의 존재 여부 같은 내부에 붙이지 않는다 — 리팩터링 한 번에 무의미해진다. 완료 판정: 제거 전에 **빨갛고** 제거 후에 초록.
- **신규 `tests/260828/test_skill_spec_agreement.py`**: SKILL.md에 새로 들어가는 수치(19 → 3, "한 번도 0으로 오지 않았다")가 `harness-spec.md`와 일치하는지. 스펙에서 옮겨온 검증 안 된 주장이고, 이 레포에 정확히 그 실패가 있다 — *"this spec counted 'eight gotchas' against a SKILL.md that had fourteen."* 드리프트 검사이지 사실 검사가 아님을 커밋 본문에 적는다.

### 4. 문서

`docs/wiki/CLI-Reference.md`(§4 `review` 절과 표 행), `Orchestration.md`(worktree 제외 표의 review 행, §6 refusal, §3 tasks 예시), `Concepts.md`(Run 정의의 `review`), `Architecture.md`, `Overview.md`, `Sandbox-Stability.md`, `Testing.md`, `Troubleshooting.md`, `Getting-Started.md`, `docs/wiki/README.md`, 루트 `README.md`. `CODE_OF_CONDUCT.md`·`CONTRIBUTING.md`의 "review"는 일반 영어라 **건드리지 않는다**.

### 5. `.claude/harness-spec.md` (53건)

- Behavior inventory에서 review 행 제거, worktree 자격 표 갱신.
- Component specs의 `codex_bridge.py` 서브커맨드 목록에서 `review` 제거.
- **새 D 항목** — 왜 `review`를 없앴는가. 위 네 근거 + **측정을 생략하고 결정했다는 사실과 그 결정의 주체**를 그대로 적는다. 이 레포는 D19·D34·D38·D40에서 "측정 없이 결정하지 않는다"를 반복해 왔으므로, 그 예외는 예외라고 기록되어야 다음 사람이 선례로 오독하지 않는다.
- **새 R 항목** — 프로즈가 `review`의 산출물을 "verdict"라 약속했고 툴은 findings만 줬다(R54 계열). 46런 중 애드혹 사용 0개 — **문서가 안내한 경로를 아무도 쓰지 않고 있었고, 어떤 검사도 그걸 볼 수 없었다.**
- T5 Mode D, R20(`--title` 드롭)을 "제거로 해소됨"으로 표시.
- `## Change history`에 2026-08-28 행.

### 6. `CHANGELOG.md`

`## [0.7.0]` 신설. **`### Removed`에 `review`를 breaking으로 명시**하고 마이그레이션 한 줄(`start --sandbox read-only "…: git show <sha>"`)을 준다. `### Changed`에 SKILL.md 가이던스. 0.6.0의 머리말 관례대로 *"Read Removed before upgrading"*을 붙인다.

## 실행 순서와 완료 판정

파일을 바꾸는 단계가 3개 이상이므로 착수 시 `TaskCreate`로 트래커를 열고 아래 판정을 각 `description`에 그대로 적는다.

0. **계획 파일을 `.claude/plans/260828/`로 옮긴다** — 레포 관례가 날짜 폴더다(`.claude/plans/README.md`, 커밋 `0e4e2c5`). 빈 `260828/`이 이미 있다.
1. **`tdd` 스킬을 열고 `tests/260828/test_review_is_gone.py`를 먼저 쓴다 — 빨간 상태로.** 제거 전이므로 실제로 실패해야 한다(레트로핏이 아닌 진짜 red). seam은 **CLI 표면**이다 — `--help` 출력, argparse 거부, tasks 파일 거부 메시지. `review_argv`의 존재 여부 같은 내부에 붙이면 리팩터링 한 번에 무의미해진다. 완료 판정: 빨간 것을 눈으로 확인.
2. **브리지에서 제거** — 완료 판정: 1의 테스트가 초록으로 바뀜; `grep -rn "review" .claude/skills/codex/scripts/ --include="*.py"` 0건; `codex_bridge.py --help`에 `review` 없음; `doctor` 정상.
3. **기존 테스트 정리 + `test_skill_spec_agreement.py` 추가** — 완료 판정: 전체 스위트 초록, 새 검사 둘 다 통과, **각각 일부러 깨뜨렸을 때 빨간 것을 확인**.
4. **SKILL.md 편집** — 완료 판정: `wc -l` 118 → 120 이하(문단 하나가 빠지고 셋이 들어오므로 순증 거의 없음); 편집이 `## Which mode` 안에만 있음; "verdict" 0개, "review" 0개; 새 문장별 근거 위치를 커밋 본문에 적음; "명확히 하라" 류 지시문 0개.
5. **문서·스펙·CHANGELOG** — 완료 판정: 위 4·5·6의 파일에서 명령으로서의 `review` 0건(일반 영어는 제외); `audit_harness.py` 드리프트 0.
6. **문서 잔여 참조 열거를 코덱스에 한 런 위임** — `grep`이 못 가르는 것(명령으로서의 `review` vs 일반 영어)을 여기서만 쓴다. `start --sandbox read-only`, 프롬프트는 *"제거된 `review` 서브커맨드를 여전히 존재하는 것처럼 말하는 문장을 전부 열거하라. 일반 영어의 review는 제외. 없으면 없다고 답하라."* **완료 판정은 "목록이 비었다"이지 findings 개수가 아니다** — 대상이 유한하므로 종료되는 열거이고, 이 라운드가 추가하는 규칙을 그 자리에서 실연한다. 5단계까지 초록이 된 **뒤에** 보낸다(한 트리에 동시 writer를 만들지 않기 위해).
7. **전체 검증** — 아래 절이 전부 초록.
8. **PR** — `feat!: 코덱스 review 모드를 없애고 검증의 정지 규칙을 스킬이 말하게 한다`. `.github/PULL_REQUEST_TEMPLATE.md` 섹션 그대로 채우고, `## 영향`에 breaking과 마이그레이션을 적는다. `gh pr merge --squash`.

**순서의 이유.** 테스트가 제거보다 앞인 것은 red를 실제로 보기 위해서다. 브리지 제거가 SKILL.md 문단보다 앞인 것은 문단이 "무엇이 남았는가"를 말하기 때문이다. 코덱스 위임이 마지막인 것은 나머지 전부가 한 트리를 쓰는 편집이라, 그 사이에 두 번째 writer를 넣으면 이 스킬 자신이 경고하는 concurrent-writer 상황이 되기 때문이다.

## 검증

```bash
cd "/Users/seongjin/Coding/codex in claude"
grep -rn "review" .claude/skills/codex/scripts/ --include="*.py"   # 0건
python3 .claude/skills/codex/scripts/codex_bridge.py --help        # review 없음
python3 .claude/skills/codex/scripts/codex_bridge.py review 2>&1   # argparse 오류
python3 .claude/skills/codex/scripts/codex_bridge.py doctor        # 환경 무결
python3 -m pytest tests/ -q                                        # 전부 초록
python3 -m pytest tests/260828/ -q                                 # 새 검사 둘
python3 "/Users/seongjin/.claude/skills/harness-creator/scripts/validate_harness.py" --path .
python3 "/Users/seongjin/.claude/skills/harness-creator/scripts/audit_harness.py" --path .   # drift 0
```

**실제 코덱스로 한 번**: `start --sandbox read-only "이 커밋을 리뷰해라: git show HEAD"`가 정상 완료하고 `result`가 사용량을 **0이 아닌 값으로** 보고하는지. 제거의 부수 효과(비용이 다시 보인다)를 한 번 눈으로 확인하는 것이고, findings를 세는 게 아니다.

**이 라운드의 정지 규칙, 명시적으로.** 위가 전부 초록이고 성진이가 한 번 읽으면 끝이다. **적대적 리뷰 라운드는 붙이지 않는다** — 산출물이 "코덱스 검증의 종료 규칙"이라 자기지시적이고, findings를 세기 시작하면 이 계획이 막으려는 루프를 그대로 실연하게 된다.

## 명시적으로 안 하는 것

- `review`의 셀렉터를 대신하는 헬퍼·프롬프트 프리셋·`schemas/` 번들 — *"Why no instruction-injection presets"*가 거부한 것.
- `SKILL.md`의 `description`·`allowed-tools` 변경.
- 글로벌 `~/.claude/CLAUDE.md` 변경 — 사용자 결정으로 이번 범위 밖.
- 프로젝트 `CLAUDE.md` 변경 — 0줄 유지.
- `## Gotchas` 변경.
- `.codex-runs/`의 기존 review 런 정리 — 레지스트리는 이력이고, 읽는 코드가 `kind`를 특별 취급하지 않게 된 뒤에도 그대로 읽힌다.
