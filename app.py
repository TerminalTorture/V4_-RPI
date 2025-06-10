import os
import sys
import threading
# import subprocess # No longer used
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor # , ProcessPoolExecutor # ProcessPoolExecutor not used

# --- Additional imports for minimal MQTT client ---
import paho.mqtt.client as mqtt
import json
import time # For unique client_id and potentially other timing
import requests
# logging, os, datetime, timezone should already be available or imported
# Ensure timezone is available if datetime.now(timezone.utc) is used.
from datetime import timezone
# --- End additional imports ---

# --- Environment Variable Loading ---
project_root = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(project_root, '.env')
try:
    from dotenv import load_dotenv
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)
        print(f"✅ app.py: Environment variables loaded from {dotenv_path}")
    else:
        print(f"⚠️ app.py: .env file not found at {dotenv_path}. Using system environment variables only.")
except ImportError:
    print("⚠️ app.py: python-dotenv not available, using system environment variables only")
# --- End Environment Variable Loading ---

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from api.config_loader import REGISTER_CONFIG # Import the loaded config
# from api.live_data import store_data_to_db, add_dynamic_columns # No longer needed here
from api.live_data import live_data_api # Only live_data_api is needed for blueprint registration
from api.hist_data import historical_data_api
from api.extensions import db
from datetime import datetime, timedelta # UTC removed, set_timezone will be used
from api.timezone_config import set_timezone # ADDED: Import set_timezone
import logging # Add logging import
import yaml # Add this import
import psycopg2 # Added for psycopg2 usage

# Import the MQTT Subscriber class
# from api.mqtt_subscriber import VFlowMQTTSubscriber # REMOVE THIS LINE

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# PostgreSQL Database Configuration for Flask-SQLAlchemy (primarily for User model)
# The sensor_data table is managed by mqtt_subscriber.py, not by Flask's SQLAlchemy models here.
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://sensor_user:Master123@localhost:5432/sensor_data')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# logging.getLogger('werkzeug').disabled = True # Consider enabling werkzeug logs for debugging

# Setup logging
logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(levelname)s - %(message)s')


# Initialize extensions
db.init_app(app) # For User model
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# Register API Blueprints
app.register_blueprint(live_data_api, url_prefix='/api')
app.register_blueprint(historical_data_api, url_prefix='/api')

# --- Add API endpoint for register definitions ---
@app.route('/api/registers/definitions')
@login_required # Or remove if definitions should be public
def get_register_definitions():
    # Return the processed configuration relevant for the frontend
    # Filter or structure as needed, here returning groups and raw list
    definitions = {
        "registers": REGISTER_CONFIG.get("raw", []),
        "groups": REGISTER_CONFIG.get("by_group", {}),
        "views": REGISTER_CONFIG.get("by_view", {})
        # Add other processed parts of the config if needed by frontend
    }
    return jsonify(definitions)
# --- Endpoint added ---


class User (UserMixin, db.Model): # User model remains for authentication
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80),unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user (user_id):
    return db.session.get(User, int(user_id)) # Keep for user authentication


# SensorData model, collect_sensor_data, and related lock are removed
# as data ingestion is handled by api/mqtt_subscriber.py

# --- Modify collect_sensor_data ---
# The collect_sensor_data function is removed. Data collection is handled by mqtt_subscriber.py

# ... (Scheduler setup remains the same)
executors = {
    'default': ThreadPoolExecutor(1) # Only allow 1 thread at a time
}

def delete_old_data():
    """Deletes sensor data older than 30 days from the database."""
    # This function now needs to use raw SQL or a different mechanism if SensorData model is removed,
    # or it should be part of the mqtt_subscriber service if that's more appropriate.
    # For now, let's assume direct psycopg2 usage for this task if it must remain in app.py
    try:
        cutoff_date = datetime.now(set_timezone) - timedelta(days=30)
        
        # Use psycopg2 to connect and delete old data from the 'sensor_data' table
        # This avoids reliance on a Flask-SQLAlchemy model for this table
        pg_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DATABASE', 'sensor_data'), # Default to sensor_data
            'user': os.getenv('POSTGRES_USER', 'sensor_user'),         # Default to sensor_user
            'password': os.getenv('POSTGRES_PASSWORD', 'Master123')   # Default to Master123
        }
        conn = None
        deleted_count = 0
        try:
            conn = psycopg2.connect(**pg_config)
            conn.autocommit = True # Use autocommit for delete operations
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {os.getenv('POSTGRES_TABLE', 'sensor_data')} WHERE timestamp < %s", (cutoff_date,))
            deleted_count = cur.rowcount
            cur.close()
        except Exception as e:
            logging.error(f"Error during raw SQL delete_old_data: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

        if deleted_count > 0:
            logging.info(f"Deleted {deleted_count} records older than {cutoff_date} using direct SQL.")
        else:
            logging.info("No old records found to delete using direct SQL.")
            
    except Exception as e:
        logging.error(f"Error in delete_old_data job: {e}", exc_info=True)


def start_scheduler():
    scheduler = BackgroundScheduler(executors=executors)
    # Schedule data collection (e.g., every 5 seconds) - REMOVED
    # scheduler.add_job(collect_sensor_data, 'interval', seconds=5, id='collect_data_job', replace_existing=True)
    # Schedule old data deletion (e.g., daily at 3 AM)
    scheduler.add_job(delete_old_data, 'cron', hour=3, id='delete_old_data_job', replace_existing=True)
    scheduler.start()
    logging.info("Background scheduler started (delete_old_data job only).")


# --- Create database tables AFTER dynamic columns are added ---
with app.app_context():
    logging.info("Initializing database for User model...")
    # add_dynamic_columns() # Removed - SensorData model and its columns are managed by mqtt_subscriber
    db.create_all() # Creates tables for models defined in Flask-SQLAlchemy (i.e., User model)
    logging.info("Database tables for User model created (if they didn't exist).")

    # Create default admin user if not exists
    if not User.query.filter_by(username='admin').first():
        # Default password is 'admin', ensure this is changed in production
        hashed_password = generate_password_hash('admin', method='pbkdf2:sha256')
        # Create a non-admin user 'vflow' with password 'password'
        # To create an admin: User(username='admin', password=generate_password_hash('admin_password'), is_admin=True)
        # For consistency with login error logs, let's use 'vflow' as the default non-admin
        default_user_username = os.getenv('DEFAULT_USER_USERNAME', 'vflow')
        default_user_password = os.getenv('DEFAULT_USER_PASSWORD', 'password') # Ensure this is secure or changed
        
        if not User.query.filter_by(username=default_user_username).first():
            hashed_password_default = generate_password_hash(default_user_password, method='pbkdf2:sha256')
            default_user = User(username=default_user_username, password=hashed_password_default, is_admin=False)
            db.session.add(default_user)
            db.session.commit()
            logging.info(f"Default user '{default_user_username}' created.")
        else:
            logging.info(f"Default user '{default_user_username}' already exists.")

        # Create admin user if it specifically doesn't exist.
        admin_username = os.getenv('ADMIN_USER_USERNAME', 'admin')
        admin_password = os.getenv('ADMIN_USER_PASSWORD', 'admin') # Ensure this is secure or changed
        if admin_username != default_user_username and not User.query.filter_by(username=admin_username).first():
            hashed_password_admin = generate_password_hash(admin_password, method='pbkdf2:sha256')
            admin_user = User(username=admin_username, password=hashed_password_admin, is_admin=True)
            db.session.add(admin_user)
            db.session.commit()
            logging.info(f"Admin user '{admin_username}' created.")
        elif admin_username != default_user_username :
             logging.info(f"Admin user '{admin_username}' already exists or is same as default user.")


# --- Definitions for Minimal MQTT Client (adapted from mqtt_minimal.py) ---

# Setup a logger for the minimal MQTT client part, consistent with app.py's logging
mqtt_minimal_logger = logging.getLogger("mqtt_minimal_client")

class MinimalFlaskAPIClient: # Renamed to avoid potential future class name collisions
    def __init__(self):
        # Use FLASK_RUN_PORT for consistency if the API is running on a configurable port
        flask_port = os.getenv('FLASK_RUN_PORT', 5001)
        self.endpoint = f"http://localhost:{flask_port}/api/live-data"
        self.timeout = 5.0
        self.success_count = 0
        self.fail_count = 0
    
    def send_data(self, data):
        try:
            payload = {
                'timestamp': data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'device_id': data.get('device_id', 'unknown_device'),
                'data': data # This is the original data from MQTT
            }
            # Use the specific logger
            mqtt_minimal_logger.info(f"Attempting to send to Flask API. Endpoint: {self.endpoint}, Payload: {json.dumps(payload)}")

            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                self.success_count += 1
                mqtt_minimal_logger.info(f"✅ Flask API success #{self.success_count}")
                return True
            else:
                self.fail_count += 1
                mqtt_minimal_logger.error(f"❌ Flask API failed #{self.fail_count} to {self.endpoint}: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.ConnectionError as e:
            self.fail_count += 1
            mqtt_minimal_logger.error(f"❌ Flask API connection error #{self.fail_count} for {self.endpoint}: {e}")
            return False
        except Exception as e:
            self.fail_count += 1
            mqtt_minimal_logger.error(f"❌ Flask API generic error #{self.fail_count} for {self.endpoint}: {e}")
            return False

# Global variables for the minimal MQTT client context
minimal_flask_client = MinimalFlaskAPIClient()
minimal_message_count = 0

def on_connect_minimal(client, userdata, flags, rc):
    mqtt_minimal_logger.info(f"Minimal MQTT client connected to broker (code: {rc})")
    if rc == 0:
        client.subscribe("vflow/data/bulk", qos=0) # Using QoS 0 as in mqtt_minimal.py
        mqtt_minimal_logger.info("Minimal MQTT client subscribed to vflow/data/bulk")
    else:
        mqtt_minimal_logger.error(f"Minimal MQTT client failed to connect, return code {rc}\\n")

def on_message_minimal(client, userdata, msg):
    global minimal_message_count, minimal_flask_client
    minimal_message_count += 1
    
    mqtt_minimal_logger.info(f"📨 Minimal MQTT: Message #{minimal_message_count} received from {msg.topic}")
    
    try:
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)
        
        success = minimal_flask_client.send_data(data)
        
        if success:
            mqtt_minimal_logger.info(f"✅ Minimal MQTT: Message #{minimal_message_count} processed successfully by API")
        else:
            mqtt_minimal_logger.warning(f"⚠️ Minimal MQTT: Message #{minimal_message_count} API send failed, but received from broker.")
        
    except json.JSONDecodeError as e:
        mqtt_minimal_logger.error(f"❌ Minimal MQTT: Error decoding JSON for message #{minimal_message_count}: {e}. Payload: {msg.payload.decode('utf-8', errors='ignore')}")
    except Exception as e:
        mqtt_minimal_logger.error(f"❌ Minimal MQTT: Error processing message #{minimal_message_count}: {e}")

def on_disconnect_minimal(client, userdata, rc):
    if rc != 0:
        mqtt_minimal_logger.warning(f"Minimal MQTT client disconnected unexpectedly (code: {rc})")
    else:
        mqtt_minimal_logger.info("Minimal MQTT client disconnected gracefully.")

def run_minimal_mqtt_thread():
    """Runs the minimal MQTT subscriber logic in a thread."""
    global minimal_flask_client, minimal_message_count # Ensure globals are accessible
    minimal_message_count = 0 # Reset count on start
    minimal_flask_client = MinimalFlaskAPIClient() # Re-initialize client for fresh counts

    client_id = f"vflow_minimal_flask_app_{int(time.time() * 1000)}"
    client = mqtt.Client(client_id=client_id)
    client.on_connect = on_connect_minimal
    client.on_message = on_message_minimal
    client.on_disconnect = on_disconnect_minimal

    broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
    broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))

    mqtt_minimal_logger.info(f"🚀 Starting Minimal MQTT Subscriber Thread for Flask App")
    mqtt_minimal_logger.info(f"MQTT Broker: {broker_host}:{broker_port}")
    mqtt_minimal_logger.info(f"Target Flask API: {minimal_flask_client.endpoint}")
    mqtt_minimal_logger.info("="*60)
    
    retry_delay = 5 # seconds
    max_retries = 5 # None for infinite
    retries = 0

    while True: # Outer loop for reconnections
        try:
            client.connect(broker_host, broker_port, 60)
            mqtt_minimal_logger.info("Minimal MQTT client attempting to connect...")
            client.loop_forever() # This is blocking until disconnect
            # If loop_forever() exits cleanly (e.g. client.disconnect() called elsewhere), break outer loop.
            # However, on_disconnect will be called for unexpected disconnects, loop_forever might raise exception.
            mqtt_minimal_logger.info("Minimal MQTT client loop_forever exited.")
            break # Exit while true if loop_forever finishes without error.
        except ConnectionRefusedError:
            mqtt_minimal_logger.error(f"Minimal MQTT: Connection refused by broker {broker_host}:{broker_port}.")
        except TimeoutError:
            mqtt_minimal_logger.error(f"Minimal MQTT: Connection attempt to {broker_host}:{broker_port} timed out.")
        except mqtt.MQTTException as e:
            mqtt_minimal_logger.error(f"Minimal MQTT: MQTT specific error: {e}")
        except Exception as e:
            mqtt_minimal_logger.error(f"Minimal MQTT: Unexpected error in connection/loop: {e}", exc_info=True)
        
        # If loop_forever was interrupted by an error or disconnect, on_disconnect handles logging.
        # We are now outside loop_forever, so we need to attempt to reconnect.
        
        if max_retries is not None and retries >= max_retries:
            mqtt_minimal_logger.error(f"Minimal MQTT: Max retries ({max_retries}) reached. Stopping attempts.")
            break

        retries += 1
        mqtt_minimal_logger.info(f"Minimal MQTT: Disconnected. Retrying connection in {retry_delay}s (attempt {retries})...")
        time.sleep(retry_delay)
        # Increase delay for next retry? (Exponential backoff could be added here)
        # retry_delay = min(retry_delay * 2, 60) # Example exponential backoff up to 60s

    mqtt_minimal_logger.info("Minimal MQTT subscriber thread finished.")
    # Final stats can be logged here if desired, similar to standalone mqtt_minimal.py
    mqtt_minimal_logger.info(f"📊 Minimal MQTT Final Stats: Messages: {minimal_message_count}, Flask API: {minimal_flask_client.success_count}✅/{minimal_flask_client.fail_count}❌")


# --- End Definitions for Minimal MQTT Client ---


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
@login_required
def index():
    # Pass authentication status to the template
    # Add current_time for cache busting static files
    current_time_val = datetime.now(set_timezone).timestamp()
    return render_template('index.html', is_authenticated=current_user.is_authenticated, current_time=current_time_val)

@app.route('/historical')
@login_required
def historical():
    return render_template('historical.html')

@app.route('/settings')
@login_required
def settings():
    # Get Modbus config from REGISTER_CONFIG, which loads from register_config.yaml
    # Provide defaults in case the keys are missing in the loaded config
    modbus_ip = REGISTER_CONFIG.get('modbus_ip', "192.168.1.25")
    modbus_port = REGISTER_CONFIG.get('modbus_port', 1502) # Ensure it's treated as int if needed by template
    return render_template('settings.html', modbus_ip=modbus_ip, modbus_port=modbus_port)


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.route('/api/set-modbus-config', methods=['POST'])
@login_required
def set_modbus_config():
    if not current_user.is_admin:
        return jsonify({"error": "Admin privileges required"}), 403

    data = request.json
    ip = data.get('ip')
    port = data.get('port')

    if not ip or not port:
        return jsonify({"error": "Missing IP or Port"}), 400

    config_path = os.path.join(app.root_path, 'register_config.yaml')

    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        if 'modbus' not in config_data or not isinstance(config_data['modbus'], dict):
            config_data['modbus'] = {} # Ensure modbus section exists

        config_data['modbus']['ip'] = ip
        config_data['modbus']['port'] = int(port) # Ensure port is an integer

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, sort_keys=False)

        logging.info(f"Admin updated Modbus config in register_config.yaml: IP={ip}, Port={port}")
        # Flash message might not be visible if this is an API call typically handled by JS
        # flash("Modbus configuration updated in register_config.yaml. Please restart the application for changes to take full effect.", "success")
        return jsonify({"message": "Modbus configuration updated in register_config.yaml. A restart of the MQTT subscriber and potentially the Flask app (if it caches this config) may be required."})
    except Exception as e:
        logging.error(f"Error updating Modbus config in {config_path}: {e}", exc_info=True)
        # flash(f"Error updating Modbus configuration file: {e}", "error")
        return jsonify({"error": f"Failed to update configuration file: {e}"}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            logging.info(f"User '{username}' logged in successfully.")
            # MODIFIED: Redirect to index after successful login
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            logging.warning(f"Failed login attempt for username: '{username}'.")
            flash('Invalid username or password')
    # Always render index.html for GET, login form is a modal there
    return render_template('index.html', is_authenticated=current_user.is_authenticated if current_user else False)


@app.route('/logout')
@login_required
def logout():
    logging.info(f"User '{current_user.username}' logged out.")
    logout_user()
    # MODIFIED: Redirect to index which will then show login modal if needed
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Load .env variables if not already loaded (e.g., by a run script)
    from dotenv import load_dotenv # Keep this for direct app.py execution
    load_dotenv() # Ensure .env is loaded before any os.getenv calls
    
    # Import threading here if not already globally imported by other means
    import threading

    start_scheduler() # Starts the 'delete_old_data' job

    # Start the MQTT subscriber in a background thread
    logging.info("Creating Minimal MQTT subscriber thread...")
    # Ensure the target function is the new one
    mqtt_thread = threading.Thread(target=run_minimal_mqtt_thread, name="MinimalMQTTSubscriberThread")
    mqtt_thread.daemon = True  # Allow main program to exit even if this thread is still running
    mqtt_thread.start()
    logging.info("Minimal MQTT subscriber thread started.")

    # Use host='0.0.0.0' to make it accessible on the network
    # Use a different port if 5000 is used by something else (like the MQTT subscriber)
    app_port = int(os.getenv('FLASK_RUN_PORT', 5001))
    app.run(debug=True, host=os.getenv('FLASK_RUN_HOST', '0.0.0.0'), port=app_port, use_reloader=False)


