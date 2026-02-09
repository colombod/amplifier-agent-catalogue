# Voice & Tone Strategy: Agent Upload Workflow

**Created:** 2026-02-08  
**Status:** Active  
**Audience:** Technical users (developers, AI practitioners)

---

## Voice Definition

**Our voice for this workflow is:**

- **Transparent** - Explain operations, not just that they're happening
- **Directive** - Guide decisions with clear recommendations
- **Technically honest** - Use accurate terms, not simplified metaphors
- **Confidence-building** - Provide context for informed choices

**Our voice is NOT:**

- Hand-holding or overly simplified
- Uncertain (avoiding "might", "maybe", "could be")
- Jargon-heavy without purpose
- Corporate or robotic

---

## Message Patterns

### Progress States (Transparency Pattern)

**Formula:** [Operation] + [What we're doing] + [Duration if >15s]

✅ **Examples:**
```
Analyzing agent definition...
• Extracting metadata
• Validating schema structure
• Detecting dependencies

Comparing with 47 existing agents...
Using semantic similarity (typically 15-20 seconds)

Improving agent quality with AI assistance...
• Enhancing description clarity
• Adding usage examples
• Strengthening instructions
(30-45 seconds)
```

❌ **Avoid:**
- "Please wait..."
- "Processing..."
- "Loading..."

---

### Error Severity Levels

#### 🔴 Blocking Error
**Formula:** "**Cannot proceed:** [What's wrong] [What to do]"

```
❌ **Cannot proceed:** Agent name is required
Add a name to your agent definition before uploading
```

#### 🟡 Warning (Recommended fix)
**Formula:** "**Recommended fix:** [Issue] [Action]"

```
⚠️ **Recommended fix:** Similar agent exists (89% match)
Review comparison to avoid duplication

[View Comparison] [Store Anyway]
```

#### 🔵 Info (Safe to ignore)
**Formula:** "**Note:** [Information]"

```
ℹ️ **Note:** No tags specified
You can add tags later for discoverability
```

---

### Comparison Labels

**Pattern:** "Your Upload" vs "Existing: [Agent Name]"

✅ **Correct:**
- "Your Upload vs Existing: Customer Support Assistant"
- "Comparing: Your Agent vs CSV DSL Development Assistant"

❌ **Avoid:**
- "Agent A vs Agent B"
- "New vs Old"
- "Original vs Duplicate"

---

### Button Copy Guidelines

| Scenario | Button Copy | Rationale |
|----------|-------------|-----------|
| Progression | "Continue" | Neutral forward |
| Final commit | "Store Agent" | Specific, clear |
| Recommendation | [Specific action] | "Improve Quality", "View Comparison" |
| Override warning | "Store Anyway" | Acknowledges bypass |
| Cancel | "Cancel Upload" | Workflow-specific |

---

## Word Choices

| Instead of | Say | Why |
|------------|-----|-----|
| Processing | Analyzing, Comparing | Specific operation |
| Error | Cannot proceed (blocking), Recommended fix (warning) | Clear severity |
| Proceed | Continue, Store Agent | Context-appropriate |
| Agent A/B | Your Upload, Existing: [name] | Clear ownership |
| May take a while | Typically 15-20 seconds | Concrete |

---

**Last updated:** 2026-02-08
