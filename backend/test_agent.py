# Simple test to verify the agent works
import asyncio
from agent.graph import app

async def test():
    print("Testing agent...")
    
    # Test 1: Simple chat
    result = await app.ainvoke({
        "user_message": "Hello, how are you?",
        "chat_history": [],
        "plan_log": []
    })
    print(f"\n=== Test 1: Chat ===")
    print(f"Response: {result.get('agent_response')}")
    print(f"Action: {result.get('action_taken')}")
    
    # Test 2: Ambiguous
    result2 = await app.ainvoke({
        "user_message": "check this",
        "chat_history": [],
        "plan_log": []
    })
    print(f"\n=== Test 2: Ambiguous ===")
    print(f"Response: {result2.get('agent_response')}")
    print(f"Action: {result2.get('action_taken')}")

if __name__ == "__main__":
    asyncio.run(test())
