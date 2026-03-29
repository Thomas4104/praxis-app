/**
 * Dashboard Widget-System — OMNIA Praxissoftware
 * Laedt Widgets per AJAX, zeichnet Canvas-Charts, verwaltet Konfiguration
 */
(function() {
    'use strict';

    // === Initialisierung ===
    var widgetConfig = window.DASHBOARD_WIDGET_CONFIG || [];
    var refreshInterval = null;

    // Datum anzeigen
    var dateEl = document.getElementById('dashboardDate');
    if (dateEl) {
        var now = new Date();
        var tage = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
        var monate = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                      'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
        dateEl.textContent = tage[now.getDay()] + ', ' + now.getDate() + '. ' + monate[now.getMonth()] + ' ' + now.getFullYear();
    }

    // === Widget-Loader ===
    function loadWidgets() {
        if (widgetConfig.indexOf('ki_tagesuebersicht') >= 0) loadKITagesuebersicht();
        if (widgetConfig.indexOf('heutige_termine') >= 0) loadHeutigeTermine();
        if (widgetConfig.indexOf('offene_aufgaben') >= 0) loadOffeneAufgaben();
        if (widgetConfig.indexOf('patientenverlauf') >= 0) loadPatientenverlauf();
        if (widgetConfig.indexOf('umsatzuebersicht') >= 0) loadUmsatzuebersicht();
        if (widgetConfig.indexOf('geburtstage') >= 0) loadGeburtstage();
        if (widgetConfig.indexOf('auslastung') >= 0) loadAuslastung();
        if (widgetConfig.indexOf('offene_rechnungen') >= 0) loadOffeneRechnungen();
        if (widgetConfig.indexOf('ungelesene_emails') >= 0) loadUngeleseneEmails();
        if (widgetConfig.indexOf('absenzen') >= 0) loadAbsenzen();
        if (widgetConfig.indexOf('notizen') >= 0) loadNotizen();
        if (widgetConfig.indexOf('behandlungshistorie') >= 0) loadBehandlungshistorie();
        if (widgetConfig.indexOf('arbeitszeiten') >= 0) loadArbeitszeiten();
    }

    function fetchJSON(url, callback) {
        fetch(url, { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(callback)
            .catch(function(err) { console.error('Dashboard fetch error:', url, err); });
    }

    // === KI-Tagesübersicht ===
    function loadKITagesuebersicht() {
        fetchJSON('/api/dashboard/ki-tagesuebersicht', function(data) {
            var el = document.getElementById('ki-tagesuebersicht-content');
            if (!el) return;
            var html = '<div class="ki-zusammenfassung">';
            html += '<p class="ki-text">' + escapeHtml(data.zusammenfassung) + '</p>';
            if (data.hinweise && data.hinweise.length > 0) {
                html += '<div class="ki-hinweise">';
                data.hinweise.forEach(function(h) {
                    html += '<div class="ki-hinweis"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> ' + escapeHtml(h) + '</div>';
                });
                html += '</div>';
            }
            html += '<button class="btn btn-sm btn-outline ki-detail-btn" onclick="document.getElementById(\'chatToggleBtn\').click();">Mehr Details im KI-Chat</button>';
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Heutige Termine ===
    function loadHeutigeTermine() {
        fetchJSON('/api/dashboard/termine-heute', function(data) {
            var el = document.getElementById('heutige-termine-content');
            if (!el) return;
            if (!data.termine || data.termine.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine Termine für heute.</p>';
                return;
            }
            var html = '<div class="termine-liste">';
            data.termine.forEach(function(t) {
                html += '<div class="termin-item">';
                html += '<div class="termin-zeit">' + t.start_time + '<span class="termin-ende"> – ' + t.end_time + '</span></div>';
                html += '<div class="termin-details">';
                html += '<span class="termin-patient">' + escapeHtml(t.patient_name) + '</span>';
                html += '<span class="termin-meta">' + escapeHtml(t.terminart);
                if (t.raum !== '-') html += ' · ' + escapeHtml(t.raum);
                html += '</span>';
                html += '</div>';
                html += '<div class="termin-therapeut" style="border-left: 3px solid ' + (t.therapeut_farbe || '#4a90d9') + '; padding-left: 6px;">';
                html += '<span class="termin-therapeut-name">' + escapeHtml(t.therapeut) + '</span>';
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Offene Aufgaben ===
    function loadOffeneAufgaben() {
        fetchJSON('/api/dashboard/aufgaben', function(data) {
            var el = document.getElementById('offene-aufgaben-content');
            var badge = document.getElementById('aufgaben-badge');
            if (!el) return;

            if (badge && data.gesamt > 0) {
                badge.textContent = data.gesamt;
                badge.style.display = 'inline-flex';
            }

            if (!data.aufgaben || data.aufgaben.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine offenen Aufgaben.</p>';
                return;
            }

            var html = '<div class="aufgaben-liste">';
            data.aufgaben.forEach(function(a) {
                var pClass = 'priority-' + a.priority;
                var ueberfaellig = a.ueberfaellig ? ' aufgabe-ueberfaellig' : '';
                html += '<a href="/tasks" class="aufgabe-item ' + pClass + ueberfaellig + '">';
                html += '<span class="aufgabe-priority-dot"></span>';
                html += '<div class="aufgabe-content">';
                html += '<span class="aufgabe-title">' + escapeHtml(a.title) + '</span>';
                if (a.due_date) {
                    html += '<span class="aufgabe-due">' + (a.ueberfaellig ? 'Überfällig: ' : 'Fällig: ') + a.due_date + '</span>';
                }
                html += '</div>';
                html += '</a>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Patientenverlauf ===
    function loadPatientenverlauf() {
        fetchJSON('/api/dashboard/patientenverlauf', function(data) {
            var el = document.getElementById('patientenverlauf-content');
            if (!el) return;
            if (!data.patienten || data.patienten.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine kürzlich bearbeiteten Patienten.</p>';
                return;
            }
            var html = '<div class="patienten-liste">';
            data.patienten.forEach(function(p) {
                html += '<a href="/patients" class="patient-item">';
                html += '<div class="patient-avatar">' + escapeHtml(p.name.charAt(0)) + '</div>';
                html += '<div class="patient-info">';
                html += '<span class="patient-name">' + escapeHtml(p.name) + '</span>';
                html += '<span class="patient-aktion">' + escapeHtml(p.letzte_aktion) + ' · ' + p.datum + '</span>';
                html += '</div>';
                html += '</a>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Umsatzübersicht ===
    function loadUmsatzuebersicht() {
        fetchJSON('/api/dashboard/umsatz', function(data) {
            var el = document.getElementById('umsatzuebersicht-content');
            if (!el) return;
            var pfeil = data.veraenderung >= 0 ? '↑' : '↓';
            var veraenderungClass = data.veraenderung >= 0 ? 'trend-positiv' : 'trend-negativ';

            var html = '<div class="umsatz-widget">';
            html += '<div class="umsatz-aktuell">';
            html += '<span class="umsatz-betrag">CHF ' + formatCHF(data.umsatz_aktuell) + '</span>';
            html += '<span class="umsatz-label">Aktueller Monat</span>';
            html += '</div>';
            html += '<div class="umsatz-trend ' + veraenderungClass + '">';
            html += '<span>' + pfeil + ' ' + Math.abs(data.veraenderung) + '% zum Vormonat</span>';
            html += '</div>';
            html += '<div class="umsatz-chart-container"><canvas id="umsatzChart" width="280" height="100"></canvas></div>';
            html += '<div class="umsatz-offene-posten">Offene Posten: <strong>CHF ' + formatCHF(data.offene_posten) + '</strong></div>';
            html += '</div>';
            el.innerHTML = html;

            // Chart zeichnen
            drawBarChart('umsatzChart', data.verlauf);
        });
    }

    // === Auslastung ===
    function loadAuslastung() {
        fetchJSON('/api/dashboard/auslastung', function(data) {
            var el = document.getElementById('auslastung-content');
            if (!el) return;
            if (!data.auslastung || data.auslastung.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine Auslastungsdaten verfügbar.</p>';
                return;
            }
            var html = '<div class="auslastung-liste">';
            data.auslastung.forEach(function(a) {
                var barColor = a.prozent < 70 ? '#27ae60' : (a.prozent < 90 ? '#f39c12' : '#e74c3c');
                html += '<div class="auslastung-item">';
                html += '<span class="auslastung-name">' + escapeHtml(a.name) + '</span>';
                html += '<div class="auslastung-bar-container">';
                html += '<div class="auslastung-bar" style="width:' + a.prozent + '%;background:' + barColor + '"></div>';
                html += '</div>';
                html += '<span class="auslastung-prozent">' + a.prozent + '%</span>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Geburtstage ===
    function loadGeburtstage() {
        fetchJSON('/api/dashboard/geburtstage', function(data) {
            var el = document.getElementById('geburtstage-content');
            if (!el) return;
            if (!data.geburtstage || data.geburtstage.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine Geburtstage in den nächsten 7 Tagen.</p>';
                return;
            }
            var html = '<div class="geburtstage-liste">';
            data.geburtstage.forEach(function(g) {
                var heuteClass = g.ist_heute ? ' geburtstag-heute' : '';
                html += '<div class="geburtstag-item' + heuteClass + '">';
                if (g.ist_heute) {
                    html += '<span class="geburtstag-icon">🎂</span>';
                }
                html += '<div class="geburtstag-info">';
                html += '<span class="geburtstag-name">' + escapeHtml(g.name) + '</span>';
                html += '<span class="geburtstag-detail">' + g.datum + ' · ' + g.alter + ' Jahre</span>';
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Offene Rechnungen ===
    function loadOffeneRechnungen() {
        fetchJSON('/api/dashboard/offene-rechnungen', function(data) {
            var el = document.getElementById('offene-rechnungen-content');
            if (!el) return;
            var html = '<div class="rechnungen-widget">';
            html += '<div class="rechnungen-row">';
            html += '<div class="rechnungen-stat">';
            html += '<span class="rechnungen-zahl">' + data.anzahl_offen + '</span>';
            html += '<span class="rechnungen-label">Rechnungen offen</span>';
            html += '<span class="rechnungen-betrag">CHF ' + formatCHF(data.betrag_offen) + '</span>';
            html += '</div>';
            html += '<div class="rechnungen-stat rechnungen-ueberfaellig">';
            html += '<span class="rechnungen-zahl">' + data.anzahl_ueberfaellig + '</span>';
            html += '<span class="rechnungen-label">Überfällig</span>';
            html += '<span class="rechnungen-betrag">CHF ' + formatCHF(data.betrag_ueberfaellig) + '</span>';
            html += '</div>';
            html += '</div>';
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Ungelesene E-Mails ===
    function loadUngeleseneEmails() {
        fetchJSON('/api/dashboard/ungelesene-emails', function(data) {
            var el = document.getElementById('ungelesene-emails-content');
            if (!el) return;
            var html = '<div class="emails-widget">';
            html += '<div class="emails-count">' + data.anzahl + ' ungelesene E-Mails</div>';
            if (data.emails && data.emails.length > 0) {
                html += '<div class="emails-liste">';
                data.emails.forEach(function(e) {
                    html += '<a href="/mailing" class="email-item">';
                    html += '<div class="email-header">';
                    html += '<span class="email-absender">' + escapeHtml(e.absender) + '</span>';
                    html += '<span class="email-datum">' + e.datum + '</span>';
                    html += '</div>';
                    html += '<span class="email-betreff">' + escapeHtml(e.betreff) + '</span>';
                    if (e.kurztext) {
                        html += '<span class="email-kurztext">' + escapeHtml(e.kurztext) + '</span>';
                    }
                    html += '</a>';
                });
                html += '</div>';
            }
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Absenzen ===
    function loadAbsenzen() {
        fetchJSON('/api/dashboard/absenzen', function(data) {
            var el = document.getElementById('absenzen-content');
            if (!el) return;
            var html = '<div class="absenzen-widget">';

            // Heute
            html += '<div class="absenzen-tag"><strong>Heute</strong></div>';
            if (data.heute && data.heute.length > 0) {
                data.heute.forEach(function(a) {
                    html += '<div class="absenz-item">';
                    html += '<span class="absenz-name">' + escapeHtml(a.name) + '</span>';
                    html += '<span class="absenz-grund">' + escapeHtml(a.grund) + (a.halbtags ? ' (halbtags)' : '') + '</span>';
                    html += '</div>';
                });
            } else {
                html += '<p class="widget-empty-sm">Niemand abwesend</p>';
            }

            // Morgen
            html += '<div class="absenzen-tag" style="margin-top:12px"><strong>Morgen</strong></div>';
            if (data.morgen && data.morgen.length > 0) {
                data.morgen.forEach(function(a) {
                    html += '<div class="absenz-item">';
                    html += '<span class="absenz-name">' + escapeHtml(a.name) + '</span>';
                    html += '<span class="absenz-grund">' + escapeHtml(a.grund) + (a.halbtags ? ' (halbtags)' : '') + '</span>';
                    html += '</div>';
                });
            } else {
                html += '<p class="widget-empty-sm">Niemand abwesend</p>';
            }

            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Notizen (Cenplex: NotesBox) ===
    window.loadNotizen = function() {
        fetchJSON('/api/dashboard/notizen', function(data) {
            var el = document.getElementById('notizen-content');
            if (!el) return;
            if (!data.notizen || data.notizen.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine Notizen vorhanden.</p><p class="widget-empty-sm" style="cursor:pointer" onclick="openNoteEditor()">+ Neue Notiz erstellen</p>';
                return;
            }
            var noteColors = ['#fff', '#fff3cd', '#d4edda', '#cce5ff', '#f8d7da', '#e2d5f1', '#fce4ec'];
            var html = '<div class="notizen-liste">';
            data.notizen.forEach(function(n) {
                var bg = noteColors[n.color] || '#fff';
                html += '<div class="notiz-item" style="background:' + bg + '; border-left:3px solid ' + (n.is_pinned ? '#f39c12' : '#ddd') + '; padding:0.5rem 0.75rem; margin-bottom:0.5rem; border-radius:4px; cursor:pointer;" onclick="openNoteEditor(' + n.id + ')">';
                if (n.title) html += '<div style="font-weight:500; font-size:0.85rem;">' + escapeHtml(n.title) + '</div>';
                html += '<div style="font-size:0.8rem; color:#666;">' + escapeHtml((n.content || '').substring(0, 80)) + (n.content && n.content.length > 80 ? '...' : '') + '</div>';
                html += '<div style="font-size:0.7rem; color:#aaa; margin-top:2px; display:flex; justify-content:space-between;">';
                html += '<span>' + n.updated_at + '</span>';
                html += '<button class="btn btn-ghost" style="padding:0; font-size:0.7rem; color:#e74c3c;" onclick="event.stopPropagation(); deleteNote(' + n.id + ')">Löschen</button>';
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // Notiz-Editor oeffnen (inline)
    window.openNoteEditor = function(noteId) {
        var el = document.getElementById('notizen-content');
        if (!el) return;

        if (noteId) {
            // Bestehende Notiz laden
            fetchJSON('/api/dashboard/notizen', function(data) {
                var note = (data.notizen || []).find(function(n) { return n.id === noteId; });
                renderNoteForm(el, note || {});
            });
        } else {
            renderNoteForm(el, {});
        }
    };

    function renderNoteForm(container, note) {
        var html = '<div class="notiz-editor" style="padding:0.5rem;">';
        html += '<input type="text" id="noteTitle" class="form-input" placeholder="Titel (optional)" value="' + escapeHtml(note.title || '') + '" style="margin-bottom:0.5rem; font-size:0.85rem;">';
        html += '<textarea id="noteContent" class="form-input" rows="3" placeholder="Notiz...">' + escapeHtml(note.content || '') + '</textarea>';
        html += '<div style="display:flex; gap:0.5rem; margin-top:0.5rem; align-items:center;">';
        html += '<select id="noteColor" class="form-input" style="width:auto; font-size:0.8rem;">';
        var colorNames = ['Standard', 'Gelb', 'Grün', 'Blau', 'Rot', 'Lila', 'Rosa'];
        for (var i = 0; i < colorNames.length; i++) {
            html += '<option value="' + i + '"' + (note.color === i ? ' selected' : '') + '>' + colorNames[i] + '</option>';
        }
        html += '</select>';
        html += '<label style="font-size:0.8rem;"><input type="checkbox" id="notePinned"' + (note.is_pinned ? ' checked' : '') + '> Anpinnen</label>';
        html += '<div style="flex:1"></div>';
        html += '<button class="btn btn-secondary btn-sm" onclick="loadNotizen()">Abbrechen</button>';
        html += '<button class="btn btn-primary btn-sm" onclick="saveNote(' + (note.id || 'null') + ')">Speichern</button>';
        html += '</div></div>';
        container.innerHTML = html;
    }

    window.saveNote = function(noteId) {
        var payload = {
            title: document.getElementById('noteTitle').value,
            content: document.getElementById('noteContent').value,
            color: parseInt(document.getElementById('noteColor').value) || 0,
            is_pinned: document.getElementById('notePinned').checked
        };
        if (noteId) payload.id = noteId;

        fetchWithCSRF('/api/dashboard/notizen', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        }).then(function(r) { return r.json(); })
          .then(function() { loadNotizen(); });
    };

    window.deleteNote = function(noteId) {
        if (!confirm('Notiz löschen?')) return;
        fetchWithCSRF('/api/dashboard/notizen/' + noteId, {
            method: 'DELETE'
        }).then(function(r) { return r.json(); })
          .then(function() { loadNotizen(); });
    };

    // Notiz-Button
    var addNoteBtn = document.getElementById('addNoteBtn');
    if (addNoteBtn) {
        addNoteBtn.addEventListener('click', function() { openNoteEditor(); });
    }

    // === Behandlungshistorie (Cenplex: TreatmentHistoryBox) ===
    function loadBehandlungshistorie() {
        fetchJSON('/api/dashboard/behandlungshistorie', function(data) {
            var el = document.getElementById('behandlungshistorie-content');
            if (!el) return;
            if (!data.behandlungen || data.behandlungen.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine offenen Behandlungen.</p>';
                return;
            }
            var html = '<div class="behandlungshistorie-liste">';
            data.behandlungen.forEach(function(b) {
                var statusIcon = b.status === 'in_progress' ? '<span style="color:#f39c12;" title="In Bearbeitung">●</span>' : '<span style="color:#e74c3c;" title="Ohne Dokumentation">○</span>';
                html += '<div class="behandlung-item" style="display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0; border-bottom:1px solid #f0f0f0;">';
                html += statusIcon;
                html += '<div style="flex:1; min-width:0;">';
                html += '<div style="font-size:0.85rem; font-weight:500;">' + escapeHtml(b.patient_name) + '</div>';
                html += '<div style="font-size:0.75rem; color:#888;">' + escapeHtml(b.behandlung) + ' · ' + b.datum + ' ' + b.zeit + '</div>';
                html += '</div>';
                html += '<span style="font-size:0.75rem; color:#888;">' + escapeHtml(b.therapeut) + '</span>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Arbeitszeiten (Cenplex: WorktimeBox) ===
    function loadArbeitszeiten() {
        fetchJSON('/api/dashboard/arbeitszeiten', function(data) {
            var el = document.getElementById('arbeitszeiten-content');
            if (!el) return;
            if (!data.arbeitszeiten || data.arbeitszeiten.length === 0) {
                el.innerHTML = '<p class="widget-empty">Keine Arbeitszeiten für heute.</p>';
                return;
            }
            var html = '<div class="arbeitszeiten-liste">';
            data.arbeitszeiten.forEach(function(a) {
                html += '<div class="arbeitszeit-item" style="display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0; border-bottom:1px solid #f0f0f0;">';
                html += '<div style="width:4px; height:24px; border-radius:2px; background:' + (a.farbe || '#4a90d9') + '"></div>';
                html += '<div style="flex:1;">';
                html += '<span style="font-size:0.85rem; font-weight:500;">' + escapeHtml(a.name) + '</span>';
                html += '</div>';
                html += '<div style="font-size:0.8rem; color:#666;">';
                a.zeiten.forEach(function(z, idx) {
                    if (idx > 0) html += ', ';
                    html += z.start + ' – ' + z.ende;
                });
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            el.innerHTML = html;
        });
    }

    // === Canvas Bar Chart (Umsatz) ===
    function drawBarChart(canvasId, verlauf) {
        var canvas = document.getElementById(canvasId);
        if (!canvas || !canvas.getContext) return;

        var ctx = canvas.getContext('2d');
        var dpr = window.devicePixelRatio || 1;
        var rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = 100 * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = '100px';
        ctx.scale(dpr, dpr);

        var w = rect.width;
        var h = 100;
        var padding = { top: 10, right: 10, bottom: 22, left: 10 };
        var chartW = w - padding.left - padding.right;
        var chartH = h - padding.top - padding.bottom;

        var maxVal = Math.max.apply(null, verlauf.map(function(v) { return v.betrag; })) || 1;
        var barWidth = (chartW / verlauf.length) * 0.6;
        var gap = (chartW / verlauf.length) * 0.4;

        ctx.clearRect(0, 0, w, h);

        verlauf.forEach(function(v, i) {
            var barH = (v.betrag / maxVal) * chartH;
            var x = padding.left + i * (barWidth + gap) + gap / 2;
            var y = padding.top + chartH - barH;

            // Balken
            ctx.fillStyle = i === verlauf.length - 1 ? '#4a90d9' : '#d4e4f7';
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barH, 3);
            ctx.fill();

            // Monatsname
            ctx.fillStyle = '#666';
            ctx.font = '11px system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(v.monat, x + barWidth / 2, h - 4);
        });
    }

    // === Hilfsfunktionen ===
    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatCHF(val) {
        return Number(val).toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // === Dashboard-Konfiguration ===
    var configBtn = document.getElementById('dashboardConfigBtn');
    var configModal = document.getElementById('dashboardConfigModal');
    var configClose = document.getElementById('dashboardConfigClose');
    var configCancel = document.getElementById('dashboardConfigCancel');
    var configSave = document.getElementById('dashboardConfigSave');

    if (configBtn) {
        configBtn.addEventListener('click', function() {
            openConfigModal();
        });
    }
    if (configClose) configClose.addEventListener('click', closeConfigModal);
    if (configCancel) configCancel.addEventListener('click', closeConfigModal);
    if (configModal) {
        configModal.addEventListener('click', function(e) {
            if (e.target === configModal) closeConfigModal();
        });
    }

    function openConfigModal() {
        fetchJSON('/api/dashboard/config', function(data) {
            var list = document.getElementById('widgetConfigList');
            if (!list) return;
            var html = '';
            data.available.forEach(function(w) {
                var checked = data.widgets.indexOf(w.id) >= 0 ? ' checked' : '';
                html += '<label class="widget-config-item">';
                html += '<input type="checkbox" value="' + w.id + '"' + checked + '>';
                html += '<span class="widget-config-name">' + escapeHtml(w.name) + '</span>';
                html += '</label>';
            });
            list.innerHTML = html;
            configModal.style.display = 'flex';
        });
    }

    function closeConfigModal() {
        if (configModal) configModal.style.display = 'none';
    }

    if (configSave) {
        configSave.addEventListener('click', function() {
            var checkboxes = document.querySelectorAll('#widgetConfigList input[type=checkbox]');
            var selected = [];
            checkboxes.forEach(function(cb) {
                if (cb.checked) selected.push(cb.value);
            });

            fetchWithCSRF('/api/dashboard/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ widgets: selected })
            })
            .then(function(r) { return r.json(); })
            .then(function() {
                // Widget-Sichtbarkeit aktualisieren
                widgetConfig = selected;
                window.DASHBOARD_WIDGET_CONFIG = selected;

                document.querySelectorAll('.widget-card').forEach(function(card) {
                    var wid = card.getAttribute('data-widget');
                    card.style.display = selected.indexOf(wid) >= 0 ? '' : 'none';
                });

                closeConfigModal();
                loadWidgets();
            });
        });
    }

    // === Auto-Refresh (alle 60 Sekunden) ===
    function startAutoRefresh() {
        refreshInterval = setInterval(function() {
            // Nur dynamische Widgets refreshen
            if (widgetConfig.indexOf('heutige_termine') >= 0) loadHeutigeTermine();
            if (widgetConfig.indexOf('offene_aufgaben') >= 0) loadOffeneAufgaben();
            if (widgetConfig.indexOf('ungelesene_emails') >= 0) loadUngeleseneEmails();
        }, 60000);
    }

    // === Start ===
    loadWidgets();
    startAutoRefresh();

    // Canvas-Polyfill fuer roundRect
    if (!CanvasRenderingContext2D.prototype.roundRect) {
        CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
            if (w < 2 * r) r = w / 2;
            if (h < 2 * r) r = h / 2;
            this.moveTo(x + r, y);
            this.arcTo(x + w, y, x + w, y + h, r);
            this.arcTo(x + w, y + h, x, y + h, r);
            this.arcTo(x, y + h, x, y, r);
            this.arcTo(x, y, x + w, y, r);
            this.closePath();
            return this;
        };
    }

})();
