"""
LLM connector - Ollama interface + prompt templates in English
"""
import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger("plutoclaw.llm")

# ── Prompt Templates ──────────────────────────────────────────────────────────

TEMPLATES = {
    "ppe_violation": """You are the PlutoClaw warehouse security system.
Write a short alert message in English (max 3 sentences) for the following event:
- Location : {location}
- Event    : {count} worker(s) detected WITHOUT full PPE (helmet/vest)
- Time     : {time}
Start with emoji ⚠️. Be brief, direct, and clear.""",

    "intrusion": """You are the PlutoClaw warehouse security system.
Write an urgent alert message in English (max 3 sentences) for the following event:
- Location : {location}
- Event    : {count} person(s) detected in the warehouse area OUTSIDE operating hours
- Time     : {time}
Start with emoji 🚨. Be firm and urgent.""",

    "forklift_danger": """You are the PlutoClaw warehouse security system.
Write a danger alert message in English (max 3 sentences):
- Location : {location}
- Event    : Forklift and worker detected in the same zone — collision risk
- Time     : {time}
Start with emoji 🚧. Very brief and urgent.""",

    "sick_animal": """You are the PlutoClaw livestock monitoring system.
Write an alert message in English (max 4 sentences):
- Location : {location}
- Event    : {count} animal(s) detected showing abnormal symptoms
- Time     : {time}
Start with emoji 🐾. Include initial action recommendation.""",

    "sensor_alert": """You are the PlutoClaw monitoring system.
Write a short alert message in English (max 3 sentences):
- Sensor   : {sensor_name}
- Value    : {value} {unit}
- Status   : {status} (threshold: {threshold})
- Time     : {time}
Start with a context-appropriate emoji. Include an action recommendation.""",

    "daily_summary": """You are the PlutoClaw daily report assistant.
Write a daily summary in English based on the following data:
{events_summary}

Report format:
📊 *Daily Report - {date}*
Device: {device_name}

Summarize key events, number of alerts, and recommendations for tomorrow.
Maximum 10 sentences. Professional and informative.""",

    "animal_count": """You are the PlutoClaw livestock monitoring system.
Write a livestock count report in English (max 3 sentences):
- Location     : {location}
- Livestock    : {count} animal(s) detected
- Time         : {time}
Start with emoji 📋.""",
}


# ── LLM Connector ─────────────────────────────────────────────────────────────

class LLMConnector:
    def __init__(self, model: str = "plutoedge", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.available = False

    def check(self) -> bool:
        """Check whether Ollama is online"""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])]
            self.available = any(self.model in m for m in models)
            if self.available:
                logger.info(f"✅ LLM ready: {self.model}")
            else:
                logger.warning(f"⚠️ Model {self.model} not found in Ollama")
            return self.available
        except Exception as e:
            logger.warning(f"Ollama unavailable: {e}")
            return False

    def generate(self, prompt: str, timeout: int = 60) -> str:
        """Generate text from prompt (legacy — use chat() for conversation)"""
        if not self.available:
            return ""
        try:
            r = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=timeout
            )
            return r.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"LLM generate error: {e}")
            return ""

    def chat(self, system: str, user: str, timeout: int = 180,
             num_ctx: int = 1024, num_predict: int = 200) -> str:
        """Generate using /api/chat with proper system/user role separation (ChatML-aware)."""
        if not self.available:
            return ""
        try:
            r = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "stream": False,
                    "options": {
                        "num_ctx":     num_ctx,
                        "num_predict": num_predict,
                    },
                },
                timeout=timeout
            )
            return r.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            return ""

    def from_template(self, template_name: str, **kwargs) -> str:
        """Generate text from an existing template"""
        template = TEMPLATES.get(template_name)
        if not template:
            logger.warning(f"Template not found: {template_name}")
            return ""

        kwargs.setdefault("time", datetime.now().strftime("%H:%M:%S"))
        kwargs.setdefault("date", datetime.now().strftime("%d %B %Y"))

        prompt = template.format(**kwargs)
        return self.generate(prompt)

    def make_fallback_message(self, template_name: str, **kwargs) -> str:
        """
        Fallback message if LLM is unavailable.
        Generates text directly without LLM.
        """
        now = datetime.now().strftime("%H:%M:%S")
        location = kwargs.get("location", "Unknown area")
        count = kwargs.get("count", 1)

        fallbacks = {
            "ppe_violation": f"⚠️ PPE ALERT: {count} worker(s) without PPE at {location} at {now}.",
            "intrusion":     f"🚨 INTRUSION: {count} person(s) detected at {location} outside working hours at {now}!",
            "forklift_danger": f"🚧 DANGER: Forklift & worker in same zone ({location}) at {now}!",
            "sick_animal":   f"🐾 ALERT: {count} animal(s) showing sick symptoms at {location} at {now}.",
            "sensor_alert":  f"📡 SENSOR: {kwargs.get('sensor_name','?')} = {kwargs.get('value','?')} ({kwargs.get('status','?')}) at {now}.",
            "daily_summary": f"📊 Daily report {kwargs.get('date', now)} - LLM unavailable.",
            "animal_count":  f"📋 {count} livestock detected at {location} at {now}.",
        }
        return fallbacks.get(template_name, f"[Alert] {template_name} at {now}")

    def alert_message(self, template_name: str, **kwargs) -> str:
        """
        Generate alert message - uses LLM if available, fallback otherwise
        """
        if self.available:
            msg = self.from_template(template_name, **kwargs)
            if msg:
                return msg
        return self.make_fallback_message(template_name, **kwargs)
