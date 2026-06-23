<p align="center">
  <img src="assets/logo.png" alt="PlutoClaw Logo" width="180" />
</p>

<h1 align="center">PlutoClaw</h1>

<p align="center">
  <strong>Edge AI orchestrator for IoT & hardware automation — runs entirely on Raspberry Pi, no cloud required.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-teal.svg" alt="MIT License"/></a>
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/Runs%20on-Raspberry%20Pi-C51A4A.svg" alt="Runs on Pi"/>
  <img src="https://img.shields.io/badge/LLM-PlutoEdge--1.5B-8A2BE2.svg" alt="PlutoEdge-1.5B"/>
  <img src="https://img.shields.io/badge/Offline-100%25-brightgreen.svg" alt="100% Offline"/>
  <img src="https://img.shields.io/badge/Skills-21-orange.svg" alt="21 Skills"/>
</p>

<p align="center">
  <code>Sensors & Cameras → Skills → Pluto AI → Actuators & Alerts</code>
</p>

---

## What is PlutoClaw?

PlutoClaw puts an **AI brain on your Raspberry Pi**. It monitors the physical world through sensors and cameras, reasons with a local LLM, and acts autonomously — controlling relays, sending WhatsApp alerts, and adapting to conditions — all **without internet or cloud**.

It ships with **PlutoEdge-1.5B**, a domain-specific LLM fine-tuned for IoT edge automation, running via Ollama at ~37s inference on Pi 4B CPU.

> Think of it as an always-on AI operator for your facility: it watches, thinks, and acts — even at 2am, even with no internet.

---

## Table of Contents

- [Features](#features)
- [Skills](#skills--industry-categories)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [PlutoEdge AI Model](#plutoedge-ai-model)
- [Hardware](#supported-hardware)
- [Configuration](#configuration)
- [Writing a Custom Skill](#writing-a-custom-skill)
- [Dashboard](#dashboard)
- [WhatsApp Alerts](#whatsapp-alerts)
- [Contributing](#contributing)

---

## Features

| Feature | Details |
|---|---|
| **100% Offline** | No cloud, no API keys — LLM runs locally via Ollama |
| **PlutoEdge-1.5B** | Domain-specific fine-tuned model for IoT commands & Q&A |
| **21 Built-in Skills** | PPE detection, coop monitor, cold chain, carbon footprint, and more |
| **GPIO Control** | Relay, buzzer, LED directly from skill logic |
| **Camera Vision** | USB webcam / Pi Camera / RTSP IP cam support |
| **WhatsApp Alerts** | Real-time notifications via wa-bridge |
| **Chat + Automation** | Chat with Pluto and let it monitor autonomously in background |
| **Knowledge Base** | Skill reference injected into LLM context for accurate Q&A |
| **Dataset Logging** | Every interaction auto-saved to `data/chat_dataset.jsonl` for future training |
| **Web Dashboard** | Local FastAPI UI — chat, manage skills, view live sensor data |

---

## Skills — Industry Categories

PlutoClaw ships with **21 skills** across 7 industry verticals:

| Category | Skills | Use Case |
|---|---|---|
| 🔒 **Security & Surveillance** | `ppe_guard`, `intrusion`, `forklift_guard` | Detect PPE violations, unauthorized access, forklift collision risk |
| 🌱 **Agriculture & Farming** | `coop_monitor`, `sick_animal`, `animal_count`, `crop_monitor`, `irrigation_control`, `livestock_monitor` | Greenhouse temp/humidity, sick animal detection, automated irrigation |
| 📦 **Logistics & Cold Chain** | `cold_chain_monitor`, `vehicle_detection` | Storage temperature monitoring, loading dock vehicle tracking |
| ⚙️ **Industrial & Machinery** | `predictive_maintenance`, `quality_control`, `energy_monitor` | Vibration anomaly detection, visual QC, power consumption tracking |
| 🏥 **Healthcare (non-critical)** | `patient_vitals`, `air_quality` | Ambient environment monitoring for patient rooms |
| 🏠 **Smart Home & IoT** | `smart_home_control`, `flood_detector`, `fire_smoke_detector` | Presence-based automation, water leak and smoke alerts |
| 🌍 **Sustainability & Energy** | `carbon_footprint_monitor`, `renewable_energy_optimizer`, `emission_sensor_monitor`, `water_footprint_monitor`, `smart_grid_scheduler` | CO₂ tracking, solar/grid switching, water footprint |

---

## Architecture

```
plutoclaw/
├── main.py                      # entry point — wires everything together
├── config.yaml                  # hardware & skill configuration
├── knowledge/
│   ├── knowledge_base.md        # full skill reference (Mac/server)
│   └── knowledge_base_compact.md # compressed version for Pi (fits 1024 ctx)
├── skills/
│   ├── base_skill.py            # BaseSkill interface
│   ├── builtin/                 # 21 built-in skills
│   └── __init__.py              # SKILL_REGISTRY + SKILL_CATEGORIES
├── pluto/
│   ├── conversation.py          # ConversationHandler — chat with Pluto
│   ├── automation.py            # AutomationHandler — autonomous background monitoring
│   ├── context_builder.py       # injects KB + live device state into LLM prompt
│   └── action_parser.py         # parses PLUTO_ACTION JSON from LLM responses
├── core/
│   ├── llm.py                   # LLM connector (Ollama)
│   ├── actuator.py              # relay, buzzer, LED GPIO control
│   ├── camera.py                # camera manager (USB / CSI / RTSP)
│   ├── alert.py                 # WhatsApp alerts via wa-bridge
│   ├── dataset_logger.py        # auto-saves interactions for LLM training
│   └── platform.py              # Pi vs Mac detection, GPIO simulation
├── dashboard/
│   ├── app.py                   # FastAPI REST backend
│   └── index.html               # single-file web UI
└── models/
    └── PlutoEdge-1.5B-v3/       # domain-specific LLM (Modelfile + GGUF)
```

### How it works

```
┌──────────────┐    ┌───────────────┐    ┌────────────────────┐
│   Sensors    │───▶│    Skills     │───▶│   Pluto (LLM)      │
│   Cameras    │    │  (21 built-in)│    │  PlutoEdge-1.5B    │
└──────────────┘    └───────────────┘    └────────────────────┘
                                                  │
                    ┌─────────────────────────────┼────────────────┐
                    ▼                             ▼                ▼
             ┌────────────┐              ┌─────────────┐  ┌──────────────┐
             │  Actuators │              │  WhatsApp   │  │  Dashboard   │
             │relay/buzzer│              │   Alerts    │  │  localhost   │
             │    LED     │              └─────────────┘  │    :8080     │
             └────────────┘                               └──────────────┘
```

---

## Quickstart

### Requirements

- Raspberry Pi 4B / 5 (or any Linux/Mac for development)
- Python 3.10+
- [Ollama](https://ollama.ai) installed

### 1. Clone & install

```bash
git clone https://github.com/plutoedge-dev/plutoclaw.git
cd plutoclaw
pip install -r requirements.txt
```

### 2. Install the PlutoEdge AI model

```bash
# Pull base model first
ollama pull qwen2.5:1.5b

# Register PlutoEdge-1.5B (domain-tuned for PlutoClaw)
cd models/PlutoEdge-1.5B-v3
ollama create plutoedge -f Modelfile
```

> **No GPU needed.** PlutoEdge-1.5B runs on Pi 4B CPU in ~37s. For faster inference, use Pi 5 (~18s) or add a Hailo-8 NPU.

### 3. Configure

Edit `config.yaml` to match your hardware:

```yaml
plutoclaw:
  device_name: "MyDevice"
  domain: farming           # farming | warehouse | home | general

llm:
  model: "plutoedge"        # uses PlutoEdge-1.5B via Ollama
  language: "english"

actuators:
  - id: relay1
    type: relay
    pin: 18                 # GPIO 18
    name: "Ventilation Fan"

skills:
  coop_monitor:
    enabled: true
    gpio_pin: 4             # DHT22 DATA pin
    temp_max: 35.0
    hum_max: 90.0
```

### 4. Run

```bash
python3 main.py
```

Dashboard opens at **[http://localhost:8080](http://localhost:8080)**

---

## PlutoEdge AI Model

PlutoClaw uses **PlutoEdge-1.5B** — a fine-tuned version of Qwen2.5-1.5B-Instruct, trained on:

- IoT device command patterns (`turn on relay1`, `activate buzzer`, etc.)
- Domain knowledge Q&A (skills by industry, hardware setup, troubleshooting)
- Sensor reading interpretation (temperature alerts, humidity thresholds)
- Multi-actuator orchestration (trigger relay + buzzer + alert simultaneously)

| Spec | Value |
|---|---|
| Base model | Qwen2.5-1.5B-Instruct |
| Fine-tuning | MLX LoRA (rank=16, 1200 iters) |
| Format | GGUF Q4_K_M |
| Size | 940 MB |
| Pi 4B inference | ~37s |
| Pi 5 inference | ~18s |
| Context window | 1024 tokens (Pi) / 2048 tokens (Mac) |

### Prompt Architecture

PlutoEdge uses a two-mode prompt system:

- **Knowledge mode** — injects `knowledge_base_compact.md` (432 tokens) for accurate skill Q&A
- **Control mode** — injects live device state for precise actuator commands

```
User: "Nyalakan kipas angin"
Pluto: "Turning on the ventilation fan."
       PLUTO_ACTION: {"type": "actuator_trigger", "params": {"id": "relay1", "action": "on"}}
```

```
User: "What skills should I use for a warehouse?"
Pluto: "For warehouse operations, use:
        - ppe_guard: detects workers without PPE
        - intrusion: detects unauthorized access outside active_hours
        - forklift_guard: detects forklift near workers (collision risk)"
```

---

## Supported Hardware

| Component | Supported Models |
|---|---|
| **SBC** | Raspberry Pi 4B (4GB+), Pi 5, Zero 2W |
| **AI Accelerator** | Hailo-8 NPU (Pi AI Kit) |
| **Temperature/Humidity** | DHT22, DS18B20 |
| **Gas / Air Quality** | MQ-2, MQ-4, MQ-135, MH-Z19B (CO₂) |
| **Power Meter** | PZEM-004T (AC mains), INA219 (DC) |
| **Flow Sensor** | YF-S201 (water consumption) |
| **Camera** | USB webcam, Pi Camera v3, IP cam (RTSP) |
| **Actuators** | Relay module (4-channel), buzzer, LED (GPIO) |
| **Medical (env)** | MAX30102 (pulse ox), MLX90614 (IR thermometer) |

### Default GPIO Pinout

| Device | GPIO | Physical Pin |
|---|---|---|
| relay1 (fan) | GPIO 18 | Pin 12 |
| relay2 (pump) | GPIO 23 | Pin 16 |
| relay3 (light) | GPIO 27 | Pin 13 |
| relay4 | GPIO 22 | Pin 15 |
| buzzer1 | GPIO 24 | Pin 18 |
| led1 | GPIO 25 | Pin 22 |
| DHT22 data | GPIO 4 | Pin 7 |
| Soil moisture DO | GPIO 17 | Pin 11 |

---

## Configuration

Full `config.yaml` reference:

```yaml
plutoclaw:
  device_name: "MyPlutoClaw"
  domain: farming             # farming | warehouse | home | general

pluto:
  automation_enabled: false   # true = autonomous background monitoring
  automation_interval: 60     # check every N seconds

llm:
  provider: ollama
  model: "plutoedge"          # PlutoEdge-1.5B (recommended) or qwen2.5:1.5b
  host: "http://localhost:11434"
  language: "english"         # response language

whatsapp:
  enabled: true
  alert_numbers:
    - "628XXXXXXXXXX"         # international format

cameras:
  - id: cam1
    source: 0                 # 0 = USB webcam, or "rtsp://user:pass@ip/stream"

sensors:
  - id: dht1
    type: DHT22
    pin: 4

skills:
  coop_monitor:
    enabled: true
    gpio_pin: 4
    temp_max: 35.0
    temp_min: 15.0
    hum_max: 90.0
    hum_min: 30.0
    cooldown_seconds: 300

  ppe_guard:
    enabled: false
    camera: cam1
    confidence: 0.5
    cooldown_seconds: 30

  intrusion:
    enabled: false
    camera: cam1
    active_hours: "20:00-06:00"
    cooldown_seconds: 30
```

---

## Writing a Custom Skill

Extend `BaseSkill` to add your own skill:

```python
from skills.base_skill import BaseSkill

class MySkill(BaseSkill):
    name        = "my_skill"
    description = "What this skill does — shown to Pluto as context"
    category    = "industrial"        # used in dashboard category filter
    requires    = ["sensor:DHT22"]    # hardware requirements (informational)

    def run_cycle(self):
        # called repeatedly every get_interval() seconds
        data = self._read_my_sensor()

        if data["value"] > self.config.get("threshold", 50) and self.can_alert():
            summary = f"Value is {data['value']} — above threshold"
            ok, reason = self.should_alert(summary)   # LLM filters false alarms
            if ok and self.alert:
                self.alert.send(f"⚠ {summary}", agent=self.name)
                self.mark_alerted()

    def get_status(self) -> dict:
        base = super().get_status()
        base["last_reading"] = self.last_reading
        return base
```

Register in `skills/__init__.py`:

```python
from skills.builtin.my_skill import MySkill

SKILL_REGISTRY = {
    ...
    "my_skill": MySkill,
}
```

---

## Dashboard

PlutoClaw includes a local web dashboard accessible at **http://\<pi-ip\>:8080**

- **Chat** — talk to Pluto in natural language (English or Bahasa Indonesia)
- **Skills** — view active/inactive skills with live sensor readings
- **Actuators** — manual control of all GPIO devices
- **Logs** — real-time event log

For remote access without port forwarding, use [Tailscale](https://tailscale.com):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

---

## WhatsApp Alerts

PlutoClaw sends alerts via [wa-bridge](https://github.com/plutoedge-dev/wa-bridge), a lightweight WhatsApp Web bridge.

Setup:
```bash
cd wa_bridge
npm install
node index.js    # scan QR code once — stays connected
```

Configure your number in `config.yaml`:
```yaml
whatsapp:
  enabled: true
  alert_numbers:
    - "628XXXXXXXXXX"    # format: 628 + your number (no leading 0)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Sensor reads null | Check GPIO wiring; DHT22 needs 10kΩ pull-up resistor on data pin |
| Slow LLM response | Normal on Pi 4B CPU (30–90s). Upgrade to Pi 5 for ~2× speed |
| Camera not found | Check `lsusb`; try `source: 0`, `1`, `2` in config; add user to `video` group |
| Ollama not running | Run `ollama serve` or `sudo systemctl start ollama` |
| Port 8080 in use | Kill existing process: `fuser -k 8080/tcp` |
| WhatsApp alert fails | Ensure wa-bridge is running on port 3000; use `628xxx` format |
| LCD display hijacked | Run `~/LCD-show/LCD-hdmi` to restore HDMI output |

---

## Contributing

Pull requests welcome! To contribute a new skill:

1. Fork the repo
2. Create `skills/builtin/your_skill.py` — extend `BaseSkill`
3. Register it in `skills/__init__.py`
4. Add it to `config.yaml` with default settings
5. Open a PR with a short description of the hardware it targets

---

## License

MIT © 2026 [Plutobot AI](https://plutobot.ai)

---

<p align="center">
  Built with 🐾 by <a href="https://plutobot.ai">Plutobot AI</a> · Jakarta, Indonesia
</p>
