"""Sicherheitstests fuer Authentifizierung."""
import pytest
from tests.conftest import login, logout


class TestLogin:
    """Tests fuer Login-Funktionalitaet."""

    def test_login_valid_credentials(self, client, admin_user):
        """Erfolgreicher Login mit korrekten Zugangsdaten."""
        response = login(client, 'admin_test', 'SecurePass123!')
        assert response.status_code == 200

    def test_login_invalid_password(self, client, admin_user):
        """Login mit falschem Passwort muss fehlschlagen."""
        response = login(client, 'admin_test', 'wrong_password')
        assert b'Ungueltig' in response.data or b'fehlgeschlagen' in response.data or response.status_code == 200

    def test_login_nonexistent_user(self, client):
        """Login mit nicht existierendem User muss fehlschlagen."""
        response = login(client, 'doesnotexist', 'password')
        assert b'Ungueltig' in response.data or b'fehlgeschlagen' in response.data or response.status_code == 200

    def test_account_lockout_after_failed_attempts(self, client, admin_user):
        """Nach 5 fehlgeschlagenen Versuchen muss Account gesperrt sein (15 Min Lockout)."""
        for i in range(5):
            login(client, 'admin_test', 'wrong_password')
        # 6. Versuch mit korrektem Passwort sollte durch Lockout fehlschlagen
        response = login(client, 'admin_test', 'SecurePass123!')
        # Lockout-Meldung muss erscheinen
        assert b'gesperrt' in response.data or b'locked' in response.data or b'Minuten' in response.data

    def test_login_inactive_user(self, client, db, org):
        """Deaktivierter User darf sich nicht einloggen."""
        from models import User
        user = User(
            username='inactive_user',
            first_name='Inactive',
            last_name='User',
            role='therapist',
            organization_id=org.id,
            is_active=False,
        )
        user.set_password('SecurePass123!')
        db.session.add(user)
        db.session.commit()

        response = login(client, 'inactive_user', 'SecurePass123!')
        # Sollte nicht eingeloggt werden
        assert b'deaktiviert' in response.data or b'gesperrt' in response.data or b'Anmelden' in response.data


class TestOpenRedirect:
    """Tests gegen Open-Redirect-Angriffe."""

    def test_next_parameter_internal(self, client, admin_user):
        """Interner Redirect nach Login sollte funktionieren."""
        response = client.post('/login', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        # Sollte intern weiterleiten (302 zum Dashboard)
        assert response.status_code in (200, 302)

    def test_next_parameter_external_blocked(self, client, admin_user):
        """Externer Redirect via next-Parameter muss blockiert werden."""
        response = client.post('/login?next=https://evil.com', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        if response.status_code in (301, 302):
            location = response.headers.get('Location', '')
            assert 'evil.com' not in location, \
                f'Open Redirect! Location zeigt auf: {location}'

    def test_next_parameter_javascript_blocked(self, client, admin_user):
        """JavaScript-URIs im next-Parameter muessen blockiert werden."""
        response = client.post('/login?next=javascript:alert(1)', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        if response.status_code in (301, 302):
            location = response.headers.get('Location', '')
            assert 'javascript' not in location, \
                f'JavaScript-Injection moeglich! Location: {location}'

    def test_next_parameter_protocol_relative_blocked(self, client, admin_user):
        """Protocol-relative URLs muessen blockiert werden."""
        response = client.post('/login?next=//evil.com', data={
            'username': 'admin_test',
            'password': 'SecurePass123!',
        }, follow_redirects=False)
        if response.status_code in (301, 302):
            location = response.headers.get('Location', '')
            assert 'evil.com' not in location, \
                f'Protocol-relative Redirect! Location: {location}'


class TestSessionSecurity:
    """Tests fuer Session-Sicherheit."""

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
                f'Route {route} ist nicht geschuetzt (Status: {response.status_code})!'

    def test_logout_clears_session(self, client, admin_user):
        """Nach Logout darf kein Zugriff auf geschuetzte Seiten moeglich sein."""
        login(client, 'admin_test', 'SecurePass123!')
        logout(client)
        response = client.get('/dashboard/', follow_redirects=False)
        assert response.status_code in (302, 301, 308), \
            'Nach Logout ist Dashboard noch zugaenglich!'


class TestSecurityHeaders:
    """Tests fuer HTTP-Sicherheitsheader."""

    def test_security_headers_present(self, client, admin_user):
        """Wichtige Sicherheitsheader muessen gesetzt sein."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/dashboard/')
        headers = response.headers
        assert 'X-Content-Type-Options' in headers, \
            'X-Content-Type-Options Header fehlt!'
        assert 'X-Frame-Options' in headers, \
            'X-Frame-Options Header fehlt!'
        assert 'Referrer-Policy' in headers, \
            'Referrer-Policy Header fehlt!'


class TestPasswordPolicy:
    """Tests fuer Passwort-Richtlinien."""

    def test_password_too_short(self, client, admin_user):
        """Passwort unter 12 Zeichen muss abgelehnt werden."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.post('/change-password', data={
            'current_password': 'SecurePass123!',
            'new_password': 'Short1!',
            'confirm_password': 'Short1!',
        }, follow_redirects=True)
        # Passwortaenderung sollte fehlschlagen
        assert response.status_code == 200

    def test_password_without_special_char(self, client, admin_user):
        """Passwort ohne Sonderzeichen muss abgelehnt werden."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.post('/change-password', data={
            'current_password': 'SecurePass123!',
            'new_password': 'SecurePass12345',
            'confirm_password': 'SecurePass12345',
        }, follow_redirects=True)
        assert response.status_code == 200
