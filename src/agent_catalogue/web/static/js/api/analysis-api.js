/**
 * API Layer for Agent Analysis Operations
 * 
 * Centralized API client for all agent catalogue endpoints.
 * Handles both streaming (SSE) and non-streaming HTTP requests.
 * 
 * @module api/analysis-api
 */

import { ActivityFeed } from '../components/activity-feed.js';

/**
 * API client for agent analysis, evaluation, comparison, and storage.
 * 
 * Responsibilities:
 * - Manage all HTTP requests to /api/* endpoints
 * - Handle streaming SSE responses via ActivityFeed
 * - Provide consistent error handling
 * - Abstract away fetch() details from UI code
 * 
 * @class
 */
export class AnalysisAPI {
    /**
     * Create a new API client instance.
     */
    constructor() {
        this._baseUrl = '';  // Same origin
    }

    // ==================== Streaming Methods (via ActivityFeed) ====================

    /**
     * Analyze uploaded agent content for metadata, domains, and similar agents.
     * 
     * @param {string} content - Raw AGENTS.md content
     * @param {string} activityFeedId - DOM element ID for activity feed display
     * @returns {Promise<Object>} Analysis result with metadata and similar agents
     * @throws {Error} If analysis fails
     */
    async analyze(content, activityFeedId) {
        const feed = new ActivityFeed(activityFeedId);
        return await feed.start('/api/stream/analyze', { content });
    }

    /**
     * Evaluate agent quality across multiple dimensions.
     * 
     * @param {string|FormData} content - Agent content (string or FormData for file upload)
     * @param {Object|null} evaluation - Optional existing evaluation to skip re-running
     * @param {string} activityFeedId - DOM element ID for activity feed display
     * @returns {Promise<Object>} Evaluation result with grade, scores, issues, strengths
     * @throws {Error} If evaluation fails
     */
    async evaluate(content, evaluation, activityFeedId) {
        const feed = new ActivityFeed(activityFeedId);
        
        // Support both string content and FormData for backwards compatibility
        let payload;
        if (content instanceof FormData) {
            // Convert FormData to JSON payload
            payload = {
                content: content.get('content'),
                evaluation: evaluation
            };
        } else {
            payload = {
                content: content,
                evaluation: evaluation
            };
        }
        
        return await feed.start('/api/stream/evaluate', payload);
    }

    /**
     * Request AI-powered improvement suggestions for agent content.
     * 
     * @param {string|FormData} content - Agent content to improve
     * @param {Object} evaluation - Quality evaluation result
     * @param {Array} issues - List of issues to address
     * @param {string} activityFeedId - DOM element ID for activity feed display
     * @returns {Promise<Object>} Improvement result with refined content and changes
     * @throws {Error} If improvement fails
     */
    async improve(content, evaluation, issues, activityFeedId) {
        const feed = new ActivityFeed(activityFeedId);
        
        // Support both string content and FormData for backwards compatibility
        let payload;
        if (content instanceof FormData) {
            payload = {
                content: content.get('content'),
                evaluation: evaluation,
                issues: issues
            };
        } else {
            payload = {
                content: content,
                evaluation: evaluation,
                issues: issues
            };
        }
        
        return await feed.start('/api/stream/improve', payload);
    }

    /**
     * Deep compare new agent against existing agent to identify overlaps.
     * 
     * @param {string} agentId - UUID of existing agent to compare against
     * @param {string} content - New agent content
     * @param {string} activityFeedId - DOM element ID for activity feed display
     * @returns {Promise<Object>} Comparison result with overlap analysis
     * @throws {Error} If comparison fails
     */
    async deepCompare(agentId, content, activityFeedId) {
        const feed = new ActivityFeed(activityFeedId);
        return await feed.start(`/api/stream/compare/${agentId}`, { content });
    }

    // ==================== Non-Streaming Methods ====================

    /**
     * Re-check duplication analysis for improved/refined content.
     * Non-throwing - returns null on failure for graceful degradation.
     * 
     * @param {string} content - Improved agent content to re-analyze
     * @returns {Promise<Object|null>} Analysis result or null if failed
     */
    async recheckDuplication(content) {
        try {
            const response = await fetch('/api/analyze-improved', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            
            if (!response.ok) {
                console.warn('Recheck duplication failed:', response.status);
                return null;
            }
            
            return await response.json();
        } catch (error) {
            console.warn('Recheck duplication error:', error);
            return null;  // Non-throwing for graceful degradation
        }
    }

    /**
     * Quick refinement to reduce overlap with similar agents.
     * 
     * @param {string} content - Original agent content
     * @param {Array<Object>} overlapAgents - List of overlapping agents with similarity data
     * @returns {Promise<Object>} Refinement result with refined_content
     * @throws {Error} If refinement fails
     */
    async refine(content, overlapAgents) {
        const response = await fetch('/api/refine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                overlap_agents: overlapAgents
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Refinement failed: ${response.status}`);
        }
        
        return await response.json();
    }

    /**
     * Start strategic differentiation recipe workflow.
     * 
     * @param {string} content - Original agent content
     * @param {Array<Object>} overlapAgents - List of overlapping agents
     * @returns {Promise<Object>} Recipe session info with session_id
     * @throws {Error} If recipe start fails
     */
    async startRecipe(content, overlapAgents) {
        const response = await fetch('/api/recipe/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                recipe: 'strategic-differentiation',
                context: {
                    content: content,
                    overlap_agents: overlapAgents
                }
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Recipe start failed: ${response.status}`);
        }
        
        return await response.json();
    }

    /**
     * Approve a recipe stage to continue execution.
     * 
     * @param {string} sessionId - Recipe session ID
     * @param {string} stageName - Stage name to approve
     * @returns {Promise<Object>} Approval result
     * @throws {Error} If approval fails
     */
    async approveRecipe(sessionId, stageName) {
        const response = await fetch('/api/recipe/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                stage_name: stageName
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Approval failed: ${response.status}`);
        }
        
        return await response.json();
    }

    /**
     * Poll recipe execution status.
     * Used for checking if recipe has completed or needs approval.
     * 
     * @param {string} sessionId - Recipe session ID
     * @returns {Promise<Object>} Status result with state and summary
     * @throws {Error} If status check fails
     */
    async pollRecipeStatus(sessionId) {
        const response = await fetch(`/api/recipe/status/${sessionId}`);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Status check failed: ${response.status}`);
        }
        
        return await response.json();
    }

    /**
     * Poll recipe status with automatic retry until completion or timeout.
     * 
     * @param {string} sessionId - Recipe session ID
     * @param {number} intervalMs - Polling interval in milliseconds (default: 2000)
     * @param {number} timeoutMs - Maximum time to poll in milliseconds (default: 300000 = 5 minutes)
     * @returns {Promise<Object>} Final status result when completed
     * @throws {Error} If polling times out or status check fails
     */
    async pollRecipeCompletion(sessionId, intervalMs = 2000, timeoutMs = 300000) {
        const startTime = Date.now();
        
        while (true) {
            // Check timeout
            if (Date.now() - startTime > timeoutMs) {
                throw new Error('Recipe polling timed out after 5 minutes');
            }
            
            const status = await this.pollRecipeStatus(sessionId);
            
            // Check if completed
            if (status.state === 'completed' || status.state === 'failed') {
                return status;
            }
            
            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, intervalMs));
        }
    }

    /**
     * Store agent in the catalogue.
     * Final step after all analysis, evaluation, and refinement.
     * 
     * @param {FormData} formData - Form data with file and metadata
     * @returns {Promise<Object>} Storage result with agent_id
     * @throws {Error} If storage fails
     */
    async storeAgent(formData) {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData  // Let browser set Content-Type with boundary
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Storage failed: ${response.status}`);
        }
        
        return await response.json();
    }
}
