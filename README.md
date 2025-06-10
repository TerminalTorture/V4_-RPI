# VFlow MQTT Data Monitoring and Visualization Application

This application provides a web interface to monitor and visualize live and historical sensor data received via MQTT. It includes a Flask web server with an integrated MQTT client for data ingestion and uses a PostgreSQL database for data storage.

## Project Structure

Key files and directories:

```
/
├── app.py                   # Main Flask application, includes integrated MQTT client
├── register_config.yaml     # Configuration for sensor registers
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (MQTT, Database, Flask settings) - IMPORTANT: Create this file
├── api/
│   ├── live_data.py         # Flask blueprint for live data API
│   ├── hist_data.py         # Flask blueprint for historical data API
│   └── config_loader.py     # Loads register_config.yaml
├── static/                  # Static assets (CSS, JS, images)
│   └── js/
│       ├── sensor.js        # JavaScript for live data visualization
│       └── historical.js    # JavaScript for historical data visualization
├── templates/               # HTML templates
└── README.md                # This file
```

## Features

*   **Live Data Monitoring:** View real-time sensor data pushed via MQTT.
*   **Historical Data Visualization:** Browse and visualize past sensor readings.
*   **MQTT Integration:** Built-in MQTT client in `app.py` subscribes to topics and forwards data.
*   **Database Storage:** Sensor data can be stored in a PostgreSQL database (current focus is on live data via API).
*   **User Authentication:** Basic login system.

## Prerequisites

*   Python 3.8+
*   PostgreSQL server (for database features)
*   An MQTT broker

## Setup

1.  **Clone the Repository (if applicable):**
    ```bash
    # git clone <repository_url>
    # cd V4_-RPI
    ```

2.  **Create a Python Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Ensure `requirements.txt` includes `Flask`, `paho-mqtt`, `requests`, `psycopg2-binary`, `python-dotenv`, `Flask-Login`, `Werkzeug`, `APScheduler`, `PyYAML`.*

4.  **Set up PostgreSQL (if using database features):**
    *   Install PostgreSQL.
    *   Create a database (e.g., `sensor_data_rpi`).
    *   Create a user (e.g., `sensor_user`) with a password and grant permissions.

5.  **Set up MQTT Broker:**
    *   Ensure an MQTT broker (like Mosquitto) is running and accessible.

6.  **Create and Configure `.env` File:**
    Create a `.env` file in the project root (`/home/unit12/Desktop/V4_-RPI/.env`) with the following, adjusting values as necessary:

    ```env
    # Flask Configuration
    FLASK_APP=app.py
    FLASK_RUN_HOST=0.0.0.0
    FLASK_RUN_PORT=5001 # Port for the Flask app
    SECRET_KEY='your_very_secret_key_here' # Change this!

    # PostgreSQL Database Configuration
    DATABASE_URL='postgresql://sensor_user:your_db_password@localhost:5432/sensor_data_rpi'
    POSTGRES_HOST='localhost'
    POSTGRES_PORT='5432'
    POSTGRES_DATABASE='sensor_data_rpi'
    POSTGRES_USER='sensor_user'
    POSTGRES_PASSWORD='your_db_password'
    POSTGRES_TABLE='sensor_data'

    # MQTT Broker Configuration
    MQTT_BROKER_HOST='localhost' # Or your MQTT broker's IP/hostname
    MQTT_BROKER_PORT='1883'
    # MQTT_USERNAME='' # Optional
    # MQTT_PASSWORD='' # Optional
    # MQTT_TOPIC_BULK='vflow/data/bulk' # Topic is hardcoded in app.py's MQTT client for now

    # Default User Credentials (created if they don't exist)
    DEFAULT_USER_USERNAME='vflow'
    DEFAULT_USER_PASSWORD='password' # Change this!
    ADMIN_USER_USERNAME='admin'
    ADMIN_USER_PASSWORD='admin'   # Change this!
    ```
    **Security Note:** Change default passwords and `SECRET_KEY`.

7.  **Review `register_config.yaml`:**
    This file is used for Modbus configuration if applicable, and potentially for other register definitions displayed in the UI.

## Running the Application

1.  **Ensure your PostgreSQL server (if used) and MQTT broker are running.**

2.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```

3.  **Run the Flask Application:**
    ```bash
    python app.py
    ```
    The application should be accessible at `http://localhost:5001` (or the port in your `.env`). The integrated MQTT client will start automatically.

## How it Works

*   **MQTT Client (in `app.py`):** Connects to the MQTT broker, subscribes to `vflow/data/bulk`.
*   **Data Ingestion:** On message arrival, the MQTT client POSTs JSON to `/api/live-data`.
*   **Flask API (`api/live_data.py`):**
    *   `POST /api/live-data`: Receives JSON, caches it in memory (`latest_live_data`).
    *   `GET /api/live-data`: Serves cached data if fresh (<30s), else queries DB (if DB is populated).
*   **Frontend (`static/js/sensor.js`):** Fetches from `GET /api/live-data` to update the dashboard.
*   **Database (`delete_old_data` in `app.py`):** Scheduled job to clean old data from PostgreSQL.

## Development Notes

*   The application creates default users (`vflow`/`password` and `admin`/`admin`). **Change these credentials.**
*   The `api/mqtt_minimal(depreciated).py` file is no longer used as its functionality is integrated into `app.py`.
