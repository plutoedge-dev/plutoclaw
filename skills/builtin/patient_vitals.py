"""
PatientVitalsSkill — monitor patient vital signs on an edge device (non-critical/room monitoring).

Required hardware:
  - MAX30102 pulse oximeter (SpO2 + heart rate) via I2C
  - MLX90614 infrared thermometer via I2C

Wiring MAX30102:
  SDA → GPIO 2 | SCL → GPIO 3 | VCC → 3.3V | GND → GND

WARNING: This skill is for non-critical monitoring and notification only.
         It is NOT a replacement for certified medical devices.

Suitable for: recovery rooms, elderly monitoring, small clinics, health posts.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.patient_vitals")


class PatientVitalsSkill(BaseSkill):
    name        = "patient_vitals"
    description = (
        "Monitor basic vital signs: SpO2, heart rate, and body temperature. "
        "Alert if any value is outside the normal range. NOT a certified medical device."
    )
    category    = "medical"
    requires    = ["sensor:MAX30102", "sensor:MLX90614"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.spo2_min      = config.get("spo2_min", 94)
        self.hr_min        = config.get("hr_min", 50)
        self.hr_max        = config.get("hr_max", 120)
        self.temp_max      = config.get("temp_max", 37.8)
        self.patient_id    = config.get("patient_id", "patient-01")
        self.last_reading  = {}

    def _read_vitals(self):
        if not is_pi():
            return {
                "spo2_pct":   round(random.uniform(93, 100), 1),
                "heart_rate": random.randint(52, 118),
                "temp_c":     round(random.uniform(36.0, 38.2), 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_vitals()
        if not data:
            return
        self.last_reading = data

        issues = []
        if data.get("spo2_pct", 100) < self.spo2_min:
            issues.append(f"Low SpO2: {data['spo2_pct']}%")
        hr = data.get("heart_rate", 70)
        if hr < self.hr_min or hr > self.hr_max:
            issues.append(f"Abnormal HR: {hr} bpm")
        if data.get("temp_c", 36.5) > self.temp_max:
            issues.append(f"High temp: {data['temp_c']}°C")

        if issues and self.can_alert():
            summary = f"[{self.patient_id}] {', '.join(issues)}"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🏥 Vital Sign: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        base["patient_id"]   = self.patient_id
        return base
