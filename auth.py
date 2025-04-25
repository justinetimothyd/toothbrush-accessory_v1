import os
import json
import uuid
import hashlib
import datetime
from functools import wraps
from flask import request, redirect, url_for, session, flash, jsonify

# Configuration
DATA_FOLDER = 'user_data'
USER_DATA_FILE = 'users.json'

# Ensure data directory exists
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# Helper to hash passwords
def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(32)  # Generate a random salt
    
    # Hash the password with the salt
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        100000  # Number of iterations
    )
    
    # Return the salt and key
    return {
        'salt': salt,
        'key': key
    }

# Verify password
def verify_password(stored_password, provided_password):
    salt = stored_password['salt']
    stored_key = stored_password['key']
    
    # Hash the provided password with the stored salt
    hashed = hash_password(provided_password, salt)
    
    # Compare the generated key with the stored key
    return hashed['key'] == stored_key

# User management
class UserManager:
    def __init__(self):
        self.users_file = os.path.join(DATA_FOLDER, USER_DATA_FILE)
        # Initialize local cache
        self.users = self._load_users()
    
    def _load_users(self):
        """Load users from local file"""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            else:
                # Create an empty users file
                with open(self.users_file, 'w') as f:
                    json.dump({}, f)
                return {}
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}
    
    def _save_users(self):
        """Save users to local file"""
        try:
            with open(self.users_file, 'w') as f:
                json.dump(self.users, f)
            return True
        except Exception as e:
            print(f"Error saving users: {e}")
            return False
    
    def register_user(self, username, email, password):
        """Register a new user"""
        # Check if user exists
        if self._get_user_by_username(username) or self._get_user_by_email(email):
            return False, "Username or email already exists"
        
        # Hash the password
        password_hash = hash_password(password)
        
        # Convert bytes to strings for JSON serialization
        serialized_password = {
            'salt': password_hash['salt'].hex(),
            'key': password_hash['key'].hex()
        }
        
        # Create user object
        user = {
            'id': str(uuid.uuid4()),
            'username': username,
            'email': email,
            'password': serialized_password,
            'created_at': datetime.datetime.now().isoformat(),
            'last_login': None
        }
        
        # Add to users dictionary
        self.users[user['id']] = user
        
        # Save to storage
        if self._save_users():
            return True, user['id']
        else:
            # Remove from local cache if save failed
            del self.users[user['id']]
            return False, "Failed to save user data"
    
    def login_user(self, username_or_email, password):
        """Login a user by username or email"""
        # Find user by username or email
        user = self._get_user_by_username(username_or_email) or self._get_user_by_email(username_or_email)
        
        if not user:
            return False, "User not found"
        
        # Convert stored password back to bytes
        stored_password = {
            'salt': bytes.fromhex(user['password']['salt']),
            'key': bytes.fromhex(user['password']['key'])
        }
        
        # Verify password
        if verify_password(stored_password, password):
            # Update last login
            user['last_login'] = datetime.datetime.now().isoformat()
            self._save_users()
            
            return True, user
        
        return False, "Invalid password"
    
    def get_user(self, user_id):
        """Get user by ID"""
        return self.users.get(user_id)
    
    def _get_user_by_username(self, username):
        """Find user by username"""
        for user_id, user in self.users.items():
            if user['username'].lower() == username.lower():
                return user
        return None
    
    def _get_user_by_email(self, email):
        """Find user by email"""
        for user_id, user in self.users.items():
            if user['email'].lower() == email.lower():
                return user
        return None
    
    def update_user(self, user_id, data):
        """Update user data"""
        if user_id not in self.users:
            return False, "User not found"
        
        # Update allowed fields
        for field in ['email', 'username']:
            if field in data:
                self.users[user_id][field] = data[field]
        
        # Update password if provided
        if 'password' in data and data['password']:
            password_hash = hash_password(data['password'])
            self.users[user_id]['password'] = {
                'salt': password_hash['salt'].hex(),
                'key': password_hash['key'].hex()
            }
        
        # Save changes
        if self._save_users():
            return True, "User updated"
        else:
            return False, "Failed to save changes"

# Initialize the user manager
user_manager = UserManager()

# Decorator to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Decorator to require API authentication (for API endpoints)
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Initialize session with user data
def init_session(user):
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['email'] = user['email']
    session['logged_in'] = True

# Clear session on logout
def clear_session():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('logged_in', None)
    session.clear()