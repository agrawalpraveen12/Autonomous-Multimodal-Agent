/**
 * Agentic AI Assistant — frontend
 *
 * Phase 1: new-chat, health polling, timestamps, action badges,
 *           copy btn, clarify banner, prompt chips, error bubbles
 * Phase 2: XHR upload with progress bar (2.3), drag-drop (2.1),
 *           auto-grow textarea (2.2), file icons (2.4), send-disable (2.5)
 * Phase 3: syntax highlighting via highlight.js + marked (3.1),
 *           SSE streaming responses (3.3), thumbs feedback (3.4)
 */

// ── DOM refs ───────────────────────────────────────────────────────────────
const chatArea          = document.getElementById('chat-area');
const userInput         = document.getElementById('user-input');
const sendBtn           = document.getElementById('send-btn');
const fileUpload        = document.getElementById('file-upload');
const attachmentPreview = document.getElementById('attachment-preview');
const uploadProgress    = document.getElementById('upload-progress');
const uploadProgressBar = document.getElementById('upload-progress-bar');
const newChatBtn        = document.getElementById('new-chat-btn');
const statusDot         = document.getElementById('status-dot');
const statusLabel       = document.getElementById('status-label');
const clarifyBanner     = document.getElementById('clarify-waiting');
const dropOverlay       = document.getElementById('drop-overlay');

const API_URL    = window.location.origin + '/api';
const SESSION_ID = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));

let currentFile  = null;
let lastFilePath = null;
let isSending    = false;

// ── Phase 3.1 — highlight.js + marked renderer ────────────────────────────
if (typeof hljs !== 'undefined' && typeof marked !== 'undefined') {
    marked.use({
        renderer: {
            code(token) {
                // Handle both marked v4 (string args) and v5+ (token object)
                const src  = (token && typeof token === 'object' && token.text  != null) ? token.text  : String(token);
                const lang = (token && typeof token === 'object' && token.lang  != null) ? token.lang  : (arguments[1] || '');
                const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
                const highlighted = hljs.highlight(src, { language: validLang, ignoreIllegals: true }).value;
                return `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`;
            }
        }
    });
}

// ── Action badge config ────────────────────────────────────────────────────
const BADGE_CONFIG = {
    summarize:         { label: '✦ Summarization',   cls: 'badge-summarize'         },
    sentiment:         { label: '✦ Sentiment',        cls: 'badge-sentiment'         },
    code_explain:      { label: '✦ Code Explanation', cls: 'badge-code_explain'      },
    chat:              { label: '✦ Conversation',     cls: 'badge-chat'              },
    ask_clarification: { label: '⏳ Awaiting reply',  cls: 'badge-ask_clarification' },
};

// ── Helpers ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function nowHHMM() {
    const d = new Date();
    return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
}

function logDotClass(line) {
    if (line.includes('✓')) return 'log-dot-ok';
    if (line.includes('⚙'))  return 'log-dot-run';
    if (line.includes('⚠'))  return 'log-dot-warn';
    if (line.includes('✗'))  return 'log-dot-err';
    return 'log-dot-info';
}

// ── Message component builders ─────────────────────────────────────────────
function makeCopyBtn(getText) {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.title = 'Copy response';
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2"/>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>`;
    btn.addEventListener('click', () => {
        navigator.clipboard.writeText(getText()).then(() => {
            btn.classList.add('copied');
            btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
            setTimeout(() => {
                btn.classList.remove('copied');
                btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
            }, 2000);
        });
    });
    return btn;
}

function addActionBadge(bubble, action) {
    const cfg = BADGE_CONFIG[action];
    if (!cfg) return;
    const badge = document.createElement('div');
    badge.className = `action-badge ${cfg.cls}`;
    badge.textContent = cfg.label;
    bubble.appendChild(badge);
}

function buildExtrasPanel(bubble, extractedContent, plan, logs) {
    if (extractedContent) {
        const det = document.createElement('details');
        det.className = 'extra-panel';
        det.innerHTML = `<summary>📄 Extracted content</summary><pre>${escapeHtml(extractedContent)}</pre>`;
        bubble.appendChild(det);
    }
    if (plan || (logs && logs.length)) {
        const det = document.createElement('details');
        det.className = 'extra-panel';
        const planHtml = plan ? `<pre class="plan-block">${escapeHtml(plan)}</pre>` : '';
        const logsHtml = (logs || []).map(line =>
            `<div class="log-line"><span class="log-dot ${logDotClass(line)}"></span><span>${escapeHtml(line)}</span></div>`
        ).join('');
        det.innerHTML = `<summary>🗂 Agent plan &amp; logs</summary>${planHtml}${logsHtml}`;
        bubble.appendChild(det);
    }
}

function addFeedbackRow(bubble, getText) {
    const row  = document.createElement('div');
    row.className = 'feedback-row';
    const upBtn   = document.createElement('button');
    const downBtn = document.createElement('button');
    upBtn.className   = 'thumb-btn thumb-up';
    downBtn.className = 'thumb-btn thumb-down';
    upBtn.title       = 'Helpful';
    downBtn.title     = 'Not helpful';
    upBtn.textContent   = '👍';
    downBtn.textContent = '👎';

    upBtn.addEventListener('click', () => {
        if (upBtn.disabled) return;
        upBtn.classList.add('active-up');
        downBtn.disabled    = true;
        console.log('[Feedback] 👍 Helpful:', getText().slice(0, 80));
    });
    downBtn.addEventListener('click', () => {
        if (downBtn.disabled) return;
        downBtn.classList.add('active-down');
        upBtn.disabled      = true;
        console.log('[Feedback] 👎 Not helpful:', getText().slice(0, 80));
    });

    row.appendChild(upBtn);
    row.appendChild(downBtn);
    bubble.appendChild(row);
}

// ── Generic message (user bubbles + error bubbles) ─────────────────────────
function addMessage(content, { isUser = false, isError = false } = {}) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('message', isUser ? 'user-message' : 'bot-message');
    if (isError) wrapper.classList.add('message-error');

    const bubble = document.createElement('div');
    bubble.classList.add('message-content');
    bubble.textContent = content;   // plain text only for user / error messages

    wrapper.appendChild(bubble);
    const ts = document.createElement('div');
    ts.className    = 'msg-timestamp';
    ts.textContent  = nowHHMM();
    wrapper.appendChild(ts);
    chatArea.appendChild(wrapper);
    chatArea.scrollTop = chatArea.scrollHeight;
    return bubble;
}

function addLoadingBubble() {
    const div = document.createElement('div');
    div.classList.add('message', 'bot-message');
    div.innerHTML = `<div class="message-content loading-dots">Thinking<span>.</span><span>.</span><span>.</span></div>`;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
}

// ── Attachment preview ─────────────────────────────────────────────────────
const FILE_ICONS = { pdf:'📄', jpg:'🖼', jpeg:'🖼', png:'🖼', mp3:'🎵', wav:'🎵', m4a:'🎵' };

function setAttachmentPreview(file) {
    attachmentPreview.innerHTML = '';
    if (!file) { attachmentPreview.style.display = 'none'; return; }
    const ext  = file.name.split('.').pop().toLowerCase();
    const icon = FILE_ICONS[ext] || '📎';
    const span = document.createElement('span');
    span.textContent = `${icon} ${file.name}`;
    const dismiss = document.createElement('button');
    dismiss.className   = 'dismiss-attach';
    dismiss.textContent = '✕';
    dismiss.title       = 'Remove attachment';
    dismiss.onclick     = () => {
        currentFile = null; lastFilePath = null;
        fileUpload.value = '';
        setAttachmentPreview(null);
    };
    attachmentPreview.appendChild(span);
    attachmentPreview.appendChild(dismiss);
    attachmentPreview.style.display = 'flex';
}

// ── Phase 2.3 — XHR upload with progress ──────────────────────────────────
function uploadFileXHR(file) {
    return new Promise((resolve, reject) => {
        const fd  = new FormData();
        fd.append('file', file);
        const xhr = new XMLHttpRequest();

        uploadProgress.style.display    = 'block';
        uploadProgressBar.style.width   = '0%';

        xhr.upload.addEventListener('progress', e => {
            if (e.lengthComputable) {
                uploadProgressBar.style.width = Math.round(e.loaded / e.total * 100) + '%';
            }
        });
        xhr.addEventListener('load', () => {
            uploadProgress.style.display  = 'none';
            uploadProgressBar.style.width = '0%';
            if (xhr.status === 200) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                let detail = `Upload failed (${xhr.status})`;
                try { detail = JSON.parse(xhr.responseText).detail || detail; } catch {}
                reject(new Error(detail));
            }
        });
        xhr.addEventListener('error', () => {
            uploadProgress.style.display = 'none';
            reject(new Error('Network error during upload'));
        });

        xhr.open('POST', `${API_URL}/upload`);
        xhr.send(fd);
    });
}

// ── Clarification banner ───────────────────────────────────────────────────
function showClarifyBanner(show) {
    clarifyBanner.style.display = show ? 'flex' : 'none';
}

// ── Auto-grow textarea ─────────────────────────────────────────────────────
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
});

// ── Health check ───────────────────────────────────────────────────────────
async function checkHealth() {
    statusDot.className   = 'dot checking';
    statusLabel.textContent = 'Checking…';
    try {
        const r = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(4000) });
        statusDot.className   = r.ok ? 'dot' : 'dot offline';
        statusLabel.textContent = r.ok ? 'Online' : 'Offline';
    } catch {
        statusDot.className   = 'dot offline';
        statusLabel.textContent = 'Offline';
    }
}
checkHealth();
setInterval(checkHealth, 15000);

// ── New chat ───────────────────────────────────────────────────────────────
newChatBtn.addEventListener('click', () => window.location.reload());

// ── Prompt chips ───────────────────────────────────────────────────────────
document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
        userInput.value = chip.dataset.prompt || '';
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
        userInput.focus();
        if (chip.dataset.needsFile) fileUpload.click();
    });
});

// ── Phase 3.3 — Streaming SSE ─────────────────────────────────────────────
async function sendStream(text, filePath, loaderEl) {
    const resp = await fetch(`${API_URL}/chat/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: text, file_path: filePath, session_id: SESSION_ID }),
    });

    if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch {}
        throw new Error(detail);
    }

    loaderEl.remove();

    // Build streaming bubble
    const wrapper = document.createElement('div');
    wrapper.classList.add('message', 'bot-message', 'streaming');

    const bubble = document.createElement('div');
    bubble.classList.add('message-content');

    const streamSpan = document.createElement('span');
    streamSpan.className = 'stream-cursor';
    bubble.appendChild(streamSpan);
    wrapper.appendChild(bubble);

    const ts = document.createElement('div');
    ts.className   = 'msg-timestamp';
    ts.textContent = nowHHMM();
    wrapper.appendChild(ts);

    chatArea.appendChild(wrapper);
    chatArea.scrollTop = chatArea.scrollHeight;

    // Read SSE stream
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';
    let fullText  = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        sseBuffer += decoder.decode(value, { stream: true });
        const parts = sseBuffer.split('\n\n');
        sseBuffer   = parts.pop() ?? '';

        for (const part of parts) {
            if (!part.startsWith('data: ')) continue;
            let data;
            try { data = JSON.parse(part.slice(6)); } catch { continue; }

            if (data.type === 'token') {
                fullText += data.content;
                streamSpan.textContent = fullText;
                chatArea.scrollTop = chatArea.scrollHeight;

            } else if (data.type === 'done') {
                wrapper.classList.remove('streaming');

                // Re-render bubble with full markdown + all extras
                let capturedText = fullText;
                bubble.innerHTML = '';
                bubble.appendChild(makeCopyBtn(() => capturedText));

                const mdDiv = document.createElement('div');
                mdDiv.innerHTML = marked.parse(fullText);
                bubble.appendChild(mdDiv);

                addActionBadge(bubble, data.action);
                buildExtrasPanel(bubble, data.extracted_content, data.plan, data.logs);
                addFeedbackRow(bubble, () => capturedText);

                chatArea.scrollTop = chatArea.scrollHeight;

                if (data.action === 'ask_clarification') {
                    showClarifyBanner(true);
                } else {
                    lastFilePath = null;
                }

            } else if (data.type === 'error') {
                wrapper.classList.add('message-error');
                bubble.innerHTML  = '';
                bubble.textContent = `Error: ${data.content}`;
            }
        }
    }
}

// ── Send orchestrator ──────────────────────────────────────────────────────
async function handleSend() {
    const text = userInput.value.trim();
    if ((!text && !currentFile && !lastFilePath) || isSending) return;

    isSending        = true;
    sendBtn.disabled = true;
    showClarifyBanner(false);

    // User bubble
    let displayMsg = text;
    if (currentFile) {
        const ext  = currentFile.name.split('.').pop().toLowerCase();
        const icon = FILE_ICONS[ext] || '📎';
        displayMsg = (text ? text + '\n' : '') + `${icon} ${currentFile.name}`;
    } else if (lastFilePath && !text) {
        displayMsg = '(continuing with previous file)';
    }
    addMessage(displayMsg, { isUser: true });

    userInput.value        = '';
    userInput.style.height = 'auto';
    const tempFile = currentFile;
    currentFile    = null;
    setAttachmentPreview(null);
    fileUpload.value = '';

    const loader = addLoadingBubble();

    try {
        if (tempFile) {
            const upData = await uploadFileXHR(tempFile);
            lastFilePath = upData.filepath;
        }

        await sendStream(text, lastFilePath || null, loader);

    } catch (err) {
        loader.remove();
        addMessage(`Error: ${err.message}`, { isError: true });
        lastFilePath = null;
    } finally {
        isSending        = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

sendBtn.addEventListener('click', handleSend);
userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
});
fileUpload.addEventListener('change', e => {
    if (e.target.files.length > 0) {
        currentFile  = e.target.files[0];
        lastFilePath = null;
        setAttachmentPreview(currentFile);
    }
});

// ── Drag-and-drop ──────────────────────────────────────────────────────────
const appContainer = document.querySelector('.app-container');
appContainer.addEventListener('dragover', e => {
    e.preventDefault();
    dropOverlay.classList.add('active');
});
appContainer.addEventListener('dragleave', e => {
    if (!appContainer.contains(e.relatedTarget)) dropOverlay.classList.remove('active');
});
appContainer.addEventListener('drop', e => {
    e.preventDefault();
    dropOverlay.classList.remove('active');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const ext     = '.' + file.name.split('.').pop().toLowerCase();
    const allowed = ['.pdf','.jpg','.jpeg','.png','.mp3','.wav','.m4a'];
    if (!allowed.includes(ext)) {
        addMessage(`File type "${ext}" not supported. Allowed: PDF, image, or audio.`, { isError: true });
        return;
    }
    currentFile  = file;
    lastFilePath = null;
    setAttachmentPreview(file);
});
