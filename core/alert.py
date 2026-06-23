"""
Alert manager - send notifications via WA bridge + logging
"""
import requests
import logging
import os
from datetime import datetime
from core.storage import Storage

logger = logging.getLogger("plutoclaw.alert")

WA_BRIDGE_URL = "http://localhost:3001"


class AlertManager:
    def __init__(self, config: dict, storage: Storage):
        self.config = config
        self.storage = storage
        self.wa_enabled = config.get("whatsapp", {}).get("enabled", False)
        self.alert_numbers = config.get("whatsapp", {}).get("alert_numbers", [])
        self.wa_available = False

    def check_wa_bridge(self) -> bool:
        """Check whether WA bridge (Node.js) is running"""
        try:
            r = requests.get(f"{WA_BRIDGE_URL}/status", timeout=2)
            self.wa_available = r.json().get("connected", False)
            if self.wa_available:
                logger.info("✅ WA Bridge connected")
            else:
                logger.warning("⚠️ WA Bridge running but WA not logged in")
            return self.wa_available
        except Exception:
            logger.warning("⚠️ WA Bridge unavailable - alerts via log only")
            self.wa_available = False
            return False

    def send(self, message: str, image_path: str = None,
             numbers: list = None, agent: str = "system"):
        """
        Send alert to WhatsApp
        Fallback: print to console + log to file if WA is unavailable
        """
        targets = numbers or self.alert_numbers

        # Always log to console
        logger.info(f"[ALERT] {message}")

        # Always log to storage
        for number in targets:
            self.storage.log_alert(
                channel="whatsapp",
                recipient=number,
                message=message,
                status="sent" if self.wa_available else "logged_only"
            )

        # Send via WA if available
        if self.wa_enabled and self.wa_available and targets:
            for number in targets:
                try:
                    payload = {"number": number, "message": message}
                    if image_path and os.path.exists(image_path):
                        payload["image_path"] = os.path.abspath(image_path)

                    r = requests.post(
                        f"{WA_BRIDGE_URL}/send",
                        json=payload,
                        timeout=10
                    )
                    if r.status_code == 200:
                        logger.debug(f"WA sent to {number}")
                    else:
                        logger.warning(f"WA failed for {number}: {r.text}")
                except Exception as e:
                    logger.error(f"Error sending WA to {number}: {e}")
        else:
            # Fallback: write to alert log file
            self._write_alert_log(message, image_path)

    def _write_alert_log(self, message: str, image_path: str = None):
        """Fallback: write alert to text file (for Mac development)"""
        os.makedirs("data", exist_ok=True)
        with open("data/alert.log", "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {message}"
            if image_path:
                line += f" | snapshot: {image_path}"
            f.write(line + "\n")
