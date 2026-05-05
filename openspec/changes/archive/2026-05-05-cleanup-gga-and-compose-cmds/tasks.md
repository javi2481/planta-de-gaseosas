# Tasks: Cleanup GGA config and Docker Compose references

## Phase 1: Config fix

- [x] 1.1 Edit `.gga` line 26: change `FILE_PATTERNS="*.ts,*.tsx,*.js,*.jsx"` to `FILE_PATTERNS="*.py"`

## Phase 2: Documentation fix

- [x] 2.1 Replace all `docker-compose` with `docker compose` in `README.md` (6 occurrences: lines 50, 56, 99, 102, 113, 119)

## Phase 3: Verification

- [x] 3.1 Verify `.gga` line 26 reads `FILE_PATTERNS="*.py"`
- [x] 3.2 Verify `README.md` has zero occurrences of `docker-compose`
- [x] 3.3 Verify `README.md` uses `docker compose` in all Docker commands
