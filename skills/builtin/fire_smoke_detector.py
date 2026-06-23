"""
FireSmokeDetectorSkill — detect smoke, LPG gas, and extreme heat.

Required hardware:
  - MQ-2 smoke/LPG sensor (DO → GPIO)
  - Optional: DS18B20 for hotspot temperature

Wiring MQ-2:
  VCC → Pin 2 | GND → Pin 6 | DO → GPIO 23

Suitable for: kitchen, fuel warehouse, electrical panel room, factory.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.fire_smoke_detector")


class FireSmokeDetectorSkill(BaseSkill):
    name        = "fire_smoke_detector"
    description = (
        "Detect smoke and LPG/CO gas using MQ-2. "
        "Send emergency alert and optionally trigger buzzer/alarm."
    )
    category    = "smart_home"
    requires    = ["sensor:MQ2"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.sensor_pin   = config.get("sensor_pin", 23)
        self.buzzer_id    = config.get("buzzer_id", "buzzer1")
        self.location     = config.get("location", "Kitchen")
        self.last_reading = {}
        self._actuator_mgr = kwargs.get("actuator_manager")

    def _read_sensor(self):
        if not is_pi():
            return {
                "smoke_detected": random.random() < 0.04,
                "gas_level":      random.randint(50, 900),
            }
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.sensor_pin, GPIO.IN)
            triggered = bool(GPIO.input(self.sensor_pin))
            return {"smoke_detected": triggered, "gas_level": None}
        except Exception as e:
            logger.warning(f"MQ-2 sensor error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_sensor()
        if not data:
            return
        self.last_reading = data

        if data.get("smoke_detected") and self.can_alert():
            summary = f"SMOKE / GAS detected at {self.location}!"
            ok, reason = self.should_alert(summary, context="Potential fire — emergency action required")
            if ok:
                if self._actuator_mgr:
                    buzzer = self._actuator_mgr.get(self.buzzer_id)
                    if buzzer:
                        buzzer.pulse(duration=5.0)
                if self.alert:
                    self.alert.send(f"🔥 FIRE/SMOKE: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
