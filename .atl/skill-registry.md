# Skill Registry — planta-de-gaseosas

Generated: 2026-04-28

## User Skills

| Skill | Trigger Context |
|-------|----------------|
| `branch-pr` | Creating PRs, preparing changes for review |
| `issue-creation` | Reporting bugs, requesting features, creating GitHub issues |
| `judgment-day` | Adversarial dual review: "judgment day", "doble review", "juzgar" |
| `sdd-apply` | Implementing tasks from a change (orchestrator launches this) |
| `sdd-archive` | Archiving completed changes (orchestrator launches this) |
| `sdd-design` | Writing technical design documents (orchestrator launches this) |
| `sdd-explore` | Investigating ideas, exploring codebase (orchestrator launches this) |
| `sdd-init` | Initializing SDD context in a project |
| `sdd-onboard` | Guided SDD walkthrough end-to-end |
| `sdd-propose` | Creating change proposals (orchestrator launches this) |
| `sdd-spec` | Writing specifications with Given/When/Then (orchestrator launches this) |
| `sdd-tasks` | Breaking down changes into task checklist (orchestrator launches this) |
| `sdd-verify` | Validating implementation against specs (orchestrator launches this) |
| `skill-creator` | Creating new AI agent skills |

## Project Conventions

**Source**: `docs/prd fabrica de gaseosas.md`

No CLAUDE.md, AGENTS.md, or .cursorrules found at project level.

## Compact Rules

### Docker Compose
- All services must have `healthcheck` defined
- Use `.env` for secrets (tokens, passwords) — never hardcode
- Startup time must be < 60 seconds total

### Python Simulator
- Python 3.11
- Use `paho-mqtt` for MQTT publishing
- Publish to topics: `planta/linea1/sensor/<nombre>`
- Publish frequency: 1 second per sensor
- Values: realistic baseline + gaussian noise + spike every ~5 min

### Sensors (8 total)
1. `caudal_jarabe` — litros/min
2. `presion_carbonatacion` — bar
3. `velocidad_cinta` — botellas/min
4. `temperatura_pasteurizador` — °C
5. `conteo_botellas` — acumulado
6. `nivel_tapas` — %
7. `vibracion_llenadora` — mm/s
8. `temperatura_camara_fria` — °C

### InfluxDB 3 + MinIO
- Backend storage: MinIO S3-compatible
- Output format: Parquet files visible in MinIO Console (port 9001)
- Auth via token in `.env`

### Grafana
- 8 time-series panels (one per sensor)
- 1 OEE panel (productos buenos / productos totales)
- Minimum 2 alerts: temperatura_pasteurizador out of range + vibracion_llenadora high
- Latency sensor → dashboard < 3 seconds
