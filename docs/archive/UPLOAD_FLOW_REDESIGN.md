# Upload Flow Redesign: Component Specifications

**Created:** 2026-02-08  
**Status:** Design Complete - Ready for Implementation  
**Approach:** Progressive Disclosure (start simple, reveal complexity as needed)

---

## Design Philosophy

**Chosen Approach:** Progressive Disclosure

**Why:**
- Technical users benefit from guidance but want control
- Reduces button proliferation through smart defaults
- Addresses confidence issues through recommendations
- Solves modal overload through focused interactions

**Core Principles:**
1. **One clear recommendation** per decision point
2. **Progressive disclosure** - hide complexity until needed
3. **Operational transparency** - show what's happening
4. **Visual severity hierarchy** - block/warn/info system
5. **Persistent context** - don't lose comparison data

---

## Component Specifications

### 1. Unified Progress Indicator

**Purpose:** Replace 7 spinner instances with one consistent loading pattern

**Props:**
```typescript
interface ProgressIndicatorProps {
  phase: 'loading' | 'streaming' | 'complete' | 'error'
  operation: string  // "Analyzing agent definition"
  subtasks?: string[]  // ["Extracting metadata", "Validating schema"]
  duration?: string  // "Typically 15-20 seconds"
  sseEndpoint?: string  // If provided, shows activity feed
  onCancel?: () => void  // If provided, shows cancel button
}
```

**States:**

**Loading (No SSE):**
```html
<div class="progress-indicator">
  <div class="spinner"></div>
  <div class="progress-content">
    <h4>Analyzing agent definition...</h4>
    <ul class="subtasks">
      <li>Extracting metadata</li>
      <li>Validating schema structure</li>
      <li>Detecting dependencies</li>
    </ul>
    <p class="duration">Typically 10-15 seconds</p>
  </div>
</div>
```

**Streaming (With SSE):**
```html
<div class="progress-indicator streaming">
  <div class="progress-header">
    <h4>Analyzing agent definition...</h4>
    <button class="toggle-details">▼ Show Details</button>
  </div>
  <div class="activity-feed" id="activity-feed-{id}">
    <!-- Real-time events appear here -->
  </div>
  {#if onCancel}
  <button class="btn-secondary">Cancel Operation</button>
  {/if}
</div>
```

**Design notes:**
- Activity feed collapsed by default, toggle to show
- Spinner removed when SSE connects (feed proves activity)
- Cancel button appears if operation is cancellable
- Duration estimate shown if no SSE available

---

### 2. Severity-Aware Message Box

**Purpose:** Replace ambiguous "You can still proceed" with clear severity system

**Props:**
```typescript
interface MessageBoxProps {
  severity: 'error' | 'warning' | 'info' | 'success'
  title: string
  message: string
  actions?: {
    primary?: { label: string, onClick: () => void }
    secondary?: { label: string, onClick: () => void }
  }
  expandable?: {
    title: string  // "Why this recommendation?"
    content: string
  }
}
```

**Visual Hierarchy:**

**Error (Blocking):**
```html
<div class="message-box error">
  <div class="message-icon">❌</div>
  <div class="message-content">
    <h4>Cannot proceed: Agent name is required</h4>
    <p>Add a name to your agent definition before uploading</p>
    <div class="message-actions">
      <button class="btn-primary" disabled>Store Agent</button>
      <span class="disabled-reason">Fix errors first</span>
    </div>
  </div>
</div>
```

**Warning (Recommended fix):**
```html
<div class="message-box warning">
  <div class="message-icon">⚠️</div>
  <div class="message-content">
    <h4>Recommended fix: Similar agent exists (89% match)</h4>
    <p>Your agent overlaps with "Customer Support Assistant"</p>
    <button class="expand-details">Why this matters ▼</button>
    <div class="expandable-content hidden">
      Storing duplicate agents creates maintenance burden and user confusion...
    </div>
    <div class="message-actions">
      <button class="btn-primary">View Comparison</button>
      <button class="btn-secondary">Store Anyway</button>
    </div>
  </div>
</div>
```

**Info:**
```html
<div class="message-box info">
  <div class="message-icon">ℹ️</div>
  <div class="message-content">
    <h4>Note: No tags specified</h4>
    <p>You can add tags later for discoverability</p>
  </div>
</div>
```

**Color system:**
- Error: `--danger` (red)
- Warning: `--warning` (amber)
- Info: `--info` (blue)
- Success: `--success` (green)

---

### 3. Decision Gate Component

**Purpose:** Reduce button proliferation by showing recommended path prominently

**Props:**
```typescript
interface DecisionGateProps {
  title: string
  context: string  // Explain the situation
  recommendation: {
    label: string
    action: () => void
    outcome: string  // What happens if you click
  }
  alternatives?: Array<{
    label: string
    action: () => void
    outcome: string
    tradeoff?: string  // "You can improve later, but..."
  }>
  rationale?: {
    title: string  // "Why this recommendation?"
    content: string
  }
}
```

**Visual Pattern:**

```html
<div class="decision-gate">
  <div class="gate-context">
    <h4>Quality Score: C</h4>
    <p>Your agent's description and instructions could be clearer.</p>
  </div>
  
  <!-- Recommended path prominent -->
  <div class="recommendation-primary">
    <button class="btn-primary">
      <span class="btn-label">Improve Quality</span>
      <span class="btn-outcome">AI will enhance clarity (~30s)</span>
    </button>
  </div>
  
  <!-- Alternatives collapsed -->
  <details class="alternatives">
    <summary>Or choose a different path</summary>
    <button class="btn-secondary">
      <span class="btn-label">Store As-is</span>
      <span class="btn-tradeoff">You can improve later, but users may find it harder to understand</span>
    </button>
  </details>
  
  <!-- Rationale expandable -->
  <details class="rationale">
    <summary>Why improve now?</summary>
    <p>Higher quality agents are easier to discover and use...</p>
  </details>
</div>
```

**Key features:**
- ONE button visible by default (recommended)
- Alternatives behind `<details>` (HTML native disclosure)
- Outcome/tradeoff shown as subtitle under button
- Rationale available but not intrusive

---

### 4. Comparison Modal (Redesigned)

**Purpose:** Fix "Agent A vs B" confusion, reduce modal overload

**Props:**
```typescript
interface ComparisonModalProps {
  yourAgent: {
    name: string
    content: string
  }
  existingAgent: {
    name: string
    content: string
  }
  similarity: number  // 0-1
  diff: BehavioralDiff
  narrative?: string
  sseEndpoint?: string  // For real-time comparison
}
```

**Visual Structure:**

```html
<div class="modal-overlay" id="comparison-modal">
  <div class="modal-content wide">
    <!-- Clear header with context -->
    <div class="modal-header comparison">
      <div class="comparison-context">
        <span class="label-yours">Your Upload</span>
        <span class="similarity-badge">79% similar</span>
        <span class="label-theirs">Existing: CSV DSL Development Assistant</span>
      </div>
      <button class="btn-close">×</button>
    </div>
    
    <div class="modal-body">
      <!-- Activity feed (if SSE) -->
      <div class="activity-feed-compact" id="compare-activity">
        <button class="toggle-feed">▼ Show AI Analysis Progress</button>
        <div class="feed-content collapsed">
          <!-- SSE events here -->
        </div>
      </div>
      
      <!-- Three-column diff (from diff_view.html) -->
      <div class="diff-body">
        <div class="diff-column-header">Your Upload Only</div>
        <div class="diff-column-header">Shared</div>
        <div class="diff-column-header">Existing: CSV DSL Dev Only</div>
        <!-- Diff content -->
      </div>
      
      <!-- Narrative explanation -->
      <div class="comparison-narrative">
        <h4>Analysis</h4>
        <p>{narrative}</p>
      </div>
    </div>
    
    <div class="modal-footer">
      <button class="btn-primary">Close & Return to Upload</button>
    </div>
  </div>
</div>
```

**Key changes:**
- Header shows BOTH agent names and similarity prominently
- "Your Upload" vs "Existing: [Specific Name]" in column headers
- Activity feed collapsed by default (toggle to show)
- Single clear action: "Close & Return to Upload" (no confusing navigation)
- Opens in modal, closes returns to exact same state

---

### 5. Early Differentiation Gate (Missing HTML)

**Purpose:** Implement the 70-84% threshold gate that's referenced in JS but missing from template

**Props:**
```typescript
interface EarlyDiffGateProps {
  similarity: number
  topAgents: Array<{name: string, score: number, capabilities: string[]}>
  onDifferentiate: () => void
  onContinue: () => void
}
```

**HTML Implementation:**

```html
<!-- Add to Step 3 body, after similar-list -->
<div class="early-diff-gate hidden" id="early-diff-gate">
  <div class="gate-header">
    <span class="gate-icon">⚠️</span>
    <h4>High Overlap Detected (<span id="overlap-percentage">79</span>%)</h4>
  </div>
  
  <div class="gate-body" id="overlap-summary">
    <!-- Populated by showEarlyDifferentiationGate() -->
  </div>
  
  <div class="gate-actions">
    <button class="btn-primary" id="differentiate-early-btn">
      <span class="btn-label">Differentiate Now</span>
      <span class="btn-outcome">Skip quality check, reduce overlap first</span>
    </button>
    <button class="btn-secondary" id="continue-quality-btn">
      <span class="btn-label">Continue to Quality Check</span>
      <span class="btn-outcome">Improve quality first, then address overlap</span>
    </button>
  </div>
  
  <details class="gate-rationale">
    <summary>Why differentiate now?</summary>
    <p>With 79% overlap, this agent may duplicate existing functionality. Differentiating first saves time by positioning your agent uniquely before quality refinement.</p>
  </details>
</div>
```

**Styling:**
```css
.early-diff-gate {
  margin: 1.5rem 0;
  padding: 1.5rem;
  border: 2px solid var(--warning);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(210, 153, 34, 0.1), rgba(187, 128, 9, 0.05));
}

.gate-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.gate-icon {
  font-size: 1.5rem;
}

.gate-actions {
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
}

.gate-actions .btn-outcome {
  display: block;
  font-size: 0.85em;
  color: var(--text-muted);
  margin-top: 0.25rem;
  font-weight: normal;
}
```

---

### 6. Action Button Hierarchy (Step 4 Simplification)

**Current Problem:** 5 competing buttons after improvement

**Solution:** Primary + overflow menu

```html
<div class="action-buttons-improved">
  <!-- Primary recommendation -->
  <button class="btn-primary" id="store-improved-btn">
    Store Improved Version
  </button>
  
  <!-- Secondary options in dropdown -->
  <details class="action-overflow">
    <summary class="btn-secondary-outline">More Options ▼</summary>
    <div class="overflow-menu">
      <button class="overflow-item" id="refine-overlap-btn" 
              style="display: none;">
        <span class="item-label">Refine to Reduce Overlap</span>
        <span class="item-desc">Pattern 1: Quick differentiation</span>
      </button>
      <button class="overflow-item" id="strategic-diff-btn" 
              style="display: none;">
        <span class="item-label">Strategic Differentiation</span>
        <span class="item-desc">Pattern 2: Review strategies first</span>
      </button>
      <button class="overflow-item" id="store-original-btn">
        <span class="item-label">Store Original Version</span>
        <span class="item-desc">Discard all improvements</span>
      </button>
      <hr>
      <button class="overflow-item danger" id="cancel-upload-btn">
        <span class="item-label">Cancel Upload</span>
        <span class="item-desc">Abort and start over</span>
      </button>
    </div>
  </details>
</div>
```

**Styling:**
```css
.action-overflow {
  position: relative;
  display: inline-block;
}

.overflow-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.5rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  min-width: 300px;
  z-index: 100;
}

.overflow-item {
  display: block;
  width: 100%;
  padding: 0.75rem 1rem;
  text-align: left;
  border: none;
  background: transparent;
  cursor: pointer;
}

.overflow-item:hover {
  background: var(--bg-hover);
}

.overflow-item .item-label {
  display: block;
  font-weight: 600;
}

.overflow-item .item-desc {
  display: block;
  font-size: 0.85em;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.overflow-item.danger {
  color: var(--danger);
}
```

**Behavior:**
- Primary action always visible (recommended path)
- Alternatives behind click/tap (progressive disclosure)
- Each option has label + description (clear consequence)
- Refine/Strategic buttons show ONLY if overlap detected (conditional rendering)

---

### 7. Comparison History Sidebar (Modal Alternative)

**Purpose:** Persistent view of comparisons without losing context

**Props:**
```typescript
interface ComparisonHistoryProps {
  comparisons: Array<{
    agentId: string
    agentName: string
    similarity: number
    timestamp: Date
    status: 'pending' | 'complete'
  }>
  onViewDetails: (agentId: string) => void
  onDismiss: (agentId: string) => void
}
```

**HTML Structure:**

```html
<div class="comparison-sidebar" id="comparison-sidebar">
  <div class="sidebar-header">
    <h4>Comparisons ({count})</h4>
    <button class="btn-collapse">▼</button>
  </div>
  
  <div class="sidebar-body">
    {#each comparison in comparisons}
    <div class="comparison-card">
      <div class="card-header">
        <span class="agent-name">{agentName}</span>
        <span class="similarity-badge {getClass(similarity)}">
          {similarity}%
        </span>
      </div>
      <div class="card-actions">
        <button class="btn-sm" onclick="viewDetails({agentId})">
          View Details
        </button>
        <button class="btn-icon" onclick="dismiss({agentId})">
          ✕
        </button>
      </div>
    </div>
    {/each}
  </div>
</div>
```

**Behavior:**
- Sticky sidebar on right side of Step 3
- Shows all compared agents in chronological order
- Click card → opens comparison modal with that data (no re-fetch)
- Dismiss button removes from sidebar
- Collapses to icon when not needed (mobile)

**Alternative (Simpler):** Inline cards in Step 3 body instead of sidebar

---

### 8. Button Component Variants

**All button states needed:**

```typescript
interface ButtonProps {
  variant: 'primary' | 'secondary' | 'danger' | 'ghost'
  size: 'sm' | 'md' | 'lg'
  state: 'default' | 'loading' | 'disabled'
  icon?: string
  subtitle?: string  // Outcome/tradeoff text
  tooltip?: string   // Why disabled?
  onClick: () => void
}
```

**Visual Specifications:**

| Variant | Background | Border | Text | Use Case |
|---------|------------|--------|------|----------|
| Primary | `--accent` | None | White | Recommended action |
| Secondary | Transparent | `--border` | `--text` | Alternative action |
| Danger | Transparent | `--danger` | `--danger` | Destructive action |
| Ghost | Transparent | None | `--text-muted` | Tertiary/cancel |

**State variants:**

**Disabled with tooltip:**
```html
<button class="btn-primary" disabled 
        data-tooltip="Complete Step 3 comparison first">
  Store Agent
</button>
```

**Loading:**
```html
<button class="btn-primary loading">
  <span class="spinner"></span>
  Storing...
</button>
```

**With subtitle (outcome preview):**
```html
<button class="btn-primary">
  <span class="btn-label">Improve Quality</span>
  <span class="btn-subtitle">AI will enhance clarity (~30s)</span>
</button>
```

---

## Implementation Priority

### Phase 1: Critical Fixes (Issue #6)
1. ✅ Add `#early-diff-gate` HTML to template
2. ✅ Fix comparison modal labels ("Your Upload" vs "Existing: [Name]")
3. ✅ Fix event listener attachment

### Phase 2: Core Components (Next)
4. **Unified Progress Indicator** - Replace 7 spinners
5. **Severity Message Boxes** - Add error/warning/info system
6. **Decision Gate pattern** - Reduce button proliferation

### Phase 3: Enhancements
7. Comparison history (sidebar or inline cards)
8. Activity feed toggle (collapsed by default)
9. Disabled button tooltips

---

## Acceptance Criteria

**A successful redesign achieves:**

✅ User never sees 5+ buttons competing for attention  
✅ Error severity obvious without reading (red/amber/blue icons)  
✅ Comparison context clear ("Your Upload" vs specific agent name)  
✅ Progress transparency (what's happening, how long)  
✅ One recommended path per decision gate  
✅ Alternatives available behind click/expand  
✅ Activity feed visible but not distracting  

---

## Next Steps

1. Implement Phase 1 critical fixes (in progress on PR #7)
2. Create Phase 2 components (separate PR)
3. User test with real upload scenarios
4. Iterate based on feedback

**Status:** Design complete, Phase 1 in progress
