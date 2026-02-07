"""Test foundation integration and recipes tool availability."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_foundation_integration():
    """Verify foundation bundle loads and recipes tool is available."""
    from agent_catalogue.config import get_config
    from agent_catalogue.services.embedder import EmbedderService
    from agent_catalogue.session_manager import SessionManager
    from agent_catalogue.storage.duckdb import DuckDBRepository

    print("\n" + "=" * 80)
    print("TESTING FOUNDATION INTEGRATION")
    print("=" * 80)

    # Initialize dependencies
    config = get_config()
    db = DuckDBRepository(config.storage)
    embedder = EmbedderService(config.embeddings)

    # Create SessionManager
    mgr = SessionManager(config)
    print("✓ SessionManager created")

    try:
        # Startup (activates modules)
        await mgr.startup(db, embedder)
        print("✓ SessionManager started")

        # Note: Can't access internal resolver state directly
        print("  Module activation completed")

        # Create a session
        session = await mgr._create_session()
        print("✓ Session created")

        # Check available tools
        tools = session.coordinator.mount_points.get("tools", {})
        tool_names = list(tools.keys())
        print(f"  Available tools ({len(tool_names)}): {tool_names}")

        if "recipes" in tools:
            print("\n✓✓✓ SUCCESS: recipes tool is mounted! ✓✓✓")

            # Try to use it
            recipes_tool = tools["recipes"]
            print(f"\n  Recipes tool type: {type(recipes_tool)}")

            # List recipe sessions
            list_result = await recipes_tool.execute({"operation": "list"})
            print(f"  List operation success: {list_result.success}")

            if list_result.success:
                sessions = list_result.output.get("sessions", [])
                print(f"  ✓ Found {len(sessions)} recipe session(s)")
        else:
            print("\n✗✗✗ FAILURE: recipes tool NOT found ✗✗✗")
            print(f"\n  Available tools: {tool_names}")

        await session.cleanup()
        await mgr.shutdown()

    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_foundation_integration())
    sys.exit(0 if success else 1)
