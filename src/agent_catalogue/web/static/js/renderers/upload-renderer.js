/**
 * Upload Renderer Module
 * 
 * Handles ALL display and rendering functions for the upload wizard.
 * Pure rendering - no business logic or state mutation.
 * 
 * @module renderers/upload-renderer
 */

import { escapeHtml } from '../utils.js';

/**
 * Renders UI elements for the upload wizard flow.
 * 
 * @class
 */
export class UploadRenderer {
    constructor() {
        this.escapeHtml = escapeHtml;
    }

    /**
     * Display duplication banner based on similarity score.
     * 
     * @param {number} similarity - Similarity score (0-1)
     * @param {string} agentName - Name of similar agent
     */
    showDuplicationBanner(similarity, agentName) {
        const banner = document.getElementById('duplication-banner');
        banner.classList.remove('hidden', 'high', 'medium');

        if (similarity >= 0.8) {
            banner.classList.add('high');
            document.getElementById('banner-icon').textContent = '🚨';
            document.getElementById('banner-title').textContent = `High Duplication: ${Math.round(similarity * 100)}% match`;
            document.getElementById('banner-subtitle').textContent = `Very similar to "${agentName}" - deep comparison required`;
        } else {
            banner.classList.add('medium');
            document.getElementById('banner-icon').textContent = '⚠️';
            document.getElementById('banner-title').textContent = `Similar Agent Found: ${Math.round(similarity * 100)}% match`;
            document.getElementById('banner-subtitle').textContent = `Overlaps with "${agentName}" - review recommended`;
        }
    }

    /**
     * Display analysis results in Step 2.
     * 
     * @param {Object} data - Analysis data from API
     * @param {Object} steps - WizardSteps instance
     * @param {Object} state - WizardState instance
     */
    displayAnalysis(data, steps, state) {
        console.log('[Render] displayAnalysis called', {
            agentName: data.metadata?.name,
            domains: data.metadata?.domains,
            capabilities: data.metadata?.capabilities?.length,
            similarCount: data.similar_agents?.length,
            isDuplicate: data.is_duplicate
        });
        const meta = data.metadata;

        // Defensive: ensure arrays exist to prevent .map() crashes
        meta.domains = meta.domains || [];
        meta.capabilities = meta.capabilities || [];
        meta.tools = meta.tools || [];

        console.log('displayAnalysis called with:', {
            hasMetadata: !!meta,
            name: meta.name,
            fieldCount: Object.keys(meta).length
        });

        // Step 1: Mark completed
        steps.setStepState(1, 'completed');

        // Step 2: Show analysis
        steps.setStepState(2, 'completed');
        steps.setStepSummary(2, meta.name);
        document.getElementById('step-2-empty').classList.add('hidden');
        document.getElementById('step-2-content').classList.remove('hidden');

        document.getElementById('metadata-display').innerHTML = `
            <dt>Name</dt><dd>${meta.name || 'Unknown'}</dd>
            <dt>Purpose</dt><dd>${meta.purpose || 'Not specified'}</dd>
            <dt>Complexity</dt><dd>${meta.complexity || 'moderate'}</dd>
            <dt>Autonomy</dt><dd>${meta.autonomy || 'hybrid'}</dd>
            <dt>Domains</dt><dd><div class="tag-list">${meta.domains.map(d => `<span class="tag tag-domain">${d}</span>`).join('') || '<em>None</em>'}</div></dd>
            <dt>Capabilities</dt><dd><div class="tag-list">${meta.capabilities.map(c => `<span class="tag">${c}</span>`).join('') || '<em>None</em>'}</div></dd>
            <dt>Tools</dt><dd><div class="tag-list">${meta.tools.map(t => `<span class="tag tag-tool">${t}</span>`).join('') || '<em>None</em>'}</div></dd>
        `;

        // Step 3: Handle similar agents
        document.getElementById('step-3-empty').classList.add('hidden');
        document.getElementById('step-3-content').classList.remove('hidden');

        if (data.similar_agents && data.similar_agents.length > 0) {
            state.highestSimilarity = Math.max(...data.similar_agents.map(s => s.similarity_score));
            steps.setStepSummary(3, `${data.similar_agents.length} similar found (${Math.round(state.highestSimilarity * 100)}% max)`);

            // Render similar agents list
            document.getElementById('similar-list').innerHTML = data.similar_agents.map(s => this.renderSimilarAgent(s, state)).join('');
        } else {
            // No similar agents
            steps.setStepSummary(3, 'No similar agents');
            document.getElementById('similar-list').innerHTML = `
                <div class="decision-box success">
                    <div class="decision-title">✓ Unique Agent</div>
                    <div>No similar agents found in the catalogue. This appears to be a new, distinct agent.</div>
                </div>
            `;
            steps.setStepState(3, 'completed');
        }
    }

    /**
     * Display quality evaluation results.
     * 
     * @param {Object} data - Evaluation data from API
     */
    displayQualityEvaluation(data) {
        document.getElementById('step-4-loading').classList.add('hidden');
        document.getElementById('step-4-content').classList.remove('hidden');

        const grade = data.grade || 'C';
        const score = data.overall_score || 5.0;
        const label = data.grade_label || grade;

        // Grade badge + summary
        document.getElementById('quality-header').innerHTML = `
            <div class="grade-badge grade-${grade}">
                <span class="grade-letter">${grade}</span>
                <span class="grade-score">${score.toFixed(1)}/10</span>
            </div>
            <div class="quality-summary-text">
                <h3>${label}</h3>
                <p>${data.summary || ''}</p>
            </div>
        `;

        // Dimension bars
        const dims = data.dimensions || {};
        const dimOrder = ['clarity', 'completeness', 'specificity', 'consistency', 'differentiation'];
        let dimsHtml = '';
        for (const name of dimOrder) {
            const dim = dims[name];
            if (!dim) continue;
            const s = dim.score || 0;
            const pct = (s / 10) * 100;
            const barClass = s >= 7 ? 'high' : s >= 5 ? 'medium' : 'low';
            dimsHtml += `
                <div class="dimension-row">
                    <span class="dimension-label">${name}</span>
                    <div class="dimension-bar-track">
                        <div class="dimension-bar-fill ${barClass}" style="width: ${pct}%"></div>
                    </div>
                    <span class="dimension-score">${s.toFixed(1)}</span>
                </div>
            `;
        }
        document.getElementById('dimensions-display').innerHTML = dimsHtml;

        // Strengths
        const strengths = data.strengths || [];
        document.getElementById('strengths-display').innerHTML = strengths.length > 0
            ? strengths.map(s => `<span class="strength-tag">${s}</span>`).join('')
            : '';

        // Token metrics
        if (data.token_metrics) {
            this.renderTokenPanel('token-metrics-panel', data.token_metrics);
            document.getElementById('token-metrics-panel').classList.remove('hidden');
        }

        // Issues
        const issues = data.issues || [];
        if (issues.length > 0) {
            const critical = issues.filter(i => i.severity === 'critical').length;
            const major = issues.filter(i => i.severity === 'major').length;
            const minor = issues.filter(i => i.severity === 'minor').length;

            let issueCountText = [];
            if (critical) issueCountText.push(`${critical} critical`);
            if (major) issueCountText.push(`${major} major`);
            if (minor) issueCountText.push(`${minor} minor`);

            let issuesHtml = `<h4>${issues.length} issue${issues.length > 1 ? 's' : ''} found (${issueCountText.join(', ')})</h4>`;
            for (const issue of issues) {
                issuesHtml += `
                    <div class="issue-card ${issue.severity}" onclick="this.classList.toggle('expanded')">
                        <div class="issue-severity">${issue.severity}</div>
                        <div class="issue-description">${issue.description || ''}</div>
                        ${issue.suggestion ? `
                            <div class="issue-suggestion">
                                <strong>Suggestion:</strong> ${issue.suggestion}
                                ${issue.location ? `<br><em>Location: ${issue.location}</em>` : ''}
                            </div>
                        ` : ''}
                    </div>
                `;
            }
            document.getElementById('issues-display').innerHTML = issuesHtml;
        } else {
            document.getElementById('issues-display').innerHTML = '';
        }
    }

    /**
     * Show quality decision choices.
     * 
     * @param {Object} data - Quality evaluation data
     */
    showQualityChoices(data) {
        const choices = document.getElementById('quality-choices');
        choices.classList.remove('hidden');

        const hasIssues = data && data.issues && data.issues.length > 0;
        const estScore = data && data.estimated_improved_score
            ? data.estimated_improved_score.toFixed(1)
            : '?';
        const estGrade = data && data.estimated_improved_grade
            ? data.estimated_improved_grade
            : '?';

        choices.innerHTML = `
            <div class="choice-card" id="store-current-choice">
                <div class="choice-card-title">Store Current Version</div>
                <div class="choice-card-desc">
                    Add this agent to the catalogue with its current definition.
                </div>
                <div class="choice-card-detail">
                    Grade: ${data ? data.grade : 'N/A'} (${data ? data.overall_score.toFixed(1) : '?'}/10)
                </div>
            </div>
            <div class="choice-card" id="improve-then-store-choice" ${!hasIssues ? 'style="opacity:0.5;pointer-events:none"' : ''}>
                <div class="choice-card-title">Improve, Then Store</div>
                <div class="choice-card-desc">
                    Generate an improved version and review changes before storing.
                </div>
                <div class="choice-card-detail">
                    ${hasIssues ? `Could reach ${estGrade} · takes ~15 seconds` : 'No issues found'}
                </div>
            </div>
        `;
    }

    /**
     * Show improvement error message.
     * 
     * @param {string} message - Error message
     */
    showImproveError(message) {
        document.getElementById('step-4-improve').classList.add('hidden');
        document.getElementById('quality-choices').classList.remove('hidden');
        const prevImpErr = document.getElementById('improve-error');
        if (prevImpErr) prevImpErr.remove();
        document.getElementById('issues-display').insertAdjacentHTML('afterend',
            `<div class="decision-box danger" id="improve-error">
                <div class="decision-title">Improvement unavailable</div>
                <div>${message}</div>
            </div>`);
    }

    /**
     * Render token efficiency panel.
     * 
     * @param {string} elementId - DOM element ID to render into
     * @param {Object} metrics - Token metrics from API
     * @param {string} label - Optional label override
     */
    renderTokenPanel(elementId, metrics, label) {
        const el = document.getElementById(elementId);
        if (!el || !metrics) return;

        const colors = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff', '#f778ba', '#79c0ff', '#56d364'];
        const sections = metrics.sections || [];

        // Section bar segments
        let barHtml = '';
        sections.forEach((s, i) => {
            const color = colors[i % colors.length];
            if (s.pct_of_total > 0) {
                barHtml += `<div class="token-section-bar" style="width:${s.pct_of_total}%;background:${color}" title="${s.heading}: ${s.tokens} tokens (${s.pct_of_total}%)"></div>`;
            }
        });

        el.innerHTML = `
            <div class="token-panel">
                <div class="token-panel-title">
                    ${label || 'Token Efficiency'}
                    <span class="token-budget-badge ${metrics.budget_category}">${metrics.budget_label}</span>
                </div>
                <div class="token-stats">
                    <div class="token-stat">
                        <span class="token-stat-value">${metrics.total_tokens.toLocaleString()}</span>
                        <span class="token-stat-label">Tokens</span>
                    </div>
                    <div class="token-stat">
                        <span class="token-stat-value">${metrics.total_lines}</span>
                        <span class="token-stat-label">Lines</span>
                    </div>
                    <div class="token-stat">
                        <span class="token-stat-value">${metrics.tokens_per_line}</span>
                        <span class="token-stat-label">Tokens/Line</span>
                    </div>
                </div>
                ${barHtml ? `<div class="token-sections">${barHtml}</div>` : ''}
                <div class="token-recommendation">${metrics.recommendation}</div>
            </div>
        `;
    }

    /**
     * Render token comparison (before vs after).
     * 
     * @param {string} elementId - DOM element ID
     * @param {Object} original - Original token metrics
     * @param {Object} improved - Improved token metrics
     */
    renderTokenComparison(elementId, original, improved) {
        const el = document.getElementById(elementId);
        if (!el || !original || !improved) return;

        const delta = improved.total_tokens - original.total_tokens;
        const pctChange = original.total_tokens > 0
            ? Math.round((delta / original.total_tokens) * 100)
            : 0;
        const deltaClass = delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral';
        const deltaSign = delta > 0 ? '+' : '';
        const deltaLabel = delta === 0 ? 'no change' : `${deltaSign}${delta} tokens (${deltaSign}${pctChange}%)`;

        el.innerHTML = `
            <div class="token-panel">
                <div class="token-panel-title">
                    Token Efficiency
                    <span class="token-budget-badge ${improved.budget_category}">${improved.budget_label}</span>
                    <span class="token-delta ${deltaClass}">${deltaLabel}</span>
                </div>
                <div class="token-stats">
                    <div class="token-stat">
                        <span class="token-stat-value">${original.total_tokens.toLocaleString()}</span>
                        <span class="token-stat-label">Original</span>
                    </div>
                    <div class="token-stat">
                        <span class="token-stat-value">${improved.total_tokens.toLocaleString()}</span>
                        <span class="token-stat-label">Improved</span>
                    </div>
                    <div class="token-stat">
                        <span class="token-stat-value">${improved.total_lines}</span>
                        <span class="token-stat-label">Lines</span>
                    </div>
                </div>
                <div class="token-recommendation">${improved.recommendation}</div>
            </div>
        `;
        el.classList.remove('hidden');
    }

    /**
     * Render section-level improvement diff.
     * 
     * @param {Array} changes - Array of change objects
     */
    renderImprovementDiff(changes) {
        const container = document.getElementById('improve-diff-display');
        if (!changes || changes.length === 0) {
            container.innerHTML = '<p class="text-muted">No changes detected.</p>';
            return;
        }

        let html = '';
        for (const change of changes) {
            if (change.type === 'unchanged') continue;

            const badgeClass = change.type;
            const badgeLabel = change.type === 'modified' ? 'Modified'
                : change.type === 'added' ? 'Added' : 'Removed';

            html += `
                <div class="diff-section" onclick="this.classList.toggle('collapsed')">
                    <div class="diff-section-header">
                        <span>${change.section}</span>
                        <span class="diff-badge ${badgeClass}">${badgeLabel}</span>
                    </div>
                    <div class="diff-section-body">`;

            if (change.type === 'modified') {
                // Show removed lines then added lines
                for (const line of (change.original_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-removed">- ${escapeHtml(line)}</div>`;
                }
                html += '<hr style="border-color: var(--border); margin: 0.5rem 0;">';
                for (const line of (change.improved_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-added">+ ${escapeHtml(line)}</div>`;
                }
            } else if (change.type === 'added') {
                for (const line of (change.improved_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-added">+ ${escapeHtml(line)}</div>`;
                }
            } else if (change.type === 'removed') {
                for (const line of (change.original_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-removed">- ${escapeHtml(line)}</div>`;
                }
            }

            html += `</div></div>`;
        }

        container.innerHTML = html || '<p class="text-muted">No meaningful changes.</p>';
    }

    /**
     * Render a similar agent card.
     * 
     * @param {Object} similar - Similar agent data
     * @param {Object} state - WizardState instance
     * @returns {string} HTML string
     */
    renderSimilarAgent(similar, state) {
        const score = similar.similarity_score;
        const scoreClass = score >= 0.8 ? 'high' : score >= 0.6 ? 'medium' : 'low';
        const cardClass = score >= 0.8 ? 'high-overlap' : score >= 0.6 ? 'medium-overlap' : '';
        const isCompared = state.comparedAgents[similar.agent.id];

        return `
            <div class="similar-agent ${cardClass} ${isCompared ? 'compared' : ''}" id="similar-${similar.agent.id}">
                <div class="similar-score ${scoreClass}">${Math.round(score * 100)}%</div>
                <div class="similar-info">
                    <div class="similar-name">
                        <a href="/agent/${similar.agent.slug}">${similar.agent.name}</a>
                        <span class="text-muted text-sm">v${similar.agent.current_version}</span>
                        ${isCompared ? '<span class="compared-badge">✓ Compared</span>' : ''}
                    </div>
                    <div class="similar-desc">${similar.agent.description || 'No description'}</div>
                    <div class="similar-actions">
                        <button class="btn btn-sm btn-compare" data-action="deepCompare" data-agent-id="${similar.agent.id}" data-agent-name="${similar.agent.name}">
                            🔬 ${isCompared ? 'Compare Again' : 'Deep Compare'}
                        </button>
                        ${isCompared ? `
                            <button class="btn btn-sm btn-view-comparison" data-action="viewStoredComparison" data-agent-id="${similar.agent.id}">
                                👁️ View Result
                            </button>
                        ` : ''}
                        <a href="/agent/${similar.agent.slug}" target="_blank" class="btn btn-sm">View Agent ↗</a>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Show early differentiation gate.
     * 
     * @param {Array} similarAgents - Similar agents data
     * @param {number} highestSimilarity - Highest similarity score
     * @param {Object} state - WizardState instance
     */
    showEarlyDifferentiationGate(similarAgents, highestSimilarity, state) {
        console.log('[Render] showEarlyDifferentiationGate', {
            agentCount: similarAgents.length,
            similarity: (highestSimilarity * 100).toFixed(1) + '%',
            topAgents: similarAgents.slice(0, 3).map(s => ({
                name: s.agent.name,
                similarity: (s.similarity_score * 100).toFixed(1) + '%'
            }))
        });

        const gateEl = document.getElementById('early-diff-gate');
        const summaryEl = document.getElementById('overlap-summary');
        const percentageEl = document.getElementById('overlap-percentage');

        // Update percentage display
        if (percentageEl) {
            percentageEl.textContent = (highestSimilarity * 100).toFixed(0);
        }

        // CRITICAL: Store overlap agents for pattern buttons to use
        window._lastOverlapAgents = similarAgents.map(s => ({
            id: s.agent.id,
            name: s.agent.name,
            description: s.agent.description || '',
            capabilities: s.agent.capabilities || [],
            domains: s.agent.domains || [],
            tools: [],
            similarity_score: s.similarity_score,
        }));

        // Build overlap summary
        const topAgents = similarAgents.slice(0, 3);
        const summaryHtml = `
            <p>Your agent overlaps significantly with existing agents:</p>
            <ul style="margin: 0.5rem 0; padding-left: 1.5rem;">
                ${topAgents.map(s => `
                    <li style="margin: 0.25rem 0;">
                        <strong>${s.agent.name}</strong> 
                        (${(s.similarity_score * 100).toFixed(0)}% similar)
                        ${s.agent.capabilities ?
                            `<br><span style="font-size: 0.85em; color: var(--text-muted);">Shared: ${s.agent.capabilities.slice(0, 3).join(', ')}${s.agent.capabilities.length > 3 ? ', ...' : ''}</span>`
                            : ''}
                    </li>
                `).join('')}
            </ul>
        `;

        summaryEl.innerHTML = summaryHtml;
        gateEl.classList.remove('hidden');

        // Hide compare prompt since we're showing differentiation gate
        document.getElementById('compare-prompt').classList.add('hidden');
    }

    /**
     * Show refined content after Pattern 1 or Pattern 2 differentiation.
     * 
     * @param {string} refinedContent - The differentiated AGENTS.md content
     * @param {Array} changes - List of change objects (optional)
     */
    showRefinedContent(refinedContent, changes = []) {
        const displayEl = document.getElementById('refined-content-display');
        const previewEl = document.getElementById('refined-content-preview');
        const changesEl = document.getElementById('refined-changes-display');
        
        if (!displayEl || !previewEl) return;
        
        // Show full refined content in preview
        previewEl.innerHTML = `<pre style="white-space: pre-wrap; background: var(--bg-secondary); padding: 1rem; border-radius: 4px; max-height: 400px; overflow-y: auto; font-size: 0.85rem;">${this.escapeHtml(refinedContent)}</pre>`;
        
        // Show changes if available
        if (changes && changes.length > 0 && changesEl) {
            this.renderChangesIntoContainer(changes, changesEl);
        }
        
        displayEl.classList.remove('hidden');
    }

    /**
     * Render changes diff into a specific container.
     * 
     * @param {Array} changes - List of change objects
     * @param {HTMLElement} container - Target container element
     */
    renderChangesIntoContainer(changes, container) {
        if (!changes || changes.length === 0) {
            container.innerHTML = '<p class="text-muted">No changes detected.</p>';
            return;
        }

        let html = '';
        for (const change of changes) {
            if (change.type === 'unchanged') continue;

            const badgeClass = change.type;
            const badgeLabel = change.type === 'modified' ? 'Modified'
                : change.type === 'added' ? 'Added' : 'Removed';

            html += `
                <div class="diff-section" onclick="this.classList.toggle('collapsed')">
                    <div class="diff-section-header">
                        <span>${change.section}</span>
                        <span class="diff-badge ${badgeClass}">${badgeLabel}</span>
                    </div>
                    <div class="diff-section-body">`;

            if (change.type === 'modified') {
                for (const line of (change.original_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-removed">- ${this.escapeHtml(line)}</div>`;
                }
                html += '<hr style="border-color: var(--border); margin: 0.5rem 0;">';
                for (const line of (change.improved_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-added">+ ${this.escapeHtml(line)}</div>`;
                }
            } else if (change.type === 'added') {
                for (const line of (change.improved_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-added">+ ${this.escapeHtml(line)}</div>`;
                }
            } else if (change.type === 'removed') {
                for (const line of (change.original_lines || [])) {
                    if (line.trim()) html += `<div class="diff-line-removed">- ${this.escapeHtml(line)}</div>`;
                }
            }

            html += `</div></div>`;
        }

        container.innerHTML = html;
    }

    /**
     * Display improvement results after LLM processing.
     * 
     * @param {Object} data - Improvement data from API
     */
    async displayImproveResults(data) {
        document.getElementById('improve-loading').classList.add('hidden');
        document.getElementById('improve-results').classList.remove('hidden');

        // Show catalogue neighbors used as context
        if (data.catalogue_neighbors && data.catalogue_neighbors.length > 0) {
            document.getElementById('catalogue-context-section').classList.remove('hidden');
            document.getElementById('catalogue-neighbors-list').innerHTML =
                data.catalogue_neighbors.map(n => `
                    <div style="background: var(--bg-secondary); border: 1px solid var(--border);
                                border-radius: 8px; padding: 0.5rem 0.75rem; font-size: 0.85rem;
                                max-width: 280px;">
                        <div style="font-weight: 600; margin-bottom: 0.15rem;">${n.name}
                            <span style="color: var(--text-muted); font-weight: 400; font-size: 0.75rem;">
                                ${Math.round(n.similarity_score * 100)}%
                            </span>
                        </div>
                        <div style="color: var(--text-muted); font-size: 0.78rem;
                                    overflow: hidden; text-overflow: ellipsis;
                                    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                            ${n.description || 'No description'}
                        </div>
                    </div>
                `).join('');
        }

        // Token comparison (before vs after)
        this.renderTokenComparison(
            'improve-token-comparison',
            data.original_token_metrics,
            data.improved_token_metrics
        );

        // Render section-level diff
        this.renderImprovementDiff(data.changes);

        // Show action buttons immediately
        document.getElementById('improve-actions').classList.remove('hidden');
    }
}
