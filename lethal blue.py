from flask import Flask, render_template, jsonify, request, send_from_directory
from threading import Thread
import time
import os
import cv2
import numpy as np
import pyautogui
import telebot
import psutil
import win32evtlog
import win32security
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import string
import sys
from datetime import datetime, timezone, timedelta

# Initialize Flask app
app = Flask(__name__)

# Global list to store alerts
alerts = []

# Folder to store media files
MEDIA_FOLDER = os.path.join(os.path.dirname(__file__), "static", "media")
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Function to add alerts to the global list
def add_alert(message, media_type=None, media_path=None):
    alerts.append({
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "message": message,
        "media_type": media_type,  # "image" or "video"
        "media_path": media_path   # Path to the media file
    })
    print(f"📢 Alert added: {message}")

# Flask route to display the dashboard
@app.route("/")
def dashboard():

    return render_template("dashboard.html", alerts=alerts)

@app.route("/get_username")
def get_username_route():
    """Get the current username."""
    username = get_username()   # Get the current username
    return jsonify({"username": username})

# Flask route to fetch alerts (used for real-time updates)
@app.route("/get_alerts")
def get_alerts():
    return jsonify(alerts)

# Flask route to serve media files
@app.route("/media/<filename>")
def media(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

# Route to get all selfies
@app.route("/get_all_selfies")
def get_all_selfies():
    """Get all selfie files."""
    selfie_files = [f for f in os.listdir(MEDIA_FOLDER) if f.startswith("selfie_")]
    if selfie_files:
        # Sort selfies by modification time (newest first)
        selfie_files.sort(key=lambda f: os.path.getmtime(os.path.join(MEDIA_FOLDER, f)), reverse=True)
        return jsonify({"selfies": selfie_files})
    return jsonify({"selfies": []})

@app.route("/get_all_recordings")
def get_all_recordings():
    """Get all screen recording files."""
    recording_files = [f for f in os.listdir(MEDIA_FOLDER) if f.startswith("screen_record_")]
    if recording_files:
        # Sort recordings by modification time (newest first)
        recording_files.sort(key=lambda f: os.path.getmtime(os.path.join(MEDIA_FOLDER, f)), reverse=True)
        return jsonify({"recordings": recording_files})
    return jsonify({"recordings": []})

# Function to run the Flask app
def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False)

# Start Flask in a separate thread
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Get AppData path dynamically
appdata_path = os.path.join(os.environ["USERPROFILE"], "AppData")

print("🛠 DEBUG: Starting screen lock monitor...")

# Telegram Bot Setup
token = "7789549594:AAEXjls1daGaI3z0yyAbjVbucNKkH_CYreQ"
chat_id = "1168273207"
bot = telebot.TeleBot(token)

def get_username():
    """Get the current username."""
    return os.getlogin()

def is_screen_locked():
    """Check if the screen is locked by looking for the LogonUI.exe process."""
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] == "LogonUI.exe":
            return True
    return False

def wait_for_screen_lock():
    """Wait for the screen to be locked."""
    print("🔍 Waiting for screen lock...")
    while True:
        if is_screen_locked():
            print("🔒 Screen lock detected!")
            return
        time.sleep(1.5)

def wait_for_screen_unlock():
    """Wait for the screen to be unlocked."""
    print("🔓 Waiting for screen unlock...")
    while True:
        if not is_screen_locked():
            print("✅ Screen unlocked! User logged in.")
            return
        time.sleep(1.5)

def get_latest_event(event_id, after_time, processed_events):
    """Query the Windows Event Log for the latest event matching the given criteria."""
    server = 'localhost'
    log_type = 'Security'
    hand = win32evtlog.OpenEventLog(server, log_type)
    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

    events = []
    while True:
        batch = win32evtlog.ReadEventLog(hand, flags, 0)
        if not batch:
            break
        events.extend(batch)

    print(f"🛠 DEBUG: Total events read: {len(events)}")

    for event in events:
        event_time = event.TimeGenerated.replace(tzinfo=timezone.utc)
        event_username = win32security.LookupAccountSid(None, event.Sid)[0] if event.Sid else "Unknown"
        event_record_id = event.RecordNumber  # Unique identifier for the event

        #print(f"🛠 DEBUG: Event ID {event.EventID} at {event_time} for user {event_username}")

        # Stop processing if we encounter an event older than the start_time
        if event_time <= after_time:
            print(f"🛠 DEBUG: Stopping event processing. Event at {event_time} is older than start_time {after_time}.")
            break

        # Only process events that occur after the specified time and haven't been processed
        if event.EventID == event_id and event_record_id not in processed_events:
            print(f"🛠 DEBUG: Found matching event: ID {event.EventID} at {event_time}")
            processed_events.add(event_record_id)  # Mark event as processed
            return event_time

    print(f"🛠 DEBUG: No matching event found for Event ID {event_id}")
    return None  # Return None if event not found

class FileEventHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(self):
        # List of system file extensions to ignore
        self.system_extensions = {".log", ".ini", ".db-wal", ".svg", ".temp", ".dll",".tmp", ".db", ".db-shm", ".dat", ".cache", ".state"}

    def is_user_file(self, file_path):
        """Check if a file is a user-created file."""
        # Ignore files with system extensions
        if any(file_path.lower().endswith(ext) for ext in self.system_extensions):
            return False
        # Ignore files in system directories (e.g., Windows, Program Files)
        system_dirs = {"C:\\Windows", appdata_path, "D:\\blue","C:\\Program Files\\JetBrains","C:\\ProgramData", "C:\\Program Files\\WindowsApps", "C:\\Program Files\\Portrait Displays"}
        if any(file_path.lower().startswith(dir.lower()) for dir in system_dirs):
            return False
        return True

    def on_modified(self, event):
        """Triggered when a file or directory is modified."""
        if not event.is_directory and self.is_user_file(event.src_path):
            print(f"🛠 DEBUG: User file modified: {event.src_path}")
            add_alert(f"🚨 File Modified!\n👤 User: {get_username()}\n📂 Path: {event.src_path}")
            try:
                bot.send_message(
                    chat_id,
                    f"🚨 File Modified!\n👤 User: {get_username()}\n📂 Path: {event.src_path}\n🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"⚠ Failed to send message: {e}")

    def on_created(self, event):
        """Triggered when a file or directory is created."""
        if not event.is_directory and self.is_user_file(event.src_path):
            print(f"🛠 DEBUG: User file created: {event.src_path}")
            add_alert(f"🚨 New File Created!\n👤 User: {get_username()}\n📂 Path: {event.src_path}")
            try:
                bot.send_message(
                    chat_id,
                    f"🚨 New File Created!\n👤 User: {get_username()}\n📂 Path: {event.src_path}\n🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"⚠ Failed to send message: {e}")

    def on_deleted(self, event):
        """Triggered when a file or directory is deleted."""
        if not event.is_directory and self.is_user_file(event.src_path):
            print(f"🛠 DEBUG: User file deleted: {event.src_path}")
            add_alert(f"🚨 File Deleted!\n👤 User: {get_username()}\n📂 Path: {event.src_path}")
            try:
                bot.send_message(
                    chat_id,
                    f"🚨 File Deleted!\n👤 User: {get_username()}\n📂 Path: {event.src_path}\n🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"⚠ Failed to send message: {e}")

    def on_moved(self, event):
        """Triggered when a file or directory is moved or renamed."""
        if not event.is_directory and self.is_user_file(event.src_path) and self.is_user_file(event.dest_path):
            print(f"🛠 DEBUG: User file moved: {event.src_path} -> {event.dest_path}")
            add_alert(f"🚨 File Moved!\n👤 User: {get_username()}\n📂 Source: {event.src_path}\n📂 Destination: {event.dest_path}")
            try:
                bot.send_message(
                    chat_id,
                    f"🚨 File Moved!\n👤 User: {get_username()}\n📂 Source: {event.src_path}\n📂 Destination: {event.dest_path}\n🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"⚠ Failed to send message: {e}")

def get_all_drives():
    """Get all available drives on the system."""
    drives = []
    for drive_letter in string.ascii_uppercase:
        drive_path = f"{drive_letter}:\\"
        if os.path.exists(drive_path):
            drives.append(drive_path)
    return drives

def start_file_monitoring():
    """Start monitoring file system events on all drives."""
    drives = get_all_drives()
    observers = []
    for drive in drives:
        event_handler = FileEventHandler()
        observer = Observer()
        observer.schedule(event_handler, drive, recursive=True)
        observer.start()
        observers.append(observer)
        print(f"🛠 DEBUG: Started monitoring file system at {drive}")
    return observers

def capture_selfie():
    """Capture a selfie using the webcam and add an alert."""
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        if ret:
            username = get_username()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            file_name = f"selfie_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            file_path = os.path.join(MEDIA_FOLDER, file_name)

            # Add timestamp to the selfie
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(frame, timestamp, (10, 30), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

            # Save the selfie
            cv2.imwrite(file_path, frame)

            # Add alert
            add_alert(f"📸 Suspicious Login Detected\n👤 Username: {username}\n📅 Timestamp: {timestamp}",
                      media_type="image", media_path=file_name)

            # Telegram alert
            caption = f"📸 Suspicious Login Detected\n👤 Username: {username}\n📅 Timestamp: {timestamp}"
            with open(file_path, 'rb') as photo:  # Use the correct file path
                bot.send_photo(chat_id, photo, caption=caption)

        cap.release()
    except Exception as e:
        print(f"⚠ Failed to capture selfie: {e}")

def record_screen():
    """Record the screen for 60 seconds and add an alert."""
    try:
        fps = 5  # Reduce frame rate if needed
        screen_size = pyautogui.size()
        screen_size = (screen_size.width // 2, screen_size.height // 2)  # Reduce resolution
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Use H.264 codec
        file_name = f"screen_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"  # Save as .mp4
        file_path = os.path.join(MEDIA_FOLDER, file_name)
        out = cv2.VideoWriter(file_path, fourcc, fps, screen_size)
        print("🎥 Screen recording started...")
        start_time = time.time()

        while time.time() - start_time < 60:
            if is_screen_locked():
                print("🔒 Screen locked. Stopping recording.")
                out.release()  # Release the VideoWriter object
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)  # Delete the partially recorded file
                        print("🎥 Partial recording deleted.")
                    except PermissionError:
                        print("⚠ Failed to delete partial recording: File is still in use.")
                return True  # Indicate that the recording was stopped due to screen lock

            try:
                img = pyautogui.screenshot()
                frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                frame = cv2.resize(frame, screen_size)  # Resize frame to reduce resolution
                out.write(frame)
            except OSError as e:
                print(f"⚠ Failed to capture screen: {e}")
                break  # Exit the loop if screen capture fails
            time.sleep(1 / fps)

        # Release the VideoWriter object
        out.release()
        print("🎥 Screen recording saved.")
        add_alert("🎥 Suspicious Login Recording", media_type="video", media_path=file_name)

        # Telegram Alert: Send the video as a file
        try:
            with open(file_path, 'rb') as video_file:
                bot.send_document(
                    chat_id,
                    video_file,
                    caption="🎥 Suspicious Login Recording",
                    timeout=30,  # Increase timeout for large files
                )
            print("✅ Video sent as a file to Telegram.")
        except Exception as e:
            print(f"⚠ Failed to send video as a file: {e}")
        finally:
            # Add a small delay to ensure the file is released
            time.sleep(2)

        return False  # Indicate that the recording completed successfully
    except Exception as e:
        print(f"⚠ Failed to record screen: {e}")
        return False

def monitor_login_attempts():
    """Monitor login attempts and handle actions."""
    failed_attempts = 0
    recording = False
    # Set start_time to the current time minus a small buffer (1 second)
    start_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    processed_events = set()  # Track processed events
    hello_sent = False  # Flag to track if "Hello Master!" has been sent

    # Start file system monitoring on all drives
    observers = start_file_monitoring()

    while True:
        # Check if the screen is locked again (LogonUI.exe is running)
        if is_screen_locked():
            print("🔒 Screen locked again. Exiting monitoring...")
            for observer in observers:
                observer.stop()  # Stop file system monitoring
                observer.join()  # Wait for the observer thread to finish
            sys.exit(0)  # Exit the program

        # Check for failed login attempts (Event ID 4625)
        failed_login = get_latest_event(4625, start_time, processed_events)
        if failed_login:
            failed_attempts += 1
            print(f"⚠ Failed login attempt at {failed_login}")
            capture_selfie()  # Capture selfie for failed login attempt

        # Check for successful login attempts (Event ID 4624)
        successful_login = get_latest_event(4624, start_time, processed_events)
        if successful_login and not hello_sent:  # Only send "Hello Master!" once
            if failed_attempts == 0:
                print(f"✅ Successful login at {successful_login}. Hello Master!")
                add_alert("Hello Master!")   # Add alert to dashboard
                bot.send_message(chat_id, "Hello Master!")  # Send message to Telegram
                hello_sent = True  # Set the flag to True after sending the message
            else:
                print(
                    f"✅ Successful login after failed attempts at {successful_login}. Capturing evidence...")
                capture_selfie()
                recording = True

        # If recording is enabled, record the screen
        while recording:
            screen_locked = record_screen()  # Record the screen and check if it was stopped due to screen lock
            if screen_locked:
                print("🔒 Screen locked during recording. Exiting program.")
                for observer in observers:
                    observer.stop()  # Stop file system monitoring
                    observer.join()  # Wait for the observer thread to finish
                sys.exit(0)  # Exit the program
            time.sleep(10)
            if is_screen_locked():
                print("🔒 Screen locked again. Stopping recording.")
                recording = False
                return

        time.sleep(1)  # Reduce sleep interval to 1 second for faster event detection

if __name__ == "__main__":
    # Step 1: Wait for the screen to be locked
    wait_for_screen_lock()

    # Step 2: Wait for the screen to be unlocked (user logs in)
    wait_for_screen_unlock()

    # Step 3: Monitor login attempts and file operations until the screen is locked again
    monitor_login_attempts()