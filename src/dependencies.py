"""Global dependencies for the application."""

import httpx
from fastapi import Request


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency to get the global shared HTTP client.
    
    This client is initialized in main.py lifespan and shared across requests
    to enable connection pooling (keep-alive).
    
    Args:
        request: The FastAPI request object.
        
    Returns:
        The global httpx.AsyncClient instance.
    """
    return request.app.state.http_client
