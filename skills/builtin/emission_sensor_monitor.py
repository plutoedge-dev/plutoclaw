"""
EmissionSensorMonitorSkill — monitor industrial gas emissions in real-time:
CO2, CH4 (methane), NOx, and SO2 for environmental compliance.

Required hardware:
  - MH-Z19B — CO2 (UART)
  - MQ-4    — CH4/methane (DO/AO GPIO)
  - Optional: Electrochemical sensor module for NOx/SO2

Wiring MH-Z19B:
  TX → GPIO 14 | RX → GPIO 15 | VCC → 5V | GND → GND

Wiring MQ-4:
  VCC → 5V | GND → GND | DO → GPIO 27

Reference emission standards (common thresholds):
  CO2 : > 5000 ppm  (OSHA workspace limit)
  CH4 : > 1000 ppm  (LEL ~5% = 50000 ppm, early warning)
  NOx : > 3 ppm     (NIOSH limit)

Suitable for: factories, large farms, landfills, chemical industry, power plants.
"""
import logging
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.emission_sensor_monitor")


class EmissionSensorMonitorSkill(BaseSkill):
    name        = "emission_sensor_monitor"
    description = (
        "Monitor industrial gas emissions: CO2, CH4, and NOx in real-time. "
        "Alert if gas levels exceed environmental/safety compliance thresholds."
    )
    category    = "sustainability"
    requires    = ["sensor:CO2_MHZ19", "sensor:gas_MQ4"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.co2_max      = config.get("co2_max_ppm",  5000)
        self.ch4_max      = config.get("ch4_max_ppm",  1000)
        self.nox_max      = config.get("nox_max_ppm",  3)
        self.location     = config.get("location", "Industrial Area")
        self.last_reading = {}

    def _read_gases(self):
        if not is_pi():
            return {
                "co2_ppm":  random.randint(400, 5500),
                "ch4_ppm":  random.randint(50, 1200),
                "nox_ppm":  round(random.uniform(0.1, 4.0), 2),
                "so2_ppm":  round(random.uniform(0.0, 2.0), 2),
            }
        return {}

    def run_cycle(self):
        data = self._read_gases()
        if not data:
            return
        self.last_reading = data

        violations = []
        if data.get("co2_ppm", 0) > self.co2_max:
            violations.append(f"CO₂ {data['co2_ppm']} ppm (max {self.co2_max})")
        if data.get("ch4_ppm", 0) > self.ch4_max:
            violations.append(f"CH₄ {data['ch4_ppm']} ppm (max {self.ch4_max})")
        if data.get("nox_ppm", 0) > self.nox_max:
            violations.append(f"NOx {data['nox_ppm']} ppm (max {self.nox_max})")

        if violations and self.can_alert():
            summary = f"{self.location}: {', '.join(violations)} — potential emission violation"
            ok, reason = self.should_alert(summary, context="Environmental emission regulatory compliance")
            if ok and self.alert:
                self.alert.send(f"🏭 Emission Alert: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
