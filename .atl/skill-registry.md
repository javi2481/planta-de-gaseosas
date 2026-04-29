# Skill Registry — planta-de-gaseosas

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

Generated: 2026-04-28

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| Creating a PR, opening a pull request, preparing changes for review | `branch-pr` | C:/Users/javie/.claude/skills/branch-pr/SKILL.md |
| Writing Go tests, Bubbletea TUI testing, teatest, adding test coverage | `go-testing` | C:/Users/javie/.claude/skills/go-testing/SKILL.md |
| Creating a GitHub issue, reporting a bug, requesting a feature | `issue-creation` | C:/Users/javie/.claude/skills/issue-creation/SKILL.md |
| "judgment day", "judgment-day", "review adversarial", "dual review", "doble review", "juzgar", "que lo juzguen" | `judgment-day` | C:/Users/javie/.claude/skills/judgment-day/SKILL.md |
| Creating a new skill, adding agent instructions, documenting patterns for AI | `skill-creator` | C:/Users/javie/.claude/skills/skill-creator/SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### branch-pr
- Every PR MUST link an approved issue with `status:approved` label — no exceptions
- Every PR MUST have exactly one `type:*` label (type:feature, type:bug, type:docs, type:refactor, type:chore, type:breaking-change)
- Branch naming: `type/description` — regex `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)\/[a-z0-9._-]+$`
- PR body MUST contain `Closes #N` (or Fixes/Resolves) linking to approved issue
- Conventional commits: `type(scope): description` — no `Co-Authored-By` trailers
- Run `shellcheck scripts/*.sh` before pushing if modifying shell scripts
- Add type label after PR creation: `gh pr edit <number> --add-label "type:feature"`

### go-testing
- Table-driven tests: `tests := []struct{ name, input, expected }{ ... }` → `for _, tt := range tests { t.Run(tt.name, ...) }`
- Test Bubbletea state directly: `newModel, _ := m.Update(tea.KeyMsg{...}); m = newModel.(Model)`
- Full TUI flows: `teatest.NewTestModel(t, m)` + `tm.Send()` + `tm.WaitFinished(t, ...)`
- Visual output regression: golden files in `testdata/*.golden`, regenerate with `-update` flag
- Organize co-located: `model.go` → `model_test.go` in same package
- Integration tests: skip with `-short` flag; use `t.TempDir()` for filesystem ops
- Commands: `go test ./...`, `go test -cover ./...`, `go test -run TestName`

### issue-creation
- Search duplicates first: `gh issue list --search "keyword"` before creating
- MUST use a template (bug_report.yml or feature_request.yml) — blank issues are blocked by CI
- Issue auto-gets `status:needs-review`; maintainer MUST add `status:approved` before any PR opens
- Questions → Discussions, NOT issues
- Bug title format: `fix(scope): description`; Feature title: `feat(scope): description`
- Pre-flight checkboxes: confirm no duplicate + understand approval workflow

### judgment-day
- Resolve skill registry FIRST (Pattern 0) before launching any judges — inject compact rules into ALL sub-agents
- Launch TWO blind judge sub-agents in parallel — never sequential, never review yourself as orchestrator
- Judges MUST classify every finding: CRITICAL | WARNING (real) | WARNING (theoretical) | SUGGESTION
- WARNING (theoretical) = requires contrived/malicious scenario → report as INFO only, do NOT fix, do NOT re-judge
- Synthesize: Confirmed (both agree) | Suspect A or B (one only) | Contradiction (disagree on same thing)
- Round 1: present verdict table → ASK user to confirm before fixing confirmed issues
- Round 2+: only re-judge for confirmed CRITICALs; fix confirmed real WARNINGs inline without re-judging
- After 2 fix iterations: ASK user whether to continue — never auto-escalate
- NEVER push/commit after fixes until re-judgment completes
- Fix Agent is a SEPARATE delegation — never reuse a judge as the fixer

### skill-creator
- File location: `skills/{skill-name}/SKILL.md` with complete frontmatter
- Frontmatter MUST include `Trigger:` in the description field — agents auto-load based on this
- Content order: When to Use → Critical Patterns → Code Examples → Commands → Resources
- No Keywords section, no troubleshooting, no web URLs in references/ (local paths only)
- After creating: register in AGENTS.md table with skill name, description, and SKILL.md link
- assets/ for templates/schemas; references/ for local doc file pointers only

## Project Conventions

| File | Path | Notes |
|------|------|-------|
| PRD | `docs/prd fabrica de gaseosas.md` | Fuente de verdad: user stories, stack, DoD |

No CLAUDE.md, AGENTS.md, or .cursorrules found at project level.

### Project-Specific Compact Rules (planta-de-gaseosas)

Rules derived from the PRD and SDD design — apply to all implementation sub-agents:

#### Docker Compose
- All services MUST have `healthcheck` defined with `interval`, `timeout`, `retries`, `start_period`
- `depends_on` MUST use `condition: service_healthy` (or `service_completed_successfully` for one-shot jobs)
- All secrets via `.env` — never hardcode in docker-compose.yml
- `restart: unless-stopped` on all services except `createbuckets` (`restart: "no"`)
- Startup time MUST be < 60 seconds total
- Single bridge network `planta_net`; services resolve each other by service name

#### InfluxDB 3 Core (CRITICAL gotchas)
- Image: `influxdb:3-core`, port **8181** (NOT 8086) — every service referencing InfluxDB must use 8181
- Run with `--without-auth` for dev — no env-var token bootstrap exists in v3
- Config via env vars: `INFLUXDB3_OBJECT_STORE=s3`, `AWS_ENDPOINT=http://minio:9000`, `AWS_ALLOW_HTTP=true`
- `AWS_ALLOW_HTTP=true` is MANDATORY — without it, MinIO writes fail silently with TLS error
- MinIO bucket `influxdb3` MUST exist before InfluxDB starts (`createbuckets` service with `quay.io/minio/mc`)

#### Telegraf
- `organization = ""` (empty string) in `[[outputs.influxdb_v2]]` — CRITICAL for InfluxDB 3 compatibility
- Any non-empty org value → HTTP 400 error (silent write failure)
- `bucket = "sensores"`, `urls = ["http://influxdb:8181"]`
- MQTT input: `data_format = "value"`, `data_type = "float"`, topic_parsing maps last segment to measurement
- `flush_interval = "1s"` to keep dashboard latency < 3s

#### Python Simulator
- Python 3.11 + paho-mqtt, single-threaded loop with `loop_start()`
- Topics: `planta/linea1/sensor/<nombre>` at 1s intervals
- 9 sensors: temperatura_pasteurizador, presion_llenadora, nivel_jarabe, caudal_agua, vibracion_llenadora, temperatura_camara_co2, velocidad_cinta, conteo_botellas, conteo_rechazos
- Spike trigger: `(t % 300) < 2` — fires for 2s every 5 minutes
- conteo_botellas and conteo_rechazos are monotonically increasing counters (never reset)

#### Grafana
- Image: `grafana/grafana:11.2.0`; datasource uses InfluxQL (NOT Flux, NOT SQL/FlightSQL)
- All config provisioned as code — no manual UI steps permitted
- Alerts in `grafana/provisioning/alerting/rules.yaml` (NOT embedded in dashboard JSON)
- Alert thresholds: `temperatura_pasteurizador > 85°C`, `vibracion_llenadora > 8 mm/s`
- Dashboard: 8 time-series panels + 1 OEE stat panel; OEE = (conteo_botellas - conteo_rechazos) / conteo_botellas
- Sensor-to-dashboard latency MUST be < 3 seconds
