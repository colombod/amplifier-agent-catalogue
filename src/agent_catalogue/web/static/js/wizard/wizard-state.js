/**
 * Wizard State Management Module
 * 
 * Centralized state management for the upload wizard flow.
 * Handles persistence to sessionStorage with automatic expiration.
 * 
 * @module wizard/wizard-state
 */

/**
 * Manages all state for the upload wizard, including persistence.
 * 
 * State lifecycle:
 * 1. User uploads file → state populated
 * 2. User progresses through steps → state saved to sessionStorage
 * 3. User refreshes page → checkRestorable() offers to resume
 * 4. User completes or cancels → reset() clears state
 * 
 * @class
 */
export class WizardState {
    /**
     * Create a new wizard state instance.
     * Initializes all state properties to null/default values.
     */
    constructor() {
        /** @type {Object|null} Analysis result from Step 2 */
        this.analysisData = null;

        /** @type {File|null} The uploaded file object */
        this.uploadedFile = null;

        /** @type {string|null} Original file content as text */
        this.originalContent = null;

        /** @type {number} Highest similarity score found (0-1) */
        this.highestSimilarity = 0;

        /** @type {Object.<string, Object>} Comparison results by agent ID */
        this.comparedAgents = {};

        /** @type {string|null} UUID of last compared agent */
        this.lastComparedAgentId = null;

        /** @type {Object|null} Quality evaluation result from Step 4 */
        this.evaluationData = null;

        /** @type {string|null} Improved/refined content from improvement step */
        this.improvedContent = null;

        /** @type {boolean} Whether to store improved version vs original */
        this.useImprovedVersion = false;

        /** @private */
        this._storageKey = 'wizardState';

        /** @private */
        this._expirationMs = 10 * 60 * 1000; // 10 minutes
    }

    /**
     * Save current state to sessionStorage.
     * Stores only critical data needed for restoration.
     * Automatically called after key wizard transitions.
     * 
     * @returns {boolean} True if save succeeded, false if storage unavailable
     */
    save() {
        try {
            const state = {
                step: this.getCurrentStep(),
                analysisData: this.analysisData,
                evaluationData: this.evaluationData,
                highestSimilarity: this.highestSimilarity,
                improvedContent: this.improvedContent,
                useImprovedVersion: this.useImprovedVersion,
                timestamp: Date.now()
            };
            sessionStorage.setItem(this._storageKey, JSON.stringify(state));
            return true;
        } catch (e) {
            // sessionStorage may be unavailable (privacy mode, quota exceeded)
            console.warn('Failed to save wizard state:', e);
            return false;
        }
    }

    /**
     * Restore state from sessionStorage.
     * Called internally by checkRestorable() after user confirms.
     * 
     * @private
     * @param {Object} state - Parsed state object from storage
     * @returns {boolean} True if restoration succeeded
     */
    _restore(state) {
        try {
            this.analysisData = state.analysisData;
            this.evaluationData = state.evaluationData;
            this.highestSimilarity = state.highestSimilarity || 0;
            this.improvedContent = state.improvedContent;
            this.useImprovedVersion = state.useImprovedVersion || false;
            return true;
        } catch (e) {
            console.error('Failed to restore wizard state:', e);
            return false;
        }
    }

    /**
     * Get the current wizard step number (1-5).
     * Determines step by checking DOM for active/completed cards.
     * 
     * @returns {number} Current step (1-5), defaults to 1
     */
    getCurrentStep() {
        for (let i = 5; i >= 1; i--) {
            const card = document.getElementById(`step-${i}-card`);
            if (card && (card.classList.contains('active') || card.classList.contains('completed'))) {
                return i;
            }
        }
        return 1;
    }

    /**
     * Check if restorable state exists and offer to resume.
     * Should be called on page load.
     * 
     * Checks:
     * - State exists in sessionStorage
     * - State has not expired (10 minutes)
     * - State has meaningful progress (step > 1, has analysisData)
     * 
     * If conditions met, prompts user to resume. If user declines,
     * clears the stored state.
     * 
     * @param {Function} displayAnalysis - Callback to re-render analysis UI
     * @param {Function} displayQualityEvaluation - Callback to re-render quality UI
     * @returns {boolean} True if state was restored, false otherwise
     */
    checkRestorable(displayAnalysis, displayQualityEvaluation) {
        try {
            const raw = sessionStorage.getItem(this._storageKey);
            if (!raw) return false;

            const state = JSON.parse(raw);

            // Check expiration
            if (Date.now() - state.timestamp > this._expirationMs) {
                sessionStorage.removeItem(this._storageKey);
                return false;
            }

            // Check if there's meaningful progress to restore
            if (state.step > 1 && state.analysisData) {
                const resume = confirm('You have an in-progress upload. Resume from where you left off?');

                if (resume) {
                    // Restore state
                    this._restore(state);

                    // Re-render UI
                    displayAnalysis(this.analysisData);

                    if (this.evaluationData && state.step >= 4) {
                        displayQualityEvaluation(this.evaluationData);
                    }

                    return true;
                } else {
                    // User declined - clear stored state
                    sessionStorage.removeItem(this._storageKey);
                    return false;
                }
            }

            return false;
        } catch (e) {
            // Invalid state data - clear it
            console.warn('Failed to check restorable state:', e);
            sessionStorage.removeItem(this._storageKey);
            return false;
        }
    }

    /**
     * Reset all state to initial values.
     * Called when starting over or after successful storage.
     * Also clears sessionStorage.
     */
    reset() {
        this.analysisData = null;
        this.uploadedFile = null;
        this.originalContent = null;
        this.highestSimilarity = 0;
        this.comparedAgents = {};
        this.lastComparedAgentId = null;
        this.evaluationData = null;
        this.improvedContent = null;
        this.useImprovedVersion = false;

        try {
            sessionStorage.removeItem(this._storageKey);
        } catch (e) {
            // Ignore storage errors on reset
        }
    }
}
