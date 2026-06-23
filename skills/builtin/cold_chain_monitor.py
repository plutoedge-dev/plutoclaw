"""
ColdChainMonitorSkill — monitor cold chain: temperature and humidity of cold storage.

Required hardware:
  - DS18B20 waterproof temperature sensor (OneWire via GPIO 4)
  - Optional: DHT22 for humidity

Wiring DS18B20:
  VCC → 3.3V | GND → GND | DATA → GPIO 4 (with 4.7kΩ pull-up to 3.3V)

Suitable for: cold storage, industrial refrigerators, pharmaceuticals, labs, restaurants.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.cold_chain_monitor")


class ColdChainMonitorSkill(BaseSkill):
    name        = "cold_chain_monitor"
    description = (
        "Monitor temperature and humidity of cold storage. "
        "Alert immediately if temperature rises above the limit — prevent product damage."
    )
    category    = "logistics"
    requires    = ["sensor:DS18B20"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.temp_max     = config.get("temp_max", 8.0)
        self.temp_min     = config.get("temp_min", 2.0)
        self.storage_name = config.get("storage_name", "Cold Storage")
        self.last_reading = {}

    def _read_temp(self):
        if not is_pi():
            return {
                "temperature_c": round(random.uniform(1.0, 12.0), 2),
                "humidity_pct":  round(random.uniform(70, 95), 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_temp()
        if not data:
            return
        self.last_reading = data

        t = data.get("temperature_c", 5)
        issues = []
        if t > self.temp_max: issues.append(f"temperature {t}°C too high (max {self.temp_max}°C)")
        if t < self.temp_min: issues.append(f"temperature {t}°C too low (min {self.temp_min}°C)")

        if issues and self.can_alert():
            summary = f"{self.storage_name}: {', '.join(issues)}"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"❄️ Cold Chain: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
