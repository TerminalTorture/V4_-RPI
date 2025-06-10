#!/usr/bin/env python3
"""
Simple MQTT test to verify connection and topics
"""
import paho.mqtt.client as mqtt
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    if rc == 0:
        # Subscribe to all vflow topics
        client.subscribe("vflow/#", 0)
        print("Subscribed to vflow/#")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    print(f"Topic: {msg.topic}")
    try:
        payload = msg.payload.decode('utf-8')
        # Try to parse as JSON for better formatting
        try:
            data = json.loads(payload)
            print(f"Data: {json.dumps(data, indent=2)}")
        except json.JSONDecodeError:
            print(f"Raw payload: {payload}")
    except UnicodeDecodeError:
        print(f"Binary payload: {msg.payload}")
    print("-" * 50)

def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code {rc}")

# Create MQTT client
client = mqtt.Client(client_id="vflow_test_client")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Get broker details from environment
broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))

print(f"Connecting to MQTT broker: {broker_host}:{broker_port}")

try:
    client.connect(broker_host, broker_port, 60)
    client.loop_start()
    
    print("Listening for MQTT messages... Press Ctrl+C to stop")
    while True:
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\nStopping...")
except Exception as e:
    print(f"Error: {e}")
finally:
    client.loop_stop()
    client.disconnect()
