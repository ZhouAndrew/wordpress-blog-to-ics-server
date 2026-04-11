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
