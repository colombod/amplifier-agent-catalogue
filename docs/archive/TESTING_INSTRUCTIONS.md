# Testing Instructions - After Complete Refactoring + Bug Fixes

## All Fixes Committed (8 commits)

```
36c3867 - Fix recipe path: 'recipes/differentiate-agent.yaml'
1b17d03 - Add Step 4 streaming visibility with ActivityFeed
4e6883a - Fix field names: 'overlapping_agents' not 'overlap_agents'
0d9ae02 - Fix 79% gate threshold + comprehensive logging
5a45f80 - Add missing metadata fields (autonomy, tools, behaviors, triggers)
80f7c1a - Clean up test files to tests/playwright/
ea3e82f - Fix classifier load_skill error
15a588d - Fix file upload dialog click handler
```

## What Was Fixed

1. ✅ File upload dialog opens
2. ✅ Classifier no longer calls load_skill (was failing)
3. ✅ 79% overlap correctly shows early differentiation gate
4. ✅ Pattern 1 (Quick Refinement) uses correct field: `overlapping_agents`
5. ✅ Pattern 2 (Strategic Analysis) uses correct path: `recipes/differentiate-agent.yaml`
6. ✅ Step 4 now shows streaming activity feed (was silent spinner)
7. ✅ Comprehensive logging in ALL JavaScript modules

## Test Now

**HARD REFRESH:** Ctrl+Shift+R (Cmd+Shift+R on Mac)

**Test Flow:**
1. Upload `test_agents/csv-dsl-development-assistant.md`
2. Click "Analyze File →"
3. Wait for analysis to complete
4. **Verify:** Early differentiation gate appears (79% overlap)
5. **Test Pattern 1:** Click "Quick Refinement →"
   - Watch console for `[API] refine() called ... → [API] refine() success`
   - Should proceed to Step 4
6. **OR Test Pattern 2:** Click "Strategic Analysis →"
   - Watch console for `[API] startRecipe() called ... → [API] startRecipe() success`
   - Should start recipe and poll for completion

**PASTE COMPLETE CONSOLE LOGS** from clicking EITHER button so I can verify the fix worked.

## Expected Console Output

### Pattern 1 Success:
```
[API] refine() called {url: '/api/refine', ...}
[SSE] phase ...
[SSE] tool:pre ...
[API] refine() success {hasRefinedContent: true}
[Step] Setting step 4 to state: active
```

### Pattern 2 Success:
```
[API] startRecipe() called {recipePath: 'recipes/differentiate-agent.yaml', ...}
[API] startRecipe() success {sessionId: '...', status: 'running'}
```

All fixes are deployed. Server needs to be restarted with latest code.
