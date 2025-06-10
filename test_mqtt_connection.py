#!/usr/bin/env python3
"""
Script to test MQTT broker connectivity and monitor incoming messages
"""

import os
import paho.mqtt.client as mqtt
import json
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MQTT configuration from .env
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', 'localhost')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))
MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', 'vflow_sensor_client')
MQTT_BASE_TOPIC = os.getenv('MQTT_BASE_TOPIC', 'vflow')

# Global variables for tracking
message_count = 0
connection_status = False

def on_connect(client, userdata, flags, rc):
    global connection_status
    if rc == 0:
        connection_status = True
        print(f"✅ Connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        print(f"Client ID: {MQTT_CLIENT_ID}")
        
        # Subscribe to all vflow topics
        topics_to_subscribe = [
            "vflow/data/bulk",
            "vflow/sensors/+",
            "vflow/status",
            "vflow/+",
            "#"  # Subscribe to all topics for debugging
        ]
        
        for topic in topics_to_subscribe:
            client.subscribe(topic, qos=0)
            print(f"📡 Subscribed to topic: {topic}")
            
    else:
        connection_status = False
        print(f"❌ Failed to connect to MQTT broker. Return code: {rc}")
        error_messages = {
            1: "Connection refused - incorrect protocol version",
            2: "Connection refused - invalid client identifier",
            3: "Connection refused - server unavailable",
            4: "Connection refused - bad username or password",
            5: "Connection refused - not authorised"
        }
        if rc in error_messages:
            print(f"   {error_messages[rc]}")

def on_message(client, userdata, msg):
    global message_count
    message_count += 1
    
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        print(f"\n📨 Message #{message_count}")
        print(f"   Topic: {topic}")
        print(f"   QoS: {msg.qos}")
        print(f"   Retain: {msg.retain}")
        print(f"   Payload length: {len(payload)} bytes")
        
        # Try to parse as JSON
        try:
            data = json.loads(payload)
            print(f"   JSON Data: {json.dumps(data, indent=2)}")
        except json.JSONDecodeError:
            print(f"   Raw Payload: {payload}")
            
    except Exception as e:
        print(f"❌ Error processing message #{message_count}: {e}")

def on_disconnect(client, userdata, rc):
    global connection_status
    connection_status = False
    if rc != 0:
        print(f"⚠️ Unexpected disconnection from MQTT broker (code: {rc})")
    else:
        print("🔌 Disconnected from MQTT broker")

def on_subscribe(client, userdata, mid, granted_qos):
    print(f"✅ Subscription confirmed (Message ID: {mid}, QoS: {granted_qos})")

def test_mqtt_connection():
    """Test MQTT broker connection and monitor for messages"""
    print("🔧 Testing MQTT Connection...")
    print(f"Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    print(f"Client ID: {MQTT_CLIENT_ID}")
    print("=" * 60)
    
    # Create MQTT client
    client = mqtt.Client(client_id=f"{MQTT_CLIENT_ID}_test_{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe
    
    try:
        print("🚀 Attempting to connect to MQTT broker...")
        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        
        print("📡 Starting message loop...")
        print("⏱️ Listening for messages for 30 seconds...")
        print("   (Press Ctrl+C to stop early)")
        print("-" * 60)
        
        # Run for 30 seconds to check for incoming messages
        start_time = time.time()
        duration = 30
        
        client.loop_start()
        
        while time.time() - start_time < duration:
            if not connection_status:
                print("❌ Lost connection to MQTT broker")
                break
            time.sleep(1)
            
            # Show periodic status
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0 and elapsed > 0:
                print(f"⏱️ {elapsed}s elapsed - {message_count} messages received so far...")
        
        print("-" * 60)
        print(f"🏁 Test completed!")
        print(f"📊 Total messages received: {message_count}")
        
        if message_count == 0:
            print("⚠️ No messages received. Possible issues:")
            print("   - MQTT broker is not running")
            print("   - No publishers are sending data")
            print("   - Firewall blocking connection")
            print("   - Wrong broker address/port")
        else:
            print(f"✅ MQTT broker is working - received {message_count} messages")
            
        client.loop_stop()
        client.disconnect()
        
    except ConnectionRefusedError:
        print(f"❌ Connection refused by MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        print("   Check if the broker is running and accessible")
    except Exception as e:
        print(f"❌ Error connecting to MQTT broker: {e}")

def send_test_message():
    """Send a test message to verify the broker accepts publications"""
    print("\n🧪 Sending test message...")
    try:
        test_client = mqtt.Client(client_id=f"{MQTT_CLIENT_ID}_publisher_{int(time.time())}")
        test_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        
        test_data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "device_id": "test_device",
            "data": {
                "test_value": 42,
                "message": "Test message from test script"
            }
        }
        
        topic = "vflow/data/bulk"
        payload = json.dumps(test_data)
        
        result = test_client.publish(topic, payload, qos=0)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"✅ Test message sent to topic: {topic}")
        else:
            print(f"❌ Failed to send test message (code: {result.rc})")
            
        test_client.disconnect()
        
    except Exception as e:
        print(f"❌ Error sending test message: {e}")

if __name__ == "__main__":
    # Test connection and listen for messages
    test_mqtt_connection()
    
    # Send a test message
    send_test_message()
    
    print("\n" + "=" * 60)
    print("💡 Next steps if no messages were received:")
    print("   1. Check if MQTT broker is running on the specified host/port")
    print("   2. Verify firewall settings")
    print("   3. Check if any MQTT publishers are sending data")
    print("   4. Try running the test_subscriber.py script to see if it publishes data") 