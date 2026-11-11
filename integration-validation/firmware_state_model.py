"""Source-derived Python model, NOT execution of sketch.ino or physical sensing.

Models only loop switch cases and unsigned 32-bit elapsed-time arithmetic.
No mock RNG, heartbeat scheduler, hardware, or network implementation is implied.
"""


class OccupancyModel:
    def __init__(self):
        self.state = 'FREE'
        self.changed_at = 0
        self.occupied = False

    def step(self, now_ms, mag, distance_mm):
        present = mag > 60 and distance_mm < 120
        absent = mag < 25 and distance_mm > 220
        elapsed = (now_ms - self.changed_at) & 0xFFFFFFFF
        if self.state == 'FREE' and present:
            self.state, self.changed_at = 'PROV_OCC', now_ms
        elif self.state == 'PROV_OCC':
            if not present:
                self.state, self.changed_at = 'FREE', now_ms
            elif elapsed >= 1500:
                self.state, self.occupied = 'OCCUPIED', True
                return True
        elif self.state == 'OCCUPIED' and absent:
            self.state, self.changed_at = 'PROV_FREE', now_ms
        elif self.state == 'PROV_FREE':
            if not absent:
                self.state, self.changed_at = 'OCCUPIED', now_ms
            elif elapsed >= 2500:
                self.state, self.occupied = 'FREE', False
                return False
        return None
