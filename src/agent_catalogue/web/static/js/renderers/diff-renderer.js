/**
 * Behavioral Diff Renderer Component
 * 
 * Renders code-diff-style comparisons of agent behavioral differences.
 * Used to visualize overlaps and unique capabilities between agents.
 * 
 * @module renderers/diff-renderer
 */

import { escapeHtml } from '../utils.js';

/**
 * Renders behavioral diff comparisons between agents.
 * 
 * Visual format inspired by code diffs:
 * - Three-column layout: New Only | Shared | Existing Only
 * - Color-coded: Blue (+) for new, Green (=) for shared, Red (-) for existing
 * - Includes verdict, similarity score, behavioral differences, recommendation
 * 
 * @class
 */
export class DiffRenderer {
    /**
     * Render a behavioral diff comparison into a DOM element.
     * 
     * @param {Object} comparison - Comparison object from API with verdict, similarity_score, capability_diff, etc.
     * @param {string} containerId - DOM element ID to render into
     * @param {string} existingAgent - Name of existing agent
     * @param {string} newAgent - Name of new agent
     * @param {string} narrative - Human-readable narrative explanation
     */
    renderBehavioralDiff(comparison, containerId, existingAgent, newAgent, narrative) {
        const container = document.getElementById(containerId);
        if (!container || !comparison) {
            if (container) {
                container.innerHTML = '<div class="diff-empty">No comparison data available</div>';
            }
            return;
        }
        
        const verdict = comparison.verdict || 'unknown';
        const verdictClass = `verdict-${verdict}`;
        const score = comparison.similarity_score || 0;
        const scorePercent = Math.round(score * 100);
        
        // Get capability diff
        const capDiff = comparison.capability_diff || {};
        const shared = capDiff.shared || [];
        const uniqueA = capDiff.unique_to_a || [];
        const uniqueB = capDiff.unique_to_b || [];
        
        // Get behavioral diff
        const behDiff = comparison.behavioral_diff || {};
        
        // Get recommendation
        const rec = comparison.recommendation || {};
        const recAction = rec.action || 'keep_both';
        const recClass = `rec-${recAction}`;
        const recReasoning = rec.reasoning || '';
        
        container.innerHTML = `
            <div class="diff-container">
                <!-- Header -->
                <div class="diff-header">
                    <div class="diff-header-left">
                        <span class="diff-verdict ${verdictClass}">${verdict}</span>
                        <span class="diff-agents">${newAgent || 'New Agent'} vs ${existingAgent || 'Existing Agent'}</span>
                    </div>
                    <div class="diff-score">${scorePercent}%</div>
                </div>
                
                <!-- Capability Diff -->
                <div class="diff-body">
                    <!-- New Agent Unique -->
                    <div class="diff-col-a">
                        <div class="diff-column-header">
                            + ${newAgent || 'New'} Only
                        </div>
                        <div class="diff-content">
                            ${this.renderCapabilities(uniqueA, 'a')}
                        </div>
                    </div>
                    
                    <!-- Shared -->
                    <div class="diff-col-shared">
                        <div class="diff-column-header">
                            = Shared
                        </div>
                        <div class="diff-content">
                            ${this.renderCapabilities(shared, 'shared')}
                        </div>
                    </div>
                    
                    <!-- Existing Agent Unique -->
                    <div class="diff-col-b">
                        <div class="diff-column-header">
                            − ${existingAgent || 'Existing'} Only
                        </div>
                        <div class="diff-content">
                            ${this.renderCapabilities(uniqueB, 'b')}
                        </div>
                    </div>
                </div>
                
                <!-- Behavioral Differences -->
                ${this.renderBehavioralDifferences(behDiff, newAgent, existingAgent)}
                
                <!-- Recommendation -->
                <div class="diff-recommendation">
                    <div class="rec-action ${recClass}">
                        ${this.getRecIcon(recAction)}
                        ${recAction.replace('_', ' ').toUpperCase()}
                    </div>
                    <p class="rec-reasoning">${recReasoning}</p>
                </div>
                
                <!-- Narrative -->
                ${narrative ? `
                    <div class="diff-narrative">
                        <div class="diff-narrative-title">Analysis</div>
                        ${narrative}
                    </div>
                ` : ''}
            </div>
        `;
    }
    
    /**
     * Render a list of capabilities as diff items.
     * 
     * @param {Array} items - Array of capability strings or objects
     * @param {string} type - Diff type: 'a' (new), 'shared', or 'b' (existing)
     * @returns {string} HTML string of rendered capabilities
     */
    renderCapabilities(items, type) {
        if (!items || items.length === 0) {
            return '<div class="diff-empty">None</div>';
        }
        return items.map(item => {
            // Handle both string items and object items
            let displayText = item;
            if (typeof item === 'object' && item !== null) {
                // If it's an object, try to extract meaningful text
                displayText = item.name || item.capability || item.description || JSON.stringify(item);
            }
            return `<div class="diff-item diff-item-${type}">${escapeHtml(displayText)}</div>`;
        }).join('');
    }
    
    /**
     * Render behavioral differences section.
     * 
     * @param {Object} behDiff - Behavioral differences object from comparison
     * @param {string} newName - Name of new agent
     * @param {string} existingName - Name of existing agent
     * @returns {string} HTML string of rendered behavioral differences
     */
    renderBehavioralDifferences(behDiff, newName, existingName) {
        if (!behDiff || Object.keys(behDiff).length === 0) {
            return '';
        }
        
        const items = Object.entries(behDiff).map(([key, value]) => {
            if (typeof value === 'object' && value !== null) {
                // Try multiple field names that LLM might use
                const agentA = value.agent_a || value.new_agent || value[newName] || value.a || '';
                const agentB = value.agent_b || value.existing_agent || value[existingName] || value.b || '';
                
                // Convert to string if still an object
                const textA = typeof agentA === 'object' ? JSON.stringify(agentA) : agentA;
                const textB = typeof agentB === 'object' ? JSON.stringify(agentB) : agentB;
                
                return `
                    <div class="diff-behavioral-item">
                        <div class="diff-behavioral-label">${this.formatLabel(key)}</div>
                        <div class="diff-behavioral-value agent-a">+ ${newName}: ${escapeHtml(textA)}</div>
                        <div class="diff-behavioral-value agent-b">− ${existingName}: ${escapeHtml(textB)}</div>
                    </div>
                `;
            }
            return '';
        }).filter(Boolean).join('');
        
        if (!items) return '';
        
        return `
            <div class="diff-behavioral">
                <div class="diff-behavioral-title">Behavioral Differences</div>
                <div class="diff-behavioral-grid">
                    ${items}
                </div>
            </div>
        `;
    }
    
    /**
     * Format a key name for display (e.g., "tool_usage" → "Tool Usage").
     * 
     * @param {string} key - Key name to format
     * @returns {string} Formatted label
     */
    formatLabel(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }
    
    /**
     * Get icon for recommendation action.
     * 
     * @param {string} action - Action type: 'reject', 'merge', 'keep_both', 'replace'
     * @returns {string} Icon character
     */
    getRecIcon(action) {
        const icons = {
            'reject': '✕',
            'merge': '⊕',
            'keep_both': '✓✓',
            'replace': '↻'
        };
        return icons[action] || '•';
    }
}
