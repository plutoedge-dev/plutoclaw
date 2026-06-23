"""
CarbonFootprintMonitor — calculate real-time carbon emissions from electrical energy consumption.

Converts kWh data from an energy meter (PZEM-004T) to CO2e (kg)
using configurable regional grid emission factors.

Required hardware:
  - PZEM-004T current/power meter (UART)
  - Optional: relay for automatic load control

Reference emission factors (kgCO2e/kWh):
  Indonesia grid : 0.794
  Malaysia grid  : 0.585
  Singapore grid : 0.4085
  EU average     : 0.233
  Custom         : set in config

Suitable for: factories, commercial buildings, data centers, greenhouse, cold storage.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.carbon_footprint_monitor")

GRID_EMISSION_FACTORS = {
    "indonesia": 0.794,
    "malaysia":  0.585,
    "singapore": 0.4085,
    "eu":        0.233,
    "us":        0.386,
    "global":    0.475,
}


class CarbonFootprintMonitorSkill(BaseSkill):
    name        = "carbon_footprint_monitor"
    description = (
        "Calculate real-time carbon emissions from electrical energy consumption. "
        "Converts kWh → CO2e using regional grid emission factors. "
        "Alert if daily emissions exceed the configured target."
    )
    category    = "sustainability"
    requires    = ["sensor:current_meter"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        grid         = config.get("grid_region", "indonesia").lower()
        self.ef      = config.get("emission_factor", GRID_EMISSION_FACTORS.get(grid, 0.794))
        self.target_kg_day  = config.get("daily_co2_target_kg", None)
        self.location        = config.get("location", "Main Facility")
        self.last_reading    = {}
        self._daily_kwh      = 0.0
        self._day_start      = time.strftime("%Y-%m-%d")
        self._session_co2    = 0.0

    def _read_power(self):
        if not is_pi():
            power_w = round(random.uniform(500, 4500), 1)
            kwh_inc = power_w / 1000 * (self.get_interval() / 3600)
            return {
                "power_w":      power_w,
                "voltage_v":    round(random.uniform(218, 225), 1),
                "kwh_increment": round(kwh_inc, 6),
            }
        return {}

    def run_cycle(self):
        data = self._read_power()
        if not data:
            return

        today = time.strftime("%Y-%m-%d")
        if today != self._day_start:
            self._daily_kwh   = 0.0
            self._day_start   = today

        kwh_inc = data.get("kwh_increment", 0)
        self._daily_kwh   += kwh_inc
        self._session_co2 += kwh_inc * self.ef

        co2_today_kg = round(self._daily_kwh * self.ef, 3)

        self.last_reading = {
            "power_w":        data.get("power_w", 0),
            "voltage_v":      data.get("voltage_v", 0),
            "daily_kwh":      round(self._daily_kwh, 4),
            "co2_today_kg":   co2_today_kg,
            "co2_today_g":    round(co2_today_kg * 1000, 1),
            "session_co2_kg": round(self._session_co2, 4),
            "emission_factor": self.ef,
            "grid_region":    self.config.get("grid_region", "indonesia"),
        }

        if self.target_kg_day and co2_today_kg > self.target_kg_day and self.can_alert():
            summary = (
                f"{self.location}: today's emissions {co2_today_kg:.2f} kgCO₂e "
                f"exceed target {self.target_kg_day} kgCO₂e"
            )
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🌍 Carbon Alert: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
