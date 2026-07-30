# Contributing to HALI

HALI was built for the IGAD Hackathon 2026. Contributions, forks, and
adoption by organizations working in early warning or humanitarian
response are welcome.

## Local setup

See the [README](README.md) for the full local development setup: the Nx
monorepo, Poetry for the backend, npm for the frontend, and Docker Compose
for local PostGIS.

## Reporting bugs or requesting features

Open a GitHub issue using the templates provided. Include reproduction
steps for bugs where possible.

## Pull requests

- Keep PRs focused on a single change.
- Run the backend test suite and linter before submitting:

  ```bash
  cd apps/backend
  poetry run pytest
  poetry run ruff check src/
  ```

- Describe what changed and why in the PR description.

## A note on facts and figures

Numbers that appear in the README, the landing page, or any public-facing
copy are derived from `apps/landing/src/data/site.ts`, which is the
project's single source of truth for them. Each entry there cites the file
it comes from. If you add a data source or a language, add it to that file
rather than hand-editing a count somewhere downstream — the counts are
computed from the arrays, so everything else follows automatically.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
