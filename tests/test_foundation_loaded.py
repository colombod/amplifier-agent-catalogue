"""Test that foundation bundle loads and recipes tool is available."""

import asyncio
import sys

sys.path.insert(0, "src")

from agent_catalogue.api import create_app


async def test_foundation_bundle_loaded():
    """Verify foundation bundle loaded and recipes tool is mounted."""

    print("\n" + "=" * 80)
    print("TESTING FOUNDATION BUNDLE INTEGRATION")
    print("=" * 80)

    app = create_app()

    # Manually trigger lifespan startup to initialize session_mgr
    print("\nInitializing app (triggering lifespan startup)...")
    async with app.router.lifespan_context(app):
        # Now session_mgr should be available
        session_mgr = app.state.session_mgr

        print("✓ SessionManager initialized")

        # Create a test session to check what's mounted
        print("\nCreating test session from recipes bundle...")
        session = await session_mgr.create_recipe_session()

        try:
            tools = session.coordinator.mount_points.get("tools", {})
            print(f"\nMounted tools: {list(tools.keys())}")

            if "recipes" in tools:
                print("✓ recipes tool is mounted!")
                recipes_tool = tools["recipes"]
                print(f"  Tool type: {type(recipes_tool).__name__}")
                print(f"  Has execute: {hasattr(recipes_tool, 'execute')}")

                # Test list operation
                try:
                    result = await recipes_tool.execute({"operation": "list"})
                    print("\n✓ recipes.list() works!")
                    print(f"  Success: {result.success}")
                    if result.success:
                        print(f"  Output keys: {list(result.output.keys())}")
                except Exception as e:
                    print(f"\n✗ recipes.list() failed: {e}")

            else:
                print("✗ recipes tool NOT mounted")
                print("  Available tools:", list(tools.keys()))

        finally:
            await session.cleanup()

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_foundation_bundle_loaded())
