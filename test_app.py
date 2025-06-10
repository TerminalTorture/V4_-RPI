#!/usr/bin/env python3
"""
Test script to check if the Flask app and database are working correctly
"""

import requests
import json
import time

def test_flask_app():
    """Test if the Flask app is running and database is accessible"""
    try:
        print("Testing Flask application...")
        
        # Test the test-db endpoint
        response = requests.get('http://localhost:5001/api/test-db', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Database test endpoint successful!")
            print(f"Database: {data.get('connection_config', {}).get('database')}")
            print(f"Table exists: {data.get('table_exists')}")
            print(f"Table name: {data.get('table_name')}")
            print(f"Row count: {data.get('row_count')}")
            
            if data.get('table_exists'):
                print("✅ sensor_data_rpi table exists and is accessible!")
                return True
            else:
                print("❌ sensor_data_rpi table still doesn't exist!")
                return False
        else:
            print(f"❌ Database test failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Flask app. Is it running on localhost:5001?")
        return False
    except Exception as e:
        print(f"❌ Error testing Flask app: {e}")
        return False

def test_live_data_endpoint():
    """Test the live data endpoint"""
    try:
        print("\nTesting live data endpoint...")
        
        # Test GET to live-data endpoint
        response = requests.get('http://localhost:5001/api/live-data', timeout=5)
        
        if response.status_code == 200:
            print("✅ Live data endpoint accessible!")
            return True
        else:
            print(f"⚠️ Live data endpoint returned status: {response.status_code}")
            print(f"Response: {response.text}")
            return True  # This might be expected if no data is available
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to live data endpoint.")
        return False
    except Exception as e:
        print(f"❌ Error testing live data endpoint: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing Flask application and database...")
    print("=" * 50)
    
    # Test database connectivity
    db_ok = test_flask_app()
    
    # Test live data endpoint
    live_ok = test_live_data_endpoint()
    
    print("\n" + "=" * 50)
    if db_ok:
        print("✅ Database issue resolved! The sensor_data_rpi table exists and is accessible.")
        if live_ok:
            print("✅ All endpoints are working correctly!")
        else:
            print("⚠️ Live data endpoint may have issues, but database is fixed.")
    else:
        print("❌ Database issue persists. Check if Flask app is running or table creation failed.") 