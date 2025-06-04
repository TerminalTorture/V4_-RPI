#!/usr/bin/env python3
import os, sys, json, time
from datetime import datetime
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

load_dotenv()

broker = os.getenv('MQTT_BROKER_HOST', 'localhost')
port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
username = os.getenv('MQTT_USERNAME')
password = os.getenv('MQTT_PASSWORD')
base_topic = os.getenv('MQTT_BASE_TOPIC', 'vflow')

messages_received = 0

def on_connect(client, userdata, flags, reason_code, properties=None):
    global messages_received
    if reason_code == 0:
        print(f"✅ Connected with auth: {username}")
        # Subscribe to multiple topic patterns
        topics = [
            f"{base_topic}/data/bulk",
            f"{base_topic}/sensors/+", 
            f"{base_topic}/status",
            f"{base_topic}/#"  # All subtopics
        ]
        for topic in topics:
            client.subscribe(topic, 1)
            print(f"📡 Subscribed: {topic}")
        print("🎧 Listening for ALL vflow messages...")
        print("=" * 60)
    else:
        print(f"❌ Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    global messages_received
    messages_received += 1
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    print(f"\n📨 #{messages_received} at {timestamp}")
    print(f"📍 Topic: {msg.topic}")
    print(f"📦 QoS: {msg.qos}, Size: {len(msg.payload)} bytes")
    
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        print("📄 JSON Data:")
        print(json.dumps(data, indent=2)[:500] + ("..." if len(str(data)) > 500 else ""))
        
        if isinstance(data, dict):
            device_id = data.get('device_id', 'Unknown')
            msg_ts = data.get('timestamp', 'No timestamp')
            print(f"🔍 Device: {device_id}")
            print(f"🕒 Timestamp: {msg_ts}")
            
            if 'data' in data:
                print(f"📊 Sensors: {len(data['data'])}")
    except:
        print(f"📄 Raw: {msg.payload}")
    
    print("=" * 60)

print(f"🔍 Enhanced MQTT Diagnostic Listener")
print(f"📡 Broker: {broker}:{port}")
print(f"🔐 User: {username}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"diagnostic_{int(time.time())}")
client.on_connect = on_connect
client.on_message = on_message

if username and password:
    client.username_pw_set(username, password)

try:
    client.connect(broker, port, 60)
    client.loop_start()
    
    # Listen for 60 seconds
    time.sleep(60)
    
except KeyboardInterrupt:
    print("\n⚠️ Stopped by user")
finally:
    client.loop_stop()
    client.disconnect()
    print(f"\n📊 Total messages: {messages_received}")
