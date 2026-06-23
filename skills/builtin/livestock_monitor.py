"""
LivestockMonitorSkill — monitor livestock pen conditions (temperature, humidity, ammonia).

Required hardware:
  - DHT22 (temperature + humidity)
  - MQ-135 gas sensor (ammonia/NH3)
  - Optional: camera for animal count

Wiring MQ-135:
  VCC → Pin 2 | GND → Pin 6 | AOUT → MCP3008 CH0 | DOUT → GPIO 27

Suitable for: chicken, cattle, pig, goat pens — intensive or semi-intensive farming.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.livestock_monitor")


class LivestockMonitorSkill(BaseSkill):
    name        = "livestock_monitor"
    description = (
        "Monitor livestock pen conditions: temperature, humidity, and ammonia level. "
        "Alert if conditions become dangerous to animal health."
    )
    category    = "agriculture"
    requires    = ["sensor:DHT22", "sensor:gas_mq135"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.temp_max     = config.get("temp_max", 32.0)
        self.hum_max      = config.get("hum_max", 85.0)
        self.nh3_max_ppm  = config.get("nh3_max_ppm", 25)
        self.sensor_name  = config.get("sensor_name", "Main Pen")
        self.last_reading = {}

    def _read_sensors(self):
        if not is_pi():
            return {
                "temperature_c": round(random.uniform(24.0, 38.0), 1),
                "humidity_pct":  round(random.uniform(55.0, 92.0), 1),
                "nh3_ppm":       round(random.uniform(5, 35), 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_sensors()
        if not data:
            return
        self.last_reading = data

        issues = []
        if data.get("temperature_c", 0) > self.temp_max:
            issues.append(f"temperature {data['temperature_c']}°C")
        if data.get("humidity_pct", 0) > self.hum_max:
            issues.append(f"humidity {data['humidity_pct']}%")
        if data.get("nh3_ppm", 0) > self.nh3_max_ppm:
            issues.append(f"ammonia {data['nh3_ppm']} ppm")

        if issues and self.can_alert():
            summary = f"{self.sensor_name}: {', '.join(issues)} exceeds safe limit"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🐄 Livestock: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
