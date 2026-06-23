PlutoClaw is an Edge AI platform on Raspberry Pi. Controls relays/sensors via GPIO, sends WhatsApp alerts, runs fully offline. Dashboard at http://<pi-ip>:8080. AI model: PlutoEdge-1.5B.

SKILLS FOR WAREHOUSE / GUDANG:
- ppe_guard: detects workers without PPE (hard hat, safety vest) via camera
- intrusion: detects people in restricted area outside working hours (set active_hours)
- forklift_guard: detects forklift near worker (collision risk) via camera

SKILLS FOR CHICKEN FARM / KANDANG AYAM / POULTRY:
- coop_monitor: reads DHT22 temperature + humidity + soil moisture, alerts on threshold breach
- sick_animal: detects abnormal chicken behavior (idle, drooping) via camera
- animal_count: counts flock size at intervals via camera

SKILLS FOR CROP FARMING / PERTANIAN SAYUR:
- coop_monitor: monitors greenhouse temperature, humidity, soil moisture
- disease_leaf: detects leaf disease (spots, yellowing) via camera
- pest_detect: detects insects and pests on plants via camera

SKILLS FOR COLD STORAGE / COLD CHAIN:
- cold_chain_monitor: monitors storage temperature, alerts if range breached

SKILLS FOR SUSTAINABILITY / ENERGY:
- carbon_footprint_monitor: tracks energy use and CO2 estimate
- renewable_energy_optimizer: switches solar/grid via relay automatically
- water_footprint_monitor: tracks water usage via flow meter

SKILLS FOR SMART HOME:
- presence_control: presence-based automation
- flood_detect: water leak detection
- fire_safety: smoke/fire detection, triggers alarm

GPIO DEFAULTS:
relay1=GPIO18 (fan), relay2=GPIO23 (pump), relay3=GPIO27 (light), relay4=GPIO22
buzzer1=GPIO24, led1=GPIO25, DHT22=GPIO4, soil moisture=GPIO17

SKILL CONFIG (config.yaml):
enabled: true | cooldown_seconds: 300 | confidence: 0.5
temp_max/min (°C) | hum_max/min (%) | active_hours: "20:00-06:00"

HARDWARE: Raspberry Pi 4B/5, USB webcam or RTSP camera (720p+), DHT22 sensor, relay module 4-channel, capacitive soil sensor

TROUBLESHOOT:
- Sensor null → check GPIO wiring, add 10kΩ pull-up to DHT22 data pin
- Slow response → normal on Pi 4B CPU (30-90s), upgrade to Pi 5 for 2x speed
- Camera not found → check lsusb, try source 0/1/2 in config.yaml
- Ollama down → run: ollama serve
- WhatsApp alert fail → check wa_bridge on port 3000, use format 628xxx
