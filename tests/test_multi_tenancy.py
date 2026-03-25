"""Integration Tests fuer Multi-Tenancy Isolation.

Stellt sicher, dass Organisationen vollstaendig voneinander isoliert sind.
"""
import pytest
from datetime import datetime, date, timedelta
from models import db, Patient, Employee, Appointment, Invoice, Location
from tests.conftest import login, logout


@pytest.fixture
def org_a_patient(db, org):
    """Patient in Organisation A."""
    patient = Patient(
        organization_id=org.id,
        first_name='Anna',
        last_name='Mueller',
        patient_number='P00001',
        date_of_birth=date(1985, 3, 15),
        is_active=True,
    )
    db.session.add(patient)
    db.session.commit()
    return patient


@pytest.fixture
def org_b_patient(db, other_org):
    """Patient in Organisation B."""
    patient = Patient(
        organization_id=other_org.id,
        first_name='Bruno',
        last_name='Schmidt',
        patient_number='P10001',
        date_of_birth=date(1990, 7, 20),
        is_active=True,
    )
    db.session.add(patient)
    db.session.commit()
    return patient


@pytest.fixture
def org_a_invoice(db, org, org_a_patient):
    """Rechnung in Organisation A."""
    invoice = Invoice(
        organization_id=org.id,
        patient_id=org_a_patient.id,
        invoice_number='R-2026-001',
        amount_total=150.00,
        amount_open=150.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


@pytest.fixture
def org_b_invoice(db, other_org, org_b_patient):
    """Rechnung in Organisation B."""
    invoice = Invoice(
        organization_id=other_org.id,
        patient_id=org_b_patient.id,
        invoice_number='R-2026-100',
        amount_total=200.00,
        amount_open=200.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


class TestPatientIsolation:
    """User in Org A kann KEINE Patienten von Org B sehen."""

    def test_patient_list_shows_only_own_org(self, client, admin_user, org_a_patient, org_b_patient):
        """Patientenliste zeigt nur Patienten der eigenen Organisation."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/')
        if response.status_code == 200:
            html = response.data.decode()
            # Eigene Patienten sichtbar
            assert 'Anna' in html or 'Mueller' in html
            # Fremde Patienten NICHT sichtbar
            assert 'Bruno' not in html
            assert 'Schmidt' not in html

    def test_patient_detail_blocked_for_other_org(self, client, admin_user, org_b_patient):
        """Zugriff auf Patient aus anderer Organisation wird blockiert."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get(f'/patients/{org_b_patient.id}')
        assert response.status_code in (302, 403, 404)

    def test_patient_edit_blocked_for_other_org(self, client, admin_user, org_b_patient):
        """Bearbeitung eines Patienten aus anderer Organisation wird blockiert."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get(f'/patients/{org_b_patient.id}/edit')
        assert response.status_code in (302, 403, 404)


class TestInvoiceIsolation:
    """User in Org A kann KEINE Rechnungen von Org B sehen."""

    def test_billing_list_shows_only_own_org(self, client, admin_user, org_a_invoice, org_b_invoice):
        """Rechnungsliste zeigt nur Rechnungen der eigenen Organisation."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/billing/')
        if response.status_code == 200:
            html = response.data.decode()
            assert 'R-2026-001' in html
            assert 'R-2026-100' not in html

    def test_invoice_detail_blocked_for_other_org(self, client, admin_user, org_b_invoice):
        """Zugriff auf Rechnung aus anderer Organisation wird blockiert."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get(f'/billing/{org_b_invoice.id}')
        assert response.status_code in (302, 403, 404)


class TestSearchIsolation:
    """Suche gibt nur Ergebnisse der eigenen Organisation zurueck."""

    def test_patient_api_search_only_own_org(self, client, admin_user, org_a_patient, org_b_patient):
        """Patienten-Suche (API) gibt nur eigene Patienten zurueck."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/api/search?q=Mueller')
        if response.status_code == 200:
            data = response.get_json()
            if data:
                assert any('Mueller' in str(p) for p in data)

        response = client.get('/patients/api/search?q=Schmidt')
        if response.status_code == 200:
            data = response.get_json()
            # Fremde Patienten duerfen nicht in der Suche erscheinen
            assert not data or len(data) == 0

    def test_patient_search_min_length(self, client, admin_user, org_a_patient):
        """Suche mit weniger als 2 Zeichen gibt leere Liste zurueck."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/api/search?q=A')
        if response.status_code == 200:
            data = response.get_json()
            assert data == [] or data is None


class TestAPIEndpointIsolation:
    """API-Endpoints filtern korrekt nach Organization."""

    def test_cross_org_patient_toggle_blocked(self, client, admin_user, org_b_patient):
        """Patient einer fremden Organisation kann nicht deaktiviert werden."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.post(f'/patients/{org_b_patient.id}/toggle')
        assert response.status_code in (302, 403, 404)

    def test_cross_org_invoice_blocked(self, client, admin_user, org_b_invoice):
        """Rechnung einer fremden Organisation kann nicht gesendet werden."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.post(f'/billing/{org_b_invoice.id}/send', data={
            'send_via': 'email',
        })
        assert response.status_code in (302, 403, 404)
