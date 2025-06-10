#!/usr/bin/env python3
"""
Minimal Working MQTT Subscriber for VFlow with Flask API Integration
"""
import paho.mqtt.client as mqtt
import json
import time
import os
import requests
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class FlaskAPIClient:
    def __init__(self):
        self.endpoint = f"http://localhost:5001/api/live-data"
        self.timeout = 5.0
        self.success_count = 0
        self.fail_count = 0
    
    def send_data(self, data):
        try:
            payload = {
                'timestamp': data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'device_id': data.get('device_id', 'unknown_device'),
                'data': data
            }
            #logger.info(f"Attempting to send to Flask API. Endpoint: {self.endpoint}, Payload: {json.dumps(payload)}")

            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                self.success_count += 1
                logger.info(f"✅ Flask API success #{self.success_count}")
                return True
            else:
                self.fail_count += 1
                logger.error(f"❌ Flask API failed #{self.fail_count}: {response.status_code}")
                return False
                
        except Exception as e:
            self.fail_count += 1
            logger.error(f"❌ Flask API error #{self.fail_count}: {e}")
            return False

# Global variables
flask_client = FlaskAPIClient()
message_count = 0

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker (code: {rc})")
    if rc == 0:
        client.subscribe("vflow/data/bulk", 0)
        logger.info("Subscribed to vflow/data/bulk")

def on_message(client, userdata, msg):
    global message_count, flask_client
    message_count += 1
    
    logger.info(f"📨 Message #{message_count} received from {msg.topic}")
    
    try:
        # Parse JSON payload
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        
        # Send to Flask API
        success = flask_client.send_data(data)
        
        if success:
            logger.info(f"✅ Message #{message_count} processed successfully")
        else:
            logger.warning(f"⚠️ Message #{message_count} API failed, but received")
        
    except Exception as e:
        logger.error(f"❌ Error processing message #{message_count}: {e}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"MQTT disconnected unexpectedly (code: {rc})")

# Create MQTT client with unique ID
client_id = f"vflow_minimal_{int(time.time() * 1000)}"
client = mqtt.Client(client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Get broker details
broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))

logger.info(f"🚀 Starting VFlow MQTT→Flask Minimal Subscriber")
logger.info(f"MQTT Broker: {broker_host}:{broker_port}")
logger.info(f"Flask API: http://localhost:5001/api/live-data")
logger.info("="*60)

try:
    client.connect(broker_host, broker_port, 60)
    client.loop_start()
    
    logger.info("✅ MQTT client started - listening for messages...")
    
    # Keep running and print stats every 30 seconds
    last_stats = time.time()
    while True:
        time.sleep(1)
        
        # Print stats every 30 seconds
        if time.time() - last_stats > 30:
            logger.info(f"📊 Stats: Messages: {message_count}, Flask API: {flask_client.success_count}✅/{flask_client.fail_count}❌")
            last_stats = time.time()
            
except KeyboardInterrupt:
    logger.info("🛑 Stopping subscriber...")
except Exception as e:
    logger.error(f"❌ Error: {e}")
finally:
    client.loop_stop()
    client.disconnect()
    logger.info(f"📊 Final Stats: Messages: {message_count}, Flask API: {flask_client.success_count}✅/{flask_client.fail_count}❌")
