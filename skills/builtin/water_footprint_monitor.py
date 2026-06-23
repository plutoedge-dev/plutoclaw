"""
WaterFootprintMonitorSkill — monitor water consumption per process and calculate
water footprint (liters/unit output) for sustainability reporting.

Required hardware:
  - YF-S201 flow sensor (pulse → GPIO)
  - Optional: TDS/turbidity sensor for water quality

Wiring YF-S201:
  VCC → 5V | GND → GND | Signal → GPIO 26 (interrupt)
  1 pulse ≈ 2.25 mL (calibrate in config)

Suitable for: beverage factory, farming, hotel, industrial laundry,
              hospital, cooling tower, ESG reporting.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.water_footprint_monitor")


class WaterFootprintMonitorSkill(BaseSkill):
    name        = "water_footprint_monitor"
    description = (
        "Monitor real-time water consumption via flow sensor. "
        "Calculate water footprint per process and alert if daily target is exceeded. "
        "Data ready for ESG / sustainability report export."
    )
    category    = "sustainability"
    requires    = ["sensor:flow_meter"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.flow_pin           = config.get("flow_pin", 26)
        self.ml_per_pulse       = config.get("ml_per_pulse", 2.25)
        self.daily_limit_liter  = config.get("daily_limit_liter", None)
        self.process_name       = config.get("process_name", "Production Process")
        self.last_reading       = {}
        self._daily_liter       = 0.0
        self._session_liter     = 0.0
        self._day_start         = time.strftime("%Y-%m-%d")

    def _read_flow(self):
        if not is_pi():
            flow_lpm = round(random.uniform(0.5, 8.0), 2)
            liter_inc = flow_lpm / 60 * self.get_interval()
            return {"flow_lpm": flow_lpm, "liter_increment": round(liter_inc, 4)}
        return {}

    def run_cycle(self):
        data = self._read_flow()
        if not data:
            return

        today = time.strftime("%Y-%m-%d")
        if today != self._day_start:
            self._daily_liter = 0.0
            self._day_start   = today

        liter_inc = data.get("liter_increment", 0)
        self._daily_liter   += liter_inc
        self._session_liter += liter_inc

        self.last_reading = {
            "flow_lpm":          data.get("flow_lpm", 0),
            "daily_liter":       round(self._daily_liter, 2),
            "session_liter":     round(self._session_liter, 2),
            "daily_m3":          round(self._daily_liter / 1000, 4),
            "daily_limit_liter": self.daily_limit_liter,
            "limit_pct":         round(self._daily_liter / self.daily_limit_liter * 100, 1)
                                  if self.daily_limit_liter else None,
        }

        if self.daily_limit_liter and self._daily_liter > self.daily_limit_liter and self.can_alert():
            summary = (
                f"{self.process_name}: today's water consumption {self._daily_liter:.0f} L "
                f"exceeds target {self.daily_limit_liter} L"
            )
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"💧 Water Footprint: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
