"""
CoopMonitorSkill — monitor temperature, air humidity, and soil moisture.

Required hardware:
  - DHT22 sensor (temperature + air humidity)
  - Soil Moisture Module YL-69/FC-28 (optional)

Wiring DHT22:
  VCC  → Pin 2 (5V) | DATA → GPIO 4 | GND → Pin 6

Wiring Soil Moisture:
  VCC → Pin 4 (5V) | GND → Pin 9 | DO → GPIO 17
  DO HIGH = dry soil, DO LOW = sufficiently moist

Suitable for: coops, greenhouse, gardens, potted plants.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.coop_monitor")


class CoopMonitorSkill(BaseSkill):
    name        = "coop_monitor"
    description = "Monitor temperature, air humidity, and soil moisture. Alert if thresholds are exceeded."
    category    = "farming"
    requires    = ["sensor:DHT22"]

    def __init__(self, config: dict, **kwargs):
        super().__init__(config, **kwargs)

        self.dht_pin      = config.get("gpio_pin", 4)
        self.soil_pin     = config.get("soil_pin", 17)
        self.soil_enabled = config.get("soil_enabled", False)
        self.sensor_name  = config.get("sensor_name", "Location")

        self.temp_max = config.get("temp_max", 32.0)
        self.temp_min = config.get("temp_min", 18.0)
        self.hum_max  = config.get("hum_max",  85.0)
        self.hum_min  = config.get("hum_min",  40.0)

        self._dht  = None
        self._gpio = None
        self._last_reading: dict = {}

        if is_pi():
            self._init_hardware()
        else:
            logger.info("[coop_monitor] Simulation mode — dummy data")

    def _init_hardware(self):
        try:
            import adafruit_dht, board
            pin_map = {4: board.D4, 17: board.D17, 22: board.D22, 27: board.D27}
            self._dht = adafruit_dht.DHT22(
                pin_map.get(self.dht_pin, board.D4), use_pulseio=False
            )
            logger.info(f"DHT22 ready on GPIO {self.dht_pin}")
        except Exception as e:
            logger.error(f"Failed to init DHT22: {e}")

        if self.soil_enabled:
            try:
                import RPi.GPIO as GPIO
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.soil_pin, GPIO.IN)
                self._gpio = GPIO
                logger.info(f"Soil moisture ready on GPIO {self.soil_pin}")
            except Exception as e:
                logger.error(f"Failed to init soil sensor: {e}")

    def _read(self) -> dict:
        if not is_pi() or self._dht is None:
            r = {
                "status":      "simulated",
                "temperature": round(27.0 + random.uniform(-2, 6), 1),
                "humidity":    round(62.0 + random.uniform(-10, 20), 1),
            }
            if self.soil_enabled:
                r["soil_dry"] = random.random() > 0.6
            return r

        try:
            temp = self._dht.temperature
            hum  = self._dht.humidity
            if temp is None or hum is None:
                return {"status": "retry"}

            r = {"status": "ok", "temperature": round(temp, 1), "humidity": round(hum, 1)}
            if self.soil_enabled and self._gpio:
                r["soil_dry"] = bool(self._gpio.input(self.soil_pin))
            return r
        except RuntimeError:
            return {"status": "retry"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run_cycle(self):
        reading = self._read()
        if reading["status"] not in ("ok", "simulated"):
            return

        self._last_reading = reading
        temp     = reading["temperature"]
        hum      = reading["humidity"]
        soil_dry = reading.get("soil_dry")

        soil_info = " | Soil: DRY ⚠️" if soil_dry else (
                    " | Soil: OK ✅" if soil_dry is not None else "")
        logger.info(f"[{self.sensor_name}] {temp}°C | {hum}%{soil_info}")

        if not self.can_alert():
            return

        msg = None
        if soil_dry:
            msg = (f"🌱 *DRY SOIL* — {self.sensor_name}\n"
                   f"Plants need watering.\n"
                   f"Temp: {temp}°C | Air humidity: {hum}%")
        elif temp > self.temp_max:
            msg = (f"🌡️ *HIGH TEMPERATURE* — {self.sensor_name}\n"
                   f"Temp: *{temp}°C* (limit: {self.temp_max}°C) | Hum: {hum}%\n"
                   f"Check ventilation.")
        elif temp < self.temp_min:
            msg = (f"❄️ *LOW TEMPERATURE* — {self.sensor_name}\n"
                   f"Temp: *{temp}°C* (min limit: {self.temp_min}°C)")
        elif hum > self.hum_max:
            msg = (f"💧 *HIGH HUMIDITY* — {self.sensor_name}\n"
                   f"Humidity: *{hum}%* (limit: {self.hum_max}%) — mold risk.")

        if msg and self.alert:
            self.alert.send(msg, agent=self.name)
            self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["sensor_name"]  = self.sensor_name
        base["last_reading"] = self._last_reading
        return base
