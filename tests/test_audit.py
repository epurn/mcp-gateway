"""Tests for the audit logging module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.audit.schemas import (
    AuditStatus,
    AuditLogCreate,
    AuditLogResponse,
    AuditLogQuery,
)
from src.audit.models import AuditLog
from src.audit.models import AuditLog
from src.audit.logger import AuditContext, log_tool_invocation, audit_tool_invocation
from src.audit.router import require_admin
from src.auth.models import AuthenticatedUser, UserClaims
from src.auth.exceptions import AuthorizationError


class TestAuditStatus:
    """Tests for AuditStatus enum."""
    
    def test_status_values(self):
        """All expected status values exist."""
        assert AuditStatus.success == "success"
        assert AuditStatus.error == "error"
        assert AuditStatus.timeout == "timeout"
        assert AuditStatus.rate_limited == "rate_limited"


class TestAuditLogCreate:
    """Tests for AuditLogCreate schema."""
    
    def test_valid_create(self):
        """Create DTO with valid data."""
        log = AuditLogCreate(
            request_id="abc-123",
            user_id="user@example.com",
            tool_name="read_file",
            status=AuditStatus.success,
            duration_ms=150,
        )
        assert log.request_id == "abc-123"
        assert log.user_id == "user@example.com"
        assert log.tool_name == "read_file"
        assert log.status == AuditStatus.success
        assert log.duration_ms == 150
        assert log.error_code is None
    
    def test_with_error_code(self):
        """Create DTO with error code."""
        log = AuditLogCreate(
            request_id="abc-123",
            user_id="user@example.com",
            tool_name="read_file",
            status=AuditStatus.error,
            duration_ms=50,
            error_code="TOOL_NOT_FOUND",
        )
        assert log.error_code == "TOOL_NOT_FOUND"
    
    def test_negative_duration_rejected(self):
        """Negative duration is rejected."""
        with pytest.raises(ValueError):
            AuditLogCreate(
                request_id="abc-123",
                user_id="user@example.com",
                tool_name="read_file",
                status=AuditStatus.success,
                duration_ms=-1,
            )


class TestAuditLogQuery:
    """Tests for AuditLogQuery schema."""
    
    def test_defaults(self):
        """Query has sensible defaults."""
        query = AuditLogQuery()
        assert query.user_id is None
        assert query.tool_name is None
        assert query.status is None
        assert query.limit == 100
        assert query.offset == 0
    
    def test_custom_filters(self):
        """Query accepts custom filters."""
        now = datetime.now(timezone.utc)
        query = AuditLogQuery(
            user_id="admin@example.com",
            tool_name="delete_file",
            status=AuditStatus.error,
            start_time=now,
            limit=50,
            offset=10,
        )
        assert query.user_id == "admin@example.com"
        assert query.tool_name == "delete_file"
        assert query.status == AuditStatus.error
        assert query.limit == 50
        assert query.offset == 10
    
    def test_limit_bounds(self):
        """Limit must be within bounds."""
        with pytest.raises(ValueError):
            AuditLogQuery(limit=0)
        
        with pytest.raises(ValueError):
            AuditLogQuery(limit=1001)


class TestAuditContext:
    """Tests for AuditContext tracking."""
    
    def test_initial_state(self):
        """Context starts with success status."""
        ctx = AuditContext(
            request_id="req-123",
            user_id="user@example.com",
            tool_name="read_file",
        )
        assert ctx.request_id == "req-123"
        assert ctx.user_id == "user@example.com"
        assert ctx.tool_name == "read_file"
        assert ctx.status == AuditStatus.success
        assert ctx.error_code is None
    
    def test_mark_error(self):
        """Can mark context as error."""
        ctx = AuditContext("req-123", "user", "tool")
        ctx.mark_error("BACKEND_ERROR")
        assert ctx.status == AuditStatus.error
        assert ctx.error_code == "BACKEND_ERROR"
    
    def test_mark_timeout(self):
        """Can mark context as timeout."""
        ctx = AuditContext("req-123", "user", "tool")
        ctx.mark_timeout()
        assert ctx.status == AuditStatus.timeout
        assert ctx.error_code == "BACKEND_TIMEOUT"
    
    def test_mark_rate_limited(self):
        """Can mark context as rate limited."""
        ctx = AuditContext("req-123", "user", "tool")
        ctx.mark_rate_limited()
        assert ctx.status == AuditStatus.rate_limited
        assert ctx.error_code == "RATE_LIMITED"
    
    def test_duration_ms(self):
        """Duration is calculated correctly."""
        ctx = AuditContext("req-123", "user", "tool")
        # Duration should be at least 0
        assert ctx.duration_ms >= 0


class TestRequireAdmin:
    """Tests for admin role requirement."""
    
    def test_admin_allowed(self):
        """User with admin role is allowed."""
        claims = UserClaims(user_id="admin@example.com", roles=["admin", "user"])
        user = AuthenticatedUser(
            claims=claims,
            allowed_tools={"*"},
        )
        result = require_admin(user)
        assert result == user
    
    def test_non_admin_rejected(self):
        """User without admin role is rejected."""
        claims = UserClaims(user_id="user@example.com", roles=["user"])
        user = AuthenticatedUser(
            claims=claims,
            allowed_tools={"read_file"},
        )
        with pytest.raises(AuthorizationError) as exc_info:
            require_admin(user)
        assert exc_info.value.code == "admin_required"


class TestLogToolInvocation:
    """Tests for the log_tool_invocation function."""
    
    @pytest.mark.asyncio
    async def test_logs_success(self):
        """Logs successful invocation."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        ctx = AuditContext(
            request_id="req-123",
            user_id="user@example.com",
            tool_name="read_file",
        )
        
        with patch("src.audit.logger.create_audit_log", new_callable=AsyncMock) as mock_create:
            await log_tool_invocation(mock_db, ctx)
            
            mock_create.assert_called_once()
            # Called with positional args: (db, log_data)
            call_args = mock_create.call_args
            assert call_args[0][0] == mock_db
            log_data = call_args[0][1]
            assert log_data.request_id == "req-123"
            assert log_data.user_id == "user@example.com"
            assert log_data.tool_name == "read_file"
            assert log_data.status == AuditStatus.success
    
    @pytest.mark.asyncio
    async def test_logs_error(self):
        """Logs error invocation."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        ctx = AuditContext(
            request_id="req-456",
            user_id="user@example.com",
            tool_name="delete_file",
        )
        ctx.mark_error("PERMISSION_DENIED")
        
        with patch("src.audit.logger.create_audit_log", new_callable=AsyncMock) as mock_create:
            await log_tool_invocation(mock_db, ctx)
            
            # Called with positional args: (db, log_data)
            log_data = mock_create.call_args[0][1]
            assert log_data.status == AuditStatus.error
            assert log_data.error_code == "PERMISSION_DENIED"


class TestAuditLogResponse:
    """Tests for AuditLogResponse schema."""
    
    def test_from_model(self):
        """Can create response from ORM model."""
        # Create a mock model with the expected attributes
        mock_log = MagicMock()
        mock_log.id = 1
        mock_log.timestamp = datetime.now(timezone.utc)
        mock_log.request_id = "req-123"
        mock_log.user_id = "user@example.com"
        mock_log.tool_name = "read_file"
        mock_log.status = AuditStatus.success
        mock_log.duration_ms = 150
        mock_log.error_code = None
        
        response = AuditLogResponse.model_validate(mock_log)
        assert response.id == 1
        assert response.request_id == "req-123"
        assert response.status == AuditStatus.success


class TestAuditToolInvocationContext:
    """Tests for the audit_tool_invocation context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_flow_success(self):
        """Test successful flow logs success."""
        db = AsyncMock()
        
        with patch("src.audit.logger.log_tool_invocation", new_callable=AsyncMock) as mock_log:
            async with audit_tool_invocation(db, "req-1", "user", "tool") as ctx:
                assert ctx.status == AuditStatus.success
            
            # Verify log was called on exit
            mock_log.assert_awaited_once()
            args = mock_log.call_args[0]
            assert args[0] == db
            assert args[1] == ctx
            assert args[1].status == AuditStatus.success

    @pytest.mark.asyncio
    async def test_context_manager_flow_exception(self):
        """Test exception flow does NOT auto-mark error (caller must do it), 
        but still logs."""
        db = AsyncMock()
        
        with patch("src.audit.logger.log_tool_invocation", new_callable=AsyncMock) as mock_log:
            try:
                async with audit_tool_invocation(db, "req-1", "user", "tool") as ctx:
                    raise ValueError("oops")
            except ValueError:
                pass
            
            # Verify log was called on exit even after exception
            mock_log.assert_awaited_once()
            args = mock_log.call_args[0]
            assert args[1].status == AuditStatus.success 
            # Note: The context manager implementation doesn't currently catch exceptions 
            # to set status=error automatically; the service layer does that explicitly.
            # This test mainly asserts that logging happens even if exception bubbles up.

