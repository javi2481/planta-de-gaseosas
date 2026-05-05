# Design: Cleanup GGA config and Docker Compose references

## Technical Approach

Two targeted string replacements in two files. No structural changes.

## Architecture Decisions

### Decision: Direct text replacement

**Choice**: Edit files in place with simple string substitution
**Alternatives considered**: N/A — trivial change
**Rationale**: Minimal risk, no refactoring needed

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.gga` | Modify | Line 26: change `FILE_PATTERNS="*.ts,*.tsx,*.js,*.jsx"` to `FILE_PATTERNS="*.py"` |
| `README.md` | Modify | Replace all 6 occurrences of `docker-compose` with `docker compose` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Manual | `.gga` has correct patterns | Open file, verify line 26 |
| Manual | README has no `docker-compose` | Search file for hyphenated form |

## Migration / Rollout

No migration required. Pure config/docs change.

## Open Questions

None
