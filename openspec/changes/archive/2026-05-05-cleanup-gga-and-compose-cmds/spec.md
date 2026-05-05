# Spec: Cleanup GGA config and Docker Compose references

## Requirements

### Requirement: GGA file patterns MUST match project language

The `.gga` configuration file SHALL specify `FILE_PATTERNS="*.py"` for this Python project.

#### Scenario: Correct file patterns for Python project

- GIVEN `.gga` exists in the project root
- WHEN the file is read
- THEN line 26 SHALL contain `FILE_PATTERNS="*.py"`

### Requirement: README MUST use Docker Compose v2 syntax

All Docker Compose commands in `README.md` SHALL use the v2 syntax `docker compose` (without hyphen).

#### Scenario: README uses docker compose without hyphen

- GIVEN `README.md` contains Docker Compose commands
- WHEN a user reads the installation and usage sections
- THEN all commands SHALL use `docker compose` (without hyphen)
- AND zero occurrences of `docker-compose` (with hyphen) SHALL exist
