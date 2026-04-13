from __future__ import annotations

from jira_chomper.jira_mcp_adapter import AuthConfig, JiraMcpAdapter, JiraMcpAdapterConfig, WorkItemFilters


class _FakeTransport:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls = 0
        self.seen_jql: list[str] = []

    def search_issues(self, *, jql: str, start_at: int, max_results: int, fields: list[str]):
        self.seen_jql.append(jql)
        idx = self.calls
        self.calls += 1
        if idx >= len(self.pages):
            return {"issues": [], "total": 0}
        return self.pages[idx]


def _issue(key: str, issue_type: str, parent: str | None = None) -> dict:
    parent_obj = {"key": parent} if parent else None
    return {
        "key": key,
        "self": f"https://example.atlassian.net/rest/api/3/issue/{key}",
        "fields": {
            "summary": f"summary-{key}",
            "issuetype": {"name": issue_type},
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Alice"},
            "parent": parent_obj,
            "updated": "2026-04-12T10:00:00.000+0000",
            "created": "2026-04-01T10:00:00.000+0000",
        },
    }


def test_ingestion_applies_filters_paginates_and_normalizes() -> None:
    transport = _FakeTransport(
        pages=[
            {
                "issues": [_issue("JCP-1", "Epic"), _issue("JCP-2", "Sub-task", parent="JCP-1")],
                "total": 3,
            },
            {
                "issues": [_issue("JCP-3", "Story")],
                "total": 3,
            },
        ]
    )
    config = JiraMcpAdapterConfig(
        base_url="https://example.atlassian.net",
        deployment_type="cloud",
        auth=AuthConfig(mode="api_token", email="dev@example.com", api_token="secret"),
    )
    adapter = JiraMcpAdapter(config, transport)

    items = adapter.fetch_work_items(WorkItemFilters(project="JCP", statuses=["In Progress"]))

    assert len(items) == 3
    assert items[0].type_category == "Epic"
    assert items[1].type_category == "Sub-task"
    assert items[1].parent_external_id == "JCP-1"
    assert items[2].type_category == "Story"
    assert transport.calls == 2
    assert "project = \"JCP\"" in transport.seen_jql[0]


def test_unsupported_type_is_filtered_out_unless_mapped() -> None:
    transport = _FakeTransport(pages=[{"issues": [_issue("JCP-9", "Custom Type")], "total": 1}])
    config = JiraMcpAdapterConfig(
        base_url="https://example.atlassian.net",
        deployment_type="cloud",
        auth=AuthConfig(mode="api_token", email="dev@example.com", api_token="secret"),
    )
    adapter = JiraMcpAdapter(config, transport)

    items = adapter.fetch_work_items(WorkItemFilters(project="JCP"))

    assert len(items) == 1
    assert items[0].type_category == "Task"
