import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Basis-Konfiguration (Produktion)"""

    # Sicherheit: SECRET_KEY muss in Produktion gesetzt sein
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY ist nicht gesetzt. '
            'Bitte als Umgebungsvariable definieren: '
            'export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")'
        )

    # Datenbank
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI', 'sqlite:///praxis.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'max_overflow': 40,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # CSRF-Schutz aktiviert
    WTF_CSRF_ENABLED = True

    # App
    APP_NAME = 'OMNIA Praxissoftware'

    # Feld-Level-Verschluesselung
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')

    # KI
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

    # Session-Sicherheit
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=20)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'

    # Datei-Uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')


class DevelopmentConfig(Config):
    """Entwicklungsumgebung"""
    # Fallback SECRET_KEY fuer lokale Entwicklung
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-nicht-fuer-produktion-verwenden')
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestConfig(Config):
    """Testumgebung"""
    SECRET_KEY = 'test-secret-key'
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # In-Memory
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite braucht keine Pool-Optionen
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Produktionsumgebung"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestConfig,
    'default': DevelopmentConfig
}
