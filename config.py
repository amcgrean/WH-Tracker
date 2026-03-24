import os
from app.runtime_settings import get_database_url, get_sqlalchemy_engine_options, load_tracker_env

basedir = os.path.abspath(os.path.dirname(__file__))
load_tracker_env()

class Config(object):
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError('DATABASE_URL is required for WH-Tracker runtime.')
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = get_sqlalchemy_engine_options(database_url)
    
    # Required for Flask sessions and flash messages
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_default_secret_key_12345')

    # Credit / RMA image uploads — stored on local disk; path relative to project root
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads/credits')

    if os.environ.get('VERCEL'):
        if SECRET_KEY == 'dev_default_secret_key_12345':
            raise RuntimeError('SECRET_KEY must be set for Vercel/serverless deployments.')

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = True

class ProductionConfig(Config):
    DEBUG = False
    # SQLALCHEMY_DATABASE_URI is handled by Config base check or env var override
