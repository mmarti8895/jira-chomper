from __future__ import annotations

from datetime import datetime

import pytest

from jira_chomper.jira_mcp_adapter import (
    AdapterValidationError,
    AuthConfig,
    IngestionError,
    IssueTypeMapping,
    JiraMcpAdapter,
    JiraMcpAdapterConfig,
    PaginationConfig,
    RetryPolicy,
    WorkItemFilters,
)


class _AlwaysFailsTransport:
    def __init__(self, status_code: int | None = None) -> None:
        self.status_code = status_code

    def search_issues(self, *, jql: str, start_at: int, max_results: int, fields: list[str]):
        class _Err(RuntimeError):
            pass

        err = _Err("boom")
        if self.status_code is not None:
            setattr(err, "status_code", self.status_code)
        raise err


def _valid_config() -> JiraMcpAdapterConfig:
    return JiraMcpAdapterConfig(
        base_url="https://example.atlassian.net",
        deployment_type="cloud",
        auth=AuthConfig(mode="api_token", email="dev@example.com", api_token="secret"),
        timeout_seconds=20,
        retry=RetryPolicy(max_attempts=2),
        pagination=PaginationConfig(page_size=10, max_pages=2, max_page_size=50),
        issue_type_mapping=IssueTypeMapping(overrides={"User Story": "Story"}, fallback="Task"),
    )


def test_valid_config_passes_validation() -> None:
    cfg = _valid_config()
    cfg.validate()


def test_missing_auth_fails_fast() -> None:
    cfg = JiraMcpAdapterConfig(
        base_url="https://example.atlassian.net",
        deployment_type="cloud",
        auth=AuthConfig(mode="api_token", email="dev@example.com", api_token=None),
    )
    with pytest.raises(AdapterValidationError) as exc:
        cfg.validate()
    assert exc.value.code == "missing_auth_fields"


def test_page_size_bounds_enforced() -> None:
    cfg = JiraMcpAdapterConfig(
        base_url="https://example.atlassian.net",
        deployment_type="cloud",
        auth=AuthConfig(mode="api_token", email="dev@example.com", api_token="secret"),
        pagination=PaginationConfig(page_size=200, max_pages=1, max_page_size=100),
    )
    with pytest.raises(AdapterValidationError) as exc:
        cfg.validate()
    assert exc.value.code == "page_size_exceeds_max"


def test_mapping_override_and_fallback_behavior() -> None:
    mapping = IssueTypeMapping(overrides={"Feature": "Epic"}, fallback="Task")
    assert mapping.resolve("Feature") == "Epic"
    assert mapping.resolve("UnknownType") == "Task"


def test_jql_contains_supported_filters() -> None:
    cfg = _valid_config()

    class _NoopTransport:
        def search_issues(self, *, jql: str, start_at: int, max_results: int, fields: list[str]):
            return {"issues": [], "total": 0}

    adapter = JiraMcpAdapter(cfg, _NoopTransport())
    jql = adapter._build_jql(
        WorkItemFilters(
            project="JCP",
            board="Main",
            statuses=["To Do", "In Progress"],
            assignee="alice",
            labels=["api", "mcp"],
            updated_since=datetime(2026, 4, 1, 8, 0),
        )
    )
    assert "project = \"JCP\"" in jql
    assert "board = \"Main\"" in jql
    assert "status in" in jql
    assert "labels in" in jql
    assert "updated >=" in jql


def test_retry_exhaustion_returns_structured_error() -> None:
    cfg = _valid_config()
    adapter = JiraMcpAdapter(cfg, _AlwaysFailsTransport(status_code=429))
    with pytest.raises(IngestionError) as exc:
        adapter.fetch_work_items(WorkItemFilters(project="JCP"))
    assert exc.value.attempts == cfg.retry.max_attempts
    assert exc.value.last_status == 429


def test_from_env_loads_values_from_dotenv_file(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://example.atlassian.net",
                "JIRA_DEPLOYMENT_TYPE=cloud",
                "JIRA_AUTH_MODE=api_token",
                "JIRA_EMAIL=dev@example.com",
                "JIRA_API_TOKEN=secret",
                "JIRA_PAGE_SIZE=25",
                "JIRA_MAX_PAGES=5",
                "JIRA_MAX_PAGE_SIZE=100",
                "JIRA_FALLBACK_ISSUE_TYPE=Task",
                "JIRA_ISSUE_TYPE_OVERRIDES=User Story:Story,Defect:Bug",
            ]
        ),
        encoding="utf-8",
    )

    cfg = JiraMcpAdapterConfig.from_env(str(env_file), environ={})
    cfg.validate()

    assert cfg.base_url == "https://example.atlassian.net"
    assert cfg.pagination.page_size == 25
    assert cfg.issue_type_mapping.resolve("User Story") == "Story"
    assert cfg.issue_type_mapping.resolve("Defect") == "Bug"


def test_from_env_explicit_environment_overrides_dotenv(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://old.example.atlassian.net",
                "JIRA_DEPLOYMENT_TYPE=cloud",
                "JIRA_AUTH_MODE=api_token",
                "JIRA_EMAIL=dev@example.com",
                "JIRA_API_TOKEN=old-secret",
            ]
        ),
        encoding="utf-8",
    )

    cfg = JiraMcpAdapterConfig.from_env(
        str(env_file),
        environ={
            "JIRA_BASE_URL": "https://new.example.atlassian.net",
            "JIRA_DEPLOYMENT_TYPE": "cloud",
            "JIRA_AUTH_MODE": "api_token",
            "JIRA_EMAIL": "new@example.com",
            "JIRA_API_TOKEN": "new-secret",
        },
    )
    cfg.validate()

    assert cfg.base_url == "https://new.example.atlassian.net"
    assert cfg.auth.email == "new@example.com"
    assert cfg.auth.api_token == "new-secret"
