# Jira MCP Adapter Operations Guide

## Purpose

This guide explains how to configure, run, troubleshoot, and rollback the Jira MCP adapter used for read-only ingestion of Jira Epics, Stories, Bugs, Tasks, and Sub-tasks.

## Setup

1. Copy the template at [config/jira-mcp-adapter.example.yaml](config/jira-mcp-adapter.example.yaml) into your environment-specific config location.
2. Copy [.env.example](.env.example) to `.env` and set environment values.
3. Set one auth mode in config:
   - api_token: requires email and JIRA_API_TOKEN
   - pat: requires JIRA_PAT
   - bearer: requires JIRA_BEARER_TOKEN
4. Export credentials in your shell before running ingestion, or rely on `.env` file loading.

## .env Configuration

The adapter supports `JiraMcpAdapterConfig.from_env()` for loading configuration from `.env`:

- Reads key/value pairs from `.env` (or custom path).
- Uses process environment variables to override file values.
- Supports auth, timeout, retry, pagination, and issue-type mapping.

Example override precedence:
- `.env` contains `JIRA_BASE_URL=https://old.example.atlassian.net`
- shell exports `JIRA_BASE_URL=https://new.example.atlassian.net`
- resolved value is `https://new.example.atlassian.net`

## Required Configuration

- base_url
- deployment_type (cloud or data-center)
- auth mode and required secret
- timeout_seconds
- pagination bounds
- retry policy
- issue type mapping fallback and optional overrides

## Troubleshooting

### Invalid configuration

Symptoms:
- Adapter fails at startup with validation error.

Checks:
- base_url has http/https and host
- deployment_type is valid
- auth mode has required fields
- page_size does not exceed max_page_size

### Authentication failures

Symptoms:
- Immediate request failure from Jira endpoint.

Checks:
- Correct secret variable is exported
- Token has Jira read scope
- Email matches API token account for api_token mode

### Rate limiting or transient failures

Symptoms:
- Repeated warnings and eventual retry exhaustion.

Checks:
- Reduce page_size
- Narrow filters (project/status/updated_since)
- Increase max_attempts or backoff if acceptable

### Unexpected type mapping

Symptoms:
- Jira issue appears under fallback type.

Checks:
- Add issue type name to overrides
- Confirm exact Jira issue type label in your instance

## Rollback / Disable

1. Disable adapter initialization in runtime wiring.
2. Remove adapter config reference from deployment config.
3. Stop ingestion jobs that depend on Jira MCP adapter.
4. Revert to previous manual backlog intake process.

## Read-only Validation Procedure

1. Select a Jira project and filter window.
2. Run ingestion in read-only mode.
3. Compare counts by type (Epic, Story, Bug, Task, Sub-task) against Jira UI.
4. Record mismatches and tune issue_type_mapping overrides.
5. Re-run until counts and type assignments align.
