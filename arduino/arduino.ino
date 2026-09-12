#include <Servo.h>

// ======================================================
// MULTI-PIN SERVO DRIVER (PINS 5, 6, 7, 8, 9, 10, 11)
// Drives all available digital pins simultaneously so that
// the servo works regardless of which pin the user plugged it into!
// ======================================================
const int NUM_SERVO_PINS = 7;
const int servoPins[NUM_SERVO_PINS] = {5, 6, 7, 8, 9, 10, 11};
Servo servos[NUM_SERVO_PINS];

// Configurable angles (can be adjusted live from frontend)
int center_angle = 35;   // Neutral flap position
int dry_angle    = 140;  // Dry waste chute
int wet_angle    = 0;    // Wet waste chute (can rotate more, e.g. 0 to 180)

const unsigned long OPEN_TIME = 6000; // 6 seconds open for waste drop

// Helper to write to ALL servo pins simultaneously
void writeServo(int angle) {
  int safeAngle = constrain(angle, 0, 180);
  for (int i = 0; i < NUM_SERVO_PINS; i++) {
    servos[i].write(safeAngle);
  }
}

// ======================================================
// HX711 LOAD CELL CONFIGURATION (NON-BLOCKING SAFE)
// ======================================================
const int DOUT_PIN = 3;
const int SCK_PIN  = 2;

long scale_offset = 0;
float calibration_factor = 104.2;
float base_weight = 0.0;

// Safe non-blocking bitbang read for HX711
bool readRawHX711(long &val) {
  unsigned long start = millis();
  while (digitalRead(DOUT_PIN) == HIGH) {
    if (millis() - start > 120) {
      return false; // HX711 not ready or disconnected
    }
  }
  
  unsigned long count = 0;
  noInterrupts();
  for (int i = 0; i < 24; i++) {
    digitalWrite(SCK_PIN, HIGH);
    delayMicroseconds(1);
    count = count << 1;
    digitalWrite(SCK_PIN, LOW);
    delayMicroseconds(1);
    if (digitalRead(DOUT_PIN)) {
      count++;
    }
  }
  // 25th pulse for Channel A, 128 gain
  digitalWrite(SCK_PIN, HIGH);
  delayMicroseconds(1);
  digitalWrite(SCK_PIN, LOW);
  delayMicroseconds(1);
  interrupts();

  // Sign extension for 24-bit two's complement
  if (count & 0x800000) {
    count |= 0xFF000000;
  }
  val = (long)count;
  return true;
}

float readWeight() {
  long raw = 0;
  long sum = 0;
  int valid = 0;
  for (int i = 0; i < 5; i++) {
    if (readRawHX711(raw)) {
      sum += raw;
      valid++;
    }
    delay(10);
  }
  if (valid == 0) return 0.0;
  long avg = sum / valid;
  float w = (float)(avg - scale_offset) / calibration_factor;
  if (abs(w) < 15.0) w = 0.0; // Noise filter: ignore < 15g
  return w;
}

// ======================================================
// SETUP
// ======================================================
void setup() {
  Serial.begin(9600);
  delay(500);

  // HX711 Pins
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);
  pinMode(DOUT_PIN, INPUT);

  // Attach servos to ALL digital pins (5, 6, 7, 8, 9, 10, 11) with full SG90 pulse range
  for (int i = 0; i < NUM_SERVO_PINS; i++) {
    servos[i].attach(servoPins[i], 500, 2500);
  }
  writeServo(center_angle);

  // Tare load cell if ready
  long raw = 0;
  if (readRawHX711(raw)) {
    scale_offset = raw;
    Serial.println("HX711:ONLINE");
  } else {
    Serial.println("HX711:OFFLINE");
  }

  Serial.println("ARDUINO READY");
  Serial.flush();
}

// ======================================================
// MAIN LOOP
// ======================================================
void loop() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  // 1. Move servo immediately to specific angle (for live slider adjustment)
  if (cmd.startsWith("MOVE:")) {
    int target = cmd.substring(5).toInt();
    writeServo(target);
    Serial.print("SERVO:MOVED:");
    Serial.println(target);
    Serial.flush();
  }

  // 2. Configure servo angles from frontend: CONFIG:<center>,<dry>,<wet>
  else if (cmd.startsWith("CONFIG:")) {
    String rest = cmd.substring(7);
    int c1 = rest.indexOf(',');
    int c2 = rest.indexOf(',', c1 + 1);
    if (c1 > 0 && c2 > 0) {
      center_angle = constrain(rest.substring(0, c1).toInt(), 0, 180);
      dry_angle    = constrain(rest.substring(c1 + 1, c2).toInt(), 0, 180);
      wet_angle    = constrain(rest.substring(c2 + 1).toInt(), 0, 180);
      writeServo(center_angle);
      Serial.print("CONFIG:OK:");
      Serial.print(center_angle); Serial.print(",");
      Serial.print(dry_angle); Serial.print(",");
      Serial.println(wet_angle);
      Serial.flush();
    }
  }

  // 3. Base tare / baseline measurement before item is placed
  else if (cmd == "BASE") {
    base_weight = readWeight();
    Serial.print("BASE_WEIGHT:");
    Serial.println(base_weight, 1);
    Serial.flush();
  }

  // 4. Dry Waste Action
  else if (cmd == "DRY") {
    writeServo(dry_angle);
    delay(OPEN_TIME);

    writeServo(center_angle);
    delay(1000);

    float final_weight = readWeight();
    float item_weight = final_weight - base_weight;
    if (item_weight < 0) item_weight = 0;

    Serial.print("ITEM_WEIGHT:");
    Serial.println(item_weight, 1);
    Serial.flush();
  }

  // 5. Wet Waste Action
  else if (cmd == "WET") {
    writeServo(wet_angle);
    delay(OPEN_TIME);

    writeServo(center_angle);
    delay(1000);

    float final_weight = readWeight();
    float item_weight = final_weight - base_weight;
    if (item_weight < 0) item_weight = 0;

    Serial.print("ITEM_WEIGHT:");
    Serial.println(item_weight, 1);
    Serial.flush();
  }

  // 6. Test Servo Sweep
  else if (cmd == "TEST_SERVO") {
    Serial.print("SERVO:MOVING_DRY:");
    Serial.println(dry_angle);
    Serial.flush();
    writeServo(dry_angle);
    delay(1500);

    Serial.print("SERVO:MOVING_WET:");
    Serial.println(wet_angle);
    Serial.flush();
    writeServo(wet_angle);
    delay(1500);

    Serial.print("SERVO:MOVING_CENTER:");
    Serial.println(center_angle);
    Serial.flush();
    writeServo(center_angle);
    delay(500);

    Serial.println("SERVO_TEST:DONE");
    Serial.flush();
  }

  // 7. Reset Flap
  else if (cmd == "NONE" || cmd == "RESET") {
    writeServo(center_angle);
    Serial.println("SERVO:CENTER");
    Serial.flush();
  }

  // 8. Ping / Status
  else if (cmd == "PING") {
    Serial.println("PONG");
    Serial.flush();
  }
}