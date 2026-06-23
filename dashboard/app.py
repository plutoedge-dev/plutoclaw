"""
PlutoClaw Dashboard - FastAPI web UI
Live camera feed + alert log + status agent
"""
import asyncio
import cv2
import json
import logging
import os
from datetime import datetime
import secrets
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("plutoclaw.dashboard")

# Referensi global ke komponen (di-inject dari main.py)
_camera_manager = None
_storage = None
_agents = {}
_config = {}
_detector = None
_llm = None
_alert = None
_actuator_manager = None

LOG_FILE = "data/plutoclaw.log"


_pluto_conv = None
_pluto_auto = None
_skills = {}


def create_app(camera_manager, storage, skills: dict, config: dict,
               detector=None, llm=None, alert=None, actuator_manager=None,
               pluto_conv=None, pluto_auto=None,
               # backward compat
               agents: dict = None):
    global _camera_manager, _storage, _agents, _skills, _config, _detector, _llm, _alert, _actuator_manager, _pluto_conv, _pluto_auto
    _camera_manager   = camera_manager
    _storage          = storage
    _skills           = skills
    _agents           = skills  # backward compat untuk kode lama
    _config           = config
    _detector         = detector
    _llm              = llm
    _alert            = alert
    _actuator_manager = actuator_manager
    _pluto_conv       = pluto_conv
    _pluto_auto       = pluto_auto

    # ── Basic Auth (optional — enable via dashboard.auth.enabled in config.yaml)
    _security = HTTPBasic(auto_error=False)
    _auth_cfg  = config.get("dashboard", {}).get("auth", {})
    _auth_on   = _auth_cfg.get("enabled", False)
    _auth_user = _auth_cfg.get("username", "admin")
    _auth_pass = _auth_cfg.get("password", "pluto1234")

    def _check_auth(creds: HTTPBasicCredentials = Depends(_security)):
        if not _auth_on:
            return True
        if creds is None:
            raise HTTPException(
                status_code=401,
                detail="Login required",
                headers={"WWW-Authenticate": "Basic realm='PlutoClaw'"}
            )
        ok_user = secrets.compare_digest(creds.username.encode(), _auth_user.encode())
        ok_pass = secrets.compare_digest(creds.password.encode(), _auth_pass.encode())
        if not (ok_user and ok_pass):
            raise HTTPException(
                status_code=401,
                detail="Username or password incorrect",
                headers={"WWW-Authenticate": "Basic realm='PlutoClaw'"}
            )
        return True

    app = FastAPI(title="PlutoClaw Dashboard", dependencies=[Depends(_check_auth)])

    import os as _os
    _public_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "public")
    if _os.path.isdir(_public_dir):
        app.mount("/public", StaticFiles(directory=_public_dir), name="public")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return open("dashboard/index.html").read()

    @app.get("/api/status")
    async def status():
        from core.platform import get_platform, has_hailo, has_gpio
        from core.llm import LLMConnector

        # Check Ollama
        llm_cfg = _config.get("llm", {})
        ollama_ok = False
        if llm_cfg.get("enabled", True):
            try:
                import requests
                r = requests.get(
                    f"{llm_cfg.get('host', 'http://localhost:11434')}/api/tags",
                    timeout=2
                )
                ollama_ok = r.status_code == 200
            except Exception:
                ollama_ok = False

        # Camera statuses
        cam_statuses = []
        if _camera_manager:
            for cam in _camera_manager.get_all_status():
                cam_statuses.append(cam)

        # Stats
        stats = _storage.get_stats() if _storage else {}

        env = get_platform()
        hailo = has_hailo()
        gpio = has_gpio()

        # Sensor statuses dari config
        sensors_cfg = _config.get("sensors", []) or []
        sensor_statuses = []
        for s in sensors_cfg:
            reading = _get_sensor_reading(s)
            sensor_statuses.append({
                "id": s.get("id", "?"),
                "name": s.get("name", s.get("id", "?")),
                "type": s.get("type", "unknown"),
                "pin": s.get("pin"),
                "enabled": s.get("enabled", True),
                "reading": reading,
            })

        # Device capacity (estimasi berdasarkan platform)
        capacity = _get_device_capacity(env, hailo)

        # Skills status
        from skills import SKILL_CATEGORIES
        skill_statuses = []
        for name, skill in (_skills or {}).items():
            s = skill.get_status() if hasattr(skill, "get_status") else {"name": name, "status": "unknown"}
            s["instance_key"] = name
            s["agent_type"]   = name
            skill_statuses.append(s)

        return {
            "device": _config.get("plutoclaw", {}).get("device_name", "PlutoClaw"),
            "domain": _config.get("plutoclaw", {}).get("domain",
                      _config.get("plutoclaw", {}).get("usecase", "-")),
            "usecase": _config.get("plutoclaw", {}).get("domain", "-"),  # backward compat
            "environment": env,
            "platform": env.upper(),
            "hailo": hailo,
            "gpio": gpio,
            "ollama": ollama_ok,
            "ollama_model": _config.get("llm", {}).get("model", "plutoedge"),
            "cameras":    cam_statuses,
            "sensors":    sensor_statuses,
            "skills":            skill_statuses,
            "skill_categories":  SKILL_CATEGORIES,
            "agents":            skill_statuses,  # backward compat
            "stats":      stats,
            "automation": _pluto_auto.status if _pluto_auto else {},
            "wa_bridge": _check_wa_bridge(),
            "capacity": capacity,
            "time": datetime.now().isoformat()
        }

    @app.post("/api/pluto/setup")
    async def pluto_setup(body: dict):
        """Pluto AI — help user configure agents based on business description"""
        message = body.get("message", "").strip()
        history = body.get("history", [])  # [{role, content}, ...]
        if not message:
            return {"reply": "Hello! Tell me about your business and I will recommend the right agents."}

        llm_cfg = _config.get("llm", {})
        host = llm_cfg.get("host", "http://localhost:11434")
        model = llm_cfg.get("model", "plutoedge")

        system_prompt = """You are **Pluto AI**, a configuration assistant for the PlutoClaw Edge AI system.
PlutoClaw is an AI device based on Raspberry Pi, deployed at business locations for automatic monitoring via cameras & sensors, with alerts via WhatsApp.

AVAILABLE AI AGENTS:

=== WAREHOUSE ===
- ppe_guard: Detect workers without PPE (hard hat, safety vest). Alert on safety violations.
- intrusion: Detect people entering outside working hours (set active hours, e.g. 22:00-05:00).
- forklift_guard: Detect dangerous proximity between forklift and workers.
- dock_monitor: Monitor loading dock, detect trucks entering/leaving.
- fire_smoke: Detect fire and smoke in real-time from camera.

=== POULTRY FARMING ===
- sick_chicken: Detect chickens showing signs of illness (idle, separated, abnormal posture).
- chicken_count: Automatically count chicken population at each interval.
- coop_monitor: Monitor coop temperature, humidity, and ammonia via DHT22/MQ135 sensors.
- feed_monitor: Monitor feed level, alert if nearly empty.

=== CATTLE FARMING ===
- estrus_detect: Detect cattle in estrus (important for breeding scheduling).
- birth_monitor: Detect signs of imminent calving (posture, behavior).
- health_monitor: Monitor daily livestock health conditions.

=== GOAT FARMING ===
- goat_health: Monitor goat health from camera.
- goat_count: Count goat population.

=== VEGETABLE FARMING ===
- disease_leaf: Detect leaf disease from camera (spots, wilting, yellowing).
- pest_detect: Detect pests on plants.
- growth_monitor: Monitor plant growth and conditions.

=== FRUIT ORCHARDS ===
- fruit_disease: Detect disease on fruit.
- harvest_ready: Detect fruit ready for harvest.

=== PADDY / RICE FIELDS ===
- rice_disease: Detect rice disease (blast, stem rot).
- water_monitor: Monitor paddy water level via sensor.

=== COLD STORAGE ===
- temp_alert: Alert if temperature goes outside safe range.
- cs_intrusion: Control access into cold storage.

RESPONSE GUIDELINES:
1. First ask about the business type if unclear
2. Recommend 2-5 most relevant agents with JSON at the end of the message
3. Explain why each agent is recommended
4. Mention hardware requirements (camera/sensor)
5. Reply in clear, friendly English
6. When recommending, include JSON on the last line in EXACTLY this format:
{"recommend": ["ppe_guard", "intrusion"]}

Do not recommend too many agents at once. Focus on the most essential ones first."""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        for h in history[-6:]:  # max 6 history
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        try:
            import requests
            r = requests.post(
                f"{host}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=30
            )
            if r.status_code == 200:
                reply = r.json().get("message", {}).get("content", "Sorry, could not process.")
                return {"reply": reply, "model": model}
            else:
                return {"reply": f"Ollama error {r.status_code}. Make sure Ollama is running.", "model": model}
        except Exception as e:
            return {"reply": f"Cannot connect to Ollama: {str(e)[:60]}. Run: `ollama serve`", "model": model}

    @app.get("/api/events")
    async def events(limit: int = 50, agent: str = None):
        rows = _storage.get_recent_events(limit=limit, agent=agent)
        return JSONResponse(rows)

    @app.get("/api/summary")
    async def summary(date: str = None):
        return _storage.get_daily_summary(date)

    @app.get("/api/logs")
    async def logs(
        lines: int = 500,
        level: str = "",       # INFO | WARNING | ERROR | "" (all levels)
        agent: str = "",       # filter nama agent, misal "ppe_guard"
        search: str = "",      # free-text search
    ):
        """
        Baca N baris terakhir dari log file dengan filtering.
        Menggabungkan log file aktif + rotated files (.1, .2, .3) jika perlu.
        Return JSON array of {text, level} so the frontend can render directly.
        """
        # Kumpulkan semua baris dari file aktif + rotated (urutan lama → baru)
        log_files = []
        for suffix in ["3", "2", "1", ""]:
            path = LOG_FILE + (f".{suffix}" if suffix else "")
            if os.path.exists(path):
                log_files.append(path)
        log_files.reverse()  # urutan: aktif dulu, lalu rotated

        all_lines = []
        for path in log_files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines.extend(f.readlines())
            except Exception:
                pass

        if not all_lines:
            return JSONResponse({"lines": [], "total": 0})

        # Filter
        def _level_of(line: str) -> str:
            if " ERROR" in line or "ERROR:" in line:   return "ERROR"
            if " WARNING" in line or "WARNING:" in line: return "WARNING"
            if " INFO" in line or "INFO:" in line:     return "INFO"
            return "DEBUG"

        filtered = []
        for raw in all_lines:
            line = raw.rstrip()
            if not line:
                continue
            lv = _level_of(line)
            if level and lv != level.upper():
                continue
            if agent and agent.lower() not in line.lower():
                continue
            if search and search.lower() not in line.lower():
                continue
            filtered.append({"text": line, "level": lv})

        # Ambil N baris terakhir setelah filter
        tail = filtered[-lines:]
        return JSONResponse({"lines": tail, "total": len(filtered)})

    @app.delete("/api/logs")
    async def clear_logs():
        """Hapus isi log file (bukan hapus file, hanya kosongkan)"""
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%H:%M:%S')} [plutoclaw.dashboard] INFO: Log dibersihkan via dashboard\n")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    @app.get("/api/agents/registry")
    async def agents_registry():
        """Return list of agent IDs yang sudah ada implementasinya"""
        from agents import AGENT_REGISTRY
        return {"registered": list(AGENT_REGISTRY.keys())}

    @app.post("/api/agents/start")
    async def start_agent(body: dict):
        """
        Hot-start agent baru tanpa restart PlutoClaw.
        Instance key = "{agent_type}__{camera_id}" sehingga agent yang sama
        can run on multiple cameras at once (stacking).
        """
        from agents import AGENT_REGISTRY
        agent_type = body.get("agent_id", "").strip()
        camera_id  = body.get("camera_id", "").strip()

        if not agent_type:
            raise HTTPException(status_code=400, detail="agent_id wajib")

        # Cari class
        AgentClass = AGENT_REGISTRY.get(agent_type)
        if not AgentClass:
            return {"ok": False, "reason": f"Agent '{agent_type}' not found in registry"}

        # Kamera — pakai yang dipilih atau default pertama
        if camera_id:
            camera = _camera_manager.get(camera_id)
        else:
            cams = list(_camera_manager.cameras.values()) if _camera_manager else []
            camera = cams[0] if cams else None

        if not camera:
            return {"ok": False, "reason": "No cameras available"}

        # Instance key unik per (agent_type, camera) → bisa stack banyak agent di 1 kamera
        instance_key = f"{agent_type}__{camera.camera_id}"

        # Sudah running di kamera yang sama?
        if instance_key in _agents and _agents[instance_key].running:
            return {"ok": False, "reason": f"Agent '{agent_type}' sudah running di kamera '{camera.camera_id}'"}

        # Bangun config agent (minimal)
        agent_cfg = dict(_config.get("agents", {}).get(agent_type, {}))
        agent_cfg["camera"] = camera.camera_id

        try:
            agent = AgentClass(
                name=instance_key,          # nama instance unik
                config=agent_cfg,
                camera=camera,
                detector=_detector,
                llm=_llm,
                alert=_alert,
                storage=_storage
            )
            agent.start()
            _agents[instance_key] = agent
            logger.info(f"[Dashboard] Hot-started: {instance_key}")
            return {
                "ok": True,
                "instance_key": instance_key,
                "agent": agent_type,
                "camera": camera.camera_id,
                "status": "started"
            }
        except Exception as e:
            logger.error(f"[Dashboard] Failed to start agent {agent_type}: {e}")
            return {"ok": False, "reason": str(e)}

    @app.post("/api/agents/stop")
    async def stop_agent(body: dict):
        """
        Hentikan satu instance agent.
        Terima 'instance_key' (misal 'ppe_guard__cam_0') ATAU kombinasi
        'agent_id' + 'camera_id' untuk backward-compatibility.
        """
        # Dukung dua cara kirim key
        instance_key = body.get("instance_key", "").strip()
        if not instance_key:
            agent_type = body.get("agent_id", "").strip()
            camera_id  = body.get("camera_id", "").strip()
            if agent_type and camera_id:
                instance_key = f"{agent_type}__{camera_id}"
            elif agent_type:
                # fallback: cari instance pertama yg match agent_type
                for k in list(_agents.keys()):
                    if k.startswith(f"{agent_type}__"):
                        instance_key = k
                        break

        if not instance_key:
            raise HTTPException(status_code=400, detail="instance_key or agent_id+camera_id required")

        if instance_key not in _agents:
            return {"ok": False, "reason": f"Instance '{instance_key}' not found"}

        try:
            _agents[instance_key].stop()
            del _agents[instance_key]
            logger.info(f"[Dashboard] Stopped: {instance_key}")
            return {"ok": True, "instance_key": instance_key, "status": "stopped"}
        except Exception as e:
            logger.error(f"[Dashboard] Failed to stop {instance_key}: {e}")
            return {"ok": False, "reason": str(e)}

    # ── WhatsApp Config API ──────────────────────────────────────────────────
    @app.get("/api/wa/config")
    async def get_wa_config():
        """Baca konfigurasi WhatsApp dari config.yaml"""
        try:
            cfg = _read_config_yaml()
            wa  = cfg.get("whatsapp", {})
            # Konversi flat list nomor → format {number, label, agents}
            raw_numbers = wa.get("alert_numbers", [])
            recipients  = wa.get("recipients", [])  # format baru dengan label & filter agent

            # Already using the new format, return directly
            if recipients:
                numbers = recipients
            else:
                # Migrasi dari format lama (plain list of strings)
                numbers = [{"number": n, "label": "", "agents": ["all"]} for n in raw_numbers]

            return {
                "ok": True,
                "enabled": wa.get("enabled", False),
                "numbers": numbers
            }
        except Exception as e:
            return {"ok": False, "reason": str(e), "enabled": False, "numbers": []}

    @app.post("/api/wa/config")
    async def save_wa_config(body: dict):
        """
        Simpan konfigurasi WhatsApp ke config.yaml.
        Body: { enabled: bool, numbers: [{number, label, agents}] }
        """
        try:
            cfg = _read_config_yaml()

            enabled = body.get("enabled", False)
            numbers = body.get("numbers", [])

            # Validasi nomor — hanya simpan yang tidak kosong
            clean = []
            for n in numbers:
                num = str(n.get("number", "")).strip()
                if num:
                    clean.append({
                        "number": num,
                        "label":  str(n.get("label", "")).strip(),
                        "agents": n.get("agents", ["all"])
                    })

            # Update section whatsapp di config
            if "whatsapp" not in cfg:
                cfg["whatsapp"] = {}
            cfg["whatsapp"]["enabled"]    = enabled
            cfg["whatsapp"]["recipients"] = clean
            # Sync alert_numbers (flat) untuk backward compat dengan AlertManager
            cfg["whatsapp"]["alert_numbers"] = [n["number"] for n in clean]

            _write_config_yaml(cfg)

            # Update AlertManager runtime jika ada
            if _alert:
                _alert.wa_enabled    = enabled
                _alert.alert_numbers = [n["number"] for n in clean]

            logger.info(f"[WA Config] Saved: enabled={enabled}, {len(clean)} recipients")
            return {"ok": True, "saved": len(clean), "enabled": enabled}
        except Exception as e:
            logger.error(f"[WA Config] Error: {e}")
            return {"ok": False, "reason": str(e)}

    @app.get("/api/wa/status")
    async def wa_status():
        """Cek status koneksi WA Bridge secara real-time"""
        connected = _check_wa_bridge()
        return {"connected": connected, "bridge_url": "http://localhost:3001"}

    @app.post("/api/wa/test")
    async def wa_test(body: dict):
        """Send a WA test message to a specific number"""
        number = body.get("number", "").strip()
        if not number:
            return {"ok": False, "reason": "Phone number is required"}
        try:
            import requests as req
            r = req.post("http://localhost:3001/send", json={
                "number":  number,
                "message": "✅ *PlutoClaw Test*\nKoneksi WhatsApp alert berfungsi dengan baik! 🎉"
            }, timeout=10)
            res = r.json()
            return {"ok": res.get("ok", False), "detail": res}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    @app.get("/api/setup/scan")
    async def setup_scan():
        """Hardware & software QC scan untuk Doctor page"""
        import sys
        import shutil
        from core.platform import get_platform, has_hailo, has_gpio

        env = get_platform()
        results = {}

        # Helper: buat result entry dengan severity eksplisit
        # severity: "ok" | "warn" | "fail"
        def ok(value, detail):
            return {"ok": True,  "severity": "ok",   "value": value, "detail": detail}
        def warn(value, detail):
            return {"ok": False, "severity": "warn",  "value": value, "detail": detail}
        def fail(value, detail):
            return {"ok": False, "severity": "fail",  "value": value, "detail": detail}

        # ── Platform (info only, selalu OK) ─────────────────────────────────
        results["platform"] = ok(env.upper(), f"Python {sys.version.split()[0]}")

        # ── Python version (KRITIS — tanpa ini PlutoClaw tidak bisa jalan) ──
        import sys as _sys
        py_ver = tuple(int(x) for x in _sys.version.split()[0].split(".")[:2])
        if py_ver >= (3, 10):
            results["python"] = ok(_sys.version.split()[0], "Python 3.10+ terpenuhi")
        else:
            results["python"] = fail(_sys.version.split()[0], "Requires Python 3.10+, upgrade needed")

        # ── Ollama (WARN — LLM optional; without it, alerts use template only) ─
        llm_cfg = _config.get("llm", {})
        ollama_ok = False
        ollama_model = llm_cfg.get("model", "plutoedge")
        try:
            import requests
            r = requests.get(
                f"{llm_cfg.get('host', 'http://localhost:11434')}/api/tags",
                timeout=2
            )
            if r.status_code == 200:
                ollama_ok = True
                # Cek apakah model target tersedia
                models = [m.get("name","") for m in r.json().get("models", [])]
                model_found = any(ollama_model in m for m in models)
                if not model_found:
                    results["ollama"] = warn(
                        "MODEL MISSING",
                        f"{ollama_model} not pulled yet. Run: ollama pull {ollama_model}"
                    )
                    ollama_ok = False
                else:
                    results["ollama"] = ok("OK", f"Model {ollama_model} available")
        except Exception:
            pass
        if not ollama_ok and "ollama" not in results:
            results["ollama"] = warn(
                "OFFLINE",
                "Ollama is not running. Alerts still work via template without AI."
            )

        # ── YOLO model (KRITIS — vision agent tidak bisa jalan tanpa ini) ───
        import os
        yolo_exists = os.path.exists("models/yolov8n.pt") or os.path.exists("yolov8n.pt")
        if yolo_exists:
            results["yolo"] = ok("OK", "yolov8n.pt ditemukan")
        else:
            results["yolo"] = fail(
                "MISSING",
                "yolov8n.pt not found. Download: yolo export model=yolov8n.pt"
            )

        # ── Cameras (WARN jika 0 connected — mungkin permission/belum dipasang) ─
        cam_statuses = _camera_manager.get_all_status() if _camera_manager else []
        cam_on  = sum(1 for c in cam_statuses if c.get("connected"))
        cam_tot = len(cam_statuses)
        if cam_on == cam_tot and cam_tot > 0:
            results["cameras"] = ok(f"{cam_on}/{cam_tot}", "All cameras connected")
        elif cam_on > 0:
            results["cameras"] = warn(
                f"{cam_on}/{cam_tot}",
                f"{cam_tot - cam_on} camera(s) not connected — check cable/URL"
            )
        elif cam_tot == 0:
            results["cameras"] = warn("0 registered", "No cameras configured in config.yaml")
        else:
            results["cameras"] = warn(
                f"0/{cam_tot}",
                "Camera not connected. On Mac: check camera permission in System Settings."
            )

        # ── WA Bridge (WARN — alert fallback ke log jika offline) ───────────
        wa_ok = _check_wa_bridge()
        if wa_ok:
            results["wa_bridge"] = ok("OK", "WA Bridge connected & ready to send alerts")
        else:
            results["wa_bridge"] = warn(
                "OFFLINE",
                "WA Alert not active. Run: cd wa_bridge && node server.js"
            )

        # ── Storage (KRITIS — tanpa DB event tidak tersimpan) ───────────────
        db_ok = _storage is not None
        if db_ok:
            results["storage"] = ok("OK", "SQLite database ready")
        else:
            results["storage"] = fail("FAIL", "Storage not initialized — check data/ folder")

        # ── GPIO (N/A di Mac = OK, WARN di Pi jika tidak tersedia) ──────────
        gpio_avail = has_gpio()
        if gpio_avail:
            results["gpio"] = ok("OK", "GPIO available, sensors can be read")
        elif env == "mac":
            results["gpio"] = ok("N/A", "GPIO not available on Mac — normal for development")
        else:
            results["gpio"] = warn("NOT DETECTED", "GPIO Pi not accessible — check user group 'gpio'")

        # ── Hailo NPU (WARN jika none — YOLO CPU fallback tersedia) ────
        hailo_avail = has_hailo()
        if hailo_avail:
            results["hailo"] = ok("OK", "Hailo-8L NPU aktif — inferensi dipercepat")
        elif env == "mac":
            results["hailo"] = ok("N/A", "Hailo not available on Mac — normal for development")
        else:
            results["hailo"] = warn(
                "TIDAK ADA",
                "Inferensi pakai CPU (lebih lambat). Pasang Hailo AI HAT+ untuk performa optimal."
            )

        # ── Network (WARN — offline bisa jalan tapi fitur cloud terbatas) ───
        net_ok = False
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            net_ok = True
        except Exception:
            pass
        if net_ok:
            results["network"] = ok("OK", "Internet available")
        else:
            results["network"] = warn(
                "OFFLINE",
                "No internet. PlutoClaw still runs locally, but model updates & remote access are limited."
            )

        return results

    # ── LLM Config API ──────────────────────────────────────────────────────
    @app.get("/api/llm/config")
    async def get_llm_config():
        """Baca konfigurasi LLM dari config.yaml"""
        try:
            cfg = _read_config_yaml()
            llm = cfg.get("llm", {})
            # Ambil list model yang tersedia dari Ollama
            available = []
            try:
                import requests as req
                r = req.get(f"{llm.get('host', 'http://localhost:11434')}/api/tags", timeout=2)
                if r.status_code == 200:
                    available = [m["name"] for m in r.json().get("models", [])]
            except Exception:
                pass
            return {
                "ok": True,
                "model":     llm.get("model", "plutoedge"),
                "host":      llm.get("host", "http://localhost:11434"),
                "enabled":   llm.get("enabled", True),
                "language":  llm.get("language", "indonesia"),
                "available": available
            }
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    @app.post("/api/llm/config")
    async def save_llm_config(body: dict):
        """
        Simpan konfigurasi LLM ke config.yaml dan update runtime.
        Body: { model, host, enabled, language }
        """
        try:
            cfg = _read_config_yaml()
            if "llm" not in cfg:
                cfg["llm"] = {}
            if "model" in body:
                cfg["llm"]["model"] = str(body["model"]).strip()
            if "host" in body:
                cfg["llm"]["host"] = str(body["host"]).strip()
            if "enabled" in body:
                cfg["llm"]["enabled"] = bool(body["enabled"])
            if "language" in body:
                cfg["llm"]["language"] = str(body["language"]).strip()
            _write_config_yaml(cfg)

            # Update runtime LLMConnector
            if _llm:
                _llm.model   = cfg["llm"].get("model", _llm.model)
                _llm.host    = cfg["llm"].get("host",  _llm.host)
                # Re-check ketersediaan model baru
                _llm.check()

            # Sync ke _config dict agar endpoint lain ikut pakai model baru
            _config["llm"] = cfg["llm"]

            logger.info(f"[LLM Config] Saved: model={cfg['llm'].get('model')}")
            return {"ok": True, "llm": cfg["llm"]}
        except Exception as e:
            logger.error(f"[LLM Config] Error: {e}")
            return {"ok": False, "reason": str(e)}

    # ── Inventory API ────────────────────────────────────────────────────
    @app.get("/api/inventory")
    async def inventory_list():
        """Get all inventory items"""
        items = _storage.inventory_get_all() if _storage else []
        low   = _storage.inventory_get_low_stock() if _storage else []
        low_ids = {i["item_id"] for i in low}
        for item in items:
            item["low_stock"] = item["item_id"] in low_ids
        return {"ok": True, "items": items, "low_count": len(low)}

    @app.post("/api/inventory")
    async def inventory_upsert(body: dict):
        """Add or update an inventory item"""
        item_id   = str(body.get("item_id", "")).strip()
        item_name = str(body.get("item_name", "")).strip()
        if not item_id or not item_name:
            return {"ok": False, "reason": "item_id dan item_name wajib"}
        _storage.inventory_upsert(
            item_id   = item_id,
            item_name = item_name,
            quantity  = float(body.get("quantity", 0)),
            unit      = str(body.get("unit", "pcs")),
            min_stock = float(body.get("min_stock", 0)),
            location  = str(body.get("location", ""))
        )
        return {"ok": True}

    @app.post("/api/inventory/{item_id}/adjust")
    async def inventory_adjust(item_id: str, body: dict):
        """Add/subtract item stock (delta can be negative)"""
        delta   = float(body.get("delta", 0))
        new_qty = _storage.inventory_adjust(item_id, delta)
        return {"ok": True, "item_id": item_id, "new_quantity": new_qty}

    @app.delete("/api/inventory/{item_id}")
    async def inventory_delete(item_id: str):
        """Hapus item dari inventory"""
        _storage.inventory_delete(item_id)
        return {"ok": True}

    # ── WA Incoming Message (dari wa_bridge → CS Agent) ──────────────────
    @app.post("/api/wa/incoming")
    async def wa_incoming(body: dict):
        """
        Terima pesan masuk dari WA Bridge (Baileys).
        wa_bridge/server.js POST ke sini saat ada pesan masuk.
        Body: { from, text, timestamp }
        Look for active 'wa_cs' agent to process, or fallback to auto-reply.
        """
        sender = body.get("from", "").strip()
        text   = body.get("text", "").strip()
        if not sender or not text:
            return {"ok": False, "reason": "from dan text wajib"}

        logger.info(f"[WA IN] {sender}: {text[:80]}")

        # Cari wa_cs agent yang sedang running
        cs_agent = None
        for ikey, agent in _agents.items():
            if ikey.startswith("wa_cs"):
                cs_agent = agent
                break

        if cs_agent and hasattr(cs_agent, "handle_message"):
            # Serahkan ke CS Agent
            reply = cs_agent.handle_message(sender, text)
        else:
            # Fallback auto-reply sederhana via LLM
            reply = None
            if _llm and _llm.available:
                prompt = f"""You are PlutoClaw's automatic assistant.
Reply briefly in English (max 2 sentences):
Pesan masuk: "{text}"
If no info is available, say the system is processing and ask the user to wait."""
                reply = _llm.generate(prompt, timeout=15)
            if not reply:
                reply = "✅ Pesan diterima. Tim akan segera merespons."

        # Send reply via WA Bridge
        if reply:
            try:
                import requests as req
                req.post("http://localhost:3001/send", json={
                    "number": sender,
                    "message": reply
                }, timeout=5)
            except Exception as e:
                logger.warning(f"[WA CS] Failed to send reply: {e}")

        return {"ok": True, "replied": bool(reply)}

    # ── Actuator API ────────────────────────────────────────────────────────
    @app.get("/api/actuators")
    async def actuators_list():
        """List all actuators and their current state"""
        if not _actuator_manager:
            return {"ok": True, "actuators": []}
        return {"ok": True, "actuators": _actuator_manager.get_all_info()}

    @app.post("/api/actuators/{act_id}/on")
    async def actuator_on(act_id: str):
        if not _actuator_manager:
            return {"ok": False, "reason": "ActuatorManager not available"}
        ok = _actuator_manager.turn_on(act_id)
        if not ok:
            return {"ok": False, "reason": f"Actuator '{act_id}' not found"}
        a = _actuator_manager.get(act_id)
        logger.info(f"[Dashboard] Actuator ON: {act_id}")
        return {"ok": True, "id": act_id, "state": True, "name": a.name}

    @app.post("/api/actuators/{act_id}/off")
    async def actuator_off(act_id: str):
        if not _actuator_manager:
            return {"ok": False, "reason": "ActuatorManager not available"}
        ok = _actuator_manager.turn_off(act_id)
        if not ok:
            return {"ok": False, "reason": f"Actuator '{act_id}' not found"}
        a = _actuator_manager.get(act_id)
        logger.info(f"[Dashboard] Actuator OFF: {act_id}")
        return {"ok": True, "id": act_id, "state": False, "name": a.name}

    @app.post("/api/actuators/{act_id}/toggle")
    async def actuator_toggle(act_id: str):
        if not _actuator_manager:
            return {"ok": False, "reason": "ActuatorManager not available"}
        ok = _actuator_manager.toggle(act_id)
        if not ok:
            return {"ok": False, "reason": f"Actuator '{act_id}' not found"}
        a = _actuator_manager.get(act_id)
        return {"ok": True, "id": act_id, "state": a.state, "name": a.name}

    @app.post("/api/actuators/{act_id}/pulse")
    async def actuator_pulse(act_id: str, body: dict = {}):
        """Nyalakan selama N detik lalu matikan otomatis"""
        duration = float(body.get("duration", 1.0))
        duration = max(0.1, min(duration, 30.0))   # clamp 0.1–30 detik
        if not _actuator_manager:
            return {"ok": False, "reason": "ActuatorManager not available"}
        ok = _actuator_manager.pulse(act_id, duration)
        if not ok:
            return {"ok": False, "reason": f"Actuator '{act_id}' not found"}
        a = _actuator_manager.get(act_id)
        logger.info(f"[Dashboard] Actuator PULSE: {act_id} {duration}s")
        return {"ok": True, "id": act_id, "duration": duration, "name": a.name}

    # ── Pluto Chat (conversation + automation mode) ───────────────────────────
    @app.post("/api/pluto/chat")
    async def pluto_chat_endpoint(body: dict):
        """
        Pluto AI — single endpoint untuk conversation dan automation.
        Otomatis inject real-time context skills + sensor + aktuator.
        Bisa eksekusi aksi nyata dan log ke dataset training Pluto-LM.

        Body: { message: str }
        Response: { reply: str, action: dict|null, action_result: dict }
        """
        message = body.get("message", "").strip()
        if not message:
            return {"reply": "Hello! I'm Pluto, PlutoClaw's AI orchestrator. How can I help you?"}

        if not _pluto_conv:
            return {"reply": "Pluto is not ready yet. Make sure the LLM is running."}

        result = _pluto_conv.chat(message)
        return {
            "reply":         result.get("reply", ""),
            "action":        result.get("action"),
            "action_result": result.get("action_result", {}),
            "model":         _config.get("llm", {}).get("model", "-"),
        }

    @app.post("/api/pluto/command")
    async def pluto_command_compat(body: dict):
        """Backward compat — redirect ke /api/pluto/chat"""
        return await pluto_chat_endpoint(body)

    @app.get("/api/pluto/dataset/stats")
    async def dataset_stats():
        """Statistik dataset training yang sudah terkumpul"""
        from core.dataset_logger import get_stats
        return get_stats()

    @app.get("/stream/{camera_id}")
    async def video_stream(camera_id: str):
        """MJPEG live stream per kamera"""
        def generate():
            cam = _camera_manager.get(camera_id) if _camera_manager else None
            import time
            while True:
                if cam:
                    jpeg = cam.get_jpeg_bytes()
                    if jpeg:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" +
                            jpeg + b"\r\n"
                        )
                time.sleep(0.05)

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace;boundary=frame"
        )

    return app


def _build_command_context() -> dict:
    """
    Build a real-time PlutoClaw state snapshot to inject into the system prompt.
    Mencakup: agents aktif, sensor readings, events terbaru, status WA.
    """
    # Agents
    agents_info = []
    for ikey, a in (_agents or {}).items():
        agents_info.append({
            "name":    ikey,
            "status":  a.status,
            "alerts":  a.alert_count,
            "running": a.running,
        })

    # Sensor readings dari config (Pi) atau placeholder (Mac)
    from core.platform import is_pi
    sensors_info = []
    for s in (_config or {}).get("sensors", []) or []:
        reading = _get_sensor_reading(s) if is_pi() else {"status": "simulation"}
        sensors_info.append({
            "id":      s.get("id"),
            "name":    s.get("name"),
            "type":    s.get("type"),
            "reading": reading,
        })

    # Recent events (5 terakhir)
    recent_events = []
    if _storage:
        try:
            rows = _storage.get_recent_events(limit=5)
            for row in rows:
                recent_events.append({
                    "agent":   row.get("agent_name", "?"),
                    "message": (row.get("message", "") or "")[:80],
                    "time":    row.get("created_at", ""),
                })
        except Exception:
            pass

    # WA status
    wa_connected = _check_wa_bridge()

    # Device info
    device_name = (_config or {}).get("plutoclaw", {}).get("device_name", "PlutoClaw")
    usecase     = (_config or {}).get("plutoclaw", {}).get("usecase", "unknown")

    # Actuator states
    actuators_info = []
    if _actuator_manager:
        for a in _actuator_manager.all():
            actuators_info.append({
                "id":    a.id,
                "name":  a.name,
                "type":  a.type,
                "state": a.state,
            })

    return {
        "device":         device_name,
        "usecase":        usecase,
        "agents_active":  [a for a in agents_info if a["running"]],
        "agents_stopped": [a for a in agents_info if not a["running"]],
        "sensors":        sensors_info,
        "actuators":      actuators_info,
        "recent_events":  recent_events,
        "wa_connected":   wa_connected,
        "llm_model":      (_config or {}).get("llm", {}).get("model", "?"),
    }


def _build_command_system_prompt(ctx: dict) -> str:
    """
    Bangun system prompt operasional untuk Pluto Command Interface.
    Real-time context is injected here.
    """
    import json

    agents_active  = ctx.get("agents_active", [])
    agents_stopped = ctx.get("agents_stopped", [])
    sensors        = ctx.get("sensors", [])
    actuators      = ctx.get("actuators", [])
    recent_events  = ctx.get("recent_events", [])
    wa_connected   = ctx.get("wa_connected", False)

    active_str  = ", ".join(a["name"] for a in agents_active)  or "none"
    stopped_str = ", ".join(a["name"] for a in agents_stopped) or "none"

    sensor_str = ""
    for s in sensors:
        r = s.get("reading", {})
        if r.get("status") == "ok":
            sensor_str += f"\n  - {s['name']}: suhu {r.get('temperature')}°C, lembab {r.get('humidity')}%"
        else:
            sensor_str += f"\n  - {s['name']}: {r.get('status', 'unknown')}"
    sensor_str = sensor_str or "\n  - No sensors registered"

    actuator_str = ""
    for a in actuators:
        status = "🟢 ON" if a.get("state") else "⚪ OFF"
        actuator_str += f"\n  - {a['id']} ({a['name']}, {a['type']}): {status}"
    actuator_str = actuator_str or "\n  - No actuators registered"

    events_str = ""
    for ev in recent_events:
        events_str += f"\n  - [{ev['time'][:16]}] {ev['agent']}: {ev['message']}"
    events_str = events_str or "\n  - No events yet"

    return f"""You are **Pluto**, the operational AI assistant for the PlutoClaw Edge AI system.
PlutoClaw is a Raspberry Pi-based monitoring platform with cameras, IoT sensors, WhatsApp alerts, and actuator control.

=== CURRENT SYSTEM STATUS ===
Device       : {ctx.get('device')} | Usecase: {ctx.get('usecase')}
LLM Model    : {ctx.get('llm_model')}
WA Bridge    : {'✅ Connected' if wa_connected else '❌ Offline'}

ACTIVE Agents : {active_str}
STOPPED Agents: {stopped_str}

Registered Sensors:{sensor_str}

Actuators:{actuator_str}

Last 5 Events:{events_str}

=== YOUR CAPABILITIES ===
You can perform real actions by writing PLUTO_ACTION at the end of your message.

Action format (write EXACTLY like this, ONLY when user requests a real action):
PLUTO_ACTION: {{"type": "actuator_trigger", "params": {{"id": "relay1", "action": "on"}}}}

Available action types:
- start_agent      → params: agent_id, camera_id
- stop_agent       → params: instance_key (e.g. "ppe_guard__cam1")
- query_events     → params: limit (default 10), agent (optional)
- send_test_wa     → params: number, message (optional)
- actuator_trigger → params: id (relay1/relay2/buzzer1/led1), action (on/off/toggle/pulse), duration (seconds, for pulse)

RESPONSE GUIDELINES:
1. Reply in clear, concise English
2. Use the real-time data above when answering status questions
3. Include PLUTO_ACTION ONLY if the user requests an action (turn on/off/start/stop)
4. For informational questions — just answer without an action
5. If unsure — ask for confirmation before executing
6. Format numbers and status clearly (emojis are fine)
7. Do not fabricate sensor data — use the data above or say 'not available'"""


def _parse_pluto_action(raw_reply: str) -> tuple:
    """
    Parse PLUTO_ACTION from LLM response.

    Returns:
        (clean_reply, action_spec) — clean_reply without marker, action_spec dict or None
    """
    import re, json

    marker = "PLUTO_ACTION:"
    if marker not in raw_reply:
        return raw_reply.strip(), None

    parts = raw_reply.split(marker, 1)
    clean = parts[0].strip()
    raw_action = parts[1].strip()

    # Ambil JSON (sampai newline atau akhir string)
    json_str = raw_action.split("\n")[0].strip()
    try:
        action_spec = json.loads(json_str)
        return clean, action_spec
    except Exception:
        logger.warning(f"[Pluto] Failed to parse action JSON: {json_str}")
        return raw_reply.strip(), None


async def _execute_pluto_action(action_spec: dict) -> dict:
    """
    Eksekusi action yang diminta LLM.
    Return dict dengan hasil eksekusi.
    """
    import requests as req

    action_type = action_spec.get("type", "")
    params      = action_spec.get("params", {})

    try:
        if action_type == "start_agent":
            agent_id  = params.get("agent_id", "")
            camera_id = params.get("camera_id", "")

            from agents import AGENT_REGISTRY
            AgentClass = AGENT_REGISTRY.get(agent_id)
            if not AgentClass:
                return {"ok": False, "type": action_type, "reason": f"Agent '{agent_id}' none"}

            camera = _camera_manager.get(camera_id) if camera_id and _camera_manager else None
            if not camera and camera_id:
                # Coba ambil kamera pertama yang tersedia
                cams = list(_camera_manager.cameras.values()) if _camera_manager else []
                camera = cams[0] if cams else None

            # Sensor-only agent tidak butuh kamera
            instance_key = f"{agent_id}__{camera.camera_id}" if camera else f"{agent_id}__sensor"
            if instance_key in _agents and _agents[instance_key].running:
                return {"ok": False, "type": action_type, "reason": f"Agent '{agent_id}' is already running"}

            agent_cfg = dict((_config.get("agents", {}) or {}).get(agent_id, {}))
            if camera:
                agent_cfg["camera"] = camera.camera_id

            agent = AgentClass(
                name=instance_key, config=agent_cfg, camera=camera,
                detector=_detector, llm=_llm, alert=_alert, storage=_storage
            )
            agent.start()
            _agents[instance_key] = agent
            logger.info(f"[Pluto CMD] Started: {instance_key}")
            return {"ok": True, "type": action_type, "instance_key": instance_key, "msg": f"Agent {agent_id} started successfully"}

        elif action_type == "stop_agent":
            instance_key = params.get("instance_key", "")
            if not instance_key:
                # Coba match dari agent_id
                agent_id = params.get("agent_id", "")
                for k in list(_agents.keys()):
                    if k.startswith(f"{agent_id}__"):
                        instance_key = k
                        break

            if not instance_key or instance_key not in _agents:
                return {"ok": False, "type": action_type, "reason": f"Instance '{instance_key}' not found"}

            _agents[instance_key].stop()
            del _agents[instance_key]
            logger.info(f"[Pluto CMD] Stopped: {instance_key}")
            return {"ok": True, "type": action_type, "msg": f"Agent {instance_key} dihentikan"}

        elif action_type == "query_events":
            limit = int(params.get("limit", 10))
            agent = params.get("agent")
            rows  = _storage.get_recent_events(limit=limit, agent=agent) if _storage else []
            return {"ok": True, "type": action_type, "events": rows, "count": len(rows)}

        elif action_type == "actuator_trigger":
            act_id  = params.get("id", "")
            command = params.get("action", "toggle")   # on | off | toggle | pulse
            duration = float(params.get("duration", 1.0))

            if not _actuator_manager:
                return {"ok": False, "type": action_type, "reason": "ActuatorManager not available"}

            a = _actuator_manager.get(act_id)
            if not a:
                ids = [x.id for x in _actuator_manager.all()]
                return {"ok": False, "type": action_type,
                        "reason": f"Actuator '{act_id}' not found. Tersedia: {ids}"}

            if command == "on":
                a.turn_on()
            elif command == "off":
                a.turn_off()
            elif command == "pulse":
                a.pulse(duration)
            else:
                a.toggle()

            logger.info(f"[Pluto CMD] Actuator {command}: {act_id}")
            return {
                "ok":    True,
                "type":  action_type,
                "id":    act_id,
                "name":  a.name,
                "state": a.state,
                "msg":   f"{'🟢' if a.state else '⚪'} {a.name} → {'ON' if a.state else 'OFF'}"
            }

        elif action_type == "send_test_wa":
            number  = params.get("number", "")
            message = params.get("message", "✅ *PlutoClaw Test*\nPesan dari Pluto AI Command Interface.")
            if not number:
                return {"ok": False, "type": action_type, "reason": "Phone number not provided"}
            r = req.post("http://localhost:3001/send",
                         json={"number": number, "message": message}, timeout=10)
            res = r.json()
            return {"ok": res.get("ok", False), "type": action_type, "detail": res}

        else:
            return {"ok": False, "type": action_type, "reason": f"Unknown action type '{action_type}'"}

    except Exception as e:
        logger.error(f"[Pluto CMD] Error eksekusi {action_type}: {e}")
        return {"ok": False, "type": action_type, "reason": str(e)}


def _get_device_capacity(env: str, hailo: bool) -> dict:
    """Estimate device capacity based on platform"""
    if env == "mac":
        return {
            "max_cameras": 2,
            "max_sensors": 0,
            "max_agents": 4,
            "device_type": "Mac (Development)",
            "notes": "USB cameras only. No GPIO sensor support on Mac.",
            "camera_types": ["USB Webcam", "RTSP IP Camera"],
            "sensor_types": [],
        }
    elif env == "pi":
        import platform as _plat
        machine = _plat.machine().lower()
        # Pi 5 biasanya aarch64, kita cek juga memori
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo = f.read()
            is_pi5 = "Raspberry Pi 5" in cpuinfo or "BCM2712" in cpuinfo
        except Exception:
            is_pi5 = False

        if is_pi5:
            return {
                "max_cameras": 6,
                "max_sensors": 10,
                "max_agents": 8,
                "device_type": "Raspberry Pi 5",
                "notes": "2x CSI + 4x USB cameras. 10 GPIO sensor slots. Hailo NPU available.",
                "camera_types": ["USB Webcam", "CSI Camera", "RTSP IP Camera"],
                "sensor_types": ["DHT22", "MQ135", "Soil Moisture", "PIR Motion", "DS18B20", "HC-SR04"],
            }
        else:
            return {
                "max_cameras": 4,
                "max_sensors": 8,
                "max_agents": 5,
                "device_type": "Raspberry Pi 4",
                "notes": "1x CSI + 3x USB cameras. 8 GPIO sensor slots.",
                "camera_types": ["USB Webcam", "CSI Camera", "RTSP IP Camera"],
                "sensor_types": ["DHT22", "MQ135", "Soil Moisture", "PIR Motion", "DS18B20"],
            }
    else:
        return {
            "max_cameras": 4,
            "max_sensors": 4,
            "max_agents": 6,
            "device_type": "Linux Server",
            "notes": "USB/IP cameras. GPIO availability depends on hardware.",
            "camera_types": ["USB Webcam", "RTSP IP Camera"],
            "sensor_types": ["DHT22", "MQ135"],
        }


def _get_sensor_reading(sensor_cfg: dict) -> dict:
    """Try to read sensor value in real-time (Pi) or return None (Mac)"""
    from core.platform import is_pi, has_gpio
    sensor_type = sensor_cfg.get("type", "").upper()
    pin = sensor_cfg.get("pin")

    if not is_pi() or not has_gpio():
        return {"value": None, "unit": "", "status": "gpio_unavailable"}

    try:
        if sensor_type == "DHT22":
            import adafruit_dht, board
            pin_map = {4: board.D4, 17: board.D17, 27: board.D27, 22: board.D22}
            dht = adafruit_dht.DHT22(pin_map.get(pin, board.D4), use_pulseio=False)
            temperature = dht.temperature
            humidity = dht.humidity
            dht.exit()
            if temperature is not None:
                return {"temperature": round(temperature, 1), "humidity": round(humidity, 1),
                        "unit": "°C / %RH", "status": "ok"}
            return {"value": None, "unit": "", "status": "read_error"}
        elif sensor_type == "MQ135":
            # Analog read via ADC (placeholder)
            return {"value": None, "unit": "ppm", "status": "adc_required"}
        else:
            return {"value": None, "unit": "", "status": "unknown_type"}
    except Exception as e:
        return {"value": None, "unit": "", "status": f"error: {str(e)[:30]}"}


def _check_wa_bridge() -> bool:
    """Check if WA Bridge (Node.js) is running"""
    try:
        import requests
        r = requests.get("http://localhost:3001/status", timeout=1)
        data = r.json()
        return data.get("connected", False)
    except Exception:
        return False


def _read_config_yaml() -> dict:
    """Baca config.yaml dan return sebagai dict"""
    import yaml
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def _write_config_yaml(data: dict):
    """Tulis dict ke config.yaml dengan format yang rapi"""
    import yaml
    config_path = "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
