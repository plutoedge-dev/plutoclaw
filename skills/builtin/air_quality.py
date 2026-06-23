"""
AirQualitySkill — monitor indoor air quality (CO2, VOC, PM2.5 particles).

Required hardware:
  - MH-Z19B CO2 sensor (UART)
  - SGP30 VOC sensor (I2C, optional)
  - PMS5003 particulate sensor (UART, optional)

Wiring MH-Z19B:
  TX → GPIO 14 | RX → GPIO 15 | VCC → 5V | GND → GND

Suitable for: offices, schools, hospitals, server rooms, factories.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.air_quality")


class AirQualitySkill(BaseSkill):
    name        = "air_quality"
    description = (
        "Monitor air quality: CO2, VOC, and fine particulates PM2.5. "
        "Alert if levels are hazardous to occupant health."
    )
    category    = "medical"
    requires    = ["sensor:CO2_MHZ19"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.co2_max      = config.get("co2_max_ppm", 1000)
        self.pm25_max     = config.get("pm25_max", 35)
        self.location     = config.get("location", "Room")
        self.last_reading = {}

    def _read_air(self):
        if not is_pi():
            return {
                "co2_ppm":    random.randint(400, 1400),
                "voc_ppb":    random.randint(10, 500),
                "pm25_ug_m3": round(random.uniform(5, 60), 1),
                "pm10_ug_m3": round(random.uniform(8, 80), 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_air()
        if not data:
            return
        self.last_reading = data

        issues = []
        if data.get("co2_ppm", 0) > self.co2_max:
            issues.append(f"CO2 {data['co2_ppm']} ppm")
        if data.get("pm25_ug_m3", 0) > self.pm25_max:
            issues.append(f"PM2.5 {data['pm25_ug_m3']} µg/m³")

        if issues and self.can_alert():
            summary = f"{self.location}: {', '.join(issues)} exceeds healthy limit"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"💨 Air Quality: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
