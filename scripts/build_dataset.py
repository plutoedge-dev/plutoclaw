"""
Pluto-LM Dataset Builder
Combines:
  1. acon96/Home-Assistant-Requests  → converted to PlutoClaw schema
  2. Synthetic PlutoClaw scenarios   → smart home + industrial + farming
  3. Organic data                    → data/chat_dataset.jsonl (existing)

Output: data/pluto_lm_dataset.jsonl  (ChatML/ShareGPT format for Unsloth)

Usage:
  python3 scripts/build_dataset.py
  python3 scripts/build_dataset.py --no-hf   # skip HuggingFace download
  python3 scripts/build_dataset.py --stats    # show stats only
"""

import json
import random
import argparse
import os
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = "data/pluto_lm_dataset.jsonl"
ORGANIC_FILE = "data/chat_dataset.jsonl"

# ─── Device profiles ──────────────────────────────────────────────────────────

DEVICE_PROFILES = {
    "sustainability": {
        "relay1": "main load switch / grid power (GPIO 18)",
        "relay2": "solar panel relay / renewable source (GPIO 23)",
        "relay3": "backup battery discharge relay (GPIO 27)",
        "relay4": "non-essential load cutoff (GPIO 22)",
        "buzzer1": "energy alert buzzer (GPIO 24)",
        "led1": "energy status LED — green:eco, red:overconsumption (GPIO 25)",
        "sensor_energy1": "smart energy meter (CT clamp, current & watt)",
        "sensor_solar1": "solar irradiance & panel output sensor (W/m²)",
        "sensor_battery1": "battery state-of-charge sensor (% SoC)",
        "sensor_co2": "CO₂ concentration sensor (ppm)",
        "sensor_flow1": "water flow meter (L/min)",
        "sensor_aq1": "air quality sensor — PM2.5, VOC index",
    },
    "smart_home": {
        "relay1": "ventilation fan (GPIO 18)",
        "relay2": "water pump / irrigation (GPIO 23)",
        "buzzer1": "alert buzzer (GPIO 24)",
        "led1": "status LED (GPIO 25)",
        "sensor_dht1": "temperature & humidity sensor (DHT22)",
        "sensor_soil1": "soil moisture sensor (GPIO 17)",
    },
    "industrial": {
        "relay1": "main motor contactor (GPIO 18)",
        "relay2": "cooling water pump (GPIO 23)",
        "relay3": "exhaust fan (GPIO 27)",
        "buzzer1": "emergency alarm (GPIO 24)",
        "led1": "status indicator LED (GPIO 25)",
        "sensor_temp1": "motor temperature sensor (NTC)",
        "sensor_vib1": "vibration sensor (GPIO 22)",
    },
    "farming": {
        "relay1": "greenhouse ventilation fan (GPIO 18)",
        "relay2": "drip irrigation pump (GPIO 23)",
        "relay3": "grow light (GPIO 27)",
        "buzzer1": "pest alert buzzer (GPIO 24)",
        "led1": "status LED (GPIO 25)",
        "sensor_dht1": "air temperature & humidity (DHT22)",
        "sensor_soil1": "soil moisture sensor (GPIO 17)",
        "sensor_light1": "light intensity sensor (LDR)",
    },
}


def make_system_prompt(domain: str, sensors: dict = None) -> str:
    devices = DEVICE_PROFILES[domain]
    device_lines = "\n".join(f"  - {k}: {v}" for k, v in devices.items())
    sensor_lines = ""
    if sensors:
        sensor_lines = "\nCurrent sensor readings:\n" + "\n".join(
            f"  - {k}: {v}" for k, v in sensors.items()
        )
    return (
        "You are Pluto, an AI controller for the PlutoClaw Edge AI platform.\n"
        "PlutoClaw runs on Raspberry Pi and controls physical IoT devices via GPIO.\n\n"
        f"Available devices:\n{device_lines}"
        f"{sensor_lines}\n\n"
        "When the user requests an action, respond with a brief explanation and end with:\n"
        "PLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"<device_id>\", \"action\": \"<on|off|toggle|pulse>\"}}\n\n"
        "For multi-device actions, use:\n"
        "PLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}\n\n"
        "For sensor queries only (no hardware action needed), respond without PLUTO_ACTION.\n"
        "Always be concise and precise."
    )


def make_entry(system: str, user: str, assistant: str, domain: str) -> dict:
    return {
        "conversations": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "domain": domain,
        "source": "synthetic",
    }


# ─── Synthetic data generators ────────────────────────────────────────────────

def gen_sustainability() -> list[dict]:
    entries = []
    sys_prompt = make_system_prompt("sustainability", {
        "grid_power": "2.4 kW", "solar_output": "1.1 kW",
        "battery_soc": "67%", "co2_ppm": "420",
        "water_flow": "3.2 L/min", "air_quality": "PM2.5: 18 µg/m³ (good)"
    })

    scenarios = [
        # ── Energy monitoring & alerts ──────────────────────────────────────
        ("Power consumption just spiked to 4.8 kW. That's too high.",
         "Power spike detected (4.8 kW). Cutting non-essential loads to reduce consumption.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"led1\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),

        ("Energy consumption is within normal range at 2.1 kW.",
         "Consumption is normal (2.1 kW). No action needed. LED set to eco green mode.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"led1\", \"action\": \"on\"}}"),

        ("It's peak hour (6–9 PM). Shift to energy-saving mode.",
         "Entering peak-hour energy saving mode: switching non-essential loads off and prioritizing solar.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        ("Off-peak hours started. Restore full power.",
         "Off-peak period active. Restoring full load from grid.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),

        ("What is the current power consumption?",
         "Current grid power draw from sensor_energy1: 2.4 kW. Solar is contributing 1.1 kW. Net grid consumption: 1.3 kW."),

        ("Alert: energy meter shows 6 kW for 10 minutes straight.",
         "Sustained high consumption detected (6 kW × 10 min). Triggering load shedding and alert.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        # ── Solar management ────────────────────────────────────────────────
        ("Solar panel output is 1.8 kW. Switch loads to solar.",
         "Good solar output (1.8 kW). Switching loads to solar relay to reduce grid dependency.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"off\"}]}"),

        ("Solar irradiance dropped, output is only 0.2 kW. Switch back to grid.",
         "Solar output insufficient (0.2 kW). Switching back to grid power.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay2\", \"action\": \"off\"}]}"),

        ("What is the solar panel generating right now?",
         "Current solar output from sensor_solar1: 1.1 kW. Irradiance conditions are moderate. Solar is covering 46% of current load (2.4 kW)."),

        ("It's a cloudy day, solar output is near zero.",
         "Solar unavailable due to cloud cover. Falling back to grid and battery if needed.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay2\", \"action\": \"off\"}]}"),

        ("Solar is producing excess power. Should we store it?",
         "Solar surplus detected. Routing excess to battery storage by keeping discharge relay off — battery will charge passively.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"off\"}}"),

        # ── Battery management ──────────────────────────────────────────────
        ("Battery is at 85% SoC. Grid power is expensive right now.",
         "Battery is well charged (85%). Switching to battery discharge to avoid expensive grid peak rates.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"off\"}]}"),

        ("Battery SoC dropped to 15%. Restore grid power immediately.",
         "Battery critically low (15%). Switching back to grid to protect battery from deep discharge.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),

        ("Battery SoC is 67%. What's the estimated runtime?",
         "Battery SoC: 67%. At current consumption of 2.4 kW with solar contributing 1.1 kW (net draw 1.3 kW), estimated battery runtime is approximately 4–5 hours depending on load stability."),

        ("Power outage detected. Switch to battery backup now.",
         "Grid failure detected. Switching to battery backup immediately.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        ("Grid power restored after outage. Switch back from battery.",
         "Grid restored. Switching back from battery to grid and stopping discharge relay.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"off\"}]}"),

        # ── CO₂ & Air Quality ───────────────────────────────────────────────
        ("CO₂ level is at 1200 ppm. Room is getting stuffy.",
         "CO₂ elevated (1,200 ppm — above 1,000 ppm threshold). Activating ventilation to improve air quality.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),

        ("CO₂ dropped to 600 ppm after ventilation. Good.",
         "CO₂ is back to safe levels (600 ppm). Turning off ventilation to save energy.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),

        ("Air quality sensor shows PM2.5 at 55 µg/m³. That's unhealthy.",
         "PM2.5 at 55 µg/m³ exceeds safe limit (35 µg/m³). Activating ventilation and alerting occupants.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),

        ("What is the current CO₂ level?",
         "Current CO₂ from sensor_co2: 420 ppm. This is outdoor ambient level — excellent air quality. No action needed."),

        ("VOC index spiked — possible chemical leak or fumes.",
         "High VOC detected. Activating maximum ventilation and sounding alert for safety.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        # ── Water conservation ──────────────────────────────────────────────
        ("Water flow sensor shows 12 L/min but no taps are open. Possible leak.",
         "Leak detected: 12 L/min flow with no active usage. Cutting water supply and sending alert.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        ("Daily water usage reached 300 L. We set a 250 L limit.",
         "Daily water limit exceeded (300 L / 250 L target). Restricting non-essential water flow.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),

        ("What is the current water consumption rate?",
         "Current water flow from sensor_flow1: 3.2 L/min. Daily consumption so far is within normal range. No action required."),

        ("Water flow is 0 L/min but the pump is running.",
         "Dry-run detected: pump is running with no water flow. Stopping pump to prevent damage.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay2\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),

        # ── Carbon footprint & reporting ────────────────────────────────────
        ("What's our estimated carbon footprint today?",
         "Based on sensor_energy1 data: consumed 18.4 kWh today, 11.2 kWh from solar (zero carbon). Grid consumption: 7.2 kWh × 0.82 kg CO₂/kWh = ~5.9 kg CO₂ today. Solar offset: ~9.2 kg CO₂ avoided."),

        ("How much energy did the solar panels save this week?",
         "This week's solar generation from sensor_solar1: 62 kWh. At grid rate 0.82 kg CO₂/kWh, you avoided approximately 50.8 kg CO₂ emissions. Cost saving estimated at 62 × local tariff."),

        ("Enable eco mode for the night.",
         "Activating night eco mode: non-essential loads off, battery discharge enabled if SoC > 50%.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        ("Disable eco mode, restore normal operations.",
         "Disabling eco mode. Restoring all loads and switching back to grid + solar hybrid.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"off\"}]}"),

        # ── Predictive & optimization ───────────────────────────────────────
        ("Weather forecast shows high sun tomorrow. Prepare for solar harvest.",
         "Pre-positioning for solar harvest: discharging battery tonight to 30% SoC so it can absorb maximum solar tomorrow.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"on\"}}"),

        ("Grid tariff is cheap right now (off-peak). Charge battery from grid.",
         "Off-peak grid pricing active. Charging battery from grid while rates are low.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"off\"}]}"),

        ("System has been idle for 30 minutes. Run energy audit.",
         "Idle state confirmed. All sensors nominal: power 2.4 kW (normal), solar 1.1 kW (active), battery 67% (healthy), CO₂ 420 ppm (good), water 3.2 L/min (normal). No anomalies detected."),

        ("What renewable energy percentage are we running at?",
         "Current energy mix: Solar 1.1 kW + Grid 1.3 kW = 2.4 kW total. Renewable share: 46%. To increase this, consider shifting deferrable loads (EV charging, laundry) to solar peak hours (10 AM–3 PM)."),

        ("Carbon alert: CO₂ emissions this hour exceeded our daily budget.",
         "Hourly carbon budget exceeded. Activating aggressive load shedding and switching fully to solar + battery.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay4\", \"action\": \"off\"}, {\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"on\"}]}"),
    ]

    for user, assistant in scenarios:
        entries.append(make_entry(sys_prompt, user, assistant, "sustainability"))

    return entries


def gen_smart_home() -> list[dict]:
    entries = []
    sys_prompt = make_system_prompt("smart_home", {
        "temperature": "29°C", "humidity": "72%", "soil_moisture": "dry (low)"
    })

    scenarios = [
        # Simple on/off commands
        ("Turn on the ventilation fan.",
         "Turning on the ventilation fan now.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Turn off the ventilation fan.",
         "Turning off the ventilation fan.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),
        ("Start the water pump.",
         "Starting the water pump (relay2).\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Stop the water pump.",
         "Stopping the water pump.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("Toggle the status LED.",
         "Toggling the status LED.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"led1\", \"action\": \"toggle\"}}"),
        ("Sound the buzzer briefly.",
         "Triggering a short buzzer pulse.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"buzzer1\", \"action\": \"pulse\"}}"),

        # Sensor-based decisions
        ("Temperature is 38°C, what should I do?",
         "38°C is above the safe threshold. I'll activate the ventilation fan immediately to cool down the environment.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Humidity is at 92%, that's too high.",
         "High humidity detected (92%). Activating the ventilation fan to reduce moisture levels.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Soil moisture sensor shows dry. Plants need water.",
         "Soil moisture is critically low. Activating the irrigation pump now.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Temperature dropped to 14°C, too cold.",
         "Temperature is below the safe minimum (14°C). Turning off the ventilation fan to retain heat.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),

        # Multi-device actions
        ("Temperature is 41°C and soil is dry. Handle both.",
         "Both conditions are critical. Activating the fan for cooling and the pump for irrigation simultaneously.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay2\", \"action\": \"on\"}]}"),
        ("Emergency! Sound alarm and turn on the fan.",
         "Triggering emergency alert and activating ventilation.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),
        ("Run a watering cycle for 5 seconds then stop.",
         "Running a 5-second irrigation pulse on the water pump.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"pulse\", \"duration\": 5}}"),

        # Status queries (no action)
        ("What's the current temperature?",
         "Current temperature reading from sensor_dht1: 29°C, humidity: 72%."),
        ("Is the fan currently on?",
         "I don't have real-time state feedback from the relay. To verify, you can check the relay LED indicator or trigger a status poll from the dashboard."),
        ("What devices are available?",
         "Available devices:\n- relay1: ventilation fan\n- relay2: water pump / irrigation\n- buzzer1: alert buzzer\n- led1: status LED\n- sensor_dht1: temperature & humidity\n- sensor_soil1: soil moisture"),

        # Automation rule queries
        ("Set up automatic watering when soil is dry.",
         "To automate watering based on soil moisture, enable the coop_monitor skill with soil_enabled: true in config.yaml. It will automatically trigger relay2 when soil moisture drops below the threshold."),
        ("What happens when temperature exceeds 35°C?",
         "When temperature exceeds 35°C (configured in temp_max), PlutoClaw automatically activates relay1 (ventilation fan) and sends a WhatsApp alert if the WA bridge is online."),

        # Edge cases
        ("Turn off all devices.",
         "Turning off all active actuators.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"off\"}, {\"id\": \"led1\", \"action\": \"off\"}]}"),
        ("Pulse the buzzer 3 times.",
         "Sending 3 short buzzer pulses as an alert signal.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"buzzer1\", \"action\": \"pulse\", \"count\": 3, \"duration\": 0.5}}"),
    ]

    for user, assistant in scenarios:
        entries.append(make_entry(sys_prompt, user, assistant, "smart_home"))

    return entries


def gen_industrial() -> list[dict]:
    entries = []
    sys_prompt = make_system_prompt("industrial", {
        "motor_temp": "72°C", "vibration": "normal", "uptime_hours": "14h"
    })

    scenarios = [
        # Normal operations
        ("Start the main motor.",
         "Starting the main motor contactor (relay1).\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Stop the main motor.",
         "Stopping the main motor contactor.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),
        ("Start the cooling pump.",
         "Activating the cooling water pump (relay2).\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Turn on the exhaust fan.",
         "Turning on the exhaust fan (relay3).\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"on\"}}"),

        # Temperature-based
        ("Motor temperature is 87°C, that's critical!",
         "Critical temperature detected (87°C). Executing emergency protocol: stopping motor, activating cooling pump, and sounding alarm.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}]}"),
        ("Temperature reached 75°C, approaching limit.",
         "Motor temperature is elevated (75°C). Starting cooling pump as a precaution.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Motor cooled down to 45°C, safe now.",
         "Temperature is back within safe range (45°C). Stopping the cooling pump.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("Temperature is 95°C! Emergency shutdown now!",
         "CRITICAL: Temperature 95°C exceeds safe limit. Triggering full emergency shutdown and alarm.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        # Vibration-based
        ("Vibration sensor detected abnormal shaking.",
         "Abnormal vibration detected. Stopping the motor for safety inspection.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"pulse\"}]}"),
        ("Vibration is back to normal.",
         "Vibration readings have normalized. System is ready to restart when you confirm."),

        # Scheduled maintenance
        ("Machine has been running for 8 hours, time for a cooldown.",
         "Acknowledged. Stopping motor for scheduled cooldown and activating cooling pump.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}]}"),
        ("Maintenance complete, restart the motor.",
         "Restarting the main motor contactor after maintenance.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),

        # Status queries
        ("What is the current motor temperature?",
         "Current motor temperature from sensor_temp1: 72°C. This is within the normal operating range (safe limit: 85°C)."),
        ("Is the cooling pump running?",
         "Based on the last command state, the cooling pump (relay2) is off. Current motor temperature is 72°C — within safe range, no active cooling needed."),
        ("What are the emergency thresholds?",
         "Emergency thresholds for this industrial setup:\n- Warning: 75°C → activate cooling pump\n- Critical: 85°C → stop motor + cooling pump + alarm\n- Abnormal vibration → stop motor + buzzer pulse"),

        # Power management
        ("End of shift, shut everything down safely.",
         "Executing end-of-shift shutdown sequence: stopping motor, then cooling pump, then exhaust fan.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay3\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"off\"}]}"),
        ("Start of shift, power up the line.",
         "Powering up: starting exhaust fan first, then main motor.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),

        # Pressure & conveyor
        ("Pressure gauge reads 8 bar, above limit. Shut down.",
         "Pressure exceeds safe limit (8 bar). Stopping motor and activating alarm.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}]}"),
        ("Conveyor belt jammed, stop immediately.",
         "Conveyor jam detected. Stopping main motor to prevent damage.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),
        ("Jam cleared, restart the conveyor.",
         "Jam cleared. Restarting the conveyor motor.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Run motor at reduced power for warm-up.",
         "Starting motor in warm-up mode. Full power will be available after 2 minutes.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Production line ready, start everything.",
         "Starting production line: exhaust fan → cooling pump → main motor.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),

        # Alerts & indicators
        ("Alert maintenance team, machine needs inspection.",
         "Sounding alert buzzer to notify maintenance team.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"buzzer1\", \"action\": \"pulse\"}}"),
        ("Set status LED to indicate machine is running.",
         "Turning on status LED to indicate active operation.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"led1\", \"action\": \"on\"}}"),
        ("Machine idle, turn off status LED.",
         "Machine is idle. Turning off status indicator LED.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"led1\", \"action\": \"off\"}}"),
        ("Test all alarms before shift start.",
         "Running alarm test: buzzer pulse and LED blink.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"buzzer1\", \"action\": \"pulse\"}, {\"id\": \"led1\", \"action\": \"toggle\"}]}"),

        # Diagnostics
        ("What is the vibration status?",
         "Current vibration reading from sensor_vib1: normal. No anomalies detected."),
        ("How long has the motor been running?",
         "Current motor uptime: 14 hours. Scheduled maintenance recommended every 8 hours of operation."),
        ("Is the exhaust fan working?",
         "Based on the last command, relay3 (exhaust fan) is in active state. Check the physical indicator on the relay module to confirm."),
        ("What triggers an emergency shutdown?",
         "Emergency shutdown triggers:\n- Motor temp ≥ 85°C → stop motor + cooling pump + alarm\n- Vibration anomaly detected → stop motor + buzzer pulse\n- Manual command → stop all relays"),
    ]

    for user, assistant in scenarios:
        entries.append(make_entry(sys_prompt, user, assistant, "industrial"))

    return entries


def gen_farming() -> list[dict]:
    entries = []
    sys_prompt = make_system_prompt("farming", {
        "air_temp": "31°C", "humidity": "65%",
        "soil_moisture": "35% (moderate)", "light": "850 lux"
    })

    scenarios = [
        # Irrigation
        ("Plants look dry, start irrigation.",
         "Starting drip irrigation pump now.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Stop watering, it's enough.",
         "Stopping irrigation pump.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("Soil moisture is at 20%, water the plants.",
         "Soil moisture is below threshold (20%). Activating drip irrigation.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"on\"}}"),
        ("Soil moisture reached 75%, stop watering.",
         "Soil moisture is now adequate (75%). Stopping irrigation pump.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("Run a 10-second watering pulse.",
         "Running a 10-second irrigation pulse.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"pulse\", \"duration\": 10}}"),

        # Temperature & ventilation
        ("Greenhouse is getting hot, 38°C inside.",
         "Greenhouse temperature is high (38°C). Activating ventilation fan to cool it down.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Temperature is 22°C, turn off the fan.",
         "Temperature is at optimal level (22°C). Turning off the ventilation fan.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"off\"}}"),

        # Lighting
        ("It's getting dark, turn on grow lights.",
         "Activating grow lights for the plants.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"on\"}}"),
        ("Sunrise detected, turn off grow lights.",
         "Natural light is sufficient. Turning off grow lights to save power.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"off\"}}"),
        ("Light intensity dropped to 200 lux, need more light.",
         "Low ambient light detected (200 lux). Activating grow lights.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"on\"}}"),

        # Pest & alerts
        ("Motion detected near crops at night, possible pest!",
         "Possible pest activity detected. Sounding alert buzzer to deter and notifying operator.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"buzzer1\", \"action\": \"pulse\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

        # Combined scenarios
        ("Temperature 40°C and soil very dry, handle both.",
         "Both temperature and moisture need attention. Starting ventilation fan and irrigation pump.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"on\"}, {\"id\": \"relay2\", \"action\": \"on\"}]}"),
        ("Evening routine: lights on, fan off, check soil.",
         "Running evening routine: activating grow lights, stopping ventilation. Soil moisture is at 35% — moderate, no watering needed yet.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay3\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"off\"}]}"),
        ("Morning routine: turn off lights and start ventilation.",
         "Running morning routine: turning off grow lights and starting ventilation fan.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay3\", \"action\": \"off\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),

        # Status queries
        ("What's the current soil moisture level?",
         "Current soil moisture from sensor_soil1: 35% (moderate). Irrigation is not required at this level."),
        ("Is the greenhouse temperature safe for tomatoes?",
         "Current temperature is 31°C. For tomatoes, the optimal range is 18-30°C. At 31°C it's slightly warm — consider turning on the ventilation fan if it rises above 33°C."),

        # Extended farming scenarios
        ("Heavy rain outside, stop the irrigation.",
         "Stopping drip irrigation to avoid over-watering during rainfall.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("Watering schedule: run pump for 30 seconds.",
         "Running scheduled irrigation: 30-second pump pulse.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"pulse\", \"duration\": 30}}"),
        ("Humidity too high at 90%, ventilate the greenhouse.",
         "Humidity at 90% is above safe range. Activating ventilation fan to reduce moisture.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}"),
        ("Night frost alert, temperature 8°C. Protect plants.",
         "Frost alert at 8°C. Turning off ventilation to retain heat and activating grow lights for warmth.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay3\", \"action\": \"on\"}]}"),
        ("Plants are overlit, reduce light exposure.",
         "Turning off grow lights to prevent over-exposure.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay3\", \"action\": \"off\"}}"),
        ("Run full greenhouse cycle: water + ventilate + light check.",
         "Running full cycle: activating irrigation and ventilation. Light is at 850 lux — sufficient, grow lights not needed.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"relay1\", \"action\": \"on\"}]}"),
        ("Shut down all greenhouse systems for the night.",
         "Shutting down day systems: stopping ventilation and irrigation. Grow lights will activate automatically when lux drops below threshold.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"off\"}]}"),
        ("Sensor shows soil moisture 80%, that's too wet.",
         "Soil is over-saturated at 80%. Stopping irrigation immediately.\n\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay2\", \"action\": \"off\"}}"),
        ("What's the optimal temperature for this greenhouse?",
         "Based on the farming configuration, the optimal air temperature range is 18-30°C. Current reading: 31°C — slightly above ideal. Ventilation is recommended."),
        ("How do I set up automatic irrigation?",
         "Enable the coop_monitor skill in config.yaml with soil_enabled: true and set the moisture threshold. PlutoClaw will automatically trigger relay2 when soil moisture drops below the defined level."),
        ("Alert: unusual pest movement detected by camera.",
         "Pest alert triggered. Sounding buzzer to deter pests and turning on LED as visual warning.\n\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"buzzer1\", \"action\": \"pulse\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),
    ]

    for user, assistant in scenarios:
        entries.append(make_entry(sys_prompt, user, assistant, "farming"))

    return entries


# ─── HuggingFace dataset converter ────────────────────────────────────────────

def load_hf_dataset() -> list[dict]:
    try:
        from datasets import load_dataset
    except ImportError:
        print("  [!] 'datasets' library not installed. Run: pip3 install datasets")
        return []

    print("  Downloading acon96/Home-Assistant-Requests from HuggingFace...")
    try:
        ds = load_dataset("acon96/Home-Assistant-Requests", split="train")
    except Exception as e:
        print(f"  [!] Failed to download: {e}")
        return []

    entries = []
    import re
    sys_prompt = make_system_prompt("smart_home")
    converted = 0
    skipped = 0

    # Map HA service → PlutoClaw action
    def ha_service_to_action(service: str) -> str:
        s = service.lower()
        if any(x in s for x in ["turn_on", "open", "unlock", "play", "start"]):
            return "on"
        if any(x in s for x in ["turn_off", "close", "lock", "stop", "pause"]):
            return "off"
        if "toggle" in s:
            return "toggle"
        return "on"

    # Map HA target device → PlutoClaw device ID
    def ha_target_to_device(target: str) -> str:
        t = target.lower()
        if any(x in t for x in ["fan", "vent", "blower"]):     return "relay1"
        if any(x in t for x in ["pump", "water", "irrigat"]):  return "relay2"
        if any(x in t for x in ["buzzer", "alarm", "siren"]):  return "buzzer1"
        if any(x in t for x in ["led", "light", "lamp"]):      return "led1"
        if any(x in t for x in ["cover", "blind", "curtain"]): return "relay1"
        if any(x in t for x in ["switch", "plug", "outlet"]):  return "relay1"
        return "relay1"

    seen_users = set()
    MAX_HA_ENTRIES = 500  # cap to keep dataset balanced

    for item in ds:
        if len(entries) >= MAX_HA_ENTRIES:
            break
        try:
            convs = item.get("conversations", [])
            # Extract user and assistant messages
            user_msg = next((m["value"] for m in convs if m["from"] == "user"), "")
            raw_response = next((m["value"] for m in convs if m["from"] == "assistant"), "")

            if not user_msg or not raw_response:
                skipped += 1
                continue

            # Light deduplication: skip if exact user message seen before
            user_key = user_msg.strip().lower()
            if user_key in seen_users:
                skipped += 1
                continue
            seen_users.add(user_key)

            # Parse homeassistant JSON block from assistant response
            ha_match = re.search(r'```homeassistant\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            if ha_match:
                try:
                    ha_json = json.loads(ha_match.group(1))
                    service = ha_json.get("service", "")
                    target  = ha_json.get("target_device", "")
                    action    = ha_service_to_action(service)
                    device_id = ha_target_to_device(target)

                    clean_text = re.sub(r'```homeassistant.*?```', '', raw_response, flags=re.DOTALL).strip()
                    if not clean_text:
                        clean_text = f"{'Activating' if action == 'on' else 'Deactivating'} {device_id}."

                    pluto_action = json.dumps({
                        "type": "actuator_trigger",
                        "params": {"id": device_id, "action": action}
                    })
                    assistant_msg = f"{clean_text}\n\nPLUTO_ACTION: {pluto_action}"
                    converted += 1
                except Exception:
                    skipped += 1
                    continue
            else:
                # No action block — info/status query
                clean = re.sub(r'```.*?```', '', raw_response, flags=re.DOTALL).strip()
                if not clean or len(clean) < 10:
                    skipped += 1
                    continue
                assistant_msg = clean
                converted += 1

            entries.append({
                "conversations": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ],
                "domain": "smart_home",
                "source": "acon96_home_assistant",
            })

        except Exception:
            skipped += 1
            continue

    print(f"  Converted {converted} entries, skipped {skipped}")
    return entries


# ─── Organic data loader ───────────────────────────────────────────────────────

def load_organic(filepath: str) -> list[dict]:
    entries = []
    if not Path(filepath).exists():
        return []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                msgs = item.get("messages", [])
                if len(msgs) >= 2:
                    # Convert to ShareGPT conversations format
                    # Skip entries with Indonesian system prompts (pre-English pivot)
                    sys_content = next((m["content"] for m in msgs if m["role"] == "system"), "")
                    if "Bahasa Indonesia" in sys_content or "asisten AI" in sys_content.lower():
                        continue  # Skip old Indonesian entries
                    entries.append({
                        "conversations": msgs,
                        "domain": "organic",
                        "source": "plutoclaw_usage",
                    })
            except Exception:
                continue

    return entries


# ─── PlutoClaw Knowledge Q&A ──────────────────────────────────────────────────

KNOWLEDGE_SYSTEM = (
    "You are Pluto, the AI controller and assistant for the PlutoClaw Edge AI platform. "
    "PlutoClaw is an open-source edge AI system built on Raspberry Pi that monitors environments "
    "via cameras and sensors, controls actuators via GPIO, and sends alerts via WhatsApp. "
    "Answer questions about PlutoClaw clearly, concisely, and helpfully."
)

KNOWLEDGE_QA = [
    # ── Platform overview ──────────────────────────────────────────────────────
    ("What is PlutoClaw?",
     "PlutoClaw is an open-source Edge AI platform built on Raspberry Pi. It monitors environments using cameras and IoT sensors, controls physical devices (relays, buzzers, LEDs) via GPIO, and sends real-time alerts via WhatsApp. It runs fully offline — no cloud required."),

    ("What is PlutoEdge?",
     "PlutoEdge is the fine-tuned LLM that powers PlutoClaw's AI brain. It's a 1.5B parameter model based on Qwen2.5, specialized for IoT control, sensor interpretation, and PlutoClaw platform knowledge. It runs locally on Raspberry Pi via Ollama."),

    ("How is PlutoClaw different from cloud AI?",
     "PlutoClaw runs 100% on-device — no internet required after setup. Your data stays local, latency is minimal, and it works in remote locations without connectivity. Cloud AI depends on internet, has ongoing subscription costs, and sends your data to external servers."),

    ("What hardware does PlutoClaw run on?",
     "PlutoClaw runs on Raspberry Pi 4B or Raspberry Pi 5. It supports USB webcams, RTSP IP cameras, DHT22/DHT11 temperature-humidity sensors, soil moisture sensors, relay modules, buzzers, and LEDs via GPIO. Optional Hailo-8 NPU for faster vision inference."),

    ("Does PlutoClaw need internet?",
     "No. After initial setup, PlutoClaw runs completely offline. All AI inference (vision + LLM) runs locally on the Raspberry Pi. WhatsApp alerts require internet only when sending notifications."),

    ("What programming language is PlutoClaw built with?",
     "PlutoClaw is built with Python. The backend uses FastAPI, the AI vision uses YOLOv8/Ultralytics, and the LLM uses Ollama with PlutoEdge. The dashboard is a web UI served locally at port 8080."),

    ("What is the PlutoClaw dashboard?",
     "The PlutoClaw dashboard is a web interface accessible at http://<pi-ip>:8080. It shows live camera feeds, sensor readings, skill status, event logs, actuator controls, and the Pluto AI chat interface. No external access required — local network only."),

    # ── Skills — general ──────────────────────────────────────────────────────
    ("What are skills in PlutoClaw?",
     "Skills are AI agents that run continuously on PlutoClaw, each monitoring a specific condition. Examples: ppe_guard monitors PPE compliance, coop_monitor tracks temperature/humidity, intrusion detects people after hours. Skills can trigger alerts and actuator actions automatically."),

    ("How many skills can PlutoClaw run at once?",
     "PlutoClaw can run multiple skills simultaneously. The recommended maximum depends on hardware: Pi 4B can handle 2-4 camera-based skills + unlimited sensor skills without performance issues. Pi 5 can handle more."),

    ("Can I create custom skills?",
     "Yes. PlutoClaw supports custom skills via the skills/custom/ directory. You can extend BaseSkill to create domain-specific monitoring logic with your own thresholds, sensor inputs, and alert conditions."),

    # ── Skills — warehouse ────────────────────────────────────────────────────
    ("What skills should I use for a warehouse?",
     "For warehouse operations, recommended skills are:\n- **ppe_guard**: Detects workers without PPE (hard hat, safety vest) — essential for safety compliance.\n- **intrusion**: Detects unauthorized access outside working hours.\n- **forklift_guard**: Detects dangerous proximity between forklifts and workers.\nRequires: camera per monitored zone."),

    ("What is the ppe_guard skill?",
     "ppe_guard is a computer vision skill that detects workers not wearing required PPE (hard hat, safety vest). It uses a YOLO model to analyze camera feeds in real-time and sends a WhatsApp alert when a violation is detected. Configurable confidence threshold and cooldown period."),

    ("What is the intrusion skill?",
     "intrusion detects people entering a monitored area outside defined working hours. You configure active_hours (e.g. '20:00-06:00') and it sends an alert when motion/person is detected during those hours. Useful for warehouses, offices, and restricted areas."),

    ("What is forklift_guard?",
     "forklift_guard uses computer vision to detect when a forklift and a worker are in the same camera frame simultaneously — a collision risk scenario. It sends an immediate alert and can trigger a buzzer. Requires a camera with a clear view of the work zone."),

    ("What camera do I need for warehouse skills?",
     "Any USB webcam or RTSP IP camera works with PlutoClaw. For warehouse use: minimum 720p resolution, positioned to cover the full work zone. For forklift_guard, mount at a high angle (3-5 meters) for better top-down visibility. RTSP cameras allow wireless installation."),

    # ── Skills — farming ──────────────────────────────────────────────────────
    ("What skills should I use for a chicken farm?",
     "For poultry farming, recommended skills are:\n- **coop_monitor**: Monitors coop temperature, humidity, and soil/litter moisture via DHT22 sensor. Alerts when thresholds are exceeded.\n- **sick_animal**: Detects chickens showing abnormal behavior (idle, separated, drooping wings) via camera.\n- **animal_count**: Counts flock size automatically at set intervals.\nRequires: DHT22 sensor + camera."),

    ("What skills should I use for vegetable farming?",
     "For vegetable/crop farming:\n- **coop_monitor** or custom sensor skill: Monitor temperature, humidity, soil moisture.\n- **disease_leaf**: Detects leaf disease (spots, yellowing, wilting) from camera.\n- **pest_detect**: Detects insects/pests on plants.\nPlutoClaw can also control drip irrigation (relay2) and grow lights (relay3) based on sensor readings."),

    ("What is coop_monitor?",
     "coop_monitor is a sensor-based skill that reads temperature, humidity (via DHT22), and optionally soil/litter moisture (via capacitive sensor). It triggers alerts when values exceed configured thresholds (temp_max, temp_min, hum_max, hum_min) and can automatically control a fan or water pump via relay."),

    ("What sensors does PlutoClaw support for farming?",
     "PlutoClaw supports:\n- **DHT22/DHT11**: Temperature and humidity (most common)\n- **Capacitive soil moisture sensor**: Digital output to GPIO\n- **MQ135**: Air quality / ammonia (useful for livestock)\n- **DS18B20**: Waterproof temperature probe\n- **LDR**: Light intensity\nAll connect directly to Raspberry Pi GPIO pins."),

    ("How do I control irrigation with PlutoClaw?",
     "Connect a submersible pump or solenoid valve to relay2 (GPIO 23) via a relay module. PlutoClaw's coop_monitor skill reads soil moisture — when soil is dry (soil_dry=True), it triggers an alert. Pluto AI can then activate relay2 to run the pump. You can also set automation rules to do this automatically."),

    # ── Skills — cold storage / cold chain ────────────────────────────────────
    ("What skills should I use for cold storage?",
     "For cold storage / cold chain monitoring:\n- **cold_chain_monitor**: Monitors temperature inside storage units, alerts if temperature goes above/below safe range.\n- **intrusion** or **cs_intrusion**: Controls and monitors access to cold storage.\nRequires: temperature sensor (DS18B20 recommended for cold environments) + optional camera."),

    ("What temperature range does cold storage monitoring support?",
     "PlutoClaw's cold chain monitoring is configurable for any temperature range. For frozen goods: typically -25°C to -18°C. For chilled produce: 2°C to 8°C. Set temp_min and temp_max in the skill config. Alerts fire via WhatsApp when the range is breached."),

    # ── Skills — health / medical ─────────────────────────────────────────────
    ("What skills are available for healthcare?",
     "PlutoClaw offers:\n- **patient_vitals**: Monitors patient temperature and environmental conditions via sensor.\n- **air_quality**: Monitors PM2.5, CO2, VOC index in clinical environments.\nNote: PlutoClaw is for non-critical environmental monitoring only — not for medical diagnostics or life-support systems."),

    # ── Skills — sustainability ───────────────────────────────────────────────
    ("What sustainability skills does PlutoClaw have?",
     "PlutoClaw's sustainability domain includes:\n- **carbon_footprint_monitor**: Tracks real-time energy consumption and estimates CO₂ emissions.\n- **renewable_energy_optimizer**: Manages solar/grid switching based on solar output and battery SoC.\n- **emission_sensor_monitor**: Monitors CO₂, PM2.5, and VOC levels.\n- **water_footprint_monitor**: Tracks water consumption via flow meter.\n- **smart_grid_scheduler**: Optimizes load timing based on renewable availability."),

    ("How does PlutoClaw manage solar energy?",
     "With the renewable_energy_optimizer skill, PlutoClaw reads solar irradiance (sensor_solar1) and battery SoC (sensor_battery1). When solar output is sufficient, it switches loads to solar (relay2 on, relay1 off). When battery is low, it restores grid power. This happens automatically based on configurable thresholds."),

    # ── Actuators & GPIO ──────────────────────────────────────────────────────
    ("What actuators can PlutoClaw control?",
     "PlutoClaw controls actuators via Raspberry Pi GPIO:\n- **Relay**: On/off control for pumps, fans, motors, lights, valves (relay1–relay4)\n- **Buzzer**: Audio alerts (buzzer1)\n- **LED**: Visual indicators (led1)\n- **PWM devices**: Fans with speed control, dimmers\nAll actuators are configured in config.yaml with GPIO pin assignments."),

    ("What is a relay in PlutoClaw?",
     "A relay is an electrically controlled switch. In PlutoClaw, relay modules connect to GPIO pins and allow the Raspberry Pi to switch high-power devices (pumps, fans, motors, lights) on and off safely. PlutoClaw supports active-high and active-low relay modules. Default wiring: relay1 → GPIO 18, relay2 → GPIO 23, relay3 → GPIO 27, relay4 → GPIO 22."),

    ("What is the default GPIO pinout for PlutoClaw?",
     "Default PlutoClaw GPIO assignments:\n- relay1 → GPIO 18 (Pin 12) — ventilation fan / main load\n- relay2 → GPIO 23 (Pin 16) — water pump / irrigation\n- relay3 → GPIO 27 (Pin 13) — grow light / backup\n- relay4 → GPIO 22 (Pin 15) — non-essential load\n- buzzer1 → GPIO 24 (Pin 18) — alert buzzer\n- led1 → GPIO 25 (Pin 22) — status LED\n- sensor DHT22 → GPIO 4 (Pin 7)\n- soil moisture → GPIO 17 (Pin 11)"),

    ("Can PlutoClaw control a water pump?",
     "Yes. Connect the pump to relay2 (GPIO 23) via a 5V/12V relay module. PlutoClaw can turn it on/off via chat command or automatically via the coop_monitor skill when soil moisture is low. For high-power pumps, use a relay rated for the pump's voltage and current (e.g. 10A relay for a 12V pump)."),

    # ── WhatsApp alerts ───────────────────────────────────────────────────────
    ("How does PlutoClaw send WhatsApp alerts?",
     "PlutoClaw sends WhatsApp alerts via a WA Bridge running on port 3000. The bridge uses a WhatsApp Web session. When a skill detects an event, it sends a message to configured phone numbers (format: 628xxx). Alerts include the event description, timestamp, and optionally an image from the camera."),

    ("What phone number format does PlutoClaw WhatsApp use?",
     "Use international format without + or spaces: 628xxxxxxxxx (Indonesia), 1xxxxxxxxxx (US), 44xxxxxxxxx (UK). Configure in config.yaml under whatsapp.alert_numbers. Multiple numbers supported."),

    # ── Setup & configuration ─────────────────────────────────────────────────
    ("How do I install PlutoClaw on Raspberry Pi?",
     "1. Flash Raspberry Pi OS (64-bit) to SD card\n2. Enable SSH and connect to network\n3. Clone PlutoClaw repo: git clone https://github.com/plutoclaw/plutoclaw\n4. Run setup.sh: bash setup.sh\n5. Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh\n6. Pull PlutoEdge: ollama pull hf.co/arvindpi/PlutoEdge-1.5B-IoT\n7. Configure config.yaml for your sensors and skills\n8. Start: python3 main.py"),

    ("How do I install PlutoEdge on my Raspberry Pi?",
     "PlutoEdge is available via Ollama. Install with:\n1. Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh\n2. Pull the model: ollama pull hf.co/arvindpi/PlutoEdge-1.5B-IoT\n3. Test: ollama run plutoedge 'Turn on relay1'\nPlutoEdge is optimized for IoT control and runs on Pi 4B with ~940MB RAM usage."),

    ("How do I enable a skill in PlutoClaw?",
     "In config.yaml, find the skill under the skills section and set enabled: true. Configure the required parameters (camera ID, sensor pin, thresholds, cooldown). Then restart PlutoClaw: python3 main.py. The skill will appear as 'running' in the dashboard."),

    ("How do I configure sensor thresholds?",
     "In config.yaml under the skill configuration:\n- temp_max: maximum safe temperature (e.g. 35.0 for °C)\n- temp_min: minimum safe temperature (e.g. 15.0)\n- hum_max: maximum humidity % (e.g. 90.0)\n- hum_min: minimum humidity % (e.g. 30.0)\n- cooldown_seconds: minimum time between alerts (e.g. 300 = 5 minutes)\nRestart PlutoClaw after changes."),

    ("What is cooldown_seconds in skill config?",
     "cooldown_seconds prevents alert spam. After an alert fires, PlutoClaw waits this many seconds before sending another alert for the same condition. For example, cooldown_seconds: 300 means alerts fire at most once every 5 minutes. Recommended: 60-300 seconds depending on the use case."),

    # ── Troubleshooting ───────────────────────────────────────────────────────
    ("Why is my sensor reading null?",
     "Sensor reading null usually means:\n1. GPIO pin not connected or wrong pin in config.yaml\n2. DHT22 needs 3.3V power — check wiring\n3. DHT22 timing issue — try adding a 10kΩ pull-up resistor on DATA pin\n4. Running on Mac (GPIO unavailable) — sensor will show 'gpio_unavailable' status, which is expected\nOn Pi, check: gpio readall to verify pin states."),

    ("Why is PlutoEdge responding slowly on Raspberry Pi?",
     "PlutoEdge (940MB Q4_K_M) runs on Pi 4B CPU — expect 30-90 seconds per response. This is normal for LLM inference on ARM CPU without GPU. To improve speed:\n1. Reduce system prompt length\n2. Set num_ctx: 1024 in Ollama options\n3. Upgrade to Raspberry Pi 5 (~2x faster)\n4. Add Hailo-8 NPU (5-10x faster for vision; LLM still on CPU)\n5. Use a lighter Q2_K quantization (~500MB, ~40s)"),

    ("Why is the camera not connecting?",
     "Camera not connecting troubleshooting:\n1. USB webcam: check lsusb to confirm it's detected\n2. Try different source: 0, 1, 2 in config.yaml\n3. RTSP camera: verify the stream URL works in VLC first\n4. Permission: add user to video group: sudo usermod -a -G video $USER\n5. On Mac development mode: USB webcam should work, but built-in camera may need macOS permissions"),

    ("Ollama is not running, how do I start it?",
     "Start Ollama with: ollama serve\nOr as a service: sudo systemctl enable ollama && sudo systemctl start ollama\nVerify it's running: curl http://localhost:11434/api/tags\nIf plutoedge model is missing: ollama pull hf.co/arvindpi/PlutoEdge-1.5B-IoT"),

    # ── PlutoEdge specifics ───────────────────────────────────────────────────
    ("What model is PlutoEdge based on?",
     "PlutoEdge-1.5B is fine-tuned from Qwen2.5-1.5B-Instruct by Alibaba. It uses LoRA fine-tuning (rank=16) trained on 600+ IoT control scenarios across smart home, industrial, farming, and sustainability domains. License: Apache 2.0."),

    ("What domains does PlutoEdge understand?",
     "PlutoEdge is trained on four IoT domains:\n- **Smart home**: temperature control, irrigation, lighting automation\n- **Industrial**: motor control, emergency shutdown, vibration/temperature monitoring\n- **Farming**: greenhouse control, soil moisture irrigation, crop monitoring\n- **Sustainability**: solar/grid switching, carbon monitoring, water footprint tracking\nIt outputs structured PLUTO_ACTION commands for all these scenarios."),

    ("What is the PLUTO_ACTION format?",
     "PLUTO_ACTION is PlutoEdge's structured output format for device control:\n\nSingle device:\nPLUTO_ACTION: {\"type\": \"actuator_trigger\", \"params\": {\"id\": \"relay1\", \"action\": \"on\"}}\n\nMultiple devices:\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}]}\n\nPlutoClaw parses this and executes the GPIO commands automatically."),

    ("Can PlutoEdge control multiple devices at once?",
     "Yes. Use multi_trigger in PLUTO_ACTION to control multiple devices simultaneously. For example, an emergency shutdown can turn off the motor, activate the cooling pump, sound the buzzer, and turn on the status LED all in one command:\nPLUTO_ACTION: {\"type\": \"multi_trigger\", \"params\": [{\"id\": \"relay1\", \"action\": \"off\"}, {\"id\": \"relay2\", \"action\": \"on\"}, {\"id\": \"buzzer1\", \"action\": \"on\"}, {\"id\": \"led1\", \"action\": \"on\"}]}"),

    ("Is PlutoEdge open source?",
     "Yes. PlutoEdge is released under Apache 2.0 license, the same as the base Qwen2.5 model. You can use it commercially, modify it, and redistribute it. The training dataset and fine-tuning scripts are available in the PlutoClaw repository."),

    # ── Business / deployment ─────────────────────────────────────────────────
    ("What industries can PlutoClaw be deployed in?",
     "PlutoClaw is designed for:\n- **Warehouse & logistics**: PPE compliance, intrusion detection, forklift safety\n- **Poultry & livestock farming**: flock monitoring, health detection, environment control\n- **Vegetable & fruit farming**: plant disease detection, irrigation automation\n- **Paddy/rice fields**: water level monitoring, disease detection\n- **Cold storage**: temperature monitoring, access control\n- **Industrial**: motor monitoring, predictive maintenance\n- **Smart home**: automation, security, energy management\n- **Healthcare**: environmental monitoring in non-critical settings"),

    ("How much does PlutoClaw cost?",
     "PlutoClaw software is free and open-source. Hardware costs:\n- Raspberry Pi 4B (4GB): ~$55\n- Camera module or USB webcam: $15-30\n- DHT22 sensor: ~$3\n- Relay module (4-channel): ~$5\n- Total starter kit: ~$80-100\nOptional Hailo-8 NPU (for faster vision AI): ~$70"),

    ("Can PlutoClaw send alerts to multiple phone numbers?",
     "Yes. In config.yaml under whatsapp.alert_numbers, add multiple numbers in a list:\nalert_numbers:\n  - '628111222333'\n  - '628444555666'\nAll numbers will receive the same alerts simultaneously."),

    ("Can I access the PlutoClaw dashboard remotely?",
     "Yes, two options:\n1. **Local network**: access via http://<pi-ip>:8080 from any device on the same WiFi\n2. **Remote access**: use Tailscale VPN (recommended) or port forwarding. With Tailscale, access via http://<tailscale-ip>:8080 from anywhere securely.\nDashboard auth can be enabled in config.yaml (dashboard.auth.enabled: true)."),

    ("What is Tailscale and why does PlutoClaw use it?",
     "Tailscale is a zero-config VPN that creates a private network between your devices. PlutoClaw uses it to enable secure remote access to the dashboard and SSH without exposing the Pi to the public internet. Install on Pi: curl -fsSL https://tailscale.com/install.sh | sh, then tailscale up."),
]


def gen_knowledge_qa() -> list[dict]:
    entries = []
    for user_q, assistant_a in KNOWLEDGE_QA:
        entries.append({
            "conversations": [
                {"role": "system",    "content": KNOWLEDGE_SYSTEM},
                {"role": "user",      "content": user_q},
                {"role": "assistant", "content": assistant_a},
            ],
            "domain": "knowledge",
            "source": "synthetic_knowledge",
        })
    return entries


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-hf", action="store_true", help="Skip HuggingFace download")
    parser.add_argument("--stats", action="store_true", help="Show stats of existing dataset")
    args = parser.parse_args()

    if args.stats:
        if not Path(OUTPUT_FILE).exists():
            print(f"Dataset not found: {OUTPUT_FILE}")
            return
        with open(OUTPUT_FILE) as f:
            entries = [json.loads(l) for l in f if l.strip()]
        by_domain = {}
        by_source = {}
        for e in entries:
            d = e.get("domain", "unknown")
            s = e.get("source", "unknown")
            by_domain[d] = by_domain.get(d, 0) + 1
            by_source[s] = by_source.get(s, 0) + 1
        print(f"\nDataset: {OUTPUT_FILE}")
        print(f"Total entries: {len(entries)}\n")
        print("By domain:")
        for k, v in sorted(by_domain.items(), key=lambda x: -x[1]):
            print(f"  {k:20s}: {v}")
        print("\nBy source:")
        for k, v in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"  {k:30s}: {v}")
        return

    os.makedirs("data", exist_ok=True)
    all_entries = []

    # 1. Synthetic data
    print("\n[1] Generating synthetic PlutoClaw scenarios...")
    sh   = gen_smart_home()
    ind  = gen_industrial()
    farm = gen_farming()
    sust = gen_sustainability()
    know = gen_knowledge_qa()
    print(f"  smart_home     : {len(sh)} entries")
    print(f"  industrial     : {len(ind)} entries")
    print(f"  farming        : {len(farm)} entries")
    print(f"  sustainability : {len(sust)} entries")
    print(f"  knowledge      : {len(know)} entries")
    all_entries.extend(sh + ind + farm + sust + know)

    # 2. HuggingFace dataset
    if not args.no_hf:
        print("\n[2] Loading acon96/Home-Assistant-Requests from HuggingFace...")
        hf_entries = load_hf_dataset()
        print(f"  Loaded {len(hf_entries)} entries")
        all_entries.extend(hf_entries)
    else:
        print("\n[2] Skipping HuggingFace download (--no-hf)")

    # 3. Organic data
    print(f"\n[3] Loading organic data from {ORGANIC_FILE}...")
    organic = load_organic(ORGANIC_FILE)
    print(f"  Loaded {len(organic)} entries")
    all_entries.extend(organic)

    # Shuffle
    random.shuffle(all_entries)

    # Write output
    print(f"\n[4] Writing {len(all_entries)} entries to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset built: {len(all_entries)} total entries")
    print(f"   Output: {OUTPUT_FILE}")
    print(f"\n   Domain breakdown:")
    by_domain = {}
    for e in all_entries:
        d = e.get("domain", "unknown")
        by_domain[d] = by_domain.get(d, 0) + 1
    for k, v in sorted(by_domain.items(), key=lambda x: -x[1]):
        print(f"     {k:20s}: {v}")
    print(f"\n   Next step: python3 scripts/finetune_pluto_lm.py")


if __name__ == "__main__":
    main()
