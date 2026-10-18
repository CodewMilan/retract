Implemented `/settings` with synthetic sign-in, session recovery, editable display name, save, sign-out, and accessible loading/error/saved states. The code diff remains preserved and uncommitted.

RETRACT recall returned `F5/S-U1`, replacing bearer fact `F1` through event `U1` and flagging plan `P1`. I revised the implementation to use cookies and CSRF while preserving PostgreSQL (`F3/S-F3`) and ownership checks (`F4/S-F4`). The backend and approved note independently confirmed this contract.

Validation:

- **10/10 existing demo contract tests passed.**
- **10/10 Chromium browser scenarios passed**, including actual cookie/CSRF requests, no bearer header, cross-user rejection, failed saves, and session recovery.
- `git diff --check` passed.
- Disposable PostgreSQL schemas were removed; fixture servers stopped.

The first browser attempt failed because the macOS sandbox blocked Chromium; the permitted retry passed. The 503 cases were simulated. Other browsers and a full accessibility audit were not tested.

[Implementation report](/private/tmp/retract-fresh-client-20261018/examples/account-settings/IMPLEMENTATION_REPORT.md) records changed files, actual tool calls and IDs, exact results, failures, and limitations. Graph memory and the existing live service were unchanged.