#!/usr/bin/env python3
"""
Test script for VFlow MQTT Subscriber

This script tests the PostgreSQL connection and MQTT subscription
functionality before running the full subscriber.

Usage:
    python test_subscriber.py
"""

import os
import sys
import json
import time
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # Ensure .env values override existing ones
    print("✅ Environment variables loaded (override enabled)")
except ImportError:
    print("⚠️ python-dotenv not available")

def test_postgresql_connection():
    """Test PostgreSQL database connection."""
    print("\n🗄️  Testing PostgreSQL connection...")
    
    try:
        import psycopg2
        
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DATABASE', 'vflow_data'),
            'user': os.getenv('POSTGRES_USER', 'vflow'),
            'password': os.getenv('POSTGRES_PASSWORD', 'password')
        }
        
        print(f"Connecting to {db_config['host']}:{db_config['port']} as {db_config['user']}")
        
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        print(f"✅ PostgreSQL connection successful!")
        print(f"   Database version: {db_version[0]}")
        
        # Test table creation
        table_name = os.getenv('POSTGRES_TABLE', 'sensor_data')
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print(f"✅ Table '{table_name}' exists")
            
            # Count records
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            record_count = cursor.fetchone()[0]
            print(f"   Records in table: {record_count}")
        else:
            print(f"⚠️ Table '{table_name}' does not exist (will be created automatically)")
        
        cursor.close()
        conn.close()
        return True
        
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False

def test_mqtt_connection():
    """Test MQTT broker connection."""
    print("\n📡 Testing MQTT connection...")
    
    try:
        import paho.mqtt.client as mqtt
        
        broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        
        print(f"Connecting to MQTT broker at {broker_host}:{broker_port}")
        
        # Connection test
        connection_successful = False
        
        def on_connect(client, userdata, flags, reason_code, properties=None):
            nonlocal connection_successful
            if reason_code == 0:
                connection_successful = True
                print("✅ MQTT connection successful!")
            else:
                print(f"❌ MQTT connection failed. Reason code: {reason_code}")
        
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_client")
        client.on_connect = on_connect
        
        # Authentication if provided
        username = os.getenv('MQTT_USERNAME')
        password = os.getenv('MQTT_PASSWORD')
        if username and password:
            client.username_pw_set(username, password)
        
        client.connect(broker_host, broker_port, 60)
        client.loop_start()
        
        # Wait for connection
        timeout = 10
        start_time = time.time()
        while not connection_successful and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        
        return connection_successful
        
    except ImportError:
        print("❌ paho-mqtt not installed. Install with: pip install paho-mqtt")
        return False
    except Exception as e:
        print(f"❌ MQTT connection test failed: {e}")
        return False

def test_mqtt_subscription():
    """Test MQTT subscription and message handling."""
    print("\n📨 Testing MQTT subscription...")
    
    try:
        import paho.mqtt.client as mqtt
        
        broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        base_topic = os.getenv('MQTT_BASE_TOPIC', 'vflow')
        
        message_received = False
        
        def on_connect(client, userdata, flags, reason_code, properties=None):
            if reason_code == 0:
                print(f"✅ Connected to MQTT broker")
                # Subscribe to test topic
                test_topic = f"{base_topic}/test"
                client.subscribe(test_topic, 1)
                print(f"📡 Subscribed to {test_topic}")
                
                # Publish test message
                test_message = {
                    "timestamp": datetime.now().isoformat(),
                    "test_data": "Hello from VFlow test!",
                    "device_id": "test_device"
                }
                client.publish(test_topic, json.dumps(test_message), 1)
                print(f"📤 Published test message")
        
        def on_message(client, userdata, msg):
            nonlocal message_received
            try:
                topic = msg.topic
                payload = json.loads(msg.payload.decode('utf-8'))
                print(f"📨 Received message on {topic}:")
                print(f"   {json.dumps(payload, indent=2)}")
                message_received = True
            except Exception as e:
                print(f"❌ Error processing message: {e}")
        
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_subscriber")
        client.on_connect = on_connect
        client.on_message = on_message
        
        # Authentication if provided
        username = os.getenv('MQTT_USERNAME')
        password = os.getenv('MQTT_PASSWORD')
        if username and password:
            client.username_pw_set(username, password)
        
        client.connect(broker_host, broker_port, 60)
        client.loop_start()
        
        # Wait for message
        timeout = 10
        start_time = time.time()
        while not message_received and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        
        if message_received:
            print("✅ MQTT subscription test successful!")
            return True
        else:
            print("❌ No message received within timeout")
            return False
        
    except Exception as e:
        print(f"❌ MQTT subscription test failed: {e}")
        return False

def display_configuration():
    """Display current configuration."""
    print("\n⚙️ Current Configuration:")
    print("=" * 40)
    print(f"PostgreSQL Host: {os.getenv('POSTGRES_HOST', 'localhost')}")
    print(f"PostgreSQL Port: {os.getenv('POSTGRES_PORT', '5432')}")
    print(f"PostgreSQL Database: {os.getenv('POSTGRES_DATABASE', 'vflow_data')}")
    print(f"PostgreSQL User: {os.getenv('POSTGRES_USER', 'vflow')}")
    print(f"PostgreSQL Table: {os.getenv('POSTGRES_TABLE', 'sensor_data')}")
    print()
    print(f"MQTT Broker: {os.getenv('MQTT_BROKER_HOST', 'localhost')}")
    print(f"MQTT Port: {os.getenv('MQTT_BROKER_PORT', '1883')}")
    print(f"MQTT Base Topic: {os.getenv('MQTT_BASE_TOPIC', 'vflow')}")
    print(f"MQTT Username: {os.getenv('MQTT_USERNAME', 'Not set')}")
    print("=" * 40)

def main():
    """Main test function."""
    print("🧪 VFlow MQTT Subscriber Test Script")
    print("=" * 50)
    
    # Display configuration
    display_configuration()
    
    # Run tests
    tests = [
        ("PostgreSQL Connection", test_postgresql_connection),
        ("MQTT Connection", test_mqtt_connection),
        ("MQTT Subscription", test_mqtt_subscription),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        result = test_func()
        results.append((test_name, result))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Results Summary")
    print("="*60)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<25} {status}")
        if not result:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("🎉 All tests passed! Your VFlow MQTT Subscriber setup is ready.")
        print("\nYou can now run the full subscriber with:")
        print("   python mqtt_subscriber.py")
    else:
        print("⚠️ Some tests failed. Please check your configuration and setup.")
        print("\nTroubleshooting:")
        print("1. Verify PostgreSQL is running: sudo systemctl status postgresql")
        print("2. Verify MQTT broker is running: sudo systemctl status mosquitto")
        print("3. Check .env file configuration")
        print("4. Ensure all dependencies are installed: pip install -r requirements_subscriber.txt")

if __name__ == "__main__":
    main()
