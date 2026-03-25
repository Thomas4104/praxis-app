/**
 * OMNIA Praxissoftware — Kalender (Tages-, Wochen-, Monatsansicht)
 * Drag & Drop, Resize, Quick-Add, Detail-Modal
 */
(function() {
    'use strict';

    const CFG = window.CALENDAR_CONFIG || {};
    const START_HOUR = CFG.dayStart ? parseInt(CFG.dayStart.split(':')[0]) : 6;
    const END_HOUR = CFG.dayEnd ? parseInt(CFG.dayEnd.split(':')[0]) + 1 : 20;
    const GRID_INTERVAL = CFG.timeGrid || 15; // Minuten pro Slot (15-Min-Raster)
    const SLOT_HEIGHT_PX = 20; // px pro 15-Min-Slot
    const SLOT_HEIGHT = SLOT_HEIGHT_PX * (60 / GRID_INTERVAL); // px pro Stunde (kompatibel)
    const QUARTER_HEIGHT = SLOT_HEIGHT_PX; // px pro 15 Min
    const BASE_URL = '/calendar';

    // Globaler State
    let appointments = [];
    let workSchedules = {};
    let absences = [];
    let holidays = [];
    let currentDate = CFG.currentDate ? new Date(CFG.currentDate + 'T00:00:00') : new Date();
    let selectedAppointment = null;
    let dragState = null;
    let resizeState = null;
    let appointmentMap = {}; // id -> appointment object for event delegation

    // Kalender-State global bereitstellen (fuer moveAppointment)
    window._calendarState = { currentDate: CFG.currentDate || new Date().toISOString().split('T')[0] };

    // Terminkarten-Konfiguration (wird beim Laden abgerufen)
    window._appointmentConfig = null;

    // ==========================================================
    // Initialisierung
    // ==========================================================
    document.addEventListener('DOMContentLoaded', function() {
        // Terminkarten-Konfiguration laden (Farben, Domizil, Gruppen)
        loadAppointmentConfig();

        if (CFG.viewType === 'day') initDayView();
        else if (CFG.viewType === 'week') initWeekView();
        else if (CFG.viewType === 'month') initMonthView();
        else if (CFG.viewType === 'serie_planen') initSerieWizard();
    });

    // Terminkarten-Konfiguration vom Server laden
    function loadAppointmentConfig() {
        fetch(BASE_URL + '/api/appointment-config')
            .then(function(r) { return r.ok ? r.json() : {}; })
            .then(function(config) { window._appointmentConfig = config; })
            .catch(function() { window._appointmentConfig = {}; });
    }

    // Farbe bestimmen basierend auf Termintyp und Farbkategorie
    function getAppointmentColor(appt) {
        if (appt.is_domicile) return '#198754';   // Gruen fuer Domizil
        if (appt.is_group) return '#6f42c1';      // Lila fuer Gruppe
        if (appt.color_category) {
            var config = window._appointmentConfig;
            if (config && config.color_categories) {
                var cat = config.color_categories.find(function(c) {
                    return c.name === appt.color_category;
                });
                if (cat) return cat.color;
            }
        }
        return '';  // Standard-Farbe (Employee-Farbe)
    }

    // ==========================================================
    // TAGESANSICHT
    // ==========================================================
    function initDayView() {
        renderTimeColumn();
        renderTherapistColumns();
        loadDayData();
        setupDayNavigation();
        setupQuickAddModal();
        setupDetailModal();
        setupCancelModal();
        setupTherapistFilters();

        // Polling alle 30 Sekunden
        setInterval(function() { loadDayData(true); }, 30000);
    }

    function renderTimeColumn() {
        const col = document.getElementById('timeColumn');
        if (!col) return;
        col.innerHTML = '<div class="time-column-header-spacer"></div>'; // Header-Platzhalter
        for (let h = START_HOUR; h < END_HOUR; h++) {
            for (let m = 0; m < 60; m += GRID_INTERVAL) {
                const label = document.createElement('div');
                label.className = 'time-slot-label';
                if (m === 0) {
                    label.classList.add('full-hour');
                    label.textContent = String(h).padStart(2, '0') + ':00';
                } else {
                    label.textContent = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
                }
                label.style.height = SLOT_HEIGHT_PX + 'px';
                col.appendChild(label);
            }
        }
    }

    function renderTherapistColumns() {
        const container = document.getElementById('therapistColumns');
        if (!container) return;
        container.innerHTML = '';

        const visibleEmployees = getVisibleEmployees();
        var columns = [];

        // Therapeuten-Spalten
        visibleEmployees.forEach(function(emp) {
            columns.push({
                type: 'employee',
                id: emp.id,
                name: emp.name,
                color: emp.color,
                employeeId: emp.id,
                resourceId: null
            });
        });

        // Ressourcen-Spalten (Raeume) wenn Toggle aktiv
        var showResources = document.getElementById('showResourceColumns');
        if ((!showResources || showResources.checked) && CFG.resources && CFG.resources.length > 0) {
            CFG.resources.forEach(function(res) {
                columns.push({
                    type: 'resource',
                    id: 'res-' + res.id,
                    name: res.name,
                    color: '#6c757d',
                    employeeId: null,
                    resourceId: res.id
                });
            });
        }

        columns.forEach(function(colDef) {
            const col = document.createElement('div');
            col.className = 'therapist-column';
            if (colDef.type === 'employee') {
                col.dataset.employeeId = colDef.employeeId;
            } else {
                col.dataset.resourceId = colDef.resourceId;
                col.classList.add('resource-column');
            }

            // Header
            const header = document.createElement('div');
            header.className = 'therapist-column-header';
            header.style.background = colDef.color;
            header.textContent = colDef.name;
            if (colDef.type === 'resource') {
                header.classList.add('resource-header');
            }
            col.appendChild(header);

            // Body mit 15-Min-Zeitslots
            const body = document.createElement('div');
            body.className = 'therapist-column-body';
            if (colDef.type === 'employee') {
                body.dataset.employeeId = colDef.employeeId;
            } else {
                body.dataset.resourceId = colDef.resourceId;
            }

            for (let h = START_HOUR; h < END_HOUR; h++) {
                for (let m = 0; m < 60; m += GRID_INTERVAL) {
                    const slot = document.createElement('div');
                    slot.className = 'time-slot';
                    slot.dataset.time = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
                    slot.dataset.hour = h;
                    slot.dataset.minutes = m;
                    slot.style.height = SLOT_HEIGHT_PX + 'px';

                    if (colDef.type === 'employee') {
                        slot.dataset.employeeId = colDef.employeeId;
                    } else {
                        slot.dataset.resourceId = colDef.resourceId;
                    }

                    // Volle-Stunde und Halbe-Stunde Linien
                    if (m === 0) {
                        slot.classList.add('full-hour-slot');
                    } else if (m === 30) {
                        slot.classList.add('half-hour-slot');
                    }

                    // Klick auf leeren Slot
                    (function(empId, hr, min) {
                        slot.addEventListener('click', function(e) {
                            if (e.target.closest('.appointment-block')) return;
                            openQuickAdd(empId || (visibleEmployees[0] ? visibleEmployees[0].id : null), hr, min);
                        });
                    })(colDef.employeeId, h, m);

                    // Drop-Zone fuer Drag & Drop
                    slot.addEventListener('dragover', handleDragOver);
                    slot.addEventListener('drop', handleDrop);
                    slot.addEventListener('dragleave', handleDragLeave);

                    body.appendChild(slot);
                }
            }

            // Event Delegation fuer Appointment-Blocks
            setupAppointmentDelegation(body);

            col.appendChild(body);
            container.appendChild(col);
        });

        // Ressourcen-Toggle Event
        if (showResources && !showResources._listenerAdded) {
            showResources.addEventListener('change', function() {
                renderTherapistColumns();
                loadDayData(true);
            });
            showResources._listenerAdded = true;
        }
    }

    // Zentrale Event-Delegation fuer Appointment-Blocks auf einem Container
    function setupAppointmentDelegation(container) {
        container.addEventListener('click', function(e) {
            var block = e.target.closest('.appointment-block');
            if (!block) return;
            if (e.target.classList.contains('resize-handle')) return;
            var appt = appointmentMap[block.dataset.appointmentId];
            if (appt) openDetailModal(appt);
        });

        container.addEventListener('dragstart', function(e) {
            var block = e.target.closest('.appointment-block');
            if (!block) return;
            var appt = appointmentMap[block.dataset.appointmentId];
            if (!appt) return;
            dragState = {
                appointmentId: appt.id,
                employeeId: appt.employee_id,
                offsetMinutes: 0
            };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', appt.id);
            setTimeout(function() { block.classList.add('dragging'); }, 0);
        });

        container.addEventListener('dragend', function(e) {
            var block = e.target.closest('.appointment-block');
            if (block) block.classList.remove('dragging');
            document.querySelectorAll('.drop-indicator').forEach(function(el) { el.remove(); });
            dragState = null;
        });
    }

    function getVisibleEmployees() {
        // Nur Therapeuten-Checkboxen (nicht den Ressourcen-Toggle)
        const checkboxes = document.querySelectorAll('#therapistFilters input[type="checkbox"]:not(#showResourceColumns)');
        if (checkboxes.length === 0) return CFG.employees || [];
        const visibleIds = new Set();
        checkboxes.forEach(function(cb) {
            if (cb.checked) visibleIds.add(parseInt(cb.value));
        });
        return (CFG.employees || []).filter(function(e) { return visibleIds.has(e.id); });
    }

    function loadDayData(silent) {
        const dateStr = formatDate(currentDate);
        const empIds = getVisibleEmployees().map(function(e) { return e.id; }).join(',');

        Promise.all([
            fetchJSON(BASE_URL + '/api/appointments?date=' + dateStr + '&location_id=' + (CFG.locationId || '') + '&employee_ids=' + empIds),
            fetchJSON(BASE_URL + '/api/work-schedules?date=' + dateStr + '&employee_ids=' + empIds),
            fetchJSON(BASE_URL + '/api/absences?date=' + dateStr),
            fetchJSON(BASE_URL + '/api/holidays?date=' + dateStr)
        ]).then(function(results) {
            appointments = results[0];
            workSchedules = results[1];
            absences = results[2];
            holidays = results[3];

            renderDayAppointments();
            renderWorkingHours();
            renderAbsences();
            renderHolidayBanner();
            renderCurrentTimeLine();
        });
    }

    function renderDayAppointments() {
        // Bestehende Bloecke entfernen
        document.querySelectorAll('.appointment-block').forEach(function(el) { el.remove(); });
        appointmentMap = {};

        appointments.forEach(function(appt) {
            appointmentMap[appt.id] = appt;

            // Termin in Therapeuten-Spalte platzieren
            var empBody = document.querySelector('.therapist-column-body[data-employee-id="' + appt.employee_id + '"]');

            // Termin auch in Ressourcen-Spalte platzieren (falls Raum zugewiesen)
            var resBody = null;
            if (appt.resource_id) {
                resBody = document.querySelector('.therapist-column-body[data-resource-id="' + appt.resource_id + '"]');
            }

            var targets = [];
            if (empBody) targets.push(empBody);
            if (resBody) targets.push(resBody);
            if (targets.length === 0) return;

            var startDt = new Date(appt.start_time);
            var endDt = new Date(appt.end_time);
            var startMinutes = startDt.getHours() * 60 + startDt.getMinutes();
            var endMinutes = endDt.getHours() * 60 + endDt.getMinutes();
            var topPx = (startMinutes - START_HOUR * 60) * (SLOT_HEIGHT / 60);
            var heightPx = (endMinutes - startMinutes) * (SLOT_HEIGHT / 60);

            if (heightPx < QUARTER_HEIGHT) heightPx = QUARTER_HEIGHT;

            targets.forEach(function(body) {
                var block = document.createElement('div');
                block.className = 'appointment-block status-' + appt.status;
                block.dataset.appointmentId = appt.id;
                block.style.top = topPx + 'px';
                block.style.height = heightPx + 'px';

                // Cenplex-Farblogik: Versicherungstyp als CSS-Klasse
                if (appt.is_domicile) block.classList.add('domicile');
                if (appt.is_group) block.classList.add('group');
                if (appt.color_category) {
                    var catClass = appt.color_category.toLowerCase().replace(/[^a-z]/g, '');
                    if (catClass) block.classList.add(catClass);
                }

                // Farbe: Kategorie ueberschreibt Employee-Farbe
                var categoryColor = getAppointmentColor(appt);
                var displayColor = categoryColor || appt.employee_color;
                block.style.background = hexToRgba(displayColor, 0.15);
                block.style.borderLeftColor = displayColor;
                block.style.color = darkenColor(displayColor, 0.6);
                block.draggable = true;

                // Status-Icons (SVG statt Emoji)
                var statusIcons = '';
                if (appt.is_documented) {
                    statusIcons += '<svg class="icon-sm icon-documented" viewBox="0 0 16 16" fill="currentColor" title="Dokumentiert"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
                }
                if (appt.is_billed) {
                    statusIcons += '<svg class="icon-sm icon-billed" viewBox="0 0 16 16" fill="currentColor" title="Abgerechnet"><path d="M4 10.781c.148 1.667 1.513 2.85 3.591 3.003V15h1.043v-1.216c2.27-.179 3.678-1.438 3.678-3.3 0-1.59-.947-2.51-2.956-3.028l-.722-.187V3.467c1.122.11 1.879.714 2.07 1.616h1.47c-.166-1.6-1.54-2.748-3.54-2.875V1H7.591v1.233c-1.939.23-3.27 1.472-3.27 3.156 0 1.454.966 2.483 2.661 2.917l.61.162v4.031c-1.149-.17-1.94-.8-2.131-1.718H4zm3.391-3.836c-1.043-.263-1.6-.825-1.6-1.616 0-.944.704-1.641 1.8-1.828v3.495l-.2-.05zm1.591 1.872c1.287.323 1.852.859 1.852 1.769 0 1.097-.826 1.828-2.2 1.939V8.73l.348.086z"/></svg>';
                }
                if (appt.is_domicile) {
                    statusIcons += '<svg class="icon-sm icon-domicile" viewBox="0 0 16 16" fill="currentColor" title="Domizil"><path d="M8.354 1.146a.5.5 0 0 0-.708 0l-6 6A.5.5 0 0 0 1.5 7.5v7a.5.5 0 0 0 .5.5h4.5a.5.5 0 0 0 .5-.5v-4h2v4a.5.5 0 0 0 .5.5H14a.5.5 0 0 0 .5-.5v-7a.5.5 0 0 0-.146-.354L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.354 1.146z"/></svg>';
                }
                if (appt.is_group) {
                    statusIcons += '<svg class="icon-sm icon-group" viewBox="0 0 16 16" fill="currentColor" title="Gruppe"><path d="M7 14s-1 0-1-1 1-4 5-4 5 3 5 4-1 1-1 1H7zm4-6a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path fill-rule="evenodd" d="M5.216 14A2.238 2.238 0 0 1 5 13c0-1.355.68-2.75 1.936-3.72A6.325 6.325 0 0 0 5 9c-4 0-5 3-5 4s1 1 1 1h4.216z"/><path d="M4.5 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z"/></svg>';
                }
                if (appt.appointment_type === 'initial') {
                    statusIcons += '<svg class="icon-sm icon-initial" viewBox="0 0 16 16" fill="currentColor" title="Ersttermin"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/></svg>';
                }

                // Termin-Inhalt (Cenplex-Stil)
                var timeStr = formatTime(startDt) + ' - ' + formatTime(endDt);
                var seriesStr = appt.series_counter ? '<span class="appt-series" title="Serie">' + escapeHtml(appt.series_counter) + '</span>' : '';

                block.innerHTML =
                    '<div class="appt-time">' + timeStr + '</div>' +
                    '<div class="appt-patient"><strong>' + escapeHtml(appt.patient_name) + '</strong></div>' +
                    '<div class="appt-meta">' +
                        seriesStr +
                        (statusIcons ? '<span class="appt-icons">' + statusIcons + '</span>' : '') +
                    '</div>' +
                    '<div class="resize-handle"></div>';

                // Resize (bleibt per-element wegen spezifischem State)
                var resizeHandle = block.querySelector('.resize-handle');
                resizeHandle.addEventListener('mousedown', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    resizeState = {
                        appointmentId: appt.id,
                        startY: e.clientY,
                        originalHeight: heightPx,
                        block: block,
                        minHeight: QUARTER_HEIGHT
                    };
                    document.addEventListener('mousemove', handleResize);
                    document.addEventListener('mouseup', handleResizeEnd);
                });

                body.appendChild(block);
            });
        });
    }

    function renderWorkingHours() {
        document.querySelectorAll('.time-slot').forEach(function(slot) {
            slot.classList.remove('non-working');
        });

        var visibleEmployees = getVisibleEmployees();
        visibleEmployees.forEach(function(emp) {
            var schedules = workSchedules[String(emp.id)] || [];
            var workingMinutes = new Set();

            schedules.forEach(function(ws) {
                var parts = ws.start_time.split(':');
                var start = parseInt(parts[0]) * 60 + parseInt(parts[1]);
                var eParts = ws.end_time.split(':');
                var end = parseInt(eParts[0]) * 60 + parseInt(eParts[1]);
                for (var m = start; m < end; m++) {
                    workingMinutes.add(m);
                }
            });

            if (workingMinutes.size === 0) return; // Keine Arbeitszeiten definiert -> alles offen

            var slots = document.querySelectorAll('.time-slot[data-employee-id="' + emp.id + '"]');
            slots.forEach(function(slot) {
                var hour = parseInt(slot.dataset.hour);
                var minutes = parseInt(slot.dataset.minutes || 0);
                var slotStart = hour * 60 + minutes;
                var isWorking = false;
                for (var m = slotStart; m < slotStart + GRID_INTERVAL; m++) {
                    if (workingMinutes.has(m)) { isWorking = true; break; }
                }
                if (!isWorking) {
                    slot.classList.add('non-working');
                }
            });
        });
    }

    function renderAbsences() {
        document.querySelectorAll('.absence-overlay').forEach(function(el) { el.remove(); });

        var dateStr = formatDate(currentDate);
        absences.forEach(function(absence) {
            if (dateStr < absence.start_date || dateStr > absence.end_date) return;

            var body = document.querySelector('.therapist-column-body[data-employee-id="' + absence.employee_id + '"]');
            if (!body) return;

            var overlay = document.createElement('div');
            overlay.className = 'absence-overlay';
            overlay.style.top = '0';
            overlay.style.height = '100%';

            var text = document.createElement('span');
            text.className = 'absence-overlay-text';
            var absenceTypes = {
                'vacation': 'Ferien', 'sick': 'Krank', 'accident': 'Unfall',
                'training': 'Weiterbildung', 'military': 'Militär',
                'maternity': 'Mutterschaft', 'paternity': 'Vaterschaft',
                'unpaid': 'Unbezahlt', 'other': 'Abwesend'
            };
            text.textContent = absenceTypes[absence.absence_type] || absence.absence_type;
            if (absence.notes) text.textContent += ' (' + absence.notes + ')';

            overlay.appendChild(text);
            body.appendChild(overlay);
        });
    }

    function renderHolidayBanner() {
        var banner = document.getElementById('holidayBanner');
        if (!banner) return;

        var dateStr = formatDate(currentDate);
        var todayHoliday = holidays.find(function(h) { return h.date === dateStr; });

        if (todayHoliday) {
            banner.textContent = 'Feiertag: ' + todayHoliday.name;
            banner.style.display = 'flex';
        } else {
            banner.style.display = 'none';
        }
    }

    function renderCurrentTimeLine() {
        document.querySelectorAll('.current-time-line').forEach(function(el) { el.remove(); });

        var now = new Date();
        var todayStr = formatDate(now);
        var currentStr = formatDate(currentDate);
        if (todayStr !== currentStr) return;

        var minutes = now.getHours() * 60 + now.getMinutes();
        var topPx = (minutes - START_HOUR * 60) * (SLOT_HEIGHT / 60);
        if (topPx < 0 || topPx > (END_HOUR - START_HOUR) * SLOT_HEIGHT) return;

        document.querySelectorAll('.therapist-column-body').forEach(function(body) {
            var line = document.createElement('div');
            line.className = 'current-time-line';
            line.style.top = topPx + 'px';
            body.appendChild(line);
        });

        // Zur aktuellen Zeit scrollen (nur beim ersten Laden)
        if (!window._scrolledToNow) {
            var grid = document.getElementById('calendarDayGrid');
            if (grid) {
                grid.scrollTop = Math.max(0, topPx - 200);
                window._scrolledToNow = true;
            }
        }
    }

    function setupTherapistFilters() {
        var filters = document.querySelectorAll('#therapistFilters input[type="checkbox"]');
        filters.forEach(function(cb) {
            cb.addEventListener('change', function() {
                renderTherapistColumns();
                loadDayData();
            });
        });
    }

    function setupDayNavigation() {
        var prevBtn = document.getElementById('prevDay') || document.getElementById('prevWeek');
        var nextBtn = document.getElementById('nextDay') || document.getElementById('nextWeek');
        var todayBtn = document.getElementById('todayBtn');
        var datePicker = document.getElementById('datePicker');
        var locationFilter = document.getElementById('locationFilter');

        if (prevBtn) {
            prevBtn.addEventListener('click', function() {
                var delta = CFG.viewType === 'week' ? 7 : 1;
                currentDate.setDate(currentDate.getDate() - delta);
                navigateToDate(currentDate);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function() {
                var delta = CFG.viewType === 'week' ? 7 : 1;
                currentDate.setDate(currentDate.getDate() + delta);
                navigateToDate(currentDate);
            });
        }
        if (todayBtn) {
            todayBtn.addEventListener('click', function() {
                navigateToDate(new Date());
            });
        }
        if (datePicker) {
            datePicker.addEventListener('change', function() {
                navigateToDate(new Date(this.value + 'T00:00:00'));
            });
        }
        if (locationFilter) {
            locationFilter.addEventListener('change', function() {
                var url = new URL(window.location);
                url.searchParams.set('location_id', this.value);
                url.searchParams.set('date', formatDate(currentDate));
                window.location.href = url.toString();
            });
        }
    }

    function navigateToDate(d) {
        var base = CFG.viewType === 'week' ? '/calendar/week' : (CFG.viewType === 'month' ? '/calendar/month' : '/calendar/');
        var params = '?date=' + formatDate(d);
        if (CFG.locationId) params += '&location_id=' + CFG.locationId;
        if (CFG.viewType === 'week' && CFG.employeeId) params += '&employee_id=' + CFG.employeeId;
        window.location.href = base + params;
    }

    // ==========================================================
    // DRAG & DROP (Cenplex-Stil mit 15-Min-Raster)
    // ==========================================================
    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        // Drop-Highlight auf aktuellem Slot
        var slot = e.target.closest('.time-slot');
        // Fallback fuer Wochenansicht (noch alte Struktur)
        if (!slot) slot = e.target.closest('.time-slot-row');
        if (!slot) return;

        document.querySelectorAll('.drop-highlight').forEach(function(el) { el.classList.remove('drop-highlight'); });
        slot.classList.add('drop-highlight');
    }

    function handleDragLeave(e) {
        var slot = e.target.closest('.time-slot');
        if (slot) slot.classList.remove('drop-highlight');
    }

    function handleDrop(e) {
        e.preventDefault();
        document.querySelectorAll('.drop-highlight').forEach(function(el) { el.classList.remove('drop-highlight'); });
        document.querySelectorAll('.drop-indicator').forEach(function(el) { el.remove(); });

        if (!dragState) return;

        // Neues Slot-basiertes System (Tagesansicht)
        var slot = e.target.closest('.time-slot');
        if (slot) {
            var newTime = slot.dataset.time; // z.B. "08:30"
            var newEmployeeId = slot.dataset.employeeId ? parseInt(slot.dataset.employeeId) : null;
            var newResourceId = slot.dataset.resourceId ? parseInt(slot.dataset.resourceId) : null;

            var currentDateStr = formatDate(currentDate);
            var newStartTime = currentDateStr + 'T' + newTime + ':00';

            var moveData = { new_start_time: newStartTime };
            if (newEmployeeId) moveData.new_employee_id = newEmployeeId;
            if (newResourceId) moveData.new_resource_id = newResourceId;

            fetchJSON(BASE_URL + '/api/appointments/' + dragState.appointmentId + '/move', {
                method: 'PUT',
                body: JSON.stringify(moveData)
            }).then(function(result) {
                if (result.success) {
                    showToast('Termin verschoben', 'success');
                    loadDayData(true);
                } else {
                    showToast(result.error || 'Fehler beim Verschieben', 'error');
                }
            });
            return;
        }

        // Fallback: Wochenansicht (alte time-slot-row Struktur)
        var row = e.target.closest('.time-slot-row');
        if (!row) return;

        var rect = row.getBoundingClientRect();
        var relY = e.clientY - rect.top;
        var quarterIndex = Math.floor(relY / (SLOT_HEIGHT / 4));
        var minutes = quarterIndex * GRID_INTERVAL;

        var hour = parseInt(row.dataset.hour);
        var employeeId = parseInt(row.dataset.employeeId);

        var newDate = new Date(currentDate);
        var dayCol = row.closest('.week-day-column');
        if (dayCol && dayCol.dataset.date) {
            newDate = new Date(dayCol.dataset.date + 'T00:00:00');
        }
        newDate.setHours(hour, minutes, 0, 0);

        var newStartTimeStr = newDate.toISOString().slice(0, 19);

        fetchJSON(BASE_URL + '/api/appointments/' + dragState.appointmentId + '/move', {
            method: 'PUT',
            body: JSON.stringify({
                new_start_time: newStartTimeStr,
                new_employee_id: employeeId
            })
        }).then(function(result) {
            if (result.success) {
                showToast('Termin verschoben', 'success');
                if (CFG.viewType === 'day') loadDayData(true);
                else if (CFG.viewType === 'week') loadWeekData(true);
            } else {
                showToast(result.error || 'Fehler beim Verschieben', 'error');
            }
        });
    }

    // ==========================================================
    // RESIZE
    // ==========================================================
    function handleResize(e) {
        if (!resizeState) return;
        var diff = e.clientY - resizeState.startY;
        var newHeight = Math.max(resizeState.minHeight, resizeState.originalHeight + diff);
        // Auf 15-Min-Raster einrasten
        newHeight = Math.round(newHeight / QUARTER_HEIGHT) * QUARTER_HEIGHT;
        resizeState.block.style.height = newHeight + 'px';
        resizeState.newHeight = newHeight;
    }

    function handleResizeEnd() {
        document.removeEventListener('mousemove', handleResize);
        document.removeEventListener('mouseup', handleResizeEnd);

        if (!resizeState || !resizeState.newHeight) { resizeState = null; return; }

        var newDuration = Math.round(resizeState.newHeight / SLOT_HEIGHT * 60);
        if (newDuration < 5) newDuration = 5;

        var appt = appointments.find(function(a) { return a.id === resizeState.appointmentId; });
        if (!appt) { resizeState = null; return; }

        fetchJSON(BASE_URL + '/api/appointments/' + resizeState.appointmentId, {
            method: 'PUT',
            body: JSON.stringify({
                start_time: appt.start_time,
                duration_minutes: newDuration
            })
        }).then(function(result) {
            if (result.success) {
                showToast('Termindauer geändert', 'success');
                if (CFG.viewType === 'day') loadDayData(true);
                else if (CFG.viewType === 'week') loadWeekData(true);
            } else {
                showToast(result.error || 'Fehler', 'error');
            }
        });

        resizeState = null;
    }

    // ==========================================================
    // QUICK-ADD MODAL
    // ==========================================================
    function setupQuickAddModal() {
        var modal = document.getElementById('quickAddModal');
        if (!modal) return;

        document.getElementById('quickAddClose').addEventListener('click', function() { modal.style.display = 'none'; });
        document.getElementById('quickAddCancel').addEventListener('click', function() { modal.style.display = 'none'; });
        modal.addEventListener('click', function(e) { if (e.target === modal) modal.style.display = 'none'; });

        document.getElementById('quickAddSave').addEventListener('click', saveQuickAdd);

        // Patient-Suche
        setupPatientSearch('qaPatientSearch', 'qaPatientResults', 'qaPatientId', 'qaPatientDisplay', 'qaSeries');
    }

    function openQuickAdd(employeeId, hour, minutes) {
        var modal = document.getElementById('quickAddModal');
        modal.style.display = 'flex';

        // Felder vorfuellen
        document.getElementById('qaEmployeeId').value = employeeId;
        var dt = new Date(currentDate);
        // Wochenansicht: ggf. anderes Datum
        dt.setHours(hour, minutes || 0, 0, 0);
        var localIso = dt.getFullYear() + '-' +
            String(dt.getMonth() + 1).padStart(2, '0') + '-' +
            String(dt.getDate()).padStart(2, '0') + 'T' +
            String(dt.getHours()).padStart(2, '0') + ':' +
            String(dt.getMinutes()).padStart(2, '0');
        document.getElementById('qaStartTime').value = localIso;

        // Reset
        document.getElementById('qaPatientSearch').value = '';
        document.getElementById('qaPatientId').value = '';
        document.getElementById('qaPatientDisplay').style.display = 'none';
        document.getElementById('qaNotes').value = '';
        document.getElementById('qaSeries').innerHTML = '<option value="">— Keine Serie —</option>';

        document.getElementById('qaPatientSearch').focus();
    }

    function saveQuickAdd() {
        var patientId = document.getElementById('qaPatientId').value;
        var employeeId = document.getElementById('qaEmployeeId').value;
        var startTime = document.getElementById('qaStartTime').value;
        var duration = document.getElementById('qaDuration').value;
        var type = document.getElementById('qaType').value;
        var seriesId = document.getElementById('qaSeries').value;
        var roomId = document.getElementById('qaRoom').value;
        var notes = document.getElementById('qaNotes').value;

        if (!patientId) { showToast('Bitte Patient auswählen', 'error'); return; }
        if (!startTime) { showToast('Bitte Datum/Uhrzeit angeben', 'error'); return; }

        fetchJSON(BASE_URL + '/api/appointments', {
            method: 'POST',
            body: JSON.stringify({
                patient_id: parseInt(patientId),
                employee_id: parseInt(employeeId),
                start_time: startTime + ':00',
                duration_minutes: parseInt(duration),
                appointment_type: type,
                series_id: seriesId ? parseInt(seriesId) : null,
                resource_id: roomId ? parseInt(roomId) : null,
                location_id: CFG.locationId,
                notes: notes,
                title: getTypeLabel(type)
            })
        }).then(function(result) {
            if (result.success) {
                showToast('Termin erstellt', 'success');
                document.getElementById('quickAddModal').style.display = 'none';
                if (CFG.viewType === 'day') loadDayData(true);
                else if (CFG.viewType === 'week') loadWeekData(true);
            } else {
                showToast(result.error || 'Fehler beim Erstellen', 'error');
            }
        });
    }

    // ==========================================================
    // TERMIN-DETAIL MODAL
    // ==========================================================
    function setupDetailModal() {
        var modal = document.getElementById('appointmentDetailModal');
        if (!modal) return;

        document.getElementById('detailClose').addEventListener('click', function() { modal.style.display = 'none'; });
        document.getElementById('detailCloseBtn').addEventListener('click', function() { modal.style.display = 'none'; });
        modal.addEventListener('click', function(e) { if (e.target === modal) modal.style.display = 'none'; });

        document.getElementById('detailSaveBtn').addEventListener('click', saveDetail);
        document.getElementById('detailStatusBtn').addEventListener('click', changeStatus);
        document.getElementById('detailCancelBtn').addEventListener('click', function() {
            document.getElementById('cancelModal').style.display = 'flex';
        });
    }

    function openDetailModal(appt) {
        selectedAppointment = appt;
        var modal = document.getElementById('appointmentDetailModal');
        modal.style.display = 'flex';

        var startDt = new Date(appt.start_time);
        var endDt = new Date(appt.end_time);
        var statusLabels = {
            'scheduled': 'Geplant', 'confirmed': 'Bestätigt', 'appeared': 'Erschienen',
            'cancelled': 'Abgesagt', 'no_show': 'Nicht erschienen'
        };
        var typeLabels = {
            'treatment': 'Behandlung', 'initial': 'Ersttermin', 'group': 'Gruppentherapie',
            'admin': 'Admin/Blocker', 'domicile': 'Domizil'
        };

        document.getElementById('detailPatient').innerHTML =
            '<a href="/patients/' + appt.patient_id + '">' + escapeHtml(appt.patient_name) + '</a>';
        document.getElementById('detailDateTime').textContent =
            formatDateGerman(startDt) + ', ' + formatTime(startDt) + ' – ' + formatTime(endDt) +
            ' (' + appt.duration_minutes + ' Min.)';
        document.getElementById('detailEmployee').textContent = appt.employee_name;
        document.getElementById('detailType').textContent = typeLabels[appt.appointment_type] || appt.appointment_type;
        document.getElementById('detailStatus').innerHTML =
            '<span class="status-badge ' + appt.status + '">' + (statusLabels[appt.status] || appt.status) + '</span>';
        document.getElementById('detailNotes').value = appt.notes || '';
        document.getElementById('detailSoapS').value = appt.soap_subjective || '';
        document.getElementById('detailSoapO').value = appt.soap_objective || '';
        document.getElementById('detailSoapA').value = appt.soap_assessment || '';
        document.getElementById('detailSoapP').value = appt.soap_plan || '';
        document.getElementById('detailStatusSelect').value = appt.status;

        var seriesRow = document.getElementById('detailSeriesRow');
        if (appt.series_id) {
            seriesRow.style.display = 'flex';
            var seriesText = 'Serie #' + appt.series_id;
            if (appt.series_counter) seriesText += ' (Termin ' + appt.series_counter + ')';
            document.getElementById('detailSeries').textContent = seriesText;
        } else {
            seriesRow.style.display = 'none';
        }

        // E-Mail-Button fuer Terminbestaetigung
        var emailBtn = document.getElementById('detailEmailBtn');
        if (emailBtn && appt.patient_id) {
            emailBtn.href = '/mailing/compose?patient_id=' + appt.patient_id + '&template=confirmation&subject=' + encodeURIComponent('Terminbestätigung');
            emailBtn.style.display = 'inline-flex';
        } else if (emailBtn) {
            emailBtn.style.display = 'none';
        }
    }

    function saveDetail() {
        if (!selectedAppointment) return;

        fetchJSON(BASE_URL + '/api/appointments/' + selectedAppointment.id, {
            method: 'PUT',
            body: JSON.stringify({
                notes: document.getElementById('detailNotes').value,
                soap_subjective: document.getElementById('detailSoapS').value,
                soap_objective: document.getElementById('detailSoapO').value,
                soap_assessment: document.getElementById('detailSoapA').value,
                soap_plan: document.getElementById('detailSoapP').value
            })
        }).then(function(result) {
            if (result.success) {
                showToast('Termin gespeichert', 'success');
                document.getElementById('appointmentDetailModal').style.display = 'none';
                if (CFG.viewType === 'day') loadDayData(true);
                else if (CFG.viewType === 'week') loadWeekData(true);
            }
        });
    }

    function changeStatus() {
        if (!selectedAppointment) return;
        var newStatus = document.getElementById('detailStatusSelect').value;

        fetchJSON(BASE_URL + '/api/appointments/' + selectedAppointment.id + '/status', {
            method: 'PUT',
            body: JSON.stringify({ status: newStatus })
        }).then(function(result) {
            if (result.success) {
                showToast('Status geändert', 'success');
                document.getElementById('appointmentDetailModal').style.display = 'none';
                if (CFG.viewType === 'day') loadDayData(true);
                else if (CFG.viewType === 'week') loadWeekData(true);
            }
        });
    }

    // ==========================================================
    // ABSAGE-MODAL
    // ==========================================================
    function setupCancelModal() {
        var modal = document.getElementById('cancelModal');
        if (!modal) return;

        document.getElementById('cancelClose').addEventListener('click', function() { modal.style.display = 'none'; });
        document.getElementById('cancelAbort').addEventListener('click', function() { modal.style.display = 'none'; });

        document.getElementById('cancelChargeFee').addEventListener('change', function() {
            document.getElementById('cancelFeeGroup').style.display = this.checked ? 'block' : 'none';
        });

        document.getElementById('cancelConfirm').addEventListener('click', function() {
            if (!selectedAppointment) return;

            var chargeFee = document.getElementById('cancelChargeFee').checked;
            fetchJSON(BASE_URL + '/api/appointments/' + selectedAppointment.id + '/cancel', {
                method: 'POST',
                body: JSON.stringify({
                    reason: document.getElementById('cancelReason').value,
                    charge_fee: chargeFee,
                    fee_amount: chargeFee ? parseFloat(document.getElementById('cancelFeeAmount').value) : 0
                })
            }).then(function(result) {
                if (result.success) {
                    showToast('Termin abgesagt', 'success');
                    document.getElementById('cancelModal').style.display = 'none';
                    document.getElementById('appointmentDetailModal').style.display = 'none';
                    if (CFG.viewType === 'day') loadDayData(true);
                    else if (CFG.viewType === 'week') loadWeekData(true);
                }
            });
        });
    }

    // ==========================================================
    // WOCHENANSICHT
    // ==========================================================
    // Gefilterte Therapeuten-IDs fuer Wochenansicht
    function getWeekVisibleEmployeeIds() {
        var checkboxes = document.querySelectorAll('#weekTherapistFilters input[type="checkbox"]');
        if (checkboxes.length === 0) return (CFG.employees || []).map(function(e) { return e.id; });
        var ids = [];
        checkboxes.forEach(function(cb) {
            if (cb.checked) ids.push(parseInt(cb.value));
        });
        return ids;
    }

    function initWeekView() {
        loadWeekData();
        setupDayNavigation();
        setupQuickAddModal();
        setupDetailModal();
        setupCancelModal();

        // Multi-Therapeut Filter: Checkboxen
        var filters = document.querySelectorAll('#weekTherapistFilters input[type="checkbox"]');
        filters.forEach(function(cb) {
            cb.addEventListener('change', function() {
                loadWeekData();
            });
        });

        setInterval(function() { loadWeekData(true); }, 30000);
    }

    function loadWeekData(silent) {
        var monday = new Date(CFG.monday + 'T00:00:00');
        var sunday = new Date(monday);
        sunday.setDate(sunday.getDate() + 6);

        var startStr = formatDate(monday);
        var endStr = formatDate(sunday);
        var empIds = getWeekVisibleEmployeeIds().join(',');

        Promise.all([
            fetchJSON(BASE_URL + '/api/appointments?start=' + startStr + '&end=' + endStr + '&employee_ids=' + empIds),
            fetchJSON(BASE_URL + '/api/absences?start=' + startStr + '&end=' + endStr),
            fetchJSON(BASE_URL + '/api/holidays?start=' + startStr + '&end=' + endStr)
        ]).then(function(results) {
            appointments = results[0];
            absences = results[1];
            holidays = results[2];
            renderWeekAppointments();
        });
    }

    function renderWeekAppointments() {
        var container = document.getElementById('weekGrid');
        if (!container) return;
        container.innerHTML = '';
        appointmentMap = {};

        var monday = new Date(CFG.monday + 'T00:00:00');
        var dayNames = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
        var todayStr = formatDate(new Date());

        // Termine nach Tag gruppieren
        var dayGroups = {};
        for (var i = 0; i < 7; i++) {
            var dd = new Date(monday);
            dd.setDate(dd.getDate() + i);
            dayGroups[formatDate(dd)] = [];
        }

        appointments.forEach(function(a) {
            appointmentMap[a.id] = a;
            var day = a.start_time ? a.start_time.split('T')[0] : null;
            if (day && dayGroups[day]) {
                dayGroups[day].push(a);
            }
        });

        var dayIndex = 0;
        Object.keys(dayGroups).sort().forEach(function(dateStr) {
            var dayAppts = dayGroups[dateStr];
            var dayCol = document.createElement('div');
            dayCol.className = 'week-day-column';

            // Header
            var header = document.createElement('div');
            header.className = 'week-day-header';
            if (dateStr === todayStr) header.className += ' today';
            if (dayIndex >= 5) header.className += ' weekend';
            var d = new Date(dateStr + 'T00:00:00');
            header.innerHTML = '<span class="day-name">' + dayNames[dayIndex] + '</span>' +
                '<span class="day-number">' + d.getDate() + '</span>';
            header.style.cursor = 'pointer';
            header.addEventListener('click', (function(ds) {
                return function() {
                    window.location.href = '/calendar/?date=' + ds +
                        (CFG.locationId ? '&location_id=' + CFG.locationId : '');
                };
            })(dateStr));
            dayCol.appendChild(header);

            // Feiertag-Badge
            var dayHoliday = holidays.find(function(h) { return h.date === dateStr; });
            if (dayHoliday) {
                var badge = document.createElement('span');
                badge.className = 'week-holiday';
                badge.style.cssText = 'display:block;font-size:10px;color:#856404;background:#fff3cd;padding:1px 4px;border-radius:3px;margin:2px 4px;text-align:center;';
                badge.textContent = dayHoliday.name;
                dayCol.appendChild(badge);
            }

            // Termine-Container
            var apptContainer = document.createElement('div');
            apptContainer.className = 'week-appt-container';

            // Sortiert nach Zeit
            dayAppts.sort(function(a, b) { return (a.start_time || '').localeCompare(b.start_time || ''); });

            dayAppts.forEach(function(appt) {
                var card = document.createElement('div');
                card.className = 'week-appt-card';
                if (appt.status === 'cancelled') card.className += ' cancelled';
                card.dataset.appointmentId = appt.id;

                // Farblogik
                var categoryColor = getAppointmentColor(appt);
                var displayColor = categoryColor || appt.employee_color || '#4a90d9';
                card.style.borderLeftColor = displayColor;
                card.style.background = hexToRgba(displayColor, 0.1);

                var startTime = appt.start_time ? appt.start_time.split('T')[1] : '';
                if (startTime) startTime = startTime.substring(0, 5);
                var endTime = appt.end_time ? appt.end_time.split('T')[1] : '';
                if (endTime) endTime = endTime.substring(0, 5);

                // Serien-Zaehler (z.B. "3/9") - kommt fertig formatiert von API
                var seriesInfo = appt.series_counter || '';

                // Therapeut-Initialen
                var empInitials = '';
                if (appt.employee_name) {
                    var parts = appt.employee_name.split(' ');
                    empInitials = parts.map(function(p) { return p.charAt(0); }).join('');
                }

                card.innerHTML =
                    '<span class="week-appt-time">' + startTime + '</span>' +
                    '<span class="week-appt-patient">' + escapeHtml(appt.patient_name || '') + '</span>' +
                    (empInitials ? '<span class="week-appt-emp" title="' + escapeHtml(appt.employee_name) + '" style="background:' + displayColor + ';">' + empInitials + '</span>' : '') +
                    (seriesInfo ? '<span class="week-appt-series">' + seriesInfo + '</span>' : '');

                card.addEventListener('click', function() {
                    openDetailModal(appt);
                });

                apptContainer.appendChild(card);
            });

            if (dayAppts.length === 0) {
                var empty = document.createElement('div');
                empty.className = 'week-day-empty';
                empty.textContent = 'Keine Termine';
                apptContainer.appendChild(empty);
            }

            dayCol.appendChild(apptContainer);
            container.appendChild(dayCol);
            dayIndex++;
        });
    }

    // ==========================================================
    // MONATSANSICHT
    // ==========================================================
    function initMonthView() {
        renderMonth();
        setupMonthNavigation();
    }

    function renderMonth() {
        var year = currentDate.getFullYear();
        var month = currentDate.getMonth();
        var firstDay = new Date(year, month, 1);
        var startDow = (firstDay.getDay() + 6) % 7; // Mo=0
        var daysInMonth = new Date(year, month + 1, 0).getDate();

        var monthNames = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
            'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
        var label = document.getElementById('monthLabel');
        if (label) label.textContent = monthNames[month] + ' ' + year;

        // Monatsdaten via API laden
        fetchJSON(BASE_URL + '/api/month-data?year=' + year + '&month=' + (month + 1) +
            '&location_id=' + (CFG.locationId || '')).then(function(data) {
            var body = document.getElementById('monthBody');
            if (!body) return;
            body.innerHTML = '';

            var todayStr = formatDate(new Date());

            // Vormonat-Tage
            var prevMonthDays = new Date(year, month, 0).getDate();
            for (var p = startDow - 1; p >= 0; p--) {
                var cell = createMonthCell(prevMonthDays - p, true);
                body.appendChild(cell);
            }

            // Aktuelle Monatstage
            for (var d = 1; d <= daysInMonth; d++) {
                var dateStr = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
                var dow = new Date(year, month, d).getDay();
                var isWeekend = (dow === 0 || dow === 6);
                var isToday = (dateStr === todayStr);
                var holiday = data.holidays[dateStr];
                var dayData = data.days[dateStr];

                var cell = document.createElement('div');
                cell.className = 'month-day-cell';
                if (isWeekend) cell.className += ' weekend';
                if (isToday) cell.className += ' today';
                if (holiday) cell.className += ' holiday';

                var numEl = document.createElement('div');
                numEl.className = 'month-day-number';
                numEl.textContent = d;
                cell.appendChild(numEl);

                if (holiday) {
                    var hName = document.createElement('span');
                    hName.className = 'month-holiday-name';
                    hName.textContent = holiday;
                    cell.appendChild(hName);
                }

                if (dayData) {
                    // Termine als kompakte Eintraege anzeigen (max 3, dann "+X weitere")
                    var maxShow = 3;
                    var appts = dayData.appointments || [];
                    appts.slice(0, maxShow).forEach(function(appt) {
                        var item = document.createElement('div');
                        item.className = 'month-appt-item';
                        if (appt.status === 'cancelled') item.className += ' cancelled';
                        var apptTime = appt.start_time ? appt.start_time.split('T')[1] : '';
                        if (apptTime) apptTime = apptTime.substring(0, 5);
                        var empColor = appt.employee_color || '#4a90d9';
                        item.style.borderLeftColor = empColor;
                        item.style.background = hexToRgba(empColor, 0.08);
                        item.innerHTML = '<small>' + apptTime + ' ' + escapeHtml(appt.patient_name || '') + '</small>';
                        item.addEventListener('click', function(e) {
                            e.stopPropagation();
                            // Zur Tagesansicht mit diesem Termin navigieren
                            window.location.href = '/calendar/?date=' + dateStr +
                                (CFG.locationId ? '&location_id=' + CFG.locationId : '');
                        });
                        cell.appendChild(item);
                    });

                    if (appts.length > maxShow) {
                        var more = document.createElement('div');
                        more.className = 'month-appt-more';
                        more.textContent = '+' + (appts.length - maxShow) + ' weitere';
                        cell.appendChild(more);
                    }
                }

                // Klick -> Tagesansicht
                (function(ds) {
                    cell.addEventListener('click', function() {
                        window.location.href = '/calendar/?date=' + ds +
                            (CFG.locationId ? '&location_id=' + CFG.locationId : '');
                    });
                })(dateStr);

                body.appendChild(cell);
            }

            // Naechster Monat auffuellen
            var totalCells = startDow + daysInMonth;
            var remaining = (7 - (totalCells % 7)) % 7;
            for (var n = 1; n <= remaining; n++) {
                body.appendChild(createMonthCell(n, true));
            }
        });
    }

    function createMonthCell(dayNum, isOtherMonth) {
        var cell = document.createElement('div');
        cell.className = 'month-day-cell' + (isOtherMonth ? ' other-month' : '');
        var numEl = document.createElement('div');
        numEl.className = 'month-day-number';
        numEl.textContent = dayNum;
        cell.appendChild(numEl);
        return cell;
    }

    function setupMonthNavigation() {
        var prevBtn = document.getElementById('prevMonth');
        var nextBtn = document.getElementById('nextMonth');
        var todayBtn = document.getElementById('todayBtn');
        var locationFilter = document.getElementById('locationFilter');

        if (prevBtn) {
            prevBtn.addEventListener('click', function() {
                currentDate.setMonth(currentDate.getMonth() - 1);
                renderMonth();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function() {
                currentDate.setMonth(currentDate.getMonth() + 1);
                renderMonth();
            });
        }
        if (todayBtn) {
            todayBtn.addEventListener('click', function() {
                currentDate = new Date();
                renderMonth();
            });
        }
        if (locationFilter) {
            locationFilter.addEventListener('change', function() {
                CFG.locationId = parseInt(this.value);
                renderMonth();
            });
        }
    }

    // ==========================================================
    // SERIEN-WIZARD
    // ==========================================================
    function initSerieWizard() {
        var currentStep = 1;
        var wizData = {};

        setupPatientSearch('wizPatientSearch', 'wizPatientResults', 'wizPatientId', 'wizPatientDisplay');

        // Template-Karten
        document.querySelectorAll('.template-card').forEach(function(card) {
            card.addEventListener('click', function() {
                document.querySelectorAll('.template-card').forEach(function(c) { c.classList.remove('selected'); });
                card.classList.add('selected');
                document.getElementById('wizTemplateId').value = card.dataset.templateId;
            });
        });

        // Employee-Karten
        document.querySelectorAll('.employee-card').forEach(function(card) {
            card.addEventListener('click', function() {
                document.querySelectorAll('.employee-card').forEach(function(c) { c.classList.remove('selected'); });
                card.classList.add('selected');
                document.getElementById('wizEmployeeId').value = card.dataset.employeeId;
            });
        });

        // Auto-Plan Button
        document.getElementById('wizAutoBtn').addEventListener('click', function() {
            var slotsContainer = document.getElementById('wizSlotsContainer');
            var loading = document.getElementById('wizSlotsLoading');
            var list = document.getElementById('wizSlotsList');

            slotsContainer.style.display = 'block';
            loading.style.display = 'block';
            list.innerHTML = '';

            var templateId = document.getElementById('wizTemplateId').value;
            var tpl = (CFG.templates || []).find(function(t) { return t.id === parseInt(templateId); });
            if (!tpl) { showToast('Vorlage nicht gefunden', 'error'); return; }

            var empId = document.getElementById('wizEmployeeId').value;
            var emp = (CFG.employees || []).find(function(e) { return e.id === parseInt(empId); });

            fetchJSON(BASE_URL + '/api/available-slots?employee_id=' + empId +
                '&duration=' + tpl.durationMinutes +
                '&num_slots=' + tpl.numAppointments +
                '&location_id=' + (emp ? emp.locationId : '')
            ).then(function(slots) {
                loading.style.display = 'none';
                wizData.slots = slots;

                if (!slots || slots.length === 0) {
                    list.innerHTML = '<p style="padding:16px;color:var(--gray-500);">Keine verfügbaren Slots gefunden.</p>';
                    return;
                }

                slots.forEach(function(slot, idx) {
                    var item = document.createElement('div');
                    item.className = 'slot-item';
                    item.innerHTML =
                        '<div class="slot-datetime">' +
                        '<strong>Termin ' + (idx + 1) + ':</strong> ' +
                        formatDateGerman(new Date(slot.datum + 'T' + slot.start_zeit)) +
                        ', ' + slot.start_zeit + ' – ' + slot.end_zeit +
                        '</div>' +
                        '<div class="slot-score">Bewertung: ' + (slot.score || '-') + '</div>' +
                        '<button class="btn btn-sm btn-primary slot-accept" data-idx="' + idx + '">Übernehmen</button>';
                    list.appendChild(item);
                });

                list.querySelectorAll('.slot-accept').forEach(function(btn) {
                    btn.addEventListener('click', function() {
                        btn.closest('.slot-item').classList.toggle('accepted');
                    });
                });
            });
        });

        // Navigation
        document.getElementById('wizNext').addEventListener('click', function() {
            if (currentStep === 1 && !document.getElementById('wizPatientId').value) {
                showToast('Bitte Patient auswählen', 'error'); return;
            }
            if (currentStep === 2 && !document.getElementById('wizTemplateId').value) {
                showToast('Bitte Vorlage auswählen', 'error'); return;
            }
            if (currentStep === 3 && !document.getElementById('wizEmployeeId').value) {
                showToast('Bitte Therapeut auswählen', 'error'); return;
            }

            if (currentStep < 7) {
                currentStep++;
                showWizardStep(currentStep);
                if (currentStep === 7) buildSummary(wizData);
            }
        });

        document.getElementById('wizPrev').addEventListener('click', function() {
            if (currentStep > 1) {
                currentStep--;
                showWizardStep(currentStep);
            }
        });

        document.getElementById('wizConfirm').addEventListener('click', function() {
            showToast('Serie wird erstellt...', 'info');
            // Akzeptierte Slots sammeln und Termine erstellen
            var accepted = document.querySelectorAll('.slot-item.accepted');
            if (accepted.length === 0 && wizData.slots && wizData.slots.length > 0) {
                // Wenn keine explizit akzeptiert, alle nehmen
                accepted = document.querySelectorAll('.slot-item');
            }

            var promises = [];
            var empId = document.getElementById('wizEmployeeId').value;
            var patId = document.getElementById('wizPatientId').value;

            accepted.forEach(function(item) {
                var idx = parseInt(item.querySelector('.slot-accept').dataset.idx);
                var slot = wizData.slots[idx];
                if (!slot) return;

                promises.push(fetchJSON(BASE_URL + '/api/appointments', {
                    method: 'POST',
                    body: JSON.stringify({
                        patient_id: parseInt(patId),
                        employee_id: parseInt(empId),
                        start_time: slot.datum + 'T' + slot.start_zeit + ':00',
                        duration_minutes: slot.dauer_minuten || 30,
                        appointment_type: 'treatment',
                        location_id: CFG.locationId || null,
                        title: 'Behandlung'
                    })
                }));
            });

            Promise.all(promises).then(function(results) {
                var created = results.filter(function(r) { return r.success; }).length;
                showToast(created + ' Termine erstellt', 'success');
                setTimeout(function() { window.location.href = '/calendar/'; }, 1000);
            });
        });

        function showWizardStep(step) {
            for (var i = 1; i <= 7; i++) {
                var panel = document.getElementById('step' + i);
                if (panel) panel.style.display = (i === step) ? 'block' : 'none';

                var stepEl = document.querySelector('.wizard-step[data-step="' + i + '"]');
                if (stepEl) {
                    stepEl.classList.remove('active', 'completed');
                    if (i === step) stepEl.classList.add('active');
                    else if (i < step) stepEl.classList.add('completed');
                }
            }

            document.getElementById('wizPrev').style.display = step > 1 ? 'inline-flex' : 'none';
            document.getElementById('wizNext').style.display = step < 7 ? 'inline-flex' : 'none';
            document.getElementById('wizConfirm').style.display = step === 7 ? 'inline-flex' : 'none';
        }

        function buildSummary(data) {
            var summary = document.getElementById('wizSummary');
            var patientName = document.querySelector('#wizPatientDisplay')?.textContent || '';
            var templateCard = document.querySelector('.template-card.selected h4');
            var employeeCard = document.querySelector('.employee-card.selected .employee-name');
            var accepted = document.querySelectorAll('.slot-item.accepted');
            var total = accepted.length || (data.slots ? data.slots.length : 0);

            summary.innerHTML =
                '<div class="summary-row"><span class="summary-label">Patient:</span><span class="summary-value">' + escapeHtml(patientName) + '</span></div>' +
                '<div class="summary-row"><span class="summary-label">Vorlage:</span><span class="summary-value">' + (templateCard ? escapeHtml(templateCard.textContent) : '-') + '</span></div>' +
                '<div class="summary-row"><span class="summary-label">Therapeut:</span><span class="summary-value">' + (employeeCard ? escapeHtml(employeeCard.textContent) : '-') + '</span></div>' +
                '<div class="summary-row"><span class="summary-label">Anzahl Termine:</span><span class="summary-value">' + total + '</span></div>' +
                '<div class="summary-row"><span class="summary-label">Versicherung:</span><span class="summary-value">' + (document.getElementById('wizInsuranceType')?.value || 'KVG') + '</span></div>';
        }
    }

    // ==========================================================
    // PATIENT-SUCHE (Autocomplete)
    // ==========================================================
    function setupPatientSearch(inputId, resultsId, hiddenId, displayId, seriesSelectId) {
        var input = document.getElementById(inputId);
        var results = document.getElementById(resultsId);
        var hidden = document.getElementById(hiddenId);
        var display = document.getElementById(displayId);
        if (!input || !results) return;

        var debounceTimer;
        input.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            var q = input.value.trim();
            if (q.length < 2) { results.classList.remove('active'); return; }

            debounceTimer = setTimeout(function() {
                fetchJSON(BASE_URL + '/api/patients/search?q=' + encodeURIComponent(q)).then(function(patients) {
                    results.innerHTML = '';
                    if (patients.length === 0) {
                        results.innerHTML = '<div class="patient-result-item"><span class="patient-info">Keine Patienten gefunden</span></div>';
                    } else {
                        patients.forEach(function(p) {
                            var item = document.createElement('div');
                            item.className = 'patient-result-item';
                            item.innerHTML = '<span class="patient-name">' + escapeHtml(p.name) + '</span>' +
                                '<span class="patient-info">' + escapeHtml(p.patient_number) +
                                (p.date_of_birth ? ' · ' + escapeHtml(p.date_of_birth) : '') + '</span>';
                            item.addEventListener('click', function() {
                                hidden.value = p.id;
                                if (display) {
                                    display.style.display = 'flex';
                                    display.innerHTML = '<span>' + escapeHtml(p.name) + ' (' + escapeHtml(p.patient_number) + ')</span>' +
                                        '<span class="remove-patient">&times;</span>';
                                    display.querySelector('.remove-patient').addEventListener('click', function() {
                                        hidden.value = '';
                                        display.style.display = 'none';
                                        input.value = '';
                                        input.style.display = 'block';
                                    });
                                }
                                input.value = p.name;
                                input.style.display = 'none';
                                results.classList.remove('active');

                                // Serien des Patienten laden
                                if (seriesSelectId) {
                                    fetchJSON(BASE_URL + '/api/patient-series/' + p.id).then(function(series) {
                                        var sel = document.getElementById(seriesSelectId);
                                        if (!sel) return;
                                        sel.innerHTML = '<option value="">— Keine Serie —</option>';
                                        series.forEach(function(s) {
                                            sel.innerHTML += '<option value="' + s.id + '">' + escapeHtml(s.name) +
                                                (s.diagnosis ? ' – ' + escapeHtml(s.diagnosis) : '') + '</option>';
                                        });
                                    });
                                }
                            });
                            results.appendChild(item);
                        });
                    }
                    results.classList.add('active');
                });
            }, 250);
        });

        // Schliessen bei Klick ausserhalb
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.patient-search-wrapper')) {
                results.classList.remove('active');
            }
        });
    }

    // ==========================================================
    // HILFSFUNKTIONEN
    // ==========================================================
    function fetchJSON(url, options) {
        var opts = options || {};
        opts.headers = opts.headers || {};
        opts.headers['Content-Type'] = 'application/json';
        opts.headers['Accept'] = 'application/json';
        var tokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (tokenMeta) {
            opts.headers['X-CSRFToken'] = tokenMeta.getAttribute('content');
        }
        opts.credentials = opts.credentials || 'same-origin';

        return fetch(url, opts).then(function(r) {
            if (!r.ok) return r.json().then(function(e) { throw e; });
            return r.json();
        }).catch(function(err) {
            console.error('API-Fehler:', err);
            return err || { error: 'Netzwerkfehler' };
        });
    }

    function formatDate(d) {
        if (typeof d === 'string') d = new Date(d + 'T00:00:00');
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function formatTime(d) {
        return String(d.getHours()).padStart(2, '0') + ':' +
            String(d.getMinutes()).padStart(2, '0');
    }

    function formatDateGerman(d) {
        var dayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
        return dayNames[d.getDay()] + ', ' +
            String(d.getDate()).padStart(2, '0') + '.' +
            String(d.getMonth() + 1).padStart(2, '0') + '.' +
            d.getFullYear();
    }

    function getTypeLabel(type) {
        var labels = {
            'treatment': 'Behandlung', 'initial': 'Ersttermin', 'group': 'Gruppentherapie',
            'admin': 'Admin/Blocker', 'domicile': 'Domizil'
        };
        return labels[type] || type;
    }

    function hexToRgba(hex, alpha) {
        if (!hex) hex = '#4a90d9';
        hex = hex.replace('#', '');
        var r = parseInt(hex.substring(0, 2), 16);
        var g = parseInt(hex.substring(2, 4), 16);
        var b = parseInt(hex.substring(4, 6), 16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    function darkenColor(hex, factor) {
        if (!hex) return '#333';
        hex = hex.replace('#', '');
        var r = Math.round(parseInt(hex.substring(0, 2), 16) * factor);
        var g = Math.round(parseInt(hex.substring(2, 4), 16) * factor);
        var b = Math.round(parseInt(hex.substring(4, 6), 16) * factor);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showToast(message, type) {
        var container = document.getElementById('toastContainer');
        if (!container) return;
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + (type || 'info');
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() { toast.remove(); }, 3000);
    }

})();
