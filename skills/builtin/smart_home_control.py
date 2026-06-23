"""
SmartHomeControlSkill — smart home automation based on context: schedule, sensors, and habits.

Required hardware:
  - PIR motion sensor (presence detection)
  - Relay module (control lights, fans, AC)
  - Optional: DHT22 for room temperature

Wiring PIR:
  VCC → Pin 2 | GND → Pin 6 | OUT → GPIO 24

Suitable for: homes, boarding houses, apartments, small offices.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.smart_home_control")


class SmartHomeControlSkill(BaseSkill):
    name        = "smart_home_control"
    description = (
        "Smart home automation: control lights and AC based on presence, schedule, and temperature. "
        "Pluto can be commanded via chat to control actuators."
    )
    category    = "smart_home"
    requires    = ["sensor:PIR", "actuator:relay"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.pir_pin         = config.get("pir_pin", 24)
        self.light_relay_id  = config.get("light_relay_id", "relay1")
        self.auto_off_min    = config.get("auto_off_minutes", 10)
        self.last_motion_at  = None
        self.last_reading    = {}
        self._actuator_mgr   = kwargs.get("actuator_manager")

    def _read_pir(self):
        if not is_pi():
            return {"motion": random.random() < 0.3}
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pir_pin, GPIO.IN)
            return {"motion": bool(GPIO.input(self.pir_pin))}
        except Exception as e:
            logger.warning(f"PIR error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_pir()
        if not data:
            return
        self.last_reading = data

        relay = self._actuator_mgr.get(self.light_relay_id) if self._actuator_mgr else None

        if data.get("motion"):
            self.last_motion_at = time.time()
            if relay and not relay.state:
                relay.turn_on()
                logger.info("Light turned on — motion detected")
        elif self.last_motion_at:
            idle_min = (time.time() - self.last_motion_at) / 60
            if idle_min >= self.auto_off_min and relay and relay.state:
                relay.turn_off()
                logger.info(f"Light turned off — no motion for {idle_min:.0f} minutes")
                self.last_motion_at = None

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"]   = self.last_reading
        base["last_motion_at"] = self.last_motion_at
        return base
