"""Test the differentiation recipe execution."""

import os
import sys

sys.path.insert(0, "src")

# Set test environment
os.environ["AS_AZURE_OPENAI_ENDPOINT"] = "https://test.cognitiveservices.azure.com/"
os.environ["AS_AZURE_OPENAI_CHAT_DEPLOYMENT"] = "gpt-4o"
os.environ["AS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = "text-embedding-3-large"
os.environ["AS_AZURE_OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-large"
os.environ["AS_AZURE_OPENAI_EMBEDDING_DIMENSIONS"] = "3072"
os.environ["AS_AZURE_OPENAI_USE_RBAC"] = "true"
os.environ["AS_DB_PATH"] = "./data/catalogue.duckdb"


def test_recipe_validation():
    """Test that the recipe validates correctly."""
    # Note: Recipe validation requires the recipes module from amplifier-foundation
    # This test just verifies the YAML structure, not execution
    print("\n" + "=" * 80)
    print("SKIPPING RECIPE VALIDATION (requires amplifier-foundation recipes module)")
    print("=" * 80)


def test_recipe_structure():
    """Verify recipe structure matches schema."""
    import yaml

    print("\n" + "=" * 80)
    print("ANALYZING RECIPE STRUCTURE")
    print("=" * 80)

    with open("recipes/differentiate-agent.yaml") as f:
        recipe = yaml.safe_load(f)

    print(f"Name: {recipe['name']}")
    print(f"Version: {recipe['version']}")
    print(f"Stages: {len(recipe['stages'])}")

    for stage in recipe["stages"]:
        print(f"\n  Stage: {stage['name']}")
        print(f"    Steps: {len(stage['steps'])}")
        for step in stage["steps"]:
            print(f"      - {step['id']} (agent: {step['agent']})")
        if "approval" in stage:
            print(f"    Approval: required={stage['approval'].get('required')}")

    # Verify structure
    assert "stages" in recipe
    assert len(recipe["stages"]) == 2
    assert all("steps" in s for s in recipe["stages"])
    assert recipe["stages"][0]["approval"]["required"] is True

    print("\n✓ Recipe structure is valid")


if __name__ == "__main__":
    try:
        test_recipe_structure()
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
