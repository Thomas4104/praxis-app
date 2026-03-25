"""Integration Tests fuer Health-Endpoint Sicherheit.

Stellt sicher, dass der Health-Endpoint korrekt funktioniert
und keine internen Details bei Fehlern exponiert.
"""
import pytest


class TestHealthEndpoint:
    """Health-Endpoint Tests."""

    def test_health_returns_200(self, client):
        """Health-Endpoint gibt 200 mit status=healthy zurueck."""
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data['database'] == 'connected'

    def test_health_response_format(self, client):
        """Health-Response hat korrektes JSON-Format."""
        response = client.get('/health')
        data = response.get_json()
        assert 'status' in data
        # Darf keine sensiblen Infos enthalten
        response_text = str(data).lower()
        assert 'password' not in response_text
        assert 'secret' not in response_text
        assert 'traceback' not in response_text

    def test_health_does_not_expose_details_on_error(self, client):
        """Bei Fehler duerfen keine internen Details exponiert werden."""
        response = client.get('/health')
        data = response.get_json()
        if 'error' in data:
            error_text = data['error'].lower()
            assert 'traceback' not in error_text
            assert 'password' not in error_text
            assert 'postgresql' not in error_text
            assert 'sqlalchemy' not in error_text
            assert 'secret_key' not in error_text

    def test_health_no_auth_required(self, client):
        """Health-Endpoint erfordert keine Authentifizierung."""
        # Ohne Login muss der Endpoint erreichbar sein
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_returns_json_content_type(self, client):
        """Health-Endpoint gibt JSON Content-Type zurueck."""
        response = client.get('/health')
        assert 'application/json' in response.content_type
