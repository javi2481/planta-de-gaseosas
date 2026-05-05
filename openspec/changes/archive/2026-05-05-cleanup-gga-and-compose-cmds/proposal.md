# Proposal: Cleanup GGA config and Docker Compose references

## Intent

Trivial cleanup: fix `.gga` file patterns for a Python project (currently set to TS/JS patterns), and update README.md to use Docker Compose v2 syntax (`docker compose` instead of `docker-compose`).

## Scope

### In Scope
- Change `.gga` line 26: `FILE_PATTERNS="*.ts,*.tsx,*.js,*.jsx"` → `FILE_PATTERNS="*.py"`
- Replace all `docker-compose` occurrences in `README.md` with `docker compose`

### Out of Scope
- Updating other docs or CI scripts (none found)
- Changing `.gga` exclude patterns or other settings

## Capabilities

### New Capabilities
None

### Modified Capabilities
None

## Approach

Two targeted text replacements — one in `.gga`, one global substitution in `README.md`. No structural changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.gga` | Modified | Fix FILE_PATTERNS for Python project |
| `README.md` | Modified | Replace `docker-compose` with `docker compose` (6 occurrences) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Accidental replacement in README code blocks | Low | Simple string replace, verify diff before commit |

## Rollback Plan

`git checkout -- .gga README.md`

## Dependencies

None

## Success Criteria

- [ ] `.gga` line 26 reads `FILE_PATTERNS="*.py"`
- [ ] `README.md` has zero occurrences of `docker-compose` (with hyphen)
- [ ] `README.md` uses `docker compose` (without hyphen) in all Docker commands
