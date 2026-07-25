# Codex in Claude

OpenAI Codex CLI를 Claude Code 안에서 **관리되는 서브에이전트**로 다루는 플러그인입니다.
백그라운드로 작업을 넘기고, 로그를 필요한 만큼만 들여다보고, 중간에 멈춰서 방향을 고쳐주고,
이전 Codex 스레드를 이어가고, 결과를 텍스트나 스키마 검증된 JSON으로 받아옵니다.

얇은 CLI 래퍼가 아닙니다. 외부 에이전트를 세션 컨텍스트와 파일시스템을 망가뜨리지 않으면서
쓸 수 있게 만드는 **오케스트레이션 · 안전장치 · 컨텍스트 규율** 레이어입니다.

## 왜 만들었나 — 측정된 결함 하나

`codex exec resume` 에는 `-s/--sandbox` 플래그가 **없습니다**. 그래서 재개된 턴은 샌드박스를
스레드가 아니라 *그 시점에 적용되는 설정 레이어* 에서 다시 가져옵니다. 실측 결과:

| 턴 | 명령 | `turn_context.sandbox_policy` | 결과 |
|---|---|---|---|
| 1 | `codex exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | 쓰기 거부 |
| 2 | `codex exec resume <id>` (사용자 설정 상속, 플래그 없음) | **`danger-full-access`** | **파일을 씀** |

반대 방향으로도 틀립니다. `workspace-write` 로 만든 스레드를 격리 모드에서 플래그 없이
재개하면 조용히 `read-only` 로 **내려가고** reasoning effort 도 함께 사라집니다.

이 플러그인은 실행 시점의 샌드박스·모델·effort·격리 여부·작업 디렉터리를 레지스트리에 기록해
두고 **매 호출마다** 다시 주입합니다. 런 레지스트리가 편의 기능이 아니라 필수인 이유가
이것입니다. 사는 것은 "권한 상승 방지" 가 아니라 **턴 사이의 설정 안정성** 이고, 상승 방지는
그 결과 중 하나일 뿐입니다.

## 설치

### 플러그인 (권장)

```bash
claude plugin marketplace add tjdwls101010/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

로컬 디렉터리에서 바로 설치하려면:

```bash
claude plugin marketplace add /path/to/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

설치 후 `claude plugin list` 에 `Status: ✔ enabled` 로 보이면 됩니다.
스킬은 `/codex:codex` 로 호출되고, 자연어로도 자동 트리거됩니다.

### 심볼릭 링크 (개발용)

```bash
ln -s /path/to/Codex-in-Claude/.claude/skills/codex ~/.claude/skills/codex
```

이 방식은 플러그인의 `allowed-tools` 가 적용되지 않으므로 폴링할 때마다 승인 프롬프트가
뜹니다. `~/.claude/settings.json` 에 아래를 넣어 같은 효과를 얻으세요:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 \"$HOME/.claude/skills/codex/scripts/codex_bridge.py\" *)"
    ]
  }
}
```

> 프로젝트 `.claude/settings.json` 의 **allow** 규칙은 워크스페이스 신뢰(trust)를 수락한
> 뒤에만 적용됩니다. deny/ask 는 즉시 적용됩니다.

### 요구사항

- [Codex CLI](https://developers.openai.com/codex/cli) — `0.144.1` 에서 검증, 인증된 상태
- Python 3.10+ (표준 라이브러리만 사용, `jq` 불필요)
- Claude Code 2.1.220+

설치가 끝나면 진단부터 돌려보세요:

```bash
python3 "<스킬 디렉터리>/scripts/codex_bridge.py" doctor
```

문제가 없으면 exit 0, 차단 요인이 있으면 exit 2 와 함께 `blockers` 배열에 이유가 나옵니다.

## 무엇을 하는가

| 명령 | 하는 일 |
|---|---|
| `start` | 새 스레드. 기본 백그라운드, 즉시 `{run_id, thread_id}` 반환 |
| `resume` | 기존 스레드에 턴 추가. 기록된 설정을 전부 다시 주입 |
| `review` | `codex exec review` 의 별도 플래그 표면 |
| `status` | 상태, 경과, `idle_seconds`, 토큰, 진행 중 아이템 |
| `log` | 필터링된 이벤트를 증분으로 (`--since` 커서) |
| `show` | 특정 아이템 하나의 전체 출력 |
| `stop` | 프로세스 그룹 단위 중단 (이름 매칭 절대 안 함) |
| `result` | 최종 메시지, 사용량, `--schema` 사용 시 파싱된 JSON |
| `doctor` | PATH, 버전, `CODEX_HOME`, 인증, 설정 샌드박스, 경로, 레지스트리 |

기본값: 백그라운드 · `workspace-write` · 사용자 설정 격리(`--ignore-user-config`) ·
`service_tier=priority` 재주입 · 모델/effort 고정 안 함 · 하드 타임아웃 없음.

## 컨텍스트 규율

`file_change` 이벤트는 **경로와 종류만** 담습니다. 컨텍스트 위험은 전부
`command_execution.aggregated_output` 한 필드에 있습니다 — 명령의 전체 stdout이라서,
Codex가 2,000줄짜리 파일을 `cat` 하면 그 파일 전체가 여기 들어옵니다.

그래서 기본 레벨은 명령 출력을 절대 싣지 않고, 대신 크기만 알려줍니다:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

필요하면 `show --run <id> --item item_2` 로 그 하나만 가져옵니다.

기본 레벨 `compact` 는 추측이 아니라 **실측으로** 골랐습니다 — 네 가지 워크로드를 실제로
돌려 모든 레벨에서 측정한 표가
[`docs/measurements/filter-calibration.md`](docs/measurements/filter-calibration.md) 에
있습니다. 핵심 근거: `compact` 바이트의 38–85%가 **에이전트 메시지 자체**입니다. 즉
`compact` 는 "답변 + 수백 바이트의 뼈대" 이고, 원시 명령 출력은 대개 그 요약의 사본입니다.

## 세션 종료 시 정리

세션이 끝나면(`/clear`, `/resume` 포함) 그 세션이 시작한 백그라운드 런을 정리합니다.
아무도 보지 않는 런이 계속 리포에 쓰고 토큰을 태우는 쪽이 더 나쁜 실패이고, 중단된 런은
rollout에서 재개할 수 있기 때문입니다. `--detach` 로 시작한 런은 면제됩니다.

## v1 범위 밖

고려한 끝에 뺀 것들입니다 — 빠뜨린 게 아닙니다.

- **`codex cloud`** — 실험적이고 표면이 큼
- **`codex mcp-server` / `app-server`** — 공식 문서상 "예고 없이 바뀔 수 있음"
- **진짜 턴 중간 개입** — `codex exec` 는 입력 채널이 없는 단일 비대화형 턴입니다. TUI는
  가능하지만 TTY가 필요합니다. v1의 개입 모델은 **중단 → 재개** 이고, SIGINT가 스레드를
  재개 가능한 상태로 남기기 때문에 동작합니다. `app-server` 는 유일하게 가능성 있는 경로로
  [`troubleshooting.md`](.claude/skills/codex/references/troubleshooting.md) 에
  **미검증** 으로 기록해 뒀습니다.

## 개발

```bash
python3 -m unittest discover -s tests -p 'test_*.py'    # T1 — 가짜 codex 대상, 무료
python3 tests/integration/run_integration.py            # T2 — 실제 Codex, 토큰 소모
python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path .
```

T1은 실제 실행에서 캡처한 이벤트 스트림을 재생하는 가짜 `codex` 를 PATH 앞에 두고 돕니다.
그 안에 위에서 설명한 샌드박스 드리프트 회귀 테스트가 들어 있습니다 — `read-only` 로 시작한
뒤 resume 했을 때 기록된 argv에 `-c sandbox_mode="read-only"` 가 실제로 들어가는지 확인합니다.

설계 근거와 측정치 전문은
[`docs/plan/codex-skill-implementation-plan.md`](docs/plan/codex-skill-implementation-plan.md),
계약은 [`.claude/harness-spec.md`](.claude/harness-spec.md) 에 있습니다.

## 라이선스

[Apache-2.0](LICENSE)
