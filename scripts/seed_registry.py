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
        "categories": ["math", "core"],
        "risk_level": "low",
    },
    {
        "name": "exact_statistics",
        "description": "Calculate exact statistics including mean, median, variance, standard deviation, min, max, sum, and count over decimal values",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
    },
    {
        "name": "exact_convert_units",
        "description": "Convert values between compatible units - length (m/cm/mm/km/in/ft/yd/mi), mass (g/kg/mg/lb), time (s/min/h/day) with exact precision",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
    },
    {
        "name": "exact_unit_arithmetic",
        "description": "Perform arithmetic operations on values with units, handling dimension checking automatically (e.g., 2m + 3ft = 2.9144m)",
        "backend_url": "http://calculator:8000/mcp",
        "categories": ["math"],
        "risk_level": "low",
    },
]

CORE_TOOLS = [
    {
        "name": "git_readonly",
        "description": "Read-only Git operations including history, diff, blame, and search across repositories",
        "backend_url": "http://gateway:8000/tools/git",  # Placeholder
        "categories": ["core"],
        "risk_level": "low",
    },
    {
        "name": "document_generate",
        "description": "Generate professional documents in PDF or DOCX format with deterministic rendering",
        "backend_url": "http://gateway:8000/tools/document",  # Placeholder
        "categories": ["core"],
        "risk_level": "low",
    },
]


async def seed_tools():
    """Seed the tool registry with production tools."""
    async with AsyncSessionLocal() as db:
        all_tools = CALCULATOR_TOOLS + CORE_TOOLS
        
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
