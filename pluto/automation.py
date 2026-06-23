"""
automation.py — Pluto automation mode.

Pluto proactively monitors system conditions (sensor, skill state)
and makes decisions / takes actions without requiring user commands.

Loop runs in a background thread; interval is configurable.
"""
import threading
import time
import logging
from pluto.context_builder import build_system_prompt
from pluto.action_parser   import parse_action

logger = logging.getLogger("plutoclaw.automation")

AUTOMATION_PROMPT = """You are in AUTOMATION mode — no user input.

Review the system conditions above. If any condition requires action
(sensor exceeded threshold, skill issue, actuator needs adjustment),
take action by including a JSON action.

If all conditions are normal, reply only with: OK

Do not provide long explanations if conditions are normal."""


class AutomationHandler:
    def __init__(self, llm, skills: dict, actuator_manager=None,
                 alert=None, config: dict = None,
                 interval_seconds: int = 60):
        self.llm              = llm
        self.skills           = skills
        self.actuator_manager = actuator_manager
        self.alert            = alert
        self.config           = config or {}
        self.interval         = interval_seconds

        self.running  = False
        self._thread: threading.Thread | None = None
        self.last_check: str = "-"
        self.last_action: dict | None = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(
            target=self._loop, name="pluto-automation", daemon=True
        )
        self._thread.start()
        logger.info(f"Pluto automation mode ON (interval: {self.interval}s)")

    def stop(self):
        self.running = False
        logger.info("Pluto automation mode OFF")

    def _loop(self):
        while self.running:
            try:
                self._check()
            except Exception as e:
                logger.error(f"Automation check error: {e}")
            time.sleep(self.interval)

    def _check(self):
        if not self.llm or not self.llm.available:
            return

        system_prompt = build_system_prompt(
            self.skills, self.actuator_manager, self.config
        )
        full_prompt = f"{system_prompt}\n\n{AUTOMATION_PROMPT}\nPluto:"

        response = self.llm.generate(full_prompt, timeout=30)
        if not response or response.strip().upper() == "OK":
            logger.debug("Automation check: all normal")
            return

        action = parse_action(response)
        if action:
            logger.info(f"Automation action: {action}")
            self.last_action = action
            self._execute(action)

        from datetime import datetime
        self.last_check = datetime.now().strftime("%H:%M:%S")

    def _execute(self, action: dict):
        a = action.get("action")
        try:
            if a == "start_skill":
                s = self.skills.get(action["skill"])
                if s: s.start()

            elif a == "stop_skill":
                s = self.skills.get(action["skill"])
                if s: s.stop()

            elif a == "actuator" and self.actuator_manager:
                act = self.actuator_manager.get(action["id"])
                if act:
                    cmd = action["cmd"]
                    if cmd == "on":     act.turn_on()
                    elif cmd == "off":  act.turn_off()
                    elif cmd == "toggle": act.toggle()
                    elif cmd == "pulse":  act.pulse(action.get("duration", 3.0))

            elif a == "send_alert" and self.alert:
                self.alert.send(action["message"], agent="pluto-auto")

        except Exception as e:
            logger.error(f"Automation execute error: {e}")

    @property
    def status(self) -> dict:
        return {
            "running":     self.running,
            "interval":    self.interval,
            "last_check":  self.last_check,
            "last_action": self.last_action,
        }
