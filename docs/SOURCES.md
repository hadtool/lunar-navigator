# Sources

Every external dataset, kernel, API and published value used by the project is listed here:
exact file name, URL, size, download date (UTC) and how it is used. Large files live in
`data/raw/` and are not committed.

## Challenge resources (official)

| Resource | URL | Used for |
|---|---|---|
| Challenge page | https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/ | Problem statement |
| JPL Horizons | https://ssd.jpl.nasa.gov/horizons/ (API: https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Independent check of Sun/Earth azimuth and elevation |
| LROC Quickmap | https://quickmap.lroc.asu.edu/ | Visual check of terrain, screenshots |
| Moon Trek | https://trek.nasa.gov/moon/ | 3D terrain view |
| CSA Moon Exploration | https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/ | Mission context |

## Terrain (LOLA, NASA PGDA)

_To be filled in T02: file names, URLs, sizes, download dates, projection._

## Ephemerides and kernels

_To be filled in T03: Horizons sample query, planetary ephemeris, lunar orientation kernels._

## Landing sites

_To be filled in T04: source of every site coordinate._

## Published values used for validation

_To be filled in T05 and T07._

## Development tooling (not part of the solution)

| Component | Source | Version | Retrieved (UTC) | Notes |
|---|---|---|---|---|
| `.claude/agents/python-reviewer.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | Code-review agent for Claude Code, copied unchanged |
| `.claude/skills/python-testing/SKILL.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | pytest guidance for Claude Code, copied unchanged |
