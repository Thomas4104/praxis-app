// OMNIA Praxissoftware - Kalender-Interaktionen

document.addEventListener('DOMContentLoaded', () => {
    loadAppointments();

    // Therapeuten-Filter
    document.querySelectorAll('.therapist-checkbox').forEach(cb => {
        cb.addEventListener('change', () => filterAppointments());
    });
});

// Termine laden und anzeigen
async function loadAppointments() {
    const container = document.getElementById('calendarContainer');
    const view = container.dataset.view;
    const dateStr = container.dataset.date;

    let start, end;
    const currentDate = new Date(dateStr);

    if (view === 'day') {
        start = dateStr;
        end = dateStr;
    } else {
        // Wochenansicht: Montag bis Freitag berechnen
        const day = currentDate.getDay();
        const monday = new Date(currentDate);
        monday.setDate(currentDate.getDate() - (day === 0 ? 6 : day - 1));
        const friday = new Date(monday);
        friday.setDate(monday.getDate() + 4);
        start = formatDate(monday);
        end = formatDate(friday);
    }

    try {
        const response = await fetch(`/api/calendar/appointments?start=${start}&end=${end}`);
        const appointments = await response.json();
        renderAppointments(appointments, view);
    } catch (error) {
        console.error('Termine laden fehlgeschlagen:', error);
    }
}

// Termine im Kalender rendern
function renderAppointments(appointments, view) {
    // Bestehende Termin-Elemente entfernen
    document.querySelectorAll('.calendar-appointment').forEach(el => el.remove());

    appointments.forEach(apt => {
        const startTime = new Date(apt.start);
        const endTime = new Date(apt.end);
        const startHour = startTime.getHours();
        const startMinutes = startTime.getMinutes();
        const durationMinutes = (endTime - startTime) / 60000;

        // Position berechnen (7:00 = 0px, jede Stunde = 60px)
        const topOffset = (startHour - 7) * 60 + startMinutes;
        const height = Math.max(durationMinutes, 15); // Minimum 15px

        if (view === 'day') {
            // Tagesansicht: In Therapeuten-Spalte einfügen
            const column = document.querySelector(`.day-slots[data-employee-id="${apt.employee_id}"]`);
            if (!column) return;

            const el = createAppointmentElement(apt, topOffset, height);
            column.appendChild(el);
        } else {
            // Wochenansicht: In Tages-Spalte einfügen
            const dateStr = formatDate(startTime);
            const column = document.querySelector(`.day-slots[data-date="${dateStr}"]`);
            if (!column) return;

            const el = createAppointmentElement(apt, topOffset, height);
            column.appendChild(el);
        }
    });
}

// Termin-Element erstellen
function createAppointmentElement(apt, top, height) {
    const el = document.createElement('div');
    el.className = 'calendar-appointment';
    el.style.top = top + 'px';
    el.style.height = height + 'px';
    el.style.backgroundColor = apt.color || '#4a90d9';
    el.dataset.appointmentId = apt.id;
    el.draggable = true;

    const startTime = new Date(apt.start);
    const endTime = new Date(apt.end);

    el.innerHTML = `
        <div class="appointment-time">${formatTime(startTime)} - ${formatTime(endTime)}</div>
        <div class="appointment-patient">${apt.title}</div>
    `;

    // Klick: Details / Bearbeiten
    el.addEventListener('click', (e) => {
        e.stopPropagation();
        showAppointmentDetails(apt);
    });

    // Drag & Drop
    el.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', JSON.stringify({
            id: apt.id,
            duration: (endTime - startTime) / 60000,
            employee_id: apt.employee_id,
        }));
        el.style.opacity = '0.5';
    });

    el.addEventListener('dragend', () => {
        el.style.opacity = '1';
    });

    return el;
}

// Auf Stunden-Slots klicken = Neuen Termin erstellen
document.addEventListener('click', (e) => {
    const hourSlot = e.target.closest('.hour-slot');
    if (!hourSlot) return;

    const hour = parseInt(hourSlot.dataset.hour);
    const employeeId = hourSlot.dataset.employeeId;
    const dateStr = hourSlot.dataset.date || document.getElementById('calendarContainer').dataset.date;

    openNewAppointmentModal(dateStr, hour, employeeId);
});

// Drag & Drop auf Stunden-Slots
document.addEventListener('dragover', (e) => {
    const hourSlot = e.target.closest('.hour-slot');
    if (hourSlot) {
        e.preventDefault();
        hourSlot.style.background = '#e8f0fe';
    }
});

document.addEventListener('dragleave', (e) => {
    const hourSlot = e.target.closest('.hour-slot');
    if (hourSlot) {
        hourSlot.style.background = '';
    }
});

document.addEventListener('drop', async (e) => {
    const hourSlot = e.target.closest('.hour-slot');
    if (!hourSlot) return;
    e.preventDefault();
    hourSlot.style.background = '';

    const data = JSON.parse(e.dataTransfer.getData('text/plain'));
    const newHour = parseInt(hourSlot.dataset.hour);
    const newEmployeeId = hourSlot.dataset.employeeId || data.employee_id;
    const newDate = hourSlot.dataset.date || document.getElementById('calendarContainer').dataset.date;

    const newStart = `${newDate}T${String(newHour).padStart(2, '0')}:00:00`;
    const endDate = new Date(newStart);
    endDate.setMinutes(endDate.getMinutes() + data.duration);
    const newEnd = endDate.toISOString().slice(0, 19);

    try {
        const response = await fetch(`/api/calendar/appointments/${data.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: newStart,
                end: newEnd,
                employee_id: parseInt(newEmployeeId),
            }),
        });

        if (response.ok) {
            loadAppointments();
        } else {
            const err = await response.json();
            alert(err.error || 'Fehler beim Verschieben');
        }
    } catch (error) {
        console.error('Termin verschieben fehlgeschlagen:', error);
    }
});

// Modal für neuen Termin öffnen
function openNewAppointmentModal(dateStr, hour, employeeId) {
    const modal = document.getElementById('appointmentModal');
    document.getElementById('modalDate').value = dateStr;
    document.getElementById('modalStartTime').value = String(hour).padStart(2, '0') + ':00';
    document.getElementById('modalEndTime').value = String(hour).padStart(2, '0') + ':30';

    if (employeeId) {
        document.getElementById('modalEmployee').value = employeeId;
    }

    // Felder zurücksetzen
    document.getElementById('modalPatientSearch').value = '';
    document.getElementById('modalPatientId').value = '';
    document.getElementById('modalNotes').value = '';
    document.getElementById('patientResults').classList.remove('active');

    modal.classList.add('open');
}

function closeModal() {
    document.getElementById('appointmentModal').classList.remove('open');
}

// Termin speichern
async function saveAppointment(event) {
    event.preventDefault();

    const patientId = document.getElementById('modalPatientId').value;
    if (!patientId) {
        alert('Bitte einen Patienten auswählen');
        return;
    }

    const dateStr = document.getElementById('modalDate').value;
    const startTime = document.getElementById('modalStartTime').value;
    const endTime = document.getElementById('modalEndTime').value;
    const employeeId = document.getElementById('modalEmployee').value;
    const notes = document.getElementById('modalNotes').value;

    try {
        const response = await fetch('/api/calendar/appointments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: parseInt(patientId),
                employee_id: parseInt(employeeId),
                start: `${dateStr}T${startTime}:00`,
                end: `${dateStr}T${endTime}:00`,
                notes: notes,
            }),
        });

        const data = await response.json();

        if (response.ok) {
            closeModal();
            loadAppointments();
        } else {
            alert(data.error || 'Fehler beim Erstellen');
        }
    } catch (error) {
        console.error('Termin erstellen fehlgeschlagen:', error);
    }
}

// Patienten-Suche für Modal
let searchTimeout;
async function searchPatients(query) {
    clearTimeout(searchTimeout);
    const resultsDiv = document.getElementById('patientResults');

    if (query.length < 2) {
        resultsDiv.classList.remove('active');
        return;
    }

    searchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/patients/api/search?q=${encodeURIComponent(query)}`);
            const patients = await response.json();

            if (patients.length === 0) {
                resultsDiv.innerHTML = '<div class="autocomplete-item">Keine Patienten gefunden</div>';
            } else {
                resultsDiv.innerHTML = patients.map(p =>
                    `<div class="autocomplete-item" onclick="selectPatient(${p.id}, '${p.name}')">${p.name} ${p.geburtsdatum ? '(' + p.geburtsdatum + ')' : ''}</div>`
                ).join('');
            }
            resultsDiv.classList.add('active');
        } catch (error) {
            console.error('Patientensuche fehlgeschlagen:', error);
        }
    }, 300);
}

function selectPatient(id, name) {
    document.getElementById('modalPatientId').value = id;
    document.getElementById('modalPatientSearch').value = name;
    document.getElementById('patientResults').classList.remove('active');
}

// Termin-Details anzeigen
function showAppointmentDetails(apt) {
    const startTime = new Date(apt.start);
    const endTime = new Date(apt.end);

    const action = confirm(
        `${apt.title}\n` +
        `${formatTime(startTime)} - ${formatTime(endTime)}\n` +
        `Therapeut: ${apt.employee_name}\n\n` +
        `Termin absagen?`
    );

    if (action) {
        cancelAppointment(apt.id);
    }
}

async function cancelAppointment(id) {
    try {
        const response = await fetch(`/api/calendar/appointments/${id}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: 'Über Kalender abgesagt' }),
        });

        if (response.ok) {
            loadAppointments();
        }
    } catch (error) {
        console.error('Termin absagen fehlgeschlagen:', error);
    }
}

// Therapeuten-Filter
function filterAppointments() {
    const visibleIds = [];
    document.querySelectorAll('.therapist-checkbox:checked').forEach(cb => {
        visibleIds.push(cb.dataset.employeeId);
    });

    document.querySelectorAll('.therapist-column').forEach(col => {
        const empId = col.dataset.employeeId;
        col.style.display = visibleIds.includes(empId) ? '' : 'none';
    });

    document.querySelectorAll('.calendar-appointment').forEach(apt => {
        const empId = apt.closest('[data-employee-id]')?.dataset.employeeId;
        if (empId) {
            apt.style.display = visibleIds.includes(empId) ? '' : 'none';
        }
    });
}

// Hilfsfunktionen
function formatDate(date) {
    const d = new Date(date);
    return d.getFullYear() + '-' +
           String(d.getMonth() + 1).padStart(2, '0') + '-' +
           String(d.getDate()).padStart(2, '0');
}

function formatTime(date) {
    return String(date.getHours()).padStart(2, '0') + ':' +
           String(date.getMinutes()).padStart(2, '0');
}
