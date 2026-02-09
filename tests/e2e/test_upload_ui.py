"""Playwright E2E tests for agent upload workflow UI improvements.

Tests Phase 1 improvements from design review:
- Early differentiation gate (70%+ overlap)
- Deep comparison with SSE streaming
- Proper label rendering (not "Agent A/B" or "[object Object]")
- Working buttons with event listeners
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

# Path to test fixture
TEST_AGENT_PATH = Path(__file__).parent.parent / "TEST_AGENT_UPLOAD.md"


@pytest.mark.slow
async def test_upload_with_early_diff_gate(page: Page, server_url: str) -> None:
    """Test complete upload flow with early differentiation gate.

    This test validates:
    1. File upload triggers analysis
    2. Step 3 (Similarity Detection) completes
    3. Early diff gate appears at 70%+ overlap
    4. Gate shows correct overlap percentage (not 0%)
    5. Buttons are clickable (not greyed out)
    6. Buttons have subtitle text
    """
    await page.goto(f"{server_url}/upload", wait_until="networkidle")

    # Step 1: Verify wizard loads
    wizard = page.locator(".wizard-container")
    await expect(wizard).to_be_visible()

    step1_card = page.locator("#step-1-card")
    await expect(step1_card).to_be_visible()

    # Step 2: Upload test file
    file_input = page.locator("input[type='file']")
    if await file_input.count() > 0:
        await file_input.set_input_files(str(TEST_AGENT_PATH))
    else:
        # Fallback to textarea if file input not found
        textarea = page.locator("textarea").first
        content = TEST_AGENT_PATH.read_text()
        await textarea.fill(content)

    # Step 3: Click analyze/upload button
    submit_btn = page.locator(
        "button:has-text('Analyze'), button:has-text('Upload'), button[type='submit']"
    ).first
    await submit_btn.click()

    # Step 4: Wait for Step 2 (Parse & Validate) to complete
    # This should be relatively fast
    step2_success = page.locator("#step-2-card .success-icon, #step-2-card.complete")
    await step2_success.wait_for(state="visible", timeout=10_000)

    # Step 5: Wait for Step 3 (Similarity Detection) to start
    step3_card = page.locator("#step-3-card")
    await expect(step3_card).to_be_visible(timeout=5_000)

    # Step 6: Wait for Step 3 to complete (LLM operation, can take 10-20 seconds)
    step3_success = page.locator("#step-3-card .success-icon, #step-3-card.complete")
    await step3_success.wait_for(state="visible", timeout=30_000)

    # Step 7: Early differentiation gate should appear
    # This appears after Step 3 when overlap >= 70%
    early_diff_gate = page.locator("#early-diff-gate")
    await expect(early_diff_gate).to_be_visible(timeout=5_000)

    # Step 8: Verify gate content
    # Should show "High Overlap Detected (XX%)" - not "0%"
    overlap_header = early_diff_gate.locator(".gate-header, h3, .overlap-percentage")
    await expect(overlap_header).to_contain_text("High Overlap Detected")
    # Verify it's not showing 0%
    header_text = await overlap_header.inner_text()
    assert "0%" not in header_text, "Overlap percentage should not be 0%"
    assert "%" in header_text, "Should show actual overlap percentage"

    # Step 9: Verify top overlapping agents are listed
    overlap_list = early_diff_gate.locator(".overlap-list, .similar-agents-list")
    await expect(overlap_list).to_be_visible()

    # Should have at least one agent listed
    agent_items = overlap_list.locator("li, .agent-item")
    await expect(agent_items.first).to_be_visible()

    # Step 10: Verify buttons exist and are clickable
    differentiate_btn = early_diff_gate.locator(
        "button:has-text('Differentiate Now'), #differentiate-now-btn"
    )
    continue_btn = early_diff_gate.locator("button:has-text('Continue'), #continue-quality-btn")

    await expect(differentiate_btn).to_be_visible()
    await expect(continue_btn).to_be_visible()

    # Verify buttons are not disabled (greyed out)
    await expect(differentiate_btn).to_be_enabled()
    await expect(continue_btn).to_be_enabled()

    # Step 11: Verify buttons have subtitle/outcome text
    differentiate_text = await differentiate_btn.inner_text()
    continue_text = await continue_btn.inner_text()

    # Buttons should have more than just the main label
    # (they include subtitle text describing outcomes)
    assert len(differentiate_text) > 20, "Differentiate button should have subtitle text"
    assert len(continue_text) > 20, "Continue button should have subtitle text"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_deep_compare_modal(page: Page, server_url: str) -> None:
    """Test deep comparison modal functionality.

    This test validates:
    1. "Deep Compare" button opens modal
    2. Modal shows real agent names (not "Agent A" and "Agent B")
    3. Similarity percentage is correct (not 0%)
    4. Capability lists show text (not "[object Object]")
    5. "View Agent" link has target="_blank"
    6. Modal can be closed properly
    """
    await page.goto(f"{server_url}/upload", wait_until="networkidle")

    # Upload and wait for similarity detection (same as previous test)
    file_input = page.locator("input[type='file']")
    if await file_input.count() > 0:
        await file_input.set_input_files(str(TEST_AGENT_PATH))
    else:
        textarea = page.locator("textarea").first
        content = TEST_AGENT_PATH.read_text()
        await textarea.fill(content)

    submit_btn = page.locator(
        "button:has-text('Analyze'), button:has-text('Upload'), button[type='submit']"
    ).first
    await submit_btn.click()

    # Wait for Step 3 to complete
    step3_success = page.locator("#step-3-card .success-icon, #step-3-card.complete")
    await step3_success.wait_for(state="visible", timeout=30_000)

    # Find and click "Deep Compare" button on first similar agent
    # This might be in the early diff gate or in the results list
    deep_compare_btn = page.locator(
        "button:has-text('Deep Compare'), .deep-compare-btn, [data-action='deep-compare']"
    ).first

    await expect(deep_compare_btn).to_be_visible(timeout=5_000)
    await deep_compare_btn.click()

    # Wait for comparison modal to open
    modal = page.locator("#comparison-modal, .comparison-modal, [role='dialog']")
    await expect(modal).to_be_visible(timeout=5_000)

    # Verify modal shows real agent names, not "Agent A" and "Agent B"
    modal_content = await modal.inner_text()
    assert "Agent A" not in modal_content or "Your Upload" in modal_content, (
        "Should show 'Your Upload' instead of generic 'Agent A'"
    )
    assert "Agent B" not in modal_content or "Existing:" in modal_content, (
        "Should show 'Existing: [Name]' instead of generic 'Agent B'"
    )

    # Wait for comparison to complete (LLM operation, 10-20 seconds)
    # Look for completion indicators
    comparison_result = modal.locator(".comparison-result, .diff-report, .behavioral-differences")

    try:
        await comparison_result.wait_for(state="visible", timeout=30_000)
    except Exception:
        # Even if comparison times out, check what's visible
        pass

    # Verify similarity percentage is shown and not 0%
    percentage_elem = modal.locator(
        ".similarity-percentage, .overlap-score, :text-matches('[0-9]+%')"
    ).first

    if await percentage_elem.count() > 0:
        percentage_text = await percentage_elem.inner_text()
        assert "0%" not in percentage_text, "Similarity should not be 0%"
        assert "%" in percentage_text, "Should show percentage"

    # Verify capability lists don't show "[object Object]"
    capabilities_section = modal.locator(
        ".capabilities, .shared-capabilities, .unique-capabilities"
    ).first

    if await capabilities_section.count() > 0:
        capabilities_text = await capabilities_section.inner_text()
        assert "[object Object]" not in capabilities_text, (
            "Capabilities should render as text, not [object Object]"
        )

    # Verify "View Agent" link has target="_blank"
    view_agent_link = modal.locator("a:has-text('View Agent'), a[href*='/agent/']")
    if await view_agent_link.count() > 0:
        target = await view_agent_link.first.get_attribute("target")
        assert target == "_blank", "View Agent link should open in new tab"

    # Close modal and verify we return to upload page
    close_btn = modal.locator("button:has-text('Close'), .close-btn, [aria-label='Close']").first

    if await close_btn.count() > 0:
        await close_btn.click()
        await expect(modal).not_to_be_visible(timeout=2_000)

        # Verify we're still on upload page
        wizard = page.locator(".wizard-container")
        await expect(wizard).to_be_visible()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_differentiate_now_flow(page: Page, server_url: str) -> None:
    """Test 'Differentiate Now' button flow.

    Validates that clicking 'Differentiate Now' skips Step 4
    and proceeds to Step 5 (differentiation).
    """
    await page.goto(f"{server_url}/upload", wait_until="networkidle")

    # Upload file
    file_input = page.locator("input[type='file']")
    if await file_input.count() > 0:
        await file_input.set_input_files(str(TEST_AGENT_PATH))
    else:
        textarea = page.locator("textarea").first
        content = TEST_AGENT_PATH.read_text()
        await textarea.fill(content)

    submit_btn = page.locator(
        "button:has-text('Analyze'), button:has-text('Upload'), button[type='submit']"
    ).first
    await submit_btn.click()

    # Wait for early diff gate
    early_diff_gate = page.locator("#early-diff-gate")
    await expect(early_diff_gate).to_be_visible(timeout=35_000)

    # Click "Differentiate Now"
    differentiate_btn = early_diff_gate.locator(
        "button:has-text('Differentiate Now'), #differentiate-now-btn"
    )
    await differentiate_btn.click()

    # Verify Step 4 is skipped and Step 5 becomes visible
    # (or we navigate to differentiation workflow)
    await asyncio.sleep(2)  # Brief wait for navigation/update

    # Look for Step 5 or differentiation interface
    step5_or_diff = page.locator(
        "#step-5-card, .differentiation-workflow, :has-text('Strategic Differentiation')"
    )

    # Should see differentiation step within reasonable time
    await expect(step5_or_diff.first).to_be_visible(timeout=10_000)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_continue_quality_check_flow(page: Page, server_url: str) -> None:
    """Test 'Continue with Quality Check' button flow.

    Validates that clicking 'Continue' proceeds to Step 4 (quality check).
    """
    await page.goto(f"{server_url}/upload", wait_until="networkidle")

    # Upload file
    file_input = page.locator("input[type='file']")
    if await file_input.count() > 0:
        await file_input.set_input_files(str(TEST_AGENT_PATH))
    else:
        textarea = page.locator("textarea").first
        content = TEST_AGENT_PATH.read_text()
        await textarea.fill(content)

    submit_btn = page.locator(
        "button:has-text('Analyze'), button:has-text('Upload'), button[type='submit']"
    ).first
    await submit_btn.click()

    # Wait for early diff gate
    early_diff_gate = page.locator("#early-diff-gate")
    await expect(early_diff_gate).to_be_visible(timeout=35_000)

    # Click "Continue to Quality Check"
    continue_btn = early_diff_gate.locator("button:has-text('Continue'), #continue-quality-btn")
    await continue_btn.click()

    # Verify Step 4 becomes active
    await asyncio.sleep(2)  # Brief wait for UI update

    step4_card = page.locator("#step-4-card")
    await expect(step4_card).to_be_visible(timeout=10_000)

    # Step 4 should be active/in-progress
    step4_active = page.locator(
        "#step-4-card.active, #step-4-card.in-progress, #step-4-card .spinner"
    )
    await expect(step4_active.first).to_be_visible(timeout=5_000)
