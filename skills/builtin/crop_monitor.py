"""
CropMonitorSkill — monitor plant growing environment (temperature, humidity, light).

Required hardware:
  - DHT22 (temperature + air humidity)
  - LDR / BH1750 (light intensity, optional)
  - CO2 sensor MH-Z19 (optional)

Wiring DHT22:
  VCC → Pin 2 | DATA → GPIO 4 | GND → Pin 6

Suitable for: greenhouse, vertical farming, indoor plants, hydroponics.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.crop_monitor")


class CropMonitorSkill(BaseSkill):
    name        = "crop_monitor"
    description = (
        "Monitor temperature, humidity, and light intensity for optimal plant growth. "
        "Alert if conditions are outside the ideal range."
    )
    category    = "agriculture"
    requires    = ["sensor:DHT22"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.gpio_pin      = config.get("gpio_pin", 4)
        self.temp_min      = config.get("temp_min", 18.0)
        self.temp_max      = config.get("temp_max", 32.0)
        self.hum_min       = config.get("hum_min", 50.0)
        self.hum_max       = config.get("hum_max", 85.0)
        self.sensor_name   = config.get("sensor_name", "Greenhouse")
        self.last_reading  = {}

    def _read_dht(self):
        if not is_pi():
            return {
                "temperature_c": round(random.uniform(17.0, 35.0), 1),
                "humidity_pct":  round(random.uniform(45.0, 90.0), 1),
                "light_lux":     round(random.uniform(200, 50000), 0),
            }
        try:
            import adafruit_dht, board
            dht = adafruit_dht.DHT22(getattr(board, f"D{self.gpio_pin}"))
            return {
                "temperature_c": dht.temperature,
                "humidity_pct":  dht.humidity,
                "light_lux":     None,
            }
        except Exception as e:
            logger.warning(f"DHT read error: {e}")
            return {}

    def run_cycle(self):
        data = self._read_dht()
        if not data:
            return
        self.last_reading = data

        t = data.get("temperature_c", 0) or 0
        h = data.get("humidity_pct", 0) or 0
        issues = []
        if t < self.temp_min: issues.append(f"temperature too low ({t}°C)")
        if t > self.temp_max: issues.append(f"temperature too high ({t}°C)")
        if h < self.hum_min:  issues.append(f"humidity too low ({h}%)")
        if h > self.hum_max:  issues.append(f"humidity too high ({h}%)")

        if issues and self.can_alert():
            summary = f"{self.sensor_name}: {', '.join(issues)}"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🌿 Crop Monitor: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
