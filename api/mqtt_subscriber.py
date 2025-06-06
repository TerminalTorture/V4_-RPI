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

# --- Environment Variable Loading ---
# Calculate the project root first (assuming this script is in api/ folder)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(project_root, '.env')

try:
    from dotenv import load_dotenv
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)
        print(f"✅ Environment variables loaded from {dotenv_path}")
    else:
        print(f"⚠️ .env file not found at {dotenv_path}. Using system environment variables only.")
except ImportError:
    print("⚠️ python-dotenv not available, using system environment variables only")
# --- End Environment Variable Loading ---

# MQTT and Database imports
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    print("❌ paho-mqtt not available. Install with: pip install paho-mqtt")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    POSTGRESQL_AVAILABLE = True
except ImportError:
    print("❌ psycopg2 not available. Install with: pip install psycopg2-binary")
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
        
        logging.info(f"PostgreSQL Handler initialized - Target DB: {self.target_database_name}, User: {self.db_user}")
    
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
                logging.info(f"Database '{self.target_database_name}' does not exist. Attempting to create it...")
                try:
                    m_cursor.execute(f"CREATE DATABASE {self.target_database_name}") # Use f-string carefully, ensure target_database_name is safe
                    logging.info(f"✅ Database '{self.target_database_name}' created successfully.")
                except psycopg2.Error as create_err:
                    logging.error(f"❌ Failed to create database '{self.target_database_name}': {create_err}")
                    # If creation fails, it could be a permissions issue or other SQL error.
                    # The main connection attempt later will likely fail if the DB wasn't created.
                    return False # Indicate failure
            else:
                logging.info(f"Database '{self.target_database_name}' already exists.")
            
            m_cursor.close()
            maintenance_conn.close()
            return True # Database exists or was created

        except psycopg2.Error as e:
            logging.error(f"❌ Error while checking/creating database '{self.target_database_name}': {e}")
            logging.error(f"  Please ensure user '{self.db_user}' has CREATEDB privilege and can connect to the 'postgres' database.")
            return False # Indicate failure
        except Exception as e:
            logging.error(f"❌ Unexpected error in ensure_database_exists: {e}")
            return False

    def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            logging.info(f"✅ Connected to PostgreSQL database '{self.target_database_name}'")
            return True
            
        except psycopg2.Error as e:
            logging.error(f"❌ Failed to connect to PostgreSQL database '{self.target_database_name}': {e}")
            return False
    
    def disconnect(self):
        """Disconnect from PostgreSQL database."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logging.info("📡 Disconnected from PostgreSQL database")
    
    def create_table_if_not_exists(self):
        """Create the sensor data table if it doesn't exist."""
        if not self.cursor:
            logging.error("❌ Cannot create table: No database cursor available. Connection might have failed.")
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
            self.connection.autocommit = True 
            logging.info(f"✅ Table '{self.table_name}' created or verified in database '{self.target_database_name}'")
            self.connection.autocommit = False
            return True
            
        except psycopg2.Error as e:
            logging.error(f"❌ Failed to create table '{self.table_name}': {e}")
            return False
    
    def insert_sensor_data(self, data: Dict[str, Any], topic: str, device_id: str = None) -> bool:
        """Insert sensor data into PostgreSQL database."""
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
                'raw_data': json.dumps(data)
            }
            
            # Map known sensor fields
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
            
            # Extract sensor data if available
            sensor_data = data.get('data', data)  # Handle both bulk format and direct format
            
            for field_name, db_column in field_mapping.items():
                if field_name in sensor_data and sensor_data[field_name] is not None:
                    try:
                        sensor_fields[db_column] = float(sensor_data[field_name])
                    except (ValueError, TypeError):
                        # If not numeric, store in raw_data only
                        pass
            
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
            """
            
            self.cursor.execute(insert_sql, values)
            logging.debug(f"📊 Inserted sensor data for device {device_id}")
            return True
            
        except psycopg2.Error as e:
            logging.error(f"❌ Failed to insert sensor data: {e}")
            return False
        except Exception as e:
            logging.error(f"❌ Unexpected error inserting data: {e}")
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
            logging.error(f"❌ Failed to retrieve data: {e}")
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
        
        logging.info(f"VFlow MQTT Subscriber initialized - Broker: {self.broker_host}:{self.broker_port}")
    
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
        
        logging.info("MQTT client configured")
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback for when the client receives a CONNACK response."""
        if reason_code == 0:
            logging.info(f"✅ Connected to MQTT broker {self.broker_host}:{self.broker_port}")
            
            # Subscribe to all VFlow topics
            for topic in self.topics:
                client.subscribe(topic, self.qos_level)
                logging.info(f"📡 Subscribed to topic: {topic}")
        else:
            logging.error(f"❌ Failed to connect to MQTT broker. Reason code: {reason_code}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback for when the client disconnects."""
        if reason_code != 0:
            logging.warning(f"⚠️ Unexpected MQTT disconnection. Reason code: {reason_code}")
            logging.info("🔄 Attempting to reconnect...")
        else:
            logging.info("📡 Disconnected from MQTT broker")
    
    def on_subscribe(self, client, userdata, mid, reason_code_list, properties=None):
        """Callback for when subscription is acknowledged."""
        logging.debug(f"✅ Subscription acknowledged - Message ID: {mid}")
    
    def on_message(self, client, userdata, msg):
        """Callback for when a message is received."""
        try:
            self.stats['messages_received'] += 1
            
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logging.debug(f"📨 Received message on topic: {topic}")
            
            # Parse JSON payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logging.error(f"❌ Failed to parse JSON message: {e}")
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
                logging.warning(f"⚠️ Unknown topic pattern: {topic}")
                success = False
            
            if success:
                self.stats['data_points_stored'] += 1
                logging.debug(f"📊 Data stored successfully from topic: {topic}")
            else:
                self.stats['errors'] += 1
                logging.error(f"❌ Failed to store data from topic: {topic}")
        
        except Exception as e:
            logging.error(f"❌ Error processing message: {e}")
            self.stats['errors'] += 1
    
    def process_bulk_data(self, data: Dict[str, Any], topic: str) -> bool:
        """Process bulk sensor data message."""
        device_id = data.get('device_id', 'unknown_device')
        return self.db_handler.insert_sensor_data(data, topic, device_id)
    
    def process_status_message(self, data: Dict[str, Any], topic: str) -> bool:
        """Process status message."""
        device_id = data.get('device_id', 'unknown_device')
        logging.info(f"📊 Status from {device_id}: {data.get('status')} - {data.get('message', '')}")
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
        logging.info("🚀 Starting VFlow MQTT Subscriber...")
        
        # Step 1: Ensure the database exists
        if not self.db_handler.ensure_database_exists():
            logging.error(f"❌ Database '{self.db_handler.target_database_name}' does not exist and could not be created. Please check permissions or create it manually. Exiting.")
            return False # Stop if database cannot be ensured

        # Step 2: Connect to the target database
        if not self.db_handler.connect():
            logging.error(f"❌ Failed to connect to database '{self.db_handler.target_database_name}'. Exiting.")
            return False
        
        # Step 3: Create database table in the target database
        if not self.db_handler.create_table_if_not_exists():
            logging.error(f"❌ Failed to create database table '{self.db_handler.table_name}'. Exiting.")
            self.db_handler.disconnect() # Disconnect if table creation failed
            return False
        
        # Setup and connect MQTT client
        self.setup_mqtt_client()
        
        try:
            self.mqtt_client.connect(self.broker_host, self.broker_port, 60)
            self.mqtt_client.loop_start()
            
            self.running = True
            self.stats['start_time'] = datetime.now()
            
            logging.info("🎉 VFlow MQTT Subscriber started successfully!")
            logging.info("📊 Press Ctrl+C to stop the subscriber")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Failed to start MQTT client: {e}")
            self.db_handler.disconnect() # Ensure DB is disconnected on MQTT start failure
            return False
    
    def stop(self):
        """Stop the MQTT subscriber."""
        logging.info("🛑 Stopping VFlow MQTT Subscriber...")
        
        self.running = False
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.db_handler.disconnect()
        
        # Print statistics
        self.print_statistics()
        
        logging.info("👋 VFlow MQTT Subscriber stopped")
    
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
                        logging.info(f"📊 Runtime: {runtime}, Messages: {self.stats['messages_received']}, Stored: {self.stats['data_points_stored']}")
        
        except KeyboardInterrupt:
            logging.info("⚠️ Keyboard interrupt received")
        except Exception as e:
            logging.error(f"❌ Unexpected error: {e}")
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
        ]
    )

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown."""
    logging.info(f"🔔 Received signal {signum}")
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
    print(f"MQTT Broker: {os.getenv('MQTT_BROKER_HOST', 'localhost')}:{os.getenv('MQTT_BROKER_PORT', '1883')}")
    print(f"PostgreSQL: {os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}")
    print(f"Database: {os.getenv('POSTGRES_DATABASE', 'vflow_data')}")
    print(f"Table: {os.getenv('POSTGRES_TABLE', 'sensor_data')}")
    print("=" * 60)
    
    # Create and run subscriber
    global subscriber
    subscriber = VFlowMQTTSubscriber()
    subscriber.run_forever()

if __name__ == "__main__":
    main()
