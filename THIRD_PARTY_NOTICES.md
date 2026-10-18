# Dependencies, attribution, and data

Recorded 17 October 2026. This is an inventory of direct dependencies and upstream
license references, not a complete transitive license audit or a claim that all
specified versions are installed. The evaluation bundle records installed Python
package versions; actual image compatibility remains a live gate.

| Component | Role / declared version | Upstream license reference |
| --- | --- | --- |
| FalkorDB Python client | Required runtime, `>=1.2,<2` | [MIT](https://github.com/FalkorDB/falkordb-py/blob/main/LICENSE) |
| FalkorDB server | Authoritative graph, candidate Docker tag `6.0.2` | [Upstream Server Side Public License v1 text](https://github.com/FalkorDB/FalkorDB/blob/master/LICENSE.txt); image-specific contents still need verification. |
| Psycopg 3 / binary extra | Optional synthetic profile API, `>=3.2,<4` | [LGPL v3 text](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt); inspect the selected binary distribution's additional bundled notices. |
| MCP Python SDK | Optional independent interoperability tests, `>=1.26,<2` | [MIT](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) |
| Playwright | Development browser checks, `1.63.0` | [Apache 2.0](https://github.com/microsoft/playwright/blob/main/LICENSE); downloaded browsers have their own notices. |
| PostgreSQL | Optional demo database, `17-alpine` | [PostgreSQL License](https://www.postgresql.org/about/licence/); the container includes additional components. |
| Python / standard library | Runtime, 3.12+ | [Python license](https://docs.python.org/3/license.html) |
| Node.js | Development JavaScript checks, 20+; CI uses 24 | [Node.js license and notices](https://github.com/nodejs/node/blob/main/LICENSE) |
| Setuptools | Python build backend, `>=75` | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| General Sans | Brand wordmark, weights 500 and 600 | [Indian Type Foundry Font License](https://www.fontshare.com/fonts/general-sans) |

Package installation and Docker image pulls obtain these components separately;
the repository does not vendor their source or browser binaries. Preserve their
own notices if distributing packaged dependencies or images. The links above
identify upstream texts; they do not assign a license to RETRACT itself.
No project LICENSE has been selected by the owner yet.

## Protocol and service references

The narrow MCP implementation follows the published
[MCP stdio protocol](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
The optional interpreter calls Groq with the configured model; access is governed
by the provider's service/model terms, not a source license granted by this repo.
No model weights or provider credentials are bundled.

## Prior art

The correction workflow was inspired by
[invalidate](https://github.com/chopratejas/invalidate). Related prior art includes
[Graphiti](https://github.com/getzep/graphiti),
[Zep provenance](https://www.getzep.com/blog/how-zep-tracks-provenance-in-agent-memory/),
and [Mem0](https://github.com/mem0ai/mem0). These are references, not declared
runtime dependencies. We make no claim to have invented temporal memory,
invalidation, or source provenance. This inventory does not claim a forensic
comparison of all repository code against those projects.

## Data and assistance

Fixtures, approved-note examples, Alice/Bob profile data, and evaluation inputs
are synthetic. “Approved” is part of the declared demo workflow, not an assertion
about an external organization's documents. The app does not scrape private or
login-protected data. Do not substitute real personal data into a public demo.
The dashboard uses system fonts and repository-native CSS; no stock media or
AI-generated raster assets are included.

OpenAI Codex assisted with design, implementation, tests, and documentation.
The participant must review, understand, and be able to explain the code and
actual results. No agent-generated benchmark, completed coding session, or demo
recording is inferred from that assistance disclosure.
