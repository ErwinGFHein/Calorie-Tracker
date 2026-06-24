import os
from datetime import datetime, timedelta
import calendar as py_calendar
import logging
import sqlite3
import asyncio
import httpx
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load .env file if it exists
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, val = stripped.split("=", 1)
                os.environ[key.strip()] = val.strip()

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

def get_daily_metrics(conn, date_str: str = None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
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
    WHERE date(l.timestamp) = ?;
    """, (date_str,))
    totals = cursor.fetchone()
    
    total_cal = totals["total_calories"]
    total_prot = totals["total_protein"]
    total_carbs = totals["total_carbs"]
    total_fat = totals["total_fat"]
    
    cal_pct = int((total_cal / daily_cal_target) * 100) if daily_cal_target > 0 else 0
    prot_pct = int((total_prot / daily_prot_target) * 100) if daily_prot_target > 0 else 0
    carbs_pct = int((total_carbs / daily_carbs_target) * 100) if daily_carbs_target > 0 else 0
    fat_pct = int((total_fat / daily_fat_target) * 100) if daily_fat_target > 0 else 0
    
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
        "bar_widths": {
            "calories": min(100, max(0, cal_pct)),
            "protein": min(100, max(0, prot_pct)),
            "carbs": min(100, max(0, carbs_pct)),
            "fat": min(100, max(0, fat_pct))
        },
        "colors": {
            "calories": get_color_class(cal_pct),
            "protein": get_color_class(prot_pct),
            "carbs": get_color_class(carbs_pct),
            "fat": get_color_class(fat_pct)
        }
    }

def get_grouped_history(conn, date_str: str = None):
    cursor = conn.cursor()
    if date_str:
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
        WHERE date(l.timestamp) = ?
        ORDER BY l.timestamp DESC;
        """, (date_str,))
    else:
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
        if not log_date:
            log_date = row["timestamp"].split()[0] if row["timestamp"] else datetime.now().strftime("%Y-%m-%d")
            
        today = datetime.now().strftime("%Y-%m-%d")
        if log_date == today:
            day_name = "Today"
        else:
            try:
                dt = datetime.strptime(log_date, "%Y-%m-%d")
                day_name = dt.strftime("%A, %b %d")
            except (ValueError, TypeError):
                day_name = "Unknown Date"
            
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

def get_calendar_days_data(conn, start_date, end_date, target_goals, mode):
    # Retrieve targets
    daily_cal_target = target_goals.get("daily_calorie_target", 2000.0)
    daily_prot_target = target_goals.get("daily_protein_target", 150.0)
    daily_carbs_target = target_goals.get("daily_carbs_target", 200.0)
    daily_fat_target = target_goals.get("daily_fat_target", 70.0)
    
    # Query logs in the range
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        date(l.timestamp) as log_date,
        COUNT(l.id) as entry_count,
        COALESCE(SUM(l.quantity * f.calories), 0.0) as total_calories,
        COALESCE(SUM(l.quantity * f.protein), 0.0) as total_protein,
        COALESCE(SUM(l.quantity * f.carbs), 0.0) as total_carbs,
        COALESCE(SUM(l.quantity * f.fat), 0.0) as total_fat
    FROM logs l
    JOIN foods f ON l.food_id = f.id
    WHERE date(l.timestamp) BETWEEN ? AND ?
    GROUP BY date(l.timestamp);
    """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    
    db_data = {row["log_date"]: row for row in cursor.fetchall()}
    
    # Also get detailed logged items per day for the weekly view
    items_by_date = {}
    cursor.execute("""
    SELECT 
        date(l.timestamp) as log_date,
        f.name,
        l.quantity * f.calories as calories
    FROM logs l
    JOIN foods f ON l.food_id = f.id
    WHERE date(l.timestamp) BETWEEN ? AND ?
    ORDER BY l.timestamp DESC;
    """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    
    for row in cursor.fetchall():
        d_str = row["log_date"]
        if d_str not in items_by_date:
            items_by_date[d_str] = []
        items_by_date[d_str].append({
            "name": row["name"],
            "calories": round(row["calories"], 1)
        })
    
    # Fill in all dates in range
    days = []
    curr = start_date
    while curr <= end_date:
        date_str = curr.strftime("%Y-%m-%d")
        row = db_data.get(date_str)
        
        if row:
            total_cal = row["total_calories"]
            total_prot = row["total_protein"]
            total_carbs = row["total_carbs"]
            total_fat = row["total_fat"]
            entry_count = row["entry_count"]
            has_data = entry_count > 0
        else:
            total_cal = 0.0
            total_prot = 0.0
            total_carbs = 0.0
            total_fat = 0.0
            entry_count = 0
            has_data = False
            
        # Calculate closeness scores (calories, carbs, fat) and compliance percentage (protein)
        cal_score = max(0.0, 100.0 - (abs(total_cal - daily_cal_target) / daily_cal_target * 100.0)) if daily_cal_target > 0 else 0.0
        prot_score = min(100.0, (total_prot / daily_prot_target * 100.0)) if daily_prot_target > 0 else 0.0
        carbs_score = max(0.0, 100.0 - (abs(total_carbs - daily_carbs_target) / daily_carbs_target * 100.0)) if daily_carbs_target > 0 else 0.0
        fat_score = max(0.0, 100.0 - (abs(total_fat - daily_fat_target) / daily_fat_target * 100.0)) if daily_fat_target > 0 else 0.0
        
        macro_score = (prot_score + carbs_score + fat_score) / 3.0
        avg_score = (cal_score + macro_score) / 2.0
        
        # Selected score
        if mode == "calorie":
            score = cal_score
        elif mode == "macro":
            score = macro_score
        else:
            score = avg_score
            
        # Color class
        if not has_data:
            color_class = "bg-slate-900/40 text-slate-650 border border-slate-900/60"
        else:
            if score >= 85:
                color_class = "bg-emerald-500/80 text-white shadow-[0_0_8px_rgba(16,185,129,0.15)] border-transparent"
            elif score >= 70:
                color_class = "bg-teal-500/60 text-white border-transparent"
            elif score >= 50:
                color_class = "bg-amber-500/60 text-white border-transparent"
            else:
                color_class = "bg-rose-500/60 text-white shadow-[0_0_8px_rgba(244,63,94,0.15)] border-transparent"
                
        days.append({
            "date": date_str,
            "date_obj": curr,
            "day_name": curr.strftime("%A"),
            "short_day_name": curr.strftime("%a"),
            "formatted_date": curr.strftime("%b %d"),
            "total_calories": round(total_cal, 1),
            "total_protein": round(total_prot, 1),
            "total_carbs": round(total_carbs, 1),
            "total_fat": round(total_fat, 1),
            "cal_score": round(cal_score, 1),
            "macro_score": round(macro_score, 1),
            "avg_score": round(avg_score, 1),
            "score": round(score, 1),
            "has_data": has_data,
            "color_class": color_class,
            "items": items_by_date.get(date_str, [])
        })
        
        curr += timedelta(days=1)
        
    return days

@app.get("/", response_class=HTMLResponse)
def index_view(request: Request, date: str = None):
    # Parse date or default to today
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
        
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
    except (ValueError, TypeError):
        date_obj = datetime.now()
        date = date_obj.strftime("%Y-%m-%d")
        
    # Helper dates
    prev_date = (date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    formatted_selected_date = date_obj.strftime("%A, %b %d, %Y")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    if date == today_str:
        selected_day_name = "Today"
    elif date == yesterday_str:
        selected_day_name = "Yesterday"
    elif date == tomorrow_str:
        selected_day_name = "Tomorrow"
    else:
        selected_day_name = date_obj.strftime("%A")
        
    conn = get_db_connection()
    metrics = get_daily_metrics(conn, date)
    history = get_grouped_history(conn, date)
    conn.close()
    
    return templates.TemplateResponse(request, "index.html", {
        "metrics": metrics,
        "history": history,
        "active_tab": "dashboard",
        "selected_date": date,
        "formatted_selected_date": formatted_selected_date,
        "selected_day_name": selected_day_name,
        "prev_date": prev_date,
        "next_date": next_date,
        "today_date": today_str
    })

@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request, view: str = "week", mode: str = "calorie"):
    if view not in ["week", "month", "year"]:
        view = "week"
    if mode not in ["calorie", "macro", "average"]:
        mode = "calorie"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM targets;")
    targets = {row["key"]: row["value"] for row in cursor.fetchall()}
    
    today = datetime.now().date()
    spacers = []
    month_name = ""
    year_num = today.year
    
    if view == "week":
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        days = get_calendar_days_data(conn, start_of_week, end_of_week, targets, mode)
        
    elif view == "month":
        start_of_month = today.replace(day=1)
        num_spacers = start_of_month.weekday()
        spacers = list(range(num_spacers))
        
        last_day = py_calendar.monthrange(today.year, today.month)[1]
        end_of_month = today.replace(day=last_day)
        
        days = get_calendar_days_data(conn, start_of_month, end_of_month, targets, mode)
        month_name = today.strftime("%B")
        year_num = today.year
        
    else: # year view
        start_of_year_raw = today - timedelta(days=364)
        start_of_year = start_of_year_raw - timedelta(days=start_of_year_raw.weekday())
        end_of_year = today + timedelta(days=(6 - today.weekday()))
        days = get_calendar_days_data(conn, start_of_year, end_of_year, targets, mode)
        
    conn.close()
    
    return templates.TemplateResponse(request, "calendar.html", {
        "active_tab": "calendar",
        "view": view,
        "mode": mode,
        "days": days,
        "spacers": spacers,
        "month_name": month_name,
        "year_num": year_num
    })

@app.get("/config", response_class=HTMLResponse)
def config_view(request: Request, success: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM targets;")
    targets = {row["key"]: row["value"] for row in cursor.fetchall()}
    conn.close()
    
    return templates.TemplateResponse(request, "config.html", {
        "active_tab": "config",
        "targets": targets,
        "success": success
    })

async def search_openfoodfacts(query: str) -> list:
    url = f"https://br.openfoodfacts.org/cgi/search.pl?search_terms={query}&search_simple=1&action=process&json=1"
    headers = {"User-Agent": "CalorieTrackerSelfHosted/1.0 (erwin@example.com)"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                products = data.get("products", [])
                results = []
                for p in products[:5]:
                    name = p.get("product_name") or p.get("product_name_pt")
                    if not name:
                        continue
                    brand = p.get("brands")
                    full_name = f"{name} ({brand})" if brand else name
                    full_name = full_name.replace("'", "").replace('"', "").strip()
                    
                    nutr = p.get("nutriments", {})
                    cal_100g = nutr.get("energy-kcal_100g")
                    if cal_100g is None:
                        # Fallback to energy in kJ
                        energy_100g = nutr.get("energy_100g")
                        if energy_100g is not None:
                            cal_100g = float(energy_100g) / 4.184
                    if cal_100g is None:
                        continue
                        
                    prot_100g = nutr.get("proteins_100g", 0.0)
                    carbs_100g = nutr.get("carbohydrates_100g", 0.0)
                    fat_100g = nutr.get("fat_100g", 0.0)
                    
                    # Convert values per 100g to per 1g
                    calories = round(float(cal_100g) / 100.0, 4)
                    protein = round(float(prot_100g) / 100.0, 4)
                    carbs = round(float(carbs_100g) / 100.0, 4)
                    fat = round(float(fat_100g) / 100.0, 4)
                    
                    results.append({
                        "id": f"ext|{full_name}|{calories}|{protein}|{carbs}|{fat}|g",
                        "name": f"🌐 {full_name}",
                        "calories": calories,
                        "protein": protein,
                        "carbs": carbs,
                        "fat": fat,
                        "unit": "g"
                    })
                return results
    except Exception as e:
        logger.error(f"Error querying Open Food Facts: {e}")
    return []

async def search_usda(query: str) -> list:
    api_key = os.environ.get("USDA_API_KEY")
    if not api_key:
        return []
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={query}&api_key={api_key}&pageSize=5"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                foods = data.get("foods", [])
                results = []
                for f in foods:
                    name = f.get("description")
                    if not name:
                        continue
                    brand = f.get("brandOwner")
                    full_name = f"{name} ({brand})" if brand else name
                    full_name = full_name.replace("'", "").replace('"', "").strip()
                    
                    cal_100g = 0.0
                    prot_100g = 0.0
                    carbs_100g = 0.0
                    fat_100g = 0.0
                    
                    for nutr in f.get("foodNutrients", []):
                        n_id = nutr.get("nutrientId")
                        val = nutr.get("value", 0.0)
                        if n_id == 1008:
                            cal_100g = val
                        elif n_id == 1003:
                            prot_100g = val
                        elif n_id == 1005:
                            carbs_100g = val
                        elif n_id == 1004:
                            fat_100g = val
                            
                    calories = round(float(cal_100g) / 100.0, 4)
                    protein = round(float(prot_100g) / 100.0, 4)
                    carbs = round(float(carbs_100g) / 100.0, 4)
                    fat = round(float(fat_100g) / 100.0, 4)
                    
                    results.append({
                        "id": f"ext|{full_name}|{calories}|{protein}|{carbs}|{fat}|g",
                        "name": f"🇺🇸 {full_name}",
                        "calories": calories,
                        "protein": protein,
                        "carbs": carbs,
                        "fat": fat,
                        "unit": "g"
                    })
                return results
    except Exception as e:
        logger.error(f"Error querying USDA: {e}")
    return []

@app.post("/search", response_class=HTMLResponse)
async def search_foods(request: Request, search_query: str = Form(""), search_online: str = Form(None)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    local_foods = []
    if not search_query.strip():
        # Display 5 common suggestions if query is empty
        cursor.execute("SELECT id, name, calories, protein, carbs, fat, unit FROM foods ORDER BY name LIMIT 5;")
        local_results = cursor.fetchall()
        for r in local_results:
            local_foods.append({
                "id": str(r["id"]),
                "name": r["name"],
                "calories": r["calories"],
                "protein": r["protein"],
                "carbs": r["carbs"],
                "fat": r["fat"],
                "unit": r["unit"]
            })
        conn.close()
        external_foods = []
    else:
        cursor.execute("""
        SELECT id, name, calories, protein, carbs, fat, unit 
        FROM foods 
        WHERE name LIKE ? 
        LIMIT 10;
        """, (f"%{search_query.strip()}%",))
        local_results = cursor.fetchall()
        for r in local_results:
            local_foods.append({
                "id": str(r["id"]),
                "name": r["name"],
                "calories": r["calories"],
                "protein": r["protein"],
                "carbs": r["carbs"],
                "fat": r["fat"],
                "unit": r["unit"]
            })
        conn.close()
        
        # Query external APIs concurrently only if requested
        if search_online in ("on", "true", "True"):
            off_task = search_openfoodfacts(search_query.strip())
            usda_task = search_usda(search_query.strip())
            off_res, usda_res = await asyncio.gather(off_task, usda_task)
            external_foods = off_res + usda_res
        else:
            external_foods = []
        
    all_foods = local_foods + external_foods
    
    return templates.TemplateResponse(request, "search.html", {
        "foods": all_foods
    })

@app.post("/food/add")
def add_food(
    name: str = Form(...),
    calories: float = Form(...),
    protein: float = Form(0.0),
    carbs: float = Form(0.0),
    fat: float = Form(0.0),
    unit: str = Form("g"),
    redirect_to: str = Form("/")
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
        
    if redirect_to == "/config":
        return RedirectResponse(url="config?success=food", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="./", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/log/add", response_class=HTMLResponse)
def add_log(
    request: Request,
    food_id: str = Form(...),
    quantity: float = Form(...),
    log_date: str = Form(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if food_id.startswith("ext|"):
        parts = food_id.split("|")
        # ext|name|calories|protein|carbs|fat|unit
        name = parts[1]
        calories = float(parts[2])
        protein = float(parts[3])
        carbs = float(parts[4])
        fat = float(parts[5])
        unit = parts[6]
        
        # Check if it already exists locally to avoid duplicate catalog items
        cursor.execute("SELECT id FROM foods WHERE name = ?;", (name,))
        existing = cursor.fetchone()
        if existing:
            final_food_id = existing["id"]
        else:
            cursor.execute("""
            INSERT INTO foods (name, calories, protein, carbs, fat, unit)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (name, calories, protein, carbs, fat, unit))
            conn.commit()
            final_food_id = cursor.lastrowid
    else:
        final_food_id = int(food_id)
    
    if not log_date:
        log_date = datetime.now().strftime("%Y-%m-%d")
    current_time_str = datetime.now().strftime("%H:%M:%S")
    timestamp = f"{log_date} {current_time_str}"
    
    cursor.execute("""
    INSERT INTO logs (food_id, quantity, timestamp)
    VALUES (?, ?, ?);
    """, (final_food_id, quantity, timestamp))
    conn.commit()
    
    metrics = get_daily_metrics(conn, log_date)
    history = get_grouped_history(conn, log_date)
    conn.close()
    
    return templates.TemplateResponse(request, "history.html", {
        "metrics": metrics,
        "history": history,
        "selected_date": log_date
    })

@app.delete("/log/{log_id}", response_class=HTMLResponse)
def delete_log(request: Request, log_id: int, date: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM logs WHERE id = ?;", (log_id,))
    conn.commit()
    
    metrics = get_daily_metrics(conn, date)
    history = get_grouped_history(conn, date)
    conn.close()
    
    return templates.TemplateResponse(request, "history.html", {
        "metrics": metrics,
        "history": history,
        "selected_date": date
    })

@app.post("/settings/update")
def update_settings(
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
    conn.close()
    
    return RedirectResponse(url="config?success=targets", status_code=status.HTTP_303_SEE_OTHER)

async def estimate_macros_with_gemini(query: str, api_key: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{
                "text": f"Provide the estimated nutritional information for the following query: {query}. If the query specifies a quantity or unit, use that, otherwise default to a standard 100g serving size. Return clean, accurate nutritional estimates."
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "The standardized name of the food item"},
                    "calories": {"type": "NUMBER", "description": "Total calories in kcal"},
                    "protein": {"type": "NUMBER", "description": "Protein in grams"},
                    "carbs": {"type": "NUMBER", "description": "Carbohydrates in grams"},
                    "fat": {"type": "NUMBER", "description": "Fat in grams"},
                    "unit": {"type": "STRING", "description": "The serving unit, e.g. 'g', 'piece', 'serving'"},
                    "serving_size": {"type": "NUMBER", "description": "The quantity/size corresponding to these macros (e.g. 100)"},
                    "explanation": {"type": "STRING", "description": "Brief explanation/notes of how the macros were estimated"}
                },
                "required": ["name", "calories", "protein", "carbs", "fat", "unit", "serving_size", "explanation"]
            }
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Gemini API returned status {resp.status_code}: {resp.text}")
            raise Exception(f"Gemini API error: {resp.text}")
        
        data = resp.json()
        text_content = data["candidates"][0]["content"]["parts"][0]["text"]
        import json
        return json.loads(text_content)

@app.post("/food/ai-estimate", response_class=HTMLResponse)
async def ai_estimate_view(request: Request, ai_query: str = Form("")):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    if k.strip() == "GEMINI_API_KEY":
                        api_key = v.strip()
                        os.environ["GEMINI_API_KEY"] = api_key
                        
    if not api_key:
        return """
        <div class="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-xl text-xs mt-4">
            <strong>Error:</strong> GEMINI_API_KEY not found in environment variables or .env file.
        </div>
        """
        
    if not ai_query.strip():
        return """
        <div class="p-4 bg-amber-500/10 border border-amber-500/20 text-amber-300 rounded-xl text-xs mt-4">
            Please enter a food description.
        </div>
        """
        
    try:
        result = await estimate_macros_with_gemini(ai_query.strip(), api_key)
        name = result.get("name", "Unknown Food")
        calories = result.get("calories", 0.0)
        protein = result.get("protein", 0.0)
        carbs = result.get("carbs", 0.0)
        fat = result.get("fat", 0.0)
        unit = result.get("unit", "g")
        serving_size = result.get("serving_size", 100.0)
        explanation = result.get("explanation", "")
        
        escaped_name = name.replace("'", "\\'")
        
        return f"""
        <div class="mt-4 p-4 bg-slate-950/60 border border-slate-800/80 rounded-2xl space-y-3 relative overflow-hidden">
            <div class="absolute -right-12 -bottom-12 w-24 h-24 bg-indigo-500/5 rounded-full blur-2xl pointer-events-none"></div>
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="text-sm font-bold text-white flex items-center gap-1.5">
                        <span class="text-indigo-400">✨</span> AI Estimation: {name}
                    </h3>
                    <p class="text-[10px] text-slate-450 mt-0.5">Based on {serving_size}{unit} serving</p>
                </div>
                <span class="text-[9px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 font-bold uppercase tracking-wider">Gemini API</span>
            </div>
            
            <div class="grid grid-cols-4 gap-2 text-center text-xs">
                <div class="p-2 bg-slate-900/50 rounded-xl border border-slate-800/40">
                    <span class="text-slate-450 block text-[9px] uppercase tracking-wider font-bold">Calories</span>
                    <span class="font-bold text-white text-sm">{calories}</span> <span class="text-[9px] text-slate-500">kcal</span>
                </div>
                <div class="p-2 bg-slate-900/50 rounded-xl border border-slate-800/40">
                    <span class="text-slate-450 block text-[9px] uppercase tracking-wider font-bold">Protein</span>
                    <span class="font-bold text-emerald-400 text-sm">{protein}</span> <span class="text-[9px] text-slate-500">g</span>
                </div>
                <div class="p-2 bg-slate-900/50 rounded-xl border border-slate-800/40">
                    <span class="text-slate-450 block text-[9px] uppercase tracking-wider font-bold">Carbs</span>
                    <span class="font-bold text-amber-400 text-sm">{carbs}</span> <span class="text-[9px] text-slate-500">g</span>
                </div>
                <div class="p-2 bg-slate-900/50 rounded-xl border border-slate-800/40">
                    <span class="text-slate-450 block text-[9px] uppercase tracking-wider font-bold">Fat</span>
                    <span class="font-bold text-rose-400 text-sm">{fat}</span> <span class="text-[9px] text-slate-500">g</span>
                </div>
            </div>
            
            <p class="text-[11px] text-slate-400 italic font-medium leading-relaxed bg-slate-900/30 p-2.5 rounded-xl border border-slate-900/40">
                "{explanation}"
            </p>
            
            <button 
                type="button"
                onclick="fillCatalogForm('{escaped_name}', '{unit}', {calories}, {protein}, {carbs}, {fat}, {serving_size})"
                class="w-full mt-1 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs tracking-wider transition-colors flex items-center justify-center gap-1.5"
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                Pre-fill Catalog Form
            </button>
        </div>
        """
    except Exception as e:
        logger.error(f"Error in AI estimation: {e}")
        return f"""
        <div class="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-xl text-xs mt-4">
            <strong>Error:</strong> Failed to estimate macros.<br/>
            <span class="text-[10px] text-slate-500 font-mono mt-1 block">{str(e)}</span>
        </div>
        """
