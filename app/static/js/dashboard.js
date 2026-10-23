/**
 * LinkForge Frontend Dashboard Logic
 * Handles asynchronous URL creation, real-time analytics calculations,
 * responsive table rendering, search filtering, and clipboard interactions.
 */

(function () {
    'use strict';

    // State
    let allLinks = [];

    // DOM Elements
    const elements = {
        sidebar: document.getElementById('sidebar'),
        sidebarOverlay: document.getElementById('sidebarOverlay'),
        mobileMenuBtn: document.getElementById('mobileMenuBtn'),

        // Nav items
        navDashboard: document.getElementById('navDashboard'),
        navLinks: document.getElementById('navLinks'),
        navAnalytics: document.getElementById('navAnalytics'),

        refreshBtn: document.getElementById('refreshBtn'),
        shortenForm: document.getElementById('shortenForm'),
        submitBtn: document.getElementById('submitBtn'),
        urlInput: document.getElementById('urlInput'),
        urlInputError: document.getElementById('urlInputError'),
        aliasInput: document.getElementById('aliasInput'),
        aliasInputError: document.getElementById('aliasInputError'),
        expiresInput: document.getElementById('expiresInput'),
        expiresInputError: document.getElementById('expiresInputError'),
        baseUrlPrefix: document.getElementById('baseUrlPrefix'),
        pasteBtn: document.getElementById('pasteBtn'),

        // Stats Cards
        statTotalLinks: document.getElementById('statTotalLinks'),
        statTotalClicks: document.getElementById('statTotalClicks'),
        statActiveLinks: document.getElementById('statActiveLinks'),
        statExpiredLinks: document.getElementById('statExpiredLinks'),

        // Result Banner
        resultBanner: document.getElementById('resultBanner'),
        resultShortUrl: document.getElementById('resultShortUrl'),
        resultOriginalUrl: document.getElementById('resultOriginalUrl'),
        resultShortCode: document.getElementById('resultShortCode'),
        copyResultBtn: document.getElementById('copyResultBtn'),
        openResultLink: document.getElementById('openResultLink'),
        closeResultBtn: document.getElementById('closeResultBtn'),

        // Table Elements
        searchInput: document.getElementById('searchInput'),
        linksTableBody: document.getElementById('linksTableBody'),
        tableLoading: document.getElementById('tableLoading'),
        tableEmpty: document.getElementById('tableEmpty'),
        tableError: document.getElementById('tableError'),
        tableErrorMessage: document.getElementById('tableErrorMessage'),
        tableRetryBtn: document.getElementById('tableRetryBtn'),

        // Toast Container
        toastContainer: document.getElementById('toastContainer')
    };

    /**
     * Escape HTML entities to prevent Cross-Site Scripting (XSS).
     * @param {string} str - Untrusted string input.
     * @returns {string} Sanitized HTML string.
     */
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * Display a floating toast notification.
     * @param {string} message - Notification text.
     * @param {'success'|'error'|'info'} [type='success'] - Toast style type.
     */
    function showToast(message, type = 'success') {
        if (!elements.toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let iconSvg;
        if (type === 'success') {
            iconSvg = '<svg class="toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        } else if (type === 'error') {
            iconSvg = '<svg class="toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';
        } else {
            iconSvg = '<svg class="toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
        }

        toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
        elements.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.25s ease';
            setTimeout(() => toast.remove(), 250);
        }, 3200);
    }

    /**
     * Copy text to clipboard with fallback for non-secure or restricted contexts.
     * @param {string} text - Content to copy.
     * @returns {Promise<boolean>} True if successful.
     */
    async function copyToClipboard(text) {
        if (!text) return false;

        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (e) {
                console.warn('Clipboard API failed, attempting fallback', e);
            }
        }

        // Fallback for older browsers or non-secure HTTP contexts
        try {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            return successful;
        } catch (err) {
            console.error('Fallback clipboard copy failed:', err);
            return false;
        }
    }

    /**
     * Format ISO-8601 timestamp to human-friendly local date string.
     * @param {string|null} isoString 
     * @returns {string} Formatted date or 'Permanent'
     */
    function formatDate(isoString) {
        if (!isoString) return '<span style="color: var(--text-muted); font-size: 0.8rem;">Permanent</span>';
        try {
            const date = new Date(isoString);
            if (isNaN(date.getTime())) return isoString;
            return date.toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return isoString;
        }
    }

    /**
     * Clear all inline form errors.
     */
    function clearFormErrors() {
        if (elements.urlInput) elements.urlInput.classList.remove('is-invalid');
        if (elements.aliasInput) elements.aliasInput.classList.remove('is-invalid');
        if (elements.expiresInput) elements.expiresInput.classList.remove('is-invalid');

        if (elements.urlInputError) elements.urlInputError.textContent = '';
        if (elements.aliasInputError) elements.aliasInputError.textContent = '';
        if (elements.expiresInputError) elements.expiresInputError.textContent = '';
    }

    /**
     * Update dashboard statistics cards based on retrieved link records.
     * @param {Array} links - Array of URLRecord objects.
     */
    function updateStatistics(links) {
        const totalLinks = links.length;
        const totalClicks = links.reduce((sum, link) => sum + (Number(link.click_count) || 0), 0);
        const activeLinks = links.filter(link => !link.is_expired).length;
        const expiredLinks = links.filter(link => link.is_expired).length;

        if (elements.statTotalLinks) elements.statTotalLinks.textContent = totalLinks.toLocaleString();
        if (elements.statTotalClicks) elements.statTotalClicks.textContent = totalClicks.toLocaleString();
        if (elements.statActiveLinks) elements.statActiveLinks.textContent = activeLinks.toLocaleString();
        if (elements.statExpiredLinks) elements.statExpiredLinks.textContent = expiredLinks.toLocaleString();
    }

    /**
     * Render links into the table body based on search query.
     */
    function filterAndRenderLinks() {
        const query = (elements.searchInput ? elements.searchInput.value : '').trim().toLowerCase();

        const filtered = allLinks.filter(item => {
            if (!query) return true;
            const code = (item.short_code || '').toLowerCase();
            const orig = (item.original_url || '').toLowerCase();
            const shortUrl = (item.short_url || '').toLowerCase();
            return code.includes(query) || orig.includes(query) || shortUrl.includes(query);
        });

        // Toggle table states
        if (allLinks.length === 0) {
            if (elements.tableEmpty) elements.tableEmpty.classList.remove('hidden');
            if (elements.linksTableBody) elements.linksTableBody.innerHTML = '';
            return;
        }

        if (elements.tableEmpty) elements.tableEmpty.classList.add('hidden');

        if (filtered.length === 0) {
            if (elements.linksTableBody) {
                elements.linksTableBody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 36px 20px; color: var(--text-secondary);">
                            No shortened links match the search query <strong>"${escapeHtml(query)}"</strong>.
                        </td>
                    </tr>
                `;
            }
            return;
        }

        const rowsHtml = filtered.map(link => {
            const isExpired = Boolean(link.is_expired);
            const statusClass = isExpired ? 'expired' : 'active';
            const statusLabel = isExpired ? 'Expired' : 'Active';
            const shortUrl = link.short_url || `${window.location.origin}/${link.short_code}`;

            return `
                <tr data-short-code="${escapeHtml(link.short_code)}" data-short-url="${escapeHtml(shortUrl)}">
                    <td class="col-short-link">
                        <a href="${escapeHtml(shortUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.short_code)}</a>
                    </td>
                    <td class="col-orig-url" title="${escapeHtml(link.original_url)}">
                        ${escapeHtml(link.original_url)}
                    </td>
                    <td>${formatDate(link.created_at)}</td>
                    <td>${formatDate(link.expires_at)}</td>
                    <td class="col-clicks">${(Number(link.click_count) || 0).toLocaleString()}</td>
                    <td>
                        <span class="status-badge ${statusClass}">
                            <span style="font-size: 8px;">●</span> ${statusLabel}
                        </span>
                    </td>
                    <td class="text-right">
                        <div class="action-buttons">
                            <button type="button" class="btn-copy btn-action-copy" data-url="${escapeHtml(shortUrl)}" title="Copy short link" aria-label="Copy short link">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                <span>Copy</span>
                            </button>
                            <a href="${escapeHtml(shortUrl)}" target="_blank" rel="noopener noreferrer" class="btn-open" title="Open redirect" aria-label="Open redirect link">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                            </a>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        if (elements.linksTableBody) {
            elements.linksTableBody.innerHTML = rowsHtml;
        }
    }

    /**
     * Fetch all links from the API and refresh dashboard stats.
     */
    async function fetchLinks() {
        if (elements.tableLoading) elements.tableLoading.classList.remove('hidden');
        if (elements.tableError) elements.tableError.classList.add('hidden');
        if (elements.tableEmpty) elements.tableEmpty.classList.add('hidden');

        try {
            const response = await fetch('/api/urls');
            if (!response.ok) {
                throw new Error(`Server returned HTTP ${response.status}`);
            }

            const data = await response.json();
            allLinks = Array.isArray(data.urls) ? data.urls : [];

            updateStatistics(allLinks);
            filterAndRenderLinks();
        } catch (err) {
            console.error('Failed to load links:', err);
            if (elements.tableErrorMessage) {
                elements.tableErrorMessage.textContent = err.message || 'Could not connect to the LinkForge API.';
            }
            if (elements.tableError) elements.tableError.classList.remove('hidden');
        } finally {
            if (elements.tableLoading) elements.tableLoading.classList.add('hidden');
        }
    }

    /**
     * Handle shortening form submission.
     */
    async function handleFormSubmit(e) {
        e.preventDefault();
        clearFormErrors();

        const url = elements.urlInput ? elements.urlInput.value.trim() : '';
        const customAlias = elements.aliasInput ? elements.aliasInput.value.trim() : '';
        const expiresLocal = elements.expiresInput ? elements.expiresInput.value : '';

        // Client-side Validation
        let hasError = false;

        if (!url) {
            elements.urlInput.classList.add('is-invalid');
            if (elements.urlInputError) elements.urlInputError.textContent = 'Please enter a destination URL.';
            hasError = true;
        } else if (!/^https?:\/\//i.test(url)) {
            elements.urlInput.classList.add('is-invalid');
            if (elements.urlInputError) elements.urlInputError.textContent = 'URL must start with http:// or https://.';
            hasError = true;
        }

        if (customAlias && !/^[A-Za-z0-9_-]{3,30}$/.test(customAlias)) {
            elements.aliasInput.classList.add('is-invalid');
            if (elements.aliasInputError) elements.aliasInputError.textContent = 'Alias must be 3-30 letters, numbers, hyphens, or underscores.';
            hasError = true;
        }

        let isoExpiration = null;
        if (expiresLocal) {
            const expDate = new Date(expiresLocal);
            if (isNaN(expDate.getTime()) || expDate <= new Date()) {
                elements.expiresInput.classList.add('is-invalid');
                if (elements.expiresInputError) elements.expiresInputError.textContent = 'Expiration date must be in the future.';
                hasError = true;
            } else {
                isoExpiration = expDate.toISOString();
            }
        }

        if (hasError) return;

        // Set Loading state
        elements.submitBtn.classList.add('is-loading');
        elements.submitBtn.disabled = true;

        try {
            const payload = {
                url: url,
                custom_alias: customAlias || undefined,
                expires_at: isoExpiration || undefined
            };

            const response = await fetch('/api/urls', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                const errorMsg = result.error || 'Failed to shorten URL.';
                if (response.status === 409) {
                    elements.aliasInput.classList.add('is-invalid');
                    if (elements.aliasInputError) elements.aliasInputError.textContent = errorMsg;
                } else if (errorMsg.toLowerCase().includes('url')) {
                    elements.urlInput.classList.add('is-invalid');
                    if (elements.urlInputError) elements.urlInputError.textContent = errorMsg;
                } else {
                    showToast(errorMsg, 'error');
                }
                return;
            }

            // Success
            showToast('Short URL created successfully!', 'success');

            // Render result banner
            if (elements.resultShortUrl) elements.resultShortUrl.textContent = result.short_url;
            if (elements.resultOriginalUrl) elements.resultOriginalUrl.textContent = result.original_url;
            if (elements.resultShortCode) elements.resultShortCode.textContent = result.short_code;
            if (elements.openResultLink) elements.openResultLink.href = result.short_url;
            if (elements.resultBanner) elements.resultBanner.classList.remove('hidden');

            // Reset Form Inputs
            elements.shortenForm.reset();

            // Refresh table and stats
            await fetchLinks();

        } catch (err) {
            console.error('Submission error:', err);
            showToast('Network error: Unable to create short link.', 'error');
        } finally {
            elements.submitBtn.classList.remove('is-loading');
            elements.submitBtn.disabled = false;
        }
    }

    /**
     * Mobile Sidebar Drawer Controls
     */
    function toggleMobileSidebar(open) {
        if (!elements.sidebar || !elements.sidebarOverlay) return;
        const isOpen = typeof open === 'boolean' ? open : !elements.sidebar.classList.contains('mobile-open');
        if (isOpen) {
            elements.sidebar.classList.add('mobile-open');
            elements.sidebarOverlay.classList.add('active');
        } else {
            elements.sidebar.classList.remove('mobile-open');
            elements.sidebarOverlay.classList.remove('active');
        }
    }

    /**
     * Active Navigation Switching
     */
    function setActiveNav(activeId) {
        [elements.navDashboard, elements.navLinks, elements.navAnalytics].forEach(nav => {
            if (nav) nav.classList.remove('active');
        });
        const activeItem = document.getElementById(activeId);
        if (activeItem) activeItem.classList.add('active');
    }

    /**
     * Setup Event Listeners
     */
    function initEvents() {
        // Mobile menu toggle
        if (elements.mobileMenuBtn) {
            elements.mobileMenuBtn.addEventListener('click', () => toggleMobileSidebar());
        }
        if (elements.sidebarOverlay) {
            elements.sidebarOverlay.addEventListener('click', () => toggleMobileSidebar(false));
        }

        // Nav click handlers
        if (elements.navDashboard) {
            elements.navDashboard.addEventListener('click', () => {
                setActiveNav('navDashboard');
                toggleMobileSidebar(false);
            });
        }
        if (elements.navLinks) {
            elements.navLinks.addEventListener('click', () => {
                setActiveNav('navLinks');
                toggleMobileSidebar(false);
            });
        }
        if (elements.navAnalytics) {
            elements.navAnalytics.addEventListener('click', () => {
                setActiveNav('navAnalytics');
                toggleMobileSidebar(false);
            });
        }

        // Form submission
        if (elements.shortenForm) {
            elements.shortenForm.addEventListener('submit', handleFormSubmit);
        }

        // Refresh action
        if (elements.refreshBtn) {
            elements.refreshBtn.addEventListener('click', () => {
                fetchLinks();
                showToast('Dashboard data refreshed.', 'info');
            });
        }

        // Table retry
        if (elements.tableRetryBtn) {
            elements.tableRetryBtn.addEventListener('click', fetchLinks);
        }

        // Live search filter
        if (elements.searchInput) {
            elements.searchInput.addEventListener('input', filterAndRenderLinks);
        }

        // Paste helper
        if (elements.pasteBtn && elements.urlInput) {
            elements.pasteBtn.addEventListener('click', async () => {
                try {
                    const text = await navigator.clipboard.readText();
                    if (text) {
                        elements.urlInput.value = text.trim();
                        elements.urlInput.focus();
                    }
                } catch (e) {
                    showToast('Unable to read clipboard. Please paste manually.', 'info');
                }
            });
        }

        // Close result banner
        if (elements.closeResultBtn && elements.resultBanner) {
            elements.closeResultBtn.addEventListener('click', () => {
                elements.resultBanner.classList.add('hidden');
            });
        }

        // Result banner copy
        if (elements.copyResultBtn) {
            elements.copyResultBtn.addEventListener('click', async () => {
                const shortUrl = elements.resultShortUrl ? elements.resultShortUrl.textContent : '';
                const success = await copyToClipboard(shortUrl);
                if (success) {
                    showToast('Copied to clipboard!', 'success');
                } else {
                    showToast('Failed to copy. Please copy manually.', 'error');
                }
            });
        }

        // Delegated table actions (Copy & Open)
        if (elements.linksTableBody) {
            elements.linksTableBody.addEventListener('click', async (e) => {
                const copyBtn = e.target.closest('.btn-action-copy');
                if (copyBtn) {
                    const url = copyBtn.getAttribute('data-url');
                    const success = await copyToClipboard(url);
                    if (success) {
                        showToast(`Copied ${url}`, 'success');
                    } else {
                        showToast('Failed to copy link.', 'error');
                    }
                }
            });
        }
    }

    /**
     * Initialize dynamic base URL display
     */
    function initBaseUrlPrefix() {
        if (elements.baseUrlPrefix) {
            const host = window.location.host;
            elements.baseUrlPrefix.textContent = host ? `${host}/` : 'link.forge/';
        }
    }

    // Bootstrap
    document.addEventListener('DOMContentLoaded', () => {
        initBaseUrlPrefix();
        initEvents();
        fetchLinks();
    });

})();
