#!/bin/bash
# VFlow MQTT Subscriber Setup Script for Raspberry Pi
# This script sets up the complete environment for receiving and storing VFlow sensor data

set -e  # Exit on any error

echo "🚀 VFlow MQTT Subscriber Setup for Raspberry Pi"
echo "================================================"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  Please don't run this script as root. Run as a regular user with sudo privileges."
   exit 1
fi

# Update system packages
echo "📦 Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install required system packages
echo "📦 Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    git \
    mosquitto-clients

# Install Python dependencies
echo "🐍 Setting up Python environment..."
python3 -m venv vflow_env
source vflow_env/bin/activate

echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements_subscriber.txt

# Setup PostgreSQL
echo "🗄️  Setting up PostgreSQL database..."

# Start PostgreSQL service
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
echo "Creating database and user..."
sudo -u postgres psql << EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'vflow') THEN
        CREATE USER vflow WITH PASSWORD 'vflow_password_123';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE vflow_data OWNER vflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vflow_data')\\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE vflow_data TO vflow;
ALTER USER vflow CREATEDB;
EOF

# Setup MQTT Broker (Mosquitto)
echo "📡 Setting up MQTT broker..."
sudo apt install -y mosquitto mosquitto-clients

# Configure Mosquitto
sudo tee /etc/mosquitto/conf.d/vflow.conf > /dev/null << EOF
# VFlow MQTT Configuration
listener 1883
allow_anonymous true

# Enable persistence
persistence true
persistence_location /var/lib/mosquitto/

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information

# Connection logging
connection_messages true
EOF

# Start Mosquitto service
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

# Setup environment configuration
echo "⚙️  Setting up environment configuration..."
if [ ! -f .env ]; then
    cp .env.subscriber .env
    echo "📝 Created .env file from template"
    echo "⚠️  Please edit .env file with your specific configuration"
else
    echo "✅ .env file already exists"
fi

# Create systemd service for auto-start
echo "🔧 Creating systemd service..."
sudo tee /etc/systemd/system/vflow-subscriber.service > /dev/null << EOF
[Unit]
Description=VFlow MQTT Subscriber Service
After=network.target postgresql.service mosquitto.service
Wants=postgresql.service mosquitto.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/vflow_env/bin
ExecStart=$(pwd)/vflow_env/bin/python mqtt_subscriber.py
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vflow-subscriber

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable vflow-subscriber

# Create log directory
sudo mkdir -p /var/log/vflow
sudo chown $(whoami):$(whoami) /var/log/vflow

# Test database connection
echo "🧪 Testing database connection..."
source vflow_env/bin/activate
python3 << EOF
import psycopg2
try:
    conn = psycopg2.connect(
        host='localhost',
        database='vflow_data',
        user='vflow',
        password='vflow_password_123'
    )
    print("✅ Database connection successful!")
    conn.close()
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)
EOF

# Test MQTT broker
echo "🧪 Testing MQTT broker..."
timeout 5 mosquitto_pub -h localhost -t "test/topic" -m "test message" || {
    echo "❌ MQTT broker test failed"
    exit 1
}
echo "✅ MQTT broker test successful!"

echo ""
echo "🎉 VFlow MQTT Subscriber setup completed!"
echo "========================================="
echo ""
echo "📋 Next steps:"
echo "1. Edit the .env file with your specific configuration:"
echo "   nano .env"
echo ""
echo "2. Update PostgreSQL password in .env file"
echo ""
echo "3. Test the subscriber:"
echo "   source vflow_env/bin/activate"
echo "   python mqtt_subscriber.py"
echo ""
echo "4. Start the service automatically:"
echo "   sudo systemctl start vflow-subscriber"
echo "   sudo systemctl status vflow-subscriber"
echo ""
echo "5. View logs:"
echo "   journalctl -u vflow-subscriber -f"
echo ""
echo "📊 Database connection details:"
echo "   Host: localhost"
echo "   Database: vflow_data"
echo "   User: vflow"
echo "   Password: vflow_password_123 (change this in .env)"
echo ""
echo "📡 MQTT broker:"
echo "   Host: localhost"
echo "   Port: 1883"
echo ""
echo "🔧 Service management:"
echo "   Start:   sudo systemctl start vflow-subscriber"
echo "   Stop:    sudo systemctl stop vflow-subscriber"
echo "   Status:  sudo systemctl status vflow-subscriber"
echo "   Logs:    journalctl -u vflow-subscriber -f"
echo ""
