// Isolated HC-SR04-only Wokwi variant. No magnetic fusion, live battery or MQTT claim.
#include <Arduino.h>

#define SENSOR_SELF_TEST 0
const int TRIG_PIN = 5;
const int ECHO_PIN = 18;
const uint32_t ECHO_TIMEOUT_US = 25000;
const uint32_t POLL_MS = 100;
const uint32_t HEARTBEAT_MS = 5000;
const uint32_t SPOT_ID = 1001;
const uint16_t BATTERY_PLACEHOLDER_MV = 3600; // NOT measured; retained wire field only

struct Reading { bool valid; uint32_t mm; };
Reading distanceFromEcho(uint32_t pulse) {
  if (pulse == 0 || pulse >= ECHO_TIMEOUT_US) return {false, 0};
  uint32_t mm = (pulse * 10U + 29U) / 58U;
  // 58 us/cm is approximate: Wokwi's nominal 400cm can calculate about 4056mm.
  return {mm >= 20 && mm <= 4100, mm};
}

class Occupancy {
 public:
  bool known = false, occupied = false, trusted = false, fault = true;
  int candidate = -1;
  uint32_t since = 0;
  // 1 = initial/recovered same-state baseline (heartbeat); 2 = actual transition.
  int sample(uint32_t pulse, uint32_t now) {
    Reading value = distanceFromEcho(pulse);
    if (!value.valid) { trusted = false; fault = true; candidate = -1; return 0; }
    int target = value.mm <= 120 ? 1 : value.mm >= 220 ? 0 : -1;
    if (target < 0) { candidate = -1; return 0; } // hysteresis band never invents initial state
    if (trusted && target == int(occupied)) { candidate = -1; return 0; }
    if (candidate != target) { candidate = target; since = now; return 0; }
    uint32_t confirm = target ? 1500 : 2500;
    if (uint32_t(now - since) < confirm) return 0;
    bool changed = known && occupied != bool(target);
    known = true; occupied = bool(target); trusted = true; fault = false; candidate = -1;
    return changed ? 2 : 1;
  }
};

Occupancy sensor;
uint8_t counter = 0;
uint32_t lastMessage = 0;

void emitState(bool heartbeat) {
  // Emit only confirmed, currently trusted observations. Timeout is never Free.
  if (!sensor.known || !sensor.trusted) return;
  Serial.printf("{\"spot_id\":%lu,\"occupied\":%s,\"batt_mv\":%u,\"status\":%u,\"ctr\":%u,\"heartbeat\":%s}\n",
    (unsigned long)SPOT_ID, sensor.occupied ? "true" : "false", BATTERY_PLACEHOLDER_MV,
    sensor.occupied ? 1 : 0, counter++, heartbeat ? "true" : "false");
  lastMessage = millis();
}

uint32_t measureEcho() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  return pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
}

void selfTest() {
  int passed = 0, failed = 0;
  auto check = [&](const char *name, bool ok) {
    Serial.printf("[SELFTEST] %s %s\n", ok ? "PASS" : "FAIL", name);
    ok ? passed++ : failed++;
  };
  check("zero_timeout_invalid", !distanceFromEcho(0).valid);
  check("timeout_limit_invalid", !distanceFromEcho(25000).valid);
  check("malformed_large_invalid", !distanceFromEcho(0xffffffff).valid);
  check("below_minimum_invalid", !distanceFromEcho(58).valid);
  check("400cm_valid", distanceFromEcho(23200).valid && distanceFromEcho(23200).mm == 4000);
  check("wokwi_400cm_echo_valid", distanceFromEcho(23523).valid);
  check("10cm_conversion", distanceFromEcho(580).mm == 100);
  Occupancy a; a.sample(580, 0);
  check("near_not_immediate", !a.known && a.sample(580, 1499) == 0);
  check("near_1500_confirmed", a.sample(580, 1500) == 1 && a.occupied && a.trusted);
  check("hysteresis_preserves_state", a.sample(986, 1600) == 0 && a.occupied);
  a.sample(2030, 1700);
  check("free_2499_not_confirmed", a.sample(2030, 4199) == 0 && a.occupied);
  check("free_2500_confirmed", a.sample(2030, 4200) == 2 && !a.occupied);
  a.sample(580, 4300); a.sample(986, 5000); a.sample(580, 5100);
  check("band_resets_debounce", a.sample(580, 6000) == 0 && !a.occupied);
  a.sample(0, 6100);
  check("timeout_does_not_free_or_trust", a.known && !a.trusted && a.fault && !a.occupied);
  a.sample(2030, 6200);
  check("recovery_requires_debounce", !a.trusted && a.sample(2030, 8699) == 0);
  check("recovery_same_state_heartbeat", a.sample(2030, 8700) == 1 && a.trusted);
  Occupancy b; b.sample(986, 0); b.sample(986, 10000);
  check("initial_band_remains_unknown", !b.known);
  Occupancy c; c.sample(696, 0);
  check("inclusive_120mm_near", c.sample(696, 1500) == 1 && c.occupied);
  c.sample(1276, 1600);
  check("inclusive_220mm_free", c.sample(1276, 4100) == 2 && !c.occupied);
  Occupancy d; d.sample(580, 0xffffff00U);
  check("millis_wraparound_debounce", d.sample(580, uint32_t(0xffffff00U + 1500U)) == 1);
  Serial.printf("[SELFTEST] SUMMARY passed=%d failed=%d\n", passed, failed);
}

void setup() {
  Serial.begin(115200); delay(300);
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT); digitalWrite(TRIG_PIN, LOW);
  Serial.println("[BOOT] HC-SR04-only measured Wokwi variant; battery placeholder; no MQTT");
  if (SENSOR_SELF_TEST) selfTest();
}

void loop() {
  if (SENSOR_SELF_TEST) { delay(1000); return; }
  uint32_t pulse = measureEcho();
  uint32_t now = millis();
  int result = sensor.sample(pulse, now);
  Reading value = distanceFromEcho(pulse);
  Serial.printf("[SENSOR] t_ms=%lu echo_us=%lu distance_mm=%lu valid=%d known=%d trusted=%d occupied=%d fault=%d\n",
    (unsigned long)now, (unsigned long)pulse, (unsigned long)value.mm,
    value.valid, sensor.known, sensor.trusted, sensor.occupied, sensor.fault);
  if (result) emitState(result == 1);
  else if (sensor.trusted && uint32_t(now - lastMessage) >= HEARTBEAT_MS) emitState(true);
  delay(POLL_MS);
}
