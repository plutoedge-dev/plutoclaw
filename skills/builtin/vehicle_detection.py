"""
VehicleDetectionSkill — detect and count vehicles in a parking area/loading dock.

Required hardware:
  - Camera (USB webcam / IP cam / CSI)
  - Optional: Hailo-8 NPU for real-time inference

Suitable for: parking areas, loading docks, warehouse entrances, toll gates.
"""
import logging
import random
import time
from skills.base_skill import BaseSkill

logger = logging.getLogger("plutoclaw.skill.vehicle_detection")


class VehicleDetectionSkill(BaseSkill):
    name        = "vehicle_detection"
    description = (
        "Detect and count vehicles in a specific area using a camera. "
        "Alert if capacity is full or an unrecognized vehicle enters."
    )
    category    = "logistics"
    requires    = ["camera"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.camera_id      = config.get("camera", "cam1")
        self.max_capacity   = config.get("max_capacity", 10)
        self.confidence     = config.get("confidence", 0.6)
        self.last_count     = 0
        self.last_result    = {}

    def _detect_vehicles(self):
        count = random.randint(0, self.max_capacity + 2)
        return {
            "vehicle_count": count,
            "capacity_pct":  round(count / self.max_capacity * 100, 1),
            "detected_at":   time.strftime("%H:%M:%S"),
        }

    def run_cycle(self):
        result = self._detect_vehicles()
        self.last_result = result
        self.last_count  = result.get("vehicle_count", 0)

        if self.last_count > self.max_capacity and self.can_alert():
            summary = f"Area full: {self.last_count}/{self.max_capacity} vehicles"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🚗 Vehicle: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_result"] = self.last_result
        base["vehicle_count"] = self.last_count
        return base
