from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import redis
import json
from datetime import datetime, timedelta
from config import Config
from subscriber import subscriber
from publisher import SystemMetricsPublisher

app = Flask(__name__)
app.config.from_object(Config)

socketio = SocketIO(app, cors_allowed_origins="*")

redis_client = redis.Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    password=Config.REDIS_PASSWORD,
    decode_responses=True
)

publisher = SystemMetricsPublisher()

def on_metrics_update(data):
    socketio.emit('metrics_update', data)

def on_alert_update(data):
    socketio.emit('alert_update', data)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/metrics/latest')
def get_latest_metrics():
    try:
        now = int(datetime.utcnow().timestamp())
        hour_ago = now - 3600
        
        keys = []
        for timestamp in range(hour_ago, now, Config.METRICS_INTERVAL):
            key = f"metrics:{timestamp}"
            if redis_client.exists(key):
                keys.append(key)
        
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
    try:
        now = int(datetime.utcnow().timestamp())
        day_ago = now - 86400
        
        metrics_list = []
        for timestamp in range(day_ago, now, Config.METRICS_INTERVAL * 12):
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
    try:
        now = int(datetime.utcnow().timestamp())
        day_ago = now - 86400
        
        alerts = []
        for timestamp in range(day_ago, now):
            key = f"alert:{timestamp}"
            if redis_client.exists(key):
                alert_data = redis_client.get(key)
                if alert_data:
                    alerts.append(json.loads(alert_data))
        
        alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(alerts[:50])
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    try:
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
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'msg': 'Connected to System Monitor'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

def initialize_services():
    subscriber.add_metrics_subscriber(on_metrics_update)
    subscriber.add_alerts_subscriber(on_alert_update)
    subscriber.start()
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
