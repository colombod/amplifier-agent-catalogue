/**
 * Wizard Step Management Module
 * 
 * Handles UI state transitions for the 5-step upload wizard:
 * Step 1: Upload file
 * Step 2: Review analysis
 * Step 3: Compare with similar (optional)
 * Step 4: Quality evaluation
 * Step 5: Store agent
 * 
 * @module wizard/wizard-steps
 */

/**
 * Manages wizard step UI states and transitions.
 * 
 * @class
 */
export class WizardSteps {
    /**
     * Toggle step collapse state.
     * 
     * @param {number} stepNum - Step number (1-5)
     */
    toggleStep(stepNum) {
        const card = document.getElementById(`step-${stepNum}-card`);
        if (card.classList.contains('disabled')) return;
        card.classList.toggle('collapsed');
    }

    /**
     * Set step UI state.
     * 
     * @param {number} stepNum - Step number (1-5)
     * @param {string} state - State: 'disabled', 'active', 'completed', 'needs-review'
     */
    setStepState(stepNum, state) {
        const card = document.getElementById(`step-${stepNum}-card`);
        card.classList.remove('disabled', 'active', 'completed', 'collapsed', 'needs-review');
        card.classList.add(state);

        // Auto-collapse completed steps
        if (state === 'completed') {
            card.classList.add('collapsed');
        }

        // Update step indicator bar
        const dot = document.getElementById(`ind-${stepNum}`);
        if (dot) {
            dot.classList.remove('active', 'completed');
            if (state === 'active' || state === 'needs-review') dot.classList.add('active');
            if (state === 'completed') dot.classList.add('completed');
        }
        // Fill connecting line when step completes
        if (state === 'completed') {
            const line = document.getElementById(`ind-line-${stepNum}`);
            if (line) line.classList.add('completed');
        }
    }

    /**
     * Set step summary text.
     * 
     * @param {number} stepNum - Step number (1-5)
     * @param {string} text - Summary text to display
     */
    setStepSummary(stepNum, text) {
        document.getElementById(`step-${stepNum}-summary`).textContent = text;
    }

    /**
     * Enable Step 4 (Quality Evaluation).
     * Skips to Step 5 if duplicate detected.
     * 
     * @param {Object} wizardState - WizardState instance
     */
    enableStep4(wizardState) {
        // If duplicate, skip quality and go straight to store (blocked)
        if (wizardState.analysisData.is_duplicate) {
            this.enableStep5();
            return;
        }

        this.setStepState(4, 'active');
        document.getElementById('step-4-empty').classList.add('hidden');
        document.getElementById('step-4-loading').classList.remove('hidden');
    }

    /**
     * Enable Step 5 (Store Agent).
     */
    enableStep5() {
        this.setStepState(5, 'active');
        document.getElementById('step-5-empty').classList.add('hidden');
        document.getElementById('step-5-content').classList.remove('hidden');
    }

    /**
     * Enable Step 5 with differentiation options visible.
     * Used when user chooses "Continue to Quality Check" from early gate.
     */
    enableStep5WithDifferentiation() {
        // Go directly to Step 5 with differentiation options visible
        this.setStepState(5, 'active');
        document.getElementById('step-5-empty').classList.add('hidden');
        document.getElementById('step-5-content').classList.remove('hidden');

        // Hide early gate and pattern picker
        document.getElementById('early-diff-gate')?.classList.add('hidden');
        document.getElementById('diff-pattern-picker')?.classList.add('hidden');

        // Step 3 is complete (user chose to continue)
        this.setStepState(3, 'completed');
        this.setStepSummary(3, 'Proceeding to quality check');

        // Enable Step 4 quality evaluation
        this.enableStep4(window.wizardState || {analysisData: {is_duplicate: false}});
    }
}
