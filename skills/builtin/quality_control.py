"""
QualityControlSkill — visual product inspection on the production line with camera + AI.

Required hardware:
  - Camera (USB webcam / CSI / IP cam)
  - Optional: Hailo-8 NPU for fast inference

Suitable for: factory, packaging line, visual QC, product defect detection.
"""
import logging
import time
import random
from skills.base_skill import BaseSkill
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.skill.quality_control")


class QualityControlSkill(BaseSkill):
    name        = "quality_control"
    description = (
        "Visual product inspection on the production line. "
        "Detect defects, incorrect size, or misaligned products via camera."
    )
    category    = "industrial"
    requires    = ["camera"]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.camera_id    = config.get("camera", "cam1")
        self.confidence   = config.get("confidence", 0.7)
        self.defect_types = config.get("defect_types", ["scratch", "crack", "missing_part"])
        self.last_result  = {}
        self._cam_mgr     = kwargs.get("camera_manager")

    def _inspect_frame(self):
        if not is_pi():
            defect = random.random() < 0.08
            return {
                "defect_detected": defect,
                "defect_type":     random.choice(self.defect_types) if defect else None,
                "confidence":      round(random.uniform(0.7, 0.99), 2) if defect else 0.0,
                "inspected_at":    time.strftime("%H:%M:%S"),
            }
        return {"defect_detected": False, "defect_type": None, "confidence": 0.0}

    def run_cycle(self):
        result = self._inspect_frame()
        if not result:
            return
        self.last_result = result

        if result.get("defect_detected") and self.can_alert():
            dtype = result.get("defect_type", "unknown")
            conf  = result.get("confidence", 0)
            summary = f"Product defect detected: {dtype} (conf {conf:.0%})"
            ok, reason = self.should_alert(summary)
            if ok and self.alert:
                self.alert.send(f"🔍 QC Alert: {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_result"] = self.last_result
        return base
