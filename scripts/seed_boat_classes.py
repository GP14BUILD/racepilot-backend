"""
Seed script to populate the boat_classes table with 30+ popular dinghy classes.

Run this script to populate the database with pre-configured boat class data including:
- Portsmouth Yardstick ratings
- Typical upwind and downwind angles for different wind speeds
- VMG targets
- Hull characteristics

Data sources:
- Portsmouth Yardstick: RYA 2024 list
- Typical angles: Class association guidelines + Olympic sailing data
- VMG targets: Calculated from PY and typical conditions
- Hull speed: sqrt(waterline_m * 0.3048) * 1.34
"""

import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import SessionLocal, BoatClass
from datetime import datetime
import math

def calculate_hull_speed(waterline_m):
    """Calculate theoretical hull speed from waterline length."""
    return math.sqrt(waterline_m * 0.3048) * 1.34

def estimate_vmg_from_py(py_rating, angle, wind_speed_range):
    """
    Estimate VMG based on Portsmouth Yardstick rating.
    Lower PY = faster boat = higher VMG

    This is a rough approximation - real VMG varies widely by conditions.
    """
    # Base speed (knots) - inversely proportional to PY
    # Reference: PY 1100 ≈ 4.5kt upwind in medium conditions
    base_speed_upwind = (1100 / py_rating) * 4.5
    base_speed_downwind = (1100 / py_rating) * 5.5

    # Adjust for wind speed range
    wind_multipliers = {
        'light': 0.7,    # 0-6kt
        'medium': 1.0,   # 6-12kt
        'fresh': 1.25,   # 12-18kt
        'strong': 1.4    # 18-30kt
    }
    multiplier = wind_multipliers.get(wind_speed_range, 1.0)

    # Calculate VMG: speed * cos(angle)
    if angle < 90:  # Upwind
        speed = base_speed_upwind * multiplier
        vmg = speed * math.cos(math.radians(angle))
    else:  # Downwind
        speed = base_speed_downwind * multiplier
        # Downwind VMG calculation (angle from wind, so 180 - angle for VMG calc)
        vmg = speed * math.cos(math.radians(180 - angle))

    return round(vmg, 2)

# Comprehensive boat class database
BOAT_CLASSES = [
    # Classic Dinghies
    {
        "name": "GP14",
        "portsmouth_yardstick": 1133,
        "waterline_length_m": 3.8,
        "description": "Classic two-person dinghy, popular for club racing",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 36},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 138}
    },
    {
        "name": "Wayfarer",
        "portsmouth_yardstick": 1102,
        "waterline_length_m": 4.27,
        "description": "Versatile cruising and racing dinghy",
        "upwind_angles": {"light": 44, "medium": 42, "fresh": 40, "strong": 38},
        "downwind_angles": {"light": 152, "medium": 148, "fresh": 144, "strong": 140}
    },
    {
        "name": "Enterprise",
        "portsmouth_yardstick": 1119,
        "waterline_length_m": 3.96,
        "description": "Popular two-person racing dinghy",
        "upwind_angles": {"light": 43, "medium": 41, "fresh": 39, "strong": 37},
        "downwind_angles": {"light": 151, "medium": 146, "fresh": 142, "strong": 138}
    },
    {
        "name": "Mirror",
        "portsmouth_yardstick": 1387,
        "waterline_length_m": 3.0,
        "description": "Popular trainer and youth racing dinghy",
        "upwind_angles": {"light": 46, "medium": 44, "fresh": 42, "strong": 40},
        "downwind_angles": {"light": 155, "medium": 150, "fresh": 145, "strong": 142}
    },
    {
        "name": "Laser",
        "portsmouth_yardstick": 1100,
        "waterline_length_m": 3.81,
        "description": "Single-handed Olympic class (ILCA 7)",
        "upwind_angles": {"light": 40, "medium": 38, "fresh": 35, "strong": 32},
        "downwind_angles": {"light": 148, "medium": 142, "fresh": 138, "strong": 135}
    },
    {
        "name": "Laser Radial",
        "portsmouth_yardstick": 1147,
        "waterline_length_m": 3.81,
        "description": "Laser with smaller sail (ILCA 6)",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 37, "strong": 34},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "Laser 4.7",
        "portsmouth_yardstick": 1207,
        "waterline_length_m": 3.81,
        "description": "Laser with smallest sail (ILCA 4)",
        "upwind_angles": {"light": 43, "medium": 41, "fresh": 38, "strong": 35},
        "downwind_angles": {"light": 151, "medium": 146, "fresh": 142, "strong": 138}
    },
    {
        "name": "420",
        "portsmouth_yardstick": 1093,
        "waterline_length_m": 3.81,
        "description": "Olympic pathway two-person trapeze dinghy",
        "upwind_angles": {"light": 40, "medium": 38, "fresh": 36, "strong": 33},
        "downwind_angles": {"light": 147, "medium": 142, "fresh": 137, "strong": 134}
    },
    {
        "name": "470",
        "portsmouth_yardstick": 966,
        "waterline_length_m": 4.09,
        "description": "Olympic two-person trapeze dinghy",
        "upwind_angles": {"light": 38, "medium": 36, "fresh": 34, "strong": 31},
        "downwind_angles": {"light": 145, "medium": 140, "fresh": 135, "strong": 132}
    },
    {
        "name": "Topper",
        "portsmouth_yardstick": 1365,
        "waterline_length_m": 3.3,
        "description": "Popular single-handed youth trainer",
        "upwind_angles": {"light": 45, "medium": 43, "fresh": 40, "strong": 38},
        "downwind_angles": {"light": 153, "medium": 148, "fresh": 143, "strong": 140}
    },

    # Modern Performance Dinghies
    {
        "name": "RS Aero 7",
        "portsmouth_yardstick": 1065,
        "waterline_length_m": 3.9,
        "description": "Modern single-handed performance dinghy (7m² sail)",
        "upwind_angles": {"light": 40, "medium": 38, "fresh": 36, "strong": 33},
        "downwind_angles": {"light": 148, "medium": 142, "fresh": 138, "strong": 135}
    },
    {
        "name": "RS Aero 9",
        "portsmouth_yardstick": 1014,
        "waterline_length_m": 3.9,
        "description": "Modern single-handed performance dinghy (9m² sail)",
        "upwind_angles": {"light": 38, "medium": 36, "fresh": 35, "strong": 32},
        "downwind_angles": {"light": 146, "medium": 140, "fresh": 136, "strong": 133}
    },
    {
        "name": "RS Feva",
        "portsmouth_yardstick": 1247,
        "waterline_length_m": 3.2,
        "description": "Two-person youth racing dinghy",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 36},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "RS 200",
        "portsmouth_yardstick": 1061,
        "waterline_length_m": 3.96,
        "description": "Fast two-person asymmetric spinnaker dinghy",
        "upwind_angles": {"light": 40, "medium": 38, "fresh": 36, "strong": 33},
        "downwind_angles": {"light": 147, "medium": 142, "fresh": 137, "strong": 134}
    },
    {
        "name": "RS 400",
        "portsmouth_yardstick": 975,
        "waterline_length_m": 4.19,
        "description": "High-performance two-person trapeze dinghy",
        "upwind_angles": {"light": 38, "medium": 36, "fresh": 34, "strong": 31},
        "downwind_angles": {"light": 145, "medium": 140, "fresh": 135, "strong": 132}
    },
    {
        "name": "RS 800",
        "portsmouth_yardstick": 852,
        "waterline_length_m": 4.88,
        "description": "High-performance skiff with trapeze",
        "upwind_angles": {"light": 36, "medium": 34, "fresh": 32, "strong": 29},
        "downwind_angles": {"light": 143, "medium": 138, "fresh": 133, "strong": 130}
    },
    {
        "name": "29er",
        "portsmouth_yardstick": 905,
        "waterline_length_m": 4.45,
        "description": "Youth Olympic pathway skiff",
        "upwind_angles": {"light": 36, "medium": 34, "fresh": 32, "strong": 29},
        "downwind_angles": {"light": 143, "medium": 138, "fresh": 133, "strong": 130}
    },
    {
        "name": "49er",
        "portsmouth_yardstick": 740,
        "waterline_length_m": 4.88,
        "description": "Olympic high-performance skiff",
        "upwind_angles": {"light": 32, "medium": 30, "fresh": 28, "strong": 25},
        "downwind_angles": {"light": 140, "medium": 135, "fresh": 130, "strong": 127}
    },
    {
        "name": "49erFX",
        "portsmouth_yardstick": 780,
        "waterline_length_m": 4.88,
        "description": "Olympic women's skiff",
        "upwind_angles": {"light": 34, "medium": 32, "fresh": 30, "strong": 27},
        "downwind_angles": {"light": 142, "medium": 137, "fresh": 132, "strong": 129}
    },

    # Single-Handers & Olympic Classes
    {
        "name": "Optimist",
        "portsmouth_yardstick": 1646,
        "waterline_length_m": 2.08,
        "description": "Junior training dinghy",
        "upwind_angles": {"light": 48, "medium": 46, "fresh": 44, "strong": 42},
        "downwind_angles": {"light": 157, "medium": 152, "fresh": 148, "strong": 145}
    },
    {
        "name": "Byte",
        "portsmouth_yardstick": 1230,
        "waterline_length_m": 3.35,
        "description": "Single-handed youth racing dinghy",
        "upwind_angles": {"light": 43, "medium": 41, "fresh": 39, "strong": 37},
        "downwind_angles": {"light": 151, "medium": 146, "fresh": 142, "strong": 138}
    },
    {
        "name": "Europe",
        "portsmouth_yardstick": 1140,
        "waterline_length_m": 3.35,
        "description": "Single-handed women's Olympic class (retired)",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 35},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "Finn",
        "portsmouth_yardstick": 1049,
        "waterline_length_m": 4.2,
        "description": "Heavyweight single-handed Olympic class",
        "upwind_angles": {"light": 40, "medium": 38, "fresh": 36, "strong": 33},
        "downwind_angles": {"light": 147, "medium": 142, "fresh": 137, "strong": 134}
    },
    {
        "name": "OK Dinghy",
        "portsmouth_yardstick": 1104,
        "waterline_length_m": 3.81,
        "description": "Single-handed classic racing dinghy",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 35},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "Solo",
        "portsmouth_yardstick": 1142,
        "waterline_length_m": 3.76,
        "description": "Single-handed racing dinghy",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 35},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "Streaker",
        "portsmouth_yardstick": 1128,
        "waterline_length_m": 3.81,
        "description": "Fast single-handed racing dinghy",
        "upwind_angles": {"light": 42, "medium": 40, "fresh": 38, "strong": 35},
        "downwind_angles": {"light": 150, "medium": 145, "fresh": 140, "strong": 137}
    },
    {
        "name": "Contender",
        "portsmouth_yardstick": 1006,
        "waterline_length_m": 4.88,
        "description": "Single-handed trapeze dinghy",
        "upwind_angles": {"light": 39, "medium": 37, "fresh": 35, "strong": 32},
        "downwind_angles": {"light": 146, "medium": 141, "fresh": 136, "strong": 133}
    },
    {
        "name": "International 14",
        "portsmouth_yardstick": 853,
        "waterline_length_m": 4.27,
        "description": "High-performance development class",
        "upwind_angles": {"light": 36, "medium": 34, "fresh": 32, "strong": 29},
        "downwind_angles": {"light": 143, "medium": 138, "fresh": 133, "strong": 130}
    },
    {
        "name": "B14",
        "portsmouth_yardstick": 807,
        "waterline_length_m": 4.27,
        "description": "Modern high-performance skiff",
        "upwind_angles": {"light": 34, "medium": 32, "fresh": 30, "strong": 27},
        "downwind_angles": {"light": 142, "medium": 137, "fresh": 132, "strong": 129}
    },
    {
        "name": "Musto Skiff",
        "portsmouth_yardstick": 848,
        "waterline_length_m": 4.55,
        "description": "Single-handed high-performance skiff",
        "upwind_angles": {"light": 36, "medium": 34, "fresh": 32, "strong": 29},
        "downwind_angles": {"light": 143, "medium": 138, "fresh": 133, "strong": 130}
    }
]

def seed_boat_classes():
    """Populate the boat_classes table with pre-configured data."""
    db = SessionLocal()

    try:
        # Check if data already exists
        existing_count = db.query(BoatClass).count()
        if existing_count > 0:
            print(f"WARNING: Database already contains {existing_count} boat classes.")
            response = input("Do you want to clear existing data and re-seed? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborting seed operation.")
                return

            # Clear existing data
            db.query(BoatClass).filter(BoatClass.is_custom == False).delete()
            db.commit()
            print("Cleared existing pre-populated boat classes")

        # Insert boat classes
        added_count = 0
        for boat_data in BOAT_CLASSES:
            # Calculate hull speed
            hull_speed = calculate_hull_speed(boat_data["waterline_length_m"]) if boat_data.get("waterline_length_m") else None

            # Calculate VMG estimates for each wind range
            upwind_vmg_light = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["upwind_angles"]["light"], 'light')
            upwind_vmg_medium = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["upwind_angles"]["medium"], 'medium')
            upwind_vmg_fresh = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["upwind_angles"]["fresh"], 'fresh')
            upwind_vmg_strong = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["upwind_angles"]["strong"], 'strong')

            downwind_vmg_light = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["downwind_angles"]["light"], 'light')
            downwind_vmg_medium = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["downwind_angles"]["medium"], 'medium')
            downwind_vmg_fresh = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["downwind_angles"]["fresh"], 'fresh')
            downwind_vmg_strong = estimate_vmg_from_py(boat_data["portsmouth_yardstick"], boat_data["downwind_angles"]["strong"], 'strong')

            boat_class = BoatClass(
                name=boat_data["name"],
                portsmouth_yardstick=boat_data["portsmouth_yardstick"],
                description=boat_data.get("description"),

                # Upwind angles
                typical_upwind_angle_light=boat_data["upwind_angles"]["light"],
                typical_upwind_angle_medium=boat_data["upwind_angles"]["medium"],
                typical_upwind_angle_fresh=boat_data["upwind_angles"]["fresh"],
                typical_upwind_angle_strong=boat_data["upwind_angles"]["strong"],

                # Downwind angles
                typical_downwind_angle_light=boat_data["downwind_angles"]["light"],
                typical_downwind_angle_medium=boat_data["downwind_angles"]["medium"],
                typical_downwind_angle_fresh=boat_data["downwind_angles"]["fresh"],
                typical_downwind_angle_strong=boat_data["downwind_angles"]["strong"],

                # VMG targets
                typical_upwind_vmg_light=upwind_vmg_light,
                typical_upwind_vmg_medium=upwind_vmg_medium,
                typical_upwind_vmg_fresh=upwind_vmg_fresh,
                typical_upwind_vmg_strong=upwind_vmg_strong,

                typical_downwind_vmg_light=downwind_vmg_light,
                typical_downwind_vmg_medium=downwind_vmg_medium,
                typical_downwind_vmg_fresh=downwind_vmg_fresh,
                typical_downwind_vmg_strong=downwind_vmg_strong,

                # Hull characteristics
                waterline_length_m=boat_data.get("waterline_length_m"),
                hull_speed_max_kn=hull_speed,

                # Metadata
                is_custom=False,
                created_by_user_id=None,
                created_at=datetime.utcnow()
            )

            db.add(boat_class)
            added_count += 1
            print(f"  + {boat_data['name']} (PY: {boat_data['portsmouth_yardstick']})")

        db.commit()
        print(f"\nSuccessfully added {added_count} boat classes to the database")

        # Print summary statistics
        print("\nBoat Class Summary:")
        print(f"  Fastest (lowest PY): {min(BOAT_CLASSES, key=lambda x: x['portsmouth_yardstick'])['name']} (PY: {min(BOAT_CLASSES, key=lambda x: x['portsmouth_yardstick'])['portsmouth_yardstick']})")
        print(f"  Slowest (highest PY): {max(BOAT_CLASSES, key=lambda x: x['portsmouth_yardstick'])['name']} (PY: {max(BOAT_CLASSES, key=lambda x: x['portsmouth_yardstick'])['portsmouth_yardstick']})")
        print(f"  Total classes: {added_count}")

    except Exception as e:
        db.rollback()
        print(f"\nERROR seeding database: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("RacePilot Boat Class Seeding Script")
    print("=" * 50)
    seed_boat_classes()
    print("\nSeeding complete!")
