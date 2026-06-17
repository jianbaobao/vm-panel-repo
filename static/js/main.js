/**
 * VM Management Panel — 主 JavaScript
 * 全局工具函数: Toast 通知, AJAX 辅助等
 */

// ── Toast 通知系统 ───────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
        success: 'bi-check-circle-fill text-success',
        error: 'bi-x-circle-fill text-danger',
        info: 'bi-info-circle-fill text-info',
        warning: 'bi-exclamation-triangle-fill text-warning',
    };

    const iconClass = icons[type] || icons.info;
    const toastId = 'toast-' + Date.now();

    const toastEl = document.createElement('div');
    toastEl.className = `toast ${type}`;
    toastEl.id = toastId;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');

    toastEl.innerHTML = `
        <div class="toast-header">
            <i class="bi ${iconClass} me-2"></i>
            <strong class="me-auto">VM Panel</strong>
            <small>刚刚</small>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
        </div>
        <div class="toast-body">${message}</div>
    `;

    container.appendChild(toastEl);

    const toast = new bootstrap.Toast(toastEl, {
        autohide: true,
        delay: duration,
    });
    toast.show();

    // 隐藏后移除 DOM
    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

// ── 确认对话框 (替代原生 confirm) ────────────────────────

function showConfirm(title, message) {
    return new Promise((resolve) => {
        const modalId = 'confirm-modal-' + Date.now();
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = modalId;
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">${message}</div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button class="btn btn-danger" id="confirm-yes-${modalId}">确定</button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(modal);

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        document.getElementById(`confirm-yes-${modalId}`).onclick = () => {
            bsModal.hide();
            modal.addEventListener('hidden.bs.modal', () => modal.remove());
            resolve(true);
        };

        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
            resolve(false);
        });
    });
}

// ── 加载指示器 ───────────────────────────────────────────

let loadingOverlay = null;

function showLoading(message = '处理中...') {
    if (loadingOverlay) return;
    loadingOverlay = document.createElement('div');
    loadingOverlay.className = 'spinner-overlay';
    loadingOverlay.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" style="width:3rem;height:3rem" role="status"></div>
            <p class="mt-2 text-light">${message}</p>
        </div>`;
    document.body.appendChild(loadingOverlay);
}

function hideLoading() {
    if (loadingOverlay) {
        loadingOverlay.remove();
        loadingOverlay = null;
    }
}

// ── AJAX 辅助 ────────────────────────────────────────────

async function apiFetch(url, options = {}) {
    const config = {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();
        if (!data.ok) {
            showToast(data.error || '请求失败', 'error');
        }
        return data;
    } catch (err) {
        showToast('网络错误: ' + err.message, 'error');
        return { ok: false, error: err.message };
    }
}

// ── 时间格式化 ───────────────────────────────────────────

function formatUptime(seconds) {
    if (!seconds || seconds <= 0) return '-';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const parts = [];
    if (d > 0) parts.push(`${d}d`);
    if (h > 0) parts.push(`${h}h`);
    if (m > 0) parts.push(`${m}m`);
    if (s > 0 && d === 0) parts.push(`${s}s`);
    return parts.join(' ') || '<1s';
}

// ── 页面加载完成 ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    // 显示模拟模式提示
    const badge = document.getElementById('sim-mode-badge');
    if (badge) {
        badge.style.display = 'inline-block';
    }

    // 加载顶部栏宿主机名
    const hostInfo = document.getElementById('host-info');
    if (hostInfo) {
        fetch('/api/host/info')
            .then(r => r.json())
            .then(res => {
                if (res.ok) {
                    const h = res.data;
                    hostInfo.innerHTML = `<i class="bi bi-hdd-network"></i> ${h.hostname}`;
                }
            })
            .catch(() => {
                hostInfo.innerHTML = `<i class="bi bi-exclamation-triangle"></i> 连接失败`;
            });
    }

    // 自动刷新仪表盘数据 (每 10 秒)
    if (window.location.pathname === '/') {
        setInterval(() => {
            fetch('/api/host/stats')
                .then(r => r.json())
                .then(res => {
                    if (res.ok) {
                        const s = res.data;
                        const cpuEl = document.getElementById('host-cpu');
                        const memEl = document.getElementById('host-memory');
                        if (cpuEl) cpuEl.textContent = `${s.cpu_percent}%`;
                        if (memEl) memEl.textContent = `${s.memory_percent}%`;
                    }
                });
        }, 10000);
    }
});
