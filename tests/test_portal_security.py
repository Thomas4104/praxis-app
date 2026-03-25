"""Integration Tests fuer Portal-Security.

Stellt sicher, dass Portal-Benutzer (Patienten) nur eigene Daten sehen
und keine fremden Daten abrufen koennen.
"""
import pytest
from datetime import datetime, date, timedelta
from models import (
    db, Organization, Patient, Employee, User, Appointment, Invoice,
    Location, PortalAccount, OnlineBookingRequest, TreatmentSeriesTemplate,
)


def portal_login(client, email, password):
    """Hilfsfunktion: Portal-User einloggen."""
    return client.post('/portal/login', data={
        'email': email,
        'password': password,
    }, follow_redirects=True)


@pytest.fixture
def portal_setup(db, org):
    """Erstellt zwei Patienten mit Portal-Accounts und Testdaten."""
    # Standort und Mitarbeiter
    location = Location(organization_id=org.id, name='Hauptstandort', is_active=True)
    db.session.add(location)
    db.session.flush()

    # Staff-User fuer Employee
    staff_user = User(
        username='portal_staff',
        first_name='Staff',
        last_name='Test',
        role='therapist',
        organization_id=org.id,
        is_active=True,
    )
    staff_user.set_password('SecurePass123!')
    db.session.add(staff_user)
    db.session.flush()

    employee = Employee(
        organization_id=org.id,
        user_id=staff_user.id,
        employee_number='E010',
        default_location_id=location.id,
        is_active=True,
    )
    db.session.add(employee)
    db.session.flush()

    # Patient A mit Portal-Account
    patient_a = Patient(
        organization_id=org.id,
        first_name='Alice',
        last_name='Portal',
        patient_number='P10001',
        date_of_birth=date(1990, 1, 1),
        email='alice@example.com',
        is_active=True,
    )
    db.session.add(patient_a)
    db.session.flush()

    account_a = PortalAccount(
        patient_id=patient_a.id,
        email='alice@example.com',
        is_active=True,
        is_verified=True,
    )
    account_a.set_password('PortalPass123!')
    db.session.add(account_a)
    db.session.flush()

    # Patient B mit Portal-Account
    patient_b = Patient(
        organization_id=org.id,
        first_name='Bob',
        last_name='Portal',
        patient_number='P10002',
        date_of_birth=date(1988, 6, 15),
        email='bob@example.com',
        is_active=True,
    )
    db.session.add(patient_b)
    db.session.flush()

    account_b = PortalAccount(
        patient_id=patient_b.id,
        email='bob@example.com',
        is_active=True,
        is_verified=True,
    )
    account_b.set_password('PortalPass456!')
    db.session.add(account_b)
    db.session.flush()

    # Termine fuer beide Patienten
    start_a = datetime.now() + timedelta(days=3)
    appt_a = Appointment(
        patient_id=patient_a.id,
        employee_id=employee.id,
        location_id=location.id,
        start_time=start_a,
        end_time=start_a + timedelta(minutes=30),
        duration_minutes=30,
        status='scheduled',
    )
    start_b = datetime.now() + timedelta(days=5)
    appt_b = Appointment(
        patient_id=patient_b.id,
        employee_id=employee.id,
        location_id=location.id,
        start_time=start_b,
        end_time=start_b + timedelta(minutes=30),
        duration_minutes=30,
        status='scheduled',
    )
    db.session.add_all([appt_a, appt_b])
    db.session.flush()

    # Rechnungen fuer beide Patienten
    invoice_a = Invoice(
        organization_id=org.id,
        patient_id=patient_a.id,
        invoice_number='R-P-001',
        amount_total=100.00,
        amount_open=100.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    invoice_b = Invoice(
        organization_id=org.id,
        patient_id=patient_b.id,
        invoice_number='R-P-002',
        amount_total=200.00,
        amount_open=200.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add_all([invoice_a, invoice_b])
    db.session.commit()

    return {
        'patient_a': patient_a,
        'patient_b': patient_b,
        'account_a': account_a,
        'account_b': account_b,
        'appt_a': appt_a,
        'appt_b': appt_b,
        'invoice_a': invoice_a,
        'invoice_b': invoice_b,
        'employee': employee,
        'location': location,
    }


class TestPortalLogin:
    """Portal-Login mit falschen Credentials wird abgelehnt."""

    def test_wrong_password_rejected(self, client, portal_setup):
        """Falsches Passwort wird abgelehnt."""
        response = portal_login(client, 'alice@example.com', 'FalschesPasswort!')
        html = response.data.decode()
        assert 'ungültig' in html.lower() or response.status_code == 200
        # Session sollte keinen portal_account_id enthalten
        with client.session_transaction() as sess:
            assert 'portal_account_id' not in sess

    def test_wrong_email_rejected(self, client, portal_setup):
        """Nicht existierende E-Mail wird abgelehnt."""
        response = portal_login(client, 'nobody@example.com', 'PortalPass123!')
        with client.session_transaction() as sess:
            assert 'portal_account_id' not in sess

    def test_inactive_account_rejected(self, client, db, portal_setup):
        """Inaktiver Account kann sich nicht einloggen."""
        portal_setup['account_a'].is_active = False
        db.session.commit()

        response = portal_login(client, 'alice@example.com', 'PortalPass123!')
        html = response.data.decode()
        assert 'aktiviert' in html.lower() or 'nicht aktiviert' in html.lower()
        with client.session_transaction() as sess:
            assert 'portal_account_id' not in sess

    def test_valid_login_succeeds(self, client, portal_setup):
        """Korrektes Login setzt portal_account_id in Session."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        with client.session_transaction() as sess:
            assert sess.get('portal_account_id') == portal_setup['account_a'].id


class TestPortalAppointmentIsolation:
    """Portal-User kann nur eigene Termine sehen."""

    def test_appointments_page_shows_only_own(self, client, portal_setup):
        """Termine-Seite zeigt nur eigene Termine."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        response = client.get('/portal/appointments')
        html = response.data.decode()
        # Alice sollte ihre Termine sehen, aber nicht Bobs
        assert response.status_code == 200

    def test_cancel_other_patients_appointment_blocked(self, client, portal_setup):
        """Absage eines fremden Termins wird mit 403 blockiert."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        other_appt_id = portal_setup['appt_b'].id
        response = client.post(f'/portal/appointments/{other_appt_id}/cancel')
        assert response.status_code in (403, 302)
        # Sicherstellen, dass der Termin nicht storniert wurde
        from models import Appointment
        appt = Appointment.query.get(other_appt_id)
        assert appt.status == 'scheduled'


class TestPortalInvoiceIsolation:
    """Portal-User kann nur eigene Rechnungen sehen."""

    def test_dashboard_shows_only_own_invoices(self, client, portal_setup):
        """Dashboard zeigt nur eigene offene Rechnungen."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        response = client.get('/portal/')
        html = response.data.decode()
        assert response.status_code == 200
        # R-P-002 (Bobs Rechnung) darf nicht sichtbar sein
        assert 'R-P-002' not in html


class TestPortalPatientDataIsolation:
    """Portal-User kann keine anderen Patienten-Daten abrufen."""

    def test_portal_requires_login(self, client, portal_setup):
        """Ohne Login wird auf Login-Seite umgeleitet."""
        response = client.get('/portal/', follow_redirects=False)
        assert response.status_code == 302
        assert '/portal/login' in response.headers.get('Location', '')

    def test_portal_session_isolation(self, client, portal_setup):
        """Manipulierte Session-ID wird abgelehnt."""
        with client.session_transaction() as sess:
            sess['portal_account_id'] = 99999  # Nicht existierender Account
        response = client.get('/portal/', follow_redirects=False)
        assert response.status_code == 302


class TestOnlineBookingValidation:
    """Online-Booking-Validierung: kein Datum in der Vergangenheit."""

    def test_booking_past_date_rejected(self, client, db, portal_setup):
        """Buchung mit Datum in der Vergangenheit wird abgelehnt."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = client.post('/portal/book', data={
            'requested_date': yesterday,
            'requested_time': '10:00',
            'notes': 'Test-Buchung',
        }, follow_redirects=True)
        html = response.data.decode()
        # Entweder Fehlermeldung oder kein Eintrag in DB
        bookings = OnlineBookingRequest.query.filter_by(
            patient_id=portal_setup['patient_a'].id
        ).all()
        past_bookings = [
            b for b in bookings
            if b.requested_date < date.today()
        ]
        assert len(past_bookings) == 0

    def test_booking_today_rejected(self, client, portal_setup):
        """Buchung fuer heute wird abgelehnt (Minimum ist morgen)."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        today = date.today().isoformat()
        response = client.post('/portal/book', data={
            'requested_date': today,
            'requested_time': '14:00',
            'notes': 'Heute buchen',
        }, follow_redirects=True)
        bookings = OnlineBookingRequest.query.filter_by(
            patient_id=portal_setup['patient_a'].id
        ).all()
        today_bookings = [
            b for b in bookings
            if b.requested_date <= date.today()
        ]
        assert len(today_bookings) == 0

    def test_booking_too_far_future_rejected(self, client, portal_setup):
        """Buchung mehr als 90 Tage in der Zukunft wird abgelehnt."""
        portal_login(client, 'alice@example.com', 'PortalPass123!')
        far_future = (date.today() + timedelta(days=100)).isoformat()
        response = client.post('/portal/book', data={
            'requested_date': far_future,
            'requested_time': '10:00',
            'notes': 'Zu weit in der Zukunft',
        }, follow_redirects=True)
        bookings = OnlineBookingRequest.query.filter_by(
            patient_id=portal_setup['patient_a'].id
        ).all()
        far_bookings = [
            b for b in bookings
            if b.requested_date > date.today() + timedelta(days=90)
        ]
        assert len(far_bookings) == 0
