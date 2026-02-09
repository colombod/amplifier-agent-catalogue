#!/usr/bin/env python3
"""Test pattern buttons work after fixes."""
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def test_patterns():
    """Test both pattern buttons with proper recipe path."""
    
    async with async_playwright() as p:
        print("🌐 Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        errors = []
        page.on("console", lambda msg: print(f"  [{msg.type}] {msg.text}") if msg.type in ["error", "log"] and "API" in msg.text else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        
        print("\n📄 Loading upload page...")
        await page.goto("http://127.0.0.1:8000/upload", timeout=15000)
        await page.wait_for_timeout(2000)
        
        if errors:
            print(f"❌ Page errors: {errors}")
            return False
        
        print("✅ Page loaded\n")
        
        # Check what recipe_path the code is actually sending
        print("🔍 Checking JavaScript code for recipe_path...")
        
        # Execute JavaScript to check the actual code
        result = await page.evaluate("""
            async () => {
                // Import the API module
                const module = await import('/static/js/api/analysis-api.js');
                const api = new module.AnalysisAPI();
                
                // Mock fetch to capture the request
                const originalFetch = window.fetch;
                let capturedRequest = null;
                
                window.fetch = async (url, options) => {
                    if (url.includes('recipe/start')) {
                        capturedRequest = {
                            url,
                            body: JSON.parse(options.body)
                        };
                        // Return fake success
                        return {
                            ok: true,
                            json: async () => ({ session_id: 'test-123', status: 'running' })
                        };
                    }
                    if (url.includes('refine')) {
                        capturedRequest = {
                            url,
                            body: JSON.parse(options.body)
                        };
                        return {
                            ok: true,
                            json: async () => ({ refined_content: 'test', changes: [] })
                        };
                    }
                    return originalFetch(url, options);
                };
                
                // Test Pattern 1 (refine)
                try {
                    await api.refine('test content', [{id: 'test', name: 'Test', similarity_score: 0.79}]);
                    const pattern1 = capturedRequest;
                    capturedRequest = null;
                    
                    // Test Pattern 2 (recipe)
                    await api.startRecipe('test content', [{id: 'test', name: 'Test', similarity_score: 0.79}]);
                    const pattern2 = capturedRequest;
                    
                    window.fetch = originalFetch;
                    
                    return {
                        pattern1: pattern1.body,
                        pattern2: pattern2.body
                    };
                } catch (error) {
                    return { error: error.message };
                }
            }
        """)
        
        print("\n📦 Pattern 1 (refine) payload:")
        print(f"   {result.get('pattern1', 'ERROR')}")
        
        print("\n📦 Pattern 2 (startRecipe) payload:")
        print(f"   {result.get('pattern2', 'ERROR')}")
        
        # Check for correct field names
        pattern1 = result.get('pattern1', {})
        pattern2 = result.get('pattern2', {})
        
        checks = []
        
        if 'overlapping_agents' in pattern1:
            checks.append("✅ Pattern 1 uses 'overlapping_agents' (correct)")
        else:
            checks.append("❌ Pattern 1 missing 'overlapping_agents'")
        
        if 'recipe_path' in pattern2:
            recipe_path = pattern2['recipe_path']
            if 'recipes/' in recipe_path and '.yaml' in recipe_path:
                checks.append(f"✅ Pattern 2 uses full recipe path: '{recipe_path}'")
            else:
                checks.append(f"⚠️ Pattern 2 recipe_path: '{recipe_path}' (may be incomplete)")
        else:
            checks.append("❌ Pattern 2 missing 'recipe_path'")
        
        if 'overlapping_agents' in pattern2.get('context', {}):
            checks.append("✅ Pattern 2 context uses 'overlapping_agents' (correct)")
        else:
            checks.append("❌ Pattern 2 context missing 'overlapping_agents'")
        
        print("\n" + "="*70)
        print("VALIDATION RESULTS")
        print("="*70)
        for check in checks:
            print(check)
        
        all_passed = all("✅" in c for c in checks)
        
        await browser.close()
        
        return all_passed

if __name__ == "__main__":
    try:
        passed = asyncio.run(test_patterns())
        print("\n" + "="*70)
        if passed:
            print("🎉 ALL CHECKS PASSED - Pattern buttons should work")
        else:
            print("❌ VALIDATION FAILED - See issues above")
        print("="*70)
        sys.exit(0 if passed else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
