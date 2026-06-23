"""
Config loader - reads config.yaml and provides it to all components
"""
import yaml
import os
from core.platform import get_platform


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate config.yaml"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r") as f:
        config = yaml.safe_load(f)

    # Auto-detect platform if not set
    if not config.get("plutoclaw", {}).get("environment"):
        config.setdefault("plutoclaw", {})["environment"] = get_platform()

    return config


def get_active_agents(config: dict) -> list:
    """Get list of enabled agents"""
    agents = config.get("agents", {})
    return [name for name, cfg in agents.items() if cfg and cfg.get("enabled", False)]


def get_camera_config(config: dict, camera_id: str) -> dict:
    """Get camera configuration by id"""
    cameras = config.get("cameras", [])
    for cam in cameras:
        if cam["id"] == camera_id:
            return cam
    return None


def get_agent_config(config: dict, agent_name: str) -> dict:
    """Get configuration for a specific agent"""
    return config.get("agents", {}).get(agent_name, {})
