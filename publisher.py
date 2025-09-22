import redis
import psutil
import json
import time
import threading
from datetime import datetime
from config import Config

class SystemMetricsPublisher:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            decode_responses=True
        )
        self.running = False
        
    def get_system_metrics(self):
        """Collect system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Network metrics
            network = psutil.net_io_counters()
            
            # Process count
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
        """Check for alert conditions"""
        alerts = []
        
        # CPU Alert
        if metrics['cpu']['percent'] > Config.ALERT_THRESHOLD_CPU:
            alerts.append({
                'type': 'cpu',
                'severity': 'high',
                'message': f"High CPU usage: {metrics['cpu']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        
        # Memory Alert
        if metrics['memory']['percent'] > Config.ALERT_THRESHOLD_MEMORY:
            alerts.append({
                'type': 'memory',
                'severity': 'high',
                'message': f"High memory usage: {metrics['memory']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        
        # Disk Alert
        if metrics['disk']['percent'] > Config.ALERT_THRESHOLD_DISK:
            alerts.append({
                'type': 'disk',
                'severity': 'critical',
                'message': f"High disk usage: {metrics['disk']['percent']:.1f}%",
                'timestamp': metrics['timestamp']
            })
        
        return alerts
    
    def publish_metrics(self):
        """Publish metrics to Redis"""
        while self.running:
            try:
                metrics = self.get_system_metrics()
                if metrics:
                    # Publish to metrics channel
                    self.redis_client.publish(Config.METRICS_CHANNEL, json.dumps(metrics))
                    
                    # Store in Redis with expiration (24 hours)
                    key = f"metrics:{int(time.time())}"
                    self.redis_client.setex(key, 86400, json.dumps(metrics))
                    
                    # Check for alerts
                    alerts = self.check_alerts(metrics)
                    for alert in alerts:
                        self.redis_client.publish(Config.ALERTS_CHANNEL, json.dumps(alert))
                        # Store alert
                        alert_key = f"alert:{int(time.time())}"
                        self.redis_client.setex(alert_key, 86400, json.dumps(alert))
                    
                    print(f"Published metrics at {metrics['timestamp']}")
                
            except Exception as e:
                print(f"Error publishing metrics: {e}")
            
            time.sleep(Config.METRICS_INTERVAL)
    
    def start(self):
        """Start publishing metrics"""
        self.running = True
        self.thread = threading.Thread(target=self.publish_metrics)
        self.thread.daemon = True
        self.thread.start()
        print("Metrics publisher started")
    
    def stop(self):
        """Stop publishing metrics"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join()
        print("Metrics publisher stopped")

if __name__ == "__main__":
    publisher = SystemMetricsPublisher()
    try:
        publisher.start()
        print("Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        publisher.stop()