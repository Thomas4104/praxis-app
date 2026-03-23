import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Basis-Konfiguration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI', 'sqlite:///praxis.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False  # Temporär deaktiviert bis HTTPS eingerichtet
    APP_NAME = 'OMNIA Praxissoftware'
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')


class DevelopmentConfig(Config):
    """Entwicklungsumgebung"""
    DEBUG = True


class ProductionConfig(Config):
    """Produktionsumgebung"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
