"""
Quick test to see what tools the Gateway would expose for different queries.

This simulates what an LLM client would see when it asks for tools/list
with different conversation contexts.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import AsyncSessionLocal
from src.auth.models import AuthenticatedUser, UserClaims
from src.mcp_transport.service import handle_tools_list_smart


async def test_tool_exposure():
    """Test what tools are exposed for different contexts."""
    
    # Create a mock user with proper structure
    claims = UserClaims(
        user_id="test-user",
        roles=["developer"]
    )
    user = AuthenticatedUser(
        claims=claims,
        allowed_tools={"*"}
    )
    
    test_scenarios = [
        {
            "context": "Can you generate a PDF report for me?",
            "expected": "document_generate",
            "strategy": "hybrid"
        },
        {
            "context": "Calculate the sum of 123.45 and 678.90",
            "expected": "exact_calculate",
            "strategy": "hybrid"
        },
        {
            "context": "Convert 5 kilometers to miles",
            "expected": "exact_convert_units",
            "strategy": "hybrid"
        },
        {
            "context": "Create a Word document with my notes",
            "expected": "document_generate",
            "strategy": "hybrid"
        },
        {
            "context": None,  # No context - should return all tools
            "expected": "all",
            "strategy": "all"
        }
    ]
    
    async with AsyncSessionLocal() as db:
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{'='*60}")
            print(f"Scenario {i}: {scenario['context'] or '(No context)'}")
            print(f"Strategy: {scenario['strategy']}")
            print(f"{'='*60}")
            
            result = await handle_tools_list_smart(
                db=db,
                user=user,
                context=scenario['context'],
                strategy=scenario['strategy'],
                max_tools=15
            )
            
            print(f"\n📋 Tools exposed to LLM ({len(result.tools)} total):")
            for tool in result.tools:
                icon = "✅" if tool.name == scenario['expected'] or scenario['expected'] == "all" else "  "
                print(f"{icon} {tool.name}")
                print(f"   {tool.description[:70]}...")
            
            # Check if expected tool is present
            tool_names = [t.name for t in result.tools]
            if scenario['expected'] != "all":
                if scenario['expected'] in tool_names:
                    print(f"\n✅ SUCCESS: '{scenario['expected']}' is in the tool list")
                else:
                    print(f"\n❌ FAILURE: '{scenario['expected']}' is NOT in the tool list")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("SMART ROUTING SIMULATION")
    print("What tools would an LLM see for different queries?")
    print("="*60)
    asyncio.run(test_tool_exposure())
    print("\n✅ Simulation complete!\n")
