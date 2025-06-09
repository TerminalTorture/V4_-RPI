#!/usr/bin/env python3
"""
MQTT Subscriber for VFlow Sensor Data Collection

This script runs on the Raspberry Pi to collect MQTT data from VFlow sensors
and store it in a PostgreSQL database.

Features:
- Subscribes to VFlow MQTT topics
- Stores sensor data in PostgreSQL database
- Handles connection failures and reconnection
- Logs all activities
- Creates database tables automatically
- Supports both bulk and individual sensor data
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import signal
import threading

# --- Get a specific logger for this module ---
logger = logging.getLogger(__name__) # Use a module-specific logger

# --- Environment Variable Loading ---
# Calculate the project root first (assuming this script is in api/ folder)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(project_root, '.env')

try:
    from dotenv import load_dotenv
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)
        logger.info(f"✅ Environment variables loaded from {dotenv_path}")
    else:
        logger.warning(f"⚠️ .env file not found at {dotenv_path}. Using system environment variables only.")
except ImportError:
    logger.warning("⚠️ python-dotenv not available, using system environment variables only")
# --- End Environment Variable Loading ---

# MQTT and Database imports
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    logger.error("❌ paho-mqtt not available. Install with: pip install paho-mqtt")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    POSTGRESQL_AVAILABLE = True
except ImportError:
    logger.error("❌ psycopg2 not available. Install with: pip install psycopg2-binary")
    sys.exit(1)


class PostgreSQLHandler:
    """Handles PostgreSQL database operations for sensor data storage."""
    
    def __init__(self):
        """Initialize PostgreSQL connection with configuration from environment."""
        self.connection = None
        self.cursor = None
        
        self.db_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.db_port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.db_user = os.getenv('POSTGRES_USER', 'sensor_user')
        self.db_password = os.getenv('POSTGRES_PASSWORD', 'Master123')
        self.target_database_name = os.getenv('POSTGRES_DATABASE', 'sensor_data')
        
        # This db_config will be for the target database
        self.db_config = {
            'host': self.db_host,
            'port': self.db_port,
            'database': self.target_database_name,
            'user': self.db_user,
            'password': self.db_password
        }
        
        self.table_name = os.getenv('POSTGRES_TABLE', 'sensor_data')
        
        logger.info(f"PostgreSQL Handler initialized - Target DB: {self.target_database_name}, User: {self.db_user}")
    
    def ensure_database_exists(self) -> bool:
        """Ensures the target database exists, creating it if necessary."""
        try:
            # Connect to the default 'postgres' database (or another maintenance DB)
            # The user must have CREATEDB privileges
            maintenance_conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                dbname='postgres'  # Connect to 'postgres' db to check/create other DBs
            )
            maintenance_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            m_cursor = maintenance_conn.cursor()
            
            # Check if the target database exists
            m_cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.target_database_name,))
            exists = m_cursor.fetchone()
            
            if not exists:
                logger.info(f"Database '{self.target_database_name}' does not exist. Attempting to create it...")
                try:
                    m_cursor.execute(f"CREATE DATABASE {self.target_database_name}") # Use f-string carefully, ensure target_database_name is safe
                    logger.info(f"DB_CREATE_SUCCESS: Database '{self.target_database_name}' created successfully.")
                except psycopg2.Error as create_err:
                    logger.error(f"DB_CREATE_FAIL: Failed to create database '{self.target_database_name}': {create_err}")
                    # If creation fails, it could be a permissions issue or other SQL error.
                    # The main connection attempt later will likely fail if the DB wasn't created.
                    return False # Indicate failure
            else:
                logger.info(f"Database '{self.target_database_name}' already exists.")
            
            m_cursor.close()
            maintenance_conn.close()
            return True # Database exists or was created

        except psycopg2.Error as e:
            logger.error(f"DB_CHECK_FAIL: Error while checking/creating database '{self.target_database_name}': {e}")
            logger.error(f"  Please ensure user '{self.db_user}' has CREATEDB privilege and can connect to the 'postgres' database.")
            return False # Indicate failure
        except Exception as e:
            logger.error(f"UNEXPECTED_DB_CHECK_ERR: Unexpected error in ensure_database_exists: {e}")
            return False

    def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            logger.info(f"DB_CONNECT_SUCCESS: Connected to PostgreSQL database '{self.target_database_name}'")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"DB_CONNECT_FAIL: Failed to connect to PostgreSQL database '{self.target_database_name}': {e}")
            return False
    
    def disconnect(self):
        """Disconnect from PostgreSQL database."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("DB_DISCONNECTED: Disconnected from PostgreSQL database")
    
    def create_table_if_not_exists(self):
        """Create the sensor data table if it doesn't exist."""
        if not self.cursor:
            logger.error("TABLE_CREATE_FAIL: Cannot create table: No database cursor. Connection might have failed.")
            return False
        try:
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                device_id VARCHAR(100),
                topic VARCHAR(200),
                
                -- Common sensor fields (adjust based on your sensor data)
                cl1_soc FLOAT,
                cl2_soc FLOAT,
                cl1_voltage FLOAT,
                cl2_voltage FLOAT,
                cl1_current FLOAT,
                cl2_current FLOAT,
                cl1_temperature FLOAT,
                cl2_temperature FLOAT,
                system_power FLOAT,
                grid_frequency FLOAT,
                system_status INTEGER,
                
                -- Flexible JSON field for additional data
                raw_data JSONB,
                
                -- Indexing for performance
                CONSTRAINT unique_timestamp_device UNIQUE (timestamp, device_id)
            );
            
            -- Create indexes for better query performance
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp ON {self.table_name} (timestamp);
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_device_id ON {self.table_name} (device_id);
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_raw_data ON {self.table_name} USING GIN (raw_data);
            """
            
            self.cursor.execute(create_table_sql)
            # If the connection is not in autocommit mode (default), we need to commit DDL.
            if not self.connection.autocommit:
                self.connection.commit()
            
            logger.info(f"TABLE_CREATE_SUCCESS: Table '{self.table_name}' created/verified in '{self.target_database_name}'")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"TABLE_CREATE_FAIL: Failed to create table '{self.table_name}': {e}")
            # If an error occurs during DDL, a rollback might be good practice 
            # if the connection is part of a larger transaction context, though here each call is somewhat standalone.
            try:
                self.connection.rollback() # Rollback on error to clear the transaction state
            except psycopg2.Error as rb_err:
                logger.error(f"TABLE_CREATE_ROLLBACK_FAIL: Failed to rollback: {rb_err}")
            return False
    
    def insert_sensor_data(self, data: Dict[str, Any], topic: str, device_id: str = None) -> bool:
        """Insert sensor data into PostgreSQL database."""
        if not self.cursor or not self.connection:
            logger.error("DATA_INSERT_FAIL: No database cursor or connection available.")
            return False
        try:
            # Prepare timestamp
            timestamp = data.get('timestamp')
            if isinstance(timestamp, str):
                try:
                    # Parse ISO timestamp
                    parsed_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    parsed_timestamp = datetime.now(timezone.utc)
            else:
                parsed_timestamp = datetime.now(timezone.utc)
            
            # Extract device_id from data or use provided
            device_id = device_id or data.get('device_id', 'unknown_device')
            
            # Prepare sensor data fields
            sensor_fields = {
                'timestamp': parsed_timestamp,
                'device_id': device_id,
                'topic': topic,
                'raw_data': json.dumps(data) # Store the original complete data object
            }
            
            # Map known sensor fields for individual columns (optional, raw_data has everything)
            field_mapping = {
                'cl1_soc': 'cl1_soc',
                'cl2_soc': 'cl2_soc',
                'cl1_voltage': 'cl1_voltage',
                'cl2_voltage': 'cl2_voltage',
                'cl1_current': 'cl1_current',
                'cl2_current': 'cl2_current',
                'cl1_temperature': 'cl1_temperature',
                'cl2_temperature': 'cl2_temperature',
                'system_power': 'system_power',
                'grid_frequency': 'grid_frequency',
                'system_status': 'system_status'
            }
            
            # The MQTT data is expected in format: {"timestamp": ..., "device_id": ..., "data": {sensors...}}
            # or flat if it's not a "bulk" like message originally.
            # The insert_sensor_data method receives the full payload (data arg).
            # If data['data'] exists, use it, otherwise use data itself for sensor values.
            actual_sensor_data_payload = data.get('data', data) 
            
            if isinstance(actual_sensor_data_payload, dict):
                for field_name, db_column in field_mapping.items():
                    if field_name in actual_sensor_data_payload and actual_sensor_data_payload[field_name] is not None:
                        try:
                            sensor_fields[db_column] = float(actual_sensor_data_payload[field_name])
                        except (ValueError, TypeError):
                            # If not numeric, store in raw_data only (already handled by raw_data field)
                            pass # logging.debug(f"Value for {field_name} is not floatable, relying on raw_data.")
            
            # Build INSERT query
            columns = ', '.join(sensor_fields.keys())
            placeholders = ', '.join(['%s'] * len(sensor_fields))
            values = list(sensor_fields.values())
            
            insert_sql = f"""
            INSERT INTO {self.table_name} ({columns})
            VALUES ({placeholders})
            ON CONFLICT (timestamp, device_id) DO UPDATE SET
                raw_data = EXCLUDED.raw_data,
                topic = EXCLUDED.topic
                -- Update other specific columns if needed, e.g.:
                -- cl1_soc = EXCLUDED.cl1_soc, ... (if they are part of sensor_fields and EXCLUDED)
            """ # Ensure all columns in sensor_fields are actually in the table definition for direct assignment
            
            self.cursor.execute(insert_sql, values)
            
            # If connection is not in autocommit mode, commit the insert
            if not self.connection.autocommit:
                self.connection.commit()
                
            logger.debug(f"DATA_INSERTED: Sensor data for device {device_id} into {self.table_name}")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"DATA_INSERT_FAIL: Failed to insert sensor data into {self.table_name}: {e}")
            try:
                self.connection.rollback() # Rollback on error
            except psycopg2.Error as rb_err:
                logger.error(f"INSERT_ROLLBACK_FAIL: Failed to rollback: {rb_err}")
            return False
        except Exception as e:
            logger.error(f"UNEXPECTED_INSERT_ERR: Unexpected error inserting data into {self.table_name}: {e}")
            # Also attempt rollback for generic exceptions if connection might be in a transaction
            if self.connection and not self.connection.closed and self.connection.status != psycopg2.extensions.STATUS_BEGIN:
                try:
                    self.connection.rollback()
                except psycopg2.Error as rb_err:
                    logger.error(f"UNEXPECTED_INSERT_ROLLBACK_FAIL: {rb_err}")
            return False
    
    def get_latest_data(self, limit: int = 10) -> list:
        """Retrieve latest sensor data from database."""
        try:
            query = f"""
            SELECT * FROM {self.table_name}
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            self.cursor.execute(query, (limit,))
            results = self.cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to retrieve data: {e}")
            return []


class VFlowMQTTSubscriber:
    """MQTT Subscriber for VFlow sensor data collection."""
    
    def __init__(self):
        """Initialize MQTT subscriber with configuration."""
        # MQTT Configuration from environment
        self.broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        self.broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        self.username = os.getenv('MQTT_USERNAME')
        self.password = os.getenv('MQTT_PASSWORD')
        self.client_id = os.getenv('MQTT_CLIENT_ID', f"vflow_subscriber_{int(time.time())}")
        
        # Topic configuration
        self.base_topic = os.getenv('MQTT_BASE_TOPIC', 'vflow')
        self.topics = [
            f"{self.base_topic}/data/bulk",
            f"{self.base_topic}/sensors/+",
            f"{self.base_topic}/status"
        ]
        
        # QoS settings
        self.qos_level = int(os.getenv('MQTT_QOS_LEVEL', '1'))
        
        # Initialize components
        self.db_handler = PostgreSQLHandler()
        self.mqtt_client = None
        self.running = False
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'data_points_stored': 0,
            'errors': 0,
            'start_time': None
        }
        
        logger.info(f"MQTT Subscriber initialized - Broker: {self.broker_host}:{self.broker_port}")
    
    def setup_mqtt_client(self):
        """Setup MQTT client with callbacks."""
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        
        # Set callbacks
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.on_subscribe = self.on_subscribe
        
        # Authentication if provided
        if self.username and self.password:
            self.mqtt_client.username_pw_set(self.username, self.password)
        
        logger.info("MQTT client configured")
    
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback for when the client receives a CONNACK response."""
        # reason_code is aliased to rc for clarity with older Paho versions if seen in examples
        # but for VERSION2, rc is an MQTTReasonCode object or int.
        actual_reason_code = rc 

        connect_successful = False
        log_rc_part = str(actual_reason_code)

        if isinstance(actual_reason_code, int):
            if actual_reason_code == 0:
                connect_successful = True
            log_rc_part = f"int({actual_reason_code}) - {mqtt.connack_string(actual_reason_code)}"
        elif hasattr(actual_reason_code, 'value') and hasattr(actual_reason_code, 'getName'): # MQTTv5 ReasonCode
            if actual_reason_code.value == 0:
                connect_successful = True
            log_rc_part = f"{actual_reason_code.getName()} (value: {actual_reason_code.value})"
        else: # Unknown type
            log_rc_part = f"unknown_type({actual_reason_code})"

        if connect_successful:
            logger.info(f"MQTT_CONNECT_SUCCESS: Connected to MQTT broker {self.broker_host}:{self.broker_port} (Reason: {log_rc_part})")
            # Subscribe to all VFlow topics
            for topic in self.topics:
                client.subscribe(topic, self.qos_level)
                # on_subscribe will log individual subscription results
        else:
            logger.error(f"MQTT_CONNECT_FAIL: Failed to connect to MQTT broker. Reason: {log_rc_part}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback for when the client disconnects."""
        # flags:  can be used to get additional disconnect information for MQTT V5.
        # For V3.1.1 it's not used beyond being passed.
        # reason_code: is an MQTTReasonCode object or int.
        # properties: MQTT V5 properties.

        actual_rc = reason_code # Use the correct variable name
        rc_value_for_check = -1 # Default to error, assuming 0 is clean disconnect
        log_message_rc_part = str(actual_rc) # Default to string of actual_rc

        if isinstance(actual_rc, int):
            rc_value_for_check = actual_rc
            err_str = mqtt.error_string(actual_rc) if actual_rc != 0 else "Clean disconnect"
            log_message_rc_part = f"int({actual_rc} - '{err_str}')" 
        elif hasattr(actual_rc, 'value') and hasattr(actual_rc, 'getName'): # MQTTv5 ReasonCode
            rc_value_for_check = actual_rc.value
            log_message_rc_part = f"{actual_rc.getName()} (value: {rc_value_for_check})"
        else: # Unknown type, treat as error
            log_message_rc_part = f"unknown_type({actual_rc})"

        # Check if it was an unexpected disconnect (rc_value_for_check != 0)
        # or if it was a clean disconnect initiated by the client (self.running is False)
        if rc_value_for_check != 0 and self.running:
            logger.warning(f"MQTT_UNEXPECTED_DISCONNECT: Reason: {log_message_rc_part}. Attempting reconnect...")
            if flags:
                logger.debug(f"Disconnect flags: {flags}")
            if properties:
                 logger.debug(f"Disconnect properties: {properties}")
        elif rc_value_for_check == 0:
            logger.info(f"MQTT_DISCONNECTED_CLEANLY: Reason: {log_message_rc_part}.")
        else: # Disconnected, but self.running is False (i.e., we called stop())
            logger.info(f"MQTT_DISCONNECTED_EXPECTEDLY (subscriber stopping): Reason: {log_message_rc_part}.")
    
    def on_subscribe(self, client, userdata, mid, granted_qos_list, properties=None):
        """Callback for when subscription is acknowledged."""
        # reason_code_list was the old name, now it's granted_qos_list for VERSION2 (or reason_codes in some contexts)
        # Paho docs say: granted_qos (for subscribe) or reason_codes (for subscribe with reason codes)
        # For on_subscribe, it's reason_code_list (an array of MQTTReasonCode objects or ints)
        # Let's assume it's a list. The original `mid, reason_code_list, properties` seems more aligned with some docs for V2.
        # The `client.subscribe()` call does not specify protocol version for subscribe options.
        # Let's stick to reason_code_list as it might be more general for V2.
        # The variable name `granted_qos_list` is often used when reason codes are not the focus.
        # If `reason_code_list` truly contains `MQTTReasonCode` objects:
        processed_codes = []
        if isinstance(granted_qos_list, list):
            for i, code in enumerate(granted_qos_list):
                if hasattr(code, 'value') and hasattr(code, 'getName'): # MQTTv5 ReasonCode object
                    processed_codes.append(f"Topic {i}: {code.getName()} (QoS granted/Reason: {code.value})")
                elif isinstance(code, int): # Integer (likely QoS level or simple reason code)
                    processed_codes.append(f"Topic {i}: QoS/Reason int({code})")
                else:
                    processed_codes.append(f"Topic {i}: Unknown type ({code})")
            logger.info(f"MQTT_SUB_ACK: Subscription acknowledged - MID: {mid}, Results: [{', '.join(processed_codes)}]")
        else: # If it's not a list (e.g. single int for older style or single subscription)
             logger.info(f"MQTT_SUB_ACK: Subscription acknowledged - MID: {mid}, QoS/Reason: {granted_qos_list}")
        
        if properties:
            logger.debug(f"Subscribe properties: {properties}")
    
    def on_message(self, client, userdata, msg):
        """Callback for when a message is received."""
        try:
            self.stats['messages_received'] += 1
            
            topic = msg.topic
            payload_bytes = msg.payload # Keep as bytes first for inspection
            
            # Log the raw payload as received (e.g., as a repr or decoded with error handling)
            try:
                payload_str_for_log = payload_bytes.decode('utf-8')
            except UnicodeDecodeError:
                payload_str_for_log = repr(payload_bytes) # Show bytes if not valid UTF-8

            logger.debug(f"MQTT_MSG_RECV: Topic: {topic}, Raw Payload: '{payload_str_for_log}'")
            
            # Decode payload for JSON parsing
            payload = payload_bytes.decode('utf-8') # This is where UnicodeDecodeError might happen if not UTF-8
                        
            # Parse JSON payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"MQTT_JSON_PARSE_FAIL: {e} (for payload: '{payload}')") # Log the payload that failed
                self.stats['errors'] += 1
                return
            
            # Process different message types
            if topic.endswith('/data/bulk'):
                success = self.process_bulk_data(data, topic)
            elif topic.endswith('/status'):
                success = self.process_status_message(data, topic)
            elif '/sensors/' in topic:
                success = self.process_individual_sensor(data, topic)
            else:
                logger.warning(f"MQTT_UNKNOWN_TOPIC: {topic}")
                success = False
            
            if success:
                self.stats['data_points_stored'] += 1
                logger.debug(f"DB_STORE_SUCCESS: Data stored from topic: {topic}")
            else:
                self.stats['errors'] += 1
                logger.error(f"DB_STORE_FAIL: Failed to store data from topic: {topic}")
        
        except Exception as e:
            logger.error(f"MQTT_MSG_PROCESS_FAIL: {e}")
            self.stats['errors'] += 1
    
    def process_bulk_data(self, data: Dict[str, Any], topic: str) -> bool:
        """Process bulk sensor data message."""
        device_id = data.get('device_id', 'unknown_device')
        return self.db_handler.insert_sensor_data(data, topic, device_id)
    
    def process_status_message(self, data: Dict[str, Any], topic: str) -> bool:
        """Process status message."""
        device_id = data.get('device_id', 'unknown_device')
        logger.info(f"STATUS_MSG: Device {device_id}: {data.get('status')} - {data.get('message', '')}")
        return self.db_handler.insert_sensor_data(data, topic, device_id)
    
    def process_individual_sensor(self, data: Dict[str, Any], topic: str) -> bool:
        """Process individual sensor data message."""
        device_id = data.get('device_id', 'unknown_device')
        sensor_name = topic.split('/')[-1]  # Extract sensor name from topic
        
        # Restructure data to match bulk format
        sensor_data = {
            'timestamp': data.get('timestamp'),
            'device_id': device_id,
            sensor_name: data.get('value')
        }
        
        return self.db_handler.insert_sensor_data(sensor_data, topic, device_id)
    
    def start(self):
        """Start the MQTT subscriber."""
        logger.info("SUBSCRIBER_STARTING: Starting VFlow MQTT Subscriber...")
        
        # Step 1: Ensure the database exists
        if not self.db_handler.ensure_database_exists():
            logger.error(f"SUBSCRIBER_FAIL: DB '{self.db_handler.target_database_name}' not ensured. Exiting.")
            return False # Stop if database cannot be ensured

        # Step 2: Connect to the target database
        if not self.db_handler.connect():
            logger.error(f"SUBSCRIBER_FAIL: DB connect to '{self.db_handler.target_database_name}' failed. Exiting.")
            return False
        
        # Step 3: Create database table in the target database
        if not self.db_handler.create_table_if_not_exists():
            logger.error(f"SUBSCRIBER_FAIL: Table '{self.db_handler.table_name}' creation failed. Exiting.")
            self.db_handler.disconnect() # Disconnect if table creation failed
            return False
        
        # Setup and connect MQTT client
        self.setup_mqtt_client()
        
        try:
            self.mqtt_client.connect(self.broker_host, self.broker_port, 60)
            self.mqtt_client.loop_start()
            
            self.running = True
            self.stats['start_time'] = datetime.now()
            
            logger.info("SUBSCRIBER_STARTED: VFlow MQTT Subscriber started successfully!")
            logger.info("Press Ctrl+C to stop the subscriber")
            
            return True
            
        except Exception as e:
            logger.error(f"MQTT_CLIENT_START_FAIL: {e}")
            self.db_handler.disconnect() # Ensure DB is disconnected on MQTT start failure
            return False
    
    def stop(self):
        """Stop the MQTT subscriber."""
        logger.info("SUBSCRIBER_STOPPING: Stopping VFlow MQTT Subscriber...")
        
        self.running = False
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.db_handler.disconnect()
        
        # Print statistics
        self.print_statistics()
        
        logger.info("SUBSCRIBER_STOPPED: VFlow MQTT Subscriber stopped")
    
    def print_statistics(self):
        """Print subscriber statistics."""
        if self.stats['start_time']:
            runtime = datetime.now() - self.stats['start_time']
            
            print("\n" + "="*50)
            print("📊 VFlow MQTT Subscriber Statistics")
            print("="*50)
            print(f"Runtime: {runtime}")
            print(f"Messages Received: {self.stats['messages_received']}")
            print(f"Data Points Stored: {self.stats['data_points_stored']}")
            print(f"Errors: {self.stats['errors']}")
            if runtime.total_seconds() > 0:
                rate = self.stats['messages_received'] / runtime.total_seconds()
                print(f"Average Rate: {rate:.2f} messages/second")
            print("="*50)
    
    def run_forever(self):
        """Run the subscriber indefinitely."""
        if not self.start():
            return
        
        try:
            while self.running:
                time.sleep(1)
                
                # Print periodic statistics (every 5 minutes)
                if self.stats['start_time']:
                    runtime = datetime.now() - self.stats['start_time']
                    if runtime.total_seconds() % 300 < 1:  # Every 5 minutes
                        logger.info(f"STATS_UPDATE: Runtime: {runtime}, Messages: {self.stats['messages_received']}, Stored: {self.stats['data_points_stored']}")
        
        except KeyboardInterrupt:
            logger.info("⚠️ Keyboard interrupt received")
        except Exception as e:
            logger.error(f"UNEXPECTED_RUNTIME_ERR: {e}")
        finally:
            self.stop()


def setup_logging():
    """Setup logging configuration."""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('vflow_mqtt_subscriber.log')
        ],
        encoding='utf-8'
    )
    # For Windows console, explicitly set encoding for stdout if possible
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
            logger.info("stdout/stderr reconfigured to UTF-8 for logging.")
        except Exception as e:
            print(f"WARNING: Could not reconfigure stdout/stderr to UTF-8: {e}")

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown."""
    logger.info(f"SIGNAL_RECEIVED: Signal {signum}")
    global subscriber
    if subscriber:
        subscriber.running = False

def main():
    """Main function."""
    print("🚀 VFlow MQTT Subscriber for PostgreSQL Storage")
    print("=" * 60)
    
    # Setup logging
    setup_logging()
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Display configuration
    print(f"INFO: MQTT Broker: {os.getenv('MQTT_BROKER_HOST', 'localhost')}:{os.getenv('MQTT_BROKER_PORT', '1883')}")
    print(f"INFO: PostgreSQL: {os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}")
    print(f"INFO: Database: {os.getenv('POSTGRES_DATABASE', 'sensor_data')}")
    print(f"INFO: Table: {os.getenv('POSTGRES_TABLE', 'sensor_data')}")
    print("=" * 60)
    
    # Create and run subscriber
    global subscriber
    subscriber = VFlowMQTTSubscriber()
    subscriber.run_forever()

if __name__ == "__main__":
    main()
