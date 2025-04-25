import os
import json
import requests
import threading
import time
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask import redirect, url_for, flash, session
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import uuid
import hashlib
import socket
import subprocess
import json
import requests
from urllib.parse import urlparse
import sqlite3

# Import the auth module
from auth import user_manager, login_required, api_login_required, init_session, clear_session
from models import scan_manager

app = Flask(__name__, static_folder='static')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Secret key for sessions (generate a secure random key in production)
app.secret_key = 'your_secret_key_here'  # Replace with a secure random key
app.permanent_session_lifetime = timedelta(days=7)  # Session lasts for 7 days

GEMINI_PROXY_URL = "https://gemini-proxy-447400638876.asia-southeast1.run.app/analyze-image"

# Request queue for the Pi to poll
capture_requests = []

# Add this function somewhere before your routes

def check_pi_connection():
    """Check if the Raspberry Pi is connected and sending data
    
    This function checks if the Pi has communicated recently with the server.
    Returns True if connected, False otherwise.
    """
    try:
        # Method 1: Check if there are recent completed capture requests
        # Consider the Pi connected if there was activity in the last 5 minutes
        current_time = datetime.now()
        for request in requests:
            if request.get('status') == 'completed':
                completed_time = datetime.fromisoformat(request.get('completed_at', ''))
                time_diff = (current_time - completed_time).total_seconds()
                if time_diff < 300:  # 5 minutes
                    return True
        
        # Method 2: Check for recent file uploads
        # Find the most recent image in the upload folder
        image_files = [f for f in os.listdir(UPLOAD_FOLDER) 
                      if f.endswith(('.jpg', '.jpeg', '.png'))]
        
        if image_files:
            latest_image = max(
                image_files,
                key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x))
            )
            # Check if the image was uploaded in the last 5 minutes
            image_time = os.path.getmtime(os.path.join(UPLOAD_FOLDER, latest_image))
            time_diff = time.time() - image_time
            if time_diff < 300:  # 5 minutes
                return True
        
        # Method 3 (NEW): Check for recent heartbeats
        # Get the most recent heartbeat from database or file storage
        latest_heartbeat = get_latest_heartbeat()  # You'll need to implement this function
        if latest_heartbeat:
            # Parse the timestamp from the heartbeat
            heartbeat_time = datetime.fromisoformat(latest_heartbeat.get('timestamp', ''))
            time_diff = (current_time - heartbeat_time).total_seconds()
            # Consider the Pi connected if heartbeat was received in the last 3 minutes
            # (heartbeat is sent every 2 minutes per Pi code)
            if time_diff < 180:  # 3 minutes
                return True
        
        return False
    except Exception as e:
        print(f"Error checking Pi connection: {e}")
        return False
def get_latest_heartbeat():
    """Retrieve the most recent heartbeat from the database"""
    try:
        # If using SQLite or similar
        conn = sqlite3.connect('your_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM heartbeats ORDER BY timestamp DESC LIMIT 1")
        heartbeat = cursor.fetchone()
        conn.close()
        
        if heartbeat:
            # Convert database row to dictionary
            return {
                'device_id': heartbeat[0],
                'timestamp': heartbeat[1],
                'status': heartbeat[2]
            }
        return None
    except Exception as e:
        print(f"Error retrieving latest heartbeat: {e}")
        return None

def initialize_database():
    """Create required database tables if they don't exist"""
    try:
        conn = sqlite3.connect('your_database.db')
        cursor = conn.cursor()
        
        # Create heartbeats table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS heartbeats (
            device_id TEXT,
            timestamp TEXT,
            status TEXT,
            PRIMARY KEY (device_id, timestamp)
        )
        ''')
        
        # Create devices table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            ip_address TEXT,
            last_connection TEXT,
            camera_available BOOLEAN
        )
        ''')
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error initializing database: {e}")

# Call this function during application startup
initialize_database()

# ===== Authentication Routes =====
@app.route('/api/pi-status', methods=['GET'])
@login_required
def pi_status():
    """API endpoint to check the Raspberry Pi connection status"""
    try:
        # Check if the Pi is connected
        connected = check_pi_connection()
        
        # Return the status as JSON
        return jsonify({
            "connected": connected,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error in pi_status route: {e}")
        return jsonify({
            "connected": False,
            "error": str(e)
        }), 500

@app.route('/heartbeat', methods=['POST'])
def receive_heartbeat():
    data = request.json
    device_id = data.get('device_id')
    timestamp = data.get('timestamp')
    status = data.get('status')
    
    # Store heartbeat in database
    try:
        conn = sqlite3.connect('your_database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO heartbeats (device_id, timestamp, status) VALUES (?, ?, ?)",
            (device_id, timestamp, status)
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/device-connected', methods=['POST'])
def device_connected():
    data = request.json
    device_id = data.get('device_id')
    ip_address = data.get('ip_address')
    connection_time = data.get('connection_time')
    camera_available = data.get('camera_available', False)
    
    # Store device connection info
    try:
        conn = sqlite3.connect('your_database.db')
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO devices 
               (device_id, ip_address, last_connection, camera_available) 
               VALUES (?, ?, ?, ?)""",
            (device_id, ip_address, connection_time, camera_available)
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'danger')
            return render_template('login.html')
        
        success, result = user_manager.login_user(username, password)
        
        if success:
            # Initialize session with user data
            init_session(result)
            
            # Get the next parameter if it exists
            next_url = request.args.get('next', url_for('dashboard'))
            
            flash('You are now logged in!', 'success')
            return redirect(next_url)
        else:
            flash(f'Login failed: {result}', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validations
        if not username or not email or not password:
            flash('Please fill in all fields', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        # Register the user
        success, result = user_manager.register_user(username, email, password)
        
        if success:
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash(f'Registration failed: {result}', 'danger')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    clear_session()
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    # Get user scans
    user_scans = scan_manager.get_user_scans(user_id)
    
    # Process scans for display
    scan_history = []
    for scan in user_scans:
        # Format timestamp
        timestamp = datetime.fromisoformat(scan['timestamp'])
        formatted_date = timestamp.strftime("%b %d, %Y %I:%M %p")
        
        # Get analysis status
        status = "Unknown"
        status_class = "unknown"
        if 'analysis' in scan and 'status' in scan['analysis']:
            status = scan['analysis']['status']
            
            # Map status to CSS class
            if status == "Good":
                status_class = "good"
            elif status == "Needs improvement":
                status_class = "warning"
            elif status == "Attention needed":
                status_class = "danger"
        
        # Add to scan history
        scan_history.append({
            'id': scan['id'],
            'date': formatted_date,
            'status': status,
            'status_class': status_class,
        })
    
    # Get user stats
    stats = scan_manager.get_user_stats(user_id)
    
    # Get user's most recent recommendations
    recommendations = scan_manager.get_recent_recommendations(user_id)
    
    return render_template('dashboard.html', 
                          scan_history=scan_history, 
                          stats=stats, 
                          recommendations=recommendations)

@app.route('/account')
@login_required
def account():
    user_id = session.get('user_id')
    user = user_manager.get_user(user_id)
    
    return render_template('account.html', user=user)

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session.get('user_id')
    
    username = request.form.get('username')
    email = request.form.get('email')
    
    if not username or not email:
        flash('Please fill in all fields', 'danger')
        return redirect(url_for('account'))
    
    # Update user data
    success, message = user_manager.update_user(user_id, {
        'username': username,
        'email': email
    })
    
    if success:
        # Update session with new data
        session['username'] = username
        session['email'] = email
        
        flash('Profile updated successfully', 'success')
    else:
        flash(f'Failed to update profile: {message}', 'danger')
    
    return redirect(url_for('account'))

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    user_id = session.get('user_id')
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        flash('Please fill in all fields', 'danger')
        return redirect(url_for('account'))
    
    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('account'))
    
    # Verify current password
    user = user_manager.get_user(user_id)
    stored_password = {
        'salt': bytes.fromhex(user['password']['salt']),
        'key': bytes.fromhex(user['password']['key'])
    }
    
    from auth import verify_password
    if not verify_password(stored_password, current_password):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('account'))
    
    # Update password
    success, message = user_manager.update_user(user_id, {
        'password': new_password
    })
    
    if success:
        flash('Password changed successfully', 'success')
    else:
        flash(f'Failed to change password: {message}', 'danger')
    
    return redirect(url_for('account'))

@app.route('/delete-account')
@login_required
def delete_account():
    # Implement account deletion logic here
    # For now, just log out the user
    clear_session()
    flash('Your account has been deleted', 'success')
    return redirect(url_for('index'))

@app.route('/view-scan/<scan_id>')
@login_required
def view_scan(scan_id):
    user_id = session.get('user_id')
    
    # Get the requested scan
    scan_data = scan_manager.get_scan(user_id, scan_id)
    
    if not scan_data:
        flash('Scan not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get the image path
    image_filename = scan_data.get('original_filename')
    
    # Format scan data for template
    timestamp = datetime.fromisoformat(scan_data['timestamp'])
    formatted_date = timestamp.strftime("%b %d, %Y %I:%M %p")
    
    # Extract analysis data
    analysis = scan_data.get('analysis', {})
    status = analysis.get('status', 'Unknown')
    primary_issue = analysis.get('primary_issue', 'No specific issues detected')
    
    # Map status to CSS class and icon
    status_class = "unknown"
    status_icon = "fa-question-circle"
    
    if status == "Good":
        status_class = "good"
        status_icon = "fa-check-circle"
    elif status == "Needs improvement":
        status_class = "warning"
        status_icon = "fa-exclamation-triangle"
    elif status == "Attention needed":
        status_class = "danger"
        status_icon = "fa-exclamation-circle"
    
    # Format detections
    detections = []
    detection_counts = analysis.get('detection_counts', {})
    confidences = analysis.get('confidences', {})
    predictions = analysis.get('predictions', [])
    
    for class_name, count in detection_counts.items():
        # Skip if count is zero
        if count == 0:
            continue
        
        # Get the confidence for this class
        confidence = confidences.get(class_name, 0)
        
        # Determine icon
        icon = "fa-question"
        if class_name == "healthy":
            icon = "fa-smile"
        elif class_name == "plaque":
            icon = "fa-bacteria"
        elif class_name == "caries":
            icon = "fa-tooth"
        
        # Add to detections list
        detections.append({
            'class': class_name,
            'label': class_name.capitalize(),
            'count': count,
            'confidence': round(confidence),
            'icon': icon
        })
    
    # Format recommendations
    recommendations = analysis.get('recommendations', ['No specific recommendations available'])
    
    scan = {
        'id': scan_id,
        'date': formatted_date,
        'image_filename': image_filename,
        'status': status,
        'status_class': status_class,
        'status_icon': status_icon,
        'primary_issue': primary_issue,
        'detections': detections,
        'recommendations': recommendations,
        'predictions': predictions
    }
    
    return render_template('view_scan.html', scan=scan)

@app.route('/delete-scan/<scan_id>')
@login_required
def delete_scan(scan_id):
    user_id = session.get('user_id')
    
    # Delete the scan
    success = scan_manager.delete_scan(user_id, scan_id)
    
    if success:
        flash('Scan deleted successfully', 'success')
    else:
        flash('Failed to delete scan', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/save-scan', methods=['POST'])
@login_required
def save_scan():
    user_id = session.get('user_id')
    
    # Get data from request
    data = request.json
    filename = data.get('filename')
    analysis_data = data.get('analysis')
    
    if not filename or not analysis_data:
        return jsonify({
            'status': 'error',
            'message': 'Missing required data'
        }), 400
    
    # Get the file path
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(file_path):
        return jsonify({
            'status': 'error',
            'message': 'Image file not found'
        }), 404
    
    # Save the scan
    success, result = scan_manager.save_scan(user_id, analysis_data, file_path)
    
    if success:
        return jsonify({
            'status': 'success',
            'scan_id': result,
            'message': 'Scan saved successfully'
        })
    else:
        return jsonify({
            'status': 'error',
            'message': f'Failed to save scan: {result}'
        }), 500

# ===== Original Routes =====

@app.route('/')
def index():
    """Serve the main web interface page"""
    # Check if user is logged in
    if 'user_id' not in session:
        # Not logged in, redirect to login page
        return redirect(url_for('login'))
    
    # User is logged in, show the main interface
    return render_template('index.html')

@app.route('/capture-only', methods=['POST'])
@login_required
def capture_only():
    """Queue a capture request for the Pi"""
    request_id = str(int(time.time()))
    
    # Add to queue
    capture_requests.append({
        "id": request_id,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    })
    
    return jsonify({
        "status": "success",
        "message": "Capture request queued",
        "request_id": request_id
    })

@app.route('/check-requests', methods=['GET'])
def check_requests():
    """Endpoint for the Pi to check for pending requests"""
    # Look for pending requests
    for request in capture_requests:
        if request.get("status") == "pending":
            return jsonify({
                "has_requests": True,
                "request": request
            })
    
    # No pending requests
    return jsonify({"has_requests": False})

@app.route('/mark-complete', methods=['POST'])
def mark_complete():
    data = request.json
    request_id = data.get('request_id')

    for req in capture_requests:
        if req.get("id") == request_id:
            req["status"] = "completed"
            req["completed_at"] = datetime.now().isoformat()

            time.sleep(1)  # Wait for image to finish uploading

            image_filename = req.get("filename")
            if not image_filename:
                return jsonify({"status": "error", "message": "Image filename not yet available"}), 400

            try:
                file_path = os.path.join(UPLOAD_FOLDER, image_filename)
                with open(file_path, "rb") as f:
                    encoded_image = base64.b64encode(f.read()).decode('utf-8')

                payload = {
                    "image_url": f"data:image/jpeg;base64,{encoded_image}"
                }

                response = requests.post(GEMINI_PROXY_URL, json=payload)
                gemini_response = response.json().get("response", "")
                structured = json.loads(gemini_response) if isinstance(gemini_response, str) else gemini_response

                analysis = structured

                result_path = os.path.join(UPLOAD_FOLDER, f"{image_filename}.json")
                with open(result_path, 'w') as f:
                    json.dump({
                        "filename": image_filename,
                        "timestamp": datetime.now().isoformat(),
                        "raw_detections": structured,
                        "analysis": analysis
                    }, f)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Gemini analysis error: {str(e)}"}), 500

            return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Request not found"}), 404

@app.route('/get-latest-image', methods=['GET'])
@login_required
def get_latest_image():
    """Get the latest uploaded image"""
    # Check completed requests
    completed_requests = [r for r in capture_requests if r.get('status') == 'completed']
    
    if not completed_requests:
        return jsonify({"status": "waiting", "message": "No completed captures yet"})
    
    # Find the latest completed request
    latest_request = max(completed_requests, key=lambda x: x.get('completed_at', ''))
    
    # Find the most recent image
    image_files = [f for f in os.listdir(UPLOAD_FOLDER) 
                   if f.endswith(('.jpg', '.jpeg', '.png'))]
    
    if not image_files:
        return jsonify({"status": "error", "message": "No images found"})
    
    # Get the most recent file
    latest_image = max(
        image_files, 
        key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x))
    )
    
    return jsonify({
        "status": "success",
        "filename": latest_image,
        "request_id": latest_request.get('id')
    })
@app.route('/analyze-image', methods=['POST'])
@login_required
def analyze_image():
    try:
        # Get the image file from the request
        if 'image' not in request.files:
            # If no file in request, try to get the latest image
            completed_requests = [r for r in capture_requests if r.get('status') == 'completed']
            if not completed_requests:
                print("❌ No completed captures yet")
                return jsonify({"error": "No completed captures yet"}), 400

            latest_request = max(completed_requests, key=lambda x: x.get('completed_at', ''))
            image_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(('.jpg', '.jpeg', '.png'))]
            if not image_files:
                print("❌ No images found")
                return jsonify({"error": "No images found"}), 400

            latest_image = max(image_files, key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x)))
            file_path = os.path.join(UPLOAD_FOLDER, latest_image)

            print(f"🔸 Sending latest image for analysis: {file_path}")
            with open(file_path, "rb") as img:
                image_data = img.read()
                current_filename = latest_image
        else:
            # Use the image file from the request
            image_file = request.files['image']
            image_data = image_file.read()
            current_filename = image_file.filename

        print(f"🔸 Sending image to Gemini proxy")
        
        # Create a multipart/form-data request to the Gemini proxy
        files = {"image": ("image.jpg", image_data, "image/jpeg")}
        response = requests.post(GEMINI_PROXY_URL, files=files)

        print("🔨 Proxy status code:", response.status_code)
        print("🔨 Proxy raw response:", response.text)

        if response.status_code != 200:
            return jsonify({"error": "Failed to analyze image"}), 500

        try:
            response_data = response.json()
        except ValueError:
            return jsonify({"error": "Invalid JSON response from Gemini proxy"}), 500

        if "response" not in response_data:
            return jsonify({"error": "Failed to get proper analysis data from server"}), 500

        # Extract the predictions and recommendations
        gemini_data = response_data["response"]
        
        # Process predictions to generate detection counts and confidences
        detection_counts = {}
        confidences = {}
        
        if "predictions" in gemini_data:
            for pred in gemini_data["predictions"]:
                class_name = pred["class"].replace("-like", "").replace("-looking", "")
                if class_name not in detection_counts:
                    detection_counts[class_name] = 0
                    confidences[class_name] = 0
                
                detection_counts[class_name] += 1
                confidences[class_name] = max(confidences[class_name], pred["confidence"] * 100)
        
        # Determine overall status based on detections
        status = "Unknown"
        primary_issue = "No specific issues detected"
        
        if "caries" in detection_counts and detection_counts["caries"] > 0:
            status = "Attention needed"
            primary_issue = f"Detected {detection_counts['caries']} potential cavity areas"
        elif "plaque" in detection_counts and detection_counts["plaque"] > 0:
            status = "Needs improvement"
            primary_issue = f"Detected {detection_counts['plaque']} areas with potential plaque buildup"
        elif "healthy" in detection_counts and detection_counts["healthy"] > 0:
            status = "Good"
            primary_issue = "Your teeth appear to be in good condition"
        
        # Enhance the response with processed data
        enhanced_data = {
            "predictions": gemini_data.get("predictions", []),
            "recommendations": gemini_data.get("recommendations", []),
            "detection_counts": detection_counts,
            "confidences": confidences,
            "status": status,
            "primary_issue": primary_issue,
            "filename": current_filename
        }
        
        # Save the result to a JSON file for later retrieval
        result_path = os.path.join(UPLOAD_FOLDER, f"{current_filename}.json")
        with open(result_path, 'w') as f:
            json.dump({
                "filename": current_filename,
                "timestamp": datetime.now().isoformat(),
                "raw_detections": gemini_data,
                "analysis": enhanced_data
            }, f)
        
        return jsonify({"response": enhanced_data})

    except Exception as e:
        print("⚠️ Exception:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/get-analysis', methods=['GET'])
@login_required
def get_analysis():
    """Get the analysis results for the most recent image"""
    # Find the most recent result file
    result_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.json')]
    
    if not result_files:
        return jsonify({"status": "error", "message": "No analysis results found"}), 404
    
    # Get the most recent file
    latest_result = max(
        result_files, 
        key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x))
    )
    

    try:
        with open(os.path.join(UPLOAD_FOLDER, latest_result), 'r') as f:
            result = json.load(f)
        
        return jsonify({
            "status": "success",
            "data": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error reading results: {str(e)}"
        }), 500

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No image selected"}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    # âœ… Match request and store filename
    request_id = request.form.get("request_id")
    if request_id:
        for req in capture_requests:
            if req.get("id") == request_id:
                req["filename"] = file.filename
                break

    return jsonify({
        "status": "success",
        "message": "Image uploaded successfully",
        "filename": file.filename
    })


@app.route('/toothbrush_monitor')
@login_required
def toothbrush_monitor():
    """Serve the toothbrush monitor page"""
    return render_template('toothbrush_monitor.html')

# API endpoint to get the device's IP on the local network
@app.route('/api/get_device_ip', methods=['POST'])
@login_required
def get_device_ip():
    """Find the device's IP address on the local network after it connects to WiFi"""
    data = request.json
    
    if not data or 'espIp' not in data:
        return jsonify({"status": "error", "message": "No ESP IP provided"}), 400
    
    # The ESP32's previous IP from its access point
    esp_ap_ip = data['espIp']
    
    try:
        # First, try to get the new IP from the device itself
        # This might not work if the device has already disconnected from its AP
        try:
            # Try with a short timeout as this likely won't work
            response = requests.get(f"http://{esp_ap_ip}/ip", timeout=2)
            if response.status_code == 200:
                # If the device has a special endpoint that returns its new IP
                new_ip = response.text.strip()
                return jsonify({"status": "success", "ip": new_ip})
        except:
            pass  # Expected to fail, continue with other methods
        
        # Option 1: Try to scan the network for the ESP32
        # This is a simple implementation - a proper one would use nmap or similar
        # Attempt to get the base network for scanning
        interface = get_active_interface()
        if not interface or not interface['addr'] or not interface['netmask']:
            return jsonify({"status": "error", "message": "Could not determine network details"}), 500
        
        # Determine network subnet
        network_base = get_network_base(interface['addr'], interface['netmask'])
        if not network_base:
            return jsonify({"status": "error", "message": "Could not determine network subnet"}), 500
        
        # Scan the network for ESP32 devices
        candidates = scan_for_esp32(network_base)
        
        if candidates:
            # Try each candidate IP to see if our device responds
            for ip in candidates:
                try:
                    response = requests.get(f"http://{ip}/health", timeout=1)
                    if response.status_code == 200:
                        # Found our device!
                        return jsonify({"status": "success", "ip": ip})
                except:
                    continue  # Try the next candidate
        
        # If we can't automatically detect it, let the user know
        return jsonify({
            "status": "warning", 
            "message": "Could not automatically detect the device. Please check your router's connected devices."
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error finding device: {str(e)}"}), 500

def get_active_interface():
    """Get the active network interface details"""
    try:
        # This is a simple implementation that works for most cases
        # A proper implementation would use netifaces or similar
        # Use socket to get the hostname and IP address
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        
        # For simplicity, assume a /24 subnet mask (255.255.255.0)
        # A proper implementation would get the actual netmask
        netmask = "255.255.255.0"
        
        return {
            "name": hostname,
            "addr": ip_address,
            "netmask": netmask
        }
    except Exception as e:
        print(f"Error getting network interface: {e}")
        return None

def get_network_base(ip, netmask):
    """Get the network base address for scanning"""
    try:
        # Convert IP and netmask to integer representation
        ip_parts = list(map(int, ip.split('.')))
        mask_parts = list(map(int, netmask.split('.')))
        
        # Calculate network base address
        base_parts = [ip_parts[i] & mask_parts[i] for i in range(4)]
        
        # Return as string
        return '.'.join(map(str, base_parts))
    except Exception as e:
        print(f"Error calculating network base: {e}")
        return None

def scan_for_esp32(network_base):
    """Scan for potential ESP32 devices on the network"""
    candidates = []
    
    # For simplicity, we'll only try the first 20 addresses
    # A proper implementation would scan more thoroughly
    network_prefix = '.'.join(network_base.split('.')[:3]) + '.'
    
    for i in range(1, 21):  # Just check the first 20 IPs
        ip = f"{network_prefix}{i}"
        
        # Skip the gateway address (usually .1)
        if i == 1:
            continue
            
        # Try a simple ping to see if the device is alive
        try:
            # Use a very short timeout for ping
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "0.2", ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=0.5
            )
            
            if result.returncode == 0:
                # Device responded to ping, add to candidates
                candidates.append(ip)
        except:
            continue  # Ignore errors and continue
    
    return candidates

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/health-check', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok"})

# ===== JavaScript for Saving Scan Results =====
@app.route('/static/js/app.js')
def serve_app_js():
    """Add save functionality to the app.js"""
    # Read the original app.js file
    with open('static/js/app.js', 'r') as f:
        js_content = f.read()
    
    # Check if save results functionality already exists
    if 'saveResults' not in js_content:
        # Add the save results function
        save_results_function = """
    function saveResults() {
        // Can't save without analysis data
        if (!currentAnalysisData) {
            alert('No analysis data available to save');
            return;
        }
        
        // Send the request to save scan
        fetch('/save-scan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: currentImageFilename,
                analysis: currentAnalysisData.analysis
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Scan saved to your profile!');
                // Option to go to dashboard
                if (confirm('View your saved scans on your dashboard?')) {
                    window.location.href = '/dashboard';
                }
            } else {
                throw new Error(data.message || 'Failed to save scan');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to save scan: ' + error.message);
        });
    }
        """
        
        # Append the function to the file
        with open('static/js/app.js', 'a') as f:
            f.write(save_results_function)
    
    # Return the app.js file
    return send_from_directory('static/js', 'app.js')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)