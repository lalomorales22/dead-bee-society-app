import os

class Config:
    SECRET_KEY = os.urandom(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Add these lines for more detailed database configuration
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
