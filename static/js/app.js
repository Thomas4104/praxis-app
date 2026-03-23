/**
 * OMNIA Praxissoftware - Globale JavaScript-Funktionen
 */

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
    }
}

function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// === Hilfsfunktionen ===
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
