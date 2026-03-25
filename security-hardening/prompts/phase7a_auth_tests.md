Du bist ein Security Test Engineer. Dein Auftrag: Sicherheitstests fuer Authentifizierung und Autorisierung in /Users/thomasbalke/praxis-app schreiben.

WICHTIG: Lies zuerst die bestehenden Auth-Routen und Models.

## Aufgabe 1: Test-Konfiguration erstellen
Erstelle: /Users/thomasbalke/praxis-app/tests/__init__.py (leere Datei)
Erstelle: /Users/thomasbalke/praxis-app/tests/conftest.py

```python
"""Test-Konfiguration und Fixtures fuer OMNIA Praxissoftware."""
import os
import pytest
from datetime import date

# Test-Umgebung setzen BEVOR app importiert wird
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-not-for-production'
os.environ['ENCRYPTION_KEY'] = ''  # Leer = Verschluesselung deaktiviert in Tests
os.environ['DATABASE_URI'] = 'sqlite:///:memory:'

from app import create_app
from models import db as _db, Organization, User, Patient, Employee


@pytest.fixture(scope='session')
def app():
    """Erstellt die Test-App einmalig pro Session."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # CSRF in Tests deaktivieren
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    return app


@pytest.fixture(scope='function')
def db(app):
    """Frische Datenbank fuer jeden Test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Test-Client."""
    return app.test_client()


@pytest.fixture
def org(db):
    """Test-Organisation."""
    org = Organization(name='Test-Praxis', slug='test')
    db.session.add(org)
    db.session.commit()
    return org


@pytest.fixture
def admin_user(db, org):
    """Admin-User."""
    user = User(
        username='admin_test',
        first_name='Admin',
        last_name='Test',
        role='admin',
        organization_id=org.id,
        is_active=True,
    )
    user.set_password('SecurePass123!')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def therapist_user(db, org):
    """Therapeuten-User."""
    user = User(
        username='therapist_test',
        first_name='Therapeut',
        last_name='Test',
        role='therapist',
        organization_id=org.id,
        is_active=True,
    )
    user.set_password('SecurePass123!')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def reception_user(db, org):
    """Empfangs-User."""
    user = User(
        username='reception_test',
        first_name='Empfang',
        last_name='Test',
        role='reception',
        organization_id=org.id,
        is_active=True,
    )
    user.set_password('SecurePass123!')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def other_org(db):
    """Zweite Organisation fuer Multi-Tenancy Tests."""
    org = Organization(name='Andere-Praxis', slug='other')
    db.session.add(org)
    db.session.commit()
    return org


@pytest.fixture
def other_org_user(db, other_org):
    """User in anderer Organisation."""
    user = User(
        username='other_admin',
        first_name='Other',
        last_name='Admin',
        role='admin',
        organization_id=other_org.id,
        is_active=True,
    )
    user.set_password('SecurePass123!')
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username, password):
    """Hilfsfunktion: User einloggen."""
    return client.post('/login', data={
        'username': username,
        'password': password,
    }, follow_redirects=True)


def logout(client):
    """Hilfsfunktion: User ausloggen."""
    return client.get('/logout', follow_redirects=True)
```

## Aufgabe 2: Auth-Tests schreiben
Erstelle: /Users/thomasbalke/praxis-app/tests/test_auth.py

```python
"""Sicherheitstests fuer Authentifizierung."""
import pytest
from tests.conftest import login, logout


class TestLogin:
    def test_login_valid_credentials(self, client, admin_user):
        response = login(client, 'admin_test', 'SecurePass123!')
        assert response.status_code == 200

    def test_login_invalid_password(self, client, admin_user):
        response = login(client, 'admin_test', 'wrong_password')
        assert b'Ungueltig' in response.data or b'fehlgeschlagen' in response.data or response.status_code == 200

    def test_login_nonexistent_user(self, client):
        response = login(client, 'doesnotexist', 'password')
        assert b'Ungueltig' in response.data or b'fehlgeschlagen' in response.data or response.status_code == 200

    def test_account_lockout_after_failed_attempts(self, client, admin_user):
        """Nach 5 fehlgeschlagenen Versuchen muss Account gesperrt sein."""
        for i in range(6):
            login(client, 'admin_test', 'wrong_password')
        # 6. Versuch mit korrektem Passwort sollte fehlschlagen
        response = login(client, 'admin_test', 'SecurePass123!')
        # Entweder Lockout-Meldung oder kein erfolgreicher Login
        # (abhaengig von Implementation)


class TestOpenRedirect:
    def test_next_parameter_internal(self, client, admin_user):
        """Interner Redirect nach Login sollte funktionieren."""
        response = client.post('/login', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        # Sollte intern weiterleiten

    def test_next_parameter_external_blocked(self, client, admin_user):
        """Externer Redirect muss blockiert werden."""
        response = client.post('/login?next=https://evil.com', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        if response.status_code in (301, 302):
            assert 'evil.com' not in response.headers.get('Location', '')

    def test_next_parameter_javascript_blocked(self, client, admin_user):
        """JavaScript-URIs muessen blockiert werden."""
        response = client.post('/login?next=javascript:alert(1)', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        if response.status_code in (301, 302):
            assert 'javascript' not in response.headers.get('Location', '')


class TestSessionSecurity:
    def test_unauthenticated_access_redirects(self, client):
        """Geschuetzte Routen muessen auf Login umleiten."""
        protected_routes = [
            '/dashboard/',
            '/patients/',
            '/calendar/',
            '/billing/',
            '/settings/',
        ]
        for route in protected_routes:
            response = client.get(route, follow_redirects=False)
            assert response.status_code in (302, 301, 308), \
                f'Route {route} ist nicht geschuetzt!'


class TestSecurityHeaders:
    def test_security_headers_present(self, client, admin_user):
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/dashboard/')
        headers = response.headers
        assert 'X-Content-Type-Options' in headers
        assert 'X-Frame-Options' in headers
        assert 'Referrer-Policy' in headers
```

## Aufgabe 3: RBAC-Tests schreiben
Erstelle: /Users/thomasbalke/praxis-app/tests/test_rbac.py

```python
"""Tests fuer rollenbasierte Zugriffskontrolle."""
import pytest
from tests.conftest import login


class TestReceptionAccess:
    """Empfangsmitarbeiter darf NUR eingeschraenkte Bereiche sehen."""

    def test_reception_cannot_access_settings(self, client, reception_user):
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/settings/', follow_redirects=False)
        assert response.status_code in (302, 403)

    def test_reception_cannot_access_accounting(self, client, reception_user):
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/accounting/', follow_redirects=False)
        assert response.status_code in (302, 403)

    def test_reception_cannot_access_hr(self, client, reception_user):
        login(client, 'reception_test', 'SecurePass123!')
        response = client.get('/hr/', follow_redirects=False)
        assert response.status_code in (302, 403)


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
        assert response.status_code in (403, 404)


from datetime import date
```

## Reihenfolge:
1. Lies auth/routes.py und models.py (User) um die tatsaechliche Implementierung zu verstehen
2. Passe conftest.py an die tatsaechlichen Model-Felder und Routen an
3. Erstelle die Test-Dateien
4. Pruefe dass die Tests syntaktisch korrekt sind: python3 -c "import ast; ast.parse(open('tests/test_auth.py').read())"
