from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import redis
import json
from datetime import datetime, timedelta
from config import Config
from subscriber import subscriber
from publisher import SystemMetricsPublisher

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Redis client
redis_client = redis.Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    password=Config.REDIS_PASSWORD,
    decode_responses=True
)

# Initialize publisher
publisher = SystemMetricsPublisher()

# Callback functions for subscriber
def on_metrics_update(data):
    """Handle metrics updates"""
    socketio.emit('metrics_update', data)

def on_alert_update(data):
    """Handle alert updates"""
    socketio.emit('alert_update', data)

@app.route('/')
def dashboard():
    """Render the main dashboard"""
    return render_template('dashboard.html')

@app.route('/api/metrics/latest')
def get_latest_metrics():
    """Get the latest system metrics"""
    try:
        # Get keys for recent metrics (last hour)
        now = int(datetime.utcnow().timestamp())
        hour_ago = now - 3600
        
        keys = []
        for timestamp in range(hour_ago, now, Config.METRICS_INTERVAL):
            key = f"metrics:{timestamp}"
            if redis_client.exists(key):
                keys.append(key)
        
        # Get the most recent metrics
        if keys:
            latest_key = max(keys)
            metrics_data = redis_client.get(latest_key)
            if metrics_data:
                return jsonify(json.loads(metrics_data))
        
        return jsonify({'error': 'No metrics available'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics/history')
def get_metrics_history():
    """Get historical metrics data"""
    try:
        # Get last 24 hours of data
        now = int(datetime.utcnow().timestamp())
        day_ago = now - 86400
        
        metrics_list = []
        for timestamp in range(day_ago, now, Config.METRICS_INTERVAL * 12):  # Every minute
            key = f"metrics:{timestamp}"
            if redis_client.exists(key):
                metrics_data = redis_client.get(key)
                if metrics_data:
                    metrics_list.append(json.loads(metrics_data))
        
        return jsonify(metrics_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def get_alerts():
    """Get recent alerts"""
    try:
        # Get alerts from last 24 hours
        now = int(datetime.utcnow().timestamp())
        day_ago = now - 86400
        
        alerts = []
        for timestamp in range(day_ago, now):
            key = f"alert:{timestamp}"
            if redis_client.exists(key):
                alert_data = redis_client.get(key)
                if alert_data:
                    alerts.append(json.loads(alert_data))
        
        # Sort by timestamp (most recent first)
        alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(alerts[:50])  # Return last 50 alerts
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        # Check Redis connection
        redis_client.ping()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'redis': 'connected',
                'publisher': 'running' if publisher.running else 'stopped',
                'subscriber': 'running' if subscriber.running else 'stopped'
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status', {'msg': 'Connected to System Monitor'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

def initialize_services():
    """Initialize all services"""
    # Start subscriber
    subscriber.add_metrics_subscriber(on_metrics_update)
    subscriber.add_alerts_subscriber(on_alert_update)
    subscriber.start()
    
    # Start publisher
    publisher.start()

if __name__ == '__main__':
    try:
        initialize_services()
        print("Starting Distributed System Monitor...")
        print(f"Dashboard available at: http://localhost:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=Config.DEBUG)
    except KeyboardInterrupt:
        print("Shutting down...")
        publisher.stop()
        subscriber.stop()