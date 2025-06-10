#!/usr/bin/env python3
"""
Script to create the sensor_data_rpi table if it doesn't exist.
This resolves the database issue where the application can't find the table.
"""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# PostgreSQL configuration
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DATABASE', 'sensor_data_rpi'),
    'user': os.getenv('POSTGRES_USER', 'sensor_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Master123')
}

POSTGRES_TABLE = os.getenv('POSTGRES_TABLE', 'sensor_data_rpi')

def create_table():
    """Create the sensor_data_rpi table if it doesn't exist"""
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (POSTGRES_TABLE,))
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print(f"✅ Table '{POSTGRES_TABLE}' already exists.")
            
            # Show current structure
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (POSTGRES_TABLE,))
            
            columns = cursor.fetchall()
            print(f"Current table structure:")
            for col_name, data_type, nullable in columns:
                print(f"  - {col_name}: {data_type} (nullable: {nullable})")
        else:
            print(f"⚠️ Table '{POSTGRES_TABLE}' does not exist. Creating it now...")
            
            # Create the table with appropriate schema
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {POSTGRES_TABLE} (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL,
                device_id VARCHAR(100) NOT NULL,
                raw_data JSONB,
                -- Additional columns for common sensor data
                cl1_soc REAL,
                cl2_soc REAL,
                cl1_voltage REAL,
                cl2_voltage REAL,
                cl1_current REAL,
                cl2_current REAL,
                cl1_temperature REAL,
                cl2_temperature REAL,
                system_power REAL,
                system_status INTEGER,
                -- Index for performance
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create indexes for better query performance
            CREATE INDEX IF NOT EXISTS idx_{POSTGRES_TABLE}_timestamp ON {POSTGRES_TABLE}(timestamp);
            CREATE INDEX IF NOT EXISTS idx_{POSTGRES_TABLE}_device_id ON {POSTGRES_TABLE}(device_id);
            CREATE INDEX IF NOT EXISTS idx_{POSTGRES_TABLE}_created_at ON {POSTGRES_TABLE}(created_at);
            """
            
            cursor.execute(create_table_sql)
            conn.commit()
            print(f"✅ Table '{POSTGRES_TABLE}' created successfully!")
            
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {POSTGRES_TABLE};")
        row_count = cursor.fetchone()[0]
        print(f"📊 Table '{POSTGRES_TABLE}' contains {row_count} records.")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

def test_connection():
    """Test the database connection"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to PostgreSQL: {version}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        print(f"Connection config: {POSTGRES_CONFIG}")
        return False

if __name__ == "__main__":
    print("🔧 Checking database connection and table setup...")
    print(f"Database: {POSTGRES_CONFIG['database']}")
    print(f"Table: {POSTGRES_TABLE}")
    print("=" * 50)
    
    # Test connection first
    if test_connection():
        # Create table if needed
        if create_table():
            print("\n✅ Database setup completed successfully!")
        else:
            print("\n❌ Database setup failed!")
    else:
        print("\n❌ Could not connect to database!") 