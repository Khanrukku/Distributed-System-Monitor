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
    
    def collect_metrics(self):
        """Collect system metrics"""
        try:
            return {
                'timestamp': datetime.now().isoformat(),
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'network_sent': psutil.net_io_counters().bytes_sent,
                'network_recv': psutil.net_io_counters().bytes_recv
            }
        except Exception as e:
            print(f"Error collecting metrics: {e}")
            return None
    
    def check_alerts(self, metrics):
        """Check if any metrics exceed thresholds"""
        alerts = []
        if metrics['cpu_percent'] > ALERT_THRESHOLDS['cpu']:
            alerts.append(f"HIGH CPU: {metrics['cpu_percent']:.1f}%")
        if metrics['memory_percent'] > ALERT_THRESHOLDS['memory']:
            alerts.append(f"HIGH MEMORY: {metrics['memory_percent']:.1f}%")
        if metrics['disk_percent'] > ALERT_THRESHOLDS['disk']:
            alerts.append(f"HIGH DISK: {metrics['disk_percent']:.1f}%")
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
                
                # Publish metrics
                self.redis_client.publish(METRICS_CHANNEL, json.dumps(metrics))
                
                # Store in Redis with expiration
                self.redis_client.setex(
                    'latest_metrics',
                    60,  # 60 seconds expiration
                    json.dumps(metrics)
                )
                
                # Check and publish alerts
                alerts = self.check_alerts(metrics)
                if alerts:
                    alert_data = {
                        'timestamp': metrics['timestamp'],
                        'alerts': alerts
                    }
                    self.redis_client.publish(ALERT_CHANNEL, json.dumps(alert_data))
                
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
                            self.socketio.emit('alert', data)
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
        # Check if templates directory exists
        template_dir = os.path.join(os.getcwd(), 'templates')
        if not os.path.exists(template_dir):
            return f"""
            <html>
            <head><title>Distributed System Monitor</title></head>
            <body>
                <h1>Distributed System Monitor</h1>
                <p>Error: Templates directory not found</p>
                <p>Current directory: {os.getcwd()}</p>
                <p>Looking for: {template_dir}</p>
                <p>Directory contents: {os.listdir('.')}</p>
                <hr>
                <p>API Endpoints:</p>
                <ul>
                    <li><a href="/api/health">/api/health</a> - Health check</li>
                    <li><a href="/api/metrics/current">/api/metrics/current</a> - Current metrics</li>
                </ul>
            </body>
            </html>
            """, 200
        
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
                <li><a href="/api/metrics/current">/api/metrics/current</a> - Current metrics</li>
            </ul>
        </body>
        </html>
        """, 200

@app.route('/api/metrics/current')
def get_current_metrics():
    """Get latest metrics"""
    try:
        if redis_client is None:
            return jsonify({'error': 'Redis not available'}), 503
            
        metrics = redis_client.get('latest_metrics')
        if metrics:
            return jsonify(json.loads(metrics))
        return jsonify({'error': 'No metrics available'}), 404
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        if redis_client is None:
            return jsonify({
                'status': 'degraded',
                'redis': 'not configured',
                'timestamp': datetime.now().isoformat(),
                'message': 'Redis connection not available'
            }), 503
            
        redis_client.ping()
        return jsonify({
            'status': 'healthy',
            'redis': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'redis': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('connected', {'status': 'Connected to monitoring system'})

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
    
    # Run with eventlet
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
