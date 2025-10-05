import os
import sys
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import redis
import json
import psutil
import threading
import time
from datetime import datetime

print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
print(f"Connecting to Redis: {REDIS_URL}")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    redis_client.ping()
    print("Successfully connected to Redis")
except Exception as e:
    print(f"ERROR: Failed to connect to Redis: {e}")
    redis_client = None

METRICS_CHANNEL = 'system_metrics'
ALERT_CHANNEL = 'system_alerts'
ALERT_THRESHOLDS = {'cpu': 80, 'memory': 85, 'disk': 90}

class SystemMonitor:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.running = False
        self.metrics_history = []
    
    def collect_metrics(self):
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()
            process_count = len(psutil.pids())
            
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'cpu': {'percent': cpu_percent, 'count': cpu_count},
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': (disk.used / disk.total) * 100
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv
                },
                'processes': process_count
            }
            return metrics
        except Exception as e:
            print(f"Error collecting metrics: {e}")
            return None
    
    def check_alerts(self, metrics):
        alerts = []
        if metrics['cpu']['percent'] > ALERT_THRESHOLDS['cpu']:
            alerts.append({
                'type': 'cpu',
                'severity': 'high',
                'message': f"High CPU usage: {metrics['cpu']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        if metrics['memory']['percent'] > ALERT_THRESHOLDS['memory']:
            alerts.append({
                'type': 'memory',
                'severity': 'high',
                'message': f"High memory usage: {metrics['memory']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        if metrics['disk']['percent'] > ALERT_THRESHOLDS['disk']:
            alerts.append({
                'type': 'disk',
                'severity': 'critical',
                'message': f"High disk usage: {metrics['disk']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        return alerts
    
    def publish_metrics(self):
        self.running = True
        while self.running:
            try:
                if self.redis_client is None:
                    time.sleep(5)
                    continue
                    
                metrics = self.collect_metrics()
                if metrics is None:
                    time.sleep(5)
                    continue
                
                self.metrics_history.append(metrics)
                if len(self.metrics_history) > 100:
                    self.metrics_history.pop(0)
                
                self.redis_client.publish(METRICS_CHANNEL, json.dumps(metrics))
                self.redis_client.setex('latest_metrics', 60, json.dumps(metrics))
                
                key = f"metrics:{int(time.time())}"
                self.redis_client.setex(key, 3600, json.dumps(metrics))
                
                alerts = self.check_alerts(metrics)
                for alert in alerts:
                    self.redis_client.publish(ALERT_CHANNEL, json.dumps(alert))
                    alert_key = f"alert:{int(time.time())}"
                    self.redis_client.setex(alert_key, 3600, json.dumps(alert))
                
                time.sleep(5)
            except Exception as e:
                print(f"Error publishing metrics: {e}")
                time.sleep(5)
    
    def start(self):
        if self.redis_client is not None:
            thread = threading.Thread(target=self.publish_metrics, daemon=True)
            thread.start()
            print("System monitor started")
    
    def stop(self):
        self.running = False

class MetricsSubscriber:
    def __init__(self, redis_client, socketio):
        self.redis_client = redis_client
        self.socketio = socketio
        self.pubsub = None
        self.running = False
    
    def subscribe(self):
        if self.redis_client is None:
            return
            
        try:
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(METRICS_CHANNEL, ALERT_CHANNEL)
            self.running = True
            
            for message in self.pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        channel = message['channel']
                        
                        if channel == METRICS_CHANNEL:
                            self.socketio.emit('metrics_update', data)
                        elif channel == ALERT_CHANNEL:
                            self.socketio.emit('alert_update', data)
                    except Exception as e:
                        print(f"Error processing message: {e}")
        except Exception as e:
            print(f"Error in subscriber: {e}")
    
    def start(self):
        if self.redis_client is not None:
            thread = threading.Thread(target=self.subscribe, daemon=True)
            thread.start()
    
    def stop(self):
        self.running = False
        if self.pubsub:
            self.pubsub.close()

monitor = SystemMonitor(redis_client)
subscriber = MetricsSubscriber(redis_client, socketio)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/metrics/latest')
def get_latest_metrics():
    try:
        if redis_client is None:
            if monitor.metrics_history:
                return jsonify(monitor.metrics_history[-1])
            return jsonify({'error': 'No metrics available'}), 404
            
        metrics = redis_client.get('latest_metrics')
        if metrics:
            return jsonify(json.loads(metrics))
        
        if monitor.metrics_history:
            return jsonify(monitor.metrics_history[-1])
            
        return jsonify({'error': 'No metrics available'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics/history')
def get_metrics_history():
    try:
        if monitor.metrics_history:
            return jsonify(monitor.metrics_history)
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def get_alerts():
    try:
        if redis_client is None:
            return jsonify([])
        
        now = int(time.time())
        hour_ago = now - 3600
        alerts = []
        
        for timestamp in range(hour_ago, now):
            key = f"alert:{timestamp}"
            if redis_client.exists(key):
                alert_data = redis_client.get(key)
                if alert_data:
                    alerts.append(json.loads(alert_data))
        
        return jsonify(alerts[:50])
    except Exception as e:
        return jsonify([])

@app.route('/api/health')
def health_check():
    try:
        if redis_client is None:
            return jsonify({'status': 'degraded', 'redis': 'not configured'}), 503
            
        redis_client.ping()
        return jsonify({
            'status': 'healthy',
            'redis': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'msg': 'Connected to System Monitor'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    monitor.start()
    subscriber.start()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
