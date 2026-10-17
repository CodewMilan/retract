# Infrastructure, free tiers, and costs

Pricing/documentation checked: 16 October 2026. These are published terms and planning estimates, not verified account entitlements or provisioned resources. Recheck before deploying or enabling billing.

## Recommended configuration

Run FalkorDB in Docker on the developer's laptop with a persistent volume and explicitly verified durability settings. Run the Python service, dashboard, and MCP adapter locally. Use a hosted model API for small update-classification requests.

Additional infrastructure spend can be $0 if existing hardware and free inference capacity suffice. Electricity, internet, existing coding-assistant subscriptions, and development time are not included. No local GPU is required with hosted inference.

| Component | MVP choice | Cost expectation |
| --- | --- | --- |
| Graph storage | Local FalkorDB container | No additional hosting fee. |
| API and dashboard | Local Python process and browser | No additional hosting fee. |
| Coding-client integration | Local MCP adapter | No hosting fee; coding-client usage billed separately if applicable. |
| Update classification | Groq free API tier | $0 within account limits. |
| Public demo URL | Optional Render deployment | Free within limits; requires a separate suitable database arrangement. |

## Database persistence

FalkorDB documents a Docker data volume at /var/lib/falkordb/data and RDB/AOF durability options. A mounted directory alone is not the acceptance test: write state, stop/start the service, and verify identical records and history. Check crash-recovery behavior separately if claiming it.

Use named volumes, pin the tested image version, and keep synthetic seed data separate from stored user updates. Restart tests must not silently reseed the graph. Avoid commands that delete volumes during rehearsal.

Source: [FalkorDB Docker persistence](https://docs.falkordb.com/operations/durability/persistence).

## FalkorDB Cloud free tier

Published terms:

- 100 MB RAM and maximum graph dataset size of 100 MB.
- No credit card required.
- No TLS, persistence, or automated backups on the free tier.
- Inactive instances stop after one day and are deleted after seven days.
- Startup paid tier begins at $73/month.

A small fixture graph is a reasonable candidate for evaluation on this tier, but measure actual use. It is not our recommended persistent-memory demonstration environment. A cloud preview using it should contain only disposable synthetic demo data and explain its limitations.

Source: [FalkorDB Cloud Free Tier](https://docs.falkordb.com/cloud/tiers/free).

## Render free hosting

Published free web-service behavior:

- 750 free instance hours per workspace per month.
- Sleeps after 15 minutes without inbound traffic.
- Wake-up takes approximately one minute.
- Filesystem changes are lost on restart/redeploy/spin-down.
- Persistent disks require a paid service.
- Bandwidth/build usage limits also apply; payment configuration affects overage behavior.

Render is optional for a public application preview. Do not store the authoritative graph on its free ephemeral filesystem. A free frontend does not make a durable database free. Keep the local demo available regardless of preview uptime.

Source: [Render free services](https://render.com/docs/free).

## Groq model API

Candidate to evaluate: openai/gpt-oss-20b through Groq. This is a proposed cost-efficient classifier, not a validated choice for our task.

Published free limits for this model:

| Limit | Published amount |
| --- | --- |
| Requests per minute | 30 |
| Requests per day | 1,000 |
| Tokens per minute | 8,000 |
| Tokens per day | 200,000 |

Organization-specific limits can differ. At an illustrative 2,000 total tokens per update, the daily allowance covers about 100 updates before other usage. The per-minute token limit can bind long before the request count. Use bounded candidate retrieval, short outputs, and backoff on rate limiting. Do not fan out one model call per stored fact.

Source: [Groq rate limits](https://console.groq.com/docs/rate-limits).

Published paid pricing is $0.075 per million input tokens and $0.30 per million output tokens. Example, not a bill estimate:

```text
1,000 calls x 1,500 input tokens = 1.5M input tokens = $0.1125
1,000 calls x 500 billable output tokens = 0.5M output tokens = $0.1500
Illustrative total = $0.2625
```

Additional reasoning tokens, longer prompts, retries, taxes, or another model change this amount. The developer's coding assistant is a separate workload. Upgrading to Groq's paid Developer tier requires a payment method; do not upgrade automatically. An optional $5 contingency is a planning allowance, not a required fee or promised total.

Sources: [Groq model pricing](https://console.groq.com/docs/model/openai/gpt-oss-20b), [billing FAQs](https://console.groq.com/docs/billing-faqs).

## What is deliberately unnecessary

For one project and a small fact set, we do not need Kubernetes, a GPU server, a separate vector database, a second relational database, a distributed queue, or a public MCP endpoint. Add infrastructure only to solve a measured problem.

## First setup checks

1. Confirm Docker runs and the selected image starts on the developer's machine.
2. Verify a graph write/read and persistence across service restart.
3. Verify one structured model response and the actual account limits.
4. Connect the selected coding client and observe a real recall call.
5. Check end-to-end latency with the real demo fixture.

The free configuration is appropriate for a local hackathon prototype. A durable hosted service needs its own hosting, security, capacity, and cost assessment.
