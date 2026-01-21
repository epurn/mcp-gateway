"""Rate limit exceptions."""

from src.auth.exceptions import MCPGatewayError


class RateLimitExceededError(MCPGatewayError):
    """Raised when a rate limit is exceeded.
    
    Attributes:
        limit: The rate limit that was exceeded.
        retry_after: Seconds until request can be retried.
    """
    
    def __init__(self, limit: int, retry_after: float):
        super().__init__(
            message=f"Rate limit exceeded ({limit} requests/min). Retry after {retry_after:.1f}s",
            code="RATE_LIMIT_EXCEEDED"
        )
        self.limit = limit
        self.retry_after = retry_after
