"""Jira MCP adapter configuration and read-only ingestion pipeline."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {"Epic", "Story", "Bug", "Task", "Sub-task"}


class AdapterValidationError(ValueError):
    """Raised when adapter config is invalid."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class IngestionError(RuntimeError):
    """Raised when ingestion fails after retries are exhausted."""

    def __init__(
        self,
        failure_class: str,
        message: str,
        attempts: int,
        last_status: int | None = None,
        last_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.attempts = attempts
        self.last_status = last_status
        self.last_error = last_error


class JiraMcpTransport(Protocol):
    """Transport interface that a concrete MCP Jira client must implement."""

    def search_issues(
        self,
        *,
        jql: str,
        start_at: int,
        max_results: int,
        fields: list[str],
    ) -> dict[str, Any]:
        """Return Jira search API response payload."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 3.0
    backoff_multiplier: float = 2.0
    retry_statuses: set[int] = field(default_factory=lambda: {408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class PaginationConfig:
    page_size: int = 50
    max_pages: int = 20
    max_page_size: int = 100


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    username: str | None = None
    email: str | None = None
    api_token: str | None = None
    personal_access_token: str | None = None
    bearer_token: str | None = None


@dataclass(frozen=True)
class IssueTypeMapping:
    overrides: dict[str, str] = field(default_factory=dict)
    fallback: str = "Task"

    def resolve(self, issue_type_name: str) -> str:
        mapped = self.overrides.get(issue_type_name, issue_type_name)
        if mapped in SUPPORTED_TYPES:
            return mapped
        if self.fallback in SUPPORTED_TYPES:
            return self.fallback
        return "Task"


@dataclass(frozen=True)
class JiraMcpAdapterConfig:
    base_url: str
    deployment_type: str
    auth: AuthConfig
    timeout_seconds: int = 30
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    issue_type_mapping: IssueTypeMapping = field(default_factory=IssueTypeMapping)

    @classmethod
    def from_env(cls, env_file: str = ".env", environ: dict[str, str] | None = None) -> JiraMcpAdapterConfig:
        """Build config from environment variables with optional .env support.

        Explicit environment variables override values loaded from env_file.
        """
        file_values = _load_env_file(env_file)
        merged = dict(file_values)
        merged.update(environ or dict(os.environ))

        base_url = merged.get("JIRA_BASE_URL", "").strip()
        deployment_type = merged.get("JIRA_DEPLOYMENT_TYPE", "cloud").strip()
        auth_mode = merged.get("JIRA_AUTH_MODE", "api_token").strip()

        auth = AuthConfig(
            mode=auth_mode,
            email=_get_opt(merged, "JIRA_EMAIL"),
            api_token=_get_opt(merged, "JIRA_API_TOKEN"),
            personal_access_token=_get_opt(merged, "JIRA_PAT"),
            bearer_token=_get_opt(merged, "JIRA_BEARER_TOKEN"),
        )

        return cls(
            base_url=base_url,
            deployment_type=deployment_type,
            auth=auth,
            timeout_seconds=_get_int(merged, "JIRA_TIMEOUT_SECONDS", 30),
            retry=RetryPolicy(
                max_attempts=_get_int(merged, "JIRA_RETRY_MAX_ATTEMPTS", 3),
                initial_delay_seconds=_get_float(merged, "JIRA_RETRY_INITIAL_DELAY_SECONDS", 0.25),
                max_delay_seconds=_get_float(merged, "JIRA_RETRY_MAX_DELAY_SECONDS", 3.0),
                backoff_multiplier=_get_float(merged, "JIRA_RETRY_BACKOFF_MULTIPLIER", 2.0),
                retry_statuses=_get_int_set(merged, "JIRA_RETRY_STATUSES", {408, 429, 500, 502, 503, 504}),
            ),
            pagination=PaginationConfig(
                page_size=_get_int(merged, "JIRA_PAGE_SIZE", 50),
                max_pages=_get_int(merged, "JIRA_MAX_PAGES", 20),
                max_page_size=_get_int(merged, "JIRA_MAX_PAGE_SIZE", 100),
            ),
            issue_type_mapping=IssueTypeMapping(
                fallback=_get_opt(merged, "JIRA_FALLBACK_ISSUE_TYPE") or "Task",
                overrides=_get_mapping(merged, "JIRA_ISSUE_TYPE_OVERRIDES"),
            ),
        )

    def validate(self) -> None:
        _validate_base_url(self.base_url)
        _validate_deployment(self.deployment_type)
        _validate_auth(self.auth)
        _validate_timeout(self.timeout_seconds)
        _validate_pagination(self.pagination)
        _validate_retry(self.retry)
        _validate_issue_mapping(self.issue_type_mapping)


@dataclass(frozen=True)
class WorkItemFilters:
    project: str | None = None
    board: str | None = None
    statuses: list[str] = field(default_factory=list)
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    updated_since: datetime | None = None


@dataclass(frozen=True)
class JiraWorkItem:
    external_id: str
    type_category: str
    summary: str
    status: str
    assignee: str | None
    parent_external_id: str | None
    source_updated_at: str | None
    source_created_at: str | None
    source_type_name: str
    source_url: str | None


class JiraMcpAdapter:
    """Read-only Jira ingestion adapter using an MCP-backed transport."""

    def __init__(self, config: JiraMcpAdapterConfig, transport: JiraMcpTransport) -> None:
        self.config = config
        self.transport = transport
        self.config.validate()
        logger.info("jira_adapter_initialized", extra={"deployment_type": config.deployment_type})

    def fetch_work_items(self, filters: WorkItemFilters) -> list[JiraWorkItem]:
        jql = self._build_jql(filters)
        fields = ["summary", "issuetype", "status", "assignee", "parent", "updated", "created"]
        page_size = self.config.pagination.page_size

        items: list[JiraWorkItem] = []
        start_at = 0
        page = 0
        total = None

        while page < self.config.pagination.max_pages:
            page += 1
            payload = self._with_retry(
                lambda: self.transport.search_issues(
                    jql=jql,
                    start_at=start_at,
                    max_results=page_size,
                    fields=fields,
                )
            )
            issues = payload.get("issues", [])
            total = payload.get("total", total)

            logger.info(
                "jira_page_retrieved",
                extra={
                    "page": page,
                    "start_at": start_at,
                    "page_size": page_size,
                    "received": len(issues),
                    "total": total,
                },
            )

            for issue in issues:
                normalized = self._normalize_issue(issue)
                if normalized is None:
                    continue
                items.append(normalized)

            if not issues:
                break

            start_at += len(issues)
            if total is not None and start_at >= int(total):
                break

        return items

    def _build_jql(self, filters: WorkItemFilters) -> str:
        clauses: list[str] = []

        allowed_type_names = sorted(SUPPORTED_TYPES | set(self.config.issue_type_mapping.overrides.keys()))
        quoted = ", ".join([f'"{t}"' for t in allowed_type_names])
        clauses.append(f"issuetype in ({quoted})")

        if filters.project:
            clauses.append(f'project = "{filters.project}"')
        if filters.board:
            clauses.append(f'board = "{filters.board}"')
        if filters.statuses:
            status_values = ", ".join([f'"{s}"' for s in filters.statuses])
            clauses.append(f"status in ({status_values})")
        if filters.assignee:
            clauses.append(f'assignee = "{filters.assignee}"')
        if filters.labels:
            label_values = ", ".join([f'"{l}"' for l in filters.labels])
            clauses.append(f"labels in ({label_values})")
        if filters.updated_since:
            clauses.append(f'updated >= "{filters.updated_since.strftime("%Y-%m-%d %H:%M")}"')

        return " AND ".join(clauses)

    def _with_retry(self, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        delay = self.config.retry.initial_delay_seconds
        attempts = 0
        last_error: Exception | None = None

        while attempts < self.config.retry.max_attempts:
            attempts += 1
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - transport-specific exceptions
                last_error = exc
                status = getattr(exc, "status_code", None)
                retryable = status in self.config.retry.retry_statuses or status is None

                logger.warning(
                    "jira_request_failed",
                    extra={
                        "attempt": attempts,
                        "status": status,
                        "retryable": retryable,
                        "error": str(exc),
                    },
                )

                if not retryable or attempts >= self.config.retry.max_attempts:
                    raise IngestionError(
                        failure_class="transient_failure" if retryable else "non_retryable_failure",
                        message="Jira ingestion request failed",
                        attempts=attempts,
                        last_status=status,
                        last_error=str(exc),
                    ) from exc

                time.sleep(min(delay, self.config.retry.max_delay_seconds))
                delay *= self.config.retry.backoff_multiplier

        raise IngestionError(
            failure_class="retry_exhausted",
            message="Jira ingestion request failed after retries",
            attempts=attempts,
            last_status=getattr(last_error, "status_code", None),
            last_error=str(last_error) if last_error else None,
        )

    def _normalize_issue(self, issue: dict[str, Any]) -> JiraWorkItem | None:
        fields = issue.get("fields", {})
        issue_type_name = (fields.get("issuetype") or {}).get("name", "")
        normalized_type = self.config.issue_type_mapping.resolve(issue_type_name)

        if normalized_type not in SUPPORTED_TYPES:
            return None

        assignee_obj = fields.get("assignee") or {}
        parent_obj = fields.get("parent") or {}

        return JiraWorkItem(
            external_id=issue.get("key", ""),
            type_category=normalized_type,
            summary=fields.get("summary", ""),
            status=(fields.get("status") or {}).get("name", ""),
            assignee=assignee_obj.get("displayName") or assignee_obj.get("accountId"),
            parent_external_id=parent_obj.get("key"),
            source_updated_at=fields.get("updated"),
            source_created_at=fields.get("created"),
            source_type_name=issue_type_name,
            source_url=issue.get("self"),
        )


def _validate_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AdapterValidationError(
            code="invalid_base_url",
            message="base_url must include valid http/https scheme and host",
        )


def _validate_deployment(deployment_type: str) -> None:
    if deployment_type not in {"cloud", "data-center"}:
        raise AdapterValidationError(
            code="invalid_deployment_type",
            message="deployment_type must be cloud or data-center",
        )


def _validate_auth(auth: AuthConfig) -> None:
    mode = auth.mode
    if mode not in {"api_token", "pat", "bearer"}:
        raise AdapterValidationError(code="invalid_auth_mode", message="auth.mode must be api_token, pat, or bearer")

    if mode == "api_token":
        if not auth.email or not auth.api_token:
            raise AdapterValidationError(
                code="missing_auth_fields",
                message="api_token mode requires email and api_token",
                details={"email": bool(auth.email), "api_token": bool(auth.api_token)},
            )
    elif mode == "pat" and not auth.personal_access_token:
        raise AdapterValidationError(
            code="missing_auth_fields",
            message="pat mode requires personal_access_token",
            details={"personal_access_token": bool(auth.personal_access_token)},
        )
    elif mode == "bearer" and not auth.bearer_token:
        raise AdapterValidationError(
            code="missing_auth_fields",
            message="bearer mode requires bearer_token",
            details={"bearer_token": bool(auth.bearer_token)},
        )


def _validate_timeout(timeout_seconds: int) -> None:
    if timeout_seconds <= 0 or timeout_seconds > 300:
        raise AdapterValidationError(
            code="invalid_timeout",
            message="timeout_seconds must be between 1 and 300",
        )


def _validate_pagination(pagination: PaginationConfig) -> None:
    if pagination.page_size <= 0:
        raise AdapterValidationError(code="invalid_page_size", message="page_size must be positive")
    if pagination.page_size > pagination.max_page_size:
        raise AdapterValidationError(
            code="page_size_exceeds_max",
            message="page_size exceeds max_page_size",
        )
    if pagination.max_pages <= 0:
        raise AdapterValidationError(code="invalid_max_pages", message="max_pages must be positive")


def _validate_retry(retry: RetryPolicy) -> None:
    if retry.max_attempts <= 0:
        raise AdapterValidationError(code="invalid_max_attempts", message="max_attempts must be positive")
    if retry.initial_delay_seconds <= 0:
        raise AdapterValidationError(code="invalid_initial_delay", message="initial_delay_seconds must be positive")
    if retry.max_delay_seconds < retry.initial_delay_seconds:
        raise AdapterValidationError(
            code="invalid_max_delay",
            message="max_delay_seconds must be greater than or equal to initial_delay_seconds",
        )


def _validate_issue_mapping(mapping: IssueTypeMapping) -> None:
    if mapping.fallback not in SUPPORTED_TYPES:
        raise AdapterValidationError(
            code="invalid_fallback_type",
            message="fallback must be one of Epic, Story, Bug, Task, Sub-task",
        )

    for _source, target in mapping.overrides.items():
        if target not in SUPPORTED_TYPES:
            raise AdapterValidationError(
                code="invalid_override_target",
                message="override target must be one of Epic, Story, Bug, Task, Sub-task",
            )


def _load_env_file(env_file: str) -> dict[str, str]:
    path = Path(env_file)
    if not path.exists():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            parsed[key] = value

    return parsed


def _get_opt(values: dict[str, str], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _get_int(values: dict[str, str], key: str, default: int) -> int:
    value = _get_opt(values, key)
    if value is None:
        return default
    return int(value)


def _get_float(values: dict[str, str], key: str, default: float) -> float:
    value = _get_opt(values, key)
    if value is None:
        return default
    return float(value)


def _get_int_set(values: dict[str, str], key: str, default: set[int]) -> set[int]:
    value = _get_opt(values, key)
    if value is None:
        return default
    parsed: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if token:
            parsed.add(int(token))
    return parsed if parsed else default


def _get_mapping(values: dict[str, str], key: str) -> dict[str, str]:
    value = _get_opt(values, key)
    if value is None:
        return {}

    mapping: dict[str, str] = {}
    for part in value.split(","):
        token = part.strip()
        if not token or ":" not in token:
            continue
        src, dst = token.split(":", 1)
        src = src.strip()
        dst = dst.strip()
        if src and dst:
            mapping[src] = dst
    return mapping
