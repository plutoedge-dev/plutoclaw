"""
PlutoClaw Skill Registry

Skills are the building blocks of PlutoClaw — each skill represents
a single sensing/acting capability that Pluto can activate independently.

Categories:
  industrial   : Factory, machinery, manufacturing, energy
  agriculture  : Farming, orchards, livestock, greenhouse
  medical      : Health monitoring, clinical air quality
  smart_home   : Smart home, security, residential environment
  logistics    : Cold chain, warehouse, vehicles, delivery
  security     : Surveillance, access control, intrusion
"""

# ── Industrial & Machinery ────────────────────────────────────────────────────
from skills.builtin.predictive_maintenance import PredictiveMaintenanceSkill
from skills.builtin.quality_control        import QualityControlSkill
from skills.builtin.energy_monitor         import EnergyMonitorSkill

# ── Agriculture & AgriTech ────────────────────────────────────────────────────
from skills.builtin.coop_monitor           import CoopMonitorSkill
from skills.builtin.crop_monitor           import CropMonitorSkill
from skills.builtin.irrigation_control     import IrrigationControlSkill
from skills.builtin.livestock_monitor      import LivestockMonitorSkill

# ── Medical & Health ──────────────────────────────────────────────────────────
from skills.builtin.patient_vitals         import PatientVitalsSkill
from skills.builtin.air_quality            import AirQualitySkill

# ── Smart Home & IoT ──────────────────────────────────────────────────────────
from skills.builtin.smart_home_control     import SmartHomeControlSkill
from skills.builtin.flood_detector         import FloodDetectorSkill
from skills.builtin.fire_smoke_detector    import FireSmokeDetectorSkill

# ── Logistics & Supply Chain ──────────────────────────────────────────────────
from skills.builtin.cold_chain_monitor     import ColdChainMonitorSkill
from skills.builtin.vehicle_detection      import VehicleDetectionSkill

# ── Security & Surveillance ───────────────────────────────────────────────────
from skills.builtin.ppe_guard                  import PPEGuardSkill
from skills.builtin.intrusion                  import IntrusionSkill

# ── AI Sustainability & Carbon Intelligence ───────────────────────────────────
from skills.builtin.carbon_footprint_monitor   import CarbonFootprintMonitorSkill
from skills.builtin.renewable_energy_optimizer import RenewableEnergyOptimizerSkill
from skills.builtin.emission_sensor_monitor    import EmissionSensorMonitorSkill
from skills.builtin.water_footprint_monitor    import WaterFootprintMonitorSkill
from skills.builtin.smart_grid_scheduler       import SmartGridSchedulerSkill


SKILL_REGISTRY: dict[str, type] = {
    # ── Industrial & Machinery ─────────────────────────────────────────────────
    "predictive_maintenance": PredictiveMaintenanceSkill,   # vibration + machine temperature
    "quality_control":        QualityControlSkill,          # visual product inspection
    "energy_monitor":         EnergyMonitorSkill,           # electrical power consumption

    # ── Agriculture & AgriTech ────────────────────────────────────────────────
    "coop_monitor":           CoopMonitorSkill,             # temperature + humidity + soil
    "crop_monitor":           CropMonitorSkill,             # greenhouse / vertical farm
    "irrigation_control":     IrrigationControlSkill,       # irrigation pump automation
    "livestock_monitor":      LivestockMonitorSkill,        # livestock pen + ammonia

    # ── Medical & Health ──────────────────────────────────────────────────────
    "patient_vitals":         PatientVitalsSkill,           # SpO2 + HR + body temperature
    "air_quality":            AirQualitySkill,              # CO2 + VOC + PM2.5

    # ── Smart Home & IoT ──────────────────────────────────────────────────────
    "smart_home_control":     SmartHomeControlSkill,        # PIR + automatic relay
    "flood_detector":         FloodDetectorSkill,           # water leak detection
    "fire_smoke_detector":    FireSmokeDetectorSkill,       # smoke + LPG gas

    # ── Logistics & Supply Chain ──────────────────────────────────────────────
    "cold_chain_monitor":     ColdChainMonitorSkill,        # cold storage temperature
    "vehicle_detection":      VehicleDetectionSkill,        # vehicle count + detection

    # ── Security & Surveillance ───────────────────────────────────────────────
    "ppe_guard":                  PPEGuardSkill,                # PPE detection (hard hat, vest)
    "intrusion":                  IntrusionSkill,               # person outside working hours

    # ── AI Sustainability & Carbon Intelligence ────────────────────────────────
    "carbon_footprint_monitor":   CarbonFootprintMonitorSkill,   # kWh → CO2e real-time
    "renewable_energy_optimizer": RenewableEnergyOptimizerSkill, # solar surplus → load shift
    "emission_sensor_monitor":    EmissionSensorMonitorSkill,     # CO2/CH4/NOx compliance
    "water_footprint_monitor":    WaterFootprintMonitorSkill,     # water consumption + water footprint
    "smart_grid_scheduler":       SmartGridSchedulerSkill,        # demand response green window
}


# Category metadata for dashboard UI
SKILL_CATEGORIES: dict[str, dict] = {
    "industrial": {
        "label": "Industrial & Machinery",
        "icon":  "⚙️",
        "desc":  "Predictive maintenance, anomaly detection, on-site quality control.",
        "skills": ["predictive_maintenance", "quality_control", "energy_monitor"],
    },
    "agriculture": {
        "label": "Agriculture & AgriTech",
        "icon":  "🌱",
        "desc":  "Smart sensor agents, crop monitoring, irrigation automation.",
        "skills": ["coop_monitor", "crop_monitor", "irrigation_control", "livestock_monitor"],
    },
    "medical": {
        "label": "Medical & Health",
        "icon":  "🏥",
        "desc":  "On-device diagnostic assistance, patient monitoring, clinical edge tools.",
        "skills": ["patient_vitals", "air_quality"],
    },
    "smart_home": {
        "label": "Smart Home & IoT",
        "icon":  "🏠",
        "desc":  "Local AI assistants, home automation agents, context-aware control.",
        "skills": ["smart_home_control", "flood_detector", "fire_smoke_detector"],
    },
    "logistics": {
        "label": "Logistics & Supply Chain",
        "icon":  "📦",
        "desc":  "Cold chain monitoring, vehicle detection, warehouse automation.",
        "skills": ["cold_chain_monitor", "vehicle_detection"],
    },
    "security": {
        "label": "Security & Surveillance",
        "icon":  "🔒",
        "desc":  "Intrusion detection, PPE compliance, access control.",
        "skills": ["ppe_guard", "intrusion"],
    },
    "sustainability": {
        "label": "AI Sustainability & Carbon Intelligence",
        "icon":  "🌍",
        "desc":  "Real-time carbon footprint, renewable optimization, emission compliance, water footprint, and smart grid demand response.",
        "skills": [
            "carbon_footprint_monitor",
            "renewable_energy_optimizer",
            "emission_sensor_monitor",
            "water_footprint_monitor",
            "smart_grid_scheduler",
        ],
    },
}


__all__ = ["SKILL_REGISTRY", "SKILL_CATEGORIES"]
