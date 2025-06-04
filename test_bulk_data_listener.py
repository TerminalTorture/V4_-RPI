#!/usr/bin/env python3
"""
VFlow Bulk Data Listener Test - Listen for bulk data messages on vflow/data/bulk
"""

import os
import sys
import json
import time
import signal
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print("✅ Environment variables loaded")
except ImportError:
    print("⚠️ python-dotenv not available")

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("❌ paho-mqtt not installed. Install with: pip install paho-mqtt")
    sys.exit(1)

class BulkDataListener:
    def __init__(self):
        self.broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        self.broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        self.username = os.getenv('MQTT_USERNAME')
        self.password = os.getenv('MQTT_PASSWORD')
        self.base_topic = os.getenv('MQTT_BASE_TOPIC', 'vflow')
        
        self.bulk_topic = f"{self.base_topic}/data/bulk"
        self.messages_received = 0
        self.running = False
        
        print(f"🎯 Target Topic: {self.bulk_topic}")
        print(f"📡 Broker: {self.broker_host}:{self.broker_port}")
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            print(f"✅ Connected to MQTT broker")
            client.subscribe(self.bulk_topic, 1)
            print(f"📡 Subscribed to: {self.bulk_topic}")
            print("🎧 Listening for bulk data messages...")
            print("=" * 60)
        else:
            print(f"❌ Failed to connect. Reason code: {reason_code}")
    
    def on_message(self, client, userdata, msg):
        try:
            self.messages_received += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"\n📨 Message #{self.messages_received} at {timestamp}")
            print(f"📍 Topic: {msg.topic}")
            
            # Parse and display JSON
            try:
                data = json.loads(msg.payload.decode('utf-8'))
                print("📄 Message content:")
                print(json.dumps(data, indent=2))
                
                # Key info
                device_id = data.get('device_id', 'Unknown')
                msg_timestamp = data.get('timestamp', 'No timestamp')
                print(f"\n🔍 Device ID: {device_id}")
                print(f"🕒 Message Timestamp: {msg_timestamp}")
                
                if 'data' in data:
                    sensor_count = len(data['data'])
                    print(f"📊 Sensor count: {sensor_count}")
                
                print("=" * 60)
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {e}")
                
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    def start_listening(self, duration=None):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, 
                           client_id=f"bulk_listener_{int(time.time())}")
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        
        if self.username and self.password:
            client.username_pw_set(self.username, self.password)
        
        try:
            print(f"🚀 Starting listener...")
            if duration:
                print(f"⏱️ Duration: {duration} seconds")
            
            client.connect(self.broker_host, self.broker_port, 60)
            client.loop_start()
            
            self.running = True
            start_time = time.time()
            
            while self.running:
                if duration and (time.time() - start_time) >= duration:
                    break
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print(f"\n⚠️ Stopped by user")
        finally:
            client.loop_stop()
            client.disconnect()
            print(f"\n📊 Total messages received: {self.messages_received}")

def main():
    print("🎧 VFlow Bulk Data Listener")
    print("=" * 40)
    
    duration = None
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            pass
    
    listener = BulkDataListener()
    listener.start_listening(duration)

if __name__ == "__main__":
    main()