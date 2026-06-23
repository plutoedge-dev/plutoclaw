"""
PlutoClaw Dataset Logger
Automatically saves every chat interaction to JSONL for future Pluto-LM training.

Format output (ChatML-compatible dengan Unsloth):
  {"messages": [...], "timestamp": "...", "context": {...}, "action": {...}}

File: data/chat_dataset.jsonl
"""
import json
import logging
import os
import uuid
from datetime import datetime

logger = logging.getLogger("plutoclaw.dataset")

DATASET_PATH = "data/chat_dataset.jsonl"


def log_interaction(
    system_prompt: str,
    user_message: str,
    assistant_response: str,
    context_snapshot: dict = None,
    action_executed: dict = None,
    session_id: str = None,
):
    """
    Save one conversation turn to the JSONL dataset.

    Args:
        system_prompt: System prompt used (including context state)
        user_message: Message from user
        assistant_response: Clean response from LLM (without action markers)
        context_snapshot: System state at that point (agents, sensors, events)
        action_executed: Action that was executed (if any)
        session_id: Chat session ID (optional, auto-generated if None)
    """
    try:
        os.makedirs("data", exist_ok=True)

        entry = {
            "id": str(uuid.uuid4())[:8],
            "session_id": session_id or str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "messages": [
                {"role": "system",    "content": system_prompt},
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ],
            "context": context_snapshot or {},
            "action": action_executed or {},
        }

        with open(DATASET_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.debug(f"[Dataset] Logged interaction id={entry['id']}")

    except Exception as e:
        logger.warning(f"[Dataset] Failed to log interaction: {e}")


def get_stats() -> dict:
    """Return statistics of collected dataset."""
    try:
        if not os.path.exists(DATASET_PATH):
            return {"total": 0, "path": DATASET_PATH, "size_kb": 0}

        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]

        size_kb = round(os.path.getsize(DATASET_PATH) / 1024, 1)
        return {
            "total": len(lines),
            "path": DATASET_PATH,
            "size_kb": size_kb,
        }
    except Exception as e:
        return {"total": 0, "path": DATASET_PATH, "size_kb": 0, "error": str(e)}
