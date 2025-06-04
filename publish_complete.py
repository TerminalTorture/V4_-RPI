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

# Complete test message - your exact data
test_data = {
    "timestamp": "2025-06-04T17:35:54.385189+08:00",
    "device_id": "vflow_sensor_client",
    "data": {
        "Digital Status Reg 1": 0,
        "Digital Status Reg 2": 0,
        "Digital Status Reg 3": 0,
        "Digital Status Reg 4": 0,
        "Pressure_1": 0,
        "Pressure_2": 0,
        "Pressure_3": 0,
        "Pressure_4": 0,
        "OCV_1": 0.023,
        "OCV_2": 0.651,
        "Cluster_1_Voltage": 0,
        "Cluster_1_Current": 0,
        "Cluster_2_Voltage": 0,
        "Cluster_2_Current": 0,
        "HVDC_Voltage": 0,
        "HVDC_Current": 0,
        "SOC1": 3.99,
        "SOC2": 3.96,
        "Primary_Pump_Ramp_PID_SP_FB": 0,
        "Secondary_Pump_Ramp_PID_SP_FB": 0,
        "Cluster_1_Power": 0,
        "Cluster_2_Power": 0,
        "HVDC_Power": 0,
        "Total_Cluster_Power": 0,
        "Cluster-1 Condition": 1,
        "Cluster-2 Condition": 4,
        "System Condition": 2,
        "Zekalab system State": 1,
        "Battery Status": 0,
        "CL_1 PowerMode": 0,
        "CL_2 PowerMode": 3,
        "ZEK_1_Main Status": 10254,
        "ZEK_1_Actual_Main_Control_word": 9863,
        "ZEK_1_Auxiliary Status": 17745,
        "ZEK_2_Auxiliary Status": 3,
        "ZEK_2_Main Status": 31777,
        "ZEK_1_Actual_Droop_Co-efficient": 0,
        "ZEK_1_Actual_Boost_2Q_Voltage_Reference": 0,
        "ZEK_1_Actual_Current_Limit_Charge_SideA": 0,
        "ZEK_2_Actual_Droop_Co-efficeint": 0,
        "ZEK_2_Actual_Boost_2Q_Voltage_Reference": 0,
        "ZEK_2_Actual_Current_Limit_Charge_SideA": 0,
        "ZEK_2_Actual_Main_Control_word": 0
    }
}

# MQTT settings
broker = os.getenv('MQTT_BROKER_HOST', 'localhost')
port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
topic = f"{os.getenv('MQTT_BASE_TOPIC', 'vflow')}/data/bulk"

print(f"📤 Publishing complete test message to {broker}:{port}")
print(f"🎯 Topic: {topic}")

# Update timestamp
test_data["timestamp"] = datetime.now().isoformat()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(broker, port, 60)

message = json.dumps(test_data)
print(f"📏 Message size: {len(message)} bytes")
print(f"📊 Sensor count: {len(test_data['data'])}")

result = client.publish(topic, message, qos=1)
print(f"✅ Published: {result.rc == 0}")

client.disconnect()
