# Fast 모드를 그 이름으로 찾을 수 있게 하고, status가 티어를 말하게 한다

## Context

성진이 "코덱스에 fast 모드가 있는 거 아니? 우리 CLI엔 통합 안 돼 있지?"라고 물었고, 두 번째 질문의 전제가 틀렸다. Fast 모드는 이미 `--priority` / `--no-priority`로 완전히 통합돼 있고, 격리(`--ignore-user-config`) 때문에 사라질 사용자 설정을 되살리려고 기본값까지 격리 상태를 따라간다(`_run.py:334-344`). 동작에는 결함이 없다 — V-02가 "bogus 티어는 error 이벤트를 내고 `priority`는 안 낸다"로 실제 파싱됨을 증명했고, `test_priority_can_be_forced_off_and_on`이 argv 조합을 고정한다.

문제는 **이름**이다. OpenAI가 사용자에게 보여주는 이름은 전부 "Fast"인데(`/fast` TUI 명령, `service_tier = "fast"` config 키, 카탈로그의 `name: "Fast"`, 키바인딩 "Turn Fast mode on or off"), 우리는 어디서도 그 단어를 쓰지 않는다. `--help`, `README.md`, `CLI-Reference.md` 어디를 grep해도 "fast"가 안 나온다. 그래서 이 기능을 아는 사람이 이 기능을 못 찾는다 — 성진이 물어본 게 그 증거다.

조사 중에 별개의 갭이 하나 더 나왔다. `run_row()`(`_run.py:625-645`)는 `sandbox`·`model`·`effort`·`isolated`를 보고하는데 `priority`만 빠져 있다. 런은 1.5배 속도 티어 값을 치르고 있는데 `status`도 `result`도 그 사실을 말하지 않는다. 비용을 만드는 설정이 보고되지 않는 건, 이 레포가 레지스트리를 두는 이유("설정이 어디에 존재하는가")와 정면으로 어긋난다.

**의도한 결과:** 새 플래그 없이(41개 유지) "fast"로 검색하면 `--help`에서 잡히고, `status`가 티어를 말한다.

## 측정 근거 — help에 넣을 문장의 출처

새 `help=` 문장은 검증 안 된 새 주장이고, R54가 기록한 실패 모드가 정확히 그것이다(틀린 help는 확신에 차서, 리뷰 없이 나간다). 그래서 넣을 주장은 아래 세 개만이고 전부 이 세션에서 `codex-cli 0.147.0`에 대해 측정했다.

| 주장 | 근거 (재현 가능) |
|---|---|
| Fast 모드는 `service_tier` 설정이다 | `codex features list` → `fast_mode  stable  true`; 바이너리 문자열에 `/fast`, `toggle_fast_mode`, "Turn Fast mode on or off" |
| 카탈로그가 광고하는 티어 id는 `priority`이고 이름이 "Fast"다 | `codex debug models` → `gpt-5.6-sol`의 `service_tiers: [{"id": "priority", "name": "Fast", "description": "1.5x speed, increased usage"}]`, `additional_speed_tiers: ["fast"]` |
| `config.toml`의 `"fast"`는 와이어에서 `"priority"`로 해석된다 | `~/.codex/config.toml`이 `service_tier = "fast"`인 상태로 돈 TUI 세션의 rollout 64행: `{"type":"thread_settings_applied","thread_settings":{...,"service_tier":"priority",...}}` |

주장하지 **않을** 것: `-c service_tier="fast"`가 주입 방향에서도 동작한다는 것. 측정한 건 config 파일 → 와이어 방향뿐이다. 우리가 주입하는 값은 카탈로그 id인 `"priority"` 그대로 두고, help는 "이게 Codex가 Fast 모드라고 부르는 것"이라는 **이름**만 말한다.

## 변경

### 1. `--priority` / `--no-priority`의 help에 이름을 넣는다

`.claude/skills/codex/scripts/codex_bridge.py:1037-1046`. 기존 문장은 전부 유지하고 첫 절만 확장한다 — `AStatedDefaultIsTheRealDefault`가 검사하는 "Unset, it follows isolation…" 부분은 실제 기본값(`_run.py:334-344`)과 맞으므로 손대지 않는다.

```
--priority   inject service_tier="priority" — the tier Codex surfaces as
             "Fast mode" (/fast in the TUI, service_tier = "fast" in
             config.toml, both resolving to priority). Ignoring the user's
             config would otherwise silently drop it. Unset, it follows
             isolation on a fresh thread or a flipped one, and otherwise
             carries forward what was recorded.
```

`--no-priority`에는 "Fast mode"를 한 번만 더 얹는다(`omit service_tier — no Fast mode — rather than injecting it…`). 두 곳 다 넣는 이유는 `--no-priority`만 보고 있는 사람도 같은 검색어로 도달해야 하기 때문이다.

### 2. 그 주장에 기계 검사를 붙인다

`tests/260823/test_help_owns_its_facts.py`의 `FACTS` 딕셔너리에 한 줄. 이 테스트는 파서의 `help=` 속성이 아니라 서브프로세스로 **실제 `--help` 출력**을 읽으므로, argparse 재줄바꿈 뒤에도 문장이 살아 있는지를 본다.

```python
"priority is the tier Codex calls Fast mode": (
    "start", ["Fast mode", "service_tier"]),
```

이게 없으면 이번 변경은 다음 리팩터에서 조용히 지워진다. `test_prose_does_not_restate.py`(Seam 2)는 `skill_docs`(SKILL.md + `references/`)만 보므로 아래 3·4의 문서 변경과는 충돌하지 않는다.

### 3. `run_row()`에 `priority`를 추가한다 — 테스트 먼저

`.claude/skills/codex/scripts/_run.py:634-636`, `"isolated"` 바로 옆에 `"priority": meta.get("priority"),`. `isolated`와 짝이라 붙여 두는 게 읽기 쉽다.

`_batch.py:1123`이 같은 `run_row`를 호출하므로 그룹·배치 뷰는 자동으로 따라온다. 별도 작업 없음.

`meta.get()`이라 `priority` 키가 없는 옛 `meta.json`은 `None`이 되고, `test_status_payload.py`가 심는 합성 meta(`priority` 없음)도 깨지지 않는다. 상태 row에 대한 정확 키셋 단언은 레포 어디에도 없다(확인함).

**이 한 줄에는 회귀 테스트가 붙어야 하고, 그 테스트를 어느 seam에 둘지가 이 계획의 유일한 미결 결정이다.** 없으면 다음 리팩터가 조용히 지운다 — `run_row`가 `sandbox`·`model`·`effort`·`isolated`를 보고하면서 `priority`만 빠뜨린 지금 상태가 이미 그 증거다. 그래서 이 단계는 `tdd` 스킬을 열고 시작한다. 후보와 추천:

| seam | 무엇을 고정하나 | 값 |
|---|---|---|
| `tests/260823/test_behavior_changes.py` **(추천)** | 실제 CLI를 돌려 `status --run`의 JSON이 `priority`를 말하는지 | 이번 라운드의 동작 변경이 모이는 파일이고, `ContradictoryPriorityFlagsAreRefused`가 이미 여기서 `--priority`를 다룬다. `--priority` / `--no-priority` 두 갈래를 한 테스트에서 대비시킬 수 있다 |
| `tests/legacy/test_status_payload.py` | 합성 `meta.json`을 심고 row에 키가 있는지 | 싸고 빠르지만, 합성 meta는 `create_run`이 실제로 무엇을 기록하는지를 건너뛴다 — `overlaps`를 눈멀게 했던 바로 그 모양(픽스처가 실제 이벤트에 없는 형태를 심음) |
| `tests/legacy/test_argv.py` | argv 조합 | 잘못된 자리다. argv는 이미 `test_priority_can_be_forced_off_and_on`이 고정하고 있고, 이번 갭은 argv가 아니라 **보고**다 |

추천은 첫 번째다: 고치려는 결함이 "런이 티어 값을 치르는데 아무도 말해주지 않는다"이므로, 검증도 실제 런의 보고 표면에서 이뤄져야 한다. 다만 최종 결정은 tdd 단계에서 내린다.

### 4. README와 CLI-Reference에 이름을 노출한다

- `README.md:34` 뒤에 기능 불릿 하나. 34행("every `resume` re-asserts the sandbox, model, and reasoning effort")은 지금 불완전하기도 하다 — `service_tier`도 재주입된다. 새 불릿은 resume가 아니라 **격리**에 관한 것이므로 별도 항목으로 둔다:
  > **Fast mode survives isolation** — Codex's Fast mode (`service_tier`) is a user-config setting, so running isolated would drop it. Every run re-injects it, and `--no-priority` opts out. See [CLI Reference](docs/wiki/CLI-Reference.md).
- `docs/wiki/CLI-Reference.md:26`의 표 행 Meaning에 이름만 덧붙인다: `` Force `service_tier="priority"` — Codex's "Fast mode" — re-injection on or off (default: on exactly when isolating) ``.

CLI-Reference는 `test_docs_match_the_cli.py`의 `DOCS`(SKILL.md + `references/*.md`)에 **없어서 기계 검사가 안 붙는 복사본**이다. 이번엔 단어 하나만 얹고 의미론은 확장하지 않는다 — 검사되지 않는 표면에 새 사실을 쌓지 않기 위해서다.

**SKILL.md는 건드리지 않는다.** 플래그의 기계적 사실은 `--help`가 소유하고, SKILL.md는 명시적으로 그걸 다시 쓰지 않기로 한 문서다(`SKILL.md:35`).

## 하지 않는 것

- `--fast` 플래그 추가 — 설정 키는 `service_tier` 하나, 티어도 하나뿐이라 두 번째 이름이지 두 번째 스위치가 아니다. 나란히 두면 사용자 대면 플래그가 41 → 43이 되고, `main()`의 모순 가드가 한 쌍에서 네 플래그 조합으로 늘고, 이 레포가 요구하는 "플래그마다 실제 `codex` 실행 증거"(T5)를 두 번 더 만들어야 한다.
- `--priority` → `--fast` rename — 문서화·테스트된 표면을 갈아엎는 값을, 검색어 하나가 치르기엔 비싸다.
- tasks-file의 per-member `priority` 필드(`_batch.py:253`) — 이번 요청 범위 밖.

## 검증

1. `python3 -m pytest tests/legacy tests/260813 tests/260814 tests/260823 -q` — 전체 T1/T6. 기대: 통과. 특히 `test_help_owns_its_facts.py`의 새 FACTS 항목이 초록, `AStatedDefaultIsTheRealDefault`와 `EveryFlagExplainsItself`가 유지, `test_status_payload.py`가 새 키에 안 깨짐.
2. 새 FACTS 항목이 **정말 무언가를 잡는지** 확인한다: help 문자열에서 "Fast mode"를 잠깐 지우고 `test_help_owns_its_facts.py`만 돌려 빨간불을 본 뒤 되돌린다. 초록만 보고 넘어가면 아무것도 검사하지 않는 테스트를 추가한 셈이 된다.
3. 검색성 실측 — 이 변경의 목적 그 자체:
   ```bash
   $CODEX start --help | grep -i fast
   $CODEX --help | grep -i fast   # 상위 help엔 없어도 무방
   grep -ri "fast mode" README.md docs/wiki/CLI-Reference.md
   ```
4. `status`가 티어를 말하는지 실측. 이미 완료된 런으로 충분하다(새 런 불필요):
   ```bash
   $CODEX status --run 20260825-124226-count-lines-3674 | python3 -m json.tool | grep -E '"priority"|"isolated"|"effort"'
   ```
   기대: `"priority": true`. 그 런의 `meta.json`이 `"priority": true`이고 argv에 `-c service_tier="priority"`가 들어 있다. 3번에서 정한 회귀 테스트가 `--priority` / `--no-priority` 두 갈래를 다 도는 형태라면 이 손검사는 그 테스트가 대신하므로 생략한다 — 손으로 한 번 보는 것과 테스트가 매번 보는 것 중 남길 것은 후자다.

## 코덱스에 거는 것 — 구현이 아니라 적대적 감사

이 변경의 대부분은 **새로 쓴 `help=` 문장**이고, 그게 이 레포에서 이미 한 번 터진 자리다. `harness-spec.md`의 2026-08-14 라운드: help로 옮긴 문장 네 개가 **하루 만에 틀렸고**(`--priority`는 `test_argv.py:206`이 단언하는 것의 정반대를 주장하고 있었다), 그걸 잡은 것이 코덱스의 적대적 감사였다. 기록된 교훈이 R54다 — 낡은 문서는 천천히 눈에 띄게 썩지만, **틀린 help는 확신에 차서 리뷰 없이 나간다. 문자열 개수를 세는 테스트는 문자열을 읽지 못하기 때문이다.**

그래서 구현은 위임하지 않는다(한 턴짜리 외과적 변경이라 코덱스 런의 대기만 붙는다). 대신 편집이 끝난 뒤, 커밋 전에 `codex` 스킬로 감사 한 번을 건다. 프롬프트의 요지:

> `--priority` / `--no-priority`의 새 `help=` 문장을 `_run.py:330-344`(기본값 도출), `_codex.py:303-304`(argv 주입), `tests/legacy/test_argv.py:41-55, 206-223`(단언되는 동작)과 한 줄씩 대조하라. 목표는 확인이 아니라 반박이다. 문장이 주장하지만 코드가 보장하지 않는 것, 코드가 하지만 문장이 부정하는 것을 찾아라. "Fast mode"라는 이름 주장은 별도로: 카탈로그 id는 `priority`이고 config 값은 `fast`인데, 이 둘이 같다는 주장이 어디까지 측정으로 뒷받침되는지 판정하라.

`--sandbox read-only`로 충분하다 — 읽고 판정하는 일이다.

## 실행 순서

1. `tdd` 스킬을 연다 → 3번의 seam을 정하고 빨간 테스트부터 쓴다.
2. `run_row` 한 줄 → 초록.
3. help 문자열 둘 + `FACTS` 한 줄 → 검증 2번의 red-green을 실제로 본다.
4. 문서(README, CLI-Reference).
5. `codex` 적대적 감사 → 나온 반박을 반영한다.
6. 전체 테스트 → 커밋.

## 마무리

- `.claude/harness-spec.md`의 B14 행(52-53행 근처) Evidence에 이번 라운드를 덧붙이고, 320행대 Defaults 문단이 여전히 맞는지 확인한다. 코덱스 감사에서 나온 게 있으면 그것도 같이 기록한다.
- 브랜치 `docs/fast-mode-is-priority`, 커밋 단위는 (1)status 회귀 테스트+`run_row`, (2)help+FACTS, (3)문서. PR 제목: `docs: Fast 모드를 그 이름으로 찾을 수 있게 한다`.
