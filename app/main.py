import os
from datetime import datetime
import logging
import sqlite3
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import get_db_connection, init_db

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Self-Hosted Calorie Tracker")

# Mount static and template directories
# Ensure directories exist
os.makedirs("app/static/css", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
def startup_event():
    init_db()

def get_daily_metrics(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM targets;")
    targets = {row["key"]: row["value"] for row in cursor.fetchall()}
    
    daily_cal_target = targets.get("daily_calorie_target", 2000.0)
    daily_prot_target = targets.get("daily_protein_target", 150.0)
    daily_carbs_target = targets.get("daily_carbs_target", 200.0)
    daily_fat_target = targets.get("daily_fat_target", 70.0)
    
    cursor.execute("""
    SELECT 
        COALESCE(SUM(l.quantity * f.calories), 0.0) as total_calories,
        COALESCE(SUM(l.quantity * f.protein), 0.0) as total_protein,
        COALESCE(SUM(l.quantity * f.carbs), 0.0) as total_carbs,
        COALESCE(SUM(l.quantity * f.fat), 0.0) as total_fat
    FROM logs l
    JOIN foods f ON l.food_id = f.id
    WHERE date(l.timestamp) = date('now', 'localtime');
    """)
    totals = cursor.fetchone()
    
    total_cal = totals["total_calories"]
    total_prot = totals["total_protein"]
    total_carbs = totals["total_carbs"]
    total_fat = totals["total_fat"]
    
    cal_pct = min(100, int((total_cal / daily_cal_target) * 100)) if daily_cal_target > 0 else 0
    prot_pct = min(100, int((total_prot / daily_prot_target) * 100)) if daily_prot_target > 0 else 0
    carbs_pct = min(100, int((total_carbs / daily_carbs_target) * 100)) if daily_carbs_target > 0 else 0
    fat_pct = min(100, int((total_fat / daily_fat_target) * 100)) if daily_fat_target > 0 else 0
    
    def get_color_class(pct):
        if pct <= 100:
            return "bg-emerald-500"  # Safe / green
        else:
            return "bg-rose-500"     # Over target / red
            
    return {
        "targets": {
            "calories": daily_cal_target,
            "protein": daily_prot_target,
            "carbs": daily_carbs_target,
            "fat": daily_fat_target
        },
        "totals": {
            "calories": round(total_cal, 1),
            "protein": round(total_prot, 1),
            "carbs": round(total_carbs, 1),
            "fat": round(total_fat, 1)
        },
        "percentages": {
            "calories": cal_pct,
            "protein": prot_pct,
            "carbs": carbs_pct,
            "fat": fat_pct
        },
        "colors": {
            "calories": get_color_class(cal_pct),
            "protein": get_color_class(prot_pct),
            "carbs": get_color_class(carbs_pct),
            "fat": get_color_class(fat_pct)
        }
    }

def get_grouped_history(conn):
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        l.id as log_id, 
        l.quantity, 
        l.timestamp,
        date(l.timestamp) as log_date,
        f.id as food_id, 
        f.name, 
        f.calories, 
        f.protein, 
        f.carbs, 
        f.fat, 
        f.unit
    FROM logs l
    JOIN foods f ON l.food_id = f.id
    ORDER BY l.timestamp DESC;
    """)
    rows = cursor.fetchall()
    
    grouped = {}
    for row in rows:
        log_date = row["log_date"]
        dt = datetime.strptime(log_date, "%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        if log_date == today:
            day_name = "Today"
        else:
            day_name = dt.strftime("%A, %b %d")
            
        if day_name not in grouped:
            grouped[day_name] = {
                "date": log_date,
                "items": [],
                "totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
            }
            
        qty = row["quantity"]
        item_cal = qty * row["calories"]
        item_prot = qty * row["protein"]
        item_carbs = qty * row["carbs"]
        item_fat = qty * row["fat"]
        
        grouped[day_name]["items"].append({
            "log_id": row["log_id"],
            "food_id": row["food_id"],
            "name": row["name"],
            "quantity": qty,
            "unit": row["unit"],
            "calories": round(item_cal, 1),
            "protein": round(item_prot, 1),
            "carbs": round(item_carbs, 1),
            "fat": round(item_fat, 1),
            "time": row["timestamp"].split()[1][:5]
        })
        
        grouped[day_name]["totals"]["calories"] += item_cal
        grouped[day_name]["totals"]["protein"] += item_prot
        grouped[day_name]["totals"]["carbs"] += item_carbs
        grouped[day_name]["totals"]["fat"] += item_fat
        
    for day_name in grouped:
        for k in grouped[day_name]["totals"]:
            grouped[day_name]["totals"][k] = round(grouped[day_name]["totals"][k], 1)
            
    return grouped

@app.get("/", response_class=HTMLResponse)
def index_view(request: Request):
    conn = get_db_connection()
    metrics = get_daily_metrics(conn)
    history = get_grouped_history(conn)
    conn.close()
    
    return templates.TemplateResponse(request, "index.html", {
        "metrics": metrics,
        "history": history
    })

@app.post("/search", response_class=HTMLResponse)
def search_foods(request: Request, search_query: str = Form("")):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if not search_query.strip():
        # Display 5 common suggestions if query is empty
        cursor.execute("SELECT id, name, calories, protein, carbs, fat, unit FROM foods ORDER BY name LIMIT 5;")
    else:
        cursor.execute("""
        SELECT id, name, calories, protein, carbs, fat, unit 
        FROM foods 
        WHERE name LIKE ? 
        LIMIT 10;
        """, (f"%{search_query.strip()}%",))
        
    foods = cursor.fetchall()
    conn.close()
    
    return templates.TemplateResponse(request, "search.html", {
        "foods": foods
    })

@app.post("/food/add")
def add_food(
    name: str = Form(...),
    calories: float = Form(...),
    protein: float = Form(0.0),
    carbs: float = Form(0.0),
    fat: float = Form(0.0),
    unit: str = Form("g")
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Standardize values to per-1g if unit is grams
    if unit == "g":
        calories = calories / 100.0
        protein = protein / 100.0
        carbs = carbs / 100.0
        fat = fat / 100.0
        
    try:
        cursor.execute("""
        INSERT INTO foods (name, calories, protein, carbs, fat, unit)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (name.replace("'", "").strip(), calories, protein, carbs, fat, unit))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
        
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/log/add", response_class=HTMLResponse)
def add_log(
    request: Request,
    food_id: int = Form(...),
    quantity: float = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT INTO logs (food_id, quantity, timestamp)
    VALUES (?, ?, datetime('now', 'localtime'));
    """, (food_id, quantity))
    conn.commit()
    
    metrics = get_daily_metrics(conn)
    history = get_grouped_history(conn)
    conn.close()
    
    return templates.TemplateResponse(request, "history.html", {
        "metrics": metrics,
        "history": history
    })

@app.delete("/log/{log_id}", response_class=HTMLResponse)
def delete_log(request: Request, log_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM logs WHERE id = ?;", (log_id,))
    conn.commit()
    
    metrics = get_daily_metrics(conn)
    history = get_grouped_history(conn)
    conn.close()
    
    return templates.TemplateResponse(request, "history.html", {
        "metrics": metrics,
        "history": history
    })

@app.post("/settings/update", response_class=HTMLResponse)
def update_settings(
    request: Request,
    daily_calorie_target: float = Form(...),
    daily_protein_target: float = Form(...),
    daily_carbs_target: float = Form(...),
    daily_fat_target: float = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE targets SET value = ? WHERE key = 'daily_calorie_target';", (daily_calorie_target,))
    cursor.execute("UPDATE targets SET value = ? WHERE key = 'daily_protein_target';", (daily_protein_target,))
    cursor.execute("UPDATE targets SET value = ? WHERE key = 'daily_carbs_target';", (daily_carbs_target,))
    cursor.execute("UPDATE targets SET value = ? WHERE key = 'daily_fat_target';", (daily_fat_target,))
    conn.commit()
    
    metrics = get_daily_metrics(conn)
    history = get_grouped_history(conn)
    conn.close()
    
    return templates.TemplateResponse(request, "history.html", {
        "metrics": metrics,
        "history": history
    })
