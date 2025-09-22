import redis
import json
import threading
from config import Config

class SystemMetricsSubscriber:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        self.subscribers = {
            'metrics': [],
            'alerts': []
        }
        self.running = False
        
    def subscribe_to_channels(self):
        """Subscribe to Redis channels"""
        self.pubsub.subscribe(Config.METRICS_CHANNEL, Config.ALERTS_CHANNEL)
        
    def add_metrics_subscriber(self, callback):
        """Add a callback for metrics updates"""
        self.subscribers['metrics'].append(callback)
        
    def add_alerts_subscriber(self, callback):
        """Add a callback for alerts"""
        self.subscribers['alerts'].append(callback)
        
    def remove_subscriber(self, callback):
        """Remove a subscriber callback"""
        for subscriber_list in self.subscribers.values():
            if callback in subscriber_list:
                subscriber_list.remove(callback)
    
    def handle_message(self, message):
        """Handle incoming messages"""
        try:
            if message['type'] == 'message':
                data = json.loads(message['data'])
                channel = message['channel']
                
                if channel == Config.METRICS_CHANNEL:
                    # Notify metrics subscribers
                    for callback in self.subscribers['metrics']:
                        try:
                            callback(data)
                        except Exception as e:
                            print(f"Error in metrics callback: {e}")
                
                elif channel == Config.ALERTS_CHANNEL:
                    # Notify alert subscribers
                    for callback in self.subscribers['alerts']:
                        try:
                            callback(data)
                        except Exception as e:
                            print(f"Error in alert callback: {e}")
                            
        except Exception as e:
            print(f"Error handling message: {e}")
    
    def listen(self):
        """Listen for messages"""
        while self.running:
            try:
                message = self.pubsub.get_message(timeout=1.0)
                if message:
                    self.handle_message(message)
            except Exception as e:
                print(f"Error listening for messages: {e}")
                break
    
    def start(self):
        """Start the subscriber"""
        self.running = True
        self.subscribe_to_channels()
        self.thread = threading.Thread(target=self.listen)
        self.thread.daemon = True
        self.thread.start()
        print("Subscriber started")
    
    def stop(self):
        """Stop the subscriber"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join()
        self.pubsub.close()
        print("Subscriber stopped")

# Global subscriber instance
subscriber = SystemMetricsSubscriber()