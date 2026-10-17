# Original accepted browser authentication decision

Historical note for the demo, superseded by the current note and confirmed U1.

The original `web-client/main` plan used Authorization bearer headers for browser
API requests. The CLI's separate scope, `cli-client/main`, also uses bearer tokens.
Account data lives in PostgreSQL and users may update only their own profiles.

The initial memory fixture deliberately stores the original browser instruction
as F1, with P1 explicitly depending on F1 and ownership requirement F4. This is
the pre-correction state, not the contract to implement after U1.
