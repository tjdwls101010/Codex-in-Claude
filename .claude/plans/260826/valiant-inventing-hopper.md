# `codex`를 네이티브 위임 도구처럼 — 실측으로 정의하고, 실측으로 판정하는 improve 패스

## Context

`codex` 스킬의 목적은 클로드가 코덱스를 자기 네이티브 위임 도구(`Agent`, `Workflow`)를 쓸 때와 같은 자연스러움으로 쓰는 것이다. 성진의 관찰은 "클로드가 각 모드를 잘 이해하지 못하는 것 같다"이고, 증상 네 축(모드 선택·위임 자체·대기와 수거·플래그 선택)을 모두 골랐다. 성공 기준은 퀄리티 하나, 비용은 감수, 전면 재작성까지 허용. 전역 `CLAUDE.md`가 codex를 권하기 *전에* 스킬 단독으로 서야 하므로, 실측은 전역 `CLAUDE.md` 없이 잰다.

조사에서 확정된 사실 (이 세션, 2026-08-26):

- 스펙(`.claude/harness-spec.md`)의 e2e 기록 E1~E9·V-24는 모두 PASS이고, 8/25 마찰면 목록은 작은 것만 남겼다. "모드를 잘 이해 못한다"는 관찰은 레포 어디에도 기록돼 있지 않다 → 느낌으로 고치면 R32·R56의 실패를 반복한다. **증상을 재는 벤치마크가 먼저다.**
- `SKILL.md:47,51`은 배치↔`Workflow` 대응(`--task`↔`parallel()`, `--as-ready`↔`pipeline()`, `--schema`, `--worktree`↔`isolation:'worktree'`)과 대응이 끊기는 지점(라운드 사이 계산)을 이미 적고 있다. **빠진 것은 단일 런 쪽**: `start`↔`Agent`, `resume`↔`SendMessage`, `stop`↔`TaskStop`, 무장 대기↔`Agent`의 자동 완료 알림, 그리고 비대칭(`Agent`엔 샌드박스·`schema`가 없고 알림은 공짜).
- 성진의 2-모드 프레임("단일=`start`, 그룹=`batch`")은 네이티브의 경계와 다르다. 클로드에게 `Agent` vs `Workflow`의 경계는 "단일 vs 그룹"이 아니라 **라운드 사이에 계산이 있나**이고, 팬아웃은 `Agent`를 한 메시지에 여러 번 부르는 것이다. 그 사고로 "독립 쓰기 작업 셋 → `start` 세 번"을 하면 worktree 격리를 못 받는다(R14에서 실측된 충돌). 이것이 모드 헷갈림의 첫 가설이다.
- worktree는 네이티브와 **일치하는** 부분이다. `Agent` 도구에 `isolation: "worktree"`, `Workflow`의 `agent()`에 `isolation: 'worktree'`가 있다. 오히려 codex는 단일 `start`에 worktree가 없어 네이티브보다 좁다. 삭제 후보가 아니라 확장 후보다.
- 표면 넓이: 41 플래그/12 명령 대 `Agent` 파라미터 6개. 이 레포 실런 35건(start 25·resume 6·review 4, 그룹 8, worktree 5)에서 한 번도 안 쓰인 플래그: `--schema --image --prompt-file --timeout --config --inherit-config --no-priority`. `--config`는 R24에서 불변식을 뚫은 pass-through라 제거 1순위. 나머지는 35건·이 레포 한정이라 사용 실측만으로 자르지 않는다.
- `start --help` 7.8KB, 위임당 1회(V-24). 자르는 이득이 토큰이면 작고 "결정 수 감소"면 진짜다 — interface over document의 근거.
- `audit_harness.py`의 드리프트 30건은 오탐(스펙 `component` 셀이 경로가 아님). 스펙 정리 때 셀을 경로로 바꾼다.
- 재작성을 제약하는 기계 검사: `tests/260813/test_docs_match_the_cli.py`(문서의 플래그가 실재·`--help`가 설명), `tests/260814/test_help_is_the_source.py`(명령표 금지, 선언된 기본값=argparse 기본값), `tests/260823/test_prose_does_not_restate.py`(도구가 말하는 사실을 프로즈가 재진술 금지), `test_waiting_is_armed.py`(Monitor는 lifetime과 함께), `test_pointers_resolve.py`, `test_help_audit_manifest.py`. CLI를 바꾸면 `docs/wiki/CLI-Reference.md`·`help-audit-manifest.md`·해당 테스트가 같이 움직인다.

## 성공 기준 — "네이티브처럼"의 조작적 정의 (코덱스 반박 1·5를 반영해 고침)

처음 정의는 "클로드가 고르는 위임의 *모양*이 네이티브와 같다"였다. 코덱스의 반박 1이 이를 깼다: 그 기준은 `Agent → SendMessage`에 맞춘 불필요한 `start → resume`를 통과시키고, 감사와 수정을 한 번의 `start`로 맡기는 더 싼 선택을 불일치로 실패시킨다. 모양은 원인이 아니라 증상이다.

**고친 정의 — 네 불변식.** 같은 과제를 codex로 시켰을 때 세션이 (1) 사용자의 결과를 완수하고, (2) 안전 불변식(샌드박스·격리·한 스레드 한 턴)을 지키고, (3) 네이티브라면 없었을 lifecycle 단계를 호출자에게 남기지 않으며, (4) 코덱스에 대한 사전 설명 없이 오류에서 회복한다. **네이티브 실행은 규범이 아니라 대조군이다** — (3)을 판정할 때 "네이티브라면 없었을 단계"를 실측으로 보여 주는 용도. 도구 호출의 모양은 설명 변수로 기록만 한다.

자발적으로 codex를 고르느냐(트리거)는 전역 `CLAUDE.md`의 몫이므로 합격 집합 밖이고, 별도 축으로 *데이터만* 모은다(P8).

최종 합격: Phase 4의 재실행이 전부 네 불변식을 통과하고, baseline에서 실패했던 P2c·P9c·P10c는 전후 transcript가 스펙에 인용된다. 두 라운드 연속 "일상 사용에서 도달 가능한 결함 0"이라는 스펙의 정지 규칙을 이번 패스가 첫 라운드로 채운다.

## 실행 순서

파일을 바꾸는 단계가 3개 이상이므로 실행 시작 시 `TaskCreate`로 트래커를 열고, 각 단계의 완료 판정을 description에 그대로 적는다.

### Phase 0 — 측정 장비 확인과 계획 검토 (파일 변경 없음) — **이 세션에서 완료**

실측 결과 (2026-08-26, Claude Code 2.1.246, `claude-fable-5`):

- `CLAUDE_CONFIG_DIR`를 스크래치로 돌리면 헤드리스가 `Not logged in`으로 끝난다 — 자격 증명은 키체인에 전역으로 있지만 새 설정 디렉터리가 받지 못한다. 토큰을 파일로 복사하는 길은 택하지 않았다.
- **대신 `--setting-sources project`가 격리를 준다.** 측정: 그 플래그로 뜬 세션은 "CLAUDE.md/AGENTS.md 없음"이라 답했고, 스킬 목록에 사용자 스킬(`harness-creator`, `tdd`, `interview`)이 없었으며 `codex`는 픽스처의 `.claude/skills/codex` 심링크로만 도달했다. 전역 `CLAUDE.md`의 위임 문장이 빠진 "스킬 단독" 조건이다.
- `run_e2e.py --isolate`는 `.git`을 빼고 복사한다 → 격리 사본이 레포가 아니라 worktree가 잘리지 않아 P2가 무력화된다. 그래서 러너(`scratchpad/runner.py`)가 픽스처를 `.git`째 복제하고 `parse_stream`만 재사용한다. 러너는 transcript 옆에 `.codex-runs/*/meta.json`의 argv 요약과 `git worktree list`를 기록한다.
- 픽스처 `scratchpad/fixture`: `lib/pricing.py`(세금을 할인 전에 적용), `lib/discount.py`(`> 1000` off-by-one), `lib/inventory.py`(`median`이 홀수 길이에서 틀림), 통과하는 테스트 넷, docstring 없음. 한 커밋.

- **코덱스 적대 검토** — **완료**. `start --sandbox read-only --model gpt-5.6-sol --effort xhigh`, 백그라운드 팔로워로 무장, 174,935 입력 토큰. 다섯 반박과 처분:
   - (1) "모양 복제"는 최적화를 결함으로 채점한다 → **채택**, 성공 기준을 네 불변식으로 다시 씀.
   - (2) C2는 `start/batch`(런 개수·주소·일괄 감시) 축과 일반/`Workflow`(라운드 사이 호스트 계산) 축을 뭉갠 범주 오류; "쓰기 둘 이상일 때만 batch"는 read-only 팬아웃(P4c가 실제로 그렇게 썼다)을 퇴행시킨다 → **채택**, 결정표를 두 축으로 분리.
   - (3) P8은 판별력 없음(설계상 데이터), P4는 "Workflow로 간다고 말함"만으로 통과 가능, 실시간 개입(`log → stop → resume → result`) 시나리오가 없다 → **채택**, P9 추가.
   - (4) C1의 `resume↔SendMessage`·`batch↔Workflow`는 등가가 아니다(실행 중 턴엔 채널이 없어 `stop` 후 `resume`; replay 비용; `resume`엔 worktree 없음; 배치는 결과 횡단 계산 불가) → **채택**, 대응표를 "가능/추가 전제/불가능" 세 열로.
   - (5) 네이티브 기준선이 스펙으로 검증되지 않았다 → 스펙이 아니라 **1라운드 실측(P1n~P4n)이 기준선**이다; 표의 네이티브 기대값은 예측이 아니라 관찰로 채운다.

### Phase 1 — baseline 벤치마크 — **3라운드 19세션 완료, 결과 아래**

시나리오 프롬프트는 `scratchpad/scenarios*.json`, 실행은 `scratchpad/runner.py <id> <prompt>`, 판독은 `scratchpad/timeline.py <id>`(transcript의 tool_use를 순서대로, 브릿지 `meta.json`의 argv와 `git worktree list`를 곁들여 기계 추출 — 판정은 내가 했다). 채점 근거는 언제나 transcript의 이벤트와 argv이지 세션의 자기 보고가 아니다.

**1라운드 실측 (2026-08-26, 11세션, `claude-fable-5`, `--setting-sources project`, 스킬 단독).** 모든 세션 `is_error: false`. 한 가지 오염을 먼저 적는다: 런처의 heredoc이 stdin으로 상속돼 11세션 모두 프롬프트 끝에 파이썬 스니펫이 붙었다(P7a·P8이 "무관한 스니펫"이라고 명시하고 무시). 모양 판정에는 영향이 없었고, 러너는 `stdin=DEVNULL`로 고쳤다.

| id | 네이티브가 고른 모양 | codex가 고른 모양 | 판정 |
|---|---|---|---|
| P1 | `Agent` 1개(general-purpose, 격리 없음) | `doctor` → `start --help` → `start --sandbox read-only --foreground --timeout 540` | **PASS** — 단일·읽기전용·헤드리스 포그라운드 모두 맞음 |
| P2 | `Agent` 3개, **격리 없음**, 한 트리에서 파일 하나씩 — 결과가 곧바로 내 트리에 있음 | `batch start` 3멤버, worktree 강제 → `status --follow` → `result --group` → **각 worktree의 diff를 `git apply`로 손수 병합** → `batch clean --force` | **FAIL(모양)** — 결과물은 같지만 codex 경로만 "수거·병합" 단계를 호출자에게 남겼다. 네이티브는 격리가 opt-in이고 결과가 내 트리에 떨어진다 |
| P3 | `Agent` 감사 → 클로드가 직접 수정 | `start --sandbox read-only` 감사 → 클로드가 직접 수정 | **PASS** — 같은 모양. 어느 쪽도 이어가기(`SendMessage`/`resume`)를 쓰지 않았으므로 이 축은 미판정 → 2라운드 P3n2/P3c2 |
| P4 | `Workflow` 1개(탐색 3 → 검증 8) | 배치 둘(`p4c-find` 3 → 클로드가 병합·중복제거 → `p4c-verify` 4, **`--schema` 사용**) | **PASS** — SKILL.md:51의 규칙("라운드 사이 계산은 배치 밖에서")을 그대로 따랐다 |
| P5 대기·수거 | — | 5세션 모두 헤드리스 예외를 맞게 적용(포그라운드 `--follow`/`--foreground`), 약속하고 끝낸 세션 0 | **PASS** |
| P6 플래그 | — | P1 read-only, P2 workspace-write(기본), model/effort 전부 미지정, timeout은 항상 지정(540~900) | **PASS** |
| P7 | — | "GPT한테 diff" → `review --uncommitted --foreground`; near-miss → `Skill` 없음 | **PASS** (E2·E3 재현) |
| P8 암묵 위임 | `Agent` | — | 데이터: codex 언급 없으면 codex를 고려하지 않는다. 의도된 경계(description은 명시적 언급에 반응) |

마찰(결함 아님, 기록): (a) codex 세션 5/5가 `doctor`를 선제 실행 — 세션당 1회, 헤드리스라 매번; (b) 위임 모양당 `--help` 1회(`start`·`batch start`·`review`·`result`); (c) **P3c가 `--help` 없이 `--read-only`를 추측해 argparse 오류를 받고 나서야 `start --help`를 읽었다** — `Agent`엔 샌드박스가 없으니 네이티브 직관으로는 플래그를 추측할 수 없고, 추측 실패의 메시지가 `--sandbox read-only`를 가리키지 않는다; (d) 소요 시간은 codex 쪽이 P2 6.5배, P4 5.7배 — 실제 코덱스 런이 도는 시간이라 비교 대상이 아니다.

**결론(1라운드)**: 네 증상 축 중 헤드리스에서 재현된 것은 **하나**, "쓰기 작업 팬아웃"에서 codex가 격리를 강제하고 병합을 호출자에게 넘기는 것. 나머지 축은 스킬 단독 조건에서 네이티브와 같은 모양을 골랐다.

**2라운드 실측 (5세션, stdin 오염 제거 후).**

| id | 관찰 | 판정 |
|---|---|---|
| P2c-r (P2c 재현) | `batch start --no-worktree` 3멤버 — 세션이 "서로 다른 파일만 건드리므로 격리 없이"라고 판단, 결과가 바로 트리에, `batch clean` 플래그 없이 | PASS — 1라운드 실패는 **비결정적**(2회 중 1회). 회피 수단은 있고 기본값이 병합 부담 쪽이다 |
| P2n2 (개수 힌트 없음, 네이티브) | `Agent` 3개 팬아웃 | 대조군 |
| P2c2 (개수 힌트 없음, codex) | `start` 1개로 세 파일 — 이유: "파일이 45줄이라 **워크트리 배치는 불필요**" | 새 기준 PASS. 그러나 worktree 기본값이 **팬아웃을 억제**한 직접 증거 |
| P3n2 (명시적 이어가기, 네이티브) | `Agent` → `ToolSearch(SendMessage)` → `SendMessage to=discount-auditor` | 대조군 |
| P3c2 (명시적 이어가기, codex) | `start --sandbox read-only` → `resume <id> --sandbox workspace-write` 같은 스레드, `start --help`+`resume --help` 읽음 | PASS — 이어가기 축 확정, 권한 상승이 명시적 |

**3라운드 실측 (코덱스 반박 3이 요구한 실시간 개입, 그리고 "맡기고 그동안 딴 일").**

| id | 관찰 | 판정 |
|---|---|---|
| P9c 실시간 개입 (codex) | `start --help`·`log --help`×2·`stop --help`·`resume --help`(≈28KB) → `start` → **`Monitor`를 무장하고 턴을 끝냈다**: 최종 답이 *"다음은 tests/ 차례이므로 주시하고 있습니다"*. 코덱스 런은 세션이 죽은 뒤에도 `running`. `stop`·`resume`·`result`는 한 번도 호출되지 않았다 | **FAIL** — 헤드리스에서 "약속하고 턴 종료"(R15·R56의 실패 그 자체). SKILL.md의 헤드리스 예외는 `--follow`만 말하고 **Monitor 분기에는 예외가 없다** |
| P10c 맡기고 딴 일 (codex) | `start` → **백그라운드 `log --follow` 무장(bg=True)** → README 작업 → `status --run` → 턴 종료: *"백그라운드 팔로워가 완료 시 알려주므로 그때 수집하겠습니다"* | **FAIL** — 같은 실패. 대화형 관용구(무장하고 돌려주기)를 헤드리스에서 썼다. P1c·P2c·P3c·V-24는 병렬 작업이 *없어서* 포그라운드를 골랐고, 병렬 작업이 *있으면* SKILL.md의 "genuinely parallel work, do it"가 앞서서 끝에 포그라운드로 막는 단계가 빠진다 |
| P10n 맡기고 딴 일 (네이티브) | `Agent`(포그라운드) → README 작업 → 결과 통합 → 테스트 | 대조군 — **`Agent`가 걸려 있는 동안 하네스가 턴을 붙든다.** 백그라운드 Bash 팔로워는 턴을 붙들지 않는다. 이것이 대기 축의 근본 비대칭이다 |

**4라운드 실측 (성진의 지적으로 추가한 세 번째 대조군, 에이전트 팀).**

| id | 관찰 | 판정 |
|---|---|---|
| P11n 구현자·검토자 2라운드 (네이티브 팀) | `Agent name=implementer` + `Agent name=reviewer` → 둘이 `SendMessage`로 **직접** R1·R2 교환 → 각자 `SendMessage to=main`으로 보고. 27 tool call, 하네스가 턴을 붙듦(turns=1) | 대조군 — 팀의 정의: 이름 있는 팀원, 상호 통신, 리더는 조율만 |
| P11c 같은 과제 (codex) | `start impl` → `start reviewer` → `resume impl` → `resume reviewer` → `resume impl`, 전부 포그라운드. **세션이 파일 메일박스를 스스로 발명**: 검토자가 `.review/roundN.md`, 구현자가 `roundN-reply.md`. 클로드는 "순서만 조율하고 내용은 전달·가공하지 않았다". 같은 수정, 15 passed, 287초 | 네 불변식 **PASS**. 네이티브에 없던 단계는 둘 — 순서 조율(5턴)과 프로토콜 발명(`.review/`가 `git status`에 남음) — 이고 둘 다 C1 표의 "불가능(상호 통신)" 열이 예고한 비용이다 |

**메일박스(클로드↔코덱스, 코덱스↔코덱스) — 후속 후보로 설계만 기록.** 구조적으로 가능하다: 팀의 `SendMessage`도 *다음 도구 호출 경계*에서 전달되므로, 코덱스에 `-c mcp_servers.<name>`로 브릿지의 stdio MCP 서버(stdlib)를 붙여 `inbox()`/`send(to,msg)`/`ask_supervisor()`를 주고, 메일박스를 `.codex-runs/<run>/inbox.jsonl`에 두면 같은 입도가 된다(격리 아래서도 통하는 표면; `app-server`는 "예고 없이 바뀜"이라 택하지 않음). 효용은 실측상 작다: 이 머신의 실런 43건 중 코덱스가 질문으로 끝낸 턴 0건, 가정을 적고 진행 4건 — B19의 preamble이 그 자리를 이미 메운다. P11c가 보여 준 남은 효용은 "프로토콜 발명과 순서 조율의 제거"이고, 라운드가 많을수록(현장 보고의 2×20) 커진다. **착수 조건**: 팀 모양의 codex 사용이 반복되고 세션이 라운드 수를 그 비용 때문에 줄이는 것이 관찰될 때. `-c mcp_servers`가 격리 아래 실제로 붙는지의 프로브가 첫 단계. 성진은 "효용이 크려나"를 물었고 위 데이터가 그 답이다 — 이번 패스 밖.

이 둘(P9c·P10c)은 헤드리스 전용 결함이지만 헤드리스는 e2e만이 아니다 — `claude -p` 파이프라인, 루틴, 그리고 **codex 스킬을 안에서 쓰는 서브에이전트**(한 턴짜리)가 전부 이 모양이다.

**현장 보고 (성진이 전달한 다른 세션, `batch start --worktree` 리뷰어 2×20라운드).** 세 항목의 처분:
- **격리 worktree가 gitignore된 런타임 자산(`.venv`, 프로바이더 캐시, 픽스처)을 떨어뜨린다** → 런이 요구받은 검증을 못 돌리거나, 자기 캐시를 새로 만들어 라이브 데이터를 받아 **거짓 회귀 경보**를 만든다. SKILL.md의 격리 gotcha는 "config·plugins·MCP"만 말한다. **C-A를 결정하는 추가 증거**이고, 어느 선택이든 gotcha 한 줄과 `batch start` 응답의 경고(worktree에 없는 gitignore 최상위 항목 나열 — 도구가 그 순간 아는 사실, R14의 교훈)가 붙는다. `--carry <path>` 플래그는 (a)를 고르면 필요가 `--worktree` 명시 사용자로 줄어들므로 **보류**.
- **`status --group`은 JSON 한 덩어리, `--follow`는 `run <id> <prev> -> <state>` 텍스트 라인(`_batch.py:1127`)인데 `status --help`가 형식을 말하지 않는다** → 보고자가 비-follow 출력을 라인으로 파싱해 빈 결과를 "전부 종료"로 오독. 최상위 `--help`엔 있고 `status --help`엔 없다. **C6**: `status --follow`의 `help=`에 두 형식을 명시. `--json` 추가는 거절(형식을 말하면 충분).
- **`batch clean` 뒤 이름 재사용 불가** → **재현 결과: 결함 아님.** 실제 CLI(`scratchpad/reuse.sh`): read-only 그룹은 clean → `name_released: true` → 즉시 재청구 성공. 더러운 worktree 그룹은 clean이 `kept` 둘과 note *"collect them, or pass --force to discard. The group name stays claimed until they are gone"*로 거절, 재청구는 `batch clean --group`을 가리키는 오류, `--force` 뒤 `name_released: true`, 재청구 성공. 보고자의 리뷰어가 worktree에 추적되지 않는 파일(부트스트랩 산출물)을 남겨 `kept`였던 것이고, 도구는 그 이유와 처방을 응답에 실었다. 처분: 변경 없음, 스펙에 재현 기록.
- **gitignore 손실 재현**: 픽스처에 `.venv/bin/python`(gitignore) 심고 두 worktree 멤버에게 `ls .venv/bin` → 둘 다 `No such file or directory`. C8의 근거.

**두 번째 현장 보고 (같은 사용자, 리뷰어 2×20라운드).** 핵심 주장: 그룹 팔로워(`status --group --follow`)는 **상태 변화만** 내고(`_batch.py:1121-1128`: `run <id> <prev> -> <state>`), 상태는 20분 동안 `running` 그대로라 "눈이 가려진 채 기다린다" — 리뷰어가 부트스트랩에서 헤매는 것, 스위트 실패 2개, 렌더 진입을 전부 손 폴링으로 알았고, 긴 침묵이 정상인지 팔로워가 죽은 건지 구분이 안 된다; 그래서 매번 폴링 루프를 손으로 짜다가 형식을 틀려 **거짓 완료 보고 직전**까지 갔다. 처분:
  - 단일 런에는 이미 그 도구가 있다: `log --run --follow --level compact`는 명령·종료코드·에이전트 메시지를 이벤트마다 낸다. **그룹에는 없다** — `log`는 `--run`만 받는다. 그래서 그룹 중간 신호를 원하면 멤버 수만큼 `log --follow`를 무장해야 하고, 보고자는 그 대신 루프를 짰다. **C9**로 채운다.
  - "Monitor는 예외"라는 배치가 틀렸다는 지적은 절반 채택: 기본값을 뒤집는 게 아니라 **선택 기준**을 주는 게 principle over rail이다 — 중간에 네가 *할 수 있는 일*(stop·redirect)이 있고 런이 그 판단 지연보다 길면 이벤트마다 깨어나는 쪽(Monitor persistent), 아니면 완료 알림 하나. C7에 합친다.
  - 하트비트: `follow_group`은 `run_row`의 파생 상태를 비교하므로 300초 유휴면 `running -> stalled` 한 줄이 나온다 — 죽은 런에 대한 하트비트는 이미 있다. 없는 것은 *바쁜* 런과 *죽은 팔로워*의 구분. C9의 `--heartbeat`.
  - `--carry`: 두 번 요청됐지만 C-A(a)를 고르면 필요가 `--worktree` 명시 사용자로 준다. **보류**, 스펙에 `declined` + 재고 조건("`--worktree` 사용에서 gitignore 손실이 다시 보고되면").
  - 보고자 본인의 실수(변이 스윕을 메인 트리에서 돌려 파일을 잠금)는 스킬 밖이지만, 격리 *수단*이 남아야 하는 이유이기도 하다 — (a)는 기본값만 바꾸고 `--worktree`는 남긴다.

**이 세션의 대화형 관찰 (헤드리스가 못 재는 축).** 코덱스 계획 검토를 `start` → 백그라운드 `log --follow` 무장 → 턴 반환 → 알림 → `result`로 수거했다. `--help`를 다시 읽지 않았고 마찰은 스크래치 레지스트리의 `--runs-dir` 반복뿐. 대화형 무장 대기는 V-20이 잰 대로 동작한다.

**21세션 종합.** 체계적으로 갈라진 곳은 **배치의 worktree 기본값 하나**다: 네이티브(`Agent`)는 격리가 opt-in이고 변경된 worktree의 병합도 호출자 몫이지만 *기본이 공유 트리*라 팬아웃에 비용이 없다. codex 배치는 쓰기 멤버 둘 이상이면 격리가 기본이라 (i) 수거·병합·`clean --force` 단계가 생기거나(P2c) (ii) 세션이 그 비용을 피하려 팬아웃을 접는다(P2c2). 나머지 축 — 단일·이어가기·계산 개입·대기·플래그·트리거 — 는 스킬 단독 조건에서 네이티브와 같은 모양을 골랐다. 성진이 고른 네 증상 중 헤드리스로 재현된 것은 이 하나다.

시나리오 정의(재측정에 그대로 쓴다): P1 단일 설명(read-only) · P2 세 모듈 docstring 팬아웃(`셋을 써서 병렬로` / 개수 힌트 없는 P2n2·P2c2) · P3 감사 후 수정(클로드가 고치는 P3 / 같은 에이전트가 이어서 고치는 P3n2·P3c2) · P4 파일별 버그 → 중복 제거 → 재검증(계산 개입) · P7a "GPT한테 이 diff"(uncommitted 결함 심음) · P7b near-miss "리뷰해줘" · P8 codex 언급 없는 위임 · P9c 실시간 개입(`_v2` 리네임, tests/ 건드리면 stop→resume) · P10 맡기고 README 작업. 네이티브 짝(n)은 "서브에이전트"로, codex 짝(c)은 "코덱스"로만 바꾼 같은 문장.

### Phase 2 — 스펙 갱신 (구현 세션의 첫 편집)

이 계획의 승인이 스펙 게이트다. 스펙 I2~I4를 한 번에 갱신한다: Goals에 성진의 이번 문장("전체 재작성까지 감수, 오직 퀄리티, 실측으로") 인용; Behavior inventory에 새 행 — 네 불변식 행, 호스트 대응표 행, C-A·C4·C6·C7·C8·C9 각각, `--carry`·C3·C5는 `declined`; `component` 셀을 경로로 교정(감사 오탐 30건 해소); Validation에 이 세션의 19세션·재현 2건을 V-25…로.

완료 판정: `audit_harness.py` 드리프트 0; 새 행마다 근거(시나리오 id 또는 재현 스크립트)가 적힘.

### Phase 3 — 재설계 (실측과 코덱스 반박으로 확정한 것, 각각 별 커밋)

이 세션의 실측이 지목한 순서다. 전면 재작성은 **아니다** — 16세션이 SKILL.md의 판단 기준 대부분을 그대로 따랐고, 갈라진 곳은 인터페이스 하나와 문서 두 블록이다.

- **C-A (인터페이스, 코드) 배치 worktree 기본값 — 결정: (a) 공유 트리 기본, `--worktree` opt-in.** 성진이 판단을 맡겨서 내가 정했다 (2026-08-26). 평문으로: worktree는 코덱스 멤버마다 프로젝트의 *복사본*을 주는 것이다. 장점은 서로의 파일을 밟지 않는 것. 비용 셋이 실측됐다 — 결과가 복사본에 남아 호출자가 가져와야 하고(P2c, `git apply` 여덟 줄 + `clean --force`), 그 비용을 아는 세션이 팬아웃 자체를 접으며(P2c2), 복사본에는 git이 추적하지 않는 것(`.venv`, 캐시, 픽스처)이 없어 검증이 안 돌거나 거짓 회귀가 난다(현장 보고 2건, 재현됨). 네이티브 서브에이전트는 복사본 없이 내 폴더에서 바로 일하고, 충돌 위험은 클로드가 "파일이 겹치나"로 판단한다 — 이번 세션이 그 판단을 세 번(P2n·P2n2·P2c-r) 스스로 내렸다. 그러니 기본값을 네이티브에 맞추고, 격리는 겹칠 때 고르는 도구로 남긴다. (b)는 병합만 줄이고 나머지 두 비용을 남기므로 택하지 않는다. 선택지였던 것:
  - (a) **공유 트리 기본, `--worktree` opt-in** — 네이티브와 같은 기본값. 세션은 P2n·P2n2·P2c-r에서 "파일이 겹치지 않으면 격리 불필요"를 스스로 판단했다. `concurrent_writers` 보고와 멤버 preamble("다른 N-1개가 같은 트리에서 돈다")은 유지. B24가 근거로 삼은 충돌 위험은 네이티브가 이미 지는 위험과 같다. `--no-worktree`는 의미를 잃고 `--worktree`가 "이 배치는 격리"가 된다.
  - (b) **격리 기본 유지 + `batch collect --group`(각 worktree의 diff를 호출자 트리에 적용, 충돌은 보고, 성공하면 clean)** — 안전은 그대로, 병합 단계가 한 호출로 줄어든다. 네이티브엔 없는 편의라 패리티는 아니지만 P2c의 수동 `git apply` 여덟 줄을 없앤다.
  - 완료 판정: (a)면 `tests/legacy/test_worktree.py`·`test_batch.py`의 자격 규칙 테스트를 뒤집고, `batch start --help`의 Worktrees epilog·`Orchestration.md`·`help-audit-manifest.md`·CHANGELOG(breaking) 동반 수정; (b)면 `collect`의 충돌·부분 적용·clean 거절 테스트. 어느 쪽이든 P2c·P2c2 재실행에서 팬아웃 3개가 나오고 병합 단계가 0(a) 또는 1(b) 호출.
- **C1 (SKILL.md) 호스트 대응표 — 세 도구, 세 열.** 성진의 지적(2026-08-26)으로 대조군이 `Agent`·`Workflow`에서 **에이전트 팀**까지 셋이 됐다. 팀은 이름 있는 팀원들이 컨텍스트를 유지한 채 서로 메시지를 주고받고 공유 태스크 보드에서 일을 집어 가는 모양이라, codex와 가장 멀다: 스레드 컨텍스트 유지(`resume`)와 라운드 반복(`--resume-from`)은 있지만 **일하는 중인 상대에게 메시지 넣기**(턴 안 채널 없음 → `stop` 뒤 `resume`), **팀원끼리의 통신**(런은 서로를 모르고 preamble로 N-1의 존재만 안다), **공유 보드**가 없다. 그 셋은 표의 "불가능" 열에 들어가고, 팀 모양의 과제를 codex로 받으면 호출자가 라운드 경계에서 메시지를 *중계*하는 모양이 된다 — 그것이 가능한 유사 동작이다. P11(구현자·검토자 2라운드 팀) 실측으로 이 열을 채운다. 코덱스 반박 4대로 등호가 아니라 "가능한 유사 동작 / 추가 전제 / 불가능"으로: `start`~`Agent`(전제: 샌드박스를 골라야 함, `Agent`엔 없음); `resume`~`SendMessage`(전제: 실행 중 턴엔 채널 없음 → `stop` 뒤에; replay 비용; `resume`엔 worktree 없음); 완료 알림(`Agent`는 공짜, codex는 백그라운드 `log --follow`로 무장); `--schema`(`Workflow`의 `schema`, `Agent`엔 없음); 배치~`parallel()`(불가능: 결과 횡단 계산 — 그건 배치 둘 사이에서 호스트가, P4c가 그렇게 했다). 자리는 `## Which mode`, `--help`가 아니다(호스트 사실은 코드가 검증 못 함 — R54·R56). 판정: `test_prose_does_not_restate.py`·`test_pointers_resolve.py` 통과, 15줄 이내.
- **C2 (SKILL.md) 모드 결정을 두 축으로.** 코덱스 반박 2를 그대로: 축 1 — 런의 개수와 주소 지정(하나면 `start`, 여럿이면 `batch`; 읽기 전용 팬아웃도 배치다, P4c); 축 2 — 라운드 사이에 호스트 계산이 필요한가(필요하면 배치 사이에서 직접 하거나 `Workflow`). 기존 47·51행의 "batch는 Workflow다" 비유가 앞서고 한계가 뒤따르는 구조를 뒤집는다. 격리 여부는 C-A의 결정에 따라 한 문장. 판정: P2c2 재실행에서 팬아웃, P4c 재실행 PASS 유지.
- **C4 (코드) 플래그 퇴역 다섯 — 성진 결정 (2026-08-26).** `--config`(R24의 불변식 관통 전력, 51런 중 0회), `--no-worktree`(C-A 뒤 죽은 플래그), `--no-preamble`(0회; B19·V-18이 preamble을 "허위 생성을 막는다"고 쟀으므로 끌 이유가 없고, 사실을 직접 주려면 프롬프트에 쓰면 된다), `--isolate`(0회; fresh 런엔 무의미, resume은 기록값 재주장이라 되돌릴 길이 사라지는 건 감수), `--interval`(log·status, 0회; 1.0s를 바꿀 이유가 실측에 없음). 각각 `retired` 행 + 이유, CHANGELOG breaking. 나머지는 성진이 목록으로 확인했다 — 결정을 담거나(`--sandbox`·`--worktree`·`--schema`·`--timeout`·`--priority/--no-priority`…), 주소를 대거나, 코덱스 자신의 표면이거나, 안전 장치. 표면 약 41 → 38(정확한 수는 T5 장부). 판정: `tests/legacy/test_argv.py`의 `RawConfigCannotOutrankTheInvariant`가 플래그 부재 테스트로 바뀌고, 다른 넷도 "인식되지 않음" 테스트 하나씩, `help-audit-manifest.md`에서 행 제거, `--help` 바이트 전후 기록, `--interval` 제거 뒤 폴링 주기 상수가 `help=`에 기본값으로 남아 있지 않은지 확인.
- **C3 선언적 거절(declined).** `--read-only` 추측 실패(P3c)는 16세션 중 1회, 한 왕복. argparse 오류에 힌트를 붙이는 건 레일이다. 기록만.
- **C5 (description) — 성진 결정: 바꾸지 않는다 (2026-08-26).** P8: codex 언급 없으면 `Agent`. 그 정책은 전역 `CLAUDE.md`가 들고, 스킬은 역량을 들고 정책은 사용자가 든다(D23). 스펙에 `declined` 행으로 기록. near-miss 경계(P7b)는 그대로.
- **C7 (SKILL.md) 한 턴짜리 컨텍스트의 대기 규칙 — 3라운드가 지목한 결함.** 지금 `## Arming a wait`의 헤드리스 예외는 "`--follow`를 포그라운드로"만 말하고, (i) 병렬 작업이 있는 경우와 (ii) Monitor 분기에는 예외가 없다. P10c는 무장 → 병렬 작업 → 약속하고 종료, P9c는 Monitor 무장 → 약속하고 종료. 고칠 문장은 하나다: **"한 턴짜리라면 무장은 아무 소용이 없다 — 팔로워든 Monitor든. 병렬 작업을 먼저 하고, 턴의 마지막 호출을 포그라운드 `--follow`(개입이 필요하면 짧은 `--follow-timeout`의 포그라운드 `log --since` 루프)로 막아라."** 그리고 헤드리스를 알아보는 단서를 한 줄("너를 깨울 것을 이름 붙일 수 없으면 한 턴짜리다"). 같은 절에서 **완료 알림 하나 vs 이벤트마다**를 예외가 아니라 기준으로: 중간에 네가 할 수 있는 일(stop·redirect)이 있고 런이 그 판단의 지연보다 길면 Monitor(persistent)로 이벤트마다, 아니면 백그라운드 `--follow` 하나 — 두 번째 현장 보고의 "20분간 눈이 가려짐"이 이 기준의 사례다. `tests/260823/test_waiting_is_armed.py`에 "헤드리스 예외가 Monitor와 병렬 작업을 함께 다룬다"는 검사 한 개. 판정: P9c·P10c 재실행에서 `stop→resume→result` / `result` 호출이 transcript에 있고 최종 답이 약속이 아님. **네이티브와의 근본 비대칭(`Agent`는 턴을 붙들고 Bash 팔로워는 안 붙든다)은 C1 표의 한 행이 된다.**
- **C6 (`help=`) `status`의 두 출력 형식.** `status --follow`의 help에 "`run <id> <prev> -> <state>` 텍스트 라인 뒤 `group.<state>`; `--follow` 없이는 JSON 한 객체"를 명시. 현장 보고가 빈 라인 파싱을 "전부 종료"로 오독한 자리. `tests/260814`의 `AStatedDefaultIsTheRealDefault`류 검사는 형식까지 못 보므로 `test_output_contract.py`에 한 줄. 판정: 그 테스트 통과.
- **C9 (코드) 그룹의 중간 신호 — `log --group <name> --follow`와 `--heartbeat`.** 두 번째 현장 보고가 지목. `log`에 `--group`을 추가해 멤버들의 compact 이벤트를 `[<index>:<label>]` 접두사로 인터리브하고, 그룹 터미널 라인으로 끝낸다 — 단일 런의 `log --follow`가 주는 것을 그룹에도. 그러면 중간 개입은 Monitor(persistent) 하나로 되고, 손 폴링 루프와 그 파싱 실수가 사라진다. `--heartbeat SEC`(둘 다의 팔로워, opt-in)는 `still-running elapsed=… running=N` 한 줄을 주기적으로 내서 *바쁜 런*과 *죽은 팔로워*를 가른다 — Monitor에 물렸을 때만 의미가 있으므로 기본은 꺼짐. `--events`는 별도 플래그로 만들지 않는다(그것이 `log --group --follow` 자체다). 판정: `tests/legacy/test_filters.py`류에 그룹 인터리브·접두사·터미널 라인 테스트, 하트비트 주기 테스트; T2에 두 멤버 실런 1개.
- **C8 (`batch start` 응답 + gotcha) 격리 worktree의 gitignore 손실.** 현장 보고. worktree를 자른 뒤 호출자 트리의 gitignore된 최상위 항목 중 worktree에 없는 것을 `missing_ignored: [".venv", ".state/cache"]`로 응답에 나열(도구가 그 순간 아는 사실). SKILL.md 격리 gotcha에 "gitignore된 것도 같이 떨어진다 — 정본 인터프리터·캐시·픽스처가 거기 있으면 런은 요구받은 명령을 못 돌리거나 자기 캐시를 새로 만들어 비교를 전부 거짓 불일치로 만든다" 한 문장. C-A에서 (a)를 고르면 `--worktree` 명시 시에만 해당. 판정: `tests/legacy/test_worktree.py`에 gitignore 항목 나열 테스트; 재현 스크립트(`scratchpad/reuse.sh` wt-c)가 실측한 손실이 응답에 보임.
- **C10 (코드) 격리 아래서 사용자의 기본값을 지킨다 — 성진 결정 (2026-08-26).** 성진의 `~/.codex/config.toml`은 `model = "gpt-5.6-sol"`, `model_reasoning_effort = "max"`, `service_tier = "fast"`를 갖는데, 격리가 그 파일을 통째로 버리고 `service_tier`만 재주입한다(B14). 그래서 21세션의 모든 런이 model/effort 없이 **서버 기본값**으로 갔다 — 스펙의 미측정 항목 "이름 없는 런이 실제로 쓰는 모델"이 이것이다. 성진의 처음 제안은 스킬 디렉터리의 `.toml`이었고, 같은 질문의 두 번째 사본(R54)·플러그인 캐시 편집 불가·정책을 스킬이 드는 문제(D23)를 설명한 뒤 **코덱스 자신의 `config.toml`에서 세 키를 선별 주입**으로 결정했다. 우선순위: 명시 플래그 > `resume`이 기록한 값(B3 그대로) > `config.toml` > 서버 기본값. 읽는 키는 정확히 셋(`model`, `model_reasoning_effort`, `service_tier`)이고 `--config`가 거부하던 네 키 중 `sandbox_mode`는 제외 — 그건 이 스킬이 소유한 불변식이다. D38의 카탈로그 검사가 config 값에도 붙어 폐기된 모델명은 실행 전 거절. 파서는 `doctor`가 이미 쓰는 것. D40("기본값 없음")은 "스킬의 기본값은 없고 사용자의 기본값은 지킨다"로 재서술. `--priority/--no-priority`는 `service_tier`를 읽게 되면서 "config에 fast가 있으면 그것, 없으면 주입 안 함"이 되므로 두 플래그의 help와 B14를 다시 쓴다. 판정: `tests/legacy/test_argv.py`에 "config.toml의 세 키가 fresh `start`의 argv에 `-c`로 실리고, 플래그가 이기고, resume은 기록값을 재주장한다" 세 테스트; `doctor` 응답에 `effective_defaults` 필드; 벤치마크 P1c 재실행 argv에 `model="gpt-5.6-sol"`·`model_reasoning_effort="max"`가 보임.
- **C-R (구조, 동작 변경 없음) — 지나가는 자리에서만.** 실측: 5,320줄 중 31%가 docstring·주석(의도된 R-기록), 테스트 9,001줄·498개. 크기는 문제가 아니고 밀도가 문제다 — `create_run` 291줄(R26·R34·R50의 가드), `cmd_batch_clean` 167줄(R10·R18·R22·R23·R35·R51 여섯 거절), `supervise` 133줄. 이번 패스가 어차피 여는 두 함수만: `create_run`을 단계(검증 → 청구 → worktree → spawn → 공개)로 나눠 락 범위를 드러내고(C-A·C10 편집 직전, 별도 커밋), `cmd_batch_clean`의 여섯 거절을 R-번호가 붙은 술어 목록 하나로(C8 편집 직전, 별도 커밋). 판정: 각 커밋에서 테스트 파일 변경 0, 498개 전부 통과, `git diff --stat`이 그 함수 하나만. 동시성 코어(`supervise`·`reap`·`_registry`)는 **이번 패스 밖** — 성진의 외과적 변경 원칙, 소크 테스트를 안전망으로 별도 패스.
- **기록만 (결함 아님).** codex 세션 6/6이 `doctor`를 선제 실행(세션당 1회); 위임 모양당 `--help` 1~2회(최대 16.6KB, P3c2); 헤드리스에서 `--timeout`을 항상 지정.

### Phase 4 — 재측정

같은 러너(`scratchpad/runner.py`, `--setting-sources project`, 픽스처 `.git`째 복제)로 **실패했거나 변경의 영향을 받는 시나리오만** 재실행: P2c·P2c2(C-A·C2), P9c·P10c(C7), P3c2(C1의 대응표가 이어가기를 망치지 않는지), P7b(near-miss 회귀), P1c(C10 — argv에 config의 model·effort·tier가 실리는지). 각 시나리오 2회 — P2c가 2회 중 1회만 실패했으므로 1회는 증거가 아니다. 전후 transcript를 스펙 Validation에 V-25…로 기록. C9는 헤드리스로 못 재므로 두 멤버 실런에 Monitor를 물린 대화형 관찰 1회.

완료 판정: 재실행 전부 네 불변식 PASS(P2c/P2c2: 팬아웃 3, 병합 단계 0; P9c: `stop→resume→result`가 transcript에; P10c: 마지막 호출이 포그라운드 `--follow`이고 최종 답이 약속이 아님); "일상 사용에서 도달 가능한 결함 0"을 스펙의 정지 규칙 카운터에 1로 기록.

### Phase 5 — 마무리

스펙 Change history, `validate_harness.py` 0 errors, CHANGELOG, 브랜치 `feat/codex-native-parity` → PR(템플릿 섹션 그대로) → squash merge. 실행 중 만든 픽스처·transcript는 스크래치에 두고 레포에 넣지 않는다(결론만 스펙에).

**머지 뒤, 레포 밖 한 줄 — 성진 결정 (2026-08-26).** `~/.claude/CLAUDE.md`의 위임 절에서 `` `gpt-5.6-sol(xhigh)`이 `sonnet`보다 낫고 Codex 구독이 이미 값을 치렀으므로 ``를 `` 코덱스는 내 `config.toml`의 모델·effort로 돌고 그 구독은 이미 값을 치렀으므로 ``로 바꾼다. 이유: 그 값은 이미 config.toml(`max`)과 어긋나 있고, 이 세션에서 그 문장이 실제로 `--model gpt-5.6-sol --effort xhigh`를 넘기게 하는 *지시*로 작동했다 — C10 뒤엔 두 번째 사본(R54)이 된다. **C10이 머지되기 전에 지우면 안 된다**: 그 전엔 그 문장이 모델을 넘기게 하는 유일한 힘이다. 성진의 개인 파일이라 PR 밖에서, 구현 세션이 성진 확인 후 직접 고친다.

## 구현 절차 — 스킬 사용 (성진 확인, 2026-08-26)

- **`tdd`를 변경마다 호출한다.** 코드 변경(C-A·C4·C6·C8·C9)은 되돌리면 실패하는 회귀 테스트가 먼저다. seam 합의 단계에서 테스트를 내부 함수가 아니라 **CLI 계약**(stdout·응답 JSON·argv)에 붙인다 — R17·T5의 교훈: 플래그 이름만 부르는 테스트는 결함을 못 본다. 문서 변경(C1·C2·C7)도 같은 순서: `tests/260823/`의 형식 검사(`test_waiting_is_armed.py`, `test_prose_does_not_restate.py`)에 새 검사를 먼저 빨갛게 넣고 SKILL.md를 고친다.
- **`codex`는 세 자리에.** (1) 변경 커밋마다 `review --commit <sha> --sandbox read-only` 적대 검토 — 다른 모델이 보는 것이 목적(R19·R50이 그렇게 잡혔다). (2) 새 `help=` 문자열(C6·C8·C9)을 코드와 대조하는 감사 — 260823의 143개 문자열 감사 절차. (3) 마무리에 SKILL.md만 주고 `start→log→resume→result`·배치·`log --group`을 처음부터 끝까지 몰게 하기 — 260823의 세 번째 검토 형태, e2e와 다른 각도. 구현 중 모든 코덱스 사용은 대기 축의 대화형 관찰로 스펙에 적는다.
- **코덱스에 구현을 통째로 맡기는 것은 C-A가 코드에 들어간 뒤에만**, 그 전엔 클로드와 코덱스가 한 트리에서 동시에 쓰는 상황을 만들지 않는다(순서대로, 또는 `--worktree` 명시).
- 파일을 바꾸는 단계가 3개 이상이므로 시작 시 `TaskCreate`로 트래커를 열고, 단계마다 위 완료 판정을 description에 적는다.

## 건드리는 파일

- `.claude/skills/codex/SKILL.md` — C1·C2·C7·C8(gotcha)
- `.claude/skills/codex/scripts/codex_bridge.py`(`log --group`, `--heartbeat`, `status --follow` help, `--config` 제거, `doctor`의 `effective_defaults`), `_codex.py`(config.toml 세 키 주입, `--priority` 의미), `_batch.py`(worktree 자격 규칙, `missing_ignored`), `_worktree.py`, `_events.py`(그룹 인터리브), `_run.py` — C-A·C4·C6·C8·C9·C10
- `tests/legacy/`, `tests/260813/`, `tests/260814/`, `tests/260823/` — 회귀·문서↔CLI 검사 동반 수정
- `docs/wiki/CLI-Reference.md`, `Orchestration.md`, `README.md`, `CHANGELOG.md`(breaking: worktree 기본값, `--config`) — C-A·C4·C9의 결과
- `.claude/plans/260823/help-audit-manifest.md` — 플래그 증감
- `.claude/harness-spec.md` — Goals·inventory·Validation·Change history
- 이 계획 파일 → 머지 후 `.claude/plans/260826/`로 이동(README 규칙)

## 검증

- 단위: `python3 -m unittest discover -s tests/legacy -p 'test_*.py'` 외 `tests/260813`, `260814`, `260823`를 각각(R30: 루트 discover는 `NO TESTS RAN` exit 0).
- 실제 CLI: `tests/legacy` T2(env-gated) — C-A·C9가 코드를 건드리므로 돌린다. `scratchpad/reuse.sh`를 C8 응답 검증에 재사용.
- e2e: Phase 4의 재실행만(약 6시나리오 × 2회 = 12세션, 각 안에 코덱스 런 1~7개). baseline 19세션은 이 세션에서 끝났다. 성진이 비용을 감수한다고 했으므로 실행 전에 다시 묻지 않는다.
- 하네스: `validate_harness.py --path .` 0 errors, `audit_harness.py` 드리프트 0.

## 구현 세션이 받는 것 — 결정 목록 (이 세션에서 전부 확정)

| 항목 | 결정 | 근거 |
|---|---|---|
| 성공 기준 | 네 불변식(결과·안전·불필요 단계 없음·회복), 네이티브는 대조군 | 코덱스 반박 1 |
| C-A worktree 기본값 | (a) 공유 트리 기본, `--worktree` opt-in, `concurrent_writers`·preamble 유지 | P2c·P2c2·현장 보고 2건·재현 |
| C1 대응표 | SKILL.md `## Which mode`, 대조군 셋(`Agent`/`Workflow`/팀) × 세 열(가능/전제/불가능), `--help`에는 없음. 팀 열의 "가능"은 P11c의 모양(라운드 경계 중계, 파일로 주고받기), "불가능"은 턴 안 채널·상호 통신·공유 보드 | 코덱스 반박 4, R54·R56, P11 |
| 메일박스 | 후속 후보, 설계 스케치와 착수 조건만 스펙에 | 43런 중 질문 0건, P11c |
| C10 기본값 | 격리 아래서 `config.toml`의 `model`·`model_reasoning_effort`·`service_tier`를 선별 주입; 플래그 > resume 기록 > config > 서버. 별도 `.toml`은 만들지 않음 | 성진 결정, 21세션 argv 전부 model/effort 없음 |
| C2 모드 결정 | 두 축(런 개수·주소 / 라운드 사이 계산) | 코덱스 반박 2, P4c |
| C4 표면 | `--config`·`--no-worktree`·`--no-preamble`·`--isolate`·`--interval` 퇴역; 나머지는 성진이 목록으로 확인 | 실런 51건 0회 + R24, 성진 결정 |
| C5 description | 변경 없음 | 성진 결정 |
| C6 `status` 형식 | `status --follow` help에 두 형식 명시; `--json` 없음 | 현장 보고 2건 |
| C7 대기 규칙 | 한 턴짜리는 무장 없이 마지막 호출을 포그라운드로; 알림 하나 vs 이벤트마다의 기준 | P9c·P10c·현장 보고 2 |
| C8 gitignore | `batch start` 응답에 `missing_ignored`, gotcha 한 문장 | 재현 |
| C9 그룹 중간 신호 | `log --group --follow`, `--heartbeat` opt-in | 현장 보고 2 |
| 보류 | `--carry`(재고 조건 명시), C3 argparse 힌트 | 위 |

## 이 계획이 약속하는 것과 약속하지 않는 것

**서브에이전트처럼 — 예.** 21세션에서 단일·이어가기·플래그·트리거는 이미 네이티브와 같은 판단이 나왔고, 갈라진 한 곳(worktree 기본값)을 C-A가 닫는다. 판정은 기대가 아니라 같은 러너의 재실행 2회다. **워크플로처럼 — 예.** P4c가 이미 그렇게 했고 C2는 기준을 또렷하게 할 뿐이다. **팀처럼 — 아직 아니오, 구조적으로.** 런은 서로 메시지를 못 보내고 턴 안으로 채널이 없다; 도달점은 P11c의 "라운드 경계에서 파일로 주고받기"이고 메일박스는 근거가 쌓이면 다음 릴리스. 어떤 구현으로도 안 사라지는 차이 둘: `Agent`는 하네스가 턴을 붙들지만 코덱스 팔로워는 대화형의 알림으로만 같은 효과를 낸다(한 턴짜리는 C7의 규칙으로); 위임마다 `--help` 한 번(≈2k 토큰)과 코덱스 자체의 턴 시간이 붙는다 — 다른 프로세스를 부르는 비용이다.

## 네 프레임 — 변경마다 통과해야 하는 검사

`principle over rail`, `interface over document`, `for user not developer`, `dense information`은 이 스킬의 헌장이고, 아래는 각 변경이 어느 프레임에서 나왔는지와 구현 중 위반을 잡는 질문이다. PR 본문 `## 검증`에 변경마다 이 네 줄의 답을 적는다.

| 변경 | 프레임 | 위반 검사 |
|---|---|---|
| C-A 공유 트리 기본 | **interface**: 잘못된 기본값은 문서로 못 고친다 — P2c-r은 `--no-worktree`를 스스로 골랐지만 P2c는 못 골랐다 | "이 배치는 격리해야 한다"는 판단이 프로즈의 규칙이 아니라 `--worktree` 한 플래그의 존재로 가르쳐지는가 |
| C1 대응표 | **principle**: 대응은 클로드가 자기 도구로 이미 아는 것을 옮겨 오는 것이라 규칙 없이 판단을 재유도한다; **for user**: 읽는 이는 위임하려는 클로드, 개발자가 아님 | 표의 어느 칸이 "왜"를 잃고 등호만 남았나(코덱스 반박 4) / 스펙의 R-기록 서사가 섞여 들어왔나 |
| C2 두 축 | **principle**: "여럿이면 batch" 같은 레일 대신 축 둘로 어떤 새 과제도 스스로 분류 | 축으로 분류가 안 되는 과제 하나를 만들어 보라 — 있으면 축이 틀린 것 |
| C4 `--config` 제거 | **interface**: 불변식을 뚫는 파라미터는 존재 자체가 오판 | 남긴 플래그마다 "클로드가 내려야 하는 결정인가"에 답이 있나 |
| C6 `status` 형식 | **interface**: 도구가 아는 사실은 `help=`에, 프로즈 금지 | `test_prose_does_not_restate.py`에 형식 재진술 패턴 추가 |
| C7 대기 규칙 | **principle**: "알림 하나 vs 이벤트마다"를 기준으로 주고 기본값을 강요하지 않음; **dense**: 문장 하나로 — 사례(P9c·P10c)는 스펙에, SKILL.md에는 규칙과 그 이유만 | SKILL.md의 새 줄 수 ≤ 5, 사례 서사 0 |
| C8 `missing_ignored` | **interface**: 도구가 그 순간 아는 사실을 응답으로(R14의 교훈); gotcha는 도구가 말 못 하는 결과("거짓 회귀")만 | 응답 필드와 gotcha 문장이 같은 사실을 두 번 말하지 않나 |
| C9 `log --group` | **interface**: 손 폴링 루프를 도구가 흡수; **for user**: 하트비트는 Monitor에 물린 클로드를 위한 것이라 opt-in | `--help`가 "언제 켜라"가 아니라 "무엇을 낸다"만 말하나 |
| C10 config 세 키 | **interface**: 정책은 사용자 파일에, 스킬은 그것을 존중; **for user**: 편집 경로가 코덱스의 `/model`·`/fast` 그대로 | 스킬 디렉터리에 정책 파일이 생기지 않았나 / `--help`가 우선순위 네 단계를 한 문장으로 말하나 |
| C5·`--carry`·메일박스 보류 | **principle**: 근거 없는 확장은 레일이 된다 | 스펙에 `declined` + 재고 조건이 있나 |

**dense information의 전역 검사**: SKILL.md 총 줄 수가 지금(118)보다 늘어나면 어느 문장이 주장을 되풀이하는지 찾는다. 대응표(C1)와 대기 기준(C7)이 더해지지만, 47·51행의 배치↔Workflow 단락과 104행의 "resume은 격리 못 함" gotcha(C-A 뒤엔 사실이 아님)가 빠진다.

## 가정과 미결

- 가정: 재측정 러너의 격리 조건(`--setting-sources project`)이 성진의 실제 세션(전역 `CLAUDE.md` 있음)보다 엄격하다. 실제 세션에서는 위임 정책이 더해질 뿐 스킬 단독 결과를 뒤집지 않는다고 본다.
- 미결 없음. 구현 중 새 증거가 결정을 뒤집으면 스펙의 R-기록으로 남긴다.
