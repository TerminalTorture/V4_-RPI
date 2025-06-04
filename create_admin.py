# create_user.py
from app import db, User, app  # Import 'app' to access the application context
from werkzeug.security import generate_password_hash

# Function to create a new user
def create_user(username, password, is_admin=False):
    with app.app_context():
        db.create_all()  # Create tables if they don't exist

        # Check if the user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"User '{username}' already exists.")
            loginPage()
            return

        # Hash the password and create a new user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        user = User(username=username, password=hashed_password, is_admin=is_admin)
        db.session.add(user)
        db.session.commit()

        role = "Admin" if is_admin else "Normal User"
        print(f"{role} '{username}' created successfully!")
        loginPage()

# Function to list all users
def list_users():
    with app.app_context():
        users = User.query.all()
        if not users:
            print("No users found.")
        else:
            print(f"Total registered users: {len(users)}")
            for user in users:
                print(f"ID: {user.id}, Username: {user.username}, Admin: {user.is_admin}")
        loginPage()

# Function to handle user creation input
def create_user_login():
    print("Create a new user:")
    username = input("Username: ")
    password = input("Password: ")
    is_admin_input = input("Is this an admin account? (yes/no): ").strip().lower()
    is_admin = is_admin_input == 'yes'
    create_user(username, password, is_admin)

# Function to delete a specific user
def delete_user():
    with app.app_context():
        username = input("Enter the username to delete: ")
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"No user found with username '{username}'.")
        else:
            db.session.delete(user)
            db.session.commit()
            print(f"User '{username}' deleted successfully.")
        loginPage()

# Function to display the menu and handle user choices
def loginPage():
    while True:
        print("\nMenu:")
        print("Create New User (A), Manage Users (B), Delete User (C), Quit (Q)")
        choice = input("Enter Choice: ").upper()

        # Define available actions
        actions = {
            "A": create_user_login,
            "B": list_users,
            "C": delete_user,
            "Q": quit_program
        }

        # Execute the selected action
        action = actions.get(choice)
        if action:
            action()
            break
        else:
            print("Invalid choice. Please select A, B, C, or Q.")

# Function to quit the program safely
def quit_program():
    print("Exiting the program. Goodbye!")
    exit()

# Main entry point
if __name__ == '__main__':
    with app.app_context():
        loginPage()
