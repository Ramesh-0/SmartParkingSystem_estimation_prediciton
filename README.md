# Smart Parking Management System

## Project Overview

**Smart Parking Management System** is an intelligent IoT-integrated parking management solution that combines real-time vehicle detection, license plate recognition (ANPR), and parking slot occupancy monitoring to provide automated parking operations with a centralized admin dashboard.

The system processes live video feeds from strategically placed cameras to:
- Detect and recognize vehicle license plates for access control
- Monitor parking slot occupancy status
- Automatically calculate parking fees
- Control gate operations based on parking availability
- Maintain a comprehensive audit log of entry/exit transactions

### Key Capabilities

- **Real-time ANPR Processing**: Automatic Number Plate Recognition with OCR text cleanup and fuzzy matching
- **Occupancy Detection**: YOLOv8-based parking slot detection and classification
- **Intelligent Gate Control**: Automated gate operation based on authorized plates and slot availability
- **Dynamic Pricing**: Configurable hourly rates with automatic fee calculation
- **Live Monitoring Dashboard**: Real-time vehicle and slot status tracking with transaction history
- **Hardware Integration**: Direct ESP32/ESP8266 device communication for gate control and data transmission

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ANPR Camera (ESP1)                       │
│                 (License Plate Detection)                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ HTTP Requests
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Smart Parking Main Application                 │
│                   (Main.py Process)                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         ANPR Monitor Thread                         │   │
│  │  - Fetches frames from ESP1                         │   │
│  │  - Detects plates using YOLO                        │   │
│  │  - Performs OCR and text cleanup                    │   │
│  │  - Fuzzy matches against known plates              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Slot Monitor Thread                         │   │
│  │  - Fetches frames from ESP2                         │   │
│  │  - Detects slot status using YOLO                  │   │
│  │  - Classifies slots (empty/occupied)                │   │
│  │  - Calculates available slots                       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │     Tkinter Dashboard (Main Thread)                │   │
│  │  - Displays live feeds and statistics              │   │
│  │  - Manages entry/exit transactions                 │   │
│  │  - Processes user interactions                     │   │
│  └──────────────────────────────────────────────────────┘   │
└────────┬──────────────────────────────────────────────┬─────┘
         │                                              │
         │                                              │
         ▼                                              ▼
    ESP1 Control                                  Top-View Camera
    (Gate Control)                                   (ESP2)
```

### Threading Model

The application employs a **multi-threaded architecture** with a queue-based message passing system:

| Thread | Purpose | Update Interval | Queue Type |
|--------|---------|-----------------|-----------|
| **ANPRMonitor** | License plate detection and recognition | 500ms | `update_queue` |
| **SlotMonitor** | Parking slot status monitoring | 1000ms | `update_queue` |
| **Main Thread** | Tkinter GUI and queue processing | 100ms | Python Queue |

**Thread Safety**: The application uses Python's thread-safe `queue.Queue` to communicate between monitoring threads and the main GUI thread, preventing race conditions and UI freezes.

---

## Technology Stack

### Core Dependencies

| Component | Purpose | Version |
|-----------|---------|---------|
| **Python** | Runtime environment | 3.8+ |
| **OpenCV (cv2)** | Image processing and video manipulation | 4.5+ |
| **YOLO (Ultralytics)** | Object detection framework | 8.0+ |
| **EasyOCR** | Optical character recognition | 1.6+ |
| **Tkinter** | GUI framework | Built-in with Python |
| **NumPy** | Numerical operations | 1.21+ |
| **Pillow (PIL)** | Image I/O and display | 8.0+ |
| **Requests** | HTTP communication with ESP devices | 2.26+ |

### Pre-trained Models

```
models/
├── plate_detector.pt      # YOLOv8 model for license plate detection
└── slot_detector.pt       # YOLOv8 model for parking slot classification
```

**Model Specifications**:
- **Format**: PyTorch (.pt) - YOLOv8 format
- **Input Size**: 640×640 (auto-scaled)
- **Confidence Threshold**: 0.5 (configurable in code)
- **Training Data**: Custom-trained on parking lot imagery

---

## Features

### 1. **Automatic Number Plate Recognition (ANPR)**

**Workflow**:
1. Capture frame from ANPR camera (ESP1)
2. Detect license plates using YOLOv8
3. Extract plate region of interest (ROI)
4. Preprocess image (grayscale, upsampling, bilateral filtering, adaptive thresholding)
5. Perform OCR using EasyOCR
6. Clean OCR text (character mapping, alphanumeric filtering)
7. Fuzzy match against known plates database (60% similarity threshold)

**OCR Character Cleanup Mapping**:
```
O → 0  (Letter O to digit zero)
Q → 0  (Letter Q to digit zero)
D → 0  (Letter D to digit zero)
I → 1  (Letter I to digit one)
L → 1  (Letter L to digit one)
Z → 2  (Letter Z to digit two)
S → 5  (Letter S to digit five)
B → 8  (Letter B to digit eight)
```

### 2. **Parking Slot Occupancy Detection**

**Slot Classification**:
- **Empty Slots**: Available for parking
- **Occupied Slots**: Vehicle currently parked
- **Hidden Slots**: Pre-configured slots not visible to cameras (managed separately)

**Configuration**:
- Total Slots: 4
- Visible Slots: 3 (camera-monitored)
- Hidden Slots: 1 (manually managed)

### 3. **Entry/Exit Management**

**Entry Process**:
1. Authorized plate detected
2. Vehicle record created with entry timestamp
3. Gate control: Opens if slots available, denies if full
4. Entry logged in transaction table

**Exit Process**:
1. Plate re-detected after 30+ seconds (exit time threshold)
2. Exit timestamp recorded
3. Fee automatically calculated
4. Transaction marked as "OUT" in table
5. Manual override via "Mark Exit" button for operators

### 4. **Dynamic Pricing System**

**Fee Calculation Formula**:
$$\text{Fee} = \frac{\text{Duration (minutes)}}{60} \times \text{Price per Hour}$$

**Configurable Parameters**:
- Price per hour (₹) - adjustable via dashboard
- Default: ₹50/hour

---

## System Requirements

### Hardware

- **Processor**: Intel Core i5 or equivalent (≥2GHz)
- **RAM**: 4GB minimum (8GB recommended)
- **Storage**: 50GB+ (for models and logs)
- **Network**: Ethernet or WiFi for ESP communication

### Network

- **ESP1 IP**: `10.115.207.192` (ANPR camera)
- **ESP2 IP**: `10.115.207.35` (Top-view camera)
- **Network Protocol**: HTTP REST API
- **Bandwidth**: ≥5 Mbps recommended

### Software

- **OS**: Windows 10+, Linux, or macOS
- **Python**: 3.8 or higher
- **CUDA** (optional): For GPU-accelerated inference

---

## Installation Guide

### Prerequisites

```bash
# Install Python 3.8+
python --version

# Verify pip is installed
pip --version
```

### Step 1: Clone Repository

```bash
cd x:\ParkingSystem
git clone https://github.com/your-repo/SmartParkingSystem_estimation_prediciton.git
cd SmartParkingSystem_estimation_prediciton
```

### Step 2: Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install opencv-python==4.8.0
pip install ultralytics==8.0.0
pip install easyocr==1.6.2
pip install Pillow==10.0.0
pip install numpy==1.24.0
pip install requests==2.31.0
```

### Step 4: Download Pre-trained Models

Place the following files in the `models/` directory:
- `plate_detector.pt` - License plate detection model
- `slot_detector.pt` - Parking slot detection model

**Model Download**: Contact DevOps team or download from model repository

### Step 5: Verify Installation

```bash
python main.py
```

The Tkinter dashboard should launch with two canvas windows for camera feeds.

---

## Configuration

### ESP Device Configuration

Update the ESP IP addresses in [main.py](main.py#L24-L26):

```python
# ANPR Camera (License Plate Detection)
ESP1_CAPTURE_URL = "http://10.115.207.192/capture"
ESP1_CONTROL_URL = "http://10.115.207.192/control"

# Parking Slot Camera (Top-View)
ESP2_CAPTURE_URL = "http://10.115.207.35/capture"
```

### Known Plates Database

Edit authorized plates in [main.py](main.py#L29-L34):

```python
KNOWN_PLATES = [
    "RJ14CV0002",
    "UP32RN5761",
    "MH14DS7000",
    "JK01AB5609"
]
```

### Parking Configuration

Modify slot settings in [main.py](main.py#L36-L39):

```python
TOTAL_SLOTS = 4          # Total parking spaces
VISIBLE_SLOTS = 3        # Slots monitored by camera
HIDDEN_OCCUPIED = 1      # Pre-configured occupied/reserved slots
```

### Plate Detection Trigger Cooldown

Prevent duplicate triggers for the same plate in [main.py](main.py#L41):

```python
PLATE_TRIGGER_COOLDOWN = 5  # Seconds between repeated plate detections
```

### Detection Confidence Threshold

Adjust detection sensitivity in [main.py](main.py#L152):

```python
results = self.plate_model(frame, conf=0.5)  # 0.5 = 50% confidence
results = self.slot_model(frame, conf=0.5)
```

---

## Usage Guide

### Starting the Application

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Run the application
python main.py
```

### Dashboard Interface

#### 1. **Live Feeds Section**
- **ANPR Camera Feed**: License plate detection in real-time (left panel)
- **Top-View Parking Feed**: Slot occupancy status (center panel)
- **Statistics Cards**: Real-time slot counts (right panel)
  - Available Slots (green)
  - Occupied Slots (red)
  - Total Slots (blue)

#### 2. **Price Management**
- Input field for hourly parking rate
- "Update Price" button to apply changes
- Updated rate applies to subsequent calculations

#### 3. **Transaction Log**
- **Columns**: Plate | Entry Time | Exit Time | Duration (hrs) | Fee (₹) | Status
- **Status Values**: "IN" (parked), "OUT" (exited)
- **Mark Exit Button**: Manual exit marking for vehicles (select vehicle first)

### Typical Workflow

```
1. Vehicle approaches entrance
   ↓
2. ANPR camera detects license plate
   ↓
3. System fuzzy-matches against known plates
   ↓
4. If authorized AND slots available → GATE OPENS
   If authorized BUT full → GATE DENIES
   If not authorized → GATE DENIES
   ↓
5. Vehicle parks (system monitors slot occupancy)
   ↓
6. Vehicle approaches exit
   ↓
7. Plate detected again after 30+ seconds → AUTO EXIT
   OR operator manually marks exit
   ↓
8. Fee calculated and displayed
   ↓
9. Gate opens for exit
```

---

## API Integration

### ESP Device Communication

#### Capturing Images

**Request**:
```
GET http://10.115.207.192/capture
GET http://10.115.207.35/capture
```

**Response**: JPEG image binary data

**Python Implementation**:
```python
def fetch_image_from_url(url, timeout=5):
    response = requests.get(url, timeout=timeout)
    if response.status_code == 200:
        nparr = np.frombuffer(response.content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    return None
```

#### Gate Control Commands

**Request**:
```
GET http://10.115.207.192/control?cmd=open
GET http://10.115.207.192/control?cmd=deny
```

**Available Commands**:
- `cmd=open` - Open gate for entry
- `cmd=deny` - Deny gate opening

**Python Implementation**:
```python
def send_esp_command(cmd, **kwargs):
    params = {'cmd': cmd}
    params.update(kwargs)
    url = f"{ESP1_CONTROL_URL}?{urlencode(params)}"
    requests.get(url, timeout=5)
```

#### Slot Status Updates

**Request**:
```
GET http://10.115.207.192/control?slots=3
```

**Payload**: Available slot count to display on entrance signage

---

## File Structure

```
SmartParkingSystem_estimation_prediciton/
│
├── main.py                          # Main application entry point (≈680 lines)
│   ├── Configuration & Constants    # System parameters
│   ├── Utility Functions            # OCR preprocessing, plate matching
│   ├── ANPRMonitor (Thread)         # License plate detection logic
│   ├── SlotMonitor (Thread)         # Slot occupancy detection logic
│   └── ParkingDashboard (Tkinter)   # GUI implementation
│
├── models/
│   ├── plate_detector.pt            # YOLOv8 license plate detector
│   └── slot_detector.pt             # YOLOv8 parking slot detector
│
├── README.md                        # This documentation
│
└── .git/                            # Version control
```

---

## Performance Metrics

### Processing Latency

| Component | Latency | Bottleneck |
|-----------|---------|-----------|
| Image capture from ESP | 50-200ms | Network |
| Plate detection (YOLO) | 30-50ms | GPU/CPU |
| OCR processing | 100-300ms | EasyOCR |
| Total ANPR pipeline | 200-600ms | OCR processing |
| Slot detection | 30-50ms | GPU/CPU |
| GUI update | 100ms | Queue processing |

### Resource Utilization

**CPU**: 15-25% (single core monitoring)
**RAM**: 1.5-2.5GB (with models loaded)
**Network Bandwidth**: 2-4 Mbps per camera feed

### Recommended Optimizations

1. **GPU Acceleration**: Enable CUDA for YOLO inference (3-5x speedup)
2. **Model Quantization**: Convert models to FP16 for reduced memory
3. **Frame Skipping**: Process every 2nd or 3rd frame during low traffic
4. **Connection Pooling**: Reuse HTTP connections to ESP devices

---

## Troubleshooting

### Issue: Camera feeds not displaying

**Symptoms**: Black canvas in ANPR/Slot sections

**Solutions**:
```python
# 1. Verify ESP IP addresses
ping 10.115.207.192
ping 10.115.207.35

# 2. Check network connectivity
# 3. Verify /capture endpoint returns valid JPEG
# 4. Check firewall settings
```

### Issue: Plates not being detected

**Symptoms**: No plate recognition despite vehicles passing

**Causes & Fixes**:
- Low image quality → Adjust camera focus/lighting
- Model confidence too high → Lower `conf` threshold (e.g., 0.3)
- Plate not in known plates list → Update `KNOWN_PLATES`
- Poor OCR accuracy → Adjust preprocessing parameters

### Issue: High false positives in slot detection

**Solutions**:
- Increase confidence threshold: `conf=0.7`
- Retrain model with cleaner data
- Adjust lighting conditions in parking area

### Issue: Application crashes on startup

```bash
# 1. Verify all dependencies installed
pip list

# 2. Check model files exist
ls models/

# 3. Verify CUDA/GPU drivers (if using GPU)
python -c "import torch; print(torch.cuda.is_available())"

# 4. Check Tkinter installation
python -m tkinter
```

### Issue: Memory leaks with long runtime

**Solutions**:
- Restart application daily
- Implement periodic frame buffer cleanup
- Monitor with `psutil` for memory trends

---

## Security Considerations

### Best Practices

1. **Network Security**
   - Restrict ESP device access to internal network only
   - Use VPN for remote administration
   - Implement IP whitelisting

2. **Data Protection**
   - Store license plates securely (encrypted database)
   - Implement audit logging for all transactions
   - Regular backups of transaction data

3. **Authentication**
   - Restrict dashboard access to authorized operators
   - Implement role-based access control (future enhancement)
   - Audit log all admin operations

4. **Plate Database**
   - Regular updates to known plates
   - Secure storage of vehicle owner information
   - GDPR/privacy law compliance

---

## Monitoring & Logging

### System Health Metrics

**Key Metrics to Monitor**:
- Camera connectivity status
- Detection success rate (plates recognized/total detected)
- Average processing latency
- Memory and CPU utilization
- Network bandwidth usage

### Recommended Logging

```python
# Add logging to production deployment
import logging

logging.basicConfig(
    filename='parking_system.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

---

## Deployment Recommendations

### Development Environment
- Single machine deployment
- Manual plate database updates
- Local network access

### Production Environment

1. **Server Deployment**
   - Dedicated Linux server with GPU
   - Containerized with Docker
   - Automated backup systems

2. **Database Integration**
   - SQLite/PostgreSQL for transaction persistence
   - Real-time data synchronization
   - Historical analytics queries

3. **Monitoring Stack**
   - Prometheus for metrics collection
   - Grafana dashboards for visualization
   - Alert system for failures

4. **Scalability**
   - Load balancer for multiple parking lots
   - Microservices architecture (camera monitoring, fee calculation, reporting)
   - Cloud-based deployment with auto-scaling

---

## Future Enhancements

### Short-term (3-6 months)
- [ ] Database integration for persistent transaction storage
- [ ] User authentication and role-based access
- [ ] SMS/Email notifications for operators
- [ ] Mobile app for remote monitoring

### Medium-term (6-12 months)
- [ ] Payment gateway integration (UPI, credit card)
- [ ] License plate validation via VAHAN database API
- [ ] Behavioral analytics (peak hours, occupancy patterns)
- [ ] Predictive occupancy estimation
- [ ] Multi-lot management dashboard

### Long-term (12+ months)
- [ ] AI-based unauthorized parking detection
- [ ] Computer vision for parking enforcement
- [ ] Integration with traffic management systems
- [ ] EV charging station integration
- [ ] IoT sensor network for environmental monitoring

---

## Support & Maintenance

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024 | Initial release with ANPR and slot detection |

### Contact & Support

- **Development Team**: [Contact Information]
- **Bug Reports**: [Issue Tracker Link]
- **Documentation**: [Wiki Link]

### Maintenance Schedule

- **Daily**: Monitor system health and availability
- **Weekly**: Backup transaction data and system logs
- **Monthly**: Model performance review and updates
- **Quarterly**: Security audit and dependency updates

---

## License

Proprietary Software - All Rights Reserved

---

**Last Updated**: May 24, 2026  
**Documentation Version**: 1.0
