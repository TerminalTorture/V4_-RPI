#!/usr/bin/env python3
import os
import json
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

import paho.mqtt.client as mqtt

# Test message
test_data = {
    "timestamp": "2025-06-04T17:35:54.385189+08:00",
    "device_id": "vflow_sensor_client",
    "data": {
        "Digital Status Reg 1": 0,
        "Pressure_1": 0,
        "OCV_1": 0.023,
        "SOC1": 3.99,
        "HVDC_Voltage": 0
    }
}

# MQTT settings
broker = os.getenv('MQTT_BROKER_HOST', 'localhost')
port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
topic = f"{os.getenv('MQTT_BASE_TOPIC', 'vflow')}/data/bulk"

print(f"Publishing to {broker}:{port} on topic {topic}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(broker, port, 60)

# Update timestamp and publish
test_data["timestamp"] = datetime.now().isoformat()
message = json.dumps(test_data)

result = client.publish(topic, message, qos=1)
print(f"Published: {result.rc == 0}")
print(json.dumps(test_data, indent=2))

client.disconnect()
