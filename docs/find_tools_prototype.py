"""
Prototype: find_tools meta-tool for dynamic tool discovery

This implements the "core tools + find_tools" pattern where:
- tools/list returns only core tools (small, static set)
- find_tools allows LLM to discover additional tools on-demand
"""

from typing import Literal
from pydantic import BaseModel, Field


class FindToolsParams(BaseModel):
    """Parameters for find_tools."""
    query: str = Field(
        ..., 
        description="Describe what you want to do (e.g., 'generate PDF', 'calculate average')"
    )
    max_results: int = Field(
        default=5,
        description="Maximum number of tools to return"
    )


async def find_tools_handler(
    db: AsyncSession,
    user: AuthenticatedUser,
    query: str,
    max_results: int = 5
) -> dict:
    """Handle find_tools call - returns discovered tool schemas.
    
    This is the meta-tool that enables dynamic tool discovery.
    
    Args:
        db: Database session
        user: Authenticated user
        query: What the user wants to do
        max_results: Max tools to return
        
    Returns:
        Dictionary with discovered tools and their schemas
    """
    from src.registry.embedding import generate_embedding
    from src.registry.repository import search_tools_by_embedding
    
    # Use semantic search to find relevant tools
    query_embedding = await generate_embedding(query)
    tools = await search_tools_by_embedding(
        db, 
        query_embedding, 
        top_k=max_results,
        threshold=0.3
    )
    
    # Return tool schemas that LLM can understand
    discovered_tools = []
    for tool in tools:
        discovered_tools.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema or {
                "type": "object",
                "properties": {},
                "additionalProperties": True
            }
        })
    
    return {
        "query": query,
        "found": len(discovered_tools),
        "tools": discovered_tools,
        "message": f"Found {len(discovered_tools)} tools matching '{query}'. You can now use these tools directly."
    }


# Modified handle_tools_list to return core tools + find_tools
async def handle_tools_list_v2(
    db: AsyncSession,
    user: AuthenticatedUser,
    context: str | None = None
) -> MCPToolListResult:
    """Return core tools + find_tools meta-tool.
    
    This enables dynamic tool discovery while keeping initial tool list small.
    """
    # Always return core tools
    core_tools = await get_core_tools(db)
    
    # Add find_tools meta-tool
    find_tools_schema = MCPTool(
        name="find_tools",
        description=(
            "Search for available tools by describing what you want to do. "
            "Use this when you need a capability that isn't in your current tool list. "
            "Examples: 'generate PDF document', 'calculate statistics', 'convert units'. "
            "This will return tools you can use immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Describe what you want to do"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of tools to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    )
    
    # Convert core tools to MCP format
    mcp_tools = [find_tools_schema]  # find_tools first!
    for tool in core_tools:
        mcp_tools.append(MCPTool(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.input_schema or {
                "type": "object",
                "properties": {},
                "additionalProperties": True
            }
        ))
    
    return MCPToolListResult(tools=mcp_tools)


# Example conversation flow:
"""
User: "Can you generate a PDF report for me?"

LLM sees tools: [find_tools, git_readonly]
LLM thinks: "I need a PDF generation tool, let me search"

LLM → find_tools(query="generate PDF document")
Gateway → Returns: {
    "found": 1,
    "tools": [{
        "name": "document_generate",
        "description": "Generate professional documents in PDF or DOCX format...",
        "inputSchema": {...}
    }]
}

LLM thinks: "Great! Now I can use document_generate"
LLM → document_generate(content="...", format="pdf", title="Report")
Gateway → Generates PDF ✅

User gets PDF without ever knowing about the tool discovery step!
"""
