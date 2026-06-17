import os
import sqlite3
import logging
import csv
import httpx

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Resolve database path
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tracker.db")
DB_PATH = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)

def get_db_connection():
    # Ensure directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def seed_foods(conn):
    url = "https://raw.githubusercontent.com/j2kun/lp-diet/main/nutrients.csv"
    logger.info(f"Downloading nutrients dataset from {url}...")
    
    # Fetch content
    response = httpx.get(url, timeout=15.0)
    if response.status_code != 200:
        raise Exception(f"HTTP error {response.status_code} fetching CSV")
        
    csv_data = response.text.splitlines()
    
    reader = csv.DictReader(csv_data)
    cursor = conn.cursor()
    
    foods_to_insert = []
    seen_names = set()
    
    for row in reader:
        name = row.get("description")
        if not name:
            continue
            
        # Clean and format description
        # Replace multiple spaces and convert UPPER case to title-ish format
        name = " ".join(name.split())
        name = name.replace(",", ", ").replace("'", "").strip()
        name = name.title()
        
        if name in seen_names:
            continue
        seen_names.add(name)
        
        try:
            # USDA data has values per 100g
            calories_100g = float(row.get("energy (kcal)", 0.0) or 0.0)
            protein_100g = float(row.get("protein (g)", 0.0) or 0.0)
            fat_100g = float(row.get("total fat (g)", 0.0) or 0.0)
            carbs_100g = float(row.get("carbohydrate (g)", 0.0) or 0.0)
        except ValueError:
            continue
            
        # Scale to 1g values
        calories = round(calories_100g / 100.0, 4)
        protein = round(protein_100g / 100.0, 4)
        fat = round(fat_100g / 100.0, 4)
        carbs = round(carbs_100g / 100.0, 4)
        
        foods_to_insert.append((name, calories, protein, carbs, fat, 'g'))
        
    if foods_to_insert:
        logger.info(f"Inserting {len(foods_to_insert)} foods into lookup database...")
        cursor.executemany("""
        INSERT OR IGNORE INTO foods (name, calories, protein, carbs, fat, unit)
        VALUES (?, ?, ?, ?, ?, ?);
        """, foods_to_insert)
        conn.commit()
        logger.info("Pre-seeding completed successfully.")

def seed_foods_fallback(conn):
    logger.info("Running fallback database seeder...")
    fallback_foods = [
        ("Chicken Breast (Raw)", 1.20, 0.225, 0.0, 0.026, 'g'),
        ("Egg (Whole, Large)", 1.43, 0.126, 0.007, 0.095, 'g'),
        ("White Rice (Cooked)", 1.30, 0.027, 0.28, 0.003, 'g'),
        ("Banana", 0.89, 0.011, 0.228, 0.003, 'g'),
        ("Apple (With Skin)", 0.52, 0.003, 0.138, 0.002, 'g'),
        ("Oats (Raw)", 3.89, 0.169, 0.66, 0.069, 'g'),
        ("Whey Protein Powder", 4.00, 0.80, 0.06, 0.06, 'g'),
        ("Whole Milk", 0.61, 0.032, 0.048, 0.033, 'g'),
        ("Broccoli (Raw)", 0.34, 0.028, 0.066, 0.004, 'g'),
        ("Olive Oil", 8.84, 0.0, 0.0, 1.0, 'g'),
        ("Almonds", 5.79, 0.21, 0.22, 0.49, 'g'),
        ("Greek Yogurt (Plain, Non-Fat)", 0.59, 0.10, 0.036, 0.004, 'g')
    ]
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT OR IGNORE INTO foods (name, calories, protein, carbs, fat, unit)
    VALUES (?, ?, ?, ?, ?, ?);
    """, fallback_foods)
    conn.commit()
    logger.info("Fallback database seeder run complete.")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Foods lookup database
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS foods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        calories REAL NOT NULL,
        protein REAL DEFAULT 0,
        carbs REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        unit TEXT DEFAULT 'g'
    );
    """)
    
    # 2. Intake logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_id INTEGER NOT NULL,
        quantity REAL NOT NULL,
        timestamp TEXT NOT NULL, -- Stored as ISO8601 string (YYYY-MM-DD HH:MM:SS)
        FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
    );
    """)
    
    # 3. Settings / Targets
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS targets (
        key TEXT PRIMARY KEY,
        value REAL NOT NULL
    );
    """)
    
    conn.commit()
    
    # Seed default target goals
    default_targets = {
        "daily_calorie_target": 2000.0,
        "daily_protein_target": 150.0,
        "daily_carbs_target": 200.0,
        "daily_fat_target": 70.0
    }
    for key, val in default_targets.items():
        cursor.execute("INSERT OR IGNORE INTO targets (key, value) VALUES (?, ?);", (key, val))
    
    conn.commit()
    
    # Pre-seed foods lookup catalog if empty
    cursor.execute("SELECT COUNT(*) FROM foods;")
    count = cursor.fetchone()[0]
    if count == 0:
        logger.info("Foods catalog is empty. Initializing pre-seeding...")
        try:
            seed_foods(conn)
        except Exception as e:
            logger.error(f"Failed to seed foods database: {e}")
            seed_foods_fallback(conn)
            
    conn.close()
