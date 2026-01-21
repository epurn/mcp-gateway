"""Unit tests for rate limiting module."""

import pytest
import time
from unittest.mock import patch

from src.ratelimit.limiter import (
    RateLimitConfig,
    TokenBucket,
    RateLimiter,
    check_rate_limit,
    get_rate_limiter,
)
from src.ratelimit.exceptions import RateLimitExceededError


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""
    
    def test_default_generous_limits(self):
        """Test that default limits are generous."""
        config = RateLimitConfig()
        
        assert config.requests_per_minute == 1000  # Generous!
        assert config.burst_size == 2000
    
    def test_tokens_per_second(self):
        """Test token rate calculation."""
        config = RateLimitConfig(requests_per_minute=60)
        
        assert config.tokens_per_second == 1.0
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RateLimitConfig(requests_per_minute=500, burst_size=1000)
        
        assert config.requests_per_minute == 500
        assert config.burst_size == 1000


class TestTokenBucket:
    """Tests for TokenBucket rate limiter."""
    
    def test_initial_tokens(self):
        """Test bucket starts with burst_size tokens."""
        config = RateLimitConfig(burst_size=100)
        bucket = TokenBucket(config)
        
        result = bucket.consume(1)
        
        assert result.allowed
        assert result.remaining == 99
    
    def test_consume_multiple(self):
        """Test consuming multiple requests."""
        config = RateLimitConfig(burst_size=10)
        bucket = TokenBucket(config)
        
        # Consume 5 tokens
        for _ in range(5):
            result = bucket.consume(1)
            assert result.allowed
        
        # Should have 5 remaining
        assert result.remaining == 5
    
    def test_bucket_empty(self):
        """Test that empty bucket denies requests."""
        config = RateLimitConfig(burst_size=5, requests_per_minute=60)
        bucket = TokenBucket(config)
        
        # Exhaust the bucket
        for _ in range(5):
            bucket.consume(1)
        
        # Next request should be denied
        result = bucket.consume(1)
        
        assert not result.allowed
        assert result.remaining == 0
        assert result.retry_after > 0
    
    def test_bucket_refills(self):
        """Test that bucket refills over time."""
        config = RateLimitConfig(burst_size=5, requests_per_minute=600)  # 10/sec
        bucket = TokenBucket(config)
        
        # Exhaust the bucket
        for _ in range(5):
            bucket.consume(1)
        
        # Wait a bit for refill (simulate with time patch)
        original_time = time.time
        with patch("src.ratelimit.limiter.time.time", return_value=original_time() + 1):
            result = bucket.consume(1)
        
        # Should have refilled some tokens
        # With 10 tokens/sec, after 1 second we should have ~10 tokens
        assert result.allowed


class TestRateLimiter:
    """Tests for multi-key RateLimiter."""
    
    def test_separate_keys(self):
        """Test that different keys have separate limits."""
        limiter = RateLimiter(RateLimitConfig(burst_size=5))
        
        # Exhaust key1
        for _ in range(5):
            limiter.check("key1")
        
        result1 = limiter.check("key1")
        assert not result1.allowed
        
        # key2 should still have tokens
        result2 = limiter.check("key2")
        assert result2.allowed
    
    def test_custom_config_per_check(self):
        """Test using custom config for specific checks."""
        limiter = RateLimiter(RateLimitConfig(burst_size=100))
        
        # Check with stricter config
        strict_config = RateLimitConfig(burst_size=2)
        
        limiter.check("key", strict_config)
        limiter.check("key", strict_config)
        result = limiter.check("key", strict_config)
        
        assert not result.allowed


class TestCheckRateLimit:
    """Tests for the check_rate_limit function."""
    
    def test_user_level_limit(self):
        """Test per-user rate limiting."""
        # Reset the global limiter
        import src.ratelimit.limiter as limiter_module
        limiter_module._rate_limiter = None
        
        result = check_rate_limit(user_id="test_user")
        
        assert result.allowed
        assert result.limit == 1000  # Generous default
    
    def test_tool_level_limit(self):
        """Test per-tool rate limiting."""
        # Reset the global limiter
        import src.ratelimit.limiter as limiter_module
        limiter_module._rate_limiter = None
        
        result = check_rate_limit(user_id="test_user", tool_name="read_file")
        
        assert result.allowed
        assert result.limit == 100  # Tool-level limit


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError exception."""
    
    def test_exception_attributes(self):
        """Test exception has correct attributes."""
        exc = RateLimitExceededError(limit=1000, retry_after=5.5)
        
        assert exc.limit == 1000
        assert exc.retry_after == 5.5
        assert "1000" in exc.message
        assert exc.code == "RATE_LIMIT_EXCEEDED"
