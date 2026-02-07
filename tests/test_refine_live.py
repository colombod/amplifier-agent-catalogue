"""Test /api/refine against running server.

Run this with server already running:
    python tests/test_refine_live.py
"""

import requests


def test_refine_endpoint():
    """Test /api/refine with real overlapping agents."""

    base_url = "http://127.0.0.1:8000"

    # Verify server is running
    try:
        resp = requests.get(f"{base_url}/api/agents", timeout=5)
        assert resp.status_code == 200, f"Server not responding: {resp.status_code}"
        agents = resp.json()
        print(f"✓ Server running with {len(agents)} agents")
    except Exception as e:
        print(f"✗ Server not running: {e}")
        print("Start server first: agent-catalogue serve")
        return False

    # Sample content that overlaps
    test_content = """
# AGENTS instructions

The help developing code and make stuff that works

## Local virtualenv and Breeze
do work on code correctly then create the right docs
"""

    # Get actual overlapping agent from catalogue
    overlapping_agents = [
        {
            "id": "323e483c-f4d1-4676-ad12-a4ad26ea292e",
            "name": "Airflow Ninja Contributor",
            "description": "Agent for Airflow development",
            "capabilities": ["set up Python environments", "configure Breeze"],
            "domains": ["Apache Airflow", "Python"],
            "tools": ["bash", "uv"],
        }
    ]

    print("\n" + "=" * 80)
    print("TESTING /api/refine ENDPOINT")
    print("=" * 80)
    print(f"Content length: {len(test_content)} chars")
    print(f"Overlapping agents: {len(overlapping_agents)}")
    print()

    # Make request
    try:
        response = requests.post(
            f"{base_url}/api/refine",
            json={"content": test_content.strip(), "overlapping_agents": overlapping_agents},
            timeout=120,  # Differentiator may take time
        )

        print(f"Response status: {response.status_code}")

        if response.status_code != 200:
            print(f"✗ Request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        data = response.json()

        # Verify structure
        assert "refined_content" in data, "Missing refined_content"
        assert "original_content" in data, "Missing original_content"
        assert "changes" in data, "Missing changes"

        refined = data["refined_content"]

        # Verify it's markdown
        assert refined.strip().startswith("#"), f"Expected markdown, got: {refined[:100]}"

        # Verify it's different
        assert refined != test_content.strip(), "Content unchanged"

        print("=" * 80)
        print("✓ TEST PASSED")
        print("=" * 80)
        print(f"Original: {len(test_content)} chars")
        print(f"Refined: {len(refined)} chars")
        print(f"Changes: {len(data['changes'])} sections")
        print()
        print("First 300 chars of refined content:")
        print(refined[:300])
        print()
        print("=" * 80)
        print("\nCheck /tmp/agent-catalogue-debug.log for full differentiator output")
        print("=" * 80)

        return True

    except requests.Timeout:
        print("✗ Request timed out (>120s)")
        print("Check /tmp/agent-catalogue-debug.log for differentiator status")
        return False
    except Exception as e:
        print(f"✗ Test error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_refine_endpoint()
    exit(0 if success else 1)
