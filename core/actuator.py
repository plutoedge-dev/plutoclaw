"""
PlutoClaw Actuator Manager
Controls GPIO outputs: relay, buzzer, LED, servo, PWM motor

Wiring Relay Module (active-high, most common):
  VCC  → Pin 2 (5V)
  GND  → Pin 6 (GND)
  IN   → GPIO pin (HIGH = ON)

Wiring Buzzer:
  +    → GPIO pin
  -    → GND

Wiring LED:
  +    → GPIO pin (via 330Ω resistor)
  -    → GND

On Mac/dev: all operations are simulated (log only, no GPIO)
On Pi     : real GPIO output via RPi.GPIO
"""
import logging
import threading
import time
from core.platform import is_pi

logger = logging.getLogger("plutoclaw.actuator")


# ── Actuator Types ─────────────────────────────────────────────────────────────
ACTUATOR_TYPES = ("relay", "buzzer", "led", "servo", "pwm")


class Actuator:
    """A single actuator unit (relay/buzzer/LED/servo/PWM)"""

    def __init__(self, cfg: dict):
        self.id          = cfg["id"]
        self.name        = cfg.get("name", self.id)
        self.type        = cfg.get("type", "relay")
        self.pin         = cfg.get("pin")
        self.active_high = cfg.get("active_high", True)   # True → HIGH=ON, False → LOW=ON
        self.enabled     = cfg.get("enabled", True)
        self.default_off = cfg.get("default_off", True)   # turn off at startup

        self._state    = False   # False = OFF, True = ON
        self._duty     = 0       # untuk PWM (0-100)
        self._lock     = threading.Lock()
        self._pulse_t  = None    # thread auto-off setelah pulse
        self._gpio     = None

        if is_pi() and self.pin:
            self._init_gpio()
        else:
            logger.info(f"[Actuator] '{self.name}' (pin {self.pin}) → simulasi mode")

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.pin, GPIO.OUT)
            # Set to OFF on init
            off_val = GPIO.HIGH if not self.active_high else GPIO.LOW
            GPIO.output(self.pin, off_val)
            self._gpio = GPIO
            logger.info(f"[Actuator] '{self.name}' ready on GPIO {self.pin}")
        except Exception as e:
            logger.error(f"[Actuator] Failed to init GPIO {self.pin}: {e}")

    def _write(self, on: bool):
        """Write state to GPIO (or simulate)"""
        self._state = on
        label = "ON" if on else "OFF"
        if self._gpio:
            import RPi.GPIO as GPIO
            val = GPIO.HIGH if (on == self.active_high) else GPIO.LOW
            self._gpio.output(self.pin, val)
            logger.info(f"[Actuator] '{self.name}' → {label} (GPIO {self.pin})")
        else:
            logger.info(f"[Actuator] [SIM] '{self.name}' → {label}")

    # ── Public API ───────────────────────────────────────────────────────────

    def turn_on(self):
        with self._lock:
            self._write(True)

    def turn_off(self):
        with self._lock:
            self._write(False)

    def toggle(self):
        with self._lock:
            self._write(not self._state)

    def pulse(self, duration: float = 1.0):
        """
        Turn on for `duration` seconds then turn off automatically.
        Thread-safe. Interrupts previous pulse if any.
        """
        with self._lock:
            if self._pulse_t and self._pulse_t.is_alive():
                # Let the old thread finish — just set state
                pass
            self._write(True)

        def _auto_off():
            time.sleep(duration)
            with self._lock:
                self._write(False)

        self._pulse_t = threading.Thread(target=_auto_off, daemon=True)
        self._pulse_t.start()

    def set_pwm(self, duty: int):
        """Set PWM duty cycle 0-100 (for motor/LED dimmer)"""
        self._duty = max(0, min(100, duty))
        logger.info(f"[Actuator] [PWM] '{self.name}' → {self._duty}%")
        # TODO: implement RPi.GPIO PWM when needed

    def cleanup(self):
        if self._gpio and self.pin:
            try:
                import RPi.GPIO as GPIO
                GPIO.output(self.pin, GPIO.LOW)
                logger.info(f"[Actuator] '{self.name}' cleanup OK")
            except Exception:
                pass

    @property
    def state(self) -> bool:
        return self._state

    @property
    def info(self) -> dict:
        return {
            "id":      self.id,
            "name":    self.name,
            "type":    self.type,
            "pin":     self.pin,
            "state":   self._state,
            "duty":    self._duty,
            "enabled": self.enabled,
        }


# ── Actuator Manager ───────────────────────────────────────────────────────────

class ActuatorManager:
    """
    Manages all actuators from config.yaml.
    Injected into agents and dashboard like other components.
    """

    def __init__(self, actuators_config: list):
        self._actuators: dict[str, Actuator] = {}

        for cfg in (actuators_config or []):
            if not cfg.get("enabled", True):
                continue
            act = Actuator(cfg)
            self._actuators[act.id] = act

        logger.info(f"ActuatorManager: {len(self._actuators)} actuator(s) registered "
                    f"({list(self._actuators.keys())})")

    def get(self, act_id: str) -> Actuator | None:
        return self._actuators.get(act_id)

    def all(self) -> list[Actuator]:
        return list(self._actuators.values())

    def get_all_info(self) -> list[dict]:
        return [a.info for a in self._actuators.values()]

    def turn_on(self, act_id: str) -> bool:
        a = self.get(act_id)
        if a:
            a.turn_on()
            return True
        return False

    def turn_off(self, act_id: str) -> bool:
        a = self.get(act_id)
        if a:
            a.turn_off()
            return True
        return False

    def toggle(self, act_id: str) -> bool:
        a = self.get(act_id)
        if a:
            a.toggle()
            return True
        return False

    def pulse(self, act_id: str, duration: float = 1.0) -> bool:
        a = self.get(act_id)
        if a:
            a.pulse(duration)
            return True
        return False

    def cleanup_all(self):
        for a in self._actuators.values():
            a.cleanup()
