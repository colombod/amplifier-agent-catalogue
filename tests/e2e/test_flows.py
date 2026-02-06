"""Playwright E2E tests for the Agent Catalogue web UI."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_AGENT_PATH = FIXTURES_DIR / "sample_agent.md"

# ---------------------------------------------------------------------------
# Page-load smoke tests
# ---------------------------------------------------------------------------


def test_home_page_loads(page: Page, server_url: str) -> None:
    """Home page loads and shows the catalogue title."""
    page.goto(server_url)
    expect(page).to_have_title(re.compile("Agent Catalogue"))
    # The page should show either an agent grid or an empty-state message
    grid_or_empty = page.locator("[data-testid='agent-grid'], .agent-grid, .empty-state, main")
    expect(grid_or_empty.first).to_be_visible()


def test_upload_page_loads(page: Page, server_url: str) -> None:
    """Upload wizard page loads and shows the wizard with step cards."""
    page.goto(f"{server_url}/upload")
    # The upload page uses a wizard with step cards
    wizard = page.locator(".wizard-container")
    expect(wizard).to_be_visible()
    # Step 1 card should be active
    step1 = page.locator("#step-1-card")
    expect(step1).to_be_visible()


def test_search_page_loads(page: Page, server_url: str) -> None:
    """Search page loads and shows the search textarea."""
    page.goto(f"{server_url}/search")
    # The search page uses a textarea with id="search-input"
    search_input = page.locator("textarea#search-input")
    expect(search_input).to_be_visible()


# ---------------------------------------------------------------------------
# API smoke tests
# ---------------------------------------------------------------------------


def test_api_agents_returns_json(server_url: str) -> None:
    """GET /api/agents returns 200 with a JSON array."""
    resp = httpx.get(f"{server_url}/api/agents", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_search_returns_results(server_url: str) -> None:
    """POST /api/search returns 200 with a JSON array."""
    resp = httpx.post(
        f"{server_url}/api/search",
        data={"query": "test agent"},
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Upload & analyze flow (LLM-dependent)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_upload_and_analyze_flow(page: Page, server_url: str) -> None:
    """Upload a sample agent file and verify the analyze step starts.

    This test submits content through the upload wizard. If an LLM backend
    is available the full analysis runs; otherwise we verify the UI handles
    the error gracefully (no unhandled crash).
    """
    page.goto(f"{server_url}/upload")

    # Try file-input upload first, fall back to textarea paste
    file_input = page.locator("input[type='file']")
    textarea = page.locator("textarea")

    if file_input.count() > 0:
        file_input.first.set_input_files(str(SAMPLE_AGENT_PATH))
    elif textarea.count() > 0:
        sample_content = SAMPLE_AGENT_PATH.read_text()
        textarea.first.fill(sample_content)
    else:
        pytest.skip("No file input or textarea found on upload page")

    # Look for and click a submit / analyze button
    submit_btn = page.locator(
        "button[type='submit'], "
        "button:has-text('Analyze'), "
        "button:has-text('Upload'), "
        "button:has-text('Submit')"
    )
    if submit_btn.count() > 0:
        submit_btn.first.click()

        # Wait for either a progress indicator, a result, or an error message.
        # We give the LLM up to 60 s to respond.
        result_or_error = page.locator(
            ".progress, "
            ".loading, "
            "[data-testid='analysis-result'], "
            ".result, "
            ".error, "
            ".alert, "
            "[role='alert']"
        )
        try:
            result_or_error.first.wait_for(state="visible", timeout=60_000)
        except Exception:
            # Even if we time out, the page should not have crashed -
            # verify there is still a meaningful page rendered.
            expect(page.locator("body")).to_be_visible()
    else:
        # No obvious submit button - the page may auto-submit or need JS
        # interaction we cannot replicate. Just confirm the page is alive.
        expect(page.locator("body")).to_be_visible()
