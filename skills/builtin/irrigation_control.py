"""
IrrigationControlSkill — irrigation automation based on soil moisture & weather.

Required hardware:
  - Soil moisture sensor YL-69 / capacitive (DO → GPIO)
  - Relay for water pump (GPIO → relay module)
  - Optional: DHT22 for air temperature/humidity

Wiring:
  Soil DO → GPIO 17 | Pump relay → GPIO 18

Suitable for: paddy fields, gardens, greenhouse, hydroponics.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.irrigation_control")


class IrrigationControlSkill(BaseSkill):
    name        = "irrigation_control"
    description = (
        "Automate irrigation based on soil moisture. "
        "Automatically turn the water pump on/off and alert if soil is too dry."
    )
    category    = "agriculture"
    requires    = ["sensor:soil_moisture", "actuator:relay"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.soil_pin        = config.get("soil_pin", 17)
        self.pump_relay_id   = config.get("pump_relay_id", "relay2")
        self.dry_duration    = config.get("dry_duration_min", 30)  # minutes before alert
        self.last_reading    = {}
        self._dry_since      = None
        self._actuator_mgr   = kwargs.get("actuator_manager")

    def _read_soil(self):
        if not is_pi():
            soil_dry = random.random() < 0.35
            return {"soil_dry": soil_dry, "soil_raw": random.randint(200, 900)}
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.soil_pin, GPIO.IN)
            soil_dry = bool(GPIO.input(self.soil_pin))
            return {"soil_dry": soil_dry, "soil_raw": None}
        except Exception as e:
            logger.warning(f"Soil sensor error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_soil()
        if not data:
            return
        self.last_reading = data

        if data.get("soil_dry"):
            if self._dry_since is None:
                self._dry_since = time.time()
            dry_min = (time.time() - self._dry_since) / 60

            if dry_min >= self.dry_duration and self.can_alert():
                summary = f"Soil dry for {dry_min:.0f} minutes — irrigation required"
                ok, reason = self.should_alert(summary)
                if ok:
                    if self._actuator_mgr:
                        pump = self._actuator_mgr.get(self.pump_relay_id)
                        if pump:
                            pump.turn_on()
                            logger.info("Irrigation pump turned on automatically")
                    if self.alert:
                        self.alert.send(f"🌱 Irrigation: {summary}", agent=self.name)
                    self.mark_alerted()
        else:
            self._dry_since = None
            if self._actuator_mgr:
                pump = self._actuator_mgr.get(self.pump_relay_id)
                if pump and pump.state:
                    pump.turn_off()
                    logger.info("Irrigation pump turned off — soil sufficiently moist")

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        base["dry_since"]    = self._dry_since
        return base
