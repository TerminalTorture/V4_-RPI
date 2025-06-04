from flask import Blueprint, request, jsonify, Response, make_response
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
import io
import csv
import logging
import psycopg2
import psycopg2.extras
import json
import os

# --- Use config loader --- 
from api.config_loader import REGISTER_CONFIG

# Import centralized timezone configuration
from api.timezone_config import set_timezone

# PostgreSQL connection helper
def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        # Load database configuration from environment
        from dotenv import load_dotenv
        load_dotenv()
        
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'vflow_data'),
            user=os.getenv('DB_USER', 'vflow_user'),
            password=os.getenv('DB_PASSWORD', 'vflow_password'),
            port=os.getenv('DB_PORT', 5432)
        )
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to PostgreSQL: {e}")
        return None

def parse_mqtt_data(raw_data):
    """Parse raw_data JSONB field from PostgreSQL to extract sensor values"""
    try:
        if isinstance(raw_data, str):
            data = json.loads(raw_data)
        else:
            data = raw_data
        
        # Extract sensor data from MQTT JSON structure
        sensor_data = {}
        
        # Handle different possible MQTT structures
        if 'data' in data and isinstance(data['data'], dict):
            # Structure: {"data": {"sensor1": value1, "sensor2": value2}}
            sensor_data.update(data['data'])
        elif isinstance(data, dict):
            # Direct structure: {"sensor1": value1, "sensor2": value2}
            # Filter out metadata fields
            for key, value in data.items():
                if key not in ['timestamp', 'device_id', 'message_type']:
                    sensor_data[key] = value
        
        return sensor_data
    except Exception as e:
        logging.error(f"Error parsing MQTT data: {e}")
        return {}

# Define Blueprint
historical_data_api = Blueprint('historical_data_api', __name__)

@historical_data_api.route('/historical-data/export', methods=['GET'])
@login_required
def export_historical_csv():
    """Export historical data as CSV from PostgreSQL"""
    # Admin check (uncomment if needed)
    # if not current_user.is_admin:
    #     return jsonify({"error": "Admin access required to download data."}), 403

    range_param = request.args.get('range', '30d')
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')
    
    now = datetime.now(set_timezone)
    start_time = None
    end_time = now

    try:
        if range_param == "custom" and start_date_str and end_date_str:
            # Parse custom date range
            start_time = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
            end_time = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
        else:
            # Parse range parameter like '30m', '1h', '7d', '4w'
            num = int(range_param[:-1])
            unit = range_param[-1]
            
            if unit == 'm':
                start_time = now - timedelta(minutes=num)
            elif unit == 'h':
                start_time = now - timedelta(hours=num)
            elif unit == 'd':
                start_time = now - timedelta(days=num)
            elif unit == 'w':
                start_time = now - timedelta(weeks=num)
            else:
                start_time = now - timedelta(days=30)  # Default to 30 days
                
    except (ValueError, IndexError):
        start_time = now - timedelta(days=30)  # Default fallback

    # Get data from PostgreSQL
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Query sensor data within time range
        query = """
            SELECT timestamp, device_id, raw_data 
            FROM sensor_data 
            WHERE timestamp >= %s AND timestamp <= %s 
            ORDER BY timestamp ASC
        """
        
        cur.execute(query, (start_time, end_time))
        records = cur.fetchall()
        
        if not records:
            return jsonify({"error": "No data found for the specified range"}), 404

        # Create CSV data
        csv_buffer = io.StringIO()
        
        # Get all possible sensor names from register config for CSV headers
        all_sensor_names = set()
        historical_sensors = REGISTER_CONFIG.get('by_view', {}).get('historical', [])
        for reg in historical_sensors:
            all_sensor_names.add(reg['name'])
        
        # Also check actual data to get any additional sensor names
        for record in records[:10]:  # Check first 10 records for sensor names
            mqtt_data = parse_mqtt_data(record['raw_data'])
            all_sensor_names.update(mqtt_data.keys())
        
        all_sensor_names = sorted(list(all_sensor_names))
        
        # Create CSV headers
        headers = ['timestamp', 'device_id'] + all_sensor_names
        writer = csv.DictWriter(csv_buffer, fieldnames=headers)
        writer.writeheader()
        
        # Write data rows
        for record in records:
            mqtt_data = parse_mqtt_data(record['raw_data'])
            
            row = {
                'timestamp': record['timestamp'].isoformat(),
                'device_id': record['device_id']
            }
            
            # Add sensor values
            for sensor_name in all_sensor_names:
                row[sensor_name] = mqtt_data.get(sensor_name, '')
            
            writer.writerow(row)
        
        cur.close()
        conn.close()
        
        # Create response
        csv_content = csv_buffer.getvalue()
        csv_buffer.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=sensor_data_{range_param}.csv'
        
        logging.info(f"Exported {len(records)} records for range {range_param}")
        return response
        
    except Exception as e:
        logging.error(f"Error exporting CSV: {e}")
        if conn:
            conn.close()
        return jsonify({"error": f"Export failed: {str(e)}"}), 500

@historical_data_api.route('/historical-data/columns', methods=['GET'])
@login_required
def get_available_columns():
    """Get available sensor columns from PostgreSQL data"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get recent records to determine available sensor columns
        query = """
            SELECT raw_data 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 50
        """
        
        cur.execute(query)
        records = cur.fetchall()
        
        # Extract all unique sensor names
        all_sensors = set()
        for record in records:
            mqtt_data = parse_mqtt_data(record['raw_data'])
            all_sensors.update(mqtt_data.keys())
        
        cur.close()
        conn.close()
        
        # Convert to list and sort
        sensor_list = sorted(list(all_sensors))
        
        # Add metadata about sensors from config
        columns_info = []
        for sensor_name in sensor_list:
            # Find register info from config
            reg_info = None
            for reg in REGISTER_CONFIG.get('raw', []):
                if reg['name'] == sensor_name:
                    reg_info = reg
                    break
            
            column_info = {
                'name': sensor_name,
                'type': 'numeric',  # Default type
                'unit': reg_info.get('unit', '') if reg_info else '',
                'description': reg_info.get('description', '') if reg_info else ''
            }
            columns_info.append(column_info)
        
        return jsonify({
            "columns": columns_info,
            "total_count": len(columns_info)
        })
        
    except Exception as e:
        logging.error(f"Error getting columns: {e}")
        if conn:
            conn.close()
        return jsonify({"error": f"Failed to get columns: {str(e)}"}), 500

@historical_data_api.route('/historical-data/latest', methods=['GET'])
@login_required
def get_latest_timestamp():
    """Get the timestamp of the latest data point"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur = conn.cursor()
        
        query = "SELECT MAX(timestamp) as latest_timestamp FROM sensor_data"
        cur.execute(query)
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result and result[0]:
            return jsonify({
                "latest_timestamp": result[0].isoformat(),
                "has_data": True
            })
        else:
            return jsonify({
                "latest_timestamp": None,
                "has_data": False
            })
            
    except Exception as e:
        logging.error(f"Error getting latest timestamp: {e}")
        if conn:
            conn.close()
        return jsonify({"error": f"Failed to get latest timestamp: {str(e)}"}), 500
