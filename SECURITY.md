# Security

Local mode trusts the developer on the machine. It is not a public
authenticated API. Do not expose `retract serve` on a shared network.

Do not commit API keys, database passwords, or `.env` files. This check scans
tracked files for a few common secret patterns and reports the location only:

```sh
python scripts/check_release.py
```

Report a vulnerability privately to the repository owner. Leave live keys out
of the report.
