## Context

This repository is moving to an OpenSpec-driven workflow and needs Jira data available through MCP so planning and execution tools can consume a consistent backlog source. Today, Jira work item access is manual and inconsistent, which introduces stale context and weak traceability. The design must support Jira Cloud and Data Center, secure credential handling, and predictable behavior under pagination and rate limits.

## Goals / Non-Goals

**Goals:**
- Define a concrete adapter configuration model for Jira MCP connectivity and runtime behavior.
- Normalize Jira issue types (Epic, Story, Bug, Task, Sub-task) into one internal work-item shape.
- Ensure deterministic query/filter behavior and stable pagination.
- Provide clear failure, retry, and observability behavior for operational reliability.

**Non-Goals:**
- Implementing Jira write-back or mutation operations.
- Replacing Jira workflow semantics with custom state machines.
- Building a full analytics/reporting layer over Jira data.
- Supporting non-Jira trackers in this change.

## Decisions

1. Use a dedicated adapter config capability (`jira-mcp-adapter-config`) separated from ingestion behavior.
- Rationale: Keeps connection/auth concerns independent from data semantics and allows reuse by future Jira reads.
- Alternative considered: Single combined capability. Rejected because it couples transport concerns to domain mapping and complicates testing.

2. Define explicit issue-type mapping rules with fallback behavior.
- Rationale: Jira instances often customize issue type names; mapping must be deterministic and overridable.
- Alternative considered: Hard-coded standard names only. Rejected because it breaks on customized Jira projects.

3. Require server-side filtering and paged retrieval with bounded page size.
- Rationale: Reduces API load and avoids unbounded memory consumption while reading large backlogs.
- Alternative considered: Full fetch then local filtering. Rejected due to cost, latency, and rate-limit exposure.

4. Standardize retry behavior using exponential backoff with max-attempt ceilings for transient HTTP failures and rate limits.
- Rationale: Improves robustness while preventing infinite retry loops.
- Alternative considered: Single retry or fixed delay. Rejected as either too brittle or too noisy under sustained throttling.

5. Treat auth and transport errors as structured adapter errors with operational metadata.
- Rationale: Enables consistent diagnostics and actionable logs across consumers.
- Alternative considered: Pass-through raw errors only. Rejected because it leaks provider-specific details and impairs troubleshooting.

## Risks / Trade-offs

- [Risk] Jira tenant-specific custom fields or issue type aliases may not map correctly on first setup.
  → Mitigation: Include configurable type mapping and validation checks during adapter initialization.

- [Risk] Aggressive polling/query windows may trigger Jira rate limits.
  → Mitigation: Enforce max page size, backoff policy, and updated-since filters as first-class config.

- [Risk] Credential misconfiguration could cause repeated auth failures and noisy logs.
  → Mitigation: Validate required auth fields at startup and fail fast with redacted diagnostics.

- [Trade-off] Strict normalization may omit tracker-specific fields not covered by the base model.
  → Mitigation: Preserve optional extension metadata for passthrough fields without violating core schema.

## Migration Plan

1. Add MCP adapter configuration files and environment variable contracts for Jira credentials.
2. Implement initialization-time validation for connectivity, auth, and mapping config.
3. Implement read path for paged Jira queries and normalization to internal work items.
4. Add tests for mapping, pagination, filtering, retry, and error translation.
5. Roll out in read-only mode and compare fetched work-item counts against Jira UI for validation.
6. Rollback by disabling Jira MCP adapter config and reverting to prior manual intake path.

## Open Questions

- Should adapter configuration support per-project mapping overrides in one config file or one profile per project?
- Do we require incremental sync checkpoints in this change, or can updated-since be provided externally by callers?
- Which minimum fields are mandatory in the normalized internal model for downstream planning tools?
