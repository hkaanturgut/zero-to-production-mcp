# Production MCP server checklist

Each item is implemented in this repo and covered by a test or a pipeline gate.

## Identity and tokens
- [ ] Validate signature, issuer, audience and expiry on every request (`test_auth`).
- [ ] Reject tokens issued for any other resource. Never pass caller tokens downstream.
- [ ] Publish Protected Resource Metadata; 401s point to it (`resource_metadata`).
- [ ] Clients register with CIMD; no Dynamic Client Registration.
- [ ] HTTPS everywhere except loopback in development.

## Least privilege
- [ ] Advertise only the baseline scope; request more by step-up.
- [ ] One permission tag per tool, enforced server-side, checked in CI (`test_tool_contracts`).
- [ ] Tools you can't use are hidden from `tools/list`.
- [ ] Agents get app roles without manager rights; managers get a role, not a consentable scope.
- [ ] Destructive or costly actions need a human confirmation (`input_required`).

## Secrets and data
- [ ] Backend credentials only in Key Vault + managed identity; never in args, results, errors or logs (`test_backend_secret_never_reaches_the_client`).
- [ ] Return the minimum data; mask personal data (`test_masking`).
- [ ] Mark free text as untrusted data; enforce policy in code, not prompts (`test_injection_...`).
- [ ] IDs are random and bound to the caller from the token (`test_cannot_read_another_salespersons_lead`).

## Tool quality
- [ ] Verb-first names, one job each, descriptions that say what not to do.
- [ ] Typed, bounded inputs; output schemas; pagination instead of truncation.
- [ ] Business math in code (Decimal), never in the model.
- [ ] Tool failures return `isError` results the model can act on.

## Failure and operations
- [ ] Per-attempt deadline, read-only retries with jitter, circuit breaker (`test_resilience_and_safety`).
- [ ] Idempotency keys on every write.
- [ ] One audit event per call with correlation ID; argument names only.
- [ ] Per-caller rate limit.
- [ ] Stateless server (2026-07-28), min 1 replica, health probes.
- [ ] Build once, scan, promote the same image; prod only on a deliberate trigger (reviewer gate, or a manual run on plans without one).
