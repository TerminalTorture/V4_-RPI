import os
import sys
import json
from flask import Blueprint, jsonify, request
# Removed: from flask_sqlalchemy import SQLAlchemy - using PostgreSQL directly
from datetime import datetime, timezone, timedelta # Import timedelta
# Removed: from sqlalchemy.exc import IntegrityError - using PostgreSQL directly
# Removed: from sqlalchemy import desc, text, and_, or_ - using PostgreSQL directly
import logging # Import logging
import psycopg2
import psycopg2.extras
# from dotenv import load_dotenv # Already imported but will be part of the new block

# --- Environment Variable Loading ---
# Assuming this file (live_data.py) is in the 'api' subdirectory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) 
dotenv_path = os.path.join(project_root, '.env')
try:
    from dotenv import load_dotenv
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)
        # Use a unique print statement to confirm which file is loading
        print(f"✅ api/live_data.py: Environment variables loaded from {dotenv_path}")
    else:
        print(f"⚠️ api/live_data.py: .env file not found at {dotenv_path}. Using system environment variables only.")
except ImportError:
    print("⚠️ api/live_data.py: python-dotenv not available, using system environment variables only")
# --- End Environment Variable Loading ---


# Calculate the project root # This was for sys.path, can be removed if project_root above is sufficient
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) # Redundant with above
if project_root not in sys.path: # Use project_root defined for dotenv
    sys.path.insert(0, project_root)

# --- Use the new config loader ---
from api.config_loader import REGISTER_CONFIG
# Removed: from api.modbus_client import read_modbus_data - no longer needed for PostgreSQL
# Removed: from api.extensions import db - PostgreSQL handled directly

# Import centralized timezone configuration
from api.timezone_config import set_timezone

# PostgreSQL configuration (should match mqtt_subscriber.py)
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DATABASE', 'sensor_data_rpi'), # Corrected default DB name
    'user': os.getenv('POSTGRES_USER', 'sensor_user'),         # Default to sensor_user
    'password': os.getenv('POSTGRES_PASSWORD', 'Master123')   # Default to Master123
}
POSTGRES_TABLE = os.getenv('POSTGRES_TABLE', 'sensor_data')

# Define Blueprint
live_data_api = Blueprint('live_data_api', __name__)

# Global variable to store the latest live data received via POST
latest_live_data = None

# PostgreSQL connection helper
def get_postgres_connection():
    """Get PostgreSQL connection"""
    try:
        # Ensure the database name here matches your intended target, e.g., sensor_data_rpi
        current_config = POSTGRES_CONFIG.copy()
        # If POSTGRES_DATABASE from .env is different from the default in POSTGRES_CONFIG,
        # load_dotenv should have overridden it. This just ensures clarity.
        current_config['database'] = os.getenv('POSTGRES_DATABASE', 'sensor_data_rpi') 
        connection = psycopg2.connect(**current_config)
        return connection
    except psycopg2.Error as e:
        logging.error(f"❌ Failed to connect to PostgreSQL (DB: {current_config.get('database')}): {e}")
        return None

# Helper function to parse MQTT JSON data structure
def parse_mqtt_data(raw_data_json):
    """Parse the raw MQTT JSON data and extract sensor values"""
    try:
        if isinstance(raw_data_json, str):
            data = json.loads(raw_data_json)
        else:
            data = raw_data_json
        
        # Extract data from the nested structure
        if 'data' in data:
            sensor_data = data['data']
        else:
            sensor_data = data
            
        # Map MQTT field names to our expected format
        mapped_data = {}
        field_mapping = {
            'SOC1': 'cl1_soc',
            'SOC2': 'cl2_soc', 
            'Cluster_1_Voltage': 'cl1_voltage',
            'Cluster_2_Voltage': 'cl2_voltage',
            'Cluster_1_Current': 'cl1_current',
            'Cluster_2_Current': 'cl2_current',
            'OCV_1': 'cl1_temperature',  # Using OCV as temperature placeholder
            'OCV_2': 'cl2_temperature',  # Using OCV as temperature placeholder
            'Total_Cluster_Power': 'system_power',
            'System Condition': 'system_status'
        }
        
        for mqtt_field, db_field in field_mapping.items():
            if mqtt_field in sensor_data:
                mapped_data[db_field] = sensor_data[mqtt_field]
        
        # Add timestamp and device_id
        if 'timestamp' in data:
            mapped_data['timestamp'] = data['timestamp']
        if 'device_id' in data:
            mapped_data['device_id'] = data['device_id']
            
        # Keep all original data in raw_data
        mapped_data['raw_data'] = data
        
        return mapped_data
    except Exception as e:
        logging.error(f"❌ Error parsing MQTT data: {e}")
        return None


@live_data_api.route('/live-data', methods=['POST'])
def receive_live_data():
    """Receive live data from MQTT subscriber and update cache"""
    global latest_live_data
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        # Add a timestamp for when we received it
        # The payload from mqtt_minimal.py already contains 'timestamp', 'device_id', and 'data'
        # We will store it directly.
        latest_live_data = data
        latest_live_data['received_at'] = datetime.now(timezone.utc).isoformat() # Add server-side received timestamp

        # For now, we just update the cache. Database saving can be added later if needed here.
        # If subscriber_workflow dictates saving to DB, that logic would go here or be triggered.
        
        logging.info(f"✅ POST /api/live-data: Data received and cached: {data.get('device_id', 'unknown_device')}")
        return jsonify({"message": "Data received successfully"}), 200
    except Exception as e:
        logging.error(f"❌ Error in POST /api/live-data: {e}")
        return jsonify({"error": "Failed to process request"}), 500


@live_data_api.route('/live-data', methods=['GET'])
def live_data():
    """Get the latest sensor data - prioritize live cache, fallback to PostgreSQL database"""
    
    # Check if we have fresh live data from MQTT subscriber (within last 30 seconds)
    global latest_live_data
    if latest_live_data:
        try:
            received_at = datetime.fromisoformat(latest_live_data['received_at'].replace('Z', '+00:00'))
            age_seconds = (datetime.now(timezone.utc) - received_at).total_seconds()
            
            if age_seconds < 30:  # Use live data if less than 30 seconds old
                logging.debug("✅ Returning fresh live data from cache")
                return jsonify(latest_live_data)
        except Exception as e:
            logging.warning(f"⚠️ Error checking live data age: {e}")
    
    # Fallback to database if no fresh live data
    logging.debug("📊 Falling back to database for live data")
    connection = get_postgres_connection()
    cursor = None # Initialize cursor to None for finally block

    if not connection:
        return jsonify({"error": "Service temporarily unavailable. Database connection failed."}), 503
    
    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = f"""
        SELECT raw_data, timestamp as db_timestamp, device_id as db_device_id 
        FROM {POSTGRES_TABLE}
        ORDER BY timestamp DESC
        LIMIT 1
        """
        cursor.execute(query)
        result = cursor.fetchone()
    except psycopg2.Error as db_err:
        logging.error(f"❌ Database query error in /live-data: {db_err}")
        # Connection will be closed in finally
        return jsonify({"error": "Database query failed"}), 500
    finally:
        if cursor: cursor.close()
        if connection: connection.close()

    if not result:
        return jsonify({"error": "No data available"}), 404 # Return 404 if no data found
    
    db_record = dict(result)
    
    if db_record.get('raw_data'):
        try:
            mqtt_message_obj = json.loads(db_record['raw_data']) if isinstance(db_record['raw_data'], str) else db_record['raw_data']
            if "timestamp" in mqtt_message_obj and "data" in mqtt_message_obj and "device_id" in mqtt_message_obj:
                if isinstance(mqtt_message_obj["timestamp"], datetime):
                    mqtt_message_obj["timestamp"] = mqtt_message_obj["timestamp"].isoformat()
                return jsonify(mqtt_message_obj)
            else:
                logging.warning(f"Live data endpoint: raw_data for latest entry has unexpected structure: {mqtt_message_obj}. Attempting reconstruction for /live-data.")
                # Attempt to reconstruct into {"timestamp": ..., "device_id": ..., "data": {...}}
                # Common fields to exclude from the 'data' sub-object
                excluded_keys = {'timestamp', 'device_id', 'topic', 'id'} # 'id' is db primary key
                
                nested_data_values = {k: v for k, v in mqtt_message_obj.items() if k not in excluded_keys}
                #logging.debug(f"Live data endpoint: Reconstructed nested_data_values: {nested_data_values}")
                
                response_data = {
                    "timestamp": mqtt_message_obj.get('timestamp', db_record['db_timestamp'].isoformat() if db_record.get('db_timestamp') else datetime.now(timezone.utc).isoformat()),
                    "device_id": mqtt_message_obj.get('device_id') or db_record.get('db_device_id', 'unknown_device'),
                    "data": nested_data_values
                }
                return jsonify(response_data)
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing raw_data JSON from DB in /live-data: {e}. Raw data: {db_record['raw_data']}")
        except Exception as e:
            logging.error(f"Unexpected error processing raw_data in /live-data: {e}")

    logging.warning("Falling back to constructing live-data from individual DB columns.")
    db_to_sensorjs_map = {
        'cl1_soc': 'SOC1',
        'cl2_soc': 'SOC2',
        'cl1_voltage': 'Cluster_1_Voltage',
        'cl2_voltage': 'Cluster_2_Voltage',
        'cl1_current': 'Cluster_1_Current',
        'cl2_current': 'Cluster_2_Current',
        'cl1_temperature': 'OCV_1',
        'cl2_temperature': 'OCV_2',
        'system_power': 'Total_Cluster_Power',
        'grid_frequency': 'Grid_Frequency',
        'system_status': 'System Condition'
    }
    data_for_fallback = {}
    for db_col, sensor_js_key in db_to_sensorjs_map.items():
        if db_record.get(db_col) is not None:
             data_for_fallback[sensor_js_key] = db_record[db_col]
        elif db_record.get(db_col.upper()) is not None:
             data_for_fallback[sensor_js_key] = db_record[db_col.upper()]
    fallback_response = {
        "timestamp": db_record['db_timestamp'].isoformat() if db_record.get('db_timestamp') else datetime.now(timezone.utc).isoformat(),
        "device_id": db_record.get('db_device_id', 'unknown_device_fallback'),
        "data": data_for_fallback
    }
    return jsonify(fallback_response)


@live_data_api.route('/historical-data', methods=['GET'])
def historical_data():
    """Get historical sensor data from PostgreSQL database - compatible with existing frontend"""
    # Get query parameters - matching the existing hist_data.py API
    range_param = request.args.get('range', '30m')
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')
    device_id = request.args.get('device_id', None)
    
    connection = get_postgres_connection()
    cursor = None
    if not connection:
        return jsonify({"error": "Failed to connect to database"}), 500
    
    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Parse time range like the original hist_data.py
        now = datetime.now(set_timezone)
        start_time = None
        end_time = now
        
        if range_param == 'custom' and start_date_str and end_date_str:
            try:
                start_time = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
                end_time = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
            except ValueError:
                logging.error(f"Invalid custom date format: start={start_date_str}, end={end_date_str}")
                return jsonify({"error": "Invalid custom date format. Use YYYY-MM-DDTHH:MM"}), 400
        else:
            try:
                num = int(range_param[:-1])
                unit = range_param[-1]
                if unit == 'm': 
                    delta = timedelta(minutes=num)
                elif unit == 'h': 
                    delta = timedelta(hours=num)
                elif unit == 'd': 
                    delta = timedelta(days=num)
                elif unit == 'w': 
                    delta = timedelta(weeks=num)
                else: 
                    delta = timedelta(minutes=30)  # Default fallback
                start_time = now - delta
            except ValueError:
                logging.error(f"Invalid range parameter: {range_param}")
                return jsonify({"error": "Invalid range parameter format. Use e.g., 30m, 1h, 7d, 4w"}), 400
        
        if not start_time:
            start_time = now - timedelta(minutes=30)  # Default if something went wrong
        
        logging.info(f"📅 Querying historical data from {start_time.isoformat()} to {end_time.isoformat()}")
        
        # Build query with time filtering
        where_conditions = ["timestamp >= %s", "timestamp <= %s"]
        params = [start_time, end_time]
        
        # Device filter
        if device_id:
            where_conditions.append("device_id = %s")
            params.append(device_id)
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
        SELECT * FROM {POSTGRES_TABLE}
        WHERE {where_clause}
        ORDER BY timestamp ASC
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Process results to match frontend expectations
        historical_data = []
        for row in results:
            row_data = dict(row)
            
            # Parse raw MQTT data if available to get full sensor data
            processed_row = {}
            if row_data.get('raw_data'):
                parsed_data = parse_mqtt_data(row_data['raw_data'])
                if parsed_data and 'raw_data' in parsed_data:
                    mqtt_data = parsed_data['raw_data']
                    if 'data' in mqtt_data:
                        # Use all the MQTT sensor data
                        processed_row = mqtt_data['data'].copy()
                        # Ensure timestamp is properly formatted
                        if mqtt_data.get('timestamp'):
                            processed_row['timestamp'] = mqtt_data['timestamp']
                        else:
                            processed_row['timestamp'] = row_data['timestamp'].isoformat()
                        historical_data.append(processed_row)
                        continue
            
            # Fallback to database fields - map back to MQTT field names for frontend compatibility
            processed_row = {
                'timestamp': row_data['timestamp'].isoformat() if row_data.get('timestamp') else None,
                'SOC1': row_data.get('cl1_soc'),
                'SOC2': row_data.get('cl2_soc'),
                'Cluster_1_Voltage': row_data.get('cl1_voltage'),
                'Cluster_2_Voltage': row_data.get('cl2_voltage'),
                'Cluster_1_Current': row_data.get('cl1_current'),
                'Cluster_2_Current': row_data.get('cl2_current'),
                'OCV_1': row_data.get('cl1_temperature'),
                'OCV_2': row_data.get('cl2_temperature'),
                'Total_Cluster_Power': row_data.get('system_power'),
                'System Condition': row_data.get('system_status'),
                # Add other common MQTT fields with default values
                'Digital Status Reg 1': 0,
                'Digital Status Reg 2': 0,
                'Digital Status Reg 3': 0,
                'Digital Status Reg 4': 0,
                'Pressure_1': 0,
                'Pressure_2': 0,
                'Pressure_3': 0,
                'Pressure_4': 0,
                'HVDC_Voltage': 0,
                'HVDC_Current': 0,
                'HVDC_Power': 0,
                'Primary_Pump_Ramp_PID_SP_FB': 0,
                'Secondary_Pump_Ramp_PID_SP_FB': 0,
                'Cluster_1_Power': 0,
                'Cluster_2_Power': 0,
                'Cluster-1 Condition': 3,
                'Cluster-2 Condition': 3,
                'Zekalab system State': 1,
                'Battery Status': 1,
                'CL_1 PowerMode': 2,
                'CL_2 PowerMode': 2
            }
            historical_data.append(processed_row)
        
        cursor.close()
        connection.close()
        
        # Return in the format expected by historical.js (just an array of data points)
        return jsonify(historical_data)
        
    except psycopg2.Error as e:
        logging.error(f"❌ Database error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": "Database query failed"}), 500
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": "Internal server error"}), 500


@live_data_api.route('/sensor-summary')
def sensor_summary():
    """Get summary statistics of sensor data"""
    connection = get_postgres_connection()
    if not connection:
        return jsonify({"error": "Failed to connect to database"}), 500
    
    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get basic statistics
        stats_query = f"""
        SELECT 
            COUNT(*) as total_records,
            MIN(timestamp) as first_record,
            MAX(timestamp) as latest_record,
            COUNT(DISTINCT device_id) as unique_devices
        FROM {POSTGRES_TABLE}
        """
        
        cursor.execute(stats_query)
        stats = dict(cursor.fetchone())
        
        # Get device list
        devices_query = f"""
        SELECT device_id, COUNT(*) as record_count, MAX(timestamp) as last_seen
        FROM {POSTGRES_TABLE}
        GROUP BY device_id
        ORDER BY last_seen DESC
        """
        
        cursor.execute(devices_query)
        devices = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'statistics': stats,
            'devices': devices
        })
        
    except psycopg2.Error as e:
        logging.error(f"❌ Database error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": "Database query failed"}), 500
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": "Internal server error"}), 500


@live_data_api.route('/test-db')
def test_db_connection():
    """Test PostgreSQL database connection and show table structure"""
    connection = get_postgres_connection()
    if not connection:
        return jsonify({"error": "Failed to connect to database"}), 500
    
    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Test connection
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (POSTGRES_TABLE,))
        table_exists = cursor.fetchone()[0]
        
        # Get table structure if it exists
        columns = []
        if table_exists:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (POSTGRES_TABLE,))
            columns = [dict(row) for row in cursor.fetchall()]
        
        # Get row count
        row_count = 0
        if table_exists:
            cursor.execute(f"SELECT COUNT(*) FROM {POSTGRES_TABLE};")
            row_count = cursor.fetchone()[0]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "database_version": dict(version),
            "table_exists": table_exists,
            "table_name": POSTGRES_TABLE,
            "columns": columns,
            "row_count": row_count,
            "connection_config": {
                "host": POSTGRES_CONFIG['host'],
                "port": POSTGRES_CONFIG['port'],
                "database": POSTGRES_CONFIG['database'],
                "user": POSTGRES_CONFIG['user']
            }
        })
        
    except psycopg2.Error as e:
        logging.error(f"❌ Database error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        if connection:
            connection.close()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


# Legacy functions - kept for compatibility but not used with PostgreSQL
def store_data_to_db(data_to_store, timestamp_val=None):
    """Legacy function - no longer used with PostgreSQL backend"""
    logging.info("store_data_to_db called - PostgreSQL backend handles data storage via MQTT subscriber")
    pass

def add_dynamic_columns():
    """Legacy function - no longer needed with PostgreSQL backend"""
    logging.info("add_dynamic_columns called - PostgreSQL schema is managed by MQTT subscriber")
    pass


@live_data_api.route('/test-blueprint')
def test_blueprint_route():
    return jsonify({"message": "Live Data Blueprint test OK"}), 200


