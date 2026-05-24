import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import requests
from PIL import Image, ImageTk
import threading
import queue
from datetime import datetime, timedelta
import difflib
import re
from urllib.parse import urlencode
from easyocr import Reader
from ultralytics import YOLO
import time

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# ESP Endpoints
ESP1_CAPTURE_URL = "http://10.115.207.192/capture"
ESP1_CONTROL_URL = "http://10.115.207.192/control"
ESP2_CAPTURE_URL = "http://10.115.207.35/capture"

# Model paths
PLATE_MODEL_PATH = "models/plate_detector.pt"
SLOT_MODEL_PATH = "models/slot_detector.pt"

# Authorized plates
KNOWN_PLATES = [
    "RJ14CV0002",
    "UP32RN5761",
    "MH14DS7000",
    "JK01AB5609"
]

# Parking configuration
TOTAL_SLOTS = 4
VISIBLE_SLOTS = 3
HIDDEN_OCCUPIED = 1

# OCR cleanup mapping
OCR_CLEANUP = {
    'O': '0',
    'Q': '0',
    'D': '0',
    'I': '1',
    'L': '1',
    'Z': '2',
    'S': '5',
    'B': '8'
}

# Throttling for repeated plate triggers (seconds)
PLATE_TRIGGER_COOLDOWN = 5

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def preprocess_ocr_image(image):
    """Preprocess image for OCR"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    bilateral = cv2.bilateralFilter(resized, 9, 75, 75)
    thresholded = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                        cv2.THRESH_BINARY, 11, 2)
    return thresholded

def cleanup_ocr_text(text):
    """Clean up OCR text"""
    text = text.upper().strip()
    for bad, good in OCR_CLEANUP.items():
        text = text.replace(bad, good)
    # Remove non-alphanumeric
    text = re.sub(r'[^A-Z0-9]', '', text)
    return text

def match_plate(ocr_text, known_plates=KNOWN_PLATES, threshold=0.6):
    """Fuzzy match OCR text against known plates"""
    if len(ocr_text) < 8:
        return None
    matches = difflib.get_close_matches(ocr_text, known_plates, n=1, cutoff=threshold)
    return matches[0] if matches else None

def fetch_image_from_url(url, timeout=5):
    """Fetch image from ESP endpoint"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            nparr = np.frombuffer(response.content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        return None
    except Exception as e:
        return None

def send_esp_command(cmd, **kwargs):
    """Send command to ESP1"""
    try:
        params = {'cmd': cmd}
        params.update(kwargs)
        url = f"{ESP1_CONTROL_URL}?{urlencode(params)}"
        requests.get(url, timeout=5)
        return True
    except:
        return False

def send_slot_count(available_slots):
    """Send available slot count to ESP1"""
    try:
        url = f"{ESP1_CONTROL_URL}?slots={available_slots}"
        requests.get(url, timeout=5)
        return True
    except:
        return False

def calculate_fee(entry_time, exit_time, price_per_hour):
    """Calculate parking fee"""
    duration = exit_time - entry_time
    hours = duration.total_seconds() / 3600
    fee = hours * price_per_hour
    return hours, fee

# ============================================================================
# ANPR MONITOR THREAD
# ============================================================================

class ANPRMonitor(threading.Thread):
    def __init__(self, queue, ocr_reader, plate_model):
        super().__init__(daemon=True)
        self.queue = queue
        self.ocr_reader = ocr_reader
        self.plate_model = plate_model
        self.running = True
        self.last_plate_time = {}
        
    def run(self):
        while self.running:
            try:
                frame = fetch_image_from_url(ESP1_CAPTURE_URL, timeout=3)
                if frame is None:
                    time.sleep(1)
                    continue
                
                # Resize for display
                display_frame = cv2.resize(frame, (400, 300))
                
                # Detect plates
                results = self.plate_model(frame, conf=0.5)
                detected_plate = None
                
                for result in results:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        plate_roi = frame[y1:y2, x1:x2]
                        
                        if plate_roi.size == 0:
                            continue
                        
                        # Preprocess and OCR
                        processed = preprocess_ocr_image(plate_roi)
                        ocr_results = self.ocr_reader.readtext(processed)
                        ocr_text = ''.join([text[1] for text in ocr_results])
                        cleaned = cleanup_ocr_text(ocr_text)
                        
                        matched = match_plate(cleaned)
                        if matched:
                            detected_plate = matched
                            break
                
                # Convert frame to RGB for display
                display_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                
                # Queue update
                self.queue.put({
                    'type': 'anpr_frame',
                    'frame': display_rgb,
                    'plate': detected_plate
                })
                
                time.sleep(0.5)
                
            except Exception as e:
                time.sleep(1)
    
    def check_plate_trigger(self, plate, available_slots):
        """Check if plate should trigger gate"""
        now = time.time()
        last_time = self.last_plate_time.get(plate, 0)
        
        if now - last_time < PLATE_TRIGGER_COOLDOWN:
            return False
        
        self.last_plate_time[plate] = now
        return True
    
    def stop(self):
        self.running = False

# ============================================================================
# SLOT MONITOR THREAD
# ============================================================================

class SlotMonitor(threading.Thread):
    def __init__(self, queue, slot_model):
        super().__init__(daemon=True)
        self.queue = queue
        self.slot_model = slot_model
        self.running = True
        self.last_slot_count = None
        
    def run(self):
        while self.running:
            try:
                frame = fetch_image_from_url(ESP2_CAPTURE_URL, timeout=3)
                if frame is None:
                    time.sleep(1)
                    continue
                
                # Resize for display
                display_frame = cv2.resize(frame, (400, 300))
                
                # Detect slots
                results = self.slot_model(frame, conf=0.5)
                
                empty_count = 0
                occupied_count = 0
                
                detection_count = 0
                for result in results:
                    for box in result.boxes:
                        if detection_count >= VISIBLE_SLOTS:
                            break
                        
                        class_id = int(box.cls[0])
                        class_name = result.names.get(class_id, "unknown")
                        
                        if "empty" in class_name.lower():
                            empty_count += 1
                        elif "occupied" in class_name.lower():
                            occupied_count += 1
                        
                        detection_count += 1
                
                # Clamp to visible slots
                total_visible = min(empty_count + occupied_count, VISIBLE_SLOTS)
                empty_count = min(empty_count, total_visible - occupied_count)
                
                # Calculate available (visible empty)
                available_slots = empty_count
                total_occupied = occupied_count + HIDDEN_OCCUPIED
                
                # Convert frame to RGB for display
                display_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                
                # Queue update
                self.queue.put({
                    'type': 'slot_frame',
                    'frame': display_rgb,
                    'available_slots': available_slots,
                    'occupied_slots': total_occupied
                })
                
                time.sleep(1)
                
            except Exception as e:
                time.sleep(1)
    
    def stop(self):
        self.running = False

# ============================================================================
# TKINTER DASHBOARD APPLICATION
# ============================================================================

class ParkingDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Smart Parking Admin Dashboard")
        self.geometry("1400x900")
        self.configure(bg="#1e1e1e")
        
        # Initialize models and readers
        try:
            self.plate_model = YOLO(PLATE_MODEL_PATH)
            self.slot_model = YOLO(SLOT_MODEL_PATH)
            self.ocr_reader = Reader(['en'], gpu=False)
        except Exception as e:
            messagebox.showerror("Model Error", f"Failed to load models: {e}\nApp will run in demo mode")
            self.plate_model = None
            self.slot_model = None
            self.ocr_reader = None
        
        # Threading
        self.update_queue = queue.Queue()
        self.anpr_thread = None
        self.slot_thread = None
        
        # State
        self.price_per_hour = 50
        self.available_slots = TOTAL_SLOTS - HIDDEN_OCCUPIED
        self.occupied_slots = HIDDEN_OCCUPIED
        self.entry_exit_data = {}  # plate -> {'entry_time': dt, 'exit_time': dt}
        self.table_items = {}  # iid -> plate
        self.plate_last_detection = {}  # plate -> time.time() for exit detection
        
        # PhotoImage cache
        self.anpr_photo = None
        self.slot_photo = None
        
        # Setup UI
        self.setup_ui()
        
        # Start threads
        self.start_monitoring()
        
        # Start update processing
        self.process_queue()
    
    def setup_ui(self):
        """Setup main UI layout"""
        # Color scheme
        bg_dark = "#1e1e1e"
        bg_card = "#2d2d2d"
        text_primary = "#ffffff"
        text_secondary = "#aaaaaa"
        accent = "#4CAF50"
        
        self.configure(bg=bg_dark)
        
        # ===== TOP SECTION: Live Feeds =====
        top_frame = tk.Frame(self, bg=bg_dark, height=350)
        top_frame.pack(fill=tk.BOTH, padx=10, pady=10)
        top_frame.pack_propagate(False)
        
        # ANPR Feed
        anpr_label = tk.Label(top_frame, text="ANPR Camera Feed", 
                             font=("Helvetica", 10, "bold"), 
                             bg=bg_dark, fg=text_primary)
        anpr_label.pack(side=tk.LEFT, padx=5, pady=5, anchor="nw")
        
        self.anpr_canvas = tk.Canvas(top_frame, width=400, height=300, 
                                      bg=bg_card, highlightthickness=2, 
                                      highlightbackground=accent)
        self.anpr_canvas.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Slot Feed
        slot_label = tk.Label(top_frame, text="Top-View Parking Feed", 
                             font=("Helvetica", 10, "bold"), 
                             bg=bg_dark, fg=text_primary)
        slot_label.pack(side=tk.LEFT, padx=5, pady=5, anchor="nw")
        
        self.slot_canvas = tk.Canvas(top_frame, width=400, height=300, 
                                      bg=bg_card, highlightthickness=2, 
                                      highlightbackground=accent)
        self.slot_canvas.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Stats cards on right
        stats_frame = tk.Frame(top_frame, bg=bg_dark)
        stats_frame.pack(side=tk.LEFT, padx=20, pady=5, fill=tk.BOTH, expand=True)
        
        # Available Slots Card
        self.available_card = self.create_stat_card(stats_frame, "Available Slots", 
                                                     str(self.available_slots), accent, bg_card, text_primary)
        self.available_card.pack(pady=10, fill=tk.X)
        
        # Occupied Slots Card
        self.occupied_card = self.create_stat_card(stats_frame, "Occupied Slots", 
                                                    str(self.occupied_slots), "#FF6B6B", bg_card, text_primary)
        self.occupied_card.pack(pady=10, fill=tk.X)
        
        # Total Slots Card
        self.total_card = self.create_stat_card(stats_frame, "Total Slots", 
                                                str(TOTAL_SLOTS), "#2196F3", bg_card, text_primary)
        self.total_card.pack(pady=10, fill=tk.X)
        
        # ===== MIDDLE SECTION: Price Control =====
        control_frame = tk.Frame(self, bg=bg_dark, height=60)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        control_frame.pack_propagate(False)
        
        price_label = tk.Label(control_frame, text="Price Per Hour (₹):", 
                              font=("Helvetica", 10, "bold"), 
                              bg=bg_dark, fg=text_primary)
        price_label.pack(side=tk.LEFT, padx=5)
        
        self.price_entry = tk.Entry(control_frame, width=10, 
                                    font=("Helvetica", 12), 
                                    bg=bg_card, fg=text_primary, 
                                    insertbackground=text_primary)
        self.price_entry.insert(0, str(self.price_per_hour))
        self.price_entry.pack(side=tk.LEFT, padx=5)
        
        update_btn = tk.Button(control_frame, text="Update Price", 
                              font=("Helvetica", 10, "bold"), 
                              bg=accent, fg="white", 
                              relief=tk.FLAT, padx=15, 
                              command=self.update_price)
        update_btn.pack(side=tk.LEFT, padx=5)
        
        # ===== BOTTOM SECTION: Entry/Exit Table =====
        table_frame = tk.Frame(self, bg=bg_dark)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        table_label = tk.Label(table_frame, text="Entry/Exit Log", 
                              font=("Helvetica", 10, "bold"), 
                              bg=bg_dark, fg=text_primary)
        table_label.pack(anchor="w", pady=5)
        
        # Treeview
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background=bg_card, foreground=text_primary, 
                       fieldbackground=bg_card, borderwidth=0)
        style.configure('Treeview.Heading', background=bg_card, foreground=text_primary)
        style.map('Treeview', background=[('selected', accent)])
        
        columns = ("Plate", "Entry Time", "Exit Time", "Duration (hrs)", "Fee (₹)", "Status")
        self.table = ttk.Treeview(table_frame, columns=columns, height=10, show='tree headings')
        
        self.table.column("#0", width=0, stretch=tk.NO)
        self.table.column("Plate", anchor=tk.W, width=120)
        self.table.column("Entry Time", anchor=tk.CENTER, width=130)
        self.table.column("Exit Time", anchor=tk.CENTER, width=130)
        self.table.column("Duration (hrs)", anchor=tk.CENTER, width=110)
        self.table.column("Fee (₹)", anchor=tk.CENTER, width=100)
        self.table.column("Status", anchor=tk.CENTER, width=80)
        
        for col in columns:
            self.table.heading(col, text=col)
        
        self.table.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Mark Exit Button
        exit_btn = tk.Button(table_frame, text="Mark Exit", 
                            font=("Helvetica", 10, "bold"), 
                            bg=accent, fg="white", 
                            relief=tk.FLAT, padx=15, 
                            command=self.mark_exit)
        exit_btn.pack(pady=10)
    
    def create_stat_card(self, parent, title, value, color, bg_color, text_color):
        """Create a stat card"""
        card = tk.Frame(parent, bg=bg_color, relief=tk.FLAT)
        card.pack(fill=tk.X)
        
        title_label = tk.Label(card, text=title, font=("Helvetica", 9), 
                              bg=bg_color, fg="#aaaaaa")
        title_label.pack(anchor="w", padx=10, pady=(5, 0))
        
        value_label = tk.Label(card, text=value, font=("Helvetica", 24, "bold"), 
                              bg=bg_color, fg=color)
        value_label.pack(anchor="w", padx=10, pady=(0, 5))
        
        card.value_label = value_label
        return card
    
    def start_monitoring(self):
        """Start monitoring threads"""
        if self.plate_model and self.ocr_reader:
            self.anpr_thread = ANPRMonitor(self.update_queue, self.ocr_reader, self.plate_model)
            self.anpr_thread.start()
        
        if self.slot_model:
            self.slot_thread = SlotMonitor(self.update_queue, self.slot_model)
            self.slot_thread.start()
    
    def process_queue(self):
        """Process updates from monitoring threads"""
        try:
            while True:
                msg = self.update_queue.get_nowait()
                
                if msg['type'] == 'anpr_frame':
                    self.update_anpr_frame(msg['frame'], msg['plate'])
                elif msg['type'] == 'slot_frame':
                    self.update_slot_frame(msg['frame'], msg['available_slots'], 
                                         msg['occupied_slots'])
        except queue.Empty:
            pass
        
        self.after(100, self.process_queue)
    
    def update_anpr_frame(self, frame, plate):
        """Update ANPR feed display"""
        try:
            pil_image = Image.fromarray(frame)
            self.anpr_photo = ImageTk.PhotoImage(pil_image)
            self.anpr_canvas.create_image(0, 0, image=self.anpr_photo, anchor=tk.NW)
            
            if plate:
                self.handle_detected_plate(plate)
        except Exception as e:
            pass
    
    def update_slot_frame(self, frame, available_slots, occupied_slots):
        """Update slot feed display"""
        try:
            pil_image = Image.fromarray(frame)
            self.slot_photo = ImageTk.PhotoImage(pil_image)
            self.slot_canvas.create_image(0, 0, image=self.slot_photo, anchor=tk.NW)
            
            # Update stats
            if available_slots != self.available_slots or occupied_slots != self.occupied_slots:
                self.available_slots = available_slots
                self.occupied_slots = occupied_slots
                
                self.available_card.value_label.config(text=str(available_slots))
                self.occupied_card.value_label.config(text=str(occupied_slots))
                
                # Send to ESP
                send_slot_count(available_slots)
        except Exception as e:
            pass
    
    def handle_detected_plate(self, plate):
        """Handle detected and matched plate - entry or exit"""
        try:
            now = time.time()
            
            if plate not in self.entry_exit_data:
                # ===== NEW ENTRY =====
                self.entry_exit_data[plate] = {
                    'entry_time': datetime.now(),
                    'exit_time': None
                }
                
                # Add to table
                entry_time_str = datetime.now().strftime("%H:%M:%S")
                iid = self.table.insert('', 'end', values=(plate, entry_time_str, "--", "--", "--", "IN"))
                self.table_items[iid] = plate
                
                # Trigger gate
                if self.available_slots > 0:
                    send_esp_command('open')
                else:
                    send_esp_command('deny')
                
                # Record detection time
                self.plate_last_detection[plate] = now
            else:
                # ===== EXISTING PLATE - CHECK FOR EXIT =====
                last_detect = self.plate_last_detection.get(plate, 0)
                time_since_last = now - last_detect
                
                # If plate is detected again after 30+ seconds, it's likely exiting
                if time_since_last > 30:
                    data = self.entry_exit_data[plate]
                    # Only mark exit if not already exited
                    if data['exit_time'] is None:
                        self.auto_mark_exit(plate)
                
                # Update last detection time
                self.plate_last_detection[plate] = now
        except Exception as e:
            pass
    
    def auto_mark_exit(self, plate):
        """Automatically mark vehicle exit and calculate fee"""
        try:
            if plate not in self.entry_exit_data:
                return
            
            data = self.entry_exit_data[plate]
            if data['exit_time'] is not None:
                return  # Already exited
            
            exit_time = datetime.now()
            data['exit_time'] = exit_time
            
            # Calculate fee
            hours, fee = calculate_fee(data['entry_time'], exit_time, self.price_per_hour)
            
            # Find and update table row
            for iid, p in self.table_items.items():
                if p == plate:
                    entry_time_str = data['entry_time'].strftime("%H:%M:%S")
                    exit_time_str = exit_time.strftime("%H:%M:%S")
                    duration_str = f"{hours:.2f}"
                    fee_str = f"{fee:.2f}"
                    
                    values = (plate, entry_time_str, exit_time_str, duration_str, fee_str, "OUT")
                    self.table.item(iid, values=values)
                    break
        except Exception as e:
            pass
    
    def update_price(self):
        """Update price per hour"""
        try:
            price = float(self.price_entry.get())
            if price < 0:
                messagebox.showwarning("Invalid Input", "Price must be positive")
                return
            self.price_per_hour = price
            messagebox.showinfo("Success", f"Price updated to ₹{price}/hour")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number")
    
    def mark_exit(self):
        """Mark selected vehicle as exited"""
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a vehicle from the table")
            return
        
        iid = selected[0]
        plate = self.table_items[iid]
        
        if plate not in self.entry_exit_data:
            messagebox.showerror("Error", "Vehicle data not found")
            return
        
        data = self.entry_exit_data[plate]
        if data['exit_time'] is not None:
            messagebox.showinfo("Already Exited", "This vehicle has already exited")
            return
        
        exit_time = datetime.now()
        data['exit_time'] = exit_time
        
        # Calculate fee
        hours, fee = calculate_fee(data['entry_time'], exit_time, self.price_per_hour)
        
        # Update table
        entry_time_str = data['entry_time'].strftime("%H:%M:%S")
        exit_time_str = exit_time.strftime("%H:%M:%S")
        duration_str = f"{hours:.2f}"
        fee_str = f"{fee:.2f}"
        
        values = (plate, entry_time_str, exit_time_str, duration_str, fee_str, "OUT")
        self.table.item(iid, values=values)
    
    def on_closing(self):
        """Handle window closing"""
        if self.anpr_thread:
            self.anpr_thread.stop()
        if self.slot_thread:
            self.slot_thread.stop()
        self.destroy()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = ParkingDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()