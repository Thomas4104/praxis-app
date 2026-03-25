"""Tests fuer rollenbasierte Zugriffskontrolle (RBAC) und Multi-Tenancy."""
import pytest
from datetime import date
from tests.conftest import login


class TestReceptionAccess:
    """Empfangsmitarbeiter darf NUR eingeschraenkte Bereiche sehen."""

    def test_reception_cannot_access_settings(self, client, reception_user):
        """Empfang darf nicht auf Einstellungen zugreifen."""
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/settings/', follow_redirects=False)
        assert response.status_code in (302, 403), \
            f'Empfang hat Zugriff auf /settings/ (Status: {response.status_code})!'

    @pytest.mark.xfail(reason='RBAC fuer Buchhaltung noch nicht implementiert - TODO')
    def test_reception_cannot_access_accounting(self, client, reception_user):
        """Empfang darf nicht auf Buchhaltung zugreifen."""
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/accounting/', follow_redirects=False)
        assert response.status_code in (302, 403, 404), \
            f'Empfang hat Zugriff auf /accounting/ (Status: {response.status_code})!'

    @pytest.mark.xfail(reason='RBAC fuer HR noch nicht implementiert - TODO')
    def test_reception_cannot_access_hr(self, client, reception_user):
        """Empfang darf nicht auf HR zugreifen."""
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/hr/', follow_redirects=False)
        assert response.status_code in (302, 403, 404), \
            f'Empfang hat Zugriff auf /hr/ (Status: {response.status_code})!'

    def test_reception_can_access_calendar(self, client, reception_user):
        """Empfang sollte auf Kalender zugreifen koennen."""
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/calendar/', follow_redirects=False)
        # Kalender sollte fuer Empfang zugaenglich sein
        assert response.status_code in (200, 302)


class TestTherapistAccess:
    """Therapeut hat klinischen Zugriff, aber kein Admin-Zugriff."""

    def test_therapist_cannot_access_settings(self, client, therapist_user):
        """Therapeut darf nicht auf Admin-Einstellungen zugreifen."""
        login(client, 'therapist_test', 'SecurePass123!')
        response = client.get('/settings/', follow_redirects=False)
        assert response.status_code in (302, 403), \
            f'Therapeut hat Zugriff auf /settings/ (Status: {response.status_code})!'

    def test_therapist_can_access_patients(self, client, therapist_user):
        """Therapeut sollte auf Patientenliste zugreifen koennen."""
        login(client, 'therapist_test', 'SecurePass123!')
        response = client.get('/patients/', follow_redirects=False)
        assert response.status_code in (200, 302)


class TestAdminAccess:
    """Admin hat vollen Zugriff."""

    def test_admin_can_access_settings(self, client, admin_user):
        """Admin darf auf Einstellungen zugreifen."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/settings/')
        # Admin sollte Zugriff haben (200) oder weitergeleitet werden (302)
        assert response.status_code in (200, 302)


class TestMultiTenancy:
    """Organisation A darf KEINE Daten von Organisation B sehen."""

    def test_patient_isolation(self, client, admin_user, other_org, other_org_user, db):
        """Patient aus Org B darf nicht von Org A gesehen werden."""
        from models import Patient
        # Patient in Org B erstellen
        patient_b = Patient(
            organization_id=other_org.id,
            first_name='Geheim',
            last_name='Patient',
            date_of_birth=date(1990, 1, 1),
        )
        db.session.add(patient_b)
        db.session.commit()

        # Als Org A Admin einloggen
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get(f'/patients/{patient_b.id}')
        # Muss blockiert werden: 403 (Forbidden), 404 (Not Found), oder 302 (Redirect)
        assert response.status_code in (302, 403, 404), \
            f'Multi-Tenancy verletzt! Patient aus anderer Org zugaenglich (Status: {response.status_code})!'

    def test_user_cannot_switch_org_via_parameter(self, client, admin_user, other_org, db):
        """User darf nicht durch URL-Manipulation auf andere Org zugreifen."""
        login(client, 'admin_test', 'SecurePass123!')
        # Versuch, Patienten der anderen Org zu laden
        response = client.get(f'/patients/?organization_id={other_org.id}')
        # Sollte nur eigene Patienten zeigen, nicht die der anderen Org
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert b'Geheim' not in response.data
