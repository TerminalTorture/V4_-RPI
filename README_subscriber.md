# VFlow MQTT Subscriber for PostgreSQL Storage

This system provides a complete MQTT-to-PostgreSQL data collection solution for VFlow sensor data. The subscriber runs on a Raspberry Pi (or any Linux system) to collect sensor data from the VFlow MQTT publisher and store it in a PostgreSQL database.

## 📋 Overview

```
VFlow Sensor System → MQTT Broker → PostgreSQL Database
                         ↑              ↑
                    (Publisher)    (Subscriber)
                   Windows PC      Raspberry Pi
```

## 🚀 Quick Setup (Raspberry Pi)

### 1. Clone/Copy Files

Copy these files to your Raspberry Pi:
- `mqtt_subscriber.py` - Main subscriber script
- `requirements_subscriber.txt` - Python dependencies
- `.env.subscriber` - Environment configuration template
- `setup_rpi.sh` - Automated setup script
- `test_subscriber.py` - Test script

### 2. Run Automated Setup

```bash
# Make setup script executable
chmod +x setup_rpi.sh

# Run setup (will install everything)
./setup_rpi.sh
```

This script will:
- Install PostgreSQL and MQTT broker (Mosquitto)
- Set up Python environment and dependencies
- Create database and user
- Configure systemd service for auto-start
- Set up logging

### 3. Configure Environment

```bash
# Edit configuration file
nano .env

# Update these key settings:
POSTGRES_PASSWORD=your_secure_password
MQTT_BROKER_HOST=localhost  # or IP of MQTT broker
```

### 4. Test Setup

```bash
# Activate Python environment
source vflow_env/bin/activate

# Run tests
python test_subscriber.py
```

### 5. Start Subscriber

```bash
# Manual start (for testing)
python mqtt_subscriber.py

# Or start as service
sudo systemctl start vflow-subscriber
sudo systemctl enable vflow-subscriber  # Auto-start on boot
```

## ⚙️ Manual Setup (Alternative)

### Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system packages
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib mosquitto mosquitto-clients
```

### PostgreSQL Setup

```bash
# Start PostgreSQL
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql << EOF
CREATE USER vflow WITH PASSWORD 'your_password';
CREATE DATABASE vflow_data OWNER vflow;
GRANT ALL PRIVILEGES ON DATABASE vflow_data TO vflow;
EOF
```

### Python Environment

```bash
# Create virtual environment
python3 -m venv vflow_env
source vflow_env/bin/activate

# Install dependencies
pip install -r requirements_subscriber.txt
```

### MQTT Broker

```bash
# Start Mosquitto
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# Test MQTT
mosquitto_pub -h localhost -t "test/topic" -m "test message"
mosquitto_sub -h localhost -t "test/topic"
```

## 📊 Database Schema

The subscriber automatically creates this table structure:

```sql
CREATE TABLE sensor_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_id VARCHAR(100),
    topic VARCHAR(200),
    
    -- Sensor data columns
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
    
    -- Raw JSON data
    raw_data JSONB,
    
    CONSTRAINT unique_timestamp_device UNIQUE (timestamp, device_id)
);
```

## 📡 MQTT Topics

The subscriber monitors these topics:

- `vflow/data/bulk` - Complete sensor data messages
- `vflow/sensors/+` - Individual sensor values
- `vflow/status` - Device status messages

## 🔧 Configuration

### Environment Variables (.env)

```bash
# MQTT Configuration
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=optional_username
MQTT_PASSWORD=optional_password
MQTT_BASE_TOPIC=vflow

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=vflow_data
POSTGRES_USER=vflow
POSTGRES_PASSWORD=your_secure_password
POSTGRES_TABLE=sensor_data

# Logging
LOG_LEVEL=INFO
```

## 🎯 Usage

### Starting the Subscriber

```bash
# Manual start
source vflow_env/bin/activate
python mqtt_subscriber.py

# Service start
sudo systemctl start vflow-subscriber
```

### Monitoring

```bash
# View real-time logs
journalctl -u vflow-subscriber -f

# Check service status
sudo systemctl status vflow-subscriber

# View database records
psql -h localhost -U vflow -d vflow_data -c "SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10;"
```

### Data Queries

```sql
-- Latest sensor readings
SELECT timestamp, device_id, cl1_soc, cl2_soc, system_power 
FROM sensor_data 
ORDER BY timestamp DESC 
LIMIT 10;

-- Average values over last hour
SELECT 
    AVG(cl1_soc) as avg_cl1_soc,
    AVG(system_power) as avg_power,
    COUNT(*) as record_count
FROM sensor_data 
WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Data by device
SELECT device_id, COUNT(*) as message_count, 
       MIN(timestamp) as first_seen, 
       MAX(timestamp) as last_seen
FROM sensor_data 
GROUP BY device_id;
```

## 🔍 Troubleshooting

### Common Issues

1. **Connection Failed**
   ```bash
   # Check PostgreSQL
   sudo systemctl status postgresql
   
   # Check MQTT broker
   sudo systemctl status mosquitto
   
   # Test database connection
   psql -h localhost -U vflow -d vflow_data
   ```

2. **Permission Denied**
   ```bash
   # Fix PostgreSQL permissions
   sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE vflow_data TO vflow;"
   ```

3. **MQTT Not Receiving**
   ```bash
   # Test MQTT subscription
   mosquitto_sub -h localhost -t "vflow/#" -v
   
   # Check firewall
   sudo ufw status
   ```

4. **Service Won't Start**
   ```bash
   # Check service logs
   journalctl -u vflow-subscriber -n 50
   
   # Check file permissions
   ls -la mqtt_subscriber.py
   ```

### Logs and Debugging

```bash
# Service logs
journalctl -u vflow-subscriber -f

# Application logs
tail -f vflow_mqtt_subscriber.log

# PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log

# MQTT broker logs
sudo tail -f /var/log/mosquitto/mosquitto.log
```

## 📈 Performance

### Optimization Tips

1. **Database Indexing**: Indexes are automatically created for common queries
2. **Batch Processing**: The subscriber handles high-frequency data efficiently
3. **Connection Pooling**: Uses persistent connections to minimize overhead
4. **Memory Management**: Automatically handles memory cleanup

### Monitoring Performance

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('vflow_data'));

-- Check table statistics
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes
FROM pg_stat_user_tables 
WHERE tablename = 'sensor_data';
```

## 🔐 Security

### Database Security
- Use strong passwords
- Limit network access with `pg_hba.conf`
- Enable SSL for remote connections

### MQTT Security
- Configure MQTT authentication
- Use TLS/SSL for encrypted communication
- Implement access control lists (ACLs)

## 📦 Files Overview

- `mqtt_subscriber.py` - Main subscriber application
- `requirements_subscriber.txt` - Python dependencies
- `.env.subscriber` - Environment configuration template
- `setup_rpi.sh` - Automated setup script
- `test_subscriber.py` - Testing utilities
- `README_subscriber.md` - This documentation

## 🆘 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Test individual components with `test_subscriber.py`
4. Verify configuration in `.env` file

## 🔄 Updates

To update the subscriber:
1. Stop the service: `sudo systemctl stop vflow-subscriber`
2. Update files
3. Restart the service: `sudo systemctl start vflow-subscriber`
