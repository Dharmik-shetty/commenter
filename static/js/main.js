/* ═══════════════════════════════════════════════════════════════════
   AI Comment Bot — Dashboard JavaScript
   ═══════════════════════════════════════════════════════════════════ */

// ── Globals ────────────────────────────────────────────────────────
const API = '';  // Base URL (same origin)
let socket = null;

document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    initTooltips();
    initModals();

    // Page-specific init
    const page = document.body.dataset.page;
    if (page === 'dashboard') initDashboard();
    else if (page === 'reddit') initRedditPage();
    else if (page === 'instagram') initInstagramPage();
    else if (page === 'youtube') initYouTubePage();
    else if (page === 'accounts') initAccountsPage();
    else if (page === 'ai-settings') initAISettingsPage();
    else if (page === 'logs') initLogsPage();
});

// ═══════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════

async function apiFetch(path, options = {}) {
    const defaults = {
        headers: { 'Content-Type': 'application/json' },
    };
    const res = await fetch(API + path, { ...defaults, ...options });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="bi bi-${type === 'success' ? 'check-circle' : type === 'error' ? 'x-circle' : 'info-circle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function formatTime(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function truncate(str, len = 60) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '…' : str;
}

// ═══════════════════════════════════════════════════════════════════
// WEBSOCKET
// ═══════════════════════════════════════════════════════════════════

function initSocket() {
    if (typeof io === 'undefined') return;
    socket = io();
    socket.on('new_log', (log) => {
        // Append to live feed if present
        const feed = document.getElementById('live-feed');
        if (feed) addLogEntry(feed, log);
        // Update counters
        refreshStats();
    });
}

function addLogEntry(feed, log) {
    const statusClass = log.status === 'success' ? 'badge-success' : log.status === 'failed' ? 'badge-danger' : 'badge-warning';
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-time">${formatTime(log.created_at)}</span>
        <span class="log-platform ${log.platform}">${log.platform}</span>
        <span class="log-text">${truncate(log.post_title || log.search_keyword, 50)} — <em>${truncate(log.comment_text, 40)}</em></span>
        <span class="log-status"><span class="badge ${statusClass}">${log.status}</span></span>
    `;
    feed.prepend(entry);
    // Keep max 50 entries
    while (feed.children.length > 50) feed.lastChild.remove();
}

// ═══════════════════════════════════════════════════════════════════
// MODALS
// ═══════════════════════════════════════════════════════════════════

function initModals() {
    document.querySelectorAll('[data-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modal = document.getElementById(btn.dataset.modal);
            if (modal) modal.classList.add('show');
        });
    });
    document.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal-overlay').classList.remove('show');
        });
    });
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('show');
        });
    });
}

function initTooltips() { /* Future enhancement */ }

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════

let statsInterval = null;

async function refreshStats() {
    try {
        const data = await apiFetch('/api/dashboard/stats');

        setTextById('stat-total', data.total_today);
        setTextById('stat-success', data.success_today);
        setTextById('stat-rate', data.success_rate + '%');
        setTextById('stat-bots', data.running_bots);

        // Platform cards
        for (const p of ['reddit', 'instagram', 'youtube']) {
            const pd = data.platforms[p] || {};
            setTextById(`${p}-comments`, pd.success || 0);
            setTextById(`${p}-accounts`, pd.accounts || 0);
            setTextById(`${p}-running`, pd.running || 0);
            setTextById(`${p}-total`, pd.total || 0);

            // Status dot
            const dot = document.getElementById(`${p}-status-dot`);
            if (dot) {
                dot.className = 'status-dot ' + (pd.running > 0 ? 'green' : 'gray');
            }
        }

        // Top bar status
        const topDot = document.getElementById('global-status-dot');
        if (topDot) topDot.className = 'status-dot ' + (data.running_bots > 0 ? 'green' : 'gray');
        setTextById('global-status-text', data.running_bots > 0 ? `${data.running_bots} bots running` : 'All bots idle');

    } catch (e) {
        console.error('Stats refresh failed:', e);
    }
}

function setTextById(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function initDashboard() {
    refreshStats();
    loadRecentLogs();
    statsInterval = setInterval(refreshStats, 5000);
}

async function loadRecentLogs() {
    try {
        const data = await apiFetch('/api/logs?limit=30');
        const feed = document.getElementById('live-feed');
        if (!feed) return;
        feed.innerHTML = '';
        (data.logs || []).forEach(log => addLogEntry(feed, log));
        if (data.logs.length === 0) {
            feed.innerHTML = '<div class="empty-state"><i class="bi bi-chat-dots"></i><p>No activity yet. Start a bot to see live logs.</p></div>';
        }
    } catch (e) {
        console.error('Load logs failed:', e);
    }
}

// ═══════════════════════════════════════════════════════════════════
// STOP ALL
// ═══════════════════════════════════════════════════════════════════

async function stopAllBots() {
    try {
        await apiFetch('/api/bot/stop-all', { method: 'POST' });
        showToast('All bots stopped', 'success');
        refreshStats();
    } catch (e) {
        showToast('Failed to stop bots: ' + e.message, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════
// REDDIT PAGE
// ═══════════════════════════════════════════════════════════════════

async function initRedditPage() {
    await loadSettings();
    await loadSubreddits();
    await loadKeywords('reddit');
    initRangeSliders();
}

async function loadSubreddits() {
    try {
        const subs = await apiFetch('/api/subreddits');
        const container = document.getElementById('subreddit-list');
        if (!container) return;
        container.innerHTML = '';
        if (subs.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No subreddits added</p></div>';
            return;
        }
        subs.forEach(s => {
            const tag = document.createElement('div');
            tag.className = 'tag';
            tag.innerHTML = `
                <span>r/${s.name}</span>
                <span style="color:var(--text-muted);font-size:11px">${s.sort_method}</span>
                <span class="tag-remove" onclick="removeSubreddit(${s.id})" title="Remove">
                    <i class="bi bi-x"></i>
                </span>
            `;
            container.appendChild(tag);
        });
    } catch (e) { console.error(e); }
}

async function addSubreddit() {
    const input = document.getElementById('subreddit-input');
    const sort = document.getElementById('subreddit-sort');
    const raw = input.value.trim();
    if (!raw) return;
    const names = raw.split(',').map(s => s.trim()).filter(Boolean);
    let added = 0, errors = [];
    for (const name of names) {
        try {
            await apiFetch('/api/subreddits', {
                method: 'POST',
                body: JSON.stringify({ name, sort_method: sort ? sort.value : 'hot' }),
            });
            added++;
        } catch (e) {
            errors.push(`r/${name}: ${e.message}`);
        }
    }
    input.value = '';
    if (added) showToast(`${added} subreddit(s) added`, 'success');
    if (errors.length) showToast(errors.join('; '), 'error');
    loadSubreddits();
}

async function removeSubreddit(id) {
    try {
        await apiFetch(`/api/subreddits/${id}`, { method: 'DELETE' });
        loadSubreddits();
    } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// KEYWORDS (shared across platforms)
// ═══════════════════════════════════════════════════════════════════

async function loadKeywords(platform) {
    try {
        const keywords = await apiFetch(`/api/keywords?platform=${platform}`);
        const container = document.getElementById(`${platform}-keyword-list`);
        if (!container) return;
        container.innerHTML = '';
        if (keywords.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No keywords added</p></div>';
            return;
        }
        keywords.forEach(k => {
            const tag = document.createElement('div');
            tag.className = 'tag';
            tag.innerHTML = `
                <span>${k.keyword}</span>
                <span class="tag-remove" onclick="removeKeyword('${platform}', ${k.id})" title="Remove">
                    <i class="bi bi-x"></i>
                </span>
            `;
            container.appendChild(tag);
        });
    } catch (e) { console.error(e); }
}

async function addKeyword(platform) {
    const input = document.getElementById(`${platform}-keyword-input`);
    const raw = input.value.trim();
    if (!raw) return;
    const keywords = raw.split(',').map(s => s.trim()).filter(Boolean);
    let added = 0, errors = [];
    for (const keyword of keywords) {
        try {
            await apiFetch('/api/keywords', {
                method: 'POST',
                body: JSON.stringify({ platform, keyword }),
            });
            added++;
        } catch (e) {
            errors.push(`"${keyword}": ${e.message}`);
        }
    }
    input.value = '';
    if (added) showToast(`${added} keyword(s) added`, 'success');
    if (errors.length) showToast(errors.join('; '), 'error');
    loadKeywords(platform);
}

async function removeKeyword(platform, id) {
    try {
        await apiFetch(`/api/keywords/${id}`, { method: 'DELETE' });
        loadKeywords(platform);
    } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// RANGE SLIDER HELPERS
// ═══════════════════════════════════════════════════════════════════

function initRangeSliders() {
    document.querySelectorAll('input[type="range"]').forEach(slider => {
        const output = document.getElementById(slider.id + '-value');
        if (output) {
            output.textContent = slider.value;
            slider.addEventListener('input', () => {
                output.textContent = slider.value;
            });
        }
    });
}

// ═══════════════════════════════════════════════════════════════════
// SETTINGS (load & save)
// ═══════════════════════════════════════════════════════════════════

let currentSettings = {};

async function loadSettings() {
    try {
        currentSettings = await apiFetch('/api/settings');
        applySettingsToForm();
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

function applySettingsToForm() {
    for (const [key, value] of Object.entries(currentSettings)) {
        const el = document.getElementById('setting-' + key);
        if (!el) continue;
        if (el.type === 'checkbox') {
            el.checked = value === 'true' || value === true;
        } else if (el.type === 'range') {
            el.value = value;
            const out = document.getElementById('setting-' + key + '-value');
            if (out) out.textContent = value;
        } else {
            el.value = value;
        }
    }
}

async function saveSettings(keys) {
    const data = {};
    keys.forEach(key => {
        const el = document.getElementById('setting-' + key);
        if (!el) return;
        if (el.type === 'checkbox') {
            data[key] = el.checked ? 'true' : 'false';
        } else {
            data[key] = el.value;
        }
    });
    try {
        await apiFetch('/api/settings', {
            method: 'POST',
            body: JSON.stringify(data),
        });
        showToast('Settings saved', 'success');
    } catch (e) {
        showToast('Failed to save: ' + e.message, 'error');
    }
}

function saveRedditSettings() {
    saveSettings([
        'reddit_min_delay', 'reddit_max_delay', 'reddit_daily_limit',
        'reddit_start_hour', 'reddit_end_hour', 'reddit_sort_method',
        'reddit_posts_per_visit', 'reddit_match_threshold', 'reddit_preprompt',
    ]);
}

function saveInstagramSettings() {
    saveSettings([
        'instagram_min_delay', 'instagram_max_delay', 'instagram_daily_limit',
        'instagram_start_hour', 'instagram_end_hour', 'instagram_preprompt',
    ]);
}

function saveYouTubeSettings() {
    saveSettings([
        'youtube_min_delay', 'youtube_max_delay', 'youtube_daily_limit',
        'youtube_start_hour', 'youtube_end_hour', 'youtube_preprompt',
    ]);
}

function saveAISettings() {
    saveSettings([
        'gemini_api_key', 'gemini_model', 'gemini_temperature',
        'gemini_max_tokens', 'gemini_top_p', 'gemini_top_k',
    ]);
}

// ═══════════════════════════════════════════════════════════════════
// BOT CONTROLS
// ═══════════════════════════════════════════════════════════════════

async function startBot(platform) {
    const btn = document.getElementById(`${platform}-start-btn`);
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Starting…'; }
    try {
        const data = await apiFetch(`/api/bot/${platform}/start`, { method: 'POST' });
        let msg = `${platform} bot started (${data.count} accounts)`;
        if (data.queued_count > 0) {
            msg += `, ${data.queued_count} queued (limit: ${data.platform_limit} concurrent)`;
        }
        showToast(msg, 'success');
        // Show proxy warnings if any
        if (data.proxy_warnings && data.proxy_warnings.length > 0) {
            data.proxy_warnings.forEach(w => showToast(`⚠️ ${w}`, 'warning'));
        }
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `<i class="bi bi-play-fill"></i> Start Bot`; }
    }
}

async function stopBot(platform) {
    try {
        await apiFetch(`/api/bot/${platform}/stop`, { method: 'POST' });
        showToast(`${platform} bot stopped`, 'success');
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════
// INSTAGRAM PAGE
// ═══════════════════════════════════════════════════════════════════

async function initInstagramPage() {
    await loadSettings();
    await loadKeywords('instagram');
    initRangeSliders();
}

// ═══════════════════════════════════════════════════════════════════
// YOUTUBE PAGE
// ═══════════════════════════════════════════════════════════════════

async function initYouTubePage() {
    await loadSettings();
    await loadKeywords('youtube');
    initRangeSliders();
}

// ═══════════════════════════════════════════════════════════════════
// ACCOUNTS PAGE
// ═══════════════════════════════════════════════════════════════════

async function initAccountsPage() {
    await loadAllAccounts();
}

async function loadAllAccounts() {
    try {
        const accounts = await apiFetch('/api/accounts');
        renderAccountTable('reddit', accounts.filter(a => a.platform === 'reddit'));
        renderAccountTable('instagram', accounts.filter(a => a.platform === 'instagram'));
        renderAccountTable('youtube', accounts.filter(a => a.platform === 'youtube'));
    } catch (e) { console.error(e); }
}

function renderAccountTable(platform, accounts) {
    const tbody = document.getElementById(`${platform}-accounts-tbody`);
    if (!tbody) return;
    tbody.innerHTML = '';
    if (accounts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state"><p>No ${platform} accounts</p></td></tr>`;
        return;
    }
    accounts.forEach(a => {
        const statusBadge = a.status === 'running'
            ? '<span class="badge badge-success">Running</span>'
            : a.status === 'error'
                ? '<span class="badge badge-danger">Error</span>'
                : '<span class="badge badge-info">Idle</span>';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${a.username}</strong></td>
            <td>${statusBadge}</td>
            <td>${a.comments_today} / ${a.daily_limit}</td>
            <td>${a.proxy || '<span style="color:var(--danger)" title="No proxy — high detection risk">⚠ None</span>'}</td>
            <td>${a.last_comment_at ? formatDate(a.last_comment_at) : '—'}</td>
            <td>
                <div class="flex gap-8">
                    <label class="toggle">
                        <input type="checkbox" ${a.is_active ? 'checked' : ''} onchange="toggleAccount(${a.id}, this.checked)">
                        <span class="slider"></span>
                    </label>
                    <button class="btn-icon" onclick="deleteAccount(${a.id})" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function addAccount() {
    const platform = document.getElementById('acc-platform').value;
    const username = document.getElementById('acc-username').value.trim();
    const password = document.getElementById('acc-password').value;
    const email = document.getElementById('acc-email').value.trim();
    const proxy = document.getElementById('acc-proxy').value.trim();
    const dailyLimit = document.getElementById('acc-limit').value || 1000;

    if (!username || !password) {
        showToast('Username and password required', 'error');
        return;
    }

    try {
        await apiFetch('/api/accounts', {
            method: 'POST',
            body: JSON.stringify({ platform, username, password, email, proxy, daily_limit: parseInt(dailyLimit) }),
        });
        showToast(`Account ${username} added`, 'success');
        document.getElementById('add-account-modal').classList.remove('show');
        // Clear form
        ['acc-username', 'acc-password', 'acc-email', 'acc-proxy'].forEach(id => {
            document.getElementById(id).value = '';
        });
        loadAllAccounts();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function toggleAccount(id, active) {
    try {
        await apiFetch(`/api/accounts/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ is_active: active }),
        });
    } catch (e) { showToast(e.message, 'error'); }
}

async function deleteAccount(id) {
    if (!confirm('Delete this account?')) return;
    try {
        await apiFetch(`/api/accounts/${id}`, { method: 'DELETE' });
        showToast('Account deleted', 'success');
        loadAllAccounts();
    } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// AI SETTINGS PAGE
// ═══════════════════════════════════════════════════════════════════

async function initAISettingsPage() {
    await loadSettings();
    initRangeSliders();
    initConcurrencyUI();
}

async function testAIConnection() {
    const btn = document.getElementById('test-ai-btn');
    if (btn) btn.innerHTML = '<span class="spinner"></span> Testing…';
    try {
        const data = await apiFetch('/api/settings/test-ai', { method: 'POST' });
        if (data.connected) {
            showToast('Gemini AI connected successfully!', 'success');
        } else {
            showToast('Connection failed. Check API key.', 'error');
        }
    } catch (e) {
        showToast('Connection test failed: ' + e.message, 'error');
    } finally {
        if (btn) btn.innerHTML = '<i class="bi bi-plug"></i> Test Connection';
    }
}
function saveConcurrencySettings() {
    saveSettings([
        'max_concurrent', 'concurrent_reddit',
        'concurrent_youtube', 'concurrent_instagram',
    ]);
}

function initConcurrencyUI() {
    // Update RAM estimate when any concurrency slider changes
    const sliderIds = ['setting-max_concurrent', 'setting-concurrent_reddit',
                       'setting-concurrent_youtube', 'setting-concurrent_instagram'];
    sliderIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', updateRAMEstimate);
        }
    });
    updateRAMEstimate();
}

function updateRAMEstimate() {
    const total = parseInt(document.getElementById('setting-max_concurrent')?.value || 5);
    const reddit = parseInt(document.getElementById('setting-concurrent_reddit')?.value || 3);
    const youtube = parseInt(document.getElementById('setting-concurrent_youtube')?.value || 1);
    const instagram = parseInt(document.getElementById('setting-concurrent_instagram')?.value || 1);

    // Use the actual concurrent count (capped by total)
    const platformSum = reddit + youtube + instagram;
    const effective = Math.min(total, platformSum);

    // ~250 MB per browser instance + ~500 MB base
    const ramGB = ((effective * 250) + 500) / 1024;
    const el = document.getElementById('ram-estimate');
    if (el) {
        el.textContent = `~${ramGB.toFixed(1)} GB`;
        if (ramGB > 8) {
            el.style.color = 'var(--danger)';
        } else if (ramGB > 4) {
            el.style.color = 'var(--warning, orange)';
        } else {
            el.style.color = 'var(--success, #22c55e)';
        }
    }
}
// ═══════════════════════════════════════════════════════════════════
// LOGS PAGE
// ═══════════════════════════════════════════════════════════════════

async function initLogsPage() {
    await loadLogs();
}

async function loadLogs(filters = {}) {
    try {
        let url = '/api/logs?limit=200';
        if (filters.platform) url += `&platform=${filters.platform}`;
        if (filters.status) url += `&status=${filters.status}`;

        const data = await apiFetch(url);
        const tbody = document.getElementById('logs-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        setTextById('logs-total', `${data.total} total`);

        if (data.logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><p>No logs found</p></td></tr>';
            return;
        }

        data.logs.forEach(log => {
            const statusBadge = log.status === 'success'
                ? '<span class="badge badge-success">Success</span>'
                : log.status === 'failed'
                    ? '<span class="badge badge-danger">Failed</span>'
                    : '<span class="badge badge-warning">Pending</span>';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${formatDate(log.created_at)}</td>
                <td><span class="log-platform ${log.platform}">${log.platform}</span></td>
                <td>${log.account_username}</td>
                <td title="${log.post_title}">${truncate(log.post_title, 35)}</td>
                <td title="${log.comment_text}">${truncate(log.comment_text, 40)}</td>
                <td>${statusBadge}</td>
                <td>${log.match_score ? (log.match_score * 100).toFixed(0) + '%' : '—'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Load logs failed:', e);
    }
}

function filterLogs() {
    const platform = document.getElementById('filter-platform').value;
    const status = document.getElementById('filter-status').value;
    loadLogs({ platform, status });
}

async function clearAllLogs() {
    if (!confirm('Clear all logs? This cannot be undone.')) return;
    try {
        await apiFetch('/api/logs/clear', { method: 'POST' });
        showToast('Logs cleared', 'success');
        loadLogs();
    } catch (e) { showToast(e.message, 'error'); }
}
