"""
PPEGuardSkill — detect workers without PPE (hard hat, safety vest) via camera.

Required hardware:
  - Camera (webcam / USB cam / IP cam)
  - YOLOv8 model

Suitable for: warehouses, factories, construction sites.
"""
import logging
from skills.base_skill import BaseSkill
from core.detector import YOLODetector

logger = logging.getLogger("plutoclaw.skill.ppe_guard")


class PPEGuardSkill(BaseSkill):
    name        = "ppe_guard"
    description = "Detect workers without PPE (hard hat/vest) via camera. Alert on violations."
    category    = "warehouse"
    requires    = ["camera", "model:yolov8"]

    def __init__(self, config: dict, camera=None, detector=None, **kwargs):
        super().__init__(config, **kwargs)
        self.camera   = camera
        self.detector = detector

    def run_cycle(self):
        if not self.camera or not self.detector:
            return

        frame = self.camera.read_frame()
        if frame is None:
            return

        detections = self.detector.detect(frame)
        persons = YOLODetector.filter_class(detections, "person")
        helmets = YOLODetector.filter_class(detections, "helmet")
        vests   = YOLODetector.filter_class(detections, "vest")

        if not persons:
            return

        violation_count = max(
            max(0, len(persons) - len(helmets)),
            max(0, len(persons) - len(vests))
        )

        if violation_count > 0 and self.can_alert():
            summary = f"{violation_count} workers without PPE at {self.camera.name}"
            should, reason = self.should_alert(summary)
            if not should:
                return

            msg = (f"⚠️ *PPE VIOLATION* — {self.camera.name}\n"
                   f"{violation_count} workers missing full PPE.\n"
                   f"Hard hat: {len(helmets)}/{len(persons)} | Vest: {len(vests)}/{len(persons)}")

            snapshot = self.camera.save_snapshot(frame, label="ppe_violation",
                                                  media_path="media/snapshots")
            if self.alert:
                self.alert.send(msg, image_path=snapshot, agent=self.name)
            if self.storage:
                self.storage.log_event(
                    agent=self.name, event_type="ppe_violation",
                    camera_id=self.camera.camera_id,
                    count=violation_count, snapshot=snapshot, message=msg
                )
            self.mark_alerted()
            logger.warning(f"[ppe_guard] {violation_count} PPE violations")

    def get_interval(self) -> float:
        return self.config.get("frame_interval", 1.0)
