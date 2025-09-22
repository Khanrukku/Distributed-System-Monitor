import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Redis Configuration
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Monitoring Configuration
    METRICS_INTERVAL = int(os.getenv('METRICS_INTERVAL', 5))  # seconds
    ALERT_THRESHOLD_CPU = float(os.getenv('ALERT_THRESHOLD_CPU', 80.0))
    ALERT_THRESHOLD_MEMORY = float(os.getenv('ALERT_THRESHOLD_MEMORY', 80.0))
    ALERT_THRESHOLD_DISK = float(os.getenv('ALERT_THRESHOLD_DISK', 90.0))
    
    # Channels
    METRICS_CHANNEL = 'system_metrics'
    ALERTS_CHANNEL = 'system_alerts'