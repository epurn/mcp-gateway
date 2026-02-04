import asyncio
from src.database import AsyncSessionLocal
from src.registry.models import Tool
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tool).where(Tool.name.in_([
            "exact_calculate", 
            "exact_statistics", 
            "exact_convert_units", 
            "exact_unit_arithmetic"
        ])).order_by(Tool.name))
        
        tools = result.scalars().all()
        print("\n📊 Tool Usage Counts:")
        for tool in tools:
            print(f"  • {tool.name}: {tool.usage_count}")

if __name__ == "__main__":
    asyncio.run(check())
