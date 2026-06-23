"""
BaseSkill — required interface for all PlutoClaw skills.

To create a new skill:
    from skills.base_skill import BaseSkill

    class MySkill(BaseSkill):
        name        = "my_skill"
        description = "What this skill does (for LLM context)"
        category    = "farming"           # farming | warehouse | home | custom
        requires    = ["sensor:DHT22"]    # required hardware
"""
import threading
import time
import logging
from abc import abstractmethod

logger = logging.getLogger("plutoclaw.skill")


class BaseSkill:
    name: str        = "base_skill"
    description: str = "Base skill — override in subclass"
    category: str    = "general"
    requires: list   = []

    def __init__(self, config: dict, llm=None, alert=None, storage=None, **kwargs):
        self.config  = config
        self.llm     = llm
        self.alert   = alert
        self.storage = storage

        self.running       = False
        self.status        = "idle"
        self.event_count   = 0
        self.alert_count   = 0
        self.last_alert_time = 0
        self.cooldown      = config.get("cooldown_seconds", 60)

        self._thread: threading.Thread | None = None
        logger.info(f"Skill '{self.name}' ready")

    # ── Cooldown ──────────────────────────────────────────────────────────────

    def can_alert(self) -> bool:
        return (time.time() - self.last_alert_time) > self.cooldown

    def mark_alerted(self):
        self.last_alert_time = time.time()
        self.alert_count += 1

    # ── LLM reasoning — filter false alarms before sending alert ────────────

    def should_alert(self, summary: str, context: str = "") -> tuple[bool, str]:
        """
        Ask the LLM whether this condition warrants an alert.
        Returns (True, reason) or (False, reason).
        If LLM is unavailable → default to sending the alert.
        """
        if not self.llm or not self.llm.available:
            return True, "LLM unavailable — alert sent directly"

        prompt = f"""You are the PlutoClaw AI system tasked with reducing false alarms.
Skill    : {self.name}
Condition: {summary}
Context  : {context or 'none'}

Does this condition TRULY warrant an alert to the owner?
Reply ONLY:
ALERT: Yes / No
REASON: <1 sentence>"""

        try:
            response = self.llm.generate(prompt, timeout=10)
            lines = response.strip().splitlines()
            alert_line  = next((l for l in lines if l.upper().startswith("ALERT:")), "")
            reason_line = next((l for l in lines if l.upper().startswith("REASON:")), "")
            alasan = reason_line.split(":", 1)[-1].strip()

            if "yes" in alert_line.lower():
                return True, alasan or "LLM: condition valid"
            elif "no" in alert_line.lower() or "not" in alert_line.lower():
                logger.info(f"[{self.name}] Alert suppressed: {alasan}")
                return False, alasan or "LLM: alert not needed"
            else:
                return True, "LLM: unclear response — alert sent"
        except Exception as e:
            logger.warning(f"[{self.name}] reasoning error: {e}")
            return True, f"reasoning error: {e}"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def run_cycle(self):
        """One work cycle — called repeatedly by _loop(). Implement sensing, decision, and action logic here."""
        pass

    def get_interval(self) -> float:
        """Interval between cycles (seconds). Override for custom interval."""
        return self.config.get("read_interval", self.config.get("interval_seconds", 5.0))

    def _loop(self):
        logger.info(f"▶ Skill '{self.name}' started")
        self.status = "running"
        while self.running:
            try:
                self.run_cycle()
                self.event_count += 1
            except Exception as e:
                logger.error(f"[{self.name}] Error in run_cycle: {e}")
            time.sleep(self.get_interval())
        self.status = "stopped"
        logger.info(f"⏹ Skill '{self.name}' stopped")

    def start(self):
        self.running = True
        self._thread = threading.Thread(
            target=self._loop, name=f"skill-{self.name}", daemon=True
        )
        self._thread.start()

    def stop(self):
        self.running = False

    # ── State untuk LLM context ───────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Return current skill state — used by context_builder.py to inject into the LLM prompt.
        Override in subclass to add skill-specific data.
        """
        return {
            "name":        self.name,
            "description": self.description,
            "category":    self.category,
            "status":      self.status,
            "events":      self.event_count,
            "alerts":      self.alert_count,
            "cooldown_remaining": max(0, round(self.cooldown - (time.time() - self.last_alert_time))),
        }
