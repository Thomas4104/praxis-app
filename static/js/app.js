/**
 * OMNIA Praxissoftware - Globale JavaScript-Funktionen
 */

/**
 * Fetch-Wrapper der automatisch den CSRF-Token mitsendet.
 * Verwenden fuer alle POST/PUT/DELETE AJAX-Requests.
 */
// Standard-Error-Handler fuer fetch-Aufrufe
function handleFetchError(error) {
    console.error('Fehler:', error);
    if (typeof showToast === 'function') {
        showToast('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'error');
    }
}

function fetchWithCSRF(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    if (!(options.body instanceof FormData)) {
        options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';
    }
    var tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        options.headers['X-CSRFToken'] = tokenMeta.getAttribute('content');
    }
    options.credentials = options.credentials || 'same-origin';
    return fetch(url, options).catch(handleFetchError);
}

document.addEventListener('DOMContentLoaded', function () {

    // === Sidebar Toggle ===
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const body = document.body;

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function () {
            const isMobile = window.innerWidth <= 768;
            if (isMobile) {
                sidebar.classList.toggle('mobile-open');
                toggleOverlay(sidebar.classList.contains('mobile-open'));
            } else {
                sidebar.classList.toggle('collapsed');
                body.classList.toggle('sidebar-collapsed');
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            }
        });

        // Gespeicherten Zustand laden
        if (localStorage.getItem('sidebarCollapsed') === 'true' && window.innerWidth > 768) {
            sidebar.classList.add('collapsed');
            body.classList.add('sidebar-collapsed');
        }
    }

    // Overlay fuer Mobile-Sidebar
    function toggleOverlay(show) {
        let overlay = document.querySelector('.sidebar-overlay');
        if (show) {
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.className = 'sidebar-overlay active';
                overlay.addEventListener('click', function () {
                    sidebar.classList.remove('mobile-open');
                    toggleOverlay(false);
                });
                document.body.appendChild(overlay);
            } else {
                overlay.classList.add('active');
            }
        } else if (overlay) {
            overlay.classList.remove('active');
        }
    }

    // === Dropdown-Menues ===
    const userMenu = document.getElementById('userMenu');
    if (userMenu) {
        const btn = userMenu.querySelector('.user-menu-btn');
        const dropdown = userMenu.querySelector('.user-dropdown');

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            dropdown.classList.toggle('active');
        });

        document.addEventListener('click', function () {
            dropdown.classList.remove('active');
        });
    }

    // === Globale Suche ===
    const searchInput = document.getElementById('globalSearch');
    const searchResults = document.getElementById('searchResults');
    let searchTimeout = null;

    if (searchInput && searchResults) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            const query = this.value.trim();

            if (query.length < 2) {
                searchResults.classList.remove('active');
                return;
            }

            searchTimeout = setTimeout(function () {
                fetch('/api/search?q=' + encodeURIComponent(query))
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        searchResults.innerHTML = '';
                        if (data.results && data.results.length > 0) {
                            data.results.forEach(function (item) {
                                var div = document.createElement('div');
                                div.className = 'search-result-item';
                                div.innerHTML =
                                    '<div>' +
                                    '<div class="search-result-label">' + escapeHtml(item.label) + '</div>' +
                                    '<div class="search-result-sublabel">' + escapeHtml(item.sublabel) + '</div>' +
                                    '</div>';
                                div.addEventListener('click', function () {
                                    if (item.url && item.url !== '#') {
                                        window.location.href = item.url;
                                    }
                                    searchResults.classList.remove('active');
                                });
                                searchResults.appendChild(div);
                            });
                            searchResults.classList.add('active');
                        } else {
                            searchResults.classList.remove('active');
                        }
                    })
                    .catch(function () {
                        searchResults.classList.remove('active');
                    });
            }, 300);
        });

        searchInput.addEventListener('blur', function () {
            setTimeout(function () {
                searchResults.classList.remove('active');
            }, 200);
        });

        searchInput.addEventListener('focus', function () {
            if (searchResults.children.length > 0) {
                searchResults.classList.add('active');
            }
        });
    }

    // === Alert schliessen ===
    document.querySelectorAll('.alert-close').forEach(function (btn) {
        btn.addEventListener('click', function () {
            this.parentElement.style.display = 'none';
        });
    });

    // === Auto-Resize Textareas ===
    document.querySelectorAll('textarea.auto-resize').forEach(function (textarea) {
        textarea.addEventListener('input', autoResize);
        autoResize.call(textarea);
    });

    function autoResize() {
        this.style.height = 'auto';
        this.style.height = this.scrollHeight + 'px';
    }

    // === Standort wechseln ===
    const locationSelect = document.getElementById('locationSelect');
    if (locationSelect) {
        locationSelect.addEventListener('change', function () {
            var locationId = this.value;
            showToast('Standort gewechselt', 'info');
        });
    }
});

// === Toast-Benachrichtigungen ===
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(function () {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = '0.3s ease';
        setTimeout(function () {
            if (toast.parentElement) toast.remove();
        }, 300);
    }, 4000);
}

// === Modal-Management ===
function openModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        // Focus Trap aktivieren
        modal._trapHandler = trapFocus(modal);
        // Erstes fokussierbares Element fokussieren
        var firstFocusable = modal.querySelector('button, [href], input, select, textarea');
        if (firstFocusable) firstFocusable.focus();
        // Escape zum Schliessen
        modal._escHandler = function (e) {
            if (e.key === 'Escape') closeModal(modalId);
        };
        document.addEventListener('keydown', modal._escHandler);
    }
}

function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        if (modal._trapHandler) {
            modal.removeEventListener('keydown', modal._trapHandler);
            delete modal._trapHandler;
        }
        modal.classList.remove('active');
        document.body.style.overflow = '';
        if (modal._escHandler) {
            document.removeEventListener('keydown', modal._escHandler);
            delete modal._escHandler;
        }
    }
}

// === Hilfsfunktionen ===
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// === Confirmation Dialog (ersetzt Browser confirm()) ===
function showConfirmDialog(options) {
    return new Promise(function (resolve) {
        var title = options.title || 'Bestätigung';
        var message = options.message || 'Sind Sie sicher?';
        var confirmText = options.confirmText || 'Bestätigen';
        var cancelText = options.cancelText || 'Abbrechen';
        var type = options.type || 'warning'; // warning, danger, info
        var btnClass = type === 'danger' ? 'btn-danger' : 'btn-primary';

        var iconSvg = {
            warning: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
            danger: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            info: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
        };

        var overlay = document.createElement('div');
        overlay.className = 'modal-overlay active confirm-dialog';
        overlay.innerHTML =
            '<div class="modal modal-sm">' +
            '<div class="modal-body" style="padding: 2rem;">' +
            '<div class="confirm-dialog-icon icon-' + type + '">' + (iconSvg[type] || iconSvg.warning) + '</div>' +
            '<div class="confirm-dialog-text">' +
            '<h3>' + escapeHtml(title) + '</h3>' +
            '<p>' + escapeHtml(message) + '</p>' +
            '</div>' +
            '</div>' +
            '<div class="modal-footer">' +
            '<button class="btn btn-ghost" data-action="cancel">' + escapeHtml(cancelText) + '</button>' +
            '<button class="btn ' + btnClass + '" data-action="confirm">' + escapeHtml(confirmText) + '</button>' +
            '</div>' +
            '</div>';

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        // Focus Trap
        var confirmBtn = overlay.querySelector('[data-action="confirm"]');
        confirmBtn.focus();

        function cleanup(result) {
            overlay.remove();
            document.body.style.overflow = '';
            resolve(result);
        }

        overlay.querySelector('[data-action="cancel"]').addEventListener('click', function () { cleanup(false); });
        overlay.querySelector('[data-action="confirm"]').addEventListener('click', function () { cleanup(true); });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) cleanup(false);
        });
        overlay.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') cleanup(false);
        });
    });
}

// === Focus Trap fuer Modals ===
function trapFocus(modal) {
    var focusable = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return null;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];

    var handler = function (e) {
        if (e.key !== 'Tab') return;
        if (e.shiftKey) {
            if (document.activeElement === first) {
                e.preventDefault();
                last.focus();
            }
        } else {
            if (document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    };
    modal.addEventListener('keydown', handler);
    return handler;
}

// === Command Palette (Cmd+K / Ctrl+K) ===
document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        var searchInput = document.getElementById('globalSearch');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }
});
