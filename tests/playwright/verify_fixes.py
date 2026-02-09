#!/usr/bin/env python3
"""Verify Pattern button fixes by making actual API calls."""
import requests
import json

print("="*70)
print("VERIFYING PATTERN BUTTON FIXES")
print("="*70)

# Test Pattern 1 (Quick Refinement)
print("\n🧪 Testing Pattern 1 (Quick Refinement)...")
pattern1_payload = {
    "content": "test content",
    "overlapping_agents": [
        {"id": "test-id", "name": "Test Agent", "similarity_score": 0.79}
    ]
}
print(f"   Payload: overlapping_agents (correct field name)")

try:
    r1 = requests.post("http://127.0.0.1:8000/api/refine", json=pattern1_payload, timeout=10)
    print(f"   Status: {r1.status_code}")
    if r1.status_code == 200:
        print("   ✅ Pattern 1 WORKS")
    else:
        print(f"   ❌ Pattern 1 FAILED: {r1.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

# Test Pattern 2 (Strategic Differentiation)
print("\n🧪 Testing Pattern 2 (Strategic Differentiation)...")
pattern2_payload = {
    "recipe_path": "recipes/differentiate-agent.yaml",  # Full path
    "context": {
        "content": "test content",
        "overlapping_agents": [
            {"id": "test-id", "name": "Test Agent", "similarity_score": 0.79}
        ]
    }
}
print(f"   Payload: recipe_path='{pattern2_payload['recipe_path']}'")

try:
    r2 = requests.post("http://127.0.0.1:8000/api/recipe/start", json=pattern2_payload, timeout=10)
    print(f"   Status: {r2.status_code}")
    if r2.status_code in [200, 201]:
        print("   ✅ Pattern 2 WORKS")
        result = r2.json()
        print(f"   Session ID: {result.get('session_id', 'N/A')}")
    else:
        print(f"   ❌ Pattern 2 FAILED: {r2.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

print("\n" + "="*70)
print("VERIFICATION COMPLETE")
print("="*70)
