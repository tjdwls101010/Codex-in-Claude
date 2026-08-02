# 구현 계획 — `codex` 스킬 v0.2.0 (배치 오케스트레이션 + 감사 소견 반영)

**상태:** 승인됨, 구현 준비 완료. 2026-08-01 계획 전용 세션에서 작성.
**독자:** 이것을 구현할 다음 Claude 세션.
**동반 파일:** `audit-findings.md`(같은 디렉터리 — 근거 기록), `.claude/harness-spec.md`(계약), `docs/plan/codex-skill-implementation-plan.md`(v0.1.0의 원 계획, 여전히 유효한 배경).

이 문서는 *지시*다. "왜 이게 문제인가"는 `audit-findings.md`에 있으니 여기서 반복하지 않는다.

---

## 0. 이 문서를 읽는 법

**§2의 결정(D01~D33)은 재논의 금지다.** 각각 사용자와 합의된 것이고, 상당수는 감사 결과와의 충돌을 사용자에게 다시 제시해 확정한 것이다. 구현 중 결정 하나가 틀렸다는 *증거*를 발견하면 — 계획대로 하면 깨진다는 재현 가능한 사실 — 멈추고 기록하고 사용자에게 물어라. 마음에 안 든다는 이유로는 바꾸지 마라.

**방법은 열려 있다.** §3 이후의 구현 상세는 근거와 함께 제안된 것이며, 더 나은 방법을 찾으면 바꿔도 된다. 다만 바꾼 이유를 `harness-spec.md`의 Change history에 남겨라. v0.1.0에서 이 방식이 R1~R9를 낳았고, 그게 정상 작동이었다.

**먼저 로드할 것:**
- `~/.claude/skills/harness-creator/references/skills.md` — SKILL.md나 `references/*.md`를 쓰기 전
- `~/.claude/skills/harness-creator/references/e2e-testing.md` — T4 전
- `audit-findings.md` §2 "손대지 말아야 할 것" — 코드를 건드리기 전

**두 가지 원칙이 v0.1.0에서 그대로 이어진다:**

1. **확신 위의 순응.** 스킬에 쓰는 모든 지시에는 모델이 열거되지 않은 케이스를 스스로 유도할 수 있을 만큼의 *이유*가 붙는다. 이유 없는 숫자는 숫자를 쓴 레일이다.
2. **사용 목적 레일 금지.** 스킬은 **메커니즘 + 가처(gotcha) + 판단기준**을 가르치고, 승인된 작업 메뉴는 절대 담지 않는다. 감사에서 "SKILL.md에 팬아웃 비용 산술을 넣어라" 같은 소견이 바로 이 원칙을 근거로 기각되었다. `references/orchestration.md`를 쓸 때 이 유혹이 가장 강하게 온다(D31 참조).

**세 번째 원칙이 이번에 추가된다:**

3. **스킬은 역량만 담는다.** 비용 정책·정리 정책은 사용자의 것이다. SessionEnd 훅이 제거되는 이유가 이것이며(D23), 새 기능에서도 "사용자를 대신해 무엇을 죽이거나 거부하는" 설계는 채택하지 않는다. 상한을 강제하는 대신 비용을 보고한다(D10).

---

## 1. 무엇을 만드는가

한 문장: **여러 Codex 런을 하나의 그룹으로 띄우고, 그룹 단위로 지켜보고, 그룹 단위로 수거하는 원시기능을 브릿지에 넣는다. 페이즈를 엮는 판단은 Claude가 한다.**

사용자의 원 요구:

> 혹시 `codex` 스킬을 한개한개 개별적인 서브에이전트로 실행하는 것을 넘어, `dynamic-workflow`처럼 여러 개의 서브에이전트를 페이즈로 구성하고, 그 페이즈를 여러개 구성해 순차적으로 실행하는 식으로 작동하도록 할 수도 있을까?

이것을 **dynamic-workflow 위에 올리지 않기로** 했다(D01). 이유는 세 가지이며 전부 실측 또는 문서 근거가 있다.

- 워크플로 스크립트는 **셸을 돌릴 수 없다.** 에이전트만 명령을 실행한다. 따라서 Codex 런 하나마다 Claude 서브에이전트를 하나씩 감싸야 하고, 워커당 (Claude + Codex) 이중 과금이 된다.
- 이 스킬의 정체성은 컨텍스트 규율이다. "기다렸다가 수거한다"가 일의 대부분인 작업에 Claude 서브에이전트를 붙이는 것은 그 정체성과 어긋난다.
- 그룹 상태가 자연스럽게 붙을 곳은 이미 존재하는 레지스트리다.

**그러나 워크플로 경로가 막힌 것은 아니다.** 실측으로 확인된 사실(`audit-findings.md` §5): 워크플로 서브에이전트는 `codex` 스킬을 *로드하지 않고도* `codex_bridge.py`를 승인 프롬프트 없이 실행할 수 있다. 즉 워크플로 스크립트가 `agent()` 프롬프트에 배치 명령 한 줄을 박아 넣으면, 그 서브에이전트는 명령을 그대로 실행하는 얇은 껍데기로 동작한다. `/workflows` 진행 UI가 필요하거나 페이즈를 재사용 가능한 명령으로 굳히고 싶을 때의 경로로서 `references/orchestration.md`에 한 절로 적는다(D12·D31 범위 안에서, 예제 워크플로 파일은 동봉하지 않는다).

### 만들지 않는 것

- 선언적 페이즈 계획 파일. 페이즈 순서와 다음 프롬프트는 Claude가 매번 결과를 읽고 정한다(D02).
- `wait`/`join` 동사. `status --group --follow`로 해소한다(D05). 감사가 "코디네이터 루프를 만들지 말라"고 명시했다.
- 다중 런 `log`. 감사가 별건으로 기각했다. `log`는 런 단위로 남는다.
- 동시 실행 상한. 비용을 보고할 뿐 막지 않는다(D10).
- `.claude/workflows/*.js` 예제 파일. D12의 근거(모양이 매번 달라지는 오케스트레이션은 얼리지 말라)가 그대로 적용된다.
- 페이즈 모양 카탈로그. `orchestration.md`는 메커니즘 + 가처만 담는다(D31).

---

## 2. 확정된 결정 — 재논의 금지

| ID | 결정 | 근거 요약 |
|---|---|---|
| D01 | 오케스트레이션 엔진은 **브릿지의 배치 원시기능**. dynamic-workflow 위에 올리지 않음 | 워크플로 스크립트는 셸 불가 → 워커당 이중 과금. 그룹 상태는 레지스트리에 붙는 게 자연스러움 |
| D02 | 페이즈 경계 판단은 **Claude가 매번 적응적으로**. 선언적 계획 파일 없음 | 위임의 모양이 앞 단계 결과에 따라 바뀜. 레일 금지 원칙과 일치 |
| D03 | 동시 쓰기 격리는 **git worktree** | 지금 코드에 아무 보호가 없음(감사 F7) |
| D04 | 범위 = **확정된 감사 소견 전부 + 신기능** | |
| D05 | 그룹 종료 대기는 **`status --group --follow`**. 새 `wait` 동사 없음 | 감사가 wait 동사 부재를 강점으로 분류. `--follow`는 이미 있는 개념이라 배울 게 늘지 않음 |
| D06 | worktree는 **남겨두고 diff 요약만 반환**, `batch clean`으로 명시적 정리 | "바이트만 보여주고 필요할 때 show"와 같은 규율 |
| D07 | 그룹 결과는 **런당 상한 + `result --run`으로 개별 전문 조회** | 같은 규율 |
| D08 | **`--resume-from <group>`으로 1:1 스레드 이어받기** 지원. 새 스레드도 가능 | resume 누적 비용은 Claude가 매번 판단 |
| D09 | 작업 명세는 **`--task` 반복 + 긴/이질적인 건 `--tasks-file <jsonl>`** | `--task`는 이미 승인된 Bash 패턴 안. `--tasks-file`은 Write 승인 프롬프트를 부름 |
| D10 | 동시 실행 **상한 없음. 투영 비용을 출력**. `--max-concurrent`는 안전장치가 아니라 큐잉 수단 | `out=8797B`와 같은 발상 — 결정으로 만들되 대신 결정해주지 않음 |
| D11 | 그룹 내 한 런 실패 시 **나머지 계속, partial 상태로 보고** | "아무것도 자동으로 죽이지 않는다"와 일관 |
| D12 | **`references/orchestration.md` 신규** + SKILL.md 본문엔 판단기준 몇 줄만 | 단일 런/그룹은 모델이 실제로 갈라지는 분기점 |
| D13 | 이름은 **`batch`** 동사, 그룹 식별자는 **`--group <name>`** | |
| D14 | 검증은 **T1~T4 전부** | |
| D15 | **v0.2.0까지** 계획에 포함 (CHANGELOG·README·wiki·태그·GitHub 릴리즈) | |
| D16 | 계획서는 **2파일**, `docs/plan/260801/` | |
| D17 | 더러운 트리는 **상태를 찍고 그대로 진행** | D10과 같은 자세 |
| D18 | worktree는 **workspace-write 런이 2개 이상일 때 자동**, `--no-worktree`로 끔 | read-only 검토 배치는 worktree를 받지 않아 사용자의 미커밋 변경을 그대로 봄 — 검토엔 이게 맞음 |
| D19 | 작업별 **`kind: start\|resume\|review`**, 기본 `start` | 세 경로가 이미 구현되어 있어 추가 비용이 거의 없음 |
| D20 | 배치 런 프리앰블에 **병렬 상황 사실 추가** (사실만, 방법론 금지) | B19의 경계 안 |
| D21 | `AGENTS.md` → `CLAUDE.md` 심볼릭 링크는 **의도적, 유지** | |
| D22 | 계획 강도: **결정은 박고 방법은 열어둔다** | v0.1.0에서 R1~R9를 낳은 방식 |
| D23 | **SessionEnd 훅 전면 제거.** SKILL.md의 관련 서술도 제거 | 사용자: *"이 훅은 내 비용 관리를 위한건데, 이거까지 스킬에 위임하고 싶진 않아. 스킬은 역량에 충실하면 좋겠어."* |
| D24 | **`--detach` 제거** (훅과 함께) | 훅이 없으면 아무것도 세션 종료 시 런을 죽이지 않으므로 `--detach`가 설명할 대상을 잃음 |
| D25 | `stop`은 **`--all-mine` 제거**, `--run` 반복 / `--group` / `--all`로 교체 | 세션 id는 서브에이전트에서 신뢰 불가(감사 F5). 범위를 눈에 보이는 것으로만 정함 |
| D26 | **`--timeout`이 백그라운드에서도 작동** | 훅 제거 후 남는 유일한 자동 상한이며, 정책이 아니라 호출자가 건별로 고르는 값 |
| D27 | 암묵적 대상(`--last`, `--run` 없는 `log`)은 **비종료 런이 2개 이상이면 거부** | 조용한 오작동 대신 시끄러운 실패 |
| D28 | 레지스트리 동시성 강화는 **배치 이전 독립 마일스톤** | 이 층이 흔들리면 그 위 배치 버그가 전부 재현 불가가 됨 |
| D29 | `batch`는 **그룹 생애주기만**(`start`, `clean`). 읽기·제어는 기존 명령 + `--group` | 한 일에 한 방법 |
| D30 | 그룹 결과는 **`overlaps: {path: [run_id]}`만**. 전체 경로 목록은 주지 않음 | 감사의 기각 사유와 사용자의 필요를 둘 다 만족시키는 유일한 지점 |
| D31 | `orchestration.md`는 **메커니즘 + 가처만**. 예제 페이즈 구성 없음 | |
| D32 | **M0에서 저장소 정리** (`__pycache__` gitignore + `git rm --cached`, 문서 산출물 커밋) | 더러운 트리가 worktree 기반 설계에서 직접 문제가 됨(D17) |
| D33 | 계획서 언어는 **한국어**. 코드·경로·식별자·인용은 원문 유지 | |

---

## 3. 명령 표면 설계

### 3.1 전체 그림

기존 9개 서브커맨드는 유지되고, 하나가 추가되며, 셋이 셀렉터를 얻는다.

| 명령 | 변화 |
|---|---|
| `batch start` | **신규** — 그룹을 띄운다 |
| `batch clean` | **신규** — 그룹의 worktree를 정리한다 |
| `status` | `--group <name>`, `--follow`, `--follow-timeout` 추가. 절단 버그 수정(F3) |
| `result` | `--group <name>` 추가, `overlaps` 필드 추가 |
| `stop` | `--all-mine` 제거. `--run` 반복 가능, `--group`, `--all` 추가 |
| `log` | 변화 없음(런 단위 유지). 커서 트레일러에 `run=<id>` 추가(F11) |
| `start` / `resume` / `review` | `--detach` 제거. `--timeout`이 백그라운드에서도 작동. `resume`의 설정 상속 수정(F6) |
| `show` | 변화 없음 |
| `doctor` | `detached_running` 제거. 대신 비종료 런이 같은 cwd를 공유하고 그중 하나라도 read-only가 아니면 경고 |

### 3.2 `batch start`

```
batch start --group <name>
            [--task "<prompt>"]…                  # 반복 가능
            [--tasks-file <path.jsonl>]           # 이질적/긴 프롬프트
            [--resume-from <group>]               # 1:1 스레드 이어받기
            [--worktree | --no-worktree] [--base <ref>]
            [--max-concurrent <N>]
            [공통 옵션: --sandbox --model --effort --schema --inherit-config
             --no-priority --config k=v --timeout --no-preamble --cwd --add-dir --label]
```

**작업 명세(D09).** `--task`와 `--tasks-file`은 함께 쓸 수 있고, 순서는 `--task`들 다음에 파일 항목이다. 그룹 수준 공통 옵션은 *기본값*이고 파일의 항목별 필드가 덮어쓴다.

`--tasks-file` 한 줄의 형태(모든 필드는 `prompt` 외 선택):

```json
{"prompt": "…", "kind": "start", "label": "moduleA", "model": "…", "effort": "…",
 "sandbox": "read-only", "schema": "…/s.json", "image": ["…"], "cwd": "…",
 "resume": "<run_id|thread_id>", "review": {"uncommitted": true}}
```

- `kind`(D19)는 `start`(기본) / `resume` / `review`. `resume`이면 `resume` 필드가 필수(또는 `--resume-from`이 대신 채운다). `review`면 `review` 객체가 `--uncommitted` / `--base` / `--commit` / `prompt` 중 하나를 지정한다.
- `--task "…"`로 준 항목은 언제나 `kind: start`다.

**`--resume-from <group>`(D08).** 앞 그룹의 멤버를 시작 순서대로 정렬해 이번 그룹의 작업과 **1:1로 짝짓는다.** 개수가 다르면 실패한다(짝을 추측하지 않는다). 짝지어진 각 작업의 `kind`는 `resume`이 되고 `resume` 대상은 앞 멤버의 `thread_id`가 된다. 앞 멤버의 worktree·cwd·샌드박스·모델·effort는 레지스트리에서 그대로 재주입된다(기존 불변식).

**앞 그룹 멤버 중 살아있는 턴이 있으면 거부한다.** 감사 F4가 "한 스레드에 동시 두 턴"을 재현했다. `--force`로만 넘어간다.

**출력** (한 줄 JSON):

```json
{"group": "p1",
 "runs": [{"run_id": "…", "label": "moduleA", "kind": "start", "cwd": "…", "sandbox": "workspace-write", "worktree": "…/.codex-runs/…/wt"}],
 "worktree": {"enabled": true, "base": "abc1234", "base_ref": "HEAD",
              "uncommitted_files": 7,
              "note": "the worktrees are cut from abc1234 and do not contain these 7 uncommitted files"},
 "projected_cost": {"runs": 3, "input_floor_per_run": 15800, "input_floor_total": 47400,
                    "note": "floor only — the isolated per-invocation base measured on this project. Real cost is higher and grows with each resume."},
 "max_concurrent": null,
 "queued": []}
```

`projected_cost`(D10)는 **막지 않고 보여주기 위한 것**이다. 숫자의 출처는 T3 측정(§9.3)이며, 측정 없이 상수를 박지 마라 — 그러면 이 프로젝트가 계속 거부해온 "이유 없는 숫자"가 된다. `uncommitted_files`가 D17의 구현이다.

**실패 정책(D11).** 어떤 작업의 스폰이 실패해도 나머지는 뜬다. 스폰 실패는 그 자리에서 `runs[]` 항목에 `error` 필드로 기록된다.

### 3.3 `status --group <name> [--follow]`

**스냅샷.** 그룹 멤버만 반환한다. 그룹 밖 런은 세지 않는다.

```json
{"group": "p1", "runs": [...], "running": [...], "done": [...], "failed": [...],
 "total_runs": 3, "runs_truncated": 0,
 "group_state": "running|completed|partial"}
```

- `group_state`: 전원 비종료 아님 → 전원 성공이면 `completed`, 하나라도 실패/중단/타임아웃이면 `partial`.
- **F3 수정이 여기에 걸린다.** `running`/`threads`/`done`/`failed`는 **자르기 전** 전체 목록에서 계산한다. 표시용 `runs`만 자르되 **비종료 행은 절대 떨어뜨리지 않는다.** `total_runs`와 `runs_truncated`를 언제나 낸다. `--group` 없는 `status`에도 같은 규칙이 적용된다.

**`--follow`(D05).** `log --follow`와 대칭이다.

- 상태가 바뀔 때마다 한 줄씩 찍는다: `run <run_id> <old> -> <new>` (+ 실패면 exit code).
- 그룹이 종료 상태에 도달하면 종료 줄을 찍고 빠져나온다: `group.completed group=p1 done=3 failed=0` 또는 `group.partial …`.
- `--follow-timeout <sec>`으로 대기를 죽이지 않고 끊을 수 있다.
- **종료 줄을 반드시 찍는다** — 그래야 조용한 그룹과 죽은 그룹이 구분된다. `log --follow`가 같은 이유로 그렇게 되어 있다.
- 백그라운드 Bash로 띄우고 **Monitor 도구와 페어링**하는 것이 의도된 사용법이다. Bash 도구의 600초 상한을 블로킹으로 넘길 수 없기 때문이다.

### 3.4 `result --group <name>`

```json
{"group": "p1",
 "results": [{"run_id": "…", "label": "…", "state": "completed", "exit_code": 0,
              "message": "<상한 걸린 앞부분>", "message_bytes": 4120, "message_truncated": true,
              "usage": {...}, "json": {...}, "turn_failed": null,
              "files_changed": 12,
              "worktree": "…", "diff": {"files": 12, "insertions": 340, "deletions": 51}}],
 "overlaps": {"src/pricing.py": ["…-moduleA-1a2b", "…-moduleC-9f8e"]},
 "totals": {"input_tokens": 51234, "output_tokens": 3901}}
```

- **런당 상한(D07).** 전문은 `result --run <id>`로 하나씩. 상한은 `show --item`의 truncation 표기와 같은 방식으로 `message_bytes` / `message_truncated`를 명시한다. 가져올지가 추측이 아닌 결정이 되게 한다.
- **`overlaps`만, 전체 경로 목록은 없음(D30).** `file_change` 이벤트에서 런별 경로 집합을 만들되 **교집합만 반환한다.** 보통 비어 있고, 비어 있지 않으면 그게 합성 단계에서 Claude가 가장 먼저 알아야 할 것이다. 런별 전체 경로 목록은 내보내지 않는다 — 감사가 그걸 컨텍스트 규율의 역전이라고 기각했다.
- `diff`는 worktree가 있을 때만. `git diff --shortstat` 수준의 요약이며 diff 본문은 주지 않는다(D06).
- `turn_failed`(F8)를 여기와 `status`에 노출한다.

### 3.5 `stop` (D25)

```
stop --run <id> [--run <id>]…   |   --group <name>   |   --all   [--grace <sec>]
```

`--all-mine`은 제거된다. `--all`은 프로젝트 레지스트리의 모든 비종료 런이다. 범위가 눈에 보이는 것으로만 정해지므로 서브에이전트 세션 경계라는 보이지 않는 것에 의존하지 않는다.

**구현 주의:** 감사가 `stop --label`을 B8("이름 매칭 금지") 근거로 기각했는데, `--group`은 그 기각에 해당하지 않는다. 라벨 문자열 매칭이 아니라 meta에 기록된 명시적 그룹 id를 레지스트리에서 run id로 해석한 뒤 각 런의 **pgid에 시그널**하는 것이다. B8이 금지한 것은 프로세스 *이름* 매칭이다. 이 구분을 코드 주석에 남겨라.

직렬 승격 비용은 감사에서 문제 없음으로 확인되었다(정상 자식 4개에 1초 미만). 병렬화하지 마라.

### 3.6 `batch clean --group <name> [--force]`

worktree를 제거한다. 다음 중 하나라도 해당하면 `--force` 없이 거부한다.

- 그룹에 비종료 런이 있다.
- 어떤 worktree에 커밋되지 않은 변경이 있다 (즉 아직 아무도 결과를 수거하지 않았다).

`git worktree remove`가 더러운 worktree를 거부하는 것을 그대로 활용한다 — 별도 검사를 짜기 전에 git이 이미 하는 일을 확인하라.

### 3.7 `--timeout`의 백그라운드 동작 (D26)

수퍼바이저가 이미 자식을 기다리고 있다. 데드라인을 추가한다.

- `started_at + timeout`에 자식이 살아있으면 **자기 프로세스 그룹에 SIGINT**를 보낸다. V-08이 SIGINT 후 스레드가 깨끗하게 resume 가능함을 증명했다 — 그래서 포기가 값싸다.
- 이후는 기존 유예 사다리(SIGTERM → SIGKILL)를 재사용한다.
- **새 종단 상태 `timed_out`을 만든다.** `interrupted`(사용자가 stop)와 `failed`(Codex가 실패)와 구분되어야 한다. `timeout_seconds`를 meta에 기록한다.
- 기본값은 없다. `--timeout`을 주지 않으면 데드라인도 없다.

---

## 4. worktree 설계

### 4.1 발동 조건 (D18)

배치에 **`workspace-write`(또는 `danger-full-access`) 런이 2개 이상**일 때 자동으로 켜진다. `--worktree`로 강제, `--no-worktree`로 끈다.

**read-only 배치는 worktree를 받지 않는다.** 의도적이다 — 검토 배치는 사용자의 미커밋 변경을 그대로 봐야 한다. worktree를 붙이면 사용자가 검토받고 싶었던 바로 그 변경을 못 본다. 이 이유를 코드와 문서 양쪽에 남겨라.

단일 `workspace-write` 런에도 worktree를 붙이지 않는다. 격리할 상대가 없다.

### 4.2 배치

- 위치: `<project>/.codex-runs/<run_id>/wt`
- `.codex-runs/.gitignore`가 `*`이므로 본 트리의 `git status`가 오염되지 않는다 — **V-13에서 실측 확인할 것.**
- **detached HEAD**로 만든다(`git worktree add --detach <path> <base>`). 브랜치를 만들지 않는 이유: 브랜치 이름 충돌이 없고, Codex는 `workspace-write`에서 보통 커밋하지 않고 파일만 고치므로 결과는 worktree의 미커밋 변경으로 남으며, 그 상태가 `git worktree remove`를 자동으로 거부하게 해 D06의 보호가 공짜로 생긴다.
- `--base <ref>`가 없으면 현재 `HEAD`.

### 4.3 더러운 트리 (D17)

**거부하지 않는다. 상태를 찍는다.** `batch start` 출력의 `worktree.uncommitted_files`와 `note`가 그것이다. 동시에 프리앰블(§4.4)이 Codex 자신에게도 같은 사실을 알린다.

### 4.4 프리앰블 추가 (D20)

배치 런에만, **사실만** 붙인다. B19의 "사실만, 방법론 금지" 경계 안이다.

```
You are one of <N> Codex runs started together as group "<name>"; the others are running in
parallel and may be editing other paths.
Your working tree is an isolated git worktree at <path>, created from <sha>. It does not
contain <M> uncommitted files that exist in the caller's working tree.
```

두 번째 문단은 worktree가 있을 때만. `--no-preamble`은 배치 문단도 함께 끈다.

이것이 사실인 이유를 판단해 보라: Codex가 이걸 모르면 잘못된 전제로 움직인다 — 자기가 보는 저장소 상태가 사용자가 보는 것과 같다고 가정하고, 다른 런이 만든 파일이 없다고 놀라고, 자기 변경이 즉시 본 트리에 반영된다고 생각한다. 방법론(어떻게 협조하라)은 넣지 않는다.

### 4.5 정리 (D06)

`batch clean --group`이 유일한 정리 수단이다. 자동 정리는 없다. 훅도 없다(D23).

---

## 5. 레지스트리 강화 (M1 — 배치 이전, D28)

`audit-findings.md` F1·F2·F15의 수정. **배치 코드를 한 줄도 쓰기 전에 끝낸다.** 이 층이 흔들리면 그 위 배치 버그가 전부 간헐적이 되어 재현 불가가 된다.

1. **고유 tmp 파일명.** `write_meta`의 `.meta.json.tmp`를 `f".meta.json.{os.getpid()}.{uuid4().hex[:8]}.tmp"`로. 이것만으로 `FileNotFoundError` 크래시와 내용 섞임이 사라진다(`os.replace`는 이미 원자적이다).
2. **read-modify-write 직렬화.** `update_meta`의 몸통 전체(읽기 + 병합 + 쓰기)를 `run_dir/.meta.lock`에 대한 `fcntl.flock(LOCK_EX)`으로 감싼다.
3. **compare-and-set.** `update_meta_if(run_dir, expected_states, **fields)`를 추가하고 `reap()`이 이것을 쓰게 한다. `pid_alive`가 False를 반환한 뒤 락 안에서 다시 읽고, 상태가 이미 종단이면 그대로 반환한다. `ended_at`/`supervisor_pid`도 새로 읽은 meta에서 가져온다.
4. **run id 충돌 재시도.** `new_run_id()` + `run_dir.mkdir()`를 최대 5회 루프로 감싸고 `FileExistsError`를 잡는다(`mkdir`이 원자적 선점이다). 소진 시 `fail(...)`. docstring의 "collision-free"를 "collision-resistant; 호출자가 드문 충돌에 재시도한다"로 낮춘다.

**M1의 완료 기준은 테스트다.** 프로세스 2개 이상이 한 run_dir에 동시에 쓰는 재현 테스트를 먼저 쓰고, 수정 전에 실패하는 것을 확인한 뒤 수정한다. 감사가 240회 중 120회 실패를 재현했으므로 통계적으로 충분히 자주 깨진다.

---

## 6. 제거되는 것 (D23·D24·D25)

훅 제거는 **삭제 목록이 길다.** 하나라도 남으면 `validate_harness.py`가 잡거나(경로 불일치) 사용자가 나중에 발견한다.

- `hooks/codex_session_cleanup.py` — 삭제
- `hooks/hooks.json` — 삭제 (`hooks/` 디렉터리째)
- `tests/test_hook_cleanup.py` — 삭제 (16개 테스트)
- `docs/wiki/Session-Cleanup-Hook.md` — 삭제, `docs/wiki/README.md`의 목차에서도 제거
- `SKILL.md`의 "Background runs are stopped when the Claude session ends…" 문단 — 삭제
- `references/environment.md` / `troubleshooting.md`의 훅·`--detach` 언급 — 삭제
- `--detach` 플래그, meta의 `detached` 필드, `doctor`의 `detached_running` — 삭제
- `stop --all-mine` — 삭제 (`--run` 반복 / `--group` / `--all`로 대체)
- `README.md`·`CHANGELOG.md`의 훅 서술 — 릴리즈 때 정리 (§11)
- `.claude/harness-spec.md`의 **B17 행 삭제**, 관련 설계 근거 문단 삭제

**남기는 것:** meta의 `claude_session_id` 기록. 무료이고 여러 세션이 한 저장소를 쓸 때 디버깅에 쓸모가 있다. 다만 **어떤 명령도 이것으로 대상을 고르지 않는다** — 감사 F5가 서브에이전트에서 이 값이 신뢰 불가함을 재현했다.

`plugin.json`이 `"hooks"`를 선언하지 않는지 확인하라. R7이 그것 때문에 플러그인 전체가 로드 실패한 사건이다. 지금은 선언하지 않고 있고, 훅 디렉터리가 사라지면 더더욱 선언하면 안 된다.

---

## 7. 단일 런 결함 수정 (M3)

`audit-findings.md`의 나머지 확정 소견. 배치와 독립적으로 고칠 수 있다.

| 소견 | 수정 | 완료 기준 |
|---|---|---|
| F3 status 절단 | 자르기 전 요약 계산, `total_runs`/`runs_truncated` 추가 | 런 25개 중 가장 오래된 3개가 살아있을 때 `--all` 없이도 `running`에 나타나는 회귀 테스트 |
| F4 암묵적 대상 (D27) | 비종료 런이 정확히 1개면 유지, 0개면 최신 런 + 어떤 걸 골랐는지 반향, 2개 이상이면 후보 목록과 함께 실패. 살아있는 스레드에 두 번째 턴은 `--force` 필요 | 각 분기의 테스트 3개 + 동시 두 턴 거부 테스트 |
| F6 설정 드리프트 | `priority = args.priority if args.priority is not None else (base.get("priority") if base else isolated)`. `extra_config`도 `base`에서 상속 | `test_resume_reasserts_every_setting_not_only_sandbox`를 `--no-priority --config k=v`로 시작하도록 강화 |
| F8 `turn_failed` | `run_row`와 `cmd_result`에 노출 | `tests/fixtures/turn-failed.jsonl` 추가, `status`와 `result` 양쪽에서 오류 메시지 확인 |
| F9 JSON 계약 | `read_prompt`를 `except OSError → fail(...)`로 감싸고, `read_events`에서 `since = max(0, since)`, `main()`에 `except Exception → fail("internal error: …")` catch-all | `start --prompt-file <없는파일>`과 `log --since -1`이 한 줄 JSON을 내는 negative 테스트 2개 |
| F10 `query_threads` | cwd 필터를 SQL로 내리되 **NFC와 NFD 두 형태 모두** 바인딩, `limit`도 직접 바인딩. `id` 컬럼이 없으면 `return []` | `threads` 테이블을 채운 sqlite fixture. 한국어 NFD cwd 케이스 포함 |
| F11 커서 트레일러 | `# cursor=<n> run=<id>`. `--since`가 파일 크기 초과 시 `fail(...)` | 트레일러 형식 테스트 + 범위 초과 거부 테스트 |
| F15 run id 충돌 | §5의 4번 | `new_run_id`를 고정값으로 몽키패치해 충돌을 강제하는 테스트 |
| F16 시그널 사다리 | 가짜 shim에 `FAKE_CODEX_IGNORE_SIGINT=1` 추가 | `signals_sent == ["SIGINT","SIGTERM"]` **정확 일치** 단언, pid가 실제로 사라짐 확인. 기존 SIGINT 테스트도 `assertIn`을 `assertEqual`로 |

**`main()`의 catch-all 주의:** `SystemExit`은 `Exception`의 하위가 아니므로 `argparse`의 정상 종료를 삼키지 않는다. 이건 감사가 확인한 사실이다.

---

## 8. 문서 (M5)

### 8.1 SKILL.md 수정

| 항목 | 수정 |
|---|---|
| F7 병렬 절 | 공유 워크트리 위험을 gotcha로 승격. 프로세스 그룹 주장의 범위를 **시그널로 한정.** `status`의 `running`/`threads`와 20행 상한 문서화 |
| F12 재주입 gotcha | `SKILL.md:81`의 "every invocation"에 조건절 추가 — *레지스트리에 항목이 있는 호출에 한해서.* TUI 스레드를 이름으로 처음 resume할 때는 `--sandbox`를 명시하라 |
| F13 `--no-preamble` | 프리앰블이 무엇인지 한 문장으로 정의. 특히 `result`가 의존하는 "답을 최종 메시지에 넣어라" 절. `argparse`에도 `help=` 추가 |
| F14 경로 복구 | `SKILL.md:30`의 순환 제거 — 먼저 파일을 찾고(`Base directory for this skill:` 줄), 그 다음에 `doctor`로 나머지 환경을 확인하라 |
| 훅 (D23) | 세션 종료·`--detach` 문단 삭제 |
| 명령표 | `batch start` / `batch clean` 행 추가, `--group` 셀렉터 표기, `stop` 옵션 갱신 |
| 판단기준 (D12) | **몇 줄만.** "언제 그룹이 값어치를 하는가" — 이유와 함께. `orchestration.md` 포인터 |

**description(frontmatter)은 건드리지 마라.** 감사가 헤드리스 e2e로 검증된 것을 확인했고, 병렬 관련 단어를 넣으라는 소견은 기각되었다. 배치 기능이 붙었다고 트리거를 손대면 검증된 경계가 무효가 된다. *만약* T4에서 "코덱스 여러 개로 병렬 검토" 같은 프롬프트가 발화하지 않으면 그때 최소한으로 고치고 재검증하라.

`allowed-tools`도 건드리지 마라. 가산으로 실측되었다.

### 8.2 `references/orchestration.md` 신규 (D12·D31)

**메커니즘 + 가처만. 예제 페이즈 구성 없음.**

담을 것:
- 배치 명령의 실제 동작 — 그룹 id의 수명, `--task`와 `--tasks-file`의 관계, `kind`, `--resume-from`의 1:1 짝짓기 규칙과 개수 불일치 시 실패
- `status --group --follow`를 Monitor와 페어링하는 법과 그 이유(Bash 600초 상한)
- worktree 가처: 발동 조건, detached HEAD, 미커밋 변경 미포함, `batch clean`이 더러운 worktree를 거부하는 것, **read-only 배치는 worktree를 안 받는다는 것과 그 이유**
- 스레드 직렬성: 한 스레드에 동시 두 턴은 거부된다는 것과 왜
- 비용이 어떻게 곱해지는가 — 격리 바닥은 호출당 지불되므로 N개 병렬은 N개 바닥을 문다. 한 스레드의 N턴은 바닥 하나 + 커지는 리플레이. **T3의 실측을 인용하고, 그 숫자로 예산을 짜지 말라고 말한다** (`environment.md`가 격리 비율에 대해 하는 것과 같은 방식)
- `overlaps`가 무엇을 의미하고 무엇을 의미하지 않는가 (worktree 격리 하에서는 손상이 아니라 병합 충돌 예고)
- dynamic-workflow 경로 한 절(§1) — 워크플로 `agent()`가 배치 명령을 실행하게 하는 법. 스킬 로드가 불필요하다는 실측 사실 포함

담지 않을 것: 어떤 작업을 병렬화해야 하는지, 몇 개로 쪼개야 하는지, fan-out/verify/synthesize 같은 페이즈 패턴 카탈로그. 그건 Claude가 매번 정한다(D02).

### 8.3 `references/troubleshooting.md` 수정

F14: 경로 해석 두 행이 가리키는 "SKILL.md의 스니펫"이 존재하지 않고, 그 스니펫의 `$VAR` 폴백은 `harness-spec.md:171`이 틀렸다고 기록한 것이다. 두 행 모두 `Base directory for this skill:` 줄을 가리키도록 다시 쓴다. 훅 관련 행도 삭제한다.

배치 증상 행 추가: 그룹이 `partial`로 끝남, `batch clean`이 거부함, worktree가 예상과 다른 코드를 보임, `--resume-from` 개수 불일치.

### 8.4 `.claude/harness-spec.md`

- **B17 삭제** (SessionEnd 훅). Design rationale의 관련 문단도.
- B7(status)·B8(stop)·B15(레지스트리) 행의 component/evidence 갱신.
- 신규 행 추가:

| id | 동작 | 층 | 컴포넌트 |
|---|---|---|---|
| B22 | 한 명령으로 N개 런을 그룹으로 시작하고 각 핸들을 즉시 받는다 | skill+script | `batch start` |
| B23 | 그룹 상태를 한 번에 조회하고, `--follow`로 그룹 종료를 알림으로 받는다 | skill+script | `status --group [--follow]` |
| B24 | 쓰기 병렬 시 각 런이 자기 git worktree에서 동작한다 | script | worktree 할당 |
| B25 | 그룹 결과를 상한 걸린 형태로 수거하고 런 간 파일 겹침을 보고한다 | skill+script | `result --group`, `overlaps` |
| B26 | 페이즈 간 1:1 스레드 이어받기 | skill+script | `batch start --resume-from` |
| B27 | 그룹 단위 중단 및 worktree 정리 | skill+script | `stop --group`, `batch clean` |
| B28 | 배치 런에 병렬 상황 사실을 프리앰블로 전달한다 | script | 배치 프리앰블 |
| B29 | 백그라운드 런에 호출자가 정한 시간 상한 | script | `--timeout`, `timed_out` 상태 |

- Change history에 2026-08-01 항목 추가. 결정 D01~D33과 감사 결과(45개 중 21개 확정)를 요약하고 이 계획서를 가리킨다.

---

## 9. 검증 항목 — 구현 *전에* 실측할 것

v0.1.0의 V-01~V-10과 같은 성격이다. 각 항목에 확인 방법과 실패 시 대안을 적었다. **V-11과 V-13이 blocker다** — 아니면 배치 설계 자체가 성립하지 않는다.

| ID | 질문 | 확인 방법 | 실패 시 |
|---|---|---|---|
| **V-11** | **여러 `codex exec`가 동시에 돌 때 `CODEX_HOME`의 sqlite 스레드 DB(`state_5.sqlite`)에 락 경합이 있는가?** | 5개를 동시에 띄우고 각각의 rollout·thread_id가 온전한지, `sqlite3` "database is locked" 오류가 이벤트 스트림에 뜨는지 확인 | 경합이 있으면 `--max-concurrent`의 기본값을 측정된 안전선으로 두거나, 시작을 짧게 stagger한다. D10(상한 없음)은 유지하되 기본 stagger는 정책이 아니라 정확성 수단이다 |
| **V-12** | N개 동시 실행에서 OpenAI 레이트리밋이나 성능 저하가 언제 시작되는가? | 2·4·8개로 같은 사소한 프롬프트를 돌리고 벽시계 시간과 오류 이벤트를 기록 | 숫자를 `orchestration.md`에 측정치로 기록. 상한은 여전히 두지 않는다(D10) |
| **V-13** | **`git worktree add --detach <project>/.codex-runs/<run_id>/wt <sha>`가 동작하고, 본 트리의 `git status`가 깨끗하게 유지되는가?** | 실제로 만들고 `git status --porcelain`이 비었는지 확인. `git worktree list`에도 나오는지 | 나오면 `.codex-runs` 바깥(예: `<project>/../.codex-worktrees/<project-name>/`)으로 옮기고 그 대가(프로젝트 밖 오염)를 문서화 |
| V-14 | worktree 안에서 Codex가 정상 동작하는가? 특히 `AGENTS.md`가 worktree에도 존재해 주입되는가? | worktree에서 `codex exec`를 돌리고 V-06의 코드워드 프로브를 재사용 | 주입되지 않으면 프리앰블에 프로젝트 지침을 실어야 하는지 재검토 |
| V-15 | worktree 안에서 `codex exec review --uncommitted`가 의미 있는가? | detached HEAD worktree는 미커밋 변경이 없으므로 빈 diff일 것 — 확인 | `review` kind는 worktree를 받지 않도록 강제하고 그 이유를 문서화 |
| V-16 | `--timeout` 만료 시 SIGINT 후 스레드가 resume 가능한가? | V-08의 절차를 타임아웃 경로로 재현 | resume 불가면 `timed_out`을 실패로 취급하고 문서에 명시 |
| V-17 | `status --group --follow`를 백그라운드 Bash + Monitor와 페어링하면 실제로 알림이 오는가? | `log --follow`가 이미 이 패턴을 쓰므로 그것과 동일하게 동작하는지 확인 | 안 되면 `--follow`의 출력 형식을 `log --follow`와 정확히 일치시킨다 |
| V-18 | 배치 프리앰블이 Codex 행동을 실제로 바꾸는가? | worktree 배치를 띄우고 "네 작업트리가 어디이고 사용자 트리와 무엇이 다른가"를 물어 답을 확인 | 무시되면 문구를 줄이거나 없앤다. 읽히지 않는 토큰은 비용일 뿐이다 |

**측정 결과는 전부 `.claude/harness-spec.md`에 기록한다.** v0.1.0의 V-01~V-10 표와 같은 형식으로, 같은 파일에 이어서.

---

## 10. 테스트 계획 (D14 — 네 계층 전부)

### 10.1 T1 — 가짜 `codex` shim 기반 단위 테스트 (무료, 결정적)

기존 124개를 유지하며(훅 16개는 삭제되므로 108개에서 출발) 다음을 추가한다.

**레지스트리 동시성 (M1):**
- 두 프로세스가 한 run_dir에 동시 쓰기 → 예외 0회, 읽기 실패 0회
- `reap` 경쟁: 스냅샷을 잡은 뒤 meta.json에 `completed`를 쓰고 `reap` 호출 → 상태가 보존되는지
- run id 충돌 강제 → 재시도 성공, 소진 시 한 줄 JSON 실패

**배치:**
- `batch start`의 argv 조합 — `--task` 반복, `--tasks-file` 파싱, 항목별 오버라이드 우선순위, `kind` 세 종류
- `--resume-from` 1:1 짝짓기, 개수 불일치 시 실패, 앞 그룹에 살아있는 턴이 있을 때 거부
- worktree 발동 조건 — write 2개 이상만, read-only 배치는 미발동, `--no-worktree`
- `status --group`이 그룹 밖 런을 세지 않는지
- `status`가 25개 중 오래된 살아있는 3개를 `--all` 없이도 `running`에 넣는지 (F3 회귀)
- `result --group`의 `overlaps` 계산 — 겹침 있음/없음 양쪽
- `stop --group`이 그룹 밖 런을 건드리지 않는지 (기존 `StopIsolation`의 그룹 버전)
- `batch clean`이 비종료 멤버·더러운 worktree를 거부하는지

**단일 런 수정 (§7):** 표의 "완료 기준" 열이 그대로 테스트 목록이다.

**shim 확장:** `FAKE_CODEX_IGNORE_SIGINT=1`(F16), `turn.failed`로 끝나는 스트림 fixture(F8), `threads` 테이블이 채워진 sqlite fixture(F10, 한국어 NFD cwd 포함).

### 10.2 T2 — 실제 Codex 통합 (env-gated, Codex 토큰 소모)

기존 I1~I8을 유지하고 추가한다. **병렬이라 지난번보다 몇 배 비싸다는 것을 알고 시작하라.**

| ID | 내용 |
|---|---|
| I9 | 3개짜리 배치가 서로 다른 thread_id와 서로 다른 pgid를 받고 전부 완료 |
| I10 | worktree 배치 — 3개가 각자 worktree에서 같은 이름의 파일을 만들고, 본 트리가 오염되지 않고, `overlaps`가 겹치는 경로를 잡아냄 |
| I11 | `--resume-from`으로 2페이즈 — 각 런이 **자기** 스레드를 이어받았는지 rollout의 thread_id로 확인 |
| I12 | 한 멤버를 일부러 실패시켜 그룹이 `partial`로 끝나고 나머지는 완료 |
| I13 | `status --group --follow`가 종료 줄을 내고 빠져나옴. 그룹이 실패해도 종료 줄이 나옴 |
| I14 | `--timeout` 백그라운드 만료 → `timed_out` 상태, 이후 resume 성공 (V-16의 통합 버전) |
| I15 | `batch clean`이 더러운 worktree를 거부하고 `--force`로 지움. 본 저장소의 `git worktree list`가 깨끗해짐 |

### 10.3 T3 — 배치 비용 측정 (D10의 근거)

**이 측정 없이는 `projected_cost`가 이유 없는 숫자다.**

같은 사소한 프롬프트를 1·2·4·8개 동시로 돌리고 기록한다:
- 런당 입력 토큰(격리 바닥이 병렬에서도 안정적인가)
- 벽시계 시간(선형인가, 어디서 꺾이는가)
- 오류 이벤트(레이트리밋, sqlite 락 — V-11·V-12와 같은 실험)

출력은 `docs/measurements/batch-cost.md`. 요약을 `references/orchestration.md`에 싣고, **그 숫자로 예산을 짜지 말라는 문장을 함께 싣는다** — R8이 격리 비율에 대해 가르쳐준 교훈이다(설계 시점 2.92배가 2주 뒤 1.09배가 되었다).

### 10.4 T4 — 헤드리스 e2e

`e2e-testing.md`에 따라 그 자리에서 구성한다. 고정 워크플로 파일을 만들지 않는다.

최소 시나리오:
- **E6** — *"이 세 모듈을 코덱스 세 개로 나눠서 동시에 감사해줘"* → 스킬 발화, `batch start`, 그룹 폴링, 결과 수거
- **E7** — *"아까 그 셋한테 각자 찾은 거 고치라고 해줘"* → `--resume-from`으로 이어받고 worktree가 붙는지
- **E8** — **near-miss.** 병렬을 언급하지만 Codex를 언급하지 않는 프롬프트(예: *"이 세 파일 동시에 리뷰해줘"*) → **발화하면 안 된다.** E3와 같은 성격이며, 증거는 부재(`Skill invocations: 0`)다
- **E9** — 배치 중 하나가 실패하는 상황에서 Claude가 `partial`을 알아채고 보고하는가

**표면적 순응은 FAIL이다.** 명령을 옳게 쳤다는 것만으로는 통과가 아니다. 인용 가능한 증거로 채점한다.

### 10.5 구조 검증

- `python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path . ` → 오류 0
- `test_hook.py`는 **더 이상 해당 없음**(훅 제거). 관련 문서에서도 이 요구를 지운다

---

## 11. 마일스톤

각 마일스톤은 독립 커밋이다. 회귀 추적을 위해 섞지 마라.

| M | 내용 | 완료 기준 |
|---|---|---|
| **M0** | 준비 — `feat/batch-orchestration` 브랜치. `.gitignore`에 `__pycache__/` 추가 + `git rm -r --cached` (D32). 미커밋 문서 산출물(`CONTRIBUTING.md`·`SECURITY.md`·`CODE_OF_CONDUCT.md`·`docs/wiki/`·수정된 `README.md`) 커밋. **기준선 테스트 전체 통과 확인** | `git status --porcelain`이 비어 있고 기존 테스트 통과 |
| **M0.5** | 검증 항목 V-11~V-18 실측. 결과를 `harness-spec.md`에 기록 | V-11·V-13이 통과했거나 대안이 결정됨 |
| **M1** | 레지스트리 동시성 강화 (§5) | 재현 테스트가 수정 전 실패·수정 후 통과 |
| **M2** | 훅 제거 + `--detach` 제거 + `stop` 표면 교체 (§6) | 삭제 목록 전부 소진, `validate_harness.py` 0 오류 |
| **M3** | 단일 런 결함 수정 (§7) | 표의 완료 기준 전부 |
| **M4** | 배치 원시기능 (§3·§4) | T1 배치 테스트 전부 통과 |
| **M5** | 문서 (§8) — SKILL.md 수정, `orchestration.md` 신규, `troubleshooting.md` 수정, `harness-spec.md` 갱신 | `validate_harness.py` 0 오류, 스킬 description 미변경 확인 |
| **M6** | 검증 — T1 전체, T2 I1~I15, T3 측정, T4 E1~E9 | 전부 통과. 실패는 기록하고 고친 뒤 재실행 |
| **M7** | 릴리즈 v0.2.0 (§12) | 태그와 GitHub 릴리즈 발행 |

**M0.5를 건너뛰지 마라.** v0.1.0에서 V-01이 "아니오"로 나와 계획 §4를 통째로 무효화했다. 같은 일이 V-11이나 V-13에서 일어날 수 있다.

---

## 12. 릴리즈 v0.2.0 (D15)

**semver 판단: minor.** 신기능이 주이지만 **`--detach`와 `stop --all-mine` 제거는 파괴적 변경**이다. 0.x이므로 minor로 처리하되, CHANGELOG의 `### Removed` 절에 명시적으로 적고 마이그레이션 한 줄을 붙인다.

- `.claude-plugin/plugin.json`의 `version`을 `0.2.0`으로. `description`에 배치 역량을 한 구절 추가
- `CHANGELOG.md` — `### Added`(배치·worktree·`--resume-from`·`overlaps`·`timed_out`), `### Changed`(status 절단 수정, resume 설정 상속, 암묵적 대상 거부, `--timeout` 백그라운드 동작), `### Removed`(SessionEnd 훅, `--detach`, `stop --all-mine`), `### Fixed`(레지스트리 동시성, `reap` 덮어쓰기, JSON 계약, `query_threads`, run id 충돌)
- `README.md`(한국어) — 배치 절 추가, 훅 절 삭제
- `docs/wiki/` — `Session-Cleanup-Hook.md` 삭제, `Orchestration.md` 신규, `CLI-Reference.md`·`Architecture.md`·`Concepts.md`·`Testing.md`·`Troubleshooting.md` 갱신, `README.md` 목차 갱신
- `docs/measurements/batch-cost.md` 신규 (T3)
- 어노테이트 태그 `v0.2.0`, GitHub 릴리즈
- **`repo-wiki` 스킬을 쓰면 이 일들이 한 흐름으로 처리된다** — 릴리즈 트랙이 단독으로 돈다

---

## 13. 상시 리스크

- **Codex CLI 버전 드리프트.** 모든 실측은 `codex-cli 0.144.1` 기준이다. `doctor`가 버전을 찍으니 다른 버전에서 이상하면 먼저 그것을 의심하라.
- **동시 실행이 새 실패 모드를 만든다.** V-11이 통과하더라도 8개·16개에서 다를 수 있다. `orchestration.md`에 "N이 커지면 네가 측정하라"는 문장을 남겨라.
- **worktree가 디스크를 먹는다.** 자동 정리가 없으므로(D06) `.codex-runs`가 커진다. `doctor`가 `.codex-runs`의 크기와 남아있는 worktree 개수를 보고하게 하는 것을 고려하라 — 정책 없이 사실만.
- **훅 제거로 런이 세션보다 오래 산다.** 이것은 의도된 것이지만(D23), `doctor`가 비종료 런을 눈에 띄게 보고하는 것은 여전히 가치 있다. 죽이지는 않는다.
- **`orchestration.md`가 레일로 미끄러지기 쉽다.** 이 문서를 쓸 때 "예를 들어 이렇게 3단계로 나누면"이라고 쓰고 있는 자신을 발견하면 멈춰라. D31이 그것을 금지한다.
- **T2·T3가 지난번보다 몇 배 비싸다.** 병렬이라 그렇다. 예산을 확인하고 시작하라.
