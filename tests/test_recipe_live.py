"""Live integration test for recipe execution (requires running server)."""

import requests

SERVER_URL = "http://127.0.0.1:8000"


def test_recipe_start():
    """Test starting a recipe execution."""
    request_body = {
        "recipe_path": "recipes/differentiate-agent.yaml",
        "context": {
            "content": "# Test Agent\n\nA simple test agent for development.",
            "overlapping_agent_ids": ["323e483c-f4d1-4676-ad12-a4ad26ea292e"],
            "attempt_number": 1,
        },
    }

    print("\n" + "=" * 80)
    print("TESTING RECIPE START ENDPOINT")
    print("=" * 80)
    print(f"Recipe: {request_body['recipe_path']}")
    print(f"Context vars: {list(request_body['context'].keys())}")

    response = requests.post(f"{SERVER_URL}/api/recipe/start", json=request_body, timeout=120)

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✓ Recipe started!")
        print(f"  Status: {data.get('status')}")
        print(f"  Session ID: {data.get('session_id')}")

        if data.get("status") == "paused":
            print(f"  Stage: {data.get('stage_name')}")
            print(f"  Approval prompt preview: {data.get('approval_prompt', '')[:200]}...")

        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_recipe_status(session_id: str):
    """Test getting recipe status."""
    print("\n" + "=" * 80)
    print("TESTING RECIPE STATUS ENDPOINT")
    print("=" * 80)
    print(f"Session ID: {session_id}")

    response = requests.get(f"{SERVER_URL}/api/recipe/status/{session_id}", timeout=10)

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✓ Status retrieved!")
        print(f"  Recipe: {data.get('recipe_name')}")
        print(f"  Status: {data.get('status')}")
        print(f"  Current stage: {data.get('current_stage')}")
        print(f"  Completed steps: {len(data.get('completed_steps', []))} steps")

        if data.get("pending_approval"):
            print("\n  Pending approval:")
            print(f"    Stage: {data['pending_approval'].get('stage_name')}")

        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_recipe_list():
    """Test listing recipe sessions."""
    print("\n" + "=" * 80)
    print("TESTING RECIPE LIST ENDPOINT")
    print("=" * 80)

    response = requests.get(f"{SERVER_URL}/api/recipe/sessions", timeout=10)

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        sessions = data.get("sessions", [])
        print(f"\n✓ Found {len(sessions)} recipe session(s)")
        for session in sessions:
            status = session.get("status", "unknown")
            recipe_name = session.get("recipe_name", "unknown")
            print(f"  - {session['session_id'][:8]}...: {recipe_name} ({status})")
        return data
    else:
        print(f"\n✗ Request failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RECIPE INTEGRATION TEST SUITE (LIVE SERVER)")
    print("=" * 80)
    print(f"Server: {SERVER_URL}")

    # Check server is running
    try:
        health = requests.get(f"{SERVER_URL}/", timeout=5)
        print(f"✓ Server responding (HTTP {health.status_code})")
    except Exception as e:
        print(f"✗ Server not reachable: {e}")
        print("\nStart the server first: agent-catalogue serve")
        exit(1)

    # Test 1: Start recipe
    start_result = test_recipe_start()

    # Test 2: List sessions
    test_recipe_list()

    # Test 3: Get status (if we got a session ID)
    if start_result and start_result.get("session_id"):
        test_recipe_status(start_result["session_id"])

    print("\n" + "=" * 80)
    print("Check /tmp/agent-catalogue-debug.log for detailed recipe execution logs")
    print("=" * 80)
