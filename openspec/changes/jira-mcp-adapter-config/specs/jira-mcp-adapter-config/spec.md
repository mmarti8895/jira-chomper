## ADDED Requirements

### Requirement: Adapter configuration SHALL validate Jira connectivity and authentication
The system SHALL support a Jira MCP adapter configuration that includes base URL, deployment type (cloud or data-center), authentication mode, and required credentials. The adapter SHALL validate required fields and fail initialization with a structured, redacted error when configuration is incomplete or invalid.

#### Scenario: Valid configuration initializes successfully
- **WHEN** the adapter receives a complete and valid Jira MCP configuration
- **THEN** the adapter initializes and reports a ready state for read operations

#### Scenario: Missing credential fails fast
- **WHEN** required authentication credentials are missing or empty
- **THEN** the adapter initialization fails with a structured error that does not expose secret values

### Requirement: Adapter configuration SHALL define bounded retrieval behavior
The system SHALL allow configuration of page size, maximum pages per request cycle, retry policy, and request timeout. The adapter SHALL enforce configured bounds and reject values outside allowed limits.

#### Scenario: Page size exceeds configured maximum
- **WHEN** a configured page size is greater than the allowed maximum
- **THEN** the adapter rejects configuration and returns a validation error

#### Scenario: Retry policy is applied from configuration
- **WHEN** a transient Jira API failure occurs during read operations
- **THEN** the adapter retries according to configured backoff and max-attempt values

### Requirement: Adapter configuration SHALL support issue type mapping overrides
The system SHALL support configurable mapping rules from Jira issue type names to normalized internal categories: Epic, Story, Bug, Task, and Sub-task. The adapter SHALL apply overrides before default mapping rules.

#### Scenario: Custom Jira issue type maps to Story
- **WHEN** configuration maps a custom Jira issue type name to Story
- **THEN** returned items with that issue type are normalized as Story

#### Scenario: Unmapped issue type receives fallback category
- **WHEN** a Jira issue type is not present in override or default mapping rules
- **THEN** the adapter assigns the configured fallback category and includes mapping metadata
