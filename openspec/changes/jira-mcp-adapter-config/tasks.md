## 1. Adapter Configuration Foundation

- [x] 1.1 Define Jira MCP adapter configuration schema (base URL, deployment type, auth mode, credentials, timeouts, retries, pagination bounds).
- [x] 1.2 Implement configuration validation with fail-fast, redacted structured errors for invalid or missing auth fields.
- [x] 1.3 Implement issue-type mapping configuration (Epic, Story, Bug, Task, Sub-task), override support, and fallback category behavior.

## 2. Jira Ingestion Pipeline

- [x] 2.1 Implement Jira read client calls through MCP with support for project, board, status, assignee, labels, and updated-since filters.
- [x] 2.2 Implement deterministic pagination with bounded page size and max-page limits.
- [x] 2.3 Implement normalization into stable internal work-item model (external ID, normalized type, title, status, assignee, parent linkage, source timestamps).

## 3. Resilience and Error Handling

- [x] 3.1 Implement transient-failure and rate-limit retries using exponential backoff and max-attempt ceilings.
- [x] 3.2 Implement structured ingestion errors for exhausted retries, including failure class, attempts, and last response context.
- [x] 3.3 Add observability hooks/logging for adapter initialization failures, pagination progress, and retry outcomes.

## 4. Verification and Rollout

- [x] 4.1 Add unit tests for config validation, mapping overrides/fallbacks, pagination limits, and normalization behavior.
- [x] 4.2 Add integration tests for Jira filter application, multi-page ingestion, rate-limit retries, and structured error outputs.
- [x] 4.3 Add operator documentation for setup, credential configuration, troubleshooting, and rollback/disable procedure.
- [ ] 4.4 Run read-only validation against a Jira project and verify fetched counts/types match Jira UI expectations.
