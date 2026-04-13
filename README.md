# jira-chomper
Get Jiras, chomp them into little pieces.

## Jira MCP Adapter

This repository includes a read-only Jira MCP adapter implementation for:
- Epic
- Story
- Bug
- Task
- Sub-task

The adapter supports:
- config validation with fail-fast errors
- .env-based configuration via `JiraMcpAdapterConfig.from_env()`
- issue type mapping overrides plus fallback behavior
- Jira query filtering by project, board, status, assignee, labels, updated_since
- deterministic pagination with bounded limits
- retry with exponential backoff for transient and rate-limit failures
- normalized internal work-item output model

## Project Layout

- [src/jira_chomper/jira_mcp_adapter.py](src/jira_chomper/jira_mcp_adapter.py): core adapter logic
- [tests/unit/test_jira_mcp_adapter_config.py](tests/unit/test_jira_mcp_adapter_config.py): unit tests for config and retry behavior
- [tests/integration/test_jira_mcp_adapter_ingestion.py](tests/integration/test_jira_mcp_adapter_ingestion.py): integration-style ingestion tests with fake transport
- [config/jira-mcp-adapter.example.yaml](config/jira-mcp-adapter.example.yaml): adapter config template
- [docs/jira-mcp-adapter-operations.md](docs/jira-mcp-adapter-operations.md): setup and troubleshooting guide

## Local Development

Install dev dependencies and run tests:

```powershell
python -m pip install -e .[dev]
pytest
```

## Environment Configuration

Create a `.env` from [.env.example](.env.example), then load config in code with:

```python
from jira_chomper import JiraMcpAdapterConfig

config = JiraMcpAdapterConfig.from_env()
config.validate()
```

## Operational Notes

Use [docs/jira-mcp-adapter-operations.md](docs/jira-mcp-adapter-operations.md) for:
- credential configuration
- common failure diagnostics
- rollback and disable procedure
- read-only validation checklist against Jira UI
