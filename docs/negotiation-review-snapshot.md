# Review snapshot — 10 October 2026

Project: /Users/krishnadvaipayan/Documents/ChatGPT/agentid hackathon

Implemented: app/negotiations.py, app/coordinator.py, authenticated app/api.py routes, narrow app/mcp_server.py creator proposal tool, app/inbox.py routing, app/web/negotiations.js Outreach panel.

Local controls: creator allowlist/contact evidence; approved current brief revision; explicit brand reveal or reviewed anonymous sender; exact frozen proposal hash; versioned per-creator proposal outbox; stable operation ID; atomic shared budget including legacy outbox; maximum three workers; received→quarantined→verified durable replies; cancellation before dispatch releases safely; unknown sends retain reservations; operator reconciliation; human external-agreement recording. Incoming text cannot change approved tool arguments, recipients or spending limits.

Evidence: 51 Python tests pass; three JavaScript regressions pass. The tests include three concurrent creator workers with distinct task IDs and scoped delegation/approval, concurrent budget exhaustion, duplicates/conflicts, spoofed sender/thread rejection, interrupted receive, uncertain provider acceptance, cancellation and human confirmation prerequisites. Runtime and SMTP are mocks in the three-worker acceptance test. No new model calls or actual email sends occurred.

Remaining verification: register/configure actual runtime and coordinator/acting identities; inspect actual delegation acknowledgement schema; configure inclusive numeric cap on both proposal tools and verify Applied; correlate Reporting; configure/review SMTP and IMAP; verify neutral identity provider headers; approve and perform controlled live email acceptance tests; rotate the chat-exposed Gemini credential and enter a replacement locally before model use. No production readiness claim.

Bounded rounds: three rounds and four hours per creator, with a verified reply to the current operation, model suggestion, operator supersession evidence, exact proposal approval and atomic shared-budget delta. Old/uncertain sends block changes. The review defect allowing redraft with creator holds is fixed and covered for reserved, dispatching, unknown, accepted and inbox-received states.

Scope limits: no unapproved autonomous bargaining, binding agreement, payment or publication. Creator brief PDF attachment could not be materialized; presentation uses inspected Wyld source structure. Existing Wyld project remained read-only. UI visual acceptance needs a real browser review; HTTP and isolated DOM tests do not establish appearance.

Reconciliation review fix: released/superseded proposals are terminal in both reconciliation and provider delivery updates. Reconciliation must target the current creator round; stronger inbox receipt evidence cannot be downgraded. Every reconciliation/provider update runs the aggregate financial invariant within the write transaction. Regression covers old 20k acceptance after replacement by 10k under a 20k campaign budget, including simultaneous old reconciliation and replacement. No late old hold can be restored.
