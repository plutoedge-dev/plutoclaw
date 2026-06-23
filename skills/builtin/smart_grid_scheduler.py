"""
SmartGridSchedulerSkill — automatic demand response: shift large loads to
low-carbon / cheap-tariff grid hours to reduce carbon intensity & electricity bills.

Strategy:
  1. Read current time → check if inside a "green window" (low-carbon grid)
  2. During green window  → activate deferrable loads (pump, chiller, battery charger)
  3. Outside green window → deactivate non-essential loads, conserve energy
  4. Alert if peak consumption is too high

Required hardware:
  - PZEM-004T power meter (consumption monitoring)
  - Relay module (load control)

Default green windows for Indonesia PLN (off-peak low-emission):
  22:00 – 06:00 (night) — low WBP tariff, grid more hydro/geothermal
  10:00 – 14:00 (day)   — regional solar peak

Suitable for: factories, cold storage, data centers, commercial buildings with ESG targets.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.smart_grid_scheduler")


def _in_window(windows: list[tuple]) -> bool:
    now_h = int(time.strftime("%H"))
    now_m = int(time.strftime("%M"))
    now_min = now_h * 60 + now_m
    for (sh, sm, eh, em) in windows:
        start = sh * 60 + sm
        end   = eh * 60 + em
        if start <= end:
            if start <= now_min < end:
                return True
        else:
            if now_min >= start or now_min < end:
                return True
    return False


class SmartGridSchedulerSkill(BaseSkill):
    name        = "smart_grid_scheduler"
    description = (
        "Automatic demand response: shift large loads to low-carbon / cheap-tariff grid hours. "
        "Reduce carbon intensity and electricity bills simultaneously."
    )
    category    = "sustainability"
    requires    = ["sensor:current_meter", "actuator:relay"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        raw_windows = config.get("green_windows", [
            ["22:00", "06:00"],
            ["10:00", "14:00"],
        ])
        self.green_windows = []
        for w in raw_windows:
            sh, sm = map(int, w[0].split(":"))
            eh, em = map(int, w[1].split(":"))
            self.green_windows.append((sh, sm, eh, em))

        self.deferrable_relays = config.get("deferrable_relay_ids", ["relay1"])
        self.peak_watt_limit   = config.get("peak_watt_limit", 5000)
        self.location          = config.get("location", "Facility")
        self.last_reading      = {}
        self._actuator_mgr     = kwargs.get("actuator_manager")
        self._last_window      = None

    def _read_power(self):
        if not is_pi():
            return {"power_w": round(random.uniform(800, 5500), 1)}
        return {}

    def run_cycle(self):
        data = self._read_power()
        if not data:
            return

        in_green = _in_window(self.green_windows)
        power_w  = data.get("power_w", 0)
        now_str  = time.strftime("%H:%M")

        self.last_reading = {
            "power_w":     power_w,
            "in_green_window": in_green,
            "current_time": now_str,
            "green_windows": [f"{w[0]:02d}:{w[1]:02d}–{w[2]:02d}:{w[3]:02d}" for w in self.green_windows],
        }

        if self._actuator_mgr and in_green != self._last_window:
            for rid in self.deferrable_relays:
                relay = self._actuator_mgr.get(rid)
                if relay:
                    if in_green:
                        relay.turn_on()
                        logger.info(f"[{now_str}] Green window → load '{rid}' activated")
                    else:
                        relay.turn_off()
                        logger.info(f"[{now_str}] Outside green window → load '{rid}' deactivated")
            self._last_window = in_green

        if power_w > self.peak_watt_limit and self.can_alert():
            summary = (
                f"{self.location}: peak consumption {power_w:.0f}W exceeds limit "
                f"{self.peak_watt_limit}W — shift loads to green window"
            )
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"⚡ Grid Scheduler: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
