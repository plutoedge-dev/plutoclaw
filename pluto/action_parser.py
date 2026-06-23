"""
action_parser.py — parses PlutoEdge LLM output into executable actions.

PlutoEdge outputs actions in this format:
  PLUTO_ACTION: {"type": "actuator_trigger", "params": {"id": "relay1", "action": "on"}}
  PLUTO_ACTION: {"type": "multi_trigger", "params": [{"id": "relay1", "action": "on"}, ...]}

These are mapped to PlutoClaw's internal action format for execution.
"""
import json
import re
import logging

logger = logging.getLogger("plutoclaw.action_parser")

VALID_ACTUATOR_CMDS = {"on", "off", "toggle", "pulse"}


def parse_action(llm_response: str) -> dict | None:
    """
    Extract PLUTO_ACTION from PlutoEdge response.
    Maps to internal PlutoClaw action format.
    Returns action dict or None if not found.
    """
    match = re.search(r'PLUTO_ACTION\s*:\s*(\{.+\})', llm_response)
    if not match:
        return None

    try:
        obj = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse PLUTO_ACTION JSON: {match.group(1)}")
        return None

    action_type = obj.get("type")
    params = obj.get("params", {})

    if action_type == "actuator_trigger":
        actuator_id = params.get("id")
        cmd = params.get("action", "").lower()
        if not actuator_id or cmd not in VALID_ACTUATOR_CMDS:
            logger.warning(f"Invalid actuator_trigger: {obj}")
            return None
        return {"action": "actuator", "id": actuator_id, "cmd": cmd}

    elif action_type == "multi_trigger":
        if not isinstance(params, list) or not params:
            logger.warning(f"Invalid multi_trigger params: {params}")
            return None
        # Return first action; caller can loop via parse_all_actions for multi
        first = params[0]
        return {
            "action": "multi_trigger",
            "triggers": [
                {"id": p["id"], "cmd": p.get("action", "on")}
                for p in params
                if p.get("id")
            ]
        }

    logger.warning(f"Unknown PLUTO_ACTION type: {action_type}")
    return None


def parse_all_actions(llm_response: str) -> list[dict]:
    """Parse all PLUTO_ACTION entries (in case model emits multiple)."""
    actions = []
    for match in re.finditer(r'PLUTO_ACTION\s*:\s*(\{.+\})', llm_response):
        try:
            obj = json.loads(match.group(1))
            action_type = obj.get("type")
            params = obj.get("params", {})
            if action_type == "actuator_trigger":
                cmd = params.get("action", "on").lower()
                if params.get("id") and cmd in VALID_ACTUATOR_CMDS:
                    actions.append({"action": "actuator", "id": params["id"], "cmd": cmd})
            elif action_type == "multi_trigger" and isinstance(params, list):
                for p in params:
                    cmd = p.get("action", "on").lower()
                    if p.get("id") and cmd in VALID_ACTUATOR_CMDS:
                        actions.append({"action": "actuator", "id": p["id"], "cmd": cmd})
        except json.JSONDecodeError:
            continue
    return actions


def strip_action_json(llm_response: str) -> str:
    """Remove PLUTO_ACTION lines from response text for clean display."""
    text = re.sub(r'\bPLUTO_ACTION\s*:.*', '', llm_response, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
