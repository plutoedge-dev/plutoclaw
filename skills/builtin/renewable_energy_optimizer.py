"""
RenewableEnergyOptimizerSkill — monitor solar/wind production and optimize
power consumption to maximize renewable energy self-consumption.

Required hardware:
  - INA219 / PZEM-017 DC meter (solar panel output)
  - PZEM-004T AC meter (grid consumption)
  - Relay for load switching (optional)

Wiring INA219:
  SDA → GPIO 2 | SCL → GPIO 3 | VCC → 3.3V | GND → GND

Strategy:
  - When solar surplus → activate secondary loads (pump, heater, battery charger)
  - When solar deficit + expensive grid → shut off non-essential loads
  - Log daily self-consumption ratio

Suitable for: solar homes, greenhouse, factories with solar panels, off-grid systems.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.renewable_energy_optimizer")


class RenewableEnergyOptimizerSkill(BaseSkill):
    name        = "renewable_energy_optimizer"
    description = (
        "Monitor solar/wind production and grid consumption in real-time. "
        "Automatically shift loads to green energy windows to maximize self-consumption "
        "and reduce electricity bills & carbon."
    )
    category    = "sustainability"
    requires    = ["sensor:dc_meter", "sensor:ac_meter"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.surplus_relay_id  = config.get("surplus_relay_id", "relay1")
        self.surplus_threshold = config.get("surplus_watt", 200)
        self.location          = config.get("location", "Solar System")
        self.last_reading      = {}
        self._total_solar_kwh  = 0.0
        self._total_grid_kwh   = 0.0
        self._actuator_mgr     = kwargs.get("actuator_manager")

    def _read_energy(self):
        if not is_pi():
            solar_w = round(random.uniform(0, 1500), 1)
            grid_w  = round(random.uniform(0, 2000), 1)
            load_w  = solar_w + grid_w
            return {
                "solar_w":      solar_w,
                "grid_w":       grid_w,
                "load_w":       round(load_w, 1),
                "surplus_w":    round(max(0, solar_w - load_w * 0.6), 1),
                "solar_pct":    round(solar_w / max(load_w, 1) * 100, 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_energy()
        if not data:
            return

        interval_h = self.get_interval() / 3600
        self._total_solar_kwh += data.get("solar_w", 0) / 1000 * interval_h
        self._total_grid_kwh  += data.get("grid_w", 0) / 1000 * interval_h

        total_kwh = self._total_solar_kwh + self._total_grid_kwh
        scr = round(self._total_solar_kwh / max(total_kwh, 0.001) * 100, 1)

        self.last_reading = {
            **data,
            "self_consumption_ratio_pct": scr,
            "session_solar_kwh": round(self._total_solar_kwh, 4),
            "session_grid_kwh":  round(self._total_grid_kwh, 4),
        }

        surplus = data.get("surplus_w", 0)
        if self._actuator_mgr:
            relay = self._actuator_mgr.get(self.surplus_relay_id)
            if relay:
                if surplus > self.surplus_threshold and not relay.state:
                    relay.turn_on()
                    logger.info(f"Solar surplus {surplus}W — secondary load activated")
                elif surplus < self.surplus_threshold * 0.5 and relay.state:
                    relay.turn_off()
                    logger.info("Solar surplus exhausted — secondary load deactivated")

        if scr < 30 and self.can_alert():
            summary = (
                f"{self.location}: self-consumption ratio low ({scr}%) — "
                f"most energy coming from grid"
            )
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"☀️ Renewable: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
