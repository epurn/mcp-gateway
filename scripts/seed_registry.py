"""Production tool registry seeding script.

This script populates the tool registry with calculator tools and generates
embeddings for RAG-based search. Run this after database migrations.

Usage:
    docker compose exec gateway python scripts/seed_registry.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import AsyncSessionLocal
from src.registry.models import Tool, RiskLevel
from src.registry.embedding import generate_embedding
from src.registry.repository import get_tool_by_name
from sqlalchemy import select


CALCULATOR_TOOLS = [
    {
        "name": "exact_calculate",
        "description": "Perform exact arithmetic operations (add, subtract, multiply, divide) with configurable precision on decimal numbers",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math", "arithmetic"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "operator": {
                    "type": "string",
                    "enum": ["add", "sub", "mul", "div"],
                    "description": "Arithmetic operation to perform"
                },
                "operands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Decimal numbers as strings"
                },
                "precision": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Significant digits (default: 28)"
                }
            },
            "required": ["operator", "operands"]
        }
    },
    {
        "name": "exact_statistics",
        "description": "Calculate exact statistics including mean, median, variance, standard deviation, min, max, sum, and count over decimal values",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Decimal numbers as strings"
                },
                "operations": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mean", "median", "variance", "std", "min", "max", "sum", "count"]},
                    "description": "Statistics to calculate"
                },
                "precision": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Significant digits (default: 28)"
                }
            },
            "required": ["values"]
        }
    },
    {
        "name": "exact_convert_units",
        "description": "Convert values between compatible units - length (m/cm/mm/km/in/ft/yd/mi), mass (g/kg/mg/lb), time (s/min/h/day) with exact precision",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "description": "Decimal value to convert"},
                "from_unit": {"type": "string", "description": "Source unit (e.g., 'm', 'kg', 's')"},
                "to_unit": {"type": "string", "description": "Target unit (e.g., 'ft', 'lb', 'min')"},
                "precision": {"type": "integer", "minimum": 1, "maximum": 100}
            },
            "required": ["value", "from_unit", "to_unit"]
        }
    },
    {
        "name": "exact_unit_arithmetic",
        "description": "Perform arithmetic operations on values with units, handling dimension checking automatically (e.g., 2m + 3ft = 2.9144m)",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "operands": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "unit": {"type": "string"}
                        },
                        "required": ["value", "unit"]
                    },
                    "description": "Values with units"
                },
                "operator": {"type": "string", "enum": ["add", "sub"], "description": "Operation (add/sub only for compatible units)"},
                "output_unit": {"type": "string", "description": "Desired output unit"},
                "precision": {"type": "integer", "minimum": 1, "maximum": 100}
            },
            "required": ["operands", "operator"]
        }
    },
]

CORE_TOOLS = [
    {
        "name": "find_tools",
        "description": (
            "Search for available tools by describing what you want to do. "
            "Use this when you need a tool that isn't in your current list. "
            "Examples: 'generate PDF document', 'calculate statistics', 'convert units'. "
            "Returns tool schemas you can use immediately."
        ),
        "backend_url": "internal://find_tools",  # Handled internally, not proxied
        "categories": ["core"],
        "risk_level": "low",
        "input_schema": {
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
    },
    {
        "name": "call_tool",
        "description": (
            "Invoke a discovered tool by name with the specified arguments. "
            "Use find_tools() first to discover available tools and their schemas, "
            "then use this to call them. Example: call_tool(name='exact_calculate', "
            "arguments={'operator': 'mul', 'operands': ['100', '0.5']})"
        ),
        "backend_url": "internal://call_tool",  # Handled internally
        "categories": ["core"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the tool to invoke (from find_tools results)"
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the tool (see inputSchema from find_tools)",
                    "additionalProperties": True
                }
            },
            "required": ["name", "arguments"]
        }
    },
]

# Non-core tools (discoverable via find_tools)
OTHER_TOOLS = [
    {
        "name": "git_readonly",
        "description": "Read-only Git operations including history, diff, blame, and search across repositories",
        "backend_url": "http://gateway:8000/tools/git",  # Placeholder
        "categories": ["git", "vcs"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["log", "diff", "blame", "search"],
                    "description": "Git operation to perform"
                },
                "path": {"type": "string", "description": "Repository path"},
                "ref": {"type": "string", "description": "Git reference (branch, tag, commit)"}
            },
            "required": ["operation", "path"]
        }
    },
    {
        "name": "document_generate",
        "description": "Generate professional documents in PDF or DOCX format with deterministic rendering",
        "backend_url": "http://document_generator:8000/mcp",
        "categories": ["documents", "pdf"],
        "risk_level": "low",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown content to convert"},
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html"],
                    "description": "Output document format"
                },
                "title": {"type": "string", "description": "Optional document title"}
            },
            "required": ["content", "format"]
        }
    },
]


async def seed_tools():
    """Seed the tool registry with production tools."""
    async with AsyncSessionLocal() as db:
        all_tools = CALCULATOR_TOOLS + CORE_TOOLS + OTHER_TOOLS
        
        created_count = 0
        updated_count = 0
        
        for tool_def in all_tools:
            print(f"Processing: {tool_def['name']}")
            
            # Check if tool exists
            existing = await get_tool_by_name(db, tool_def["name"])
            
            # Generate embedding
            try:
                embedding = await generate_embedding(tool_def["description"])
            except RuntimeError as e:
                print(f"Warning: Could not generate embedding for {tool_def['name']}: {e}")
                embedding = None
            
            if existing:
                # Update existing tool
                existing.description = tool_def["description"]
                existing.backend_url = tool_def["backend_url"]
                existing.categories = tool_def["categories"]
                existing.risk_level = RiskLevel(tool_def["risk_level"])
                existing.embedding = embedding
                existing.input_schema = tool_def.get("input_schema")  # Add input_schema
                existing.is_active = True
                updated_count += 1
                print(f"  ✓ Updated {tool_def['name']}")
            else:
                # Create new tool
                tool = Tool(
                    name=tool_def["name"],
                    description=tool_def["description"],
                    backend_url=tool_def["backend_url"],
                    categories=tool_def["categories"],
                    risk_level=RiskLevel(tool_def["risk_level"]),
                    embedding=embedding,
                    input_schema=tool_def.get("input_schema"),  # Add input_schema
                    is_active=True,
                )
                db.add(tool)
                created_count += 1
                print(f"  ✓ Created {tool_def['name']}")
        
        await db.commit()
        
        print(f"\n✅ Seeding complete!")
        print(f"   Created: {created_count}")
        print(f"   Updated: {updated_count}")
        print(f"   Total: {len(all_tools)}")


if __name__ == "__main__":
    print("🌱 Seeding tool registry...\n")
    asyncio.run(seed_tools())
