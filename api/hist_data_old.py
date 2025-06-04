from flask import Blueprint, request, jsonify, Response, make_response, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone # Import timezone
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
    # ... (Admin check logic remains the same) ...
    # if not current_user.is_admin:
    #     return jsonify({"error": "Admin access required to download data."}), 403

    range_param = request.args.get('range', '30d')
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')
    # Get variables, default to all numeric historical variables if none specified
    requested_variables = request.args.get('variables')
    if requested_variables:
        variables_to_export = requested_variables.split(",")
    else:
        # Default: Get all variables marked for 'historical' view and are numeric
        variables_to_export = [
            reg['name'] for reg in REGISTER_CONFIG['by_view'].get('historical', [])
            if hasattr(SensorData, reg['name'].lower()) # Check if column exists in DB model
        ]

    now = datetime.now(set_timezone) # Use application timezone
    start_time = None
    end_time = now

    try:
        if range_param == "custom" and start_date_str and end_date_str:
            # Interpret frontend's local datetime string as application timezone
            start_time = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
            end_time = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
        else:
            # Simplified range parsing (assuming format like '30m', '1h', '7d', '4w')
            num = int(range_param[:-1])
            unit = range_param[-1]
            if unit == 'm': delta = timedelta(minutes=num)
            elif unit == 'h': delta = timedelta(hours=num)
            elif unit == 'd': delta = timedelta(days=num)
            elif unit == 'w': delta = timedelta(weeks=num)
            else: delta = timedelta(days=30) # Default fallback
            start_time = now - delta
    except ValueError as e:
        logging.error(f"Error parsing date/range for export: {e}")
        return jsonify({"error": "Invalid date format or range parameter"}), 400

    if not start_time:
         start_time = now - timedelta(days=30) # Default if parsing failed

    logging.info(f"Exporting data from {start_time.isoformat()} to {end_time.isoformat()} for variables: {variables_to_export}")

    # Query data - use lowercase column names
    columns_to_select = [SensorData.timestamp]
    valid_variables_in_query = []
    for var in variables_to_export:
        col_name = var.lower()
        if hasattr(SensorData, col_name):
            columns_to_select.append(getattr(SensorData, col_name))
            valid_variables_in_query.append(var) # Keep original case for header
        else:
            logging.warning(f"Variable '{var}' requested for export not found in SensorData model.")

    if len(columns_to_select) <= 1:
        return jsonify({"error": "No valid variables selected for export."}), 400

    query = db.session.query(*columns_to_select).filter(
        SensorData.timestamp >= start_time,
        SensorData.timestamp <= end_time
    ).order_by(SensorData.timestamp)

    records = query.all()

    # Convert to CSV
    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    # Use the original case names for the header
    writer.writerow(["timestamp"] + valid_variables_in_query)

    for row in records:
        # Convert stored naive timestamp to aware application timezone for output
        record_timestamp_aware = row[0].replace(tzinfo=set_timezone)
        formatted_row = [record_timestamp_aware.isoformat()] + list(row[1:])
        writer.writerow(formatted_row)

    response = Response(csv_output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=historical_data_{start_time.strftime('%Y%m%d')}_{end_time.strftime('%Y%m%d')}.csv"

    return response

@historical_data_api.route('/historical-data', methods=['GET'])
def get_historical_data():
    """Fetch historical sensor data based on user-selected time range."""
    try:
        range_param = request.args.get('range', '30m')
        start_date_str = request.args.get('start')
        end_date_str = request.args.get('end')
        now = datetime.now(set_timezone) # Use application timezone

        logging.info(f"📩 Received Historical Data Request: range={range_param}, start={start_date_str}, end={end_date_str}, current_server_time_app_tz={now.isoformat()}")

        start_time = None
        end_time = now

        if range_param == 'custom' and start_date_str and end_date_str:
            try:
                # Adjust format if needed based on how frontend sends it
                start_time = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
                end_time = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=set_timezone)
            except ValueError:
                logging.error(f"Invalid custom date format: start={start_date_str}, end={end_date_str}")
                return jsonify({"error": "Invalid custom date format. Use YYYY-MM-DDTHH:MM"}), 400
        else:
            try:
                num = int(range_param[:-1])
                unit = range_param[-1]
                if unit == 'm': delta = timedelta(minutes=num)
                elif unit == 'h': delta = timedelta(hours=num)
                elif unit == 'd': delta = timedelta(days=num)
                elif unit == 'w': delta = timedelta(weeks=num)
                else: delta = timedelta(minutes=30) # Default fallback
                start_time = now - delta
            except ValueError:
                 logging.error(f"Invalid range parameter: {range_param}")
                 return jsonify({"error": "Invalid range parameter format. Use e.g., 30m, 1h, 7d, 4w"}), 400

        if not start_time:
             start_time = now - timedelta(minutes=30) # Default if something went wrong

        logging.info(f"📅 Querying historical data from {start_time.isoformat()} to {end_time.isoformat()} (App Timezone)")

        # Determine which columns (variables) to fetch - all numeric ones by default
        columns_to_select = [SensorData.timestamp]
        column_names_map = {'timestamp': 'timestamp'} # Map lowercase back to original case
        for reg_name, reg_info in REGISTER_CONFIG['by_name'].items():
            col_name = reg_name.lower()
            if hasattr(SensorData, col_name):
                columns_to_select.append(getattr(SensorData, col_name))
                column_names_map[col_name] = reg_name # Store mapping

        records = db.session.query(*columns_to_select).filter(
            SensorData.timestamp >= start_time,
            SensorData.timestamp <= end_time
        ).order_by(SensorData.timestamp).all()

        if not records:
            logging.info("No historical records found for the specified range.")
            return jsonify([]) # Return empty list if no data

        # Convert records to list of dictionaries using original variable names
        result_list = []
        column_keys = [col.key for col in columns_to_select] # Get the actual column names (lowercase)

        for record in records:
            entry = {}
            for i, key in enumerate(column_keys):
                original_name = column_names_map.get(key, key) # Get original case name
                value = record[i]
                if isinstance(value, datetime):
                    # Convert stored naive timestamp to aware application timezone for output
                    value = value.replace(tzinfo=set_timezone)
                    entry[original_name] = value.isoformat() # Use ISO format for timestamp
                else:
                    entry[original_name] = value
            result_list.append(entry)

        logging.info(f"📊 Returning {len(result_list)} historical records.")
        return jsonify(result_list)

    except Exception as e:
        logging.error(f"❌ Error fetching historical data: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred while fetching historical data."}), 500

@historical_data_api.route('/get-variables', methods=['GET'])
def get_variables():
    """Returns a list of variables available for historical data selection."""
    # Return variables that have a corresponding column in SensorData
    available_vars = [
        reg['name'] for reg_name, reg in REGISTER_CONFIG['by_name'].items()
        if hasattr(SensorData, reg_name.lower())
    ]
    return jsonify(available_vars)

@historical_data_api.route('/historical-variables', methods=['GET'])
def get_historical_variables():
    """Returns a list of variables available for historical querying."""
    available_vars = []
    # Determine available columns dynamically from SensorData model
    for column in SensorData.__table__.columns:
        # Exclude primary key and potentially timestamp if not queryable directly
        if column.name not in ['id', 'timestamp']:
            # Try to find original case name from REGISTER_CONFIG
            original_name = next((name for name, info in REGISTER_CONFIG['by_name'].items() if name.lower() == column.name), column.name)
            available_vars.append(original_name)
    return jsonify(sorted(available_vars))

@historical_data_api.route('/historical-snapshot', methods=['GET'])
def get_historical_snapshot():
    """Gets the latest recorded value for all historical variables."""
    latest_data = {}
    try:
        # Find the timestamp of the most recent record
        latest_record = SensorData.query.order_by(desc(SensorData.timestamp)).first()
        if not latest_record:
            return jsonify({}) # No data yet

        # Assume latest_record.timestamp is application timezone, make it aware for isoformat
        aware_timestamp = latest_record.timestamp.replace(tzinfo=set_timezone)
        latest_data['timestamp'] = aware_timestamp.isoformat() 

        # Fetch values for all relevant columns from that latest record
        for column in SensorData.__table__.columns:
            if column.name not in ['id', 'timestamp']:
                 value = getattr(latest_record, column.name)
                 # Find original case name
                 original_name = next((name for name, info in REGISTER_CONFIG['by_name'].items() if name.lower() == column.name), column.name)
                 latest_data[original_name] = value

        return jsonify(latest_data)

    except Exception as e:
        logging.error(f"Error fetching historical snapshot: {e}", exc_info=True)
        return jsonify({"error": "Internal server error fetching snapshot"}), 500

