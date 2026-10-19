# Contributing

Retract is a local Python service, a marketing site, and browser checks.
Install, the demo, and the API are in the [README](README.md).

## Layout

| Path | What it is |
| --- | --- |
| `src/retract/` | Service, graph, HTTP API, MCP adapter, dashboard, and account settings UI |
| `tests/` | Python tests and browser checks |
| `scripts/` | Phase verification and the release secret scan |
| `fixtures/` | Synthetic update and seed inputs |
| `examples/account-settings/` | Separate PostgreSQL-backed demo app |
| `landing/` | Marketing site. The image build publishes it at `/` |
| `docs/` | Product direction, specification, verification notes, and the submission draft |
| `docs/evidence/` | Recorded client and investigator runs cited by the docs |
| `compose.yaml` | Local FalkorDB |
| `compose.demo.yaml` | Synthetic account database |
| `compose.production.yaml` | Hosted-style service composition |
| `compose.verify.yaml` | Disposable verification database |

Copy [.env.example](.env.example) to `.env`. Generated output stays out of git:
virtualenvs, `reports/`, `landing/dist`, `node_modules`, and environment files.

## Checks

From an activated virtualenv with the package installed:

```sh
python -m unittest discover -s tests -v
npm test
python scripts/check_release.py
```

Browser checks need Playwright, as described in the README. The phase scripts
under `scripts/` are the acceptance gates. They write into `reports/`, which
is gitignored.

## What not to commit

- `.env`, `.env.*`, and any other secret file. `.env.example` is the only environment file in git.
- `reports/` and other local verification output.
- `.agents/` and `.aider-desk/`. `skills-lock.json` records the design skill used while building the dashboard. Reinstall that skill locally; do not vendor its tree.
- Build artifacts: `dist/`, `*.egg-info/`, and `src/retract/site/`.

This repository does not have a license yet. Do not add one unless the maintainer chooses it.
