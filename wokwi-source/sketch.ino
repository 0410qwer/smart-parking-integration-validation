// --- ESP32 Parking Node Simulator (Wokwi) ---
// Simulates occupancy and prints BLE-like advertising payloads to Serial.

#include <Arduino.h>

// === Config you can tweak ===
static uint32_t SPOT_ID = 1001;      // default; change via Serial: ID=12345
const uint32_t COMPANY_ID = 0xFFFF;  // replace with your Company ID later
const uint8_t  PROTO_VER  = 0x01;

// Heartbeat / cadence
const unsigned long HEARTBEAT_MS = 5000; // steady-state publish
const unsigned long LOOP_MS       = 200; // sensor poll rate

// Occupancy thresholds (for mocked signals)
const int TH_MAG_ON   = 60;   // delta nT to consider "car present"
const int TH_MAG_OFF  = 25;   // back to baseline
const int TH_DIST_ON  = 120;  // ToF (mm) < this => near (car)
const int TH_DIST_OFF = 220;  // ToF (mm) > this => empty

// Debounce durations
const unsigned long CONFIRM_ON_MS  = 1500; // need stable presence
const unsigned long CONFIRM_OFF_MS = 2500; // need stable absence

enum State { FREE, PROV_OCC, OCCUPIED, PROV_FREE };
State state = FREE;

bool occupied = false;
unsigned long stateChangedAt = 0;
unsigned long lastHeartbeat  = 0;
uint8_t  counter    = 0;
uint16_t battery_mv = 3600;  // mocked battery

int mockMagDelta() {
  static unsigned long t0 = millis();
  unsigned long t = (millis() - t0) / 1000;  // seconds
  int phase = t % 70;                         // cycle pattern every 70s
  int base = (phase >= 20 && phase < 55) ? 80 : 10; // higher when "car present"
  base += random(-5, 6);                      // noise
  return max(0, base);
}

int mockToFmm() {
  int mag = mockMagDelta();
  int base = (mag > 60) ? 90 : 350;  // mm: near when occupied
  base += random(-20, 21);
  return max(50, base);
}

typedef struct __attribute__((packed)) {
  uint16_t company_id;  // 0xFFFF placeholder
  uint8_t  ver;         // protocol version
  uint32_t spot_id;
  uint8_t  status;      // bit0=occupied, bit1=fault, bit2=low_batt
  uint16_t batt_mv;
  uint8_t  ctr;
} adv_t;

void printAdv(bool occupiedFlag, bool lowBatt=false, bool fault=false, bool isHeartbeat=false) {
  adv_t p;
  p.company_id = COMPANY_ID;
  p.ver        = PROTO_VER;
  p.spot_id    = SPOT_ID;
  p.status     = (occupiedFlag ? 0x01 : 0x00) | (fault ? 0x02 : 0x00) | (lowBatt ? 0x04 : 0x00);
  p.batt_mv    = battery_mv;
  p.ctr        = counter++;

  // JSON (gateway-friendly)
  Serial.printf(
    "{\"spot_id\":%lu,\"occupied\":%s,\"batt_mv\":%u,\"status\":%u,\"ctr\":%u,\"heartbeat\":%s}\n",
    (unsigned long)p.spot_id,
    occupiedFlag ? "true" : "false",
    p.batt_mv, p.status, p.ctr,
    isHeartbeat ? "true" : "false"
  );

  // Hex payload (what would be in BLE manufacturer data)
  const uint8_t* bytes = (const uint8_t*)&p;
  Serial.print("HEX:");
  for (size_t i = 0; i < sizeof(p); i++) {
    if (bytes[i] < 16) Serial.print('0');
    Serial.print(bytes[i], HEX);
  }
  Serial.println();
}

void handleSerial() {
  if (!Serial.available()) return;
  String s = Serial.readStringUntil('\n'); s.trim();
  if (s.startsWith("ID=")) {
    String num = s.substring(3);
    SPOT_ID = (uint32_t) strtoul(num.c_str(), nullptr, 10);
    Serial.printf("[CFG] Spot ID set to %lu\n", (unsigned long)SPOT_ID);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("[BOOT] Parking Node Simulator starting...");
  Serial.println("Type: ID=<number> to set Spot ID");
  randomSeed(analogRead(0));
  stateChangedAt = millis();
  lastHeartbeat  = millis();
}

void loop() {
  handleSerial();

  int mag = mockMagDelta();
  int dmm = mockToFmm();
  unsigned long now = millis();

  switch (state) {
    case FREE:
      if (mag > TH_MAG_ON && dmm < TH_DIST_ON) {
        state = PROV_OCC; stateChangedAt = now;
      }
      break;
    case PROV_OCC:
      if (mag > TH_MAG_ON && dmm < TH_DIST_ON) {
        if (now - stateChangedAt >= CONFIRM_ON_MS) {
          state = OCCUPIED; occupied = true; printAdv(true, false, false, false);
        }
      } else { state = FREE; stateChangedAt = now; }
      break;
    case OCCUPIED:
      if (mag < TH_MAG_OFF && dmm > TH_DIST_OFF) {
        state = PROV_FREE; stateChangedAt = now;
      }
      break;
    case PROV_FREE:
      if (mag < TH_MAG_OFF && dmm > TH_DIST_OFF) {
        if (now - stateChangedAt >= CONFIRM_OFF_MS) {
          state = FREE; occupied = false; printAdv(false, false, false, false);
        }
      } else { state = OCCUPIED; stateChangedAt = now; }
      break;
  }

  // Heartbeat
  if (now - lastHeartbeat >= HEARTBEAT_MS) {
    lastHeartbeat = now;
    if (battery_mv > 3000) battery_mv -= 1;   // slow drain
    bool lowBatt = battery_mv < 3200;
    printAdv(occupied, lowBatt, false, true);
  }

  delay(LOOP_MS);
}
