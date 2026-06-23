# PlutoClaw Knowledge Base

## Platform
PlutoClaw is an open-source Edge AI platform running on Raspberry Pi. Monitors environments via cameras and IoT sensors, controls actuators via GPIO, sends alerts via WhatsApp. Fully offline after setup. Dashboard at http://<pi-ip>:8080. Model: PlutoEdge-1.5B (Qwen2.5 fine-tuned, 940MB Q4_K_M via Ollama).

## Skills by Domain

### Warehouse / Logistics
- `ppe_guard` — detects workers without PPE (hard hat, vest) via camera
- `intrusion` — detects people in restricted area outside active_hours
- `forklift_guard` — detects forklift + worker in same camera frame (collision risk)

### Poultry / Livestock Farming
- `coop_monitor` — reads DHT22 temp/humidity + soil moisture, alerts on threshold breach
- `sick_animal` — detects abnormal animal behavior (idle, drooping) via camera
- `animal_count` — counts flock size at set intervals via camera

### Crop / Vegetable Farming
- `coop_monitor` — also used for greenhouse temp/humidity/soil control
- `disease_leaf` — detects leaf disease (spots, yellowing) via camera
- `pest_detect` — detects insects/pests on plants via camera

### Cold Storage / Cold Chain
- `cold_chain_monitor` — monitors temperature inside storage, alerts on range breach

### Healthcare (non-critical)
- `patient_vitals` — monitors patient environment temp via sensor
- `air_quality` — monitors PM2.5, CO2, VOC in clinical spaces

### Sustainability / Energy
- `carbon_footprint_monitor` — tracks energy consumption and CO₂ estimate
- `renewable_energy_optimizer` — manages solar/grid switching via relay
- `emission_sensor_monitor` — monitors CO₂, PM2.5, VOC
- `water_footprint_monitor` — tracks water consumption via flow meter
- `smart_grid_scheduler` — optimizes load timing based on renewable availability

### Smart Home
- `presence_control` — presence-based device automation
- `flood_detect` — water leak detection via sensor
- `fire_safety` — smoke/fire detection, triggers alarm

## Default GPIO Pinout
- relay1 → GPIO 18 (ventilation fan / main load)
- relay2 → GPIO 23 (water pump / irrigation)
- relay3 → GPIO 27 (grow light / backup)
- relay4 → GPIO 22 (non-essential load)
- buzzer1 → GPIO 24
- led1 → GPIO 25
- DHT22 data → GPIO 4
- Soil moisture DO → GPIO 17

## Skill Configuration (config.yaml)
Key parameters per skill:
- `enabled: true/false`
- `camera: cam1` (for vision skills)
- `cooldown_seconds` — min delay between alerts (default 300)
- `confidence` — detection threshold (0.0–1.0, default 0.5)
- `temp_max/temp_min` — °C thresholds for coop_monitor
- `hum_max/hum_min` — % thresholds
- `active_hours: "20:00-06:00"` — for intrusion skill

## Hardware Requirements
- Raspberry Pi 4B (4GB+) or Pi 5
- USB webcam or RTSP IP camera (min 720p for vision skills)
- DHT22 sensor: temp + humidity (GPIO 4, needs 3.3V + 10kΩ pull-up)
- Capacitive soil moisture: digital output to GPIO 17
- Relay module (5V/12V, 4-channel): controls pumps, fans, valves
- Optional: Hailo-8 NPU for 5-10x faster vision inference

## Supported Sensors
DHT22/DHT11 (temp+humidity), Capacitive soil moisture, MQ135 (air quality/ammonia), DS18B20 (waterproof temp probe), LDR (light), Flow meter (water consumption)

## Remote Access
Use Tailscale VPN for secure remote dashboard access without port forwarding.
Install on Pi: `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up`

## Troubleshooting
- Sensor null → check GPIO wiring, DHT22 needs 10kΩ pull-up resistor
- PlutoEdge slow on Pi → normal (30–90s on Pi 4B CPU); upgrade to Pi 5 for ~2x speed
- Camera not found → check `lsusb`, try source: 0/1/2, add user to video group
- Ollama not running → `ollama serve` or `sudo systemctl start ollama`
- Alerts not sending → check WA Bridge running on port 3000, verify phone number format (628xxx)
