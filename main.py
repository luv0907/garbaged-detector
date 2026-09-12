import os
import io
import time
import glob
import json
import uuid
import base64
from typing import Optional

import cv2
import numpy as np
import serial
import qrcode
from PIL import Image
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
BAUD_RATE = int(os.getenv("BAUD_RATE", 9600))
DRY_RATE = float(os.getenv("DRY_RATE", 0.02))
WET_RATE = float(os.getenv("WET_RATE", 0.005))

IMAGE_PATH = "captured.jpg"
RECORDS_FILE = "waste_records.json"

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==============================
# FIREBASE FIRESTORE INIT
# ==============================
db = None
if os.path.exists("serviceAccountKey.json"):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore connected successfully!")
    except Exception as e:
        print(f"⚠️ Firebase init failed: {e}")

# ==============================
# OPTIMIZED WASTE VISION PROMPT
# ==============================
PROMPT = """
You are an expert computer vision model for an automated smart waste sorting bin.
Your job is to identify the primary waste item held up or presented to the camera in the image and classify it as either DRY WASTE or WET WASTE.

CRITICAL INSTRUCTIONS:
- If a person is holding the item, or standing in front of the camera, IGNORE the person, their clothes, their face, hands, and room background!
- Focus EXCLUSIVELY on the target waste item, particle, object, scrap, or debris being presented for sorting.

Classification Categories & Criteria:

1. DRY WASTE (Non-biodegradable, moisture-free, recyclable, or dry sweepings):
- dry dust / sweepings (household dry dust, floor sweepings, powdery dirt, dry sand, crumbs, lint, ash)
- plastic (plastic bottles, cups, wraps, bags, containers, plastic packaging, caps)
- paper & cardboard (dry paper sheets, notebooks, cartons, clean tissues, paper cups)
- metal (aluminum soda cans, tins, foils, bottle caps, metal scraps)
- glass (bottles, jars, broken glass pieces)
- electronics / battery (batteries, cables, wires, e-waste)
- dry others (shoes, dry cloth rags)

2. WET WASTE (Moisture-containing, organic, biodegradable, or muddy/wet waste):
- wet dust / mud (moist dirt, wet soil, wet mud, damp swept sludge, soaked dirt, wet slurry)
- food & organic (fruit peels, banana peels, apple cores, vegetable scraps, leftover cooked food, tea bags, coffee grounds, egg shells, bones)
- biological & plant (wet leaves, fresh flowers, plants, lawn clippings)
- soiled wet paper / wipes (damp food-stained napkins, wet wipes)
- wet others (liquid/slurry food waste, damp compostable matter)

Dust / Waste Classification Rules:
1. DUST/DIRT CLASSIFICATION:
   - If the dust, dirt, or sweepings appear DRY, powdery, or dry debris -> classify as: dry dust, dry-waste
   - If the dust, dirt, or sweepings appear WET, damp, muddy, moist, sludge, or soaked -> classify as: wet dust, wet-waste
2. GENERAL CLASSIFICATION:
   - Any organic food matter, peels, or moist kitchen scraps -> classify as: organic, wet-waste
   - Any plastic, metal, dry paper, dry packaging -> classify as: <subcategory>, dry-waste
3. Output MUST strictly be a single line in this exact format:
<subcategory>, <main-category>

Examples:
- dry dust or sweepings -> dry dust, dry-waste
- wet dust, wet dirt, or mud -> wet dust, wet-waste
- banana peel -> organic, wet-waste
- plastic water bottle -> plastic, dry-waste
- damp food leftovers -> organic, wet-waste
- aluminum can -> metal, dry-waste
- dry paper scrap -> paper, dry-waste
"""

app = FastAPI(title="Smart Waste Sorter API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_header(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

# ==============================
# SERIAL ARDUINO MANAGER
# ==============================
class ArduinoManager:
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.port: Optional[str] = None
        self.connect()

    def find_port(self) -> Optional[str]:
        # macOS serial ports
        ports = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/cu.wchusbserial*")
        if ports:
            return ports[0]
        # Windows fallback if needed
        windows_ports = [f"COM{i}" for i in range(1, 25)]
        for p in windows_ports:
            try:
                s = serial.Serial(p)
                s.close()
                return p
            except Exception:
                pass
        return None

    def connect(self) -> bool:
        if self.serial_conn and self.serial_conn.is_open:
            return True
        port = self.find_port()
        if not port:
            return False
        try:
            self.serial_conn = serial.Serial(port, BAUD_RATE, timeout=2)
            self.port = port
            time.sleep(2)
            self.serial_conn.reset_input_buffer()
            print(f"🔌 Connected to Arduino on {port}")
            return True
        except Exception as e:
            print(f"⚠️ Failed to connect to Arduino on {port}: {e}")
            self.serial_conn = None
            return False

    def is_connected(self) -> bool:
        if self.serial_conn and self.serial_conn.is_open:
            try:
                _ = self.serial_conn.in_waiting
                return True
            except Exception:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
        return self.connect()

    def wait_for_serial(self, prefix: str, timeout: float = 18.0) -> Optional[float]:
        if not self.is_connected():
            return None
        start = time.time()
        while time.time() - start < timeout:
            try:
                if self.serial_conn and self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    print(f"📡 Arduino: {line}")
                    if line.startswith(prefix):
                        parts = line.split(":")
                        if len(parts) > 1:
                            return float(parts[1].strip())
            except Exception as e:
                print(f"Serial read error: {e}")
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
                break
            time.sleep(0.05)
        return None

    def send_command(self, cmd: str):
        if self.is_connected():
            try:
                print(f"📤 Sending to Arduino: {cmd.strip()}")
                self.serial_conn.write(cmd.encode())
                self.serial_conn.flush()
            except Exception as e:
                print(f"⚠️ Failed to send command: {e}")
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None

arduino_mgr = ArduinoManager()

# ==============================
# LOCAL DB HELPER
# ==============================
def save_local_record(record: dict):
    records = []
    if os.path.exists(RECORDS_FILE):
        try:
            with open(RECORDS_FILE, "r") as f:
                records = json.load(f)
        except Exception:
            records = []
    records.append(record)
    with open(RECORDS_FILE, "w") as f:
        json.dump(records, f, indent=2)

# ==============================
# REQUEST MODELS
# ==============================
class CapturePayload(BaseModel):
    image: Optional[str] = None

class ProcessWasteRequest(BaseModel):
    type: str

# ==============================
# ENDPOINTS
# ==============================

@app.get("/status")
async def get_status():
    connected = arduino_mgr.is_connected()
    return {
        "arduino_connected": connected,
        "port": arduino_mgr.port,
        "server": True
    }

@app.post("/measure-base")
async def measure_base():
    """Tares the scale or measures base weight before item placement"""
    print("\n⚖️ [Endpoint] /measure-base called")
    if not arduino_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Arduino board not connected! Please connect Arduino.")
    
    arduino_mgr.send_command("BASE\n")
    weight = arduino_mgr.wait_for_serial("BASE_WEIGHT", timeout=8.0)
    if weight is None:
        raise HTTPException(status_code=500, detail="Failed to read base weight from Arduino scale.")
    return {"weight": weight}

@app.post("/capture")
async def capture(payload: Optional[CapturePayload] = None):
    """Captures a photo directly from browser live video stream or OpenCV fallback"""
    print("\n📸 [Endpoint] /capture called")
    frame = None

    # 1. Prefer direct browser video frame (prevents macOS device lock and gives crisp user-aligned frame)
    if payload and payload.image:
        try:
            raw_base64 = payload.image
            if "," in raw_base64:
                raw_base64 = raw_base64.split(",", 1)[1]
            img_bytes = base64.b64decode(raw_base64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if decoded is not None and decoded.size > 0:
                frame = decoded
                print(f"✅ Frame received directly from browser camera ({frame.shape[1]}x{frame.shape[0]})")
        except Exception as e:
            print(f"⚠️ Error decoding browser image frame: {e}")

    # 2. Fallback to OpenCV webcam if browser didn't send image
    if frame is None:
        for idx in [0, 1, 2]:
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    # Warm up 5 frames for auto-exposure/balance
                    for _ in range(5):
                        cap.read()
                    ret, img = cap.read()
                    cap.release()
                    if ret and img is not None:
                        frame = img
                        print(f"✅ Frame captured from local OpenCV camera {idx}")
                        break
            except Exception as e:
                print(f"Camera index {idx} error: {e}")

    # 3. Fallback to existing or placeholder
    if frame is not None:
        cv2.imwrite(IMAGE_PATH, frame)
    elif os.path.exists(IMAGE_PATH):
        print(f"⚠️ Using existing '{IMAGE_PATH}'")
        frame = cv2.imread(IMAGE_PATH)
    else:
        print("⚠️ Generating placeholder image")
        placeholder = Image.new("RGB", (640, 480), color=(50, 50, 50))
        placeholder.save(IMAGE_PATH)
        frame = cv2.imread(IMAGE_PATH)

    # Encode image to base64 for preview in UI
    _, buffer = cv2.imencode(".jpg", frame)
    base64_str = base64.b64encode(buffer).decode("utf-8")
    return {"image": base64_str}

@app.post("/classify")
async def classify():
    """Classifies the captured image using Gemini 2.5 Flash Vision"""
    print("\n🧠 [Endpoint] /classify called")
    if not os.path.exists(IMAGE_PATH):
        raise HTTPException(status_code=400, detail="No captured image found. Call /capture first.")

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        img = Image.open(IMAGE_PATH)
        response = model.generate_content([PROMPT, img])
        result = response.text.strip().lower()
        print(f"🧠 AI Classification result: {result}")

        # Parse subcategory and main category
        # Format: <subcategory>, <main-category>
        parts = [p.strip() for p in result.split(",")]
        category = parts[0] if parts else "item"
        
        waste_type = "DRY"
        if "wet-waste" in result or "wet" in result:
            waste_type = "WET"
        elif "dry-waste" in result or "dry" in result:
            waste_type = "DRY"

        return {
            "category": category,
            "type": waste_type,
            "raw": result
        }
    except Exception as e:
        print(f"❌ Classification error: {e}")
        # Graceful fallback so app continues
        return {
            "category": "dry waste",
            "type": "DRY",
            "error": str(e)
        }

class MoveServoRequest(BaseModel):
    angle: int

class SetAnglesRequest(BaseModel):
    center_angle: int = 35
    dry_angle: int = 140
    wet_angle: int = 0

# Persistent angle state
current_angles = {
    "center_angle": 35,
    "dry_angle": 140,
    "wet_angle": 0
}

@app.get("/get-angles")
async def get_angles():
    return current_angles

@app.post("/move-servo")
async def move_servo(req: MoveServoRequest):
    """Moves servo immediately to specified angle for live slider adjustment"""
    if not arduino_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Arduino board not connected!")
    angle = max(0, min(180, req.angle))
    print(f"🎛️ [Endpoint] /move-servo called: {angle}°")
    arduino_mgr.send_command(f"MOVE:{angle}\n")
    return {"status": "moved", "angle": angle}

@app.post("/set-angles")
async def set_angles(req: SetAnglesRequest):
    """Configures neutral, dry, and wet angles on Arduino"""
    if not arduino_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Arduino board not connected!")
    c = max(0, min(180, req.center_angle))
    d = max(0, min(180, req.dry_angle))
    w = max(0, min(180, req.wet_angle))
    current_angles["center_angle"] = c
    current_angles["dry_angle"] = d
    current_angles["wet_angle"] = w
    print(f"📐 [Endpoint] /set-angles: Center={c}°, Dry={d}°, Wet={w}°")
    arduino_mgr.send_command(f"CONFIG:{c},{d},{w}\n")
    return {"status": "configured", "angles": current_angles}

@app.post("/test-servo")
async def test_servo():
    """Directly commands Arduino servo to perform a test sweep and verifies response"""
    print("\n⚙️ [Endpoint] /test-servo called")
    if not arduino_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Arduino board not connected!")
    arduino_mgr.send_command("TEST_SERVO\n")
    lines = []
    start = time.time()
    while time.time() - start < 4.5:
        if arduino_mgr.serial_conn and arduino_mgr.serial_conn.in_waiting:
            l = arduino_mgr.serial_conn.readline().decode(errors="ignore").strip()
            if l:
                print(f"📡 Arduino test reply: {l}")
                lines.append(l)
                if "SERVO_TEST:DONE" in l:
                    break
        time.sleep(0.05)
    return {"status": "Servo sweep test executed", "arduino_replies": lines}

@app.post("/process-waste")
async def process_waste(req: ProcessWasteRequest):
    """Rotates servo flap, measures final weight, calculates reward, creates QR voucher"""
    if not arduino_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Arduino board not connected! Please connect Arduino.")

    waste_type = req.type.upper()
    if waste_type not in ["DRY", "WET"]:
        waste_type = "DRY"

    print(f"\n🔄 [Endpoint] /process-waste called for {waste_type} waste")
    
    # Command servo to move to DRY or WET chute
    arduino_mgr.send_command(f"{waste_type}\n")
    # Arduino handles: open for 6s, return to center (1s), read weight, and prints ITEM_WEIGHT:XX
    item_weight = arduino_mgr.wait_for_serial("ITEM_WEIGHT", timeout=18.0)
    if item_weight is None:
        raise HTTPException(status_code=500, detail="Failed to communicate with Arduino scale.")
    if item_weight < 0:
        item_weight = 0.0

    # Calculate reward amount
    rate = DRY_RATE if waste_type == "DRY" else WET_RATE
    amount = round(item_weight * rate, 2)

    # Generate QR Code ID
    qr_id = "QR_" + uuid.uuid4().hex[:8].upper()

    # Generate QR Code image
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_id)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert QR Code directly to base64 in memory (no disk clutter)
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    # Save to Firebase Firestore
    if db:
        try:
            from firebase_admin import firestore
            qr_data = {
                "qr_id": qr_id,
                "amount": amount,
                "wasteType": waste_type.lower(),
                "weight": item_weight,
                "claimed": False,
                "claimedBy": None,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "claimedAt": None,
                "qr_code_base64": qr_base64
            }
            db.collection("qr_codes").document(qr_id).set(qr_data)
            print(f"🔥 QR document {qr_id} saved to Firestore successfully!")
        except Exception as e:
            print(f"⚠️ Firestore save error: {e}")
    else:
        # Fallback to local record only if Firebase is not connected
        record = {
            "qr_id": qr_id,
            "waste_type": waste_type.lower(),
            "weight": item_weight,
            "amount": amount,
            "claimed": False,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        save_local_record(record)

    return {
        "weight": item_weight,
        "amount": amount,
        "qr_code": qr_base64,
        "qr_id": qr_id
    }

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Smart Waste Backend on http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)