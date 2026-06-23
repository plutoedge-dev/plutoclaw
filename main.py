"""
PlutoClaw — AI Orchestrator for IoT & Hardware Automation
Run: python3 main.py
"""
import sys
import os
import logging
import signal
import threading
import time
import uvicorn

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.config_loader import load_config
from core.platform      import print_platform_info
from core.camera        import CameraManager
from core.detector      import YOLODetector
from core.llm           import LLMConnector
from core.alert         import AlertManager
from core.storage       import Storage
from core.actuator      import ActuatorManager
from skills             import SKILL_REGISTRY
from pluto              import ConversationHandler, AutomationHandler
from dashboard.app      import create_app

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
from logging.handlers import RotatingFileHandler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("data/plutoclaw.log", maxBytes=5*1024*1024,
                            backupCount=3, encoding="utf-8")
    ]
)
logger = logging.getLogger("plutoclaw")

# ── Shutdown ──────────────────────────────────────────────────────────────────
shutdown_event = threading.Event()

def handle_shutdown(sig, frame):
    logger.info("Received shutdown signal...")
    shutdown_event.set()

signal.signal(signal.SIGINT,  handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "═"*52)
    print("  🐾  PlutoClaw — AI Orchestrator IoT & Hardware")
    print("═"*52)
    print_platform_info()
    print("═"*52 + "\n")

    # 1. Config
    config      = load_config("config.yaml")
    device_name = config["plutoclaw"]["device_name"]
    domain      = config["plutoclaw"].get("domain", config["plutoclaw"].get("usecase", "general"))
    logger.info(f"Device: {device_name} | Domain: {domain}")

    # 2. Core services
    storage_cfg = config.get("storage", {})
    storage     = Storage(db_path=storage_cfg.get("db_path", "data/plutoclaw.db"),
                          media_path=storage_cfg.get("media_path", "media"))

    llm_cfg = config.get("llm", {})
    llm = LLMConnector(model=llm_cfg.get("model", "plutoedge"),
                       host=llm_cfg.get("host", "http://localhost:11434"))
    if llm_cfg.get("enabled", True):
        llm.check()

    alert           = AlertManager(config, storage)
    actuator_manager = ActuatorManager(config.get("actuators", []))
    logger.info(f"Actuators: {[a.id for a in actuator_manager.all()]}")

    # 3. Camera & detector (only init if vision skill is present)
    camera_manager = CameraManager(cameras_config=config.get("cameras", []),
                                   media_path=storage_cfg.get("media_path", "media"))
    camera_manager.start_all()
    time.sleep(1)

    detector = YOLODetector(model_name="yolov8n.pt", confidence=0.5)
    detector.load()

    # 4. Start skills
    active_skills: dict = {}
    skills_cfg = config.get("skills", config.get("agents", {}))

    for skill_name, skill_cfg in skills_cfg.items():
        if not skill_cfg.get("enabled", False):
            continue
        SkillClass = SKILL_REGISTRY.get(skill_name)
        if not SkillClass:
            logger.warning(f"Skill '{skill_name}' not found in registry, skipping")
            continue

        cam_id = skill_cfg.get("camera")
        camera = camera_manager.get(cam_id) if cam_id else None

        skill = SkillClass(
            config=skill_cfg,
            camera=camera,
            detector=detector,
            llm=llm,
            alert=alert,
            storage=storage
        )
        skill.start()
        active_skills[skill_name] = skill

    logger.info(f"✅ {len(active_skills)} skill(s) running: {list(active_skills.keys())}")

    # 5. Init Pluto AI (conversation + automation)
    pluto_conv = ConversationHandler(
        llm=llm, skills=active_skills,
        actuator_manager=actuator_manager,
        alert=alert, config=config
    )

    pluto_auto = AutomationHandler(
        llm=llm, skills=active_skills,
        actuator_manager=actuator_manager,
        alert=alert, config=config,
        interval_seconds=config.get("pluto", {}).get("automation_interval", 60)
    )
    if config.get("pluto", {}).get("automation_enabled", True):
        pluto_auto.start()

    # 6. Dashboard
    dash_cfg = config.get("dashboard", {})
    if dash_cfg.get("enabled", True):
        app = create_app(
            camera_manager=camera_manager,
            storage=storage,
            skills=active_skills,
            config=config,
            detector=detector,
            llm=llm,
            alert=alert,
            actuator_manager=actuator_manager,
            pluto_conv=pluto_conv,
            pluto_auto=pluto_auto
        )
        host = dash_cfg.get("host", "0.0.0.0")
        port = dash_cfg.get("port", 8080)
        threading.Thread(
            target=lambda: uvicorn.run(app, host=host, port=port, log_level="warning"),
            daemon=True
        ).start()
        logger.info(f"✅ Dashboard: http://localhost:{port}")

    # 7. Summary
    print("\n" + "─"*52)
    print(f"  PlutoClaw running — {device_name}")
    print(f"  Dashboard   : http://localhost:{dash_cfg.get('port', 8080)}")
    print(f"  Skills      : {list(active_skills.keys())}")
    print(f"  Automation  : {'ON' if pluto_auto.running else 'OFF'}")
    print("  Press Ctrl+C to stop")
    print("─"*52 + "\n")

    # 8. Main loop
    while not shutdown_event.is_set():
        time.sleep(1)

    # Cleanup
    logger.info("Stopping all skills...")
    for skill in active_skills.values():
        skill.stop()
    pluto_auto.stop()
    camera_manager.stop_all()
    actuator_manager.cleanup_all()
    logger.info("PlutoClaw stopped. Goodbye! 🐾")


if __name__ == "__main__":
    main()
