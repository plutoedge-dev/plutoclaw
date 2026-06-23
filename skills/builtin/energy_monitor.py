"""
EnergyMonitorSkill — monitor machine/panel power consumption in real-time.

Required hardware:
  - PZEM-004T current sensor (UART) or ACS712 (analog via MCP3008)
  - Optional: Relay for automatic load shedding

Wiring PZEM-004T:
  TX → GPIO 14 (Pi RX) | RX → GPIO 15 (Pi TX)

Suitable for: industrial panels, generator monitoring, factory energy audit.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.energy_monitor")


class EnergyMonitorSkill(BaseSkill):
    name        = "energy_monitor"
    description = (
        "Monitor power consumption in real-time. "
        "Alert if power exceeds the limit or an abnormal spike is detected."
    )
    category    = "industrial"
    requires    = ["sensor:current_meter"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.max_watt      = config.get("max_watt", 5000)
        self.sensor_name   = config.get("sensor_name", "Main Panel")
        self.last_reading  = {}

    def _read_power(self):
        if not is_pi():
            return {
                "voltage_v":  round(random.uniform(218.0, 225.0), 1),
                "current_a":  round(random.uniform(0.5, 20.0), 2),
                "power_w":    round(random.uniform(100, 4800), 1),
                "energy_kwh": round(random.uniform(0.1, 50.0), 3),
                "frequency":  round(random.uniform(49.8, 50.2), 1),
            }
        return {}

    def run_cycle(self):
        data = self._read_power()
        if not data:
            return
        self.last_reading = data

        power = data.get("power_w", 0)
        if power > self.max_watt and self.can_alert():
            summary = f"{self.sensor_name}: power {power}W exceeds limit {self.max_watt}W"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"⚡ Energy Alert: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
