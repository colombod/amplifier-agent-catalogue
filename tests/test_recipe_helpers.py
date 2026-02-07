"""Test recipe session state management helpers."""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

# Import the helper functions we need to test
from agent_catalogue.api.routes import (
    _get_recipe_session_dir,
    _get_recipe_sessions_root,
    _list_recipe_sessions,
    _load_recipe_session_state,
)


def test_get_recipe_sessions_root():
    """Test that we can get the recipe sessions root directory."""
    print("\n" + "=" * 80)
    print("TEST: _get_recipe_sessions_root()")
    print("=" * 80)

    root = _get_recipe_sessions_root()

    print(f"\nRecipe sessions root: {root}")
    print("Expected format: ~/.amplifier/projects/{project_name}/recipe-sessions/")
    print(f"Path exists: {root.exists()}")

    assert isinstance(root, Path)
    assert "recipe-sessions" in str(root)
    assert ".amplifier/projects" in str(root)

    print("✓ Root path has correct structure")


def test_get_recipe_session_dir_missing():
    """Test that getting a missing session raises FileNotFoundError."""
    print("\n" + "=" * 80)
    print("TEST: _get_recipe_session_dir() with missing session")
    print("=" * 80)

    fake_session_id = "recipe_99999999_999999_zzzz"

    try:
        _get_recipe_session_dir(fake_session_id)
        print("✗ Should have raised FileNotFoundError")
        raise AssertionError("Expected FileNotFoundError")
    except FileNotFoundError as e:
        print(f"\n✓ Correctly raised FileNotFoundError: {e}")
        assert fake_session_id in str(e)


def test_list_recipe_sessions():
    """Test listing all recipe sessions."""
    print("\n" + "=" * 80)
    print("TEST: _list_recipe_sessions()")
    print("=" * 80)

    sessions = _list_recipe_sessions()

    print(f"\nFound {len(sessions)} recipe session(s)")

    if len(sessions) == 0:
        print("  (No sessions found - this is OK if no recipes have been run)")
    else:
        for i, session in enumerate(sessions[:5], 1):  # Show first 5
            print(f"\n  Session {i}:")
            print(f"    ID: {session.get('session_id', 'N/A')}")
            print(f"    Recipe: {session.get('recipe_name', 'N/A')}")
            print(f"    Status: {session.get('status', 'N/A')}")
            print(f"    Stage: {session.get('current_stage', 'N/A')}")

    assert isinstance(sessions, list)
    print("\n✓ List returned successfully")


def test_load_recipe_session_state_missing():
    """Test that loading a missing session state raises FileNotFoundError."""
    print("\n" + "=" * 80)
    print("TEST: _load_recipe_session_state() with missing session")
    print("=" * 80)

    fake_session_id = "recipe_99999999_999999_zzzz"

    try:
        _load_recipe_session_state(fake_session_id)
        print("✗ Should have raised FileNotFoundError")
        raise AssertionError("Expected FileNotFoundError")
    except FileNotFoundError as e:
        print(f"\n✓ Correctly raised FileNotFoundError: {e}")
        assert fake_session_id in str(e)


def test_create_and_load_mock_session():
    """Test creating a mock session and loading its state."""
    print("\n" + "=" * 80)
    print("TEST: Create mock session and load state")
    print("=" * 80)

    # Create a temporary session directory for testing
    root = _get_recipe_sessions_root()
    root.mkdir(parents=True, exist_ok=True)

    test_session_id = "recipe_test_123456_abcd"
    test_session_dir = root / test_session_id

    try:
        # Create mock session directory and state file
        test_session_dir.mkdir(parents=True, exist_ok=True)

        mock_state = {
            "status": "completed",
            "recipe_name": "test-recipe",
            "current_stage": "stage-1",
            "context": {"test_var": "test_value"},
            "created_at": "2026-02-07T20:00:00",
        }

        state_file = test_session_dir / "state.json"
        with open(state_file, "w") as f:
            json.dump(mock_state, f, indent=2)

        print(f"\n✓ Created mock session: {test_session_id}")
        print(f"  Directory: {test_session_dir}")

        # Test loading the state
        loaded_state = _load_recipe_session_state(test_session_id)

        print("\n✓ Loaded state successfully")
        print(f"  Status: {loaded_state['status']}")
        print(f"  Recipe: {loaded_state['recipe_name']}")
        print(f"  Stage: {loaded_state['current_stage']}")

        assert loaded_state["status"] == "completed"
        assert loaded_state["recipe_name"] == "test-recipe"
        assert loaded_state["context"]["test_var"] == "test_value"

        # Test listing includes our mock session
        sessions = _list_recipe_sessions()
        session_ids = [s["session_id"] for s in sessions]

        assert test_session_id in session_ids
        print(f"\n✓ Mock session appears in list (found {len(sessions)} total)")

    finally:
        # Cleanup
        if test_session_dir.exists():
            state_file = test_session_dir / "state.json"
            if state_file.exists():
                state_file.unlink()
            test_session_dir.rmdir()
            print("\n✓ Cleaned up mock session")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RECIPE HELPER FUNCTIONS TEST SUITE")
    print("=" * 80)

    try:
        test_get_recipe_sessions_root()
        test_get_recipe_session_dir_missing()
        test_list_recipe_sessions()
        test_load_recipe_session_state_missing()
        test_create_and_load_mock_session()

        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED")
        print("=" * 80)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
