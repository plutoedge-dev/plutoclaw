"""
conversation.py — handler for Pluto conversation mode.

User chats freely with Pluto. Pluto can answer questions
and execute actions if needed.
"""
import logging
from pluto.context_builder import build_system_prompt, _is_knowledge_query, _normalize_to_english, _IS_PI
from pluto.action_parser   import parse_action, parse_all_actions, strip_action_json
from core.dataset_logger   import log_interaction

logger = logging.getLogger("plutoclaw.conversation")


class ConversationHandler:
    def __init__(self, llm, skills: dict, actuator_manager=None,
                 alert=None, config: dict = None):
        self.llm              = llm
        self.skills           = skills
        self.actuator_manager = actuator_manager
        self.alert            = alert
        self.config           = config or {}

    def chat(self, user_message: str) -> dict:
        """
        Process user message, return dict:
        {
          "reply": str,           # reply text to display
          "action": dict | None,  # action to execute (if any)
          "action_result": dict   # action execution result
        }
        """
        if not self.llm or not self.llm.available:
            return {
                "reply": "Pluto LLM unavailable. Make sure Ollama is running.",
                "action": None,
                "action_result": {}
            }

        is_knowledge = _is_knowledge_query(user_message)
        system_prompt = build_system_prompt(
            self.skills, self.actuator_manager, self.config,
            user_message=user_message
        )

        # Knowledge queries: normalize Bahasa → English so 1.5B extracts skill names correctly
        llm_user_msg = _normalize_to_english(user_message) if is_knowledge else user_message

        # Pi uses compact KB → stays within 1024 ctx; Mac uses full KB → needs 2048
        ctx_size   = 1024 if (_IS_PI or not is_knowledge) else 2048
        num_pred   = 150  if (_IS_PI and is_knowledge) else (300 if is_knowledge else 200)
        timeout    = 240  if (_IS_PI and is_knowledge) else 180
        raw_response = self.llm.chat(
            system_prompt, llm_user_msg,
            timeout=timeout, num_ctx=ctx_size, num_predict=num_pred
        )
        if not raw_response:
            return {"reply": "Pluto is not responding.", "action": None, "action_result": {}}

        # Parse all actions from response (PlutoEdge may emit multi_trigger)
        actions = parse_all_actions(raw_response)
        action = actions[0] if actions else None
        clean_reply = strip_action_json(raw_response)

        # Execute all actions
        action_result = {}
        for act in actions:
            result = self._execute(act)
            if not action_result:
                action_result = result

        # Log interaction for Pluto-LM training
        log_interaction(
            system_prompt=system_prompt,
            user_message=user_message,
            assistant_response=raw_response,
            action_executed=action
        )

        return {
            "reply":         clean_reply,
            "action":        action,
            "action_result": action_result
        }

    def _execute(self, action: dict) -> dict:
        """Execute action parsed from LLM response."""
        a = action.get("action")
        try:
            if a == "start_skill":
                skill_name = action["skill"]
                if skill_name in self.skills:
                    self.skills[skill_name].start()
                    return {"ok": True, "msg": f"Skill '{skill_name}' started"}
                return {"ok": False, "msg": f"Skill '{skill_name}' not found"}

            elif a == "stop_skill":
                skill_name = action["skill"]
                if skill_name in self.skills:
                    self.skills[skill_name].stop()
                    return {"ok": True, "msg": f"Skill '{skill_name}' stopped"}
                return {"ok": False, "msg": f"Skill '{skill_name}' not found"}

            elif a == "actuator":
                if not self.actuator_manager:
                    return {"ok": False, "msg": "Actuator manager not available"}
                act = self.actuator_manager.get(action["id"])
                if not act:
                    return {"ok": False, "msg": f"Actuator '{action['id']}' not found"}
                cmd = action["cmd"]
                if cmd == "on":     act.turn_on()
                elif cmd == "off":  act.turn_off()
                elif cmd == "toggle": act.toggle()
                elif cmd == "pulse":  act.pulse(action.get("duration", 3.0))
                return {"ok": True, "msg": f"Actuator '{action['id']}' → {cmd}"}

            elif a == "send_alert":
                if self.alert:
                    self.alert.send(action["message"], agent="pluto")
                    return {"ok": True, "msg": "Alert sent"}
                return {"ok": False, "msg": "Alert manager not available"}

        except Exception as e:
            logger.error(f"Failed to execute action {a}: {e}")
            return {"ok": False, "msg": str(e)}

        return {"ok": False, "msg": f"Unknown action: {a}"}
