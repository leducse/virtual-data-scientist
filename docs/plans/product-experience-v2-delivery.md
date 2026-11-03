# Product experience v2 delivery

Started October 31, 2026. Mode: portfolio advancing production readiness.
User authorized implementation, code pushes and testing of the proposed roadmap.
Existing AWS development/test allowance: $10; public launch is a separate release
gate because of the documented container findings and public spending controls.

- [x] Preserve and push the deployed AgentCore baseline on `feat/product-experience-v2`.
- [x] Implement reviewed method catalog, deterministic suggestions and Plotly figures/palettes/exports.
- [x] Persist execution events and redact runtime exception logging.
- [x] Test and deploy the first feature slice to the existing AWS development stacks.
- [x] Add authenticated streaming with replay and explicit cancellation.
- [x] Add server-enforced guest/account quotas and safe workspace claiming on login.
- [x] Add bounded speech input with editable transcripts.
- [x] Add private CloudWatch dashboard/alarms and operational runbooks.
- [x] Configure and test the branded subdomain, preserving existing access.
- [x] Complete hosted/browser/security acceptance, push implementation and record remaining release gates.

Baseline: 58 Python tests and 4 Node tests passed. First feature checks: 63 Python
tests and 6 Node tests passed. Baseline commit: b36c106.
Current AWS region/account were verified; current Cost Explorer estimates are
delayed, account-wide and do not yet reconcile this project's AgentCore usage.
They must not be represented as an exact project spend balance.

Do not read credential-bearing files, change the consulting website, create extra
chats, or reset other edits. Keep owner onboarding separate from temporary tests.


Final delivery: development release `dev-20261031-15`, runtime version 14, branded
HTTPS origin, 71 Python and 12 Node tests passing. Private AWS guest acceptance,
real browser Excel/forecast/Plotly/theme/export/reconnect, synthetic-microphone
Transcribe and fresh-Interpreter export reproduction passed. Detailed evidence is
under `docs/deployment/dev-v2-*` and `docs/validation.md`.

Public anonymous admission/self-signup, outbound alert delivery, continuous voice,
crash-resumable scheduling, broad cloud ML/research and reconciled billing remain
explicit boundaries. No additional user chats or subagents were created.
