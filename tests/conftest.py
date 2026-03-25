"""Test-Konfiguration und Fixtures fuer OMNIA Praxissoftware."""
import os
import pytest
from datetime import date

# Test-Umgebung setzen BEVOR app importiert wird
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-not-for-production'
os.environ['ENCRYPTION_KEY'] = ''
os.environ['DATABASE_URI'] = 'sqlite://'

from app import create_app, limiter
from models import db as _db, Organization, User, Patient


@pytest.fixture(scope='session')
def app():
    """Erstellt die Test-App einmalig pro Session."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}
    # Rate-Limiter in Tests deaktivieren
    limiter.enabled = False
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
    org = Organization(name='Test-Praxis')
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
    org = Organization(name='Andere-Praxis')
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
