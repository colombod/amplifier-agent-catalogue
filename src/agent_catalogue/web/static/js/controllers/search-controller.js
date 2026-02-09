/**
 * Search Controller
 * 
 * Manages the search page functionality including HyDE semantic search,
 * result rendering, and error handling.
 * 
 * @module controllers/search-controller
 */

import { ActivityFeed } from '../components/activity-feed.js';
import { escapeHtml } from '../utils.js';

/**
 * Controller for the search page.
 * 
 * Handles:
 * - Streaming HyDE search with real-time activity feed
 * - Fallback to non-streaming search
 * - Result rendering with relevance scores
 * - Error display
 * 
 * @class
 */
export class SearchController {
    /**
     * Create a search controller.
     * 
     * @param {AnalysisAPI} api - API client instance
     */
    constructor(api) {
        this.api = api;
        this.searchNarrative = null;
    }

    /**
     * Execute search with streaming fallback.
     * 
     * @param {string} query - Search query from user
     * @param {string} feedId - Activity feed element ID
     */
    async runSearch(query, feedId) {
        if (!query) return;

        const btn = document.getElementById('search-btn');
        btn.disabled = true;
        btn.textContent = 'Searching...';

        document.getElementById('search-loading').classList.remove('hidden');
        document.getElementById('search-results').classList.add('hidden');

        // Try streaming endpoint first — shows real-time agent reasoning
        const feedEl = document.getElementById(feedId);
        const spinnerWrap = document.getElementById('search-spinner-wrap');

        feedEl.style.display = 'block';
        spinnerWrap.style.display = 'none';

        const feed = new ActivityFeed(feedId);
        try {
            const data = await feed.start('/api/stream/search-agent', { query });
            this.renderResults(data, query, 'search-results');
            btn.disabled = false;
            btn.textContent = 'Search';
            document.getElementById('search-loading').classList.add('hidden');
            return;
        } catch {
            // Streaming failed — fall through to classic endpoint
            feedEl.style.display = 'none';
            spinnerWrap.style.display = '';
        }

        // Fallback: classic non-streaming endpoint
        const phases = [
            'Understanding your query...',
            'Generating search profile...',
            'Searching the catalogue...',
            'Evaluating matches...',
            'Ranking results...'
        ];
        let idx = 0;
        this.searchNarrative = setInterval(() => {
            idx = (idx + 1) % phases.length;
            document.getElementById('search-progress').textContent = phases[idx];
        }, 2000);

        try {
            const formData = new FormData();
            formData.append('query', query);

            const response = await fetch('/api/search-agent', {
                method: 'POST',
                body: formData
            });

            if (this.searchNarrative) clearInterval(this.searchNarrative);

            if (!response.ok) {
                const error = await response.json();
                this.showError(error.detail || 'Search failed', 'search-results');
                return;
            }

            const data = await response.json();
            this.renderResults(data, query, 'search-results');

        } catch (error) {
            if (this.searchNarrative) clearInterval(this.searchNarrative);
            this.showError(error.message, 'search-results');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Search';
            document.getElementById('search-loading').classList.add('hidden');
        }
    }

    /**
     * Display error message.
     * 
     * @param {string} message - Error message to display
     * @param {string} containerId - DOM element ID to render into
     */
    showError(message, containerId) {
        document.getElementById('search-loading').classList.add('hidden');
        const container = document.getElementById(containerId);
        container.classList.remove('hidden');
        container.innerHTML = `
            <div class="card" style="margin-top: 1rem;">
                <p class="text-muted">Search error: ${message}</p>
            </div>
        `;
    }

    /**
     * Render search results.
     * 
     * @param {Object} data - Search result data with results array and hypothetical_doc
     * @param {string} query - Original search query
     * @param {string} containerId - DOM element ID to render into
     */
    renderResults(data, query, containerId) {
        const container = document.getElementById(containerId);
        container.classList.remove('hidden');

        const results = data.results || [];

        if (results.length === 0) {
            container.innerHTML = `
                <div class="empty-search">
                    <h3>No matching agents found</h3>
                    <p>No agents in the catalogue match "${escapeHtml(query)}".
                       This might be a gap worth filling.</p>
                    <a href="/upload" class="btn btn-primary">Upload an Agent</a>
                    <p class="text-muted text-sm" style="margin-top: 1rem;">
                        Have an AGENTS.md that could help? Upload it to fill this gap.
                    </p>
                </div>
            `;
            return;
        }

        let html = `<h2 class="mt-2">${results.length} result${results.length !== 1 ? 's' : ''}</h2>`;

        if (data.hypothetical_doc) {
            html += `
                <details class="hyde-doc">
                    <summary>How this search worked</summary>
                    <div class="hyde-doc-content">
                        Your query was translated into this agent profile for matching:<br>
                        "${escapeHtml(data.hypothetical_doc)}"
                    </div>
                </details>
            `;
        }

        for (const r of results) {
            const pct = Math.round((r.relevance_score || 0) * 100);
            const cls = pct >= 70 ? 'high' : pct >= 40 ? 'medium' : 'low';

            html += `
                <div class="result-card">
                    <div class="result-header">
                        <div>
                            <div class="card-title">
                                <a href="/agent/${r.slug || '#'}">${escapeHtml(r.name || 'Unknown')}</a>
                            </div>
                            <div class="card-meta">
                                ${escapeHtml(r.description || '')}${r.token_count ? ' &middot; ' + r.token_count.toLocaleString() + ' tokens' : ''}
                            </div>
                        </div>
                        <div class="result-score ${cls}">${pct}%</div>
                    </div>
                    ${r.domains && r.domains.length > 0 ? `
                        <div class="result-meta">
                            ${r.domains.map(d => `<span class="tag tag-domain">${escapeHtml(d)}</span>`).join('')}
                            ${(r.capabilities || []).slice(0, 3).map(c => `<span class="tag">${escapeHtml(c)}</span>`).join('')}
                        </div>
                    ` : ''}
                    ${r.explanation ? `<div class="result-explanation">${escapeHtml(r.explanation)}</div>` : ''}
                </div>
            `;
        }

        container.innerHTML = html;
    }

    /**
     * Set up event listeners for search page.
     * Should be called on page load.
     */
    setupEventListeners() {
        const searchInput = document.getElementById('search-input');
        const searchBtn = document.getElementById('search-btn');

        if (searchInput) {
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const query = searchInput.value.trim();
                    this.runSearch(query, 'search-activity-feed');
                }
            });
        }

        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                const query = searchInput.value.trim();
                this.runSearch(query, 'search-activity-feed');
            });
        }
    }
}
