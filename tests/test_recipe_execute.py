"""Test recipe execution endpoints with live server."""


import requests

SERVER_URL = "http://127.0.0.1:8000"


def test_recipe_start():
    """Test starting the differentiation recipe."""

    print("\n" + "=" * 80)
    print("TESTING RECIPE EXECUTION: differentiate-agent.yaml")
    print("=" * 80)

    # Simple overlapping agent content
    content = """# Code Helper

An agent that helps with code development and testing.

## What I Do
- Write code
- Run tests  
- Set up environments
"""

    request_body = {
        "recipe_path": "recipes/differentiate-agent.yaml",
        "context": {
            "content": content,
            "overlapping_agent_ids": ["323e483c-f4d1-4676-ad12-a4ad26ea292e"],
            "attempt_number": 1,
        },
    }

    print(f"\nStarting recipe: {request_body['recipe_path']}")
    print(f"Context keys: {list(request_body['context'].keys())}")
    print(f"Content preview: {content[:100]}...")
    print()

    try:
        response = requests.post(
            f"{SERVER_URL}/api/recipe/start",
            json=request_body,
            timeout=180,  # Recipe execution can take a while
        )

        print(f"Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("\n✓ Recipe execution response received!")
            print(f"  Status: {data.get('status')}")
            print(f"  Session ID: {data.get('session_id', 'N/A')[:16]}...")

            if data.get("status") == "paused":
                print(f"  Stage requiring approval: {data.get('stage_name')}")
                print("  Approval prompt preview:")
                approval_text = data.get("approval_prompt", "")
                print(f"    {approval_text[:300]}...")
                print()
                print("  ✓ Approval gate working - recipe paused for user decision")

            elif data.get("status") == "completed":
                print("  ✓ Recipe completed without approval gates")
                summary = data.get("summary", {})
                print(f"  Summary keys: {list(summary.keys())}")

            return data
        else:
            print(f"\n✗ Request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.Timeout:
        print("\n✗ Request timed out (>180s)")
        return None
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_recipe_list():
    """Test listing active recipe sessions."""
    print("\n" + "=" * 80)
    print("TESTING RECIPE SESSION LISTING")
    print("=" * 80)

    response = requests.post(
        f"{SERVER_URL}/api/recipe/list", json={"operation": "list"}, timeout=10
    )

    print(f"Response status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        sessions = data.get("sessions", [])
        print(f"\n✓ Found {len(sessions)} active recipe sessions")
        for sess in sessions:
            print(f"  - {sess.get('session_id', 'unknown')[:16]}... : {sess.get('recipe_name')}")
    else:
        print(f"✗ Failed: {response.text}")


if __name__ == "__main__":
    import sys

    # Verify server is running
    try:
        response = requests.get(f"{SERVER_URL}/api/agents", timeout=5)
        if response.status_code != 200:
            print("✗ Server not ready")
            sys.exit(1)
        print(f"✓ Server running ({len(response.json())} agents)")
    except Exception:
        print("✗ Server not accessible at", SERVER_URL)
        sys.exit(1)

    # Test recipe execution
    result = test_recipe_start()

    # Test session listing
    test_recipe_list()

    if result and result.get("status") in ["paused", "completed"]:
        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED - Recipe system is working!")
        print("=" * 80)
    else:
        print("\n✗ Tests incomplete or failed")
        sys.exit(1)
