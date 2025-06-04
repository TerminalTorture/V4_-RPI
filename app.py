import os
import sys
import threading
import subprocess
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from api.config_loader import REGISTER_CONFIG # Import the loaded config
from api.live_data import live_data_api, SensorData, store_data_to_db, add_dynamic_columns # Import add_dynamic_columns
from api.hist_data import historical_data_api
from api.modbus_client import read_modbus_data
from api.extensions import db
from datetime import datetime, timedelta, timezone # MODIFIED: timezone import already present, UTC removed as set_timezone will be used
import logging # Add logging import
import yaml # Add this import

# Import centralized timezone configuration
from api.timezone_config import set_timezone

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
# SQLite Database Configuration
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/sensor_data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.getcwd(), 'instance', 'sensor_data.db') + '?check_same_thread=False'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
logging.getLogger('werkzeug').disabled = True # Consider enabling werkzeug logs for debugging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Initialize extensions
db.init_app(app)
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


class User (UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80),unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user (user_id):
    return User.query.get(int(user_id))


# ... (Background task setup)
collect_sensor_lock = threading.Lock()

# --- Modify collect_sensor_data ---
def collect_sensor_data():
    """Fetch Modbus data and store it, using the config-driven logic."""
    # Use logging instead of print
    logging.debug("Attempting to acquire lock for sensor data collection...")
    if not collect_sensor_lock.acquire(blocking=False):
        logging.warning("Could not acquire lock, collect_sensor_data already running.")
        return # Exit if already running

    # --- Add app context here ---
    with app.app_context():
        try:
            #logging.info("Running scheduled task: collect_sensor_data")
            # read_modbus_data now uses the config internally
            raw_data = read_modbus_data()
            if raw_data:
                # Process and store data (live_data endpoint logic can be reused or called)
                # For simplicity, directly call store_data_to_db after basic processing
                # Note: This duplicates some processing from the /live-data endpoint.
                # Consider refactoring processing logic into a shared function.

                processed_data_for_db = {}
                timestamp = datetime.now(set_timezone) # MODIFIED: Use application timezone

                for name, raw_value in raw_data.items():
                    if raw_value is None: continue
                    reg_info = REGISTER_CONFIG['by_name'].get(name)
                    if reg_info:
                        # Apply scaling for storage if needed (assuming stored values are scaled)
                        scale = reg_info.get('scale')
                        processed_value = float(raw_value) * float(scale) if scale is not None else raw_value

                        # Check if column exists and store (using lowercase name)
                        column_name = name.lower()
                        if hasattr(SensorData, column_name):
                            try:
                                processed_data_for_db[column_name] = float(processed_value)
                            except (ValueError, TypeError):
                                logging.warning(f"Scheduler: Could not convert {name} value {processed_value} to float for DB.")
                    else:
                        logging.warning(f"Scheduler: Unknown variable {name} found in Modbus data.")

                if processed_data_for_db:
                    store_data_to_db(processed_data_for_db, timestamp) # Pass only data meant for DB columns
                else:
                    logging.info("Scheduler: No data processed for DB storage in this cycle.")

            else:
                logging.error("Scheduler: Failed to read Modbus data.")
        except Exception as e:
            logging.error(f"Scheduler: Error in collect_sensor_data: {e}", exc_info=True)
            # Rollback might be needed here too if an error occurs *during* processing but before store_data_to_db fails
            try:
                db.session.rollback()
                logging.info("Rolled back DB session due to error in collect_sensor_data processing.")
            except Exception as db_err:
                logging.error(f"Scheduler: Failed to rollback DB session: {db_err}", exc_info=True)
        finally:
            logging.debug("Releasing lock for sensor data collection.")
            collect_sensor_lock.release() # Release lock even if context push fails (though unlikely)


# ... (Scheduler setup remains the same)
executors = {
    'default': ThreadPoolExecutor(1) # Only allow 1 thread at a time
}

def delete_old_data():
    """Deletes sensor data older than 30 days from the database."""
    # ... (delete_old_data logic remains the same) ...
    try:
        cutoff_date = datetime.now(set_timezone) - timedelta(days=30) # MODIFIED: Use application timezone
        with app.app_context(): # Ensure app context for db operations
            deleted_count = SensorData.query.filter(SensorData.timestamp < cutoff_date).delete()
            db.session.commit()
            if deleted_count > 0:
                logging.info(f"Deleted {deleted_count} records older than {cutoff_date}.")
            else:
                logging.info("No old records found to delete.")
    except Exception as e:
        logging.error(f"Error deleting old data: {e}", exc_info=True)
        db.session.rollback() # Rollback on error


def start_scheduler():
    scheduler = BackgroundScheduler(executors=executors)
    # Schedule data collection (e.g., every 5 seconds)
    scheduler.add_job(collect_sensor_data, 'interval', seconds=5, id='collect_data_job', replace_existing=True)
    # Schedule old data deletion (e.g., daily at 3 AM)
    scheduler.add_job(delete_old_data, 'cron', hour=3, id='delete_old_data_job', replace_existing=True)
    scheduler.start()
    logging.info("Background scheduler started.")


# --- Create database tables AFTER dynamic columns are added ---
with app.app_context():
    logging.info("Adding dynamic columns to SensorData model...")
    add_dynamic_columns() # Ensure columns are defined on the model class
    logging.info("Initializing database and creating tables...")
    db.create_all() # Now create tables with dynamic columns
    logging.info("Database tables created (if they didn't exist).")

    # Create default admin user if not exists
    if not User.query.filter_by(username='admin').first():
        hashed_password = generate_password_hash('admin', method='pbkdf2:sha256')
        admin_user = User(username='admin', password=hashed_password, is_admin=True)
        db.session.add(admin_user)
        db.session.commit()
        logging.info("Default admin user created.")



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
        flash("Modbus configuration updated in register_config.yaml. Please restart the application for changes to take full effect.", "success")
        return jsonify({"message": "Modbus configuration updated in register_config.yaml. A restart is likely required."})
    except Exception as e:
        logging.error(f"Error updating Modbus config in {config_path}: {e}", exc_info=True)
        flash(f"Error updating Modbus configuration file: {e}", "error")
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
            return redirect(url_for('index'))
        else:
            logging.warning(f"Failed login attempt for username: '{username}'.")
            flash('Invalid username or password')
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logging.info(f"User '{current_user.username}' logged out.")
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    start_scheduler()
    # Use host='0.0.0.0' to make it accessible on the network
    app.run(debug=True, host='0.0.0.0', port=5000) # Added host and port


