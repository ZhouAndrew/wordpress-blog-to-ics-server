class WpLogParserError(Exception):
    """Base exception for the wp_log_parser package."""


class WPCLIUnavailableError(WpLogParserError):
    """Raised when wp-cli cannot be executed."""


class WordPressPathError(WpLogParserError):
    """Raised when a configured WordPress path is invalid."""


class AuthenticationFailedError(WpLogParserError):
    """Raised when WordPress REST auth fails."""


class PostNotFoundError(WpLogParserError):
    """Raised when a post ID cannot be found or fetched."""


class MalformedResponseError(WpLogParserError):
    """Raised when WordPress response does not match expected schema."""


class ConfigError(WpLogParserError):
    """Raised when config file content is invalid."""


NO_VALID_LOG_ENTRIES_MESSAGE = "No valid timed log entries found in post."


class NoValidLogEntriesError(RuntimeError, WpLogParserError):
    """Raised when a post contains no valid timed log entries to export."""

    def __init__(self, message: str = NO_VALID_LOG_ENTRIES_MESSAGE):
        super().__init__(message)
