
import sqlalchemy
from sqlalchemy.exc import OperationalError

# Define the database URI
SQLALCHEMY_DATABASE_URI = 'postgresql://sensor_user:Master123@localhost:5432/sensor_data'

def test_database_connection():
    """Tests the database connection using SQLAlchemy."""
    try:
        # Create an engine instance
        engine = sqlalchemy.create_engine(SQLALCHEMY_DATABASE_URI)
        
        # Try to connect to the database
        connection = engine.connect()
        
        print(f"Successfully connected to the database: {SQLALCHEMY_DATABASE_URI}")
        
        # Check if the 'sensor_data' table (or any table) exists as a basic test
        # You might need to adjust the table name if it's different or use a more generic query
        inspector = sqlalchemy.inspect(engine)
        if 'sensor_data' in inspector.get_table_names():
            print("Table 'sensor_data' exists in the database.")
        else:
            print("Table 'sensor_data' does NOT exist in the database (or is not accessible).")
            
        connection.close()
        print("Connection closed.")
        return True
    except OperationalError as e:
        print(f"Failed to connect to the database: {SQLALCHEMY_DATABASE_URI}")
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    print("Testing database connection...")
    test_database_connection()

