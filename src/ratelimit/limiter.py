"""Token bucket rate limiter with in-memory storage."""

import time
import threading
from typing import NamedTuple
from pydantic import BaseModel, Field


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting.
    
    Attributes:
        requests_per_minute: Maximum requests allowed per minute.
        burst_size: Maximum burst size (tokens available).
    """
    
    # Generous defaults as requested
    requests_per_minute: int = Field(default=1000, description="Requests per minute")
    burst_size: int = Field(default=2000, description="Max burst tokens")
    
    @property
    def tokens_per_second(self) -> float:
        """Calculate token refill rate."""
        return self.requests_per_minute / 60.0


class RateLimitResult(NamedTuple):
    """Result of a rate limit check.
    
    Attributes:
        allowed: Whether the request is allowed.
        limit: The rate limit.
        remaining: Remaining requests in window.
        reset_at: Unix timestamp when limit resets.
        retry_after: Seconds to wait if denied (0 if allowed).
    """
    
    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after: float = 0.0


class TokenBucket:
    """Thread-safe token bucket rate limiter.
    
    Tokens are added at a constant rate up to a maximum (burst_size).
    Each request consumes one token. If no tokens available, request is denied.
    """
    
    def __init__(self, config: RateLimitConfig):
        """Initialize token bucket.
        
        Args:
            config: Rate limit configuration.
        """
        self.config = config
        self.tokens = float(config.burst_size)
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(
            self.config.burst_size,
            self.tokens + elapsed * self.config.tokens_per_second
        )
        self.last_update = now
    
    def consume(self, tokens: int = 1) -> RateLimitResult:
        """Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume.
            
        Returns:
            RateLimitResult with allow/deny status and metadata.
        """
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return RateLimitResult(
                    allowed=True,
                    limit=self.config.requests_per_minute,
                    remaining=int(self.tokens),
                    reset_at=int(self.last_update + 60),
                )
            else:
                # Calculate wait time until enough tokens available
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.config.tokens_per_second
                
                return RateLimitResult(
                    allowed=False,
                    limit=self.config.requests_per_minute,
                    remaining=0,
                    reset_at=int(self.last_update + 60),
                    retry_after=wait_time,
                )


class RateLimiter:
    """Multi-key rate limiter using token buckets.
    
    Maintains separate token buckets per key (e.g., per user or per user+tool).
    Old buckets are cleaned up periodically.
    """
    
    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize rate limiter.
        
        Args:
            config: Default rate limit config. Uses generous defaults if not provided.
        """
        self.config = config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes
    
    def _cleanup_old_buckets(self) -> None:
        """Remove buckets that haven't been used recently."""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return
            
        stale_time = time.time() - 600  # 10 minutes
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if bucket.last_update < stale_time
        ]
        for key in stale_keys:
            del self._buckets[key]
        
        self._last_cleanup = time.time()
    
    def check(self, key: str, config: RateLimitConfig | None = None) -> RateLimitResult:
        """Check rate limit for a key.
        
        Args:
            key: Rate limit key (e.g., user_id or user_id:tool_name).
            config: Override config for this check.
            
        Returns:
            RateLimitResult with status and headers.
        """
        with self._lock:
            self._cleanup_old_buckets()
            
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(config or self.config)
            
            return self._buckets[key].consume()


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def check_rate_limit(
    user_id: str,
    tool_name: str | None = None,
    config: RateLimitConfig | None = None
) -> RateLimitResult:
    """Check rate limit for a user and optional tool.
    
    Args:
        user_id: User identifier.
        tool_name: Optional tool name for per-tool limits.
        config: Optional custom config.
        
    Returns:
        RateLimitResult with status and headers.
    """
    limiter = get_rate_limiter()
    
    # Check user-level limit first
    user_key = f"user:{user_id}"
    user_result = limiter.check(user_key, config)
    
    if not user_result.allowed:
        return user_result
    
    # Check per-tool limit if tool specified
    if tool_name:
        tool_config = config or RateLimitConfig(
            requests_per_minute=100,  # Lower limit per-tool
            burst_size=200
        )
        tool_key = f"user:{user_id}:tool:{tool_name}"
        return limiter.check(tool_key, tool_config)
    
    return user_result
