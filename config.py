import os
from app.runtime_settings import get_central_db_url, get_database_url, load_tracker_env

basedir = os.path.abspath(os.path.dirname(__file__))
load_tracker_env()

class Config(object):
    SQLALCHEMY_DATABASE_URI = get_database_url() or \
        'sqlite:///' + os.path.join('/tmp', 'picker.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Optional central database connection (beisser-api sync DB)
    # If not provided, it will gracefully fallback in the services.
    central_db_url = get_central_db_url()
        
    SQLALCHEMY_BINDS = {}
    if central_db_url:
        SQLALCHEMY_BINDS['central_db'] = central_db_url
    
    # Required for Flask sessions and flash messages
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_default_secret_key_12345')

    # Credit / RMA image uploads — stored on local disk; path relative to project root
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads/credits')

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = True

class ProductionConfig(Config):
    DEBUG = False
    # SQLALCHEMY_DATABASE_URI is handled by Config base check or env var override

