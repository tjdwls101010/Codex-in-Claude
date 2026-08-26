# 감사 기록 — `codex` 스킬 (2026-08-01)

**성격:** 이 문서는 *기록*이다. 무엇을 고칠지에 대한 지시는 `implementation-plan.md`에 있다. 여기 있는 것은 각 소견의 근거이며, 구현 중 "이게 왜 문제라고 했더라"를 되짚을 때 열어보는 파일이다.

**방법:** 다섯 개 축(트리거·본문·CLI 표면·오케스트레이션 준비도·정확성/테스트)으로 병렬 감사를 돌려 45개 소견을 얻고, 각 소견마다 **독립된 검증자 한 명씩을 붙여 "반박하라, 확신 없으면 기각하라"**로 지시했다. 검증자는 실제 파일을 열고, 재현을 주장한 소견은 직접 재현하도록 했다.

**결과: 45개 중 21개 확정, 24개 기각.** 확정된 것 중 blocker는 없다. 최고 심각도는 major다. 21개는 중복 병합 후 **16개 항목**이 된다.

기각된 24개 중 상당수는 *실제로는 `.claude/harness-spec.md`에 이유와 함께 기록된 의도적 설계 결정*이었다. 그 목록은 §4에 있고, **다시 제기하지 말 것**.

---

## 1. 평결

> 잘 만들어진 스킬이고, 설계 기록이 이례적으로 규율 있다. 메커니즘 — 런당 프로세스 그룹, 원자적 의도를 가진 레지스트리, 커서 기반 이벤트 스트리밍, 샌드박스 재주입, 컨텍스트 상한 출력 — 은 옳다. 리뷰어가 "빠졌다"고 부를 것의 대부분은 `harness-spec.md`에 의도적으로 기록된 결정이었다.
>
> 지배적 결함 유형은 **단일 런 가정이 다중 런 경로로 새는 것**이다. 표시용 절단이 "돌고 있는 게 있나"의 답을 조용히 바꾸고, 레지스트리 쓰기에 락이 없고, `reap()`이 낡은 스냅샷으로 판단해 정상 종료를 덮어쓰고, `log`/`resume --last`가 조용히 "가장 최근 런"을 고른다.
>
> 두 번째 유형은 resume 시의 설정 드리프트(`priority`, `--config` 미상속)와, 파일시스템이 제공하지 않는 격리를 약속하는 문서다.
>
> 배치 기능은 첫 번째 유형의 폭발 반경 정중앙에 있다. 저 결함들은 전부 *동시에 떠 있는 런 수에 비례해* 악화된다.

## 2. 손대지 말아야 할 것 — 의도적으로 옳은 부분

구현자가 "개선"하려다 망칠 수 있는 지점이라 명시한다.

- **프로세스 그룹으로만 stop, 이름 매칭은 절대 안 함.** `codex_bridge.py:486`의 SIGINT/유예 → SIGTERM → SIGKILL 사다리. SIGINT를 무시하는 자식 프로세스를 상대로 실제 검증됨(5.26초, reap 정상). `harness-spec.md:45`(B8)에 이름 매칭 거부가 기록되어 있다.
- **`status`의 `running` 목록은 이미 조용한 조인 신호다.** 살아있는 런 3개를 대상으로 until-루프로 검증됨. `harness-spec.md:107`이 "오케스트레이션은 Claude 쪽 일"이라고 기록한다. 배치 기능은 이 노선을 따라야 한다 — 그룹 *상태*를 노출하되 코디네이터 루프를 만들지 말 것.
- **`doctor`의 exit 0/2 프로토콜.** 의도적이고 두 곳(`environment.md:148`, `troubleshooting.md:3`)에 문서화되어 있으며, "진단이 실패함"과 "환경에 blocker가 있음"을 옳게 구분한다.
- **`file_change` 이벤트는 기본 레벨에서 경로를 이미 찍는다** (`_events.py:207-215`). 런 간 파일 충돌은 `log`로 이미 답할 수 있다.
- **컨텍스트 규율은 실재하고 적용되어 있다.** `last_agent_message` 400자, `stderr_tail` 800자, 레벨별 이벤트 포매팅, `show --item`이 유일한 명시적 opt-in.
- **description의 트리거 표면과 near-miss.** 헤드리스로 실증됨(`harness-spec.md:221-229`). 목록에 없는 한국어 표현에도 발화하고, Codex를 언급하지 않은 리뷰 요청에는 발화하지 않는 것이 확인됨. **건드리지 말 것.**
- **`_codex.py:60-61`의 `--last` argv 가드는 죽은 코드가 아니다.** `resume -- --last`로 도달 가능하며, `--last`가 Codex에 리터럴 세션 id로 넘어가는 것을 막는다.
- **`allowed-tools`는 제한이 아니라 가산이다.** 실측: 스킬이 활성인 상태에서 Skill·Read·Write가 모두 성공했다. 세 도구를 추가로 선언할 필요 없다.

## 3. 확정된 소견 16개

심각도 순. `location`은 감사 시점의 줄 번호이므로 구현 시 재확인할 것.

### 3.1 major — 레지스트리 동시성

| # | 항목 | 위치 |
|---|---|---|
| F1 | `write_meta`가 모든 쓰기를 고정된 `.meta.json.tmp` 경로로 스테이징하고, `update_meta`는 락 없는 read-modify-write다 | `_registry.py:73-85`, 훅에 중복 구현 `hooks/codex_session_cleanup.py:158-163` |

**재현됨.** 두 프로세스가 같은 run_dir에 쓰면 240회 중 120회가 잡히지 않은 `FileNotFoundError`를 낸다 — 두 번째 writer가 첫 번째의 inode를 `O_TRUNC`하고, 첫 번째의 `os.replace`가 사라진 소스를 대상으로 실패한다. 키가 유실되기도 하고, 리더가 반쯤 쓰인 JSON을 볼 수도 있다. `replace` 자체는 원자적이지만 **공유된 tmp *경로*는 원자적이지 않다.** docstring이 주장하는 원자성과 모순된다.

수정: tmp 이름을 writer마다 고유하게(`f".meta.json.{os.getpid()}.{uuid4().hex[:8]}.tmp"`) + `run_dir/.meta.lock`에 `flock`을 읽기·쓰기 전체에 건다. 훅은 제거되므로(D23) 훅 쪽 중복은 자연히 사라진다.

| # | 항목 | 위치 |
|---|---|---|
| F2 | `reap()`이 호출자의 낡은 스냅샷으로 판단하고 `update_meta`(재읽기)로 커밋한다 | `_registry.py:135-154` (쓰기는 :153), 낡은 호출자 `codex_bridge.py:273, 527, 686` |

**재현됨.** 스냅샷 시점과 `pid_alive` 검사 사이에 수퍼바이저가 `completed`를 쓰고 종료하면, `reap`이 그 위에 `orphaned`를 덧씌운다. 결과는 `state: orphaned, exit_code: 0`이고 `ended_at`이 뭉개진다. **자가 치유되지 않는다** — 한 번 기록되면 영구적이다.

수정: `update_meta_if(run_dir, ("running","starting"), …)` 같은 compare-and-set을 도입한다. `pid_alive`가 False를 반환한 뒤 다시 읽고, 상태가 이미 종료 상태면 그대로 반환한다. `ended_at`/`supervisor_pid`도 새로 읽은 meta에서 가져온다.

### 3.2 major — status API

| # | 항목 | 위치 |
|---|---|---|
| F3 | `cmd_status`가 `rows`를 최신 20개로 자른 **뒤에** `running`과 `threads`를 파생시킨다 | `codex_bridge.py:352-361` |

**재현됨.** 런 25개 중 가장 오래된 3개가 살아있는 상태에서 `status`는 `rows: 20, running: []`을 반환하고, `status --all`은 `rows: 25, running: ['…-0000','…-0001','…-0002']`을 반환한다. 페이로드 어디에도 절단이 일어났다는 표시가 없다.

표시용으로는 방어 가능한 절단이 파생 요약에서는 조용히 틀린 답이 된다. 페이즈 게이트는 문자 그대로 `len(running) == 0`이므로, 배치 5개가 몇 페이즈만 돌아도 한 세션 안에서 레지스트리 20개를 넘고, 그 뒤로는 런이 아직 쓰고 있는데도 게이트가 통과한다.

수정: `running`/`threads`/`--include-external`의 `known`을 자르기 **전** 전체 목록에서 계산한다. 표시용 `runs`만 자르되 비종료 행은 절대 떨어뜨리지 않는다. `total_runs`와 `runs_truncated`를 추가한다.

### 3.3 major — 런 선택

| # | 항목 | 위치 |
|---|---|---|
| F4 | `resume --last`가 프로젝트 전체에서 최신 런을 고르고, `--run` 없는 `log`도 `runs[-1]`을 고른다. 게다가 같은 스레드에 이미 턴이 돌고 있는지 아무도 확인하지 않는다 | `codex_bridge.py:218-222`, `:385-388`, `:195-243` |

**재현됨, 두 가지.**
1. read-only 호출자가 `resume --last`를 부르자 남의 런에서 `--label phaseB`**와** `danger-full-access` 샌드박스를 함께 상속했다. 즉 조용한 오작동이 아니라 **조용한 권한 상승**이다.
2. 한 스레드에 동시에 두 턴을 돌렸는데 rc 0, 경고 없음.

수정: 살아있는 스레드가 2개 이상이면 후보 목록과 함께 실패시킨다. JSON에 `resolved_from_run_id`/`label`/`sandbox`를 반향한다. 살아있는 스레드에 두 번째 턴은 `--force` 없이는 거부한다.

**중요:** `claude_session_id`로 범위를 좁히지 말 것. 서브에이전트 Bash에서 비어 있거나 공유되는 값이라 신뢰할 수 없다(F5 참조).

| # | 항목 | 위치 |
|---|---|---|
| F11 | `log`의 커서 트레일러가 run id 없는 `# cursor=<n>`이고, 범위를 벗어난 `--since`가 조용히 받아들여진다 | `codex_bridge.py:402, 418, 423`; `_events.py:61-62` |

아무것도 출력하지 않고 exit 0으로 나쁜 커서를 그대로 반향하므로, 스트림이 영구히 죽는다. 런이 여럿이면 커서끼리 구분이 안 되어 잘못된 커서를 되먹이기 쉽다.

수정: `# cursor=<n> run=<id>`로 자기 식별시킨다. `--since`가 이벤트 파일 크기를 넘으면 `fail(...)`. **다중 런 `log`는 만들지 말 것** — 감사가 별건으로 기각했다(§4).

### 3.4 major — 세션 범위

| # | 항목 | 위치 |
|---|---|---|
| F5 | Claude 서브에이전트에서 시작된 런은 서브에이전트의 `CLAUDE_CODE_SESSION_ID`를 기록한다 | `codex_bridge.py:138`, `:518-529`, `:685-687` |

**재현됨.** 최상위 SessionEnd 훅이 그 런을 건너뛴다(pgid가 살아남고 meta는 `running`인 채로 남음). `stop --all-mine`도 도달하지 못한다.

**본 계획에서의 처리:** 훅과 `--all-mine`을 모두 제거하기로 했으므로(D23·D25) 이 소견의 두 소비자가 사라진다. 남는 교훈은 하나 — **`claude_session_id`를 선택자로 쓰지 말 것.** 기록은 계속 하되(디버깅 출처 정보로 무료다) 아무 명령도 그것으로 대상을 고르지 않는다.

### 3.5 major — 설정 드리프트

| # | 항목 | 위치 |
|---|---|---|
| F6 | resume 시 `priority`가 `base`가 아니라 `isolated`에서 재유도되고, `extra_config`(`--config k=v`)는 아예 상속되지 않는다 | `codex_bridge.py:104`, `:132` |

**재현됨.** `start --no-priority --config tools.web_search=true`로 시작한 스레드를 `resume --last`하면 `service_tier="priority"`가 조용히 되살아나고 `-c`가 사라진다. 다른 모든 기록 설정(샌드박스·모델·effort·schema_path·isolated)은 `base[...]`로 폴백하는데 이 둘만 빠졌다. **레지스트리가 존재하는 이유가 바로 이 종류의 드리프트를 막는 것**이므로 특히 아프다.

수정: 둘 다 `base`에서 상속한다. `priority = isolated and inherited_priority`를 유지해 격리된 부모를 `--inherit-config`로 이어받아도 priority가 안 붙게 한다. `tests/test_argv.py:202`가 기본값이 아닌 값을 단언하도록 강화한다.

### 3.6 major — 문서

| # | 항목 | 위치 |
|---|---|---|
| F7 | 병렬 절이 *시그널에 한해서만* 성립하는 격리를 약속하고, 동시 런이 하나의 git top level과 하나의 `.git/index`를 공유한다는 사실을 말하지 않는다 | `SKILL.md:97-99`, `:39`, `:46`; 메커니즘은 `codex_bridge.py:88-89`, `:103`, `:256` |

`project`는 `git_toplevel(cwd) or cwd`이고 그 한 줄 아래 샌드박스 기본값은 `workspace-write`다. 즉 `start` × 3의 기본 동작은 **한 워크트리·한 git 인덱스·한 파일 집합에 쓰기 권한을 가진 독립 GPT 에이전트 3개**다. `--cwd`/`--add-dir`는 `start` 전용이라 나중에 격리를 붙일 수 없다. `status`의 다중 런 필드와 20행 상한도 문서화되어 있지 않다. `review --uncommitted`는 다른 런이 쓰고 있는 트리를 diff한다.

수정: 공유 워크트리 위험과 세 가지 레버(`start` 시점의 `--cwd`, writer마다 `git worktree`, `--sandbox read-only`)를 명시하는 gotcha를 추가한다. 프로세스 그룹 주장의 범위를 시그널로 한정한다. `running`/`threads`/상한을 문서화한다.

**이 소견의 수정은 배치 기능의 worktree 격리 요구사항 그 자체다** — 문서가 아니라 코드로 승격된다.

### 3.7 minor / nit

| # | 항목 | 위치 | 요지 |
|---|---|---|---|
| F8 | `turn.failed`가 파싱되고 버려짐 | `_events.py:240, 251`; `codex_bridge.py:308-334`, `:556-559` | `status`/`result`가 `state: failed, exit_code: 1, message: null`을 보이고 이유는 `log`를 한 번 더 불러야 나온다. `grep -rn turn_failed`가 `_events.py` 두 줄만 잡는다 |
| F9 | 잡히지 않은 예외가 "한 줄 JSON" 계약을 깬다 | `codex_bridge.py:71-72`, `:821-829`; `_events.py:64` | `start --prompt-file <없는파일>`이 트레이스백을 stderr에 찍고 stdout은 비운다. `log --since -1`은 `seek`에서 `OSError`. 인접한 두 경우(schema·image)는 명시적으로 처리되어 있어 더 눈에 띈다 |
| F10 | `query_threads`가 `limit*4`를 과다 페치한 뒤 파이썬에서 cwd를 거른다 | `_codex.py:256-289`; 소비자 `codex_bridge.py:227`, `:364` | **재현됨** — 다른 디렉터리의 새 스레드가 4개 이상이면 빈 레지스트리에서의 `resume --last`가 "기록된 스레드 없음"을 보고한다. 스키마가 바뀌어 `id` 컬럼이 빠지면 우아한 성능 저하 대신 `KeyError`. **`threads` 테이블을 채우는 테스트가 하나도 없다** |
| F12 | `SKILL.md:81`의 "모든 호출에서 레지스트리로부터 설정을 재주입한다"가 레지스트리에 없는 경우를 빠뜨린다 | `SKILL.md:81`; 코드 `codex_bridge.py:238`, `:88`, `:103`, `:227-231` | **재현됨** — TUI 스레드를 이름으로 resume하면 래퍼의 `workspace-write` 기본값과 프로젝트 루트를 받는다. 코드 기본값은 옳고 **산문만 과잉 약속**이다 |
| F13 | `--no-preamble`이 무엇을 끄는지 어디에도 정의되어 있지 않다 | `SKILL.md:46`; `_codex.py:117-127`; `codex_bridge.py:722` | SKILL.md에도, references에도, `--help`에도 없다. `result`가 의존하는 "답을 최종 메시지에 넣어라" 절도 포함해서 |
| F14 | troubleshooting.md의 경로 해석 두 행이 SKILL.md에 더 이상 없는 스니펫을 가리킨다 | `references/troubleshooting.md:9-10`; `SKILL.md:30` | 그 스니펫의 `$VAR` 폴백은 `harness-spec.md:171`이 **틀렸다고 기록**한 바로 그것이다. 게다가 `SKILL.md:30`의 "doctor를 실행하라"는 순환이다 — doctor는 방금 해석에 실패한 그 파일의 서브커맨드다 |
| F15 | run id 충돌이 잡히지 않은 `FileExistsError`가 된다 | `_registry.py:57-61`; `codex_bridge.py:108` | 1초 스탬프 + 라벨 + uuid 16비트라 같은 초·같은 라벨 시작 쌍당 약 1/65536. docstring은 "병렬 시작에서 충돌 없음"이라고 과장한다. **배치 시작은 같은 초·같은 라벨 시작을 정상 케이스로 만든다** |
| F16 (nit) | `signal_run`의 SIGTERM/SIGKILL 승격이 어떤 테스트에서도 실행되지 않는다 | `codex_bridge.py:486`; `tests/test_lifecycle.py:35`; `tests/fake_codex/codex:154` | 가짜 `codex`가 SIGINT에 죽고, 유일한 단언이 `assertIn("SIGINT", …)`이라 `["SIGINT"]`와 `["SIGINT","SIGTERM","SIGKILL"]`을 구분조차 못 한다. 사다리 자체는 실제로 작동함이 검증됨 — 격차는 회귀 탐지에만 있다 |

## 4. 확인하고 종결됨 — 다시 제기하지 말 것

각각 조사되어 근거와 함께 기각되었다.

- **`--label`을 선택자로 / 라벨로 배치 stop** — 이름 매칭 stop은 의도적으로 거부됨(`harness-spec.md:45`, B8). `status --all`이 이미 행마다 `label`을 반환하므로 클라이언트 측 필터로 충분하다. *단, 본 계획의 `--group`은 이 기각에 해당하지 않는다* — 라벨 문자열 매칭이 아니라 meta에 기록된 명시적 그룹 id를 레지스트리에서 run id로 해석한 뒤 각 런의 pgid에 시그널하는 것이며, B8이 금지한 것은 프로세스 *이름* 매칭이다.
- **`wait`/`join` 동사** — `status`의 `running`이 이미 N개 런 조인을 제공한다. → **D05에서 `status --group --follow`로 해소.**
- **`result`가 변경 파일 경로를 나열해야 / 여러 런을 받아야** — `file_change`가 기본 레벨에서 이미 경로를 찍는다. 무제한 경로 목록을 `result`에 넣는 것은 컨텍스트 규율의 역전이다. → **D30에서 "겹침만" 으로 해소.**
- **`status` 페이로드 중복 / `--brief` 필요** — status는 이미 자르고 거르고 상한을 건다. 스펙의 "컨텍스트 규율" 제약은 Codex의 파일 내용에 관한 것이지 레지스트리 메타데이터가 아니다.
- **`--foreground` 유무에 따른 `start`의 두 JSON 모양** — 의도적이고 테스트되어 있다. `result`/`status`가 균일한 계약이다.
- **`run_dir` / `last-message.txt` 핸들 없음** — `emit()`이 한 줄 JSON을 쓰므로 `result … > out.json`으로 이미 메시지를 컨텍스트 밖에 둘 수 있다.
- **`stop`의 직렬 승격 비용(N×9초)** — SIGINT를 존중하는 정상 자식 4개에 대해 1초 미만으로 측정됨. `--grace`는 호출자가 조절 가능하다.
- **`threads` 맵의 `"(unknown)"` 센티넬** — 프로그램적 소비자가 없고 `runs`에 `thread_id: null`이 이미 있다.
- **`doctor`의 exit-2 프로토콜** — 두 번 문서화됨. `error`와 합치는 것은 회귀다.
- **예제의 `$CODEX` 축약** — 헤드리스 e2e 5세션이 리터럴 경로를 썼다. 오작동 관측 없음.
- **`--timeout`의 백그라운드 "조용한 no-op"** — `--foreground [--timeout <sec>]`로 문서화되어 있고, 백그라운드 데드라인 없음은 기록된 기본값이다(`harness-spec.md:71`). → *본 계획은 이를 버그 수정이 아니라 **새 기능 결정**(D26)으로 다룬다.*
- **"stderr 내용을 실패로 취급하지 말라"** — `troubleshooting.md:15`와 일관된다. 실패 신호는 `state`/`exit_code`이고 같은 문장이 `stderr_tail`을 가리킨다.
- **비용 절 중복 / 팬아웃 산술 누락** — 의도적. 스펙이 방법론 레일을 금지하고 측정치가 주장과 함께 다닐 것을 요구한다.
- **description: 병렬 단어 누락, 맨 `GPT` 트리거, 한국어 조사 낭비, TUI 미부인, 타 스킬 충돌** — 전부 실증되었거나 기록된 설계 결정. description은 의도적 미발화를 포함한 헤드리스 e2e로 검증되어 있다.
- **`allowed-tools`가 Read/Write/Monitor를 제한한다** — 실측: 가산이다. 헤드리스 실행에서 Skill·Read·Write 모두 성공.
- **심볼릭 링크 설치에서 `allowed-tools` 미매칭** — README/troubleshooting의 `settings.json` 처방이 옳다. `doctor`의 `bridge_path`를 붙여넣는 것은 오히려 매칭되지 않는다(권한 규칙은 명령 *텍스트*를 매칭한다).
- **`resume --last`의 argv 분기가 죽은 코드** — `resume -- --last`로 도달 가능한 살아있는 가드다.
- **동시성 상한 / `--max-concurrent`** — opt-in 상한은 그것을 정당화하는 데 쓰인 폭주 시나리오를 잡지 못하고, 기본 상한은 자동 거부하지 않는다는 자세와 모순된다. → *본 계획은 상한을 두지 않고 비용을 보고한다(D10). `--max-concurrent`는 안전장치가 아니라 큐잉 수단으로만 제공한다.*
- **`stop --all-mine`이 detached 런을 죽인다** — 의도적. `--detach`는 자동 훅만 면제한다. → *훅 제거(D23)로 무의미해짐.*

## 5. 부수적으로 확인된 환경 사실

배치 설계가 이 위에 서 있으므로 기록한다.

| 사실 | 근거 |
|---|---|
| dynamic-workflow 서브에이전트는 `Skill` 도구를 가지고 있고, 스킬 목록에서 `codex`를 본다 (이 머신에서는 `~/.claude/skills/codex`가 프로젝트를 가리키는 심볼릭 링크라 접두사 없는 `codex`) | 워크플로 서브에이전트의 자기 컨텍스트 검사. 22개 스킬 목록 전문 확보 |
| 그러나 스킬은 **자동 로드되지 않는다.** `Base directory for this skill:` 줄은 `Skill()` 호출 이후에만 나타난다 | 같은 프로브. 호출하지 않은 상태에서 해당 문자열이 컨텍스트에 없음 |
| **워크플로 서브에이전트는 스킬을 로드하지 않고도 `codex_bridge.py`를 Bash로 실행할 수 있다 — 승인 프롬프트 없이 exit 0** | `doctor` 전문 JSON 반환 확인 |
| `~/.claude/skills/codex`는 중복본이 아니라 프로젝트로의 심볼릭 링크 (양쪽 SKILL.md inode `238286158`, `diff -r` 비어 있음) | 트리거 감사자의 직접 확인 |
| 이 머신의 `config.toml`은 `sandbox_mode = "danger-full-access"`, `approval_policy = "never"` | `doctor` 출력. 래퍼가 매 호출 `-c sandbox_mode=`를 넣으므로 폴백에 도달하지 않지만, 사용자가 직접 치는 `codex`는 이 값을 맞는다 |
