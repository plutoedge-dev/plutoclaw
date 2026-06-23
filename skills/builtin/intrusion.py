"""
IntrusionSkill — detect people outside operational hours via camera.

Required hardware:
  - Camera (webcam / USB cam / IP cam)
  - YOLOv8 model

Config:
  active_hours: "20:00-06:00"   # monitoring active hours (can be overnight)

Suitable for: warehouses, factories, restricted areas.
"""
import logging
from datetime import datetime, time as dtime
from skills.base_skill import BaseSkill
from core.detector import YOLODetector

logger = logging.getLogger("plutoclaw.skill.intrusion")


class IntrusionSkill(BaseSkill):
    name        = "intrusion"
    description = "Detect people in restricted areas outside operational hours. Immediate WhatsApp alert."
    category    = "warehouse"
    requires    = ["camera", "model:yolov8"]

    def __init__(self, config: dict, camera=None, detector=None, **kwargs):
        super().__init__(config, **kwargs)
        self.camera       = camera
        self.detector     = detector
        self.active_hours = config.get("active_hours", "00:00-23:59")

    def _is_active_hours(self) -> bool:
        try:
            start_str, end_str = self.active_hours.split("-")
            now   = datetime.now().time()
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start, end = dtime(sh, sm), dtime(eh, em)
            if start > end:   # overnight range, e.g. 20:00-06:00
                return now >= start or now <= end
            return start <= now <= end
        except Exception:
            return True

    def run_cycle(self):
        if not self._is_active_hours() or not self.camera or not self.detector:
            return

        frame = self.camera.read_frame()
        if frame is None:
            return

        detections = self.detector.detect(frame)
        persons    = YOLODetector.filter_class(detections, "person")

        if not persons or not self.can_alert():
            return

        summary = f"{len(persons)} person(s) detected at {self.camera.name}"
        should, _ = self.should_alert(summary)
        if not should:
            return

        msg = (f"🚨 *INTRUSION* — {self.camera.name}\n"
               f"{len(persons)} person(s) detected in restricted area.\n"
               f"Time: {datetime.now().strftime('%H:%M:%S')}")

        snapshot = self.camera.save_snapshot(frame, label="intrusion",
                                              media_path="media/snapshots")
        if self.alert:
            self.alert.send(msg, image_path=snapshot, agent=self.name)
        if self.storage:
            self.storage.log_event(
                agent=self.name, event_type="intrusion",
                camera_id=self.camera.camera_id,
                count=len(persons), snapshot=snapshot, message=msg
            )
        self.mark_alerted()
        logger.warning(f"[intrusion] {len(persons)} person(s) at '{self.camera.name}'")

    def get_interval(self) -> float:
        return self.config.get("frame_interval", 1.0)
