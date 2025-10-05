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

# Print Python version and environment info for debugging
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Directory contents: {os.listdir('.')}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Initialize SocketIO with eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=True)

# Redis connection - use environment variable for Render
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
print(f"Connecting to Redis: {REDIS_URL}")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    redis_client.ping()
    print("Successfully connected to Redis")
except Exception as e:
    print(f"ERROR: Failed to connect to Redis: {e}")
    redis_client = None

# Configuration
METRICS_CHANNEL = 'system_metrics'
ALERT_CHANNEL = 'system_alerts'
ALERT_THRESHOLDS = {
    'cpu': 80,
    'memory': 85,
    'disk': 90
}

class SystemMonitor:
    """Publisher: Collects and publishes system metrics"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.running = False
        self.metrics_history = []  # Store history in memory
    
    def collect_metrics(self):
        """Collect system metrics in the format dashboard expects"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()
            process_count = len(psutil.pids())
            
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count
                },
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
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'processes': process_count
            }
            
            return metrics
        except Exception as e:
            print(f"Error collecting metrics: {e}")
            return None
    
    def check_alerts(self, metrics):
        """Check if any metrics exceed thresholds"""
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
        """Continuously publish metrics"""
        self.running = True
        while self.running:
            try:
                if self.redis_client is None:
                    print("Redis client not available, skipping metrics publish")
                    time.sleep(5)
                    continue
                    
                metrics = self.collect_metrics()
                if metrics is None:
                    time.sleep(5)
                    continue
                
                # Add to history (keep last 100 entries)
                self.metrics_history.append(metrics)
                if len(self.metrics_history) > 100:
                    self.metrics_history.pop(0)
                
                # Publish metrics
                self.redis_client.publish(METRICS_CHANNEL, json.dumps(metrics))
                
                # Store latest metrics in Redis with expiration
                self.redis_client.setex('latest_metrics', 60, json.dumps(metrics))
                
                # Store in history with timestamp key
                key = f"metrics:{int(time.time())}"
                self.redis_client.setex(key, 3600, json.dumps(metrics))  # 1 hour expiration
                
                # Check and publish alerts
                alerts = self.check_alerts(metrics)
                if alerts:
                    for alert in alerts:
                        self.redis_client.publish(ALERT_CHANNEL, json.dumps(alert))
                        # Store alert
                        alert_key = f"alert:{int(time.time())}"
                        self.redis_client.setex(alert_key, 3600, json.dumps(alert))
                
                time.sleep(5)  # Publish every 5 seconds
            except Exception as e:
                print(f"Error publishing metrics: {e}")
                time.sleep(5)
    
    def start(self):
        """Start monitoring in background thread"""
        if self.redis_client is not None:
            thread = threading.Thread(target=self.publish_metrics, daemon=True)
            thread.start()
            print("System monitor started")
        else:
            print("Cannot start monitor: Redis not available")
    
    def stop(self):
        """Stop monitoring"""
        self.running = False

class MetricsSubscriber:
    """Subscriber: Receives and broadcasts metrics via WebSocket"""
    
    def __init__(self, redis_client, socketio):
        self.redis_client = redis_client
        self.socketio = socketio
        self.pubsub = None
        self.running = False
    
    def subscribe(self):
        """Subscribe to metrics and alerts"""
        if self.redis_client is None:
            print("Cannot subscribe: Redis not available")
            return
            
        try:
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(METRICS_CHANNEL, ALERT_CHANNEL)
            self.running = True
            print("Subscriber started, listening for messages...")
            
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
        """Start subscribing in background thread"""
        if self.redis_client is not None:
            thread = threading.Thread(target=self.subscribe, daemon=True)
            thread.start()
            print("Metrics subscriber started")
        else:
            print("Cannot start subscriber: Redis not available")
    
    def stop(self):
        """Stop subscribing"""
        self.running = False
        if self.pubsub:
            self.pubsub.close()

# Initialize monitor and subscriber
monitor = SystemMonitor(redis_client)
subscriber = MetricsSubscriber(redis_client, socketio)

@app.route('/')
def index():
    """Serve the dashboard"""
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error rendering template: {e}")
        return f"""
        <html>
        <head><title>Distributed System Monitor</title></head>
        <body>
            <h1>Distributed System Monitor</h1>
            <p>Error loading dashboard: {str(e)}</p>
            <hr>
            <p>API Endpoints:</p>
            <ul>
                <li><a href="/api/health">/api/health</a> - Health check</li>
                <li><a href="/api/metrics/latest">/api/metrics/latest</a> - Latest metrics</li>
                <li><a href="/api/metrics/history">/api/metrics/history</a> - Metrics history</li>
                <li><a href="/api/alerts">/api/alerts</a> - Recent alerts</li>
            </ul>
        </body>
        </html>
        """, 200

@app.route('/api/metrics/current')
def get_current_metrics():
    """Get latest metrics (alias)"""
    return get_latest_metrics()

@app.route('/api/metrics/latest')
def get_latest_metrics():
    """Get latest metrics"""
    try:
        if redis_client is None:
            return jsonify({'error': 'Redis not available'}), 503
            
        metrics = redis_client.get('latest_metrics')
        if metrics:
            return jsonify(json.loads(metrics))
        
        # Fallback to in-memory history
        if monitor.metrics_history:
            return jsonify(monitor.metrics_history[-1])
            
        return jsonify({'error': 'No metrics available'}), 404
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics/history')
def get_metrics_history():
    """Get historical metrics data"""
    try:
        if redis_client is None:
            # Return in-memory history
            return jsonify(monitor.metrics_history)
        
        # Get last hour of data from Redis
        now = int(time.time())
        hour_ago = now - 3600
        
        metrics_list = []
        for timestamp in range(hour_ago, now, 60):  # Every minute
            key = f"metrics:{timestamp}"
            if redis_client.exists(key):
                metrics_data = redis_client.get(key)
                if metrics_data:
                    metrics_list.append(json.loads(metrics_data))
        
        # If no Redis data, return in-memory history
        if not metrics_list and monitor.metrics_history:
            return jsonify(monitor.metrics_history)
        
        return jsonify(metrics_list)
        
    except Exception as e:
        print(f"Error getting metrics history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def get_alerts():
    """Get recent alerts"""
    try:
        if redis_client is None:
            return jsonify([]), 200
        
        # Get alerts from last hour
        now = int(time.time())
        hour_ago = now - 3600
        
        alerts = []
        for timestamp in range(hour_ago, now):
            key = f"alert:{timestamp}"
            if redis_client.exists(key):
                alert_data = redis_client.get(key)
                if alert_data:
                    alerts.append(json.loads(alert_data))
        
        # Sort by timestamp (most recent first)
        alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(alerts[:50])  # Return last 50 alerts
        
    except Exception as e:
        print(f"Error getting alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        if redis_client is None:
            return jsonify({
                'status': 'degraded',
                'redis': 'not configured',
                'timestamp': datetime.utcnow().isoformat(),
                'message': 'Redis connection not available'
            }), 503
            
        redis_client.ping()
        return jsonify({
            'status': 'healthy',
            'redis': 'connected',
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'redis': 'connected',
                'publisher': 'running' if monitor.running else 'stopped',
                'subscriber': 'running' if subscriber.running else 'stopped'
            }
        })
    except Exception as e:
        print(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'redis': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status', {'msg': 'Connected to System Monitor'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('request_metrics')
def handle_metrics_request():
    """Handle manual metrics request"""
    try:
        if redis_client is None:
            emit('error', {'message': 'Redis not available'})
            return
            
        metrics = redis_client.get('latest_metrics')
        if metrics:
            emit('metrics_update', json.loads(metrics))
        elif monitor.metrics_history:
            emit('metrics_update', monitor.metrics_history[-1])
        else:
            emit('error', {'message': 'No metrics available'})
    except Exception as e:
        print(f"Error handling metrics request: {e}")
        emit('error', {'message': str(e)})

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    print(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

if __name__ == '__main__':
    print("Starting Distributed System Monitor...")
    
    # Start monitoring and subscription
    monitor.start()
    subscriber.start()
    
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    print(f"Dashboard will be available at: http://0.0.0.0:{port}")
    
    # Run with eventlet
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
