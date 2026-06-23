"""
FloodDetectorSkill — detect water leaks or flooding in a home/warehouse.

Required hardware:
  - Water/flood sensor (DO → GPIO)
  - Optional: ultrasonic HC-SR04 for water level (TRIG + ECHO GPIO)

Wiring flood sensor:
  VCC → Pin 2 | GND → Pin 6 | DO → GPIO 25

Suitable for: server rooms, basements, kitchens, bathrooms, warehouses.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.flood_detector")


class FloodDetectorSkill(BaseSkill):
    name        = "flood_detector"
    description = (
        "Detect water leaks or flood pooling using a water sensor. "
        "Alert immediately when water is detected."
    )
    category    = "smart_home"
    requires    = ["sensor:water"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.sensor_pin   = config.get("sensor_pin", 25)
        self.location     = config.get("location", "Server Room")
        self.last_reading = {}

    def _read_sensor(self):
        if not is_pi():
            return {"water_detected": random.random() < 0.05}
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.sensor_pin, GPIO.IN)
            return {"water_detected": bool(GPIO.input(self.sensor_pin))}
        except Exception as e:
            logger.warning(f"Water sensor error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_sensor()
        if not data:
            return
        self.last_reading = data

        if data.get("water_detected") and self.can_alert():
            summary = f"Water detected at {self.location}!"
            ok, reason = self.should_alert(summary, context="Water leak or flood can cause property damage")
            if ok and self.alert:
                self.alert.send(f"🚨 FLOOD ALERT: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
