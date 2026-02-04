"""Test script to verify dynamic tool registry with document_generate."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import AsyncSessionLocal
from src.registry.repository import get_all_active_tools, search_tools_by_embedding
from src.registry.embedding import generate_embedding


async def test_registry():
    """Test that document_generate is properly registered with embeddings."""
    async with AsyncSessionLocal() as db:
        # Get all tools
        tools = await get_all_active_tools(db)
        print(f"\n📊 Total active tools in registry: {len(tools)}\n")
        
        for tool in tools:
            has_embedding = "✅" if tool.embedding is not None else "❌"
            print(f"{has_embedding} {tool.name}")
            print(f"   Description: {tool.description[:80]}...")
            print(f"   Categories: {', '.join(tool.categories)}")
            print(f"   Embedding: {'Yes' if tool.embedding is not None else 'No'}")
            print()
        
        # Test semantic search for document generation
        print("\n🔍 Testing semantic search for 'generate a PDF report'...\n")
        query_embedding = await generate_embedding("generate a PDF report")
        results = await search_tools_by_embedding(db, query_embedding, top_k=3, threshold=0.3)
        
        print(f"Top {len(results)} matches:")
        for i, tool in enumerate(results, 1):
            print(f"{i}. {tool.name}")
            print(f"   {tool.description[:80]}...")
            print()
        
        # Test semantic search for document-related queries
        test_queries = [
            "create a Word document",
            "make a PDF file",
            "generate HTML report",
            "convert markdown to PDF"
        ]
        
        print("\n🧪 Testing various document-related queries:\n")
        for query in test_queries:
            query_embedding = await generate_embedding(query)
            # Lower threshold to 0.3 for better recall
            results = await search_tools_by_embedding(db, query_embedding, top_k=1, threshold=0.3)
            if results:
                tool = results[0]
                match_icon = "✅" if tool.name == "document_generate" else "⚠️"
                print(f"{match_icon} '{query}'")
                print(f"   → {tool.name}")
            else:
                print(f"❌ '{query}' → No results")


if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Tool Registry Test")
    print("=" * 60)
    asyncio.run(test_registry())
    print("\n✅ Test complete!")
