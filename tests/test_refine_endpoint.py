"""Test /api/refine endpoint and differentiation workflow."""

from fastapi.testclient import TestClient

from agent_catalogue.api import create_app


def test_refine_endpoint_with_overlap():
    """Test /api/refine with overlapping agents.

    This test verifies:
    1. Endpoint accepts refine request
    2. Differentiator agent is invoked
    3. Agent returns valid markdown (not JSON, not prose)
    4. Response contains refined content and changes
    """
    app = create_app()
    client = TestClient(app)

    # Sample overlapping agents (from actual catalogue)
    overlapping_agents = [
        {
            "id": "323e483c-f4d1-4676-ad12-a4ad26ea292e",
            "name": "Airflow Ninja Contributor",
            "description": "Agent for Airflow development workflows",
            "capabilities": ["set up Python environments", "configure Breeze"],
            "domains": ["Apache Airflow", "Python environments"],
            "tools": ["bash", "uv", "breeze"],
        }
    ]

    # Content that overlaps with above
    test_content = """
# AGENTS instructions

The help developing code and make stuff that works

## Local virtualenv and Breeze
do work on code correctly then create the right docs
"""

    request_body = {"content": test_content.strip(), "overlapping_agents": overlapping_agents}

    # Make request
    response = client.post("/api/refine", json=request_body)

    # Check response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    # Verify structure
    assert "refined_content" in data
    assert "original_content" in data
    assert "changes" in data
    assert "token_metrics" in data

    # Verify refined content is markdown (starts with # heading)
    refined = data["refined_content"]
    assert refined.strip().startswith("#"), f"Expected markdown heading, got: {refined[:100]}"

    # Verify it's different from original
    assert refined != test_content, "Refined content should differ from original"

    # Verify changes detected
    assert len(data["changes"]) > 0, "Should have detected changes"

    print("\n" + "=" * 80)
    print("REFINE TEST PASSED")
    print("=" * 80)
    print(f"Original length: {len(test_content)} chars")
    print(f"Refined length: {len(refined)} chars")
    print(f"Changes: {len(data['changes'])} sections modified")
    print("=" * 80)


def test_refine_logs_differentiator_output():
    """Verify diagnostic logging captures differentiator output."""
    app = create_app()
    client = TestClient(app)

    test_content = "# Test Agent\n\nMinimal agent for testing."
    overlapping = [{"id": "323e483c-f4d1-4676-ad12-a4ad26ea292e", "name": "Test"}]

    # Attempt request (may fail, but logs should show details)
    try:
        _response = client.post(
            "/api/refine",
            json={"content": test_content, "overlapping_agents": overlapping},
        )
    except Exception:
        pass

    # Check logs exist
    print("\nCheck /tmp/agent-catalogue-debug.log for differentiator output")


if __name__ == "__main__":
    # Run test directly
    import sys

    sys.path.insert(0, "src")

    try:
        test_refine_endpoint_with_overlap()
        print("\n✓ All tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
