# Upload Flow Implementation Plan

**Created:** 2026-02-08  
**Status:** Ready for Implementation  
**Branch:** feat/early-differentiation-gate-6  
**PR:** #7

---

## Executive Summary

Based on deep workflow analysis and design expert consultation, we're implementing a **Progressive Disclosure** approach to fix critical UX issues in the 5-step upload wizard.

**Core Problems Solved:**
1. ✅ Button proliferation (5 competing buttons → 1 primary + overflow menu)
2. ✅ Ambiguous error messages (→ severity system with guidance)
3. ✅ Confusing comparison labels ("Agent A/B" → "Your Upload" vs "Existing: [Name]")
4. ✅ Opaque progress states (→ operational transparency)
5. ✅ Missing early diff gate HTML (→ implemented with clear actions)

**Design Approach:** Progressive Disclosure
- Show recommended path prominently
- Hide alternatives behind expandable sections
- Provide rationale on demand
- Build confidence through guidance

---

## Implementation Phases

### Phase 1: Critical Fixes ✅ (Current PR #7)

**Status:** In progress

**Changes:**
1. ✅ Add `#early-diff-gate` HTML element (missing from template)
2. ✅ Fix comparison modal labels ("Your Upload" vs "Existing: [Agent Name]")
3. ✅ Fix event listener bug (buttons greyed out)
4. ✅ Wire up SSE streaming for deep comparison
5. ✅ Fix [object Object] rendering in diff view

**Files Modified:**
- `src/agent_catalogue/web/templates/upload.html`
- `src/agent_catalogue/web/templates/components/diff_view.html`
- `src/agent_catalogue/api/routes.py` (add `/api/stream/compare/{agent_id}`)

---

### Phase 2: Core Component Improvements (Next PR)

**Status:** Designed, not yet implemented

**Priority Changes:**

#### 2.1 Unified Progress Indicator
**File:** Create `src/agent_catalogue/web/templates/components/progress_indicator.html`

**Replace:** 7 different spinner instances

**With:** Single reusable component:
```html
{% macro progress_indicator(operation, subtasks=[], duration=None, sse_endpoint=None) %}
<div class="progress-indicator {% if sse_endpoint %}streaming{% endif %}">
  <div class="spinner"></div>
  <div class="progress-content">
    <h4>{{ operation }}</h4>
    {% if subtasks %}
    <ul class="subtasks">
      {% for task in subtasks %}
      <li>{{ task }}</li>
      {% endfor %}
    </ul>
    {% endif %}
    {% if duration %}
    <p class="duration">{{ duration }}</p>
    {% endif %}
  </div>
  {% if sse_endpoint %}
  <div class="activity-feed-toggle">
    <button class="toggle-details">▼ Show AI Progress</button>
    <div class="feed-content collapsed" id="activity-{{ id }}"></div>
  </div>
  {% endif %}
</div>
{% endmacro %}
```

**Usage:** Replace spinners in Steps 1-5

---

#### 2.2 Severity-Aware Message Box
**File:** Create `src/agent_catalogue/web/templates/components/message_box.html`

**Component:**
```html
{% macro message_box(severity, title, message, actions=None, expandable=None) %}
<div class="message-box {{ severity }}">
  <div class="message-icon">
    {% if severity == 'error' %}❌{% endif %}
    {% if severity == 'warning' %}⚠️{% endif %}
    {% if severity == 'info' %}ℹ️{% endif %}
    {% if severity == 'success' %}✓{% endif %}
  </div>
  <div class="message-content">
    <h4>{{ title }}</h4>
    <p>{{ message }}</p>
    
    {% if expandable %}
    <details class="message-details">
      <summary>{{ expandable.title }}</summary>
      <div class="details-content">{{ expandable.content }}</div>
    </details>
    {% endif %}
    
    {% if actions %}
    <div class="message-actions">
      {% if actions.primary %}
      <button class="btn-primary" onclick="{{ actions.primary.onClick }}">
        {{ actions.primary.label }}
      </button>
      {% endif %}
      {% if actions.secondary %}
      <button class="btn-secondary" onclick="{{ actions.secondary.onClick }}">
        {{ actions.secondary.label }}
      </button>
      {% endif %}
    </div>
    {% endif %}
  </div>
</div>
{% endmacro %}
```

**Usage:** Replace decision boxes in error handling

---

#### 2.3 Decision Gate Component
**File:** Create `src/agent_catalogue/web/templates/components/decision_gate.html`

**Component:**
```html
{% macro decision_gate(title, context, recommendation, alternatives=[], rationale=None) %}
<div class="decision-gate">
  <div class="gate-context">
    <h4>{{ title }}</h4>
    <p>{{ context }}</p>
  </div>
  
  <!-- Recommended path prominent -->
  <div class="recommendation-primary">
    <button class="btn-primary" onclick="{{ recommendation.action }}">
      <span class="btn-label">{{ recommendation.label }}</span>
      <span class="btn-outcome">{{ recommendation.outcome }}</span>
    </button>
  </div>
  
  <!-- Alternatives collapsed -->
  {% if alternatives %}
  <details class="alternatives">
    <summary>Or choose a different path</summary>
    {% for alt in alternatives %}
    <button class="btn-secondary" onclick="{{ alt.action }}">
      <span class="btn-label">{{ alt.label }}</span>
      {% if alt.tradeoff %}
      <span class="btn-tradeoff">{{ alt.tradeoff }}</span>
      {% endif %}
    </button>
    {% endfor %}
  </details>
  {% endif %}
  
  <!-- Rationale expandable -->
  {% if rationale %}
  <details class="rationale">
    <summary>{{ rationale.title }}</summary>
    <p>{{ rationale.content }}</p>
  </details>
  {% endif %}
</div>
{% endmacro %}
```

**Usage:** Replace multi-button sections in Step 4

---

### Phase 3: Polish & Enhancement (Future PR)

**Not blocking, but improves UX:**

1. **Comparison history sidebar** - Persistent view of all comparisons
2. **Activity feed auto-collapse** - Collapsed by default, toggle to show
3. **Disabled button tooltips** - Explain why action unavailable
4. **Token metrics fold-in** - Hide detailed metrics behind "Technical Details" expander
5. **Smart defaults** - Remember user's last choice (improve vs store as-is)

---

## Message Updates (Phase 2)

**Apply voice strategy from docs/UPLOAD_FLOW_VOICE_STRATEGY.md:**

### Current → Improved Messages

**Progress states:**

| Current | Improved |
|---------|----------|
| "This may take 10-20 seconds" | "Comparing with 47 existing agents using semantic similarity<br>Typically takes 15-20 seconds" |
| "Running deep behavioral analysis..." | "Comparing agents...<br>• Analyzing behavioral differences<br>• Generating explanation" |
| "Evaluating agent quality..." | "Evaluating agent quality...<br>• Checking description clarity<br>• Analyzing completeness<br>• Validating examples" |

**Error messages:**

| Current | Improved |
|---------|----------|
| "You can still store the agent" | "**Note:** Evaluation unavailable<br>You can store without quality score" |
| "Analysis failed" | "**Cannot proceed:** Analysis failed<br>Upload a valid AGENTS.md file" |
| "You can still proceed" | "**Recommended fix:** Overlap detected<br>Review comparison to avoid duplication" |

**Comparison labels:**

| Current | Improved |
|---------|----------|
| "Agent A" / "Agent B" | "Your Upload" / "Existing: [Agent Name]" |
| "distinct" (verdict) | "79% similar to Existing: [Name]" |
| "Behavioral Diff Analysis" | "Comparing: Your Upload vs Existing: [Name]" |

---

## Testing Checklist

**Before merging PR #7:**

- [ ] Early diff gate appears at 70-84% similarity
- [ ] Both buttons work (not greyed out)
- [ ] Comparison modal shows real agent names (not Agent A/B)
- [ ] Similarity percentage displays correctly (not 0%)
- [ ] Capability lists show text (not [object Object])
- [ ] "View Agent" opens in new tab (doesn't lose context)
- [ ] SSE activity feed shows during deep comparison
- [ ] Event listeners don't fail on hidden elements

**Before merging Phase 2:**

- [ ] Unified progress component used in all 7 loading states
- [ ] Severity badges visible on all error/warning messages
- [ ] Decision gates show ONE primary recommendation
- [ ] Alternatives behind expandable sections
- [ ] Disabled buttons have tooltips explaining why
- [ ] Button copy follows guidelines (no generic "Proceed")

---

## File Changes Summary

### Phase 1 (Current PR #7)
- ✅ `upload.html` - Early diff gate HTML, comparison labels, event listeners
- ✅ `diff_view.html` - Fix rendering, update labels
- ✅ `routes.py` - Add streaming comparison endpoint
- ✅ `docs/UPLOAD_FLOW_VOICE_STRATEGY.md` - NEW
- ✅ `docs/UPLOAD_FLOW_REDESIGN.md` - NEW
- ✅ `docs/UPLOAD_FLOW_IMPLEMENTATION_PLAN.md` - NEW (this file)

### Phase 2 (Next PR)
- Create `components/progress_indicator.html`
- Create `components/message_box.html`
- Create `components/decision_gate.html`
- Update `upload.html` to use new components
- Update all progress messages per voice strategy

### Phase 3 (Future)
- Create comparison history sidebar OR inline cards
- Add activity feed toggle controls
- Add disabled button tooltips
- Collapse token metrics

---

**Status:** Phase 1 ready for testing, Phase 2 designed and documented
