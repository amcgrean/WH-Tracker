import os
from datetime import timedelta
from app.runtime_settings import env_bool, get_database_url, get_sqlalchemy_engine_options, is_fly_runtime, load_tracker_env

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

    # Sessions stay alive for 7 days after last activity
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    # Prevent session cookie being sent over plain HTTP in production
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE",
                                     bool(os.environ.get("VERCEL")) or is_fly_runtime())
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Authentication feature flag — set AUTH_REQUIRED=true to enforce login on all routes
    AUTH_REQUIRED = env_bool("AUTH_REQUIRED", False)

    # Credit / RMA image uploads — stored on local disk; path relative to project root
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads/credits')

    # Cloudflare R2 object storage (S3-compatible)
    # Used by both the file storage feature and PO check-in photo uploads.
    R2_ENDPOINT_URL      = os.environ.get('R2_ENDPOINT_URL', '')
    R2_ACCESS_KEY_ID     = os.environ.get('R2_ACCESS_KEY_ID', '')
    R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
    R2_BUCKET            = os.environ.get('R2_BUCKET', 'wh-tracker-files')      # general file storage
    R2_BUCKET_NAME       = os.environ.get('R2_BUCKET_NAME', 'po-checkin-photos') # PO check-in photos
    R2_PUBLIC_URL        = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')       # public base URL

    # Estimating app integration
    # URL of the beisser-takeoff / LiveEdge estimating module.  Set via Fly
    # secret ESTIMATING_APP_URL once the unified domain is live.
    ESTIMATING_APP_URL = os.environ.get('ESTIMATING_APP_URL', '#')

    # Shared secret used by the estimating app (and other internal services)
    # to call WH-Tracker API endpoints without a user session.
    # Set via Fly secret INTERNAL_API_KEY.  An empty string disables key auth.
    INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', '')

    require_strong_secret = env_bool(
        "REQUIRE_STRONG_SECRET_KEY",
        bool(os.environ.get("VERCEL")) or is_fly_runtime(),
    )
    if require_strong_secret:
        if SECRET_KEY == 'dev_default_secret_key_12345':
            raise RuntimeError('SECRET_KEY must be set when REQUIRE_STRONG_SECRET_KEY is enabled.')
        if len(SECRET_KEY) < 32:
            raise RuntimeError('SECRET_KEY must be at least 32 characters when REQUIRE_STRONG_SECRET_KEY is enabled.')

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = True

class ProductionConfig(Config):
    DEBUG = False
    # SQLALCHEMY_DATABASE_URI is handled by Config base check or env var override
