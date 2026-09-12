import os
import sys
import time
import glob
import json
import uuid
import qrcode
import cv2
from PIL import Image
from dotenv import load_dotenv

import google.generativeai as genai

load_dotenv()

# ==============================
# CONFIG
# ==============================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
IMAGE_PATH = "captured.jpg"
BAUD_RATE = int(os.getenv("BAUD_RATE", 9600))
RECORDS_FILE = "waste_records.json"

# Auto-detect Arduino port on macOS/Windows/Linux
def find_arduino_port():
    ports = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/cu.wchusbserial*")
    if ports:
        return ports[0]
    for i in range(1, 25):
        p = f"COM{i}"
        try:
            import serial
            s = serial.Serial(p)
            s.close()
            return p
        except Exception:
            pass
    return None

# ==============================
# FIREBASE INIT (Optional)
# ==============================
db = None
if os.path.exists("serviceAccountKey.json"):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase connected successfully")
    except Exception as e:
        print(f"⚠️ Firebase init failed: {e}. Falling back to local mode.")
else:
    print("📁 'serviceAccountKey.json' not found: Running in Local Mode (QR and records saved locally).")

# ==============================
# RATE PER GRAM (₹)
# ==============================
RATES = {
    "DRY": float(os.getenv("DRY_RATE", 0.02)),
    "WET": float(os.getenv("WET_RATE", 0.005))
}

# ==============================
# PROMPT
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

# ==============================
# CAMERA
# ==============================
def capture_image():
    cap = None
    for idx in [0, 1, 2]:
        try:
            temp = cv2.VideoCapture(idx)
            if temp.isOpened():
                ret, _ = temp.read()
                if ret:
                    cap = temp
                    print(f"📷 Using camera index {idx}")
                    break
            temp.release()
        except Exception:
            pass

    if cap is None:
        if os.path.exists(IMAGE_PATH):
            print(f"⚠️ Camera not accessible. Using existing image '{IMAGE_PATH}'")
            return True
        elif os.path.exists("temp.jpg"):
            print("⚠️ Camera not accessible. Using 'temp.jpg'")
            import shutil
            shutil.copy("temp.jpg", IMAGE_PATH)
            return True
        print("❌ Camera not accessible and no fallback image found.")
        return False

    print("📸 Press SPACE to capture | ESC to cancel")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        cv2.imshow("Camera", frame)
        key = cv2.waitKey(1)

        if key == 27:  # ESC
            cap.release()
            cv2.destroyAllWindows()
            return False

        if key == 32:  # SPACE
            cv2.imwrite(IMAGE_PATH, frame)
            print("✅ Image captured")
            break

    cap.release()
    cv2.destroyAllWindows()
    return True

# ==============================
# GEMINI
# ==============================
def classify_image():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    image = Image.open(IMAGE_PATH)
    response = model.generate_content([PROMPT, image])
    result = response.text.lower()

    print("🧠 Gemini output:", result.strip())

    if "dry-waste" in result or "dry" in result:
        return "DRY"
    elif "wet-waste" in result or "wet" in result:
        return "WET"
    else:
        return "UNKNOWN"

# ==============================
# SERIAL HELPER
# ==============================
def wait_for_serial(prefix, ser, timeout=10):
    start = time.time()
    while True:
        if time.time() - start > timeout:
            return None

        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        print("🔎 Arduino:", line)
        if line.startswith(prefix):
            parts = line.split(":")
            if len(parts) > 1:
                return float(parts[1].strip())

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    import serial

    arduino_port = find_arduino_port()
    arduino = None

    if arduino_port:
        print(f"\n🔌 Connecting to Arduino on {arduino_port}...")
        try:
            arduino = serial.Serial(arduino_port, BAUD_RATE, timeout=2)
            time.sleep(2)
            arduino.reset_input_buffer()
            print("✅ Arduino connected!")
        except Exception as e:
            print(f"⚠️ Arduino connection failed: {e}")
            arduino = None
    else:
        print("\n⚠️ No Arduino port detected. Running in Demo/Simulation Mode.")

    # 1️⃣ BASE WEIGHT
    print("\n⚖️ Measuring base weight...")
    base_weight = 0.0
    if arduino:
        arduino.write(b"BASE\n")
        base_weight = wait_for_serial("BASE_WEIGHT", arduino, 8)
        if base_weight is None:
            print("⚠️ Failed to read base weight from Arduino, defaulting to 0.0g")
            base_weight = 0.0
    print(f"📏 Base weight: {base_weight} g")

    # 2️⃣ IMAGE CAPTURE
    if not capture_image():
        if arduino:
            arduino.close()
        sys.exit(0)

    # 3️⃣ CLASSIFY
    waste_type = classify_image()
    print("♻️ Waste type:", waste_type)

    if waste_type not in ["DRY", "WET"]:
        print("❌ Unable to classify waste")
        if arduino:
            arduino.close()
        sys.exit(1)

    # 4️⃣ SORT
    print(f"🔄 Sorting waste: {waste_type}...")
    if arduino:
        arduino.write((waste_type + "\n").encode())
        item_weight = wait_for_serial("ITEM_WEIGHT", arduino, 20)
        arduino.close()
    else:
        print("ℹ️ Simulating servo rotation and item weight...")
        time.sleep(2)
        item_weight = 45.0

    if item_weight is None or item_weight <= 0:
        item_weight = 25.0

    print(f"⚖️ Item weight: {item_weight} g")

    # 5️⃣ CALCULATE AMOUNT
    rate = RATES[waste_type]
    amount = round(item_weight * rate, 2)
    print(f"💰 Reward amount: ₹{amount}")

    # 6️⃣ GENERATE QR ID
    qr_id = "QR_" + uuid.uuid4().hex[:8].upper()

    # Save to Firebase if available
    if db:
        try:
            from firebase_admin import firestore
            qr_data = {
                "wasteType": waste_type.lower(),
                "weight": item_weight,
                "amount": amount,
                "claimed": False,
                "claimedBy": None,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "claimedAt": None
            }
            db.collection("qr_codes").document(qr_id).set(qr_data)
            print("🔥 Record saved to Firebase")
        except Exception as e:
            print(f"⚠️ Firebase save failed: {e}")

    # Save locally to waste_records.json
    records = []
    if os.path.exists(RECORDS_FILE):
        try:
            with open(RECORDS_FILE, "r") as f:
                records = json.load(f)
        except Exception:
            records = []
    records.append({
        "qr_id": qr_id,
        "waste_type": waste_type.lower(),
        "weight": item_weight,
        "amount": amount,
        "claimed": False,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    with open(RECORDS_FILE, "w") as f:
        json.dump(records, f, indent=2)

    print(f"🆔 QR ID: {qr_id}")

    # 7️⃣ GENERATE QR CODE
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_id)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(f"{qr_id}.png")

    print("\n📟 Scan this QR code:\n")
    qr.print_ascii(invert=True)

    print(f"\n📁 QR image saved as {qr_id}.png")
    print("\n✅ PROCESS COMPLETE\n")