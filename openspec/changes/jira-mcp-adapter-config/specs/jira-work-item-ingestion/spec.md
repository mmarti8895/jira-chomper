## ADDED Requirements

### Requirement: Ingestion SHALL retrieve Jira work items by supported types
The system SHALL retrieve Jira work items of types Epic, Story, Bug, Task, and Sub-task using Jira query endpoints through MCP. The ingestion flow SHALL ignore unsupported issue types unless explicitly mapped by configuration.

#### Scenario: Mixed Jira issues include supported and unsupported types
- **WHEN** a query result contains supported and unsupported issue types
- **THEN** only supported or explicitly mapped types are returned in normalized output

#### Scenario: No supported issue types returned
- **WHEN** Jira responds with issues that do not match supported or mapped types
- **THEN** ingestion returns an empty normalized list without failing the request

### Requirement: Ingestion SHALL support deterministic filtering and pagination
The system SHALL support filtering by project, board (if available), status, assignee, labels, and updated-since timestamp. The system SHALL apply deterministic pagination until configured limits are reached or result pages are exhausted.

#### Scenario: Filtered query returns only matching items
- **WHEN** ingestion is called with project and status filters
- **THEN** normalized results contain only items matching those filter constraints

#### Scenario: Multi-page results are fully traversed within limits
- **WHEN** Jira query results span multiple pages within configured max pages
- **THEN** ingestion retrieves and returns normalized items from each traversed page

### Requirement: Ingestion SHALL normalize output into a stable internal model
The system SHALL return each work item with stable fields including external ID, type category, title/summary, status, assignee, parent linkage (for sub-tasks), and source timestamps. The normalization SHALL preserve source references needed for traceability.

#### Scenario: Sub-task includes parent linkage
- **WHEN** a Jira sub-task is normalized
- **THEN** the normalized output includes a parent reference to the related Jira issue

#### Scenario: Epic is normalized with traceability metadata
- **WHEN** a Jira Epic is normalized
- **THEN** the output includes external ID, normalized type, and source metadata for auditability

### Requirement: Ingestion SHALL handle rate limits and transient failures safely
The system SHALL apply exponential backoff retries for transient HTTP errors and Jira rate-limit responses. The system SHALL return a structured error when retry budget is exhausted.

#### Scenario: Rate-limit response is retried
- **WHEN** Jira returns a rate-limit response during ingestion
- **THEN** the system retries with exponential backoff until success or max attempts reached

#### Scenario: Retry budget exhausted
- **WHEN** transient failures persist beyond configured max attempts
- **THEN** ingestion returns a structured failure including failure class, attempts made, and last response context
