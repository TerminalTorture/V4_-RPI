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
from api.live_data import live_data_api # Import only the blueprint, not the old SQLAlchemy models
from api.hist_data import historical_data_api  # Updated to use PostgreSQL
# Removed: from api.modbus_client import read_modbus_data - no longer needed for PostgreSQL-based data
from api.extensions import db  # SQLAlchemy for user authentication (SQLite), PostgreSQL handled directly in live_data.py
from datetime import datetime, timedelta, timezone # MODIFIED: timezone import already present, UTC removed as set_timezone will be used
import logging # Add logging import
import yaml # Add this import

# Import centralized timezone configuration
from api.timezone_config import set_timezone

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
# SQLite Database Configuration (used only for user authentication, not sensor data)
# Sensor data is now stored in PostgreSQL and accessed via mqtt_subscriber.py
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
app.register_blueprint(historical_data_api, url_prefix='/api')  # Re-enabled with PostgreSQL support

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

# --- Legacy function - sensor data collection now handled by MQTT subscriber ---
def collect_sensor_data():
    """Legacy function - sensor data collection now handled by MQTT subscriber"""
    # This function is now replaced by the PostgreSQL MQTT subscriber
    # The web app only reads data from PostgreSQL, it doesn't collect it
    logging.debug("collect_sensor_data called - data collection now handled by MQTT subscriber")
    pass

# ... (Scheduler setup remains the same)
executors = {
    'default': ThreadPoolExecutor(1) # Only allow 1 thread at a time
}

def delete_old_data():
    """Legacy function - data cleanup now handled by PostgreSQL MQTT subscriber"""
    # Data cleanup is now handled by the PostgreSQL subscriber or database maintenance
    logging.debug("delete_old_data called - data cleanup now handled by PostgreSQL subscriber")
    pass


def start_scheduler():
    """
    Background scheduler for web app maintenance tasks.
    Note: Sensor data collection is now handled by mqtt_subscriber.py
    """
    scheduler = BackgroundScheduler(executors=executors)
    
    # Note: Data collection and cleanup now handled by PostgreSQL MQTT subscriber
    # Only add scheduler jobs here if needed for web app maintenance
    
    scheduler.start()
    logging.info("Background scheduler started (sensor data collection handled by MQTT subscriber).")


# --- Create database tables (User table only) ---
with app.app_context():
    logging.info("Initializing SQLite database for user authentication...")
    db.create_all() # Create User table for authentication
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
    app.run(debug=True, host='0.0.0.0', port=5001) # Added host and port


