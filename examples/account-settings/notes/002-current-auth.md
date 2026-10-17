# Approved browser authentication correction

Scope: `web-client/main`. The browser account API uses HTTP-only cookie sessions
instead of Authorization bearer headers. The existing backend handles sessions;
the settings frontend uses that contract and the returned CSRF token. This keeps
session handling inside the application rather than asking the frontend to
invent a browser bearer-token flow.

The browser correction does not change `cli-client/main` authentication. Account
data remains in PostgreSQL, and ownership requirement F4 remains accepted: users
may access and update only their own profiles.

U1 is the explicit confirmed memory update. F1 is historical after U1, its
replacement F5 is current, and P1 needs review because it depended on F1. The
MongoDB question U2 remains an unaccepted proposal. These are expected fixture
outcomes; retrieve the actual state rather than assuming the update ran.
