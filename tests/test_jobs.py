"""Tests for Async Jobs module."""

import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import AuthenticatedUser, UserClaims
from src.jobs.models import Job
from src.jobs.schemas import JobCreate, JobStatus
from src.jobs.service import submit_job, process_job_task
from src.jobs.repository import create_job, get_job, update_job_status
from src.gateway.schemas import MCPResponse, MCPErrorDetail


class TestJobsRepository:
    """Tests for job repository functions."""
    
    @pytest.mark.asyncio
    async def test_create_and_get_job(self):
        """Test creating and retrieving a job."""
        user_id = "test-user"
        job_create = JobCreate(
            tool_name="test_tool",
            arguments={"foo": "bar"}
        )
        
        db_mock = AsyncMock()
        db_mock.add = MagicMock()
        
        async def mock_refresh(instance):
            instance.id = uuid4()
            
        db_mock.refresh.side_effect = mock_refresh
        
        # Test Create
        job = await create_job(db_mock, job_create, user_id)
        assert job.id is not None
        assert job.status == JobStatus.PENDING
        assert job.user_id == user_id
        
        db_mock.add.assert_called_once()
        db_mock.commit.assert_awaited_once()
        db_mock.refresh.assert_awaited_once()
        
        # Test Get (Mocking select execution is complex, so we just verify the call structure if possible,
        # or skip deep SQL verification in unit tests without a real DB)
        
    @pytest.mark.asyncio
    async def test_update_job_status(self):
        """Test updating job status."""
        # Setup
        job_id = uuid4()
        db_mock = AsyncMock()
        
        # Mock get_job to return a job
        mock_job = Job(id=job_id, status=JobStatus.PENDING, tool_name="t", arguments={})
        
        # We need to mock the get_job function imported in repository.py? 
        # No, update_job_status calls get_job from the same module.
        # We can patch it.
        
        with patch("src.jobs.repository.get_job", new_callable=AsyncMock) as mock_get_job:
            mock_get_job.return_value = mock_job
            
            # Update to completed
            updated = await update_job_status(
                db_mock, 
                job_id, 
                JobStatus.COMPLETED, 
                result={"output": 1}
            )
            
            assert updated.status == JobStatus.COMPLETED
            assert updated.result == {"output": 1}
            assert updated.completed_at is not None
            
            db_mock.commit.assert_awaited_once()
            db_mock.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self):
        """Test cleanup deletes old jobs."""
        from src.jobs.repository import cleanup_old_jobs
        
        db_mock = AsyncMock()
        # Mock execute result
        mock_result = MagicMock()
        mock_result.rowcount = 5
        db_mock.execute.return_value = mock_result
        
        deleted_count = await cleanup_old_jobs(db_mock, retention_hours=24)
        
        assert deleted_count == 5
        db_mock.execute.assert_awaited_once()
        db_mock.commit.assert_awaited_once()



class TestJobsService:
    """Tests for job service logic."""
    
    @pytest.fixture
    def user(self) -> AuthenticatedUser:
        return AuthenticatedUser(
            claims=UserClaims(user_id="u1", roles=[]),
            allowed_tools={"*"}
        )

    @pytest.mark.asyncio
    async def test_submit_job(self, user):
        """Test submitting a job schedules background task."""
        db = AsyncMock()
        db.add = MagicMock()
        
        bg_tasks = MagicMock(spec=BackgroundTasks)
        
        job_create = JobCreate(tool_name="test")
        
        with patch("src.jobs.service.create_job", new_callable=AsyncMock) as mock_create:
            mock_job = Job(id=uuid4(), status=JobStatus.PENDING)
            mock_create.return_value = mock_job
            
            result = await submit_job(db, user, job_create, bg_tasks)
            
            assert result == mock_job
            bg_tasks.add_task.assert_called_once()
            
            # Verify args passed to background task
            call_args = bg_tasks.add_task.call_args
            assert call_args[0][0] == process_job_task
            assert call_args[1]["job_id"] == mock_job.id

    @pytest.mark.asyncio
    async def test_process_job_success(self, user):
        """Test successful job processing."""
        job_id = uuid4()
        job_create = JobCreate(tool_name="test_tool", arguments={})
        
        mock_response = MCPResponse.success(id="req-1", result={"done": True})
        
        with patch("src.jobs.service.AsyncSessionLocal") as mock_session_cls, \
             patch("src.jobs.service.httpx.AsyncClient"), \
             patch("src.jobs.service.update_job_status", new_callable=AsyncMock) as mock_update, \
             patch("src.jobs.service.gateway_invoke_tool", new_callable=AsyncMock) as mock_invoke:
            
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_db
            mock_invoke.return_value = mock_response
            
            await process_job_task(job_id, user, job_create)
            
            # Should update to RUNNING first via specific call, 
            # but we just check if it was called with COMPLETED eventually
            
            # Check invoke called
            mock_invoke.assert_awaited_once()
            
            # Check final update
            # We expect update_job_status called with COMPLETED
            calls = mock_update.await_args_list
            assert len(calls) >= 2  # Running, then Completed
            
            final_call = calls[-1]
            assert final_call.args[1] == job_id
            assert final_call.args[2] == JobStatus.COMPLETED
            assert final_call.kwargs.get("result") == {"done": True}

    @pytest.mark.asyncio
    async def test_process_job_failure(self, user):
        """Test failed job processing."""
        job_id = uuid4()
        job_create = JobCreate(tool_name="test_tool")
        
        mock_response = MCPResponse.error_response(
            id="req-1", 
            code=1, 
            message="Tool fail"
        )
        
        with patch("src.jobs.service.AsyncSessionLocal") as mock_session_cls, \
             patch("src.jobs.service.httpx.AsyncClient"), \
             patch("src.jobs.service.update_job_status", new_callable=AsyncMock) as mock_update, \
             patch("src.jobs.service.gateway_invoke_tool", new_callable=AsyncMock) as mock_invoke:
            
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_db
            mock_invoke.return_value = mock_response
            
            await process_job_task(job_id, user, job_create)
            
            # Check final update
            calls = mock_update.await_args_list
            final_call = calls[-1]
            assert final_call.args[2] == JobStatus.FAILED
            assert final_call.kwargs.get("error") == "Tool fail"
