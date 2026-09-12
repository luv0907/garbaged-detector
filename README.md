# ♻️ Smart Waste Classification System (AI + Arduino)

An **AI-powered waste classification system** that integrates **computer vision**, a **web-based interface**, and **Arduino hardware** to classify waste (wet/dry).  
Designed for hackathons, college projects, and real-world smart city applications.

🔗 GitHub Repository: https://github.com/Shanmukhcr7/hackathon

---

## 📁 Project Structure

├── main.py # Python backend (AI + Arduino communication)
├── requirements.txt # Python dependencies
├── my-waste-app/ # Frontend (Vite + React)
│ ├── package.json
│ └── ...
├── Arduino/
│ └── HX711-ADC-MASTER/ # HX711 amplifier module library
└── README.md


---

## ✅ Prerequisites

Make sure the following are installed:

- Python 3.9 or higher
- Node.js 18+
- npm
- Arduino IDE
- USB Camera / Webcam
- Arduino Board
- HX711 Amplifier Module

---

## 🚀 Installation & Execution Steps

### Step 1️⃣ Clone the Repository

```bash
git clone https://github.com/Shanmukhcr7/hackathon
cd hackathon

pip install -r requirements.txt


Step 3️⃣ Run the Python + Arduino Backend

This starts:

Camera-based image capture

AI waste classification

Arduino serial communication

python main.py


⚠️ Ensure:

Arduino is connected

Correct COM port is set

Arduino IDE Serial Monitor is CLOSED

Step 4️⃣ Navigate to Frontend Folder
cd my-waste-app

Step 5️⃣ Install Frontend Dependencies
npm install

Step 6️⃣ Start the Frontend Development Server
npm run dev

Step 7️⃣ Open the Web Application

Open your browser and go to:

https://localhost:5173


📸 This interface is used for capturing waste images and interacting with the AI system.

🔌 Arduino Library Setup (VERY IMPORTANT)
HX711 Amplifier Module Library

Copy the folder:

HX711-ADC-MASTER


Paste it into:

Documents → Arduino → libraries → (paste here)


Restart the Arduino IDE

This library is required for proper HX711 load cell / amplifier module communication.

🧠 How the System Works

Camera captures the waste image

AI model classifies waste (wet / dry)

Arduino reads sensor data via HX711

Backend processes results

Frontend displays classification output in real time

🛠 Troubleshooting
❌ COM Port Permission Error

Close Arduino IDE and Serial Monitor

Reconnect Arduino

Run python main.py again

❌ HX711 Not Working

Verify wiring

Confirm library placement

Restart Arduino IDE

❌ Frontend Not Loading

Make sure npm run dev is running

Ensure port 5173 is free

