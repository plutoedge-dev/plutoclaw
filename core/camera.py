"""
Camera manager - handles USB webcam and RTSP IP camera
"""
import cv2
import threading
import time
import os
import logging
from datetime import datetime

logger = logging.getLogger("plutoclaw.camera")


class CameraStream:
    """
    Reads frames from camera continuously in a background thread.
    Supports: USB webcam (index 0,1,2), RTSP URL, video file (for testing)
    """

    def __init__(self, camera_id: str, source, name: str = "Camera"):
        self.camera_id = camera_id
        self.source = source
        self.name = name
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self.error = None

    def connect(self) -> bool:
        """Open connection to camera"""
        try:
            # Convert source: "0" -> 0 (integer for webcam)
            src = int(self.source) if str(self.source).isdigit() else self.source
            self.cap = cv2.VideoCapture(src)

            if not self.cap.isOpened():
                self.error = f"Cannot open camera: {self.source}"
                logger.error(self.error)
                return False

            # Set resolution based on platform & source type
            # USB camera (index 0-9) on Pi 4: max 640x480 to avoid dropped frames
            # CSI camera & RTSP: support 720p
            import platform as _platform
            _is_pi = _platform.system() == "Linux" and (
                "aarch64" in _platform.machine() or "armv" in _platform.machine()
            )
            _is_usb = isinstance(self.source, int) or (
                str(self.source).isdigit() and int(self.source) < 10
            )
            if _is_pi and _is_usb:
                width, height = 640, 480    # USB camera on Pi 4 — stable & CPU-efficient
            else:
                width, height = 1280, 720   # CSI / RTSP / Mac webcam — 720p ok
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            logger.info(f"Camera '{self.camera_id}' resolution: {width}x{height}")

            self.connected = True
            logger.info(f"✅ Camera '{self.name}' ({self.camera_id}) connected")
            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Error connecting camera {self.camera_id}: {e}")
            return False

    def _read_loop(self):
        """Background thread - continuously reads frames"""
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.frame = frame
                    self.connected = True
                else:
                    self.connected = False
                    logger.warning(f"Camera {self.camera_id} failed to read frame, reconnecting...")
                    time.sleep(2)
                    self.cap.release()
                    self.connect()
            time.sleep(0.03)  # ~30fps max

    def start(self):
        """Start background thread"""
        if not self.connected:
            if not self.connect():
                return False
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop camera"""
        self.running = False
        if self.cap:
            self.cap.release()

    def read_frame(self):
        """Get the latest frame (non-blocking)"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def save_snapshot(self, frame, label: str = "", media_path: str = "media/snapshots") -> str:
        """Save snapshot to disk, return file path"""
        os.makedirs(media_path, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.camera_id}_{label}_{ts}.jpg"
        filepath = os.path.join(media_path, filename)
        cv2.imwrite(filepath, frame)
        return filepath

    def get_jpeg_bytes(self):
        """Return frame as JPEG bytes (for dashboard streaming)"""
        frame = self.read_frame()
        if frame is None:
            return None
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes()

    @property
    def status(self) -> dict:
        return {
            "id": self.camera_id,
            "name": self.name,
            "source": str(self.source),
            "connected": self.connected,
            "error": self.error
        }


class CameraManager:
    """Manages multiple cameras simultaneously"""

    def __init__(self, cameras_config: list, media_path: str = "media"):
        self.cameras: dict[str, CameraStream] = {}
        self.media_path = media_path

        for cam_cfg in cameras_config:
            cam = CameraStream(
                camera_id=cam_cfg["id"],
                source=cam_cfg["source"],
                name=cam_cfg.get("name", cam_cfg["id"])
            )
            self.cameras[cam_cfg["id"]] = cam

    def start_all(self):
        """Start all cameras"""
        started = []
        for cam_id, cam in self.cameras.items():
            if cam.start():
                started.append(cam_id)
            else:
                logger.warning(f"Camera {cam_id} failed to start")
        return started

    def stop_all(self):
        for cam in self.cameras.values():
            cam.stop()

    def get(self, camera_id: str) -> CameraStream:
        return self.cameras.get(camera_id)

    def get_all_status(self) -> list:
        return [cam.status for cam in self.cameras.values()]
