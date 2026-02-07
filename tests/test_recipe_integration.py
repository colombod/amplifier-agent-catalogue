"""Integration test for recipe execution endpoints."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_recipe_start():
    """Test starting a recipe execution."""
    from fastapi.testclient import TestClient

    from agent_catalogue.api import create_app

    # TestClient needs to use app lifespan context
    app = create_app()

    with TestClient(app) as client:
        # Test data
        request_body = {
            "recipe_path": "recipes/differentiate-agent.yaml",
            "context": {
                "content": "# Test Agent\n\nA simple test agent.",
                "overlapping_agent_ids": ["323e483c-f4d1-4676-ad12-a4ad26ea292e"],
                "attempt_number": 1,
            },
        }

    print("\n" + "=" * 80)
    print("TESTING RECIPE START ENDPOINT")
    print("=" * 80)
    print(f"Recipe: {request_body['recipe_path']}")
    print(f"Context vars: {list(request_body['context'].keys())}")

    response = client.post("/api/recipe/start", json=request_body)

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✓ Recipe started!")
        print(f"  Status: {data.get('status')}")
        print(f"  Session ID: {data.get('session_id')}")

        if data.get("status") == "paused":
            print(f"  Stage: {data.get('stage_name')}")
            print(f"  Approval prompt: {data.get('approval_prompt', '')[:200]}")

        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.json()}")
        return None


async def test_recipe_status(session_id: str):
    """Test getting recipe status."""
    from fastapi.testclient import TestClient

    from agent_catalogue.api import create_app

    app = create_app()
    client = TestClient(app)

    print("\n" + "=" * 80)
    print("TESTING RECIPE STATUS ENDPOINT")
    print("=" * 80)
    print(f"Session ID: {session_id}")

    response = client.get(f"/api/recipe/status/{session_id}")

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✓ Status retrieved!")
        print(f"  Recipe: {data.get('recipe_name')}")
        print(f"  Status: {data.get('status')}")
        print(f"  Current stage: {data.get('current_stage')}")
        print(f"  Completed steps: {data.get('completed_steps', [])}")

        if data.get("pending_approval"):
            print("\n  Pending approval:")
            print(f"    Stage: {data['pending_approval'].get('stage_name')}")

        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.json()}")
        return None


async def test_recipe_list():
    """Test listing recipe sessions."""
    from fastapi.testclient import TestClient

    from agent_catalogue.api import create_app

    app = create_app()
    client = TestClient(app)

    print("\n" + "=" * 80)
    print("TESTING RECIPE LIST ENDPOINT")
    print("=" * 80)

    response = client.get("/api/recipe/sessions")

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        sessions = data.get("sessions", [])
        print(f"\n✓ Found {len(sessions)} recipe session(s)")
        for session in sessions:
            sid = session["session_id"]
            recipe = session.get("recipe_name")
            status = session.get("status")
            print(f"  - {sid}: {recipe} ({status})")
        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.json()}")
        return None


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RECIPE INTEGRATION TEST SUITE")
    print("=" * 80)

    # Test 1: Start recipe
    start_result = asyncio.run(test_recipe_start())

    # Test 2: List sessions
    asyncio.run(test_recipe_list())

    # Test 3: Get status (if we got a session ID)
    if start_result and start_result.get("session_id"):
        asyncio.run(test_recipe_status(start_result["session_id"]))

    print("\n" + "=" * 80)
    print("Check /tmp/agent-catalogue-debug.log for detailed recipe execution logs")
    print("=" * 80)
