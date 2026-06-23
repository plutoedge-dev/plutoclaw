"""
context_builder.py — injects system state into LLM prompt.

Called before every LLM call (conversation and automation mode)
so Pluto always has up-to-date context.
"""
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger("plutoclaw.context")

import platform as _platform

_KNOWLEDGE_BASE = None
_IS_PI = _platform.machine() == "aarch64"

# Compact KB for Pi (fits in 1024 ctx), full KB for Mac (uses 2048 ctx)
_KB_PATH = Path(__file__).parent.parent / "knowledge" / (
    "knowledge_base_compact.md" if _IS_PI else "knowledge_base.md"
)

# Action verbs → device control command (no KB needed)
_COMMAND_VERBS = {
    "turn on", "turn off", "switch on", "switch off",
    "activate", "deactivate", "enable", "disable",
    "toggle", "pulse", "trigger",
    "nyalakan", "matikan", "aktifkan", "nonaktifkan",
    "hidupkan", "padamkan", "jalankan",
}

# Status/sensor queries → read device state, not KB
_STATUS_KEYWORDS = {
    "temperature", "humidity", "sensor", "reading", "status",
    "current", "right now", "sekarang", "saat ini", "berapa",
    "suhu", "kelembaban", "tanah", "soil", "moisture",
    "what is the", "what are the", "show me", "check",
    "relay", "buzzer", "led", "actuator", "device",
}

# Platform/feature questions → need KB
_KNOWLEDGE_KEYWORDS = {
    "skill", "skills", "what skill", "feature", "capability",
    "install", "setup", "configure", "how to", "how do",
    "recommend", "suggest", "use case", "industry", "domain",
    "warehouse", "gudang", "farming", "pertanian", "kandang",
    "cold storage", "healthcare", "smart home",
    "apa itu", "what is plutoclaw", "what is plutoedge",
    "troubleshoot", "not working", "error",
}


_BAHASA_TO_EN = [
    ("skill apa untuk", "what skills for"),
    ("skill apa",       "what skills"),
    ("apa saja skill",  "what skills"),
    ("apa saja",        "what are"),
    ("kandang ayam",    "chicken farm poultry"),
    ("kandang",         "poultry farm"),
    ("pertanian sayur", "vegetable farming"),
    ("pertanian",       "crop farming"),
    ("gudang",          "warehouse"),
    ("cold storage",    "cold storage"),
    ("untuk apa",       "what is used for"),
    ("digunakan untuk", "used for"),
    ("bagaimana cara",  "how to"),
    ("bagaimana",       "how"),
    ("caranya",         "how to"),
    ("apa itu",         "what is"),
    ("untuk",           "for"),
    ("apa",             "what"),
]


def _normalize_to_english(msg: str) -> str:
    """Translate common Bahasa knowledge query terms to English for better 1.5B extraction."""
    result = msg.lower()
    for bahasa, english in _BAHASA_TO_EN:
        result = result.replace(bahasa, english)
    return result


def _load_knowledge_base() -> str:
    global _KNOWLEDGE_BASE
    if _KNOWLEDGE_BASE is None:
        if _KB_PATH.exists():
            _KNOWLEDGE_BASE = _KB_PATH.read_text(encoding="utf-8")
            logger.info(f"Knowledge base loaded: {len(_KNOWLEDGE_BASE)} chars")
        else:
            _KNOWLEDGE_BASE = ""
            logger.warning(f"Knowledge base not found: {_KB_PATH}")
    return _KNOWLEDGE_BASE


def _is_knowledge_query(user_message: str) -> bool:
    """
    Return True only for platform/feature questions that need KB injection.
    Status queries (sensor readings, device state) and commands skip KB.
    """
    msg = user_message.lower()
    if any(v in msg for v in _COMMAND_VERBS):
        return False
    if any(k in msg for k in _STATUS_KEYWORDS):
        return False
    if any(k in msg for k in _KNOWLEDGE_KEYWORDS):
        return True
    # Default: no KB (safe fallback — avoids hallucination from irrelevant KB content)
    return False


def build_context(skills: dict, actuator_manager=None, config: dict = None) -> str:
    """
    Build context string from current system state.
    Injected into Pluto LLM system prompt.
    """
    lines = [
        f"Current time: {datetime.now().strftime('%d %B %Y %H:%M:%S')}",
        f"Device: {(config or {}).get('plutoclaw', {}).get('device_name', 'PlutoClaw')}",
        "",
        "=== ACTIVE SKILLS ===",
    ]

    if skills:
        for name, skill in skills.items():
            status = skill.get_status() if hasattr(skill, "get_status") else {}
            s = status.get("status", "unknown")
            desc = getattr(skill, "description", "")
            lines.append(f"- {name} [{s}]: {desc}")

            # Add last_reading if available (sensor skills)
            last = status.get("last_reading", {})
            if last and last.get("status") in ("ok", "simulated"):
                details = []
                if "temperature" in last:
                    details.append(f"temp={last['temperature']}°C")
                if "humidity" in last:
                    details.append(f"humidity={last['humidity']}%")
                if "soil_dry" in last:
                    details.append(f"soil={'DRY' if last['soil_dry'] else 'moist enough'}")
                if details:
                    lines.append(f"  Sensor: {', '.join(details)}")
    else:
        lines.append("- No active skills")

    lines.append("")
    lines.append("=== ACTUATORS ===")

    if actuator_manager:
        for act in actuator_manager.all():
            state = "ON" if act._state else "OFF"
            lines.append(f"- {act.id} ({act.name}): {state} | type: {act.type}")
    else:
        lines.append("- No actuators registered")

    return "\n".join(lines)


def build_system_prompt(skills: dict, actuator_manager=None, config: dict = None,
                        user_message: str = "") -> str:
    """
    Full system prompt for Pluto LLM.
    KB is placed at the TOP so the model reads it before device state.
    """
    lang         = (config or {}).get("llm", {}).get("language", "english")
    context      = build_context(skills, actuator_manager, config)
    skill_names  = list(skills.keys()) if skills else []
    actuator_ids = [a.id for a in actuator_manager.all()] if actuator_manager else []

    is_knowledge = user_message and _is_knowledge_query(user_message)

    lang_instruction = (
        "Always respond in English only. Do not switch to any other language even if the user writes in another language."
        if lang.lower() == "english"
        else f"Always respond in {lang}."
    )

    if is_knowledge:
        # Knowledge mode: KB only — hide live device state to prevent model bias
        kb = _load_knowledge_base()
        kb_block = (
            f"=== PLUTOCLAW REFERENCE ===\n{kb}\n=== END REFERENCE ==="
        ) if kb else ""

        return f"""You are Pluto, an AI assistant for the PlutoClaw Edge AI platform.
{lang_instruction}

{kb_block}

When asked about skills for a domain, list ONLY the exact skill names shown in the PLUTOCLAW REFERENCE for that domain.
Format: "- skill_name: what it does"
Do not invent skill names. Use only names written above."""

    else:
        # Control/status mode: live device state, no KB
        return f"""You are Pluto, an AI controller for the PlutoClaw Edge AI platform.
{lang_instruction}

{context}

=== DEVICE COMMANDS ===
To control a device, end your response with PLUTO_ACTION on its own line.
Single: PLUTO_ACTION: {{"type": "actuator_trigger", "params": {{"id": "<id>", "action": "on/off/toggle"}}}}
Multi:  PLUTO_ACTION: {{"type": "multi_trigger", "params": [{{"id": "<id1>", "action": "on"}}, ...]}}
Available actuators: {actuator_ids}
Available skills: {skill_names}

=== RULES ===
- Respond briefly then add PLUTO_ACTION for device control.
- For sensor/status questions, read from the device state above.
- Only use actuator IDs listed above."""
