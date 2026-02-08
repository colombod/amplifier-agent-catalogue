# Upload Flow Analysis - Bugs Found

## What User Experienced (BROKEN)

1. ✅ Upload TEST_AGENT_UPLOAD.md (79% overlap)
2. ✅ Step 2 completes (AI classification)
3. ✅ Step 3 shows early diff gate with 79% (correct)
4. ❌ **BUG: Step 3 is COLLAPSED** (should be EXPANDED to show similar agents list)
5. ✅ User clicks "Differentiate Now"
6. ✅ Step 4 skipped (correct behavior)
7. ❌ **BUG: Step 5 shows NO differentiation buttons**
   - Expected: Pattern 1 (Refine) and Pattern 2 (Strategic) buttons
   - Actual: Only "Store Without Differentiating" or "Start Over"
   - Message: "Skipped quality check to prioritize differentiation. Use one of the patterns below to reduce overlap."
   - NO PATTERNS SHOWN!

## Root Causes

### Bug 1: Step 3 Collapsed
**Where:** `showEarlyDifferentiationGate()` line 2588
**Issue:** Gate is shown but step card state isn't set to expanded
**Fix:** Add `document.getElementById('step-3-card').classList.remove('collapsed')`

### Bug 2: Differentiation Buttons Missing from Step 5
**Where:** `enableStep5WithDifferentiation()` lines 2649-2650
**Code:**
```javascript
document.getElementById('refine-overlap-btn').style.display = '';
document.getElementById('strategic-diff-btn').style.display = '';
```
**Issue:** These buttons ONLY exist in Step 4 HTML (`improve-actions` div)
**When Step 4 is skipped, Step 5 never sees these buttons**

**Current HTML structure:**
```
Step 4 (Quality Evaluation):
  <div id="improve-actions">
    <button id="refine-overlap-btn">...</button>      ← Only here!
    <button id="strategic-diff-btn">...</button>      ← Only here!
  </div>

Step 5 (Decision & Store):
  <div id="step-5-content">
    <button id="store-btn">Store Agent</button>
    <!-- NO DIFFERENTIATION BUTTONS -->
  </div>
```

**Fix needed:** Add differentiation buttons to Step 5 HTML structure

---

## Expected User Flow

### Scenario: High Overlap (70-84%)

```
STEP 1: Upload file
  → File accepted
  ↓
STEP 2: AI Classification  
  → Agent categorized
  ↓
STEP 3: Similarity Detection (EXPANDED, not collapsed)
  Similar Agents card shows:
  - Top 3 similar agents (CSV DSL Dev 79%, etc.)
  - Can click "Deep Compare" on each
  
  Early Diff Gate appears:
  ┌──────────────────────────────────────────────────┐
  │ ⚠ High Overlap Detected (79%)                    │
  │                                                   │
  │ Your agent overlaps with:                        │
  │ • CSV DSL Development Assistant (79%)            │
  │                                                   │
  │ [Differentiate Now] [Continue to Quality Check]  │
  └──────────────────────────────────────────────────┘
  
  USER CHOICE:
  
  A) "Differentiate Now"
     ↓
     SKIP Step 4 → Go to Step 5 WITH differentiation options:
     
     STEP 5: Differentiation Decision
     ┌──────────────────────────────────────────────┐
     │ Skipped quality check to prioritize diff    │
     │                                              │
     │ Pattern 1: Quick Refinement                  │
     │ [Refine to Reduce Overlap]                   │
     │ Removes overlapping capabilities (~15s)      │
     │                                              │
     │ Pattern 2: Strategic Analysis                │
     │ [Strategic Differentiation]                  │
     │ Recipe analyzes overlap, proposes strategies │
     │                                              │
     │ Or:                                          │
     │ [Store Without Differentiating]              │
     │ [Cancel Upload]                              │
     └──────────────────────────────────────────────┘
  
  B) "Continue to Quality Check"
     ↓
     STEP 4: Quality Evaluation
       → LLM scores agent (A-F grade)
       → Show results with issues
       → Option to improve or store as-is
     ↓
     STEP 5: Store Decision
       [Store Improved] or [Store Original]
```

---

## State Machine (Correct)

```
STATE_0: INIT
  → upload file → STATE_1

STATE_1: ANALYZING (Steps 1-2)
  → success → STATE_2
  → error → STATE_ERROR

STATE_2: SIMILARITY_CHECK (Step 3)
  CASE overlap >= 0.85 → STATE_3_HIGH (needs deep compare)
  CASE overlap >= 0.70 → STATE_3_EARLY_GATE (show gate)
  CASE overlap >= 0.50 → STATE_3_SIMILAR (just show list)
  CASE overlap < 0.50 → STATE_4 (skip to quality)
  
STATE_3_EARLY_GATE: (Step 3 with gate)
  EXPANDED step card, showing:
  - Similar agents list
  - Early diff gate
  
  USER CHOICE:
    differentiate_now → STATE_5_DIFF (skip quality)
    continue_quality → STATE_4
    cancel → STATE_CANCELLED
    
STATE_3_HIGH: (Step 3 duplication warning)
  MUST do deep compare
  
STATE_4: QUALITY_EVAL
  → evaluate → STATE_4_RESULTS
  
STATE_4_RESULTS:
  CHOICE: improve → STATE_4_IMPROVING
  CHOICE: store_as_is → STATE_5_STORE
  CHOICE: cancel → STATE_CANCELLED
  
STATE_4_IMPROVING:
  → improved → STATE_4_IMPROVED
  
STATE_4_IMPROVED:
  CHOICE: store_improved → STATE_5_STORE
  CHOICE: store_original → STATE_5_STORE
  CHOICE: refine_overlap → STATE_DIFF_REFINE
  CHOICE: strategic_diff → STATE_DIFF_STRATEGIC
  
STATE_5_DIFF: (Differentiation options)
  Display:
  - Pattern 1 button (refine)
  - Pattern 2 button (strategic)
  - Store anyway button
  - Cancel button
  
  CHOICE: pattern1 → STATE_DIFF_REFINE
  CHOICE: pattern2 → STATE_DIFF_STRATEGIC
  CHOICE: store → STATE_5_STORE
  CHOICE: cancel → STATE_CANCELLED
  
STATE_5_STORE:
  → store → STATE_SUCCESS
  
STATE_CANCELLED:
  → redirect to /
  
STATE_SUCCESS:
  → show agent page
```

---

## Fixes Required

1. **Fix Step 3 expand** - When showEarlyDifferentiationGate() called
2. **Add differentiation buttons to Step 5 HTML** - Native buttons in Step 5
3. **Wire up Step 5 diff button handlers** - Connect to existing refine/strategic logic
4. **Add Cancel button** - Visible in all states
5. **Test complete flow** - All paths work

