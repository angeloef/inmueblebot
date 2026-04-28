"""
Test script to verify Gemini 2.5 Flash tool calling works.
Run: docker-compose exec app python /app/test_gemini.py
"""
import asyncio
import os
import sys

sys.path.insert(0, '/app')

from app.agents.gemini_client import test_gemini, test_gemini_no_tools
from app.agents.prompts import TOOL_DEFINITIONS
from app.core.config import get_settings


async def run_test():
    settings = get_settings()
    
    print("=" * 60)
    print("Gemini 2.5 Flash Tool Calling Test")
    print("=" * 60)
    print(f"API Key: {settings.GEMINI_API_KEY[:20]}..." if settings.GEMINI_API_KEY else "NOT SET")
    print(f"Model: {settings.GEMINI_MODEL}")
    print("=" * 60)
    
    if not settings.GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in environment")
        return False
    
    print("\n[Test 1] Testing WITHOUT tools (basic generation)...")
    result = await test_gemini_no_tools()
    
    if result.error:
        print(f"\n[BASIC] Error: {result.error}")
        print("The model may be temporarily overloaded. Try again later.")
        return False
    
    print(f"[BASIC] ✓ Response: {result.content[:150]}...")
    
    print("\n[Test 2] Testing WITH tools (tool calling)...")
    result = await test_gemini()
    
    print("\n" + "=" * 60)
    if result.has_tool_calls:
        print("SUCCESS: Tool calling works with Gemini 2.5 Flash!")
        print("=" * 60)
    else:
        print(f"FAILED: No tool calls made")
        print(f"Content: {result.content[:100] if result.content else '(empty)'}")
        print(f"Error: {result.error}")
        print("=" * 60)
    
    return result.has_tool_calls


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)