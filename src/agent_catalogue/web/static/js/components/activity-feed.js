/**
 * ActivityFeed — real-time SSE event viewer for Amplifier kernel events.
 *
 * Handles these actual kernel events emitted by loop-streaming orchestrator:
 *   tool:pre / tool:post           — Tool invocations
 *   content_block:start / :end     — LLM response blocks (includes thinking)
 *   execution:start / :end         — Agent reasoning lifecycle
 *   provider:request / :response   — LLM API calls with model info
 *   prompt:submit                  — Turn start
 *   orchestrator:complete          — Turn complete
 *
 * Plus app-level events from the streaming endpoints:
 *   phase                          — Workflow phase transitions
 *   result                         — Final result payload
 *   error                          — Error message
 * 
 * @module components/activity-feed
 */
export class ActivityFeed {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this._items = [];
        this._resolved = false;
    }

    clear() {
        if (this.container) this.container.innerHTML = '';
        this._items = [];
        this._resolved = false;
    }

    /**
     * POST to an SSE endpoint and stream events into the feed.
     * Returns a promise that resolves with the "result" event payload.
     */
    start(url, payload) {
        console.log('[ActivityFeed] Starting SSE stream', { url, payloadSize: JSON.stringify(payload).length });
        this.clear();
        this._resolved = false;

        return new Promise(async (resolve, reject) => {
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                console.log('[ActivityFeed] Fetch response received', { status: resp.status, ok: resp.ok });

                if (!resp.ok) {
                    let detail = `HTTP ${resp.status}`;
                    try { detail = (await resp.json()).detail || detail; } catch { }
                    console.error('[ActivityFeed] Fetch failed', { url, status: resp.status, detail });
                    return reject(new Error(detail));
                }

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buf = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buf += decoder.decode(value, { stream: true });

                    const parts = buf.split('\n\n');
                    buf = parts.pop();

                    for (const raw of parts) {
                        if (!raw.trim()) continue;
                        if (raw.includes('data: [DONE]')) {
                            if (!this._resolved) {
                                this._markLastRunningDone();
                                resolve(null);
                            }
                            continue;
                        }

                        let evType = 'message', evData = '';
                        for (const line of raw.split('\n')) {
                            if (line.startsWith('event: ')) evType = line.slice(7).trim();
                            else if (line.startsWith('data: ')) evData += line.slice(6);
                        }
                        if (!evData) continue;
                        try {
                            const parsedData = JSON.parse(evData);
                            console.log('[SSE] ✅', evType, parsedData);
                            this._dispatch(evType, parsedData, resolve, reject);
                        } catch (err) { 
                            console.error('[SSE] ❌ Parse error -', 'type:', evType, 'raw:', evData, 'error:', err);
                        }
                    }
                }

                if (!this._resolved) resolve(null);

            } catch (err) {
                if (!this._resolved) reject(err);
            }
        });
    }

    /* —— event dispatch —————————————————————————————————— */

    _dispatch(type, data, resolve, reject) {
        switch (type) {

            // ── App-level phase transitions ──
            case 'phase':
                this._markLastRunningDone();
                this._addPhase(data.message || data.phase || 'Processing...', data.agent_name);
                break;

            // ── Amplifier kernel: tool calls ──
            case 'tool:pre': {
                const agent = data.agent_name || '';
                const name = data.tool_name || 'tool';
                const preview = data.input_preview || '';
                const agentLabel = agent ? `<strong>${this._esc(agent)}</strong>: ` : '';
                this._add('→',
                    `${agentLabel}calling <span class="tool-name">${this._esc(name)}</span> ${this._esc(preview)}`,
                    'tool');
                break;
            }
            case 'tool:post': {
                const agent = data.agent_name || '';
                const name = data.tool_name || 'tool';
                const ok = data.success;
                const preview = data.output_preview || '';
                const agentLabel = agent ? `<strong>${this._esc(agent)}</strong>: ` : '';
                this._add(ok ? '←' : '✗',
                    `${agentLabel}<span class="tool-name">${this._esc(name)}</span> ${ok ? preview : 'failed'}`,
                    ok ? 'tool' : 'error');
                break;
            }
            case 'tool:error':
                this._add('✗',
                    `<span class="tool-name">${this._esc(data.tool_name || 'tool')}</span> ${this._esc(data.error || '')}`,
                    'error');
                break;

            // ── Amplifier kernel: content blocks (includes thinking) ──
            case 'content_block:start': {
                const agent = data.agent_name || '';
                const btype = data.block_type || 'text';
                if (btype === 'thinking') {
                    const agentLabel = agent ? `<strong>${this._esc(agent)}</strong>: ` : '';
                    this._add('◌', `${agentLabel}Reasoning...`, 'content');
                }
                break;
            }
            case 'content_block:end': {
                const agent = data.agent_name || '';
                const btype = data.block_type || 'text';
                const fullText = data.full_text || data.text_preview || '';
                const len = data.text_length || 0;
                const agentLabel = agent ? `<strong>${this._esc(agent)}</strong>: ` : '';

                if (btype === 'thinking' && fullText) {
                    // Show reasoning summary
                    const lines = fullText.split('\n').filter(l => l.trim());
                    const snippet = lines.slice(0, 3).join(' ').substring(0, 300);
                    if (snippet) {
                        this._add('◌', `${agentLabel}${this._esc(snippet)}${len > 300 ? '…' : ''}`, 'content');
                    }
                } else if (btype === 'text' && fullText) {
                    // Show the actual response content with detailed JSON extraction
                    let displayParts = [];

                    // Try to parse as JSON and show structured details
                    if (fullText.trim().startsWith('{') || fullText.includes('```json')) {
                        try {
                            // Extract JSON from code fences if present
                            let jsonText = fullText;
                            const jsonMatch = fullText.match(/```json\s*([\s\S]*?)\s*```/);
                            if (jsonMatch) {
                                jsonText = jsonMatch[1];
                            }

                            const parsed = JSON.parse(jsonText.trim());

                            // Show key summary info
                            if (parsed.overall_score || parsed.grade) {
                                const score = parsed.overall_score ? `${parsed.overall_score}/10` : '';
                                const grade = parsed.grade || '';
                                displayParts.push(`<strong>Quality: ${score} (${grade})</strong>`);
                            }

                            // Show summary if present
                            if (parsed.summary) {
                                displayParts.push(this._esc(parsed.summary.substring(0, 300)));
                            }

                            // Show issues with severity
                            if (parsed.issues && Array.isArray(parsed.issues) && parsed.issues.length > 0) {
                                const critical = parsed.issues.filter(i => i.severity === 'critical').length;
                                const major = parsed.issues.filter(i => i.severity === 'major').length;
                                const minor = parsed.issues.filter(i => i.severity === 'minor').length;
                                const issueBreakdown = [
                                    critical ? `${critical} critical` : null,
                                    major ? `${major} major` : null,
                                    minor ? `${minor} minor` : null
                                ].filter(Boolean).join(', ');
                                displayParts.push(`<span style="color: var(--warning)">Issues: ${issueBreakdown}</span>`);

                                // Show first issue detail
                                if (parsed.issues[0] && parsed.issues[0].description) {
                                    displayParts.push(`• ${this._esc(parsed.issues[0].description.substring(0, 200))}`);
                                }
                            }

                            // Show strengths
                            if (parsed.strengths && Array.isArray(parsed.strengths) && parsed.strengths.length > 0) {
                                displayParts.push(`<span style="color: var(--success)">Strengths: ${parsed.strengths.length}</span>`);
                                if (parsed.strengths[0]) {
                                    displayParts.push(`• ${this._esc(parsed.strengths[0].substring(0, 200))}`);
                                }
                            }

                            // Show capabilities if present
                            if (parsed.capabilities && Array.isArray(parsed.capabilities)) {
                                displayParts.push(`Capabilities: ${parsed.capabilities.length}`);
                            }

                            if (displayParts.length > 0) {
                                // Add each part as a separate line for readability
                                displayParts.forEach((part, idx) => {
                                    if (idx === 0) {
                                        this._add('✎', `${agentLabel}${part}`, 'content');
                                    } else {
                                        this._add('·', part, 'detail');
                                    }
                                });
                            } else {
                                // Fallback to text preview
                                const snippet = fullText.substring(0, 500);
                                this._add('✎', `${agentLabel}${this._esc(snippet)}${len > 500 ? '…' : ''}`, 'content');
                            }
                        } catch {
                            // Not valid JSON, show text preview
                            const snippet = fullText.substring(0, 500);
                            this._add('✎', `${agentLabel}${this._esc(snippet)}${len > 500 ? '…' : ''}`, 'content');
                        }
                    } else {
                        // Plain text response
                        const snippet = fullText.substring(0, 500);
                        this._add('✎', `${agentLabel}${this._esc(snippet)}${len > 500 ? '…' : ''}`, 'content');
                    }
                }
                break;
            }

            // ── Amplifier kernel: LLM provider calls ──
            case 'provider:request': {
                const agent = data.agent_name || '';
                const agentLabel = agent ? `${this._esc(agent)} → ` : '';
                this._add('⟶',
                    `${agentLabel}<strong>${this._esc(data.provider || 'LLM')}</strong> (${this._esc(data.model || '?')})`,
                    'provider');
                break;
            }
            case 'provider:response':
                if (data.input_tokens || data.output_tokens) {
                    const agent = data.agent_name || '';
                    const agentLabel = agent ? `<strong>${this._esc(agent)}</strong>: ` : '';
                    this._add('⟵',
                        `${agentLabel}${this._esc(data.model || 'LLM')}: ${data.input_tokens || '?'}→${data.output_tokens || '?'} tokens`,
                        'provider');
                }
                break;

            // ── Amplifier kernel: orchestrator lifecycle ──
            case 'execution:start': {
                const agent = data.agent_name || '';
                const agentLabel = agent ? `<strong>${this._esc(agent)}</strong> ` : '';
                this._add('▸', `${agentLabel}reasoning started`, 'detail');
                break;
            }
            case 'execution:end': {
                const agent = data.agent_name || '';
                const agentLabel = agent ? `<strong>${this._esc(agent)}</strong> ` : '';
                this._add('▪', `${agentLabel}reasoning complete`, 'detail');
                break;
            }
            case 'prompt:submit':
                // Prompt length removed - not useful for users
                break;
            case 'orchestrator:complete':
                if (data.status) {
                    this._add('▪', `Turn complete: ${this._esc(data.status)}`, 'detail');
                }
                break;
            case 'session:fork':
                this._add('⤷', 'Sub-agent spawned', 'detail');
                break;

            // ── App-level: result / error ──
            case 'result':
                this._markLastRunningDone();
                this._add('✓', 'Complete', 'done');
                this._resolved = true;
                resolve(data.result !== undefined ? data.result : data);
                break;
            case 'error':
                this._markLastRunningDone();
                this._add('✗', data.message || 'An error occurred', 'error');
                this._resolved = true;
                reject(new Error(data.message || 'Stream error'));
                break;

            default:
                if (data.message) this._add('·', this._esc(data.message), 'detail');
        }
    }

    /* —— DOM helpers ————————————————————————————————————— */

    _addPhase(text, agentName) {
        const el = document.createElement('div');
        el.className = 'af-item phase running';
        const agentTag = agentName ? ` <strong>${this._esc(agentName)}</strong>` : '';
        el.innerHTML = `<span class="af-icon">●</span><span class="af-text">${this._esc(text)}${agentTag}</span>`;
        this.container.appendChild(el);
        this._items.push(el);
        this.container.scrollTop = this.container.scrollHeight;
        return el;
    }

    _add(icon, html, cls) {
        const el = document.createElement('div');
        el.className = 'af-item' + (cls ? ' ' + cls : '');
        el.innerHTML = `<span class="af-icon">${icon}</span><span class="af-text">${html}</span>`;
        this.container.appendChild(el);
        this._items.push(el);
        this.container.scrollTop = this.container.scrollHeight;
        return el;
    }

    _markLastRunningDone() {
        for (let i = this._items.length - 1; i >= 0; i--) {
            const el = this._items[i];
            if (el.classList.contains('running')) {
                el.classList.remove('running');
                el.classList.add('done');
                const ico = el.querySelector('.af-icon');
                if (ico) { ico.textContent = '✓'; ico.style.animation = 'none'; }
                break;
            }
        }
    }

    _esc(t) {
        const d = document.createElement('span');
        d.textContent = String(t);
        return d.innerHTML;
    }
}
