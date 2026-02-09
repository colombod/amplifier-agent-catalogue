/**
 * Upload Controller Module
 * 
 * Orchestrates the complete upload wizard flow including:
 * - File upload and analysis
 * - Quality evaluation and improvement
 * - Similarity detection and differentiation
 * - Agent storage
 * 
 * @module controllers/upload-controller
 */

/**
 * Main controller for the upload wizard.
 * Coordinates between state, API, renderers, and wizard steps.
 * 
 * @class
 */
export class UploadController {
    /**
     * Create upload controller.
     * 
     * @param {WizardState} state - Wizard state manager
     * @param {AnalysisAPI} api - API client
     * @param {UploadRenderer} renderer - UI renderer
     * @param {WizardSteps} steps - Step manager
     * @param {DiffRenderer} diffRenderer - Diff renderer
     */
    constructor(state, api, renderer, steps, diffRenderer) {
        this.state = state;
        this.api = api;
        this.renderer = renderer;
        this.steps = steps;
        this.diffRenderer = diffRenderer;
        this.searchNarrative = null;
    }

    /**
     * Initialize the controller - set up all event listeners and restore state.
     */
    init() {
        this.setupStepHeaders();
        this.setupFileInput();
        this.setupAnalyzeButton();
        this.setupStep3Actions();
        this.setupStep4Actions();
        this.setupStep5Actions();
        this.setupEarlyDifferentiationGate();
        this.setupModals();
        this.setupStateWrapping();
        
        // Check for restorable state on page load
        this.state.checkRestorable(
            (data) => this.renderer.displayAnalysis(data, this.steps, this.state),
            (data) => this.renderer.displayQualityEvaluation(data)
        );
    }

    // ==================== File Input Setup ====================

    setupFileInput() {
        const fileInput = document.getElementById('file');
        const fileWrapper = document.getElementById('file-wrapper');
        const analyzeBtn = document.getElementById('analyze-btn');

        // Click on wrapper to open file dialog
        fileWrapper.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                this.state.uploadedFile = fileInput.files[0];
                console.log('[Upload] File selected:', {
                    name: this.state.uploadedFile.name,
                    size: this.state.uploadedFile.size,
                    type: this.state.uploadedFile.type
                });
                fileWrapper.classList.add('has-file');
                document.getElementById('file-name').textContent = this.state.uploadedFile.name;
                document.getElementById('file-name').classList.remove('hidden');
                analyzeBtn.disabled = false;
                this.steps.setStepSummary(1, this.state.uploadedFile.name);
            }
        });

        // Drag and drop
        fileWrapper.addEventListener('dragover', (e) => {
            e.preventDefault();
            fileWrapper.style.borderColor = 'var(--accent)';
        });

        fileWrapper.addEventListener('dragleave', () => {
            fileWrapper.style.borderColor = '';
        });

        fileWrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            fileWrapper.style.borderColor = '';
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                fileInput.dispatchEvent(new Event('change'));
            }
        });
    }

    setupAnalyzeButton() {
        const analyzeBtn = document.getElementById('analyze-btn');
        
        analyzeBtn.addEventListener('click', async () => {
            if (!this.state.uploadedFile) return;

            // CRITICAL: Read file content first and store for later use
            try {
                this.state.originalContent = await this.state.uploadedFile.text();
                console.log('[Analysis] File content loaded:', {
                    length: this.state.originalContent.length,
                    lines: this.state.originalContent.split('\n').length
                });
            } catch (error) {
                console.error('[Analysis] Failed to read file content:', error);
                alert('Failed to read file content: ' + error.message);
                return;
            }

            const prevErr = document.getElementById('analyze-error');
            if (prevErr) prevErr.remove();

            // Disable button during analysis
            analyzeBtn.innerHTML = '<span class="loading-spinner"></span>Analyzing...';
            analyzeBtn.disabled = true;

            // Show activity feed for real-time progress
            const activityFeedId = 'analyze-activity-feed';
            document.getElementById('step-1-body').insertAdjacentHTML('beforeend', `
                <div id="analyze-progress" style="margin-top: 1rem;">
                    <div id="${activityFeedId}" class="activity-feed"></div>
                </div>
            `);

            try {
                console.log('[Analysis] Starting API call with content length:', this.state.originalContent.length);
                // Use API client for streaming analysis
                this.state.analysisData = await this.api.analyze(this.state.originalContent, activityFeedId);

                console.log('[Analysis] Complete, received data:', {
                    metadata: this.state.analysisData?.metadata?.name,
                    isDuplicate: this.state.analysisData?.is_duplicate,
                    similarCount: this.state.analysisData?.similar_agents?.length,
                    hasOverlap: this.state.analysisData?.has_significant_overlap
                });

                if (this.state.analysisData) {
                    this.handleAnalysisComplete(this.state.analysisData);
                }
                document.getElementById('analyze-progress')?.remove();

            } catch (error) {
                document.getElementById('step-1-body').insertAdjacentHTML('beforeend',
                    `<div class="decision-box danger" id="analyze-error">
                        <div class="decision-title">Analysis failed</div>
                        <div>${error.message}</div>
                    </div>`);
                document.getElementById('analyze-progress')?.remove();
            } finally {
                analyzeBtn.innerHTML = 'Analyze File →';
                analyzeBtn.disabled = false;
            }
        });
    }

    handleAnalysisComplete(data) {
        console.log('[Flow] handleAnalysisComplete called', {
            agentName: data?.metadata?.name,
            similarCount: data?.similar_agents?.length,
            highestSimilarity: this.state.highestSimilarity,
            hasSignificantOverlap: data?.has_significant_overlap,
            isDuplicate: data?.is_duplicate
        });
        
        if (!data || !data.metadata) {
            console.error('[Flow] handleAnalysisComplete: Missing data or metadata', data);
            return;
        }
        
        this.renderer.displayAnalysis(data, this.steps, this.state);

        if (data.similar_agents && data.similar_agents.length > 0) {
            const mostSimilar = data.similar_agents.find(s => s.similarity_score === this.state.highestSimilarity);

            // Smart gating
            const hasTraitOverlap = data.has_significant_overlap;
            const hasLikelyDuplicate = data.similar_agents.some(
                s => s.comparison && s.comparison.recommendation === 'likely_duplicate'
            );
            
            // Fix: needsReview should only trigger for HIGH-RISK duplicates (85%+)
            // hasTraitOverlap is informational, not a blocking condition
            const needsReview = hasLikelyDuplicate || this.state.highestSimilarity >= 0.85;
            const shouldOfferEarlyDiff = this.state.highestSimilarity >= 0.70 && this.state.highestSimilarity < 0.85;

            console.log('[Gate] Decision variables:', {
                highestSimilarity: this.state.highestSimilarity,
                hasTraitOverlap,
                hasLikelyDuplicate,
                needsReview,
                shouldOfferEarlyDiff,
                mostSimilarAgent: mostSimilar?.agent?.name,
                logic: needsReview ? 'NEEDS_REVIEW (85%+)' : shouldOfferEarlyDiff ? 'EARLY_DIFF_GATE (70-84%)' : 'PROCEED (<70%)'
            });

            if (needsReview) {
                console.log('[Gate] Path: NEEDS_REVIEW - Showing duplication banner (85%+ or likely_duplicate)');
                // Genuine duplication risk: require review
                this.renderer.showDuplicationBanner(this.state.highestSimilarity, mostSimilar.agent.name);
                this.steps.setStepState(3, 'needs-review');
                document.getElementById('compare-prompt').classList.remove('hidden');
                document.getElementById('step-3-actions').classList.add('hidden');
                this.steps.setStepState(4, 'disabled');
                this.steps.setStepState(5, 'disabled');
            } else if (shouldOfferEarlyDiff) {
                console.log('[Gate] Path: EARLY_DIFF - Showing differentiation gate');
                // Moderate overlap: offer early differentiation choice
                this.renderer.showEarlyDifferentiationGate(data.similar_agents, this.state.highestSimilarity, this.state);
                this.steps.setStepState(3, 'active');
                document.getElementById('step-3-card').classList.remove('collapsed');
                this.steps.setStepState(4, 'disabled');
                this.steps.setStepState(5, 'disabled');
            } else {
                console.log('[Gate] Path: PROCEED - Similar but not duplicates, proceeding to Step 4');
                // Similar but not duplicates: proceed
                this.steps.setStepState(3, 'completed');
                this.steps.enableStep4(this.state);
            }
        } else {
            console.log('[Gate] Path: NO_SIMILAR - No similar agents found, proceeding to Step 4');
            // No similar agents: proceed
            this.steps.setStepState(3, 'completed');
            this.steps.enableStep4(this.state);
        }

        // Setup click handlers for dynamically created similar agent cards
        this.setupSimilarAgentHandlers();
    }

    setupSimilarAgentHandlers() {
        // Use event delegation for dynamically created similar agent cards
        document.getElementById('similar-list')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;

            const action = btn.dataset.action;
            const agentId = btn.dataset.agentId;
            const agentName = btn.dataset.agentName;

            if (action === 'deepCompare') {
                this.deepCompare(agentId, agentName);
            } else if (action === 'viewStoredComparison') {
                this.viewStoredComparison(agentId);
            }
        });
    }

    // ==================== Step 3 Actions ====================

    setupStep3Actions() {
        document.getElementById('view-last-comparison-btn')?.addEventListener('click', () => {
            if (this.state.lastComparedAgentId && this.state.comparedAgents[this.state.lastComparedAgentId]) {
                this.viewStoredComparison(this.state.lastComparedAgentId);
            }
        });

        document.getElementById('proceed-to-store-btn')?.addEventListener('click', () => {
            this.steps.setStepState(3, 'completed');
            this.steps.enableStep4(this.state);
            document.getElementById('step-4-card')?.scrollIntoView({ behavior: 'smooth' });
        });

        document.getElementById('skip-compare-btn')?.addEventListener('click', () => {
            if (this.state.highestSimilarity >= 0.8) {
                if (!confirm('High duplication detected. Are you sure you want to skip the deep comparison?')) {
                    return;
                }
            }
            this.steps.setStepState(3, 'completed');
            this.steps.setStepSummary(3, 'Skipped comparison');
            document.getElementById('duplication-banner')?.classList.add('hidden');
            this.steps.enableStep4(this.state);
            document.getElementById('step-4-card')?.scrollIntoView({ behavior: 'smooth' });
        });
    }

    async deepCompare(agentId, agentName) {
        if (!this.state.originalContent) return;

        document.getElementById('diff-modal').classList.remove('hidden');
        document.getElementById('diff-modal-title').textContent = `Comparing with ${agentName}`;

        const activityFeedId = 'compare-activity-feed';
        document.getElementById('diff-container').innerHTML = `
            <div id="${activityFeedId}" class="activity-feed"></div>
        `;

        try {
            const data = await this.api.deepCompare(agentId, this.state.originalContent, activityFeedId);

            if (data) {
                this.state.comparedAgents[agentId] = {
                    data: data,
                    agentName: agentName,
                    timestamp: new Date()
                };
                this.state.lastComparedAgentId = agentId;

                this.diffRenderer.renderBehavioralDiff(
                    data.comparison, 
                    'diff-container', 
                    data.existing_agent, 
                    data.new_agent, 
                    data.narrative
                );

                // Update the similar agent card
                const card = document.getElementById(`similar-${agentId}`);
                if (card && this.state.analysisData) {
                    card.classList.add('compared');
                    const similar = this.state.analysisData.similar_agents.find(s => s.agent.id === agentId);
                    if (similar) {
                        card.outerHTML = this.renderer.renderSimilarAgent(similar, this.state);
                    }
                }

                // Re-setup handlers after re-rendering
                this.setupSimilarAgentHandlers();

                document.getElementById('compare-prompt')?.classList.add('hidden');
                document.getElementById('step-3-actions')?.classList.remove('hidden');
                this.steps.setStepState(3, 'active');
                this.steps.setStepSummary(3, `Compared (${Math.round(this.state.highestSimilarity * 100)}% overlap)`);
            }

        } catch (error) {
            document.getElementById('diff-container').innerHTML = `
                <div class="alert alert-error">Error: ${error.message}</div>
            `;
        }
    }

    viewStoredComparison(agentId) {
        const stored = this.state.comparedAgents[agentId];
        if (!stored) return;

        document.getElementById('diff-modal').classList.remove('hidden');
        document.getElementById('diff-modal-title').textContent = `Comparison with ${stored.agentName}`;
        this.diffRenderer.renderBehavioralDiff(
            stored.data.comparison,
            'diff-container',
            stored.data.existing_agent,
            stored.data.new_agent,
            stored.data.narrative
        );
    }

    // ==================== Step 4 Actions ====================

    setupStep4Actions() {
        // Listen for auto-triggered evaluation from enableStep4()
        window.addEventListener('startEvaluation', () => {
            console.log('[Step4] startEvaluation event received - running quality evaluation');
            this.runQualityEvaluation();
        });

        // Quality choices are rendered with inline onclick - wire them up with delegation
        document.getElementById('quality-choices')?.addEventListener('click', (e) => {
            if (e.target.closest('#store-current-choice')) {
                this.proceedWithOriginal();
            } else if (e.target.closest('#improve-then-store-choice')) {
                this.requestImprovement();
            }
        });

        document.getElementById('store-improved-btn')?.addEventListener('click', () => {
            this.state.useImprovedVersion = true;
            this.steps.setStepState(4, 'completed');
            this.steps.setStepSummary(4, `Improved (est. ${this.state.evaluationData?.estimated_improved_grade || '?'})`);
            this.steps.enableStep5();
            document.getElementById('step-5-card')?.scrollIntoView({ behavior: 'smooth' });
        });

        document.getElementById('store-original-btn')?.addEventListener('click', () => {
            this.state.useImprovedVersion = false;
            this.steps.setStepState(4, 'completed');
            this.steps.setStepSummary(4, `Grade ${this.state.evaluationData ? this.state.evaluationData.grade : '?'} (as-is)`);
            this.steps.enableStep5();
            document.getElementById('step-5-card')?.scrollIntoView({ behavior: 'smooth' });
        });

        document.getElementById('refine-overlap-btn')?.addEventListener('click', () => this.refineToReduceOverlap());
        document.getElementById('strategic-diff-btn')?.addEventListener('click', () => this.runStrategicDifferentiation());
    }

    async runQualityEvaluation() {
        console.log('[Step4] runQualityEvaluation started');
        
        const contentToEvaluate = this.state.improvedContent || this.state.originalContent;
        if (!contentToEvaluate) {
            console.error('[Step4] No content to evaluate!');
            return;
        }

        console.log('[Step4] Evaluating content:', { 
            length: contentToEvaluate.length,
            source: this.state.improvedContent ? 'improved' : 'original'
        });

        // Show activity feed, hide static spinner
        const feedEl = document.getElementById('evaluate-activity-feed');
        const spinnerWrap = document.getElementById('evaluate-spinner-wrap');
        
        if (feedEl) {
            feedEl.style.display = 'block';
            console.log('[Step4] Activity feed visible');
        }
        if (spinnerWrap) {
            spinnerWrap.style.display = 'none';
            console.log('[Step4] Spinner hidden');
        }

        try {
            console.log('[Step4] Calling API evaluate with activityFeedId: evaluate-activity-feed');
            this.state.evaluationData = await this.api.evaluate(
                contentToEvaluate, 
                this.state.evaluationData,
                'evaluate-activity-feed'
            );

            console.log('[Step4] Evaluation complete:', {
                grade: this.state.evaluationData.grade,
                score: this.state.evaluationData.overall_score,
                issueCount: this.state.evaluationData.issues?.length || 0
            });

            document.getElementById('step-4-loading')?.classList.add('hidden');
            this.renderer.displayQualityEvaluation(this.state.evaluationData);

        } catch (error) {
            console.error('[Step4] Evaluation failed:', error);
            document.getElementById('step-4-loading')?.classList.add('hidden');
            document.getElementById('step-4-content')?.classList.remove('hidden');
            document.getElementById('quality-header').innerHTML = `
                <div class="decision-box warning">
                    <div class="decision-title">Evaluation error</div>
                    <div>${error.message}. You can still store the agent.</div>
                </div>
            `;
            this.renderer.showQualityChoices(null);
        }
    }

    proceedWithOriginal() {
        this.state.useImprovedVersion = false;
        this.steps.setStepState(4, 'completed');
        const tm = this.state.evaluationData?.token_metrics;
        const tokenInfo = tm ? ` · ${tm.total_tokens.toLocaleString()} tokens (${tm.budget_label.toLowerCase()})` : '';
        this.steps.setStepSummary(4, `Grade ${this.state.evaluationData?.grade || '?'} · stored as-is${tokenInfo}`);
        this.steps.enableStep5();
        document.getElementById('step-5-card')?.scrollIntoView({ behavior: 'smooth' });
    }

    proceedFromQuality() {
        this.state.useImprovedVersion = false;
        this.steps.setStepState(4, 'completed');
        const tm = this.state.evaluationData?.token_metrics;
        const tokenInfo = tm ? ` · ${tm.total_tokens.toLocaleString()} tokens (${tm.budget_label.toLowerCase()})` : '';
        this.steps.setStepSummary(4, `Grade ${this.state.evaluationData?.grade || '?'} · ${this.state.evaluationData?.overall_score.toFixed(1) || '?'}/10${tokenInfo}`);
        this.steps.enableStep5();
        document.getElementById('step-5-card')?.scrollIntoView({ behavior: 'smooth' });
    }

    async requestImprovement() {
        if (!this.state.uploadedFile) return;

        document.getElementById('quality-choices').classList.add('hidden');
        document.getElementById('step-4-improve').classList.remove('hidden');
        document.getElementById('improve-loading').classList.remove('hidden');
        document.getElementById('improve-results').classList.add('hidden');

        let contentStr;
        try { contentStr = await this.state.uploadedFile.text(); } catch { contentStr = null; }

        const issues = this.state.evaluationData?.issues || [];

        // Try streaming first
        if (contentStr) {
            const feedEl = document.getElementById('improve-activity-feed');
            const spinnerWrap = document.getElementById('improve-spinner-wrap');
            feedEl.style.display = 'block';
            spinnerWrap.style.display = 'none';

            try {
                const data = await this.api.improve(contentStr, this.state.evaluationData, issues, 'improve-activity-feed');
                await this.displayImproveResults(data);
                return;
            } catch {
                feedEl.style.display = 'none';
                spinnerWrap.style.display = '';
            }
        }

        // Fallback
        const improveNarrative = this.startProgressNarrative('improve-progress', [
            'Reading your agent definition...',
            'Finding similar agents in catalogue...',
            'Identifying differentiation opportunities...',
            'Crafting improved version...',
            'Optimizing token efficiency...'
        ], 2500);

        const formData = new FormData();
        formData.append('file', this.state.uploadedFile);

        try {
            if (improveNarrative) clearInterval(improveNarrative);
            const data = await this.api.improve(formData, this.state.evaluationData, issues, 'improve-activity-feed');
            await this.displayImproveResults(data);
        } catch (error) {
            if (improveNarrative) clearInterval(improveNarrative);
            this.renderer.showImproveError(error.message);
        }
    }

    async displayImproveResults(data) {
        this.state.improvedContent = data.improved_content;
        await this.renderer.displayImproveResults(data);
        await this.recheckDuplication(this.state.improvedContent);
    }

    async refineToReduceOverlap() {
        if (!this.state.improvedContent || !window._lastOverlapAgents) return;

        document.getElementById('improve-actions').classList.add('hidden');
        document.getElementById('refine-loading').classList.remove('hidden');

        const refineNarrative = this.startProgressNarrative('refine-progress', [
            'Analyzing overlapping capabilities...',
            'Identifying unique differentiation angles...',
            'Removing duplicated coverage...',
            'Sharpening the agent niche...',
            'Optimizing token efficiency...'
        ], 2500);

        try {
            const data = await this.api.refine(this.state.improvedContent, window._lastOverlapAgents);
            this.state.improvedContent = data.refined_content;

            document.getElementById('refine-loading').classList.add('hidden');
            this.renderer.renderImprovementDiff(data.changes);

            if (data.token_metrics) {
                this.renderer.renderTokenPanel('improve-token-comparison', data.token_metrics, 'Refined Version');
                document.getElementById('improve-token-comparison').classList.remove('hidden');
            }

            document.getElementById('improve-actions').classList.remove('hidden');
            document.getElementById('refine-overlap-btn').style.display = 'none';
            await this.recheckDuplication(this.state.improvedContent);

        } catch (error) {
            if (refineNarrative) clearInterval(refineNarrative);
            document.getElementById('refine-loading').classList.add('hidden');
            document.getElementById('improve-actions').classList.remove('hidden');
            document.getElementById('recheck-status').innerHTML =
                `Refinement error: ${error.message}. You can still store the current version.`;
        }
    }

    async runStrategicDifferentiation() {
        if (!this.state.improvedContent || !window._lastOverlapAgents) return;

        document.getElementById('improve-actions').classList.add('hidden');
        document.getElementById('refine-loading').classList.remove('hidden');
        document.getElementById('refine-progress').textContent = 'Starting strategic analysis...';

        try {
            const result = await this.api.startRecipe(
                this.state.improvedContent || this.state.originalContent,
                window._lastOverlapAgents
            );

            window._recipeSessionId = result.session_id;
            window._recipeStage = result.stage_name;

            if (result.status === 'paused') {
                document.getElementById('refine-loading').classList.add('hidden');
                document.getElementById('strategy-content').innerHTML =
                    `<div style="white-space: pre-wrap; font-family: monospace; padding: 1rem; background: var(--bg-secondary); border-radius: 4px; max-height: 400px; overflow-y: auto;">${result.approval_prompt}</div>`;
                document.getElementById('strategy-approval-modal').classList.remove('hidden');
            } else if (result.status === 'completed') {
                this.handleStrategyComplete(result.summary?.refined_content || this.state.improvedContent);
            }

        } catch (error) {
            document.getElementById('refine-loading').classList.add('hidden');
            document.getElementById('improve-actions').classList.remove('hidden');
            alert(`Strategic differentiation error: ${error.message}`);
        }
    }

    async recheckDuplication(content) {
        const statusEl = document.getElementById('recheck-status');
        statusEl.classList.remove('hidden', 'clear', 'overlap');
        statusEl.classList.add('checking');
        statusEl.innerHTML = '<span class="loading-spinner"></span><span>Checking improved version for duplication...</span>';

        const data = await this.api.recheckDuplication(content);

        if (!data) {
            statusEl.classList.remove('checking');
            statusEl.classList.add('clear');
            statusEl.innerHTML = 'Duplication check unavailable - you can still proceed.';
            return;
        }

        statusEl.classList.remove('checking');
        if (data.has_duplication_risk) {
            statusEl.classList.add('overlap');
            const pct = Math.round(data.highest_similarity * 100);
            const topName = data.similar_agents[0]?.agent?.name || 'existing agents';
            statusEl.innerHTML = `${pct}% overlap with "${topName}". You can refine further to reduce overlap.`;

            document.getElementById('refine-overlap-btn').style.display = '';
            document.getElementById('strategic-diff-btn').style.display = '';
            window._lastOverlapAgents = data.similar_agents.map(s => ({
                id: s.agent.id,
                name: s.agent.name,
                description: s.agent.description || '',
                capabilities: s.agent.capabilities || [],
                domains: s.agent.domains || [],
                tools: [],
                similarity_score: s.similarity_score,
            }));
        } else {
            statusEl.classList.add('clear');
            statusEl.innerHTML = 'No duplication risk. Ready to store.';
            document.getElementById('refine-overlap-btn').style.display = 'none';
            document.getElementById('strategic-diff-btn').style.display = 'none';
        }
    }

    handleStrategyComplete(refinedContent) {
        document.getElementById('refine-loading').classList.add('hidden');
        this.state.improvedContent = refinedContent;
        document.getElementById('improve-content-display').innerHTML =
            `<pre style="white-space: pre-wrap; background: var(--bg-secondary); padding: 1rem; border-radius: 4px; max-height: 400px; overflow-y: auto;">${this.renderer.escapeHtml(refinedContent)}</pre>`;
        document.getElementById('improve-actions').classList.remove('hidden');
        document.getElementById('refine-overlap-btn').style.display = 'none';
        document.getElementById('strategic-diff-btn').style.display = 'none';
        this.recheckDuplication(refinedContent);
    }

    // ==================== Step 5 Actions ====================

    setupStep5Actions() {
        document.getElementById('store-btn')?.addEventListener('click', async (e) => {
            await this.storeAgent(e.target);
        });

        document.getElementById('reset-btn')?.addEventListener('click', () => {
            if (confirm('Start over? This will discard all analysis progress.')) {
                this.state.reset();
                location.reload();
            }
        });

        document.getElementById('cancel-upload-btn')?.addEventListener('click', () => {
            if (confirm('Cancel this upload? All analysis and improvements will be discarded.')) {
                sessionStorage.removeItem('wizardState');
                window.location.href = '/';
            }
        });
    }

    async storeAgent(btn) {
        const formData = new FormData();

        if (this.state.useImprovedVersion && this.state.improvedContent) {
            const blob = new Blob([this.state.improvedContent], { type: 'text/markdown' });
            formData.append('file', blob, this.state.uploadedFile ? this.state.uploadedFile.name : 'AGENTS.md');
        } else if (this.state.uploadedFile) {
            formData.append('file', this.state.uploadedFile);
        } else {
            return;
        }

        formData.append('force', 'true');

        try {
            btn.innerHTML = '<span class="loading-spinner"></span>Storing...';
            btn.disabled = true;

            const result = await this.api.storeAgent(formData);
            this.steps.setStepState(5, 'completed');
            this.steps.setStepSummary(5, 'Stored');
            sessionStorage.removeItem('wizardState');

            document.getElementById('decision-display').innerHTML = `
                <div class="decision-box success">
                    <div class="decision-title">Agent stored successfully</div>
                    <div><strong>${result.agent.name}</strong> is now in the catalogue.</div>
                    <div class="action-buttons" style="margin-top: 0.75rem;">
                        <a href="/agent/${result.agent.slug}" target="_blank" class="btn btn-primary">View Agent ↗</a>
                        <a href="/upload" class="btn">Upload Another</a>
                    </div>
                </div>
            `;
            document.getElementById('store-btn').classList.add('hidden');
            document.getElementById('reset-btn').classList.add('hidden');

        } catch (error) {
            document.getElementById('decision-display').innerHTML = `
                <div class="decision-box danger">
                    <div class="decision-title">Storing failed</div>
                    <div>${error.message}</div>
                </div>`;
        } finally {
            btn.innerHTML = 'Store Agent';
            btn.disabled = false;
        }
    }

    // ==================== Early Differentiation Gate ====================

    setupEarlyDifferentiationGate() {
        // Wire up buttons with delegation since they're dynamically shown
        document.addEventListener('click', (e) => {
            if (e.target.id === 'differentiate-early-btn' || e.target.closest('#differentiate-early-btn')) {
                document.getElementById('early-diff-gate')?.classList.add('hidden');
                document.getElementById('pattern-picker')?.classList.remove('hidden');
            }
            
            if (e.target.id === 'continue-quality-btn' || e.target.closest('#continue-quality-btn')) {
                document.getElementById('early-diff-gate')?.classList.add('hidden');
                this.steps.setStepState(3, 'completed');
                this.steps.enableStep4(this.state);
            }

            if (e.target.id === 'pattern1-btn' || e.target.closest('#pattern1-btn')) {
                this.runPattern1();
            }

            if (e.target.id === 'pattern2-btn' || e.target.closest('#pattern2-btn')) {
                this.runPattern2();
            }

            if (e.target.id === 'cancel-diff-btn' || e.target.closest('#cancel-diff-btn')) {
                document.getElementById('pattern-picker')?.classList.add('hidden');
                document.getElementById('early-diff-gate')?.classList.remove('hidden');
            }
        });

        // Setup strategy modal buttons
        document.getElementById('approve-strategy-btn')?.addEventListener('click', () => this.approveStrategy());
        document.getElementById('deny-strategy-btn')?.addEventListener('click', () => this.denyStrategy());
        document.getElementById('close-strategy-modal')?.addEventListener('click', () => this.closeStrategyModal());
    }

    async runPattern1() {
        if (!this.state.originalContent || !window._lastOverlapAgents) return;

        document.getElementById('pattern-picker')?.classList.add('hidden');
        this.steps.setStepSummary(3, 'Refining to reduce overlap...');

        try {
            const data = await this.api.refine(
                this.state.improvedContent || this.state.originalContent,
                [window._lastOverlapAgents[0]]
            );
            this.state.improvedContent = data.refined_content;

            this.steps.setStepState(3, 'completed');
            this.steps.setStepSummary(3, 'Differentiated (Pattern 1)');
            this.steps.enableStep4(this.state);

        } catch (error) {
            this.steps.setStepSummary(3, 'Refinement failed');
            alert(`Pattern 1 failed: ${error.message}. Please try again or choose Pattern 2.`);
            document.getElementById('pattern-picker')?.classList.remove('hidden');
        }
    }

    async runPattern2() {
        if (!this.state.originalContent || !window._lastOverlapAgents) return;

        document.getElementById('pattern-picker')?.classList.add('hidden');
        this.steps.setStepSummary(3, 'Strategic differentiation...');

        try {
            const result = await this.api.startRecipe(
                this.state.improvedContent || this.state.originalContent,
                window._lastOverlapAgents
            );

            window._recipeSessionId = result.session_id;
            window._recipeStage = result.stage_name;

            if (result.status === 'paused') {
                document.getElementById('strategy-content').innerHTML =
                    `<div style="white-space: pre-wrap; font-family: monospace; padding: 1rem; background: var(--bg-secondary); border-radius: 4px; max-height: 400px; overflow-y: auto;">${result.approval_prompt}</div>`;
                document.getElementById('strategy-approval-modal').classList.remove('hidden');
            } else if (result.status === 'completed') {
                this.state.improvedContent = result.summary?.refined_content || this.state.originalContent;
                this.steps.setStepState(3, 'completed');
                this.steps.setStepSummary(3, 'Differentiated (Pattern 2)');
                this.steps.enableStep4(this.state);
            }

        } catch (error) {
            this.steps.setStepSummary(3, 'Strategic differentiation failed');
            alert(`Pattern 2 failed: ${error.message}. Please try again or use Pattern 1.`);
            document.getElementById('pattern-picker')?.classList.remove('hidden');
        }
    }

    async approveStrategy() {
        const sessionId = window._recipeSessionId;
        const stageName = window._recipeStage;
        if (!sessionId || !stageName) return;

        document.getElementById('strategy-approval-modal').classList.add('hidden');
        document.getElementById('refine-loading').classList.remove('hidden');
        document.getElementById('refine-progress').textContent = 'Applying recommended strategy...';

        try {
            await this.api.approveRecipe(sessionId, stageName);
            await this.pollRecipeCompletion(sessionId);
        } catch (error) {
            document.getElementById('refine-loading').classList.add('hidden');
            document.getElementById('improve-actions').classList.remove('hidden');
            alert(`Strategy application error: ${error.message}`);
        }
    }

    denyStrategy() {
        document.getElementById('strategy-approval-modal').classList.add('hidden');
        document.getElementById('refine-loading').classList.add('hidden');
        document.getElementById('improve-actions').classList.remove('hidden');
    }

    closeStrategyModal() {
        document.getElementById('strategy-approval-modal').classList.add('hidden');
        document.getElementById('refine-loading').classList.add('hidden');
        document.getElementById('improve-actions').classList.remove('hidden');
    }

    async pollRecipeCompletion(sessionId) {
        const maxAttempts = 60;
        let attempts = 0;

        return new Promise((resolve, reject) => {
            const pollInterval = setInterval(async () => {
                attempts++;

                if (attempts > maxAttempts) {
                    clearInterval(pollInterval);
                    reject(new Error('Recipe execution timed out'));
                    return;
                }

                try {
                    const status = await this.api.pollRecipeStatus(sessionId);

                    if (status.status === 'completed') {
                        clearInterval(pollInterval);
                        const refinedContent = status.outputs?.refined_content;
                        if (refinedContent) {
                            this.handleStrategyComplete(refinedContent);
                        }
                        resolve();
                    } else if (status.status === 'failed') {
                        clearInterval(pollInterval);
                        reject(new Error('Recipe execution failed'));
                    }
                } catch (error) {
                    clearInterval(pollInterval);
                    reject(error);
                }
            }, 2000);
        });
    }

    // ==================== Modals ====================

    setupModals() {
        document.getElementById('close-modal')?.addEventListener('click', () => {
            document.getElementById('diff-modal')?.classList.add('hidden');
        });

        document.getElementById('diff-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'diff-modal') {
                document.getElementById('diff-modal').classList.add('hidden');
            }
        });
    }

    // ==================== Utilities ====================

    startProgressNarrative(elementId, phases, intervalMs) {
        const el = document.getElementById(elementId);
        if (!el) return null;
        let idx = 0;
        el.textContent = phases[0];
        return setInterval(() => {
            idx = (idx + 1) % phases.length;
            el.textContent = phases[idx];
        }, intervalMs || 2500);
    }

    setupStateWrapping() {
        // Wrap setStepState to auto-save
        const originalSetStepState = this.steps.setStepState.bind(this.steps);
        this.steps.setStepState = (stepNum, state) => {
            originalSetStepState(stepNum, state);
            if (state === 'completed') {
                this.state.save();
            }
        };
    }

    /**
     * Wire up step header clicks using event delegation.
     * Removes need for inline onclick attributes.
     */
    setupStepHeaders() {
        // Handle all step header clicks with delegation
        document.querySelectorAll('.step-header').forEach(header => {
            header.addEventListener('click', (e) => {
                const stepCard = e.target.closest('.step-card');
                if (stepCard) {
                    const stepNum = parseInt(stepCard.id.replace('step-', '').replace('-card', ''));
                    if (!isNaN(stepNum)) {
                        this.steps.toggleStep(stepNum);
                    }
                }
            });
        });
    }
}
