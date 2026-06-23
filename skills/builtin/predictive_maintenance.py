"""
PredictiveMaintenanceSkill — detect vibration/temperature anomalies before machine failure.

Required hardware:
  - Vibration sensor (SW-420 / ADXL345 via I2C)
  - Optional: NTC Thermistor or DS18B20 for bearing temperature

Wiring SW-420:
  VCC → Pin 2 | GND → Pin 6 | DO → GPIO 22

Suitable for: industrial machines, motors, pumps, conveyors, generators.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.predictive_maintenance")


class PredictiveMaintenanceSkill(BaseSkill):
    name        = "predictive_maintenance"
    description = (
        "Monitor machine vibration and temperature in real-time. "
        "Detect early anomalies to prevent unexpected failures."
    )
    category    = "industrial"
    requires    = ["sensor:vibration", "sensor:temperature"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.vib_pin       = config.get("vibration_pin", 22)
        self.temp_max      = config.get("temp_max", 80.0)
        self.vib_threshold = config.get("vib_threshold", 5)
        self.sensor_name   = config.get("sensor_name", "Main Machine")
        self.last_reading  = {}

    def _read_sensors(self):
        if not is_pi():
            return {
                "vibration_level": round(random.uniform(0.1, 3.0), 2),
                "bearing_temp_c":  round(random.uniform(30.0, 75.0), 1),
                "anomaly_count":   random.randint(0, 2),
            }
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.vib_pin, GPIO.IN)
            vib = GPIO.input(self.vib_pin)
            return {"vibration_level": float(vib), "bearing_temp_c": None, "anomaly_count": int(vib)}
        except Exception as e:
            logger.warning(f"Sensor read error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_sensors()
        if not data:
            return
        self.last_reading = data

        anom  = data.get("anomaly_count", 0)
        temp  = data.get("bearing_temp_c", 0) or 0
        alert_needed = anom >= self.vib_threshold or temp > self.temp_max

        if alert_needed and self.can_alert():
            summary = (
                f"{self.sensor_name} — vibration anomalies: {anom}, "
                f"bearing temp: {temp}°C (max {self.temp_max}°C)"
            )
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"⚙️ Predictive Maintenance: {summary}\n{reason}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
