"""
config.py - Application Configuration
Handles all environment-specific configuration using .env file.
"""
import os
import secrets
from dotenv import load_dotenv

# MAIL_PASSWORD is intentionally captured before dotenv loading so it must come
# from the real process environment, not .env or .env.production files.
SYSTEM_MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration class."""

    # -----------------------------------------------------------
    # Security
    # -----------------------------------------------------------
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Must be set in .env

    # -----------------------------------------------------------
    # Database
    # -----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Enable WAL mode for safer concurrent writes on SQLite
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},
        'pool_pre_ping': True,
    }

    # -----------------------------------------------------------
    # File Uploads
    # -----------------------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max request size
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
    MAX_FILES_PER_REQUEST = 10
    MAX_FILE_SIZE_MB = 5

    # -----------------------------------------------------------
    # Export / Backup paths
    # -----------------------------------------------------------
    EXPORT_FOLDER = os.path.join(BASE_DIR, 'exports')
    BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
    LOG_FOLDER = os.path.join(BASE_DIR, 'logs')

    # -----------------------------------------------------------
    # Email (optional)
    # -----------------------------------------------------------
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = SYSTEM_MAIL_PASSWORD
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    # -----------------------------------------------------------
    # Pagination
    # -----------------------------------------------------------
    ITEMS_PER_PAGE = 20

    # -----------------------------------------------------------
    # Backup protection token
    # -----------------------------------------------------------
    BACKUP_TOKEN = os.environ.get('BACKUP_TOKEN')  # Must be set in .env

    # -----------------------------------------------------------
    # Logging
    # -----------------------------------------------------------
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'ERROR')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    LOG_LEVEL = 'ERROR'
    SESSION_COOKIE_SECURE = True      # Only send cookie over HTTPS
    SESSION_COOKIE_HTTPONLY = True    # Block JS access to session cookie
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour session timeout

    @classmethod
    def init_app(cls, app):
        """Validate required secrets are present at startup."""
        if not cls.SECRET_KEY:
            raise RuntimeError(
                'SECRET_KEY is not set. Add it to your .env file.\n'
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if not cls.BACKUP_TOKEN:
            raise RuntimeError('BACKUP_TOKEN is not set. Add it to your .env file.')


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
