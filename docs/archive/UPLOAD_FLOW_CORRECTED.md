# Upload Flow - Corrected Understanding

**Based on user feedback:** 2026-02-08 18:17

---

## The Correct Flow

### High Overlap Scenario (70-84%)

```
STEP 1: Upload file ✓
  ↓
STEP 2: AI Classification ✓
  ↓
STEP 3: Similarity Detection (MUST BE EXPANDED)
  Shows:
  - List of similar agents (CSV DSL Dev 79%, etc.)
  - Early Differentiation Gate:
  
  ┌─────────────────────────────────────────────┐
  │ ⚠ High Overlap Detected (79%)               │
  │                                              │
  │ [Differentiate Now] [Continue to Quality]   │
  └─────────────────────────────────────────────┘
  
  USER CHOICE:
  
  ═══════════════════════════════════════════════
  CHOICE A: "Differentiate Now"
  ═══════════════════════════════════════════════
  
  → Show Differentiation Options (inline in Step 3 or modal):
  
  ┌─────────────────────────────────────────────┐
  │ Choose Differentiation Approach:            │
  │                                              │
  │ Pattern 1: Quick Refinement                 │
  │ [Refine to Reduce Overlap]                  │
  │ Removes overlapping capabilities (~15s)     │
  │                                              │
  │ Pattern 2: Strategic Analysis               │
  │ [Strategic Differentiation]                 │
  │ Recipe-based, shows strategies for review   │
  │                                              │
  │ [Cancel]                                     │
  └─────────────────────────────────────────────┘
  
  User picks Pattern 1 or Pattern 2
    ↓
  Differentiation runs (LLM or Recipe)
    ↓
  Differentiation completes → refined content available
    ↓
  RESUME AT STEP 3 → Continue to Step 4 (Quality Analysis)
    ↓
  STEP 4: Quality Evaluation
    → Run quality check on DIFFERENTIATED version
    → Show score and issues
    → Option to improve further or store
    ↓
  STEP 5: Store Decision
    → Store differentiated (and maybe improved) version
  
  ═══════════════════════════════════════════════
  CHOICE B: "Continue to Quality Check"
  ═══════════════════════════════════════════════
  
  → Skip differentiation for now
    ↓
  STEP 4: Quality Evaluation
    → Run quality check on ORIGINAL version
    → Show score and issues
    → Option to improve or store as-is
    → If still has overlap, can differentiate from Step 4
    ↓
  STEP 5: Store Decision
    → Store (original, improved, or differentiated)
```

---

## Key Insight

**"Differentiate Now" means:**
- Do differentiation FIRST
- THEN continue with quality analysis on the differentiated version
- NOT "skip quality analysis entirely"

**The flow is:**
```
Differentiate → Quality → Store
```

**NOT:**
```
Differentiate → Store (skip quality)
```

---

## State Machine (Corrected)

```
STATE_3_EARLY_GATE: (Step 3 - high overlap 70-84%)
  DISPLAY:
    - Similar agents list (expanded)
    - Early diff gate
  
  USER CHOICE:
    "Differentiate Now" → STATE_3_DIFF_PICKER
    "Continue Quality" → STATE_4
    "Cancel" → STATE_CANCELLED

STATE_3_DIFF_PICKER: (Choose diff pattern)
  DISPLAY:
    - Pattern 1 button (Quick Refine)
    - Pattern 2 button (Strategic)
    - Cancel button
  
  USER CHOICE:
    pattern1 → STATE_DIFF_REFINING
    pattern2 → STATE_DIFF_STRATEGIC
    cancel → STATE_3_EARLY_GATE (back to gate)
    
STATE_DIFF_REFINING: (Pattern 1 running)
  → LLM refines to reduce overlap
  → SUCCESS → STATE_3_RESUME_AFTER_DIFF
  
STATE_DIFF_STRATEGIC: (Pattern 2 running)
  → Recipe runs, shows strategies
  → User approves strategy
  → SUCCESS → STATE_3_RESUME_AFTER_DIFF
  
STATE_3_RESUME_AFTER_DIFF:
  → Auto-proceed to STATE_4 (quality eval on differentiated content)
  
STATE_4: QUALITY_EVAL
  → Evaluate (original OR differentiated content)
  → STATE_4_RESULTS
  
STATE_4_RESULTS:
  → Show score, issues, options
  → User chooses: improve, store as-is, or cancel
  
STATE_5: STORE
  → Final store action
```

---

## Implementation Changes Needed

### Current (WRONG):
```javascript
// "Differentiate Now" button handler
document.getElementById('differentiate-early-btn').addEventListener('click', () => {
    // Skip Step 4, go straight to Step 5
    enableStep5WithDifferentiation();  // ← WRONG
});
```

### Corrected (RIGHT):
```javascript
// "Differentiate Now" button handler
document.getElementById('differentiate-early-btn').addEventListener('click', () => {
    // Show differentiation pattern picker
    showDifferentiationPatternPicker();  // ← Show options FIRST
});

function showDifferentiationPatternPicker() {
    // Show modal or inline picker with Pattern 1 and Pattern 2 buttons
    // When user picks:
    //   Pattern 1 → runQuickRefinement() → then enableStep4()
    //   Pattern 2 → runStrategicDiff() → then enableStep4()
}
```

---

## 🎯 Questions for You

**Is this the correct understanding now?**

1. "Differentiate Now" → Show diff options → Run chosen pattern → THEN go to quality eval
2. "Continue to Quality Check" → Skip differentiation → Quality eval on original
3. Step 3 should be EXPANDED when gate appears
4. Differentiation always leads back to quality analysis (not straight to store)

**If YES, I'll implement these fixes. If NO, please correct my understanding.**