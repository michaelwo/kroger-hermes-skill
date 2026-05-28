"""Custom exceptions for the Kroger Shopping skill."""


class KrogerError(Exception):
    """Base exception for all Kroger-related errors."""
    pass


class KrogerAuthError(KrogerError):
    """Raised when authentication or token issues occur."""
    pass


class KrogerRateLimitError(KrogerError):
    """Raised when hitting Kroger API rate limits."""
    pass


class KrogerValidationError(KrogerError):
    """Raised when input validation fails (UPC, quantity, etc.)."""
    pass


class KrogerServerError(KrogerError):
    """Raised when Kroger returns a 5xx server error."""
    pass


class KrogerNotFoundError(KrogerError):
    """Raised when a requested resource is not found."""
    pass