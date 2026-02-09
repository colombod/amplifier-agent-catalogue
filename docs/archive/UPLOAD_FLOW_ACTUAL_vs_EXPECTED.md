# Upload Workflow - Actual vs Expected Flow

**Created:** 2026-02-08  
**Status:** Analysis of current bugs

---

## User's Experience (ACTUAL - BROKEN)

```
Step 1: Upload TEST_AGENT_UPLOAD.md (79% overlap) ✓
  ↓
Step 2: AI Classification completes ✓
  ↓
Step 3: Similarity Detection (79% overlap detected)
  ❌ Step 3 is COLLAPSED (should be EXPANDED to show similar agents)
  ✓ Early diff gate appears with correct percentage
  ✓ Two buttons visible and clickable
  
User clicks: "Differentiate Now"
  ↓
Step 4: SKIPPED (expected) ✓
  ↓
Step 5: Decision & Store
  ❌ Shows: "Skipped quality check to prioritize differentiation. Use one of the patterns below to reduce overlap."
  ❌ NO DIFFERENTIATION BUTTONS VISIBLE (refine-overlap-btn, strategic-diff-btn)
  ❌ Only options: "Store Without Differentiating" or "Start Over"
  ❌ Expected: Should show Pattern 1 (Refine) and Pattern 2 (Strategic Diff) buttons
```

---

## Expected Flow (CORRECT BEHAVIOR)

### Happy Path (Low Overlap <50%)
```
Upload → Analysis → No Similar Agents → Quality Check → Store
```

### Moderate Overlap Path (50-69%)
```
Upload → Analysis → Similar Agents (expanded) → Quality Check → Store
                       ↑
                     Can do Deep Compare (optional)
```

### High Overlap Path (70-84% - Early Diff Gate)
```
Upload → Analysis → Similar Agents (EXPANDED - not collapsed!)
                       ↓
                    Early Diff Gate appears:
                    ┌──────────────────────────────────────────┐
                    │ ⚠ High Overlap Detected (79%)            │
                    │                                          │
                    │ [Differentiate Now] [Continue Quality]  │
                    └──────────────────────────────────────────┘
                       ↓
              USER CHOICE:
              
   Choice A: "Differentiate Now"
   ↓
   Skip Step 4 (Quality) → Go to Step 5
   Step 5 MUST show:
   ┌─────────────────────────────────────────────────────────┐
   │ 📊 Differentiation Options                              │
   │                                                          │
   │ Pattern 1: Quick Refinement                             │
   │ [Refine to Reduce Overlap] ← MUST BE VISIBLE            │
   │ Removes overlapping capabilities (fast, ~15s)           │
   │                                                          │
   │ Pattern 2: Strategic Differentiation                    │
   │ [Strategic Differentiation] ← MUST BE VISIBLE           │
   │ Uses recipe to analyze and propose strategies           │
   │                                                          │
   │ Or:                                                      │
   │ [Store Without Differentiating] ← Secondary option      │
   │ [Cancel Upload] ← Always available                      │
   └─────────────────────────────────────────────────────────┘
   
   Choice B: "Continue to Quality Check"
   ↓
   Step 4: Quality Evaluation → Improvement → Step 5: Store
```

### Very High Overlap Path (85%+ - Duplication Risk)
```
Upload → Analysis → Duplication Warning
                       ↓
                    MUST do Deep Compare before proceeding
                    Can skip, but warned
```

---

## Current Bugs

### Bug 1: Step 3 Collapsed When Should Be Expanded
**Where:** `displayAnalysis()` line 1410
**Issue:** Sets Step 3 to 'completed' but doesn't ensure it's expanded
**Fix:** Add `document.getElementById('step-3-card').classList.remove('collapsed')` or expand logic

### Bug 2: Differentiation Buttons Not Visible in Step 5
**Where:** `enableStep5WithDifferentiation()` lines 2649-2650
**Code:**
```javascript
document.getElementById('refine-overlap-btn').style.display = '';
document.getElementById('strategic-diff-btn').style.display = '';
```

**Issue:** These buttons exist in Step 4's HTML, not Step 5's HTML!

**Root cause:** 
- refine-overlap-btn and strategic-diff-btn are in Step 4 `<div id="improve-actions">`
- When we skip Step 4, Step 5 never sees these buttons
- Need to either:
  1. Clone buttons to Step 5, OR
  2. Have differentiation buttons natively in Step 5 HTML

### Bug 3: No Cancel/Quit Options
**Issue:** User can't easily bail out of the flow
**Fix:** Add prominent "Cancel Upload" button visible in all states

---

## Required Fixes

### Fix 1: Keep Step 3 Expanded
```javascript
// In displayAnalysis() at line 1409
showEarlyDifferentiationGate(data.similar_agents, highestSimilarity);
setStepState(3, 'completed');

// ADD THIS:
const step3Card = document.getElementById('step-3-card');
step3Card.classList.remove('collapsed');
step3Card.classList.add('expanded');
```

### Fix 2: Add Differentiation Buttons to Step 5 HTML
**Current:** Buttons only exist in Step 4
**Fix:** Add buttons to Step 5 body so they're available when Step 4 is skipped

```html
<!-- In Step 5 body, add differentiation actions section -->
<div class="differentiation-actions hidden" id="step-5-diff-actions">
    <h4>Choose Differentiation Approach</h4>
    
    <div class="action-card">
        <button class="btn btn-primary" id="refine-overlap-step5-btn">
            Pattern 1: Quick Refinement
        </button>
        <p class="action-desc">Removes overlapping capabilities (~15 seconds)</p>
    </div>
    
    <div class="action-card">
        <button class="btn btn-accent" id="strategic-diff-step5-btn">
            Pattern 2: Strategic Differentiation
        </button>
        <p class="action-desc">AI analyzes and proposes differentiation strategies</p>
    </div>
    
    <hr>
    
    <button class="btn btn-secondary" id="store-without-diff-btn">
        Store Without Differentiating
    </button>
    <button class="btn btn-ghost" id="cancel-from-step5-btn">
        Cancel Upload
    </button>
</div>
```

### Fix 3: Update enableStep5WithDifferentiation()
```javascript
function enableStep5WithDifferentiation() {
    setStepState(5, 'active');
    document.getElementById('step-5-empty').classList.add('hidden');
    document.getElementById('step-5-content').classList.remove('hidden');
    
    // Show differentiation options section
    document.getElementById('step-5-diff-actions').classList.remove('hidden');
    
    // Hide default store button
    document.getElementById('store-btn').style.display = 'none';
    
    // Store original content for differentiation
    improvedContent = originalContent;
    window._lastOverlapAgents = analysisData.similar_agents.map(s => ({...}));
}
```

### Fix 4: Add Cancel Button to Persistent Header
Add a sticky header/banner with Cancel always visible.

---

## State Machine (CORRECT)

```
STATE: upload_init
  → analyze → STATE: analyzing
  
STATE: analyzing
  → success → STATE: similarity_check
  
STATE: similarity_check
  CASE: no_overlap (<50%) → STATE: quality_eval
  CASE: moderate_overlap (50-69%) → STATE: similar_agents_review
  CASE: high_overlap (70-84%) → STATE: early_diff_gate
  CASE: very_high (85%+) → STATE: duplication_warning
  
STATE: early_diff_gate
  CHOICE: differentiate_now → STATE: differentiation_options
  CHOICE: continue_quality → STATE: quality_eval
  
STATE: differentiation_options
  CHOICE: pattern1 (refine) → STATE: refining
  CHOICE: pattern2 (strategic) → STATE: strategic_diff
  CHOICE: store_anyway → STATE: store
  CHOICE: cancel → STATE: cancelled
  
STATE: quality_eval
  → auto_run → STATE: quality_results
  
STATE: quality_results
  CHOICE: improve → STATE: improving
  CHOICE: store_as_is → STATE: store
  CHOICE: cancel → STATE: cancelled
  
STATE: improving
  → success → STATE: improved_review
  
STATE: improved_review
  CHOICE: store_improved → STATE: store
  CHOICE: store_original → STATE: store
  CHOICE: refine_overlap (if still overlap) → STATE: refining
  CHOICE: cancel → STATE: cancelled
```

---

## Implementation Plan

1. ✅ **Document this flow** (this file)
2. ⬜ **Fix Step 3 expand logic**
3. ⬜ **Add differentiation buttons to Step 5 HTML**
4. ⬜ **Wire up Step 5 differentiation button handlers**
5. ⬜ **Add Cancel button to all states**
6. ⬜ **Test complete flow**

---

**Next:** Implement these fixes systematically.
