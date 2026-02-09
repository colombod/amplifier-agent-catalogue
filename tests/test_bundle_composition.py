"""Unit test for bundle composition and session creation.

Tests the EXACT pattern used in SessionManager without needing LLMs or server.
"""
import asyncio
import logging
from pathlib import Path

from amplifier_core import AmplifierSession
from amplifier_foundation import Bundle, load_bundle

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_bundle_composition():
    """Test that we can create a working session from composed bundles."""
    
    print("="*70)
    print("TEST: Bundle Composition and Session Creation")
    print("="*70)
    
    # Step 1: Load @recipes bundle (like SessionManager does)
    print("\n1. Loading @recipes bundle...")
    try:
        recipes_bundle = await load_bundle(
            "git+https://github.com/microsoft/amplifier-bundle-recipes@main"
        )
        print(f"   ✅ Loaded: {recipes_bundle.name}")
        print(f"   Type: {type(recipes_bundle).__name__}")
    except Exception as e:
        print(f"   ❌ Failed to load @recipes: {e}")
        return False
    
    # Step 2: Create override bundle (like SessionManager does)
    print("\n2. Creating override bundle with providers...")
    override = Bundle(
        name="test-config",
        version="1.0.0",
        providers=[
            {
                "module": "provider-anthropic",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
                "config": {"api_key": "test-key"}
            }
        ],
        session={
            "default_provider": "provider-anthropic",
            "orchestrator": "loop-basic",  # Try explicitly specifying
        },
    )
    print(f"   ✅ Created override bundle")
    
    # Step 3: Compose (like SessionManager does)
    print("\n3. Composing recipes + override...")
    try:
        composed = recipes_bundle.compose(override)
        print(f"   ✅ Composed: {composed.name}")
        print(f"   Type: {type(composed).__name__}")
    except Exception as e:
        print(f"   ❌ Composition failed: {e}")
        return False
    
    # Step 4: Prepare (like SessionManager does)
    print("\n4. Preparing bundle (downloading modules)...")
    try:
        await composed.prepare(install_deps=True)
        print(f"   ✅ Prepared successfully")
        print(f"   Type after prepare: {type(composed).__name__}")
        
        # Inspect what attributes it has
        print(f"\n   Attributes with 'resolv' or 'source':")
        for attr in dir(composed):
            if 'resolv' in attr.lower() or 'source' in attr.lower():
                if not callable(getattr(composed, attr, None)):
                    val = getattr(composed, attr, None)
                    print(f"     {attr}: {type(val).__name__ if val else None}")
        
    except Exception as e:
        print(f"   ❌ Prepare failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 5: Get mount plan
    print("\n5. Getting mount plan...")
    try:
        mount_plan = composed.to_mount_plan()
        print(f"   ✅ Mount plan created")
        print(f"   Providers: {len(mount_plan.get('providers', []))}")
        print(f"   Tools: {len(mount_plan.get('tools', []))}")
        print(f"   Orchestrator: {mount_plan.get('orchestrator', {}).get('module', 'NONE')}")
    except Exception as e:
        print(f"   ❌ to_mount_plan failed: {e}")
        return False
    
    # Step 6: Create session
    print("\n6. Creating AmplifierSession...")
    try:
        session = AmplifierSession(
            config=mount_plan,
            session_id="test-session-123",
        )
        print(f"   ✅ Session created: {session.session_id}")
    except Exception as e:
        print(f"   ❌ Session creation failed: {e}")
        return False
    
    # Step 7: Try to mount resolver (THIS IS WHERE WE'RE STUCK)
    print("\n7. Attempting to mount source resolver...")
    
    # Check what the composed bundle actually has
    print(f"   composed has 'resolver': {hasattr(composed, 'resolver')}")
    print(f"   composed has '_resolver': {hasattr(composed, '_resolver')}")
    print(f"   composed has 'source_resolver': {hasattr(composed, 'source_resolver')}")
    
    # Try to find ANY resolver
    resolver_found = False
    for attr_name in ['resolver', '_resolver', 'source_resolver', '_source_resolver']:
        if hasattr(composed, attr_name):
            resolver = getattr(composed, attr_name)
            print(f"   Found: {attr_name} = {type(resolver).__name__}")
            try:
                await session.coordinator.mount("module-source-resolver", resolver)
                print(f"   ✅ Mounted {attr_name} to session")
                resolver_found = True
                break
            except Exception as e:
                print(f"   ❌ Failed to mount {attr_name}: {e}")
    
    if not resolver_found:
        print(f"   ❌ NO RESOLVER FOUND on composed bundle")
        print(f"   This explains why loader can't find modules!")
    
    # Step 8: Try to initialize
    print("\n8. Initializing session...")
    try:
        await session.initialize()
        print(f"   ✅ Session initialized successfully!")
        return True
    except Exception as e:
        print(f"   ❌ Initialize failed: {e}")
        print(f"\n   This is expected if no resolver was mounted.")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_bundle_composition())
    
    print("\n" + "="*70)
    if success:
        print("✅ TEST PASSED - Bundle composition works!")
    else:
        print("❌ TEST FAILED - See errors above")
    print("="*70)
    
    exit(0 if success else 1)
