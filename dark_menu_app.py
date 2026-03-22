import os
import csv
import json
import hashlib
import urllib.parse
import io
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "antwan-smart-csv-v4")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

# Standard Internal Format
INTERNAL_COLS = [
    "Category_EN", "Category_AR", "Category_KU",
    "Item_EN", "Item_AR", "Item_KU",
    "Description_EN", "Description_AR", "Description_KU",
    "Price"
]

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- UTILS ---
def load_menu():
    if not os.path.exists(DATA_FILE): return []
    items = []
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append({k.strip(): v.strip() for k, v in row.items()})
    except: pass
    return items

def save_menu(items):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INTERNAL_COLS)
        writer.writeheader()
        for item in items:
            writer.writerow({col: item.get(col, "") for col in INTERNAL_COLS})

def get_image_url(item_name_en):
    if not item_name_en: return "https://ui-avatars.com/api/?name=Menu&background=18181b&color=eab308"
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(digest + "."): return f"/uploads/{f}"
    if os.path.exists(os.path.join(IMAGE_DIR, f"{digest}.png")): return f"/images/{digest}.png"
    return f"https://ui-avatars.com/api/?name={urllib.parse.quote(item_name_en)}&background=18181b&color=eab308&size=512"

# --- SMART MAPPING LOGIC ---
def map_csv_row(row):
    """Attempt to map any CSV header to our internal 10-column format."""
    new_row = {col: "" for col in INTERNAL_COLS}
    for key, value in row.items():
        k = key.lower()
        # Item Names
        if any(x in k for x in ["item", "name", "title"]) and "en" in k: new_row["Item_EN"] = value
        elif any(x in k for x in ["item", "name", "title"]) and ("ar" in k or "عربي" in k): new_row["Item_AR"] = value
        elif any(x in k for x in ["item", "name", "title"]) and ("ku" in k or "کورد" in k): new_row["Item_KU"] = value
        elif any(x in k for x in ["item", "name", "title"]) and not any(lang in k for lang in ["en","ar","ku"]): new_row["Item_EN"] = value
        
        # Categories
        elif "cat" in k and "en" in k: new_row["Category_EN"] = value
        elif "cat" in k and ("ar" in k or "عربي" in k): new_row["Category_AR"] = value
        elif "cat" in k and ("ku" in k or "کورد" in k): new_row["Category_KU"] = value
        elif "cat" in k: new_row["Category_EN"] = value

        # Descriptions
        elif "desc" in k and "en" in k: new_row["Description_EN"] = value
        elif "desc" in k and ("ar" in k or "عربي" in k): new_row["Description_AR"] = value
        elif "desc" in k and ("ku" in k or "کورد" in k): new_row["Description_KU"] = value
        
        # Price
        elif "price" in k or "سعر" in k or "نرخ" in k: new_row["Price"] = value
            
    return new_row

# --- ROUTES ---
@app.route("/")
def index():
    lang = request.args.get("l", "en")
    raw_items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = sorted(list(set(item.get(cat_key, "") for item in raw_items if item.get(cat_key))))
    for item in raw_items: item['image'] = get_image_url(item.get("Item_EN", "Item"))
    
    # Template strings moved here for brevity, keep the ones from previous message
    return render_template_string(PUBLIC_HTML, items=raw_items, categories=categories, lang=lang, lang_data=LANG_MAP[lang], settings={"site_title": "Menu"})

@app.route("/admin/upload_csv", methods=["POST"])
def upload_csv():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("csv_file")
    if file:
        content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(content)
        reader = csv.DictReader(stream)
        
        # Perform the smart mapping
        processed_items = [map_csv_row(row) for row in reader]
        save_menu(processed_items)
        flash("Menu updated with smart mapping!")
    return redirect(url_for("admin_dashboard"))

# ... (Keep all other admin/login routes from the previous message) ...

# Ensure PUBLIC_HTML and ADMIN_HTML and LANG_MAP are present in your app.py
# [Insert previous PUBLIC_HTML and ADMIN_HTML strings here]

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_menu([])
    app.run(debug=True, port=5000)
