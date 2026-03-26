import os
import csv
import io
import re
import json
import base64
import hashlib
import html
import urllib.request
import urllib.parse
from collections import OrderedDict
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    render_template_string,
    flash,
    send_from_directory,
    session,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# === Configuration ===
app = Flask(__name__)
port = int(os.environ.get("PORT", 8000))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-menu-key")

DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
EXPECTED_COLUMNS = ["Category", "Item Name", "Description", "Price"]
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "dall-e-3")
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Helpers ---

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)

def load_settings():
    defaults = {"site_title": "قائمة المطعم", "site_subtitle": "قائمة رقمية حديثة", "logo_path": ""}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
        except: pass
    return defaults

def load_menu():
    if not os.path.exists(DATA_FILE): return []
    items = []
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Item Name"): items.append({k.strip(): v.strip() for k, v in row.items()})
    return items

def best_image_url(item_name, category):
    digest = hashlib.sha1(item_name.encode("utf-8")).hexdigest()[:16]
    # Check uploads
    for ext in ['.png', '.jpg', '.jpeg']:
        if os.path.exists(os.path.join(UPLOAD_DIR, digest + ext)):
            return f"/uploads/{digest}{ext}"
    # Check AI generated
    if os.path.exists(os.path.join(IMAGE_DIR, f"{digest}.png")):
        return f"/images/{digest}.png"
    # Placeholder
    return f"data:image/svg+xml;charset=utf-8,{urllib.parse.quote(f'<svg xmlns=...>{item_name}</svg>')}"

# --- HTML Templates ---

BASE_HTML = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ settings.site_title }}</title>
  <style>
    :root { --bg: #09090b; --panel: #111113; --text: #fafafa; --muted: #a1a1aa; --accent: #eab308; }
    body { margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); direction: rtl; }
    .container { max-width: 800px; margin: 0 auto; padding: 20px; }
    .header { text-align: center; padding: 40px 0; }
    .category-title { color: var(--accent); border-bottom: 2px solid var(--accent); display: inline-block; margin: 30px 0 15px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
    .item-card { background: var(--panel); border-radius: 15px; overflow: hidden; border: 1px solid #27272a; }
    .item-img { width: 100%; height: 200px; object-fit: cover; background: #222; }
    .item-body { padding: 15px; }
    .item-price { color: var(--accent); font-weight: bold; float: left; }
    .admin-link { position: fixed; bottom: 10px; right: 10px; opacity: 0.3; font-size: 12px; color: white; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
        <h1>{{ settings.site_title }}</h1>
        <p>{{ settings.site_subtitle }}</p>
    </div>

    {% set last_cat = [] %}
    <div class="grid">
    {% for item in items %}
        {% if item.Category != last_cat[-1] %}
            <div style="grid-column: 1/-1"><h2 class="category-title">{{ item.Category }}</h2></div>
            {% if last_cat.append(item.Category) %}{% endif %}
        {% endif %}
        <div class="item-card">
            <img src="{{ item.ImageURL }}" class="item-img" alt="{{ item['Item Name'] }}">
            <div class="item-body">
                <span class="item-price">{{ item.Price }}</span>
                <h3>{{ item['Item Name'] }}</h3>
                <p style="color: var(--muted); font-size: 0.9em;">{{ item.Description }}</p>
            </div>
        </div>
    {% endfor %}
    </div>
    <a href="/admin" class="admin-link">Admin</a>
  </div>
</body>
</html>
"""

# --- Routes ---

@app.route("/")
def index():
    settings = load_settings()
    items = load_menu()
    view_items = [
        {**item, "ImageURL": best_image_url(item["Item Name"], item["Category"])}
        for item in items
    ]
    return render_template_string(BASE_HTML, items=view_items, settings=settings)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        if request.method == "POST" and request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        return '''<form method="post" style="text-align:center;margin-top:100px;">
                  <input name="password" type="password" placeholder="Password"><button>Login</button></form>'''
    
    if request.method == "POST":
        # Handle CSV Update
        if "csv_text" in request.form:
            raw_csv = request.form.get("csv_text")
            f = io.StringIO(raw_csv.strip())
            reader = csv.DictReader(f)
            items = [row for row in reader]
            with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS)
                writer.writeheader()
                writer.writerows(items)
            flash("Menu Updated!")

    current_menu = ""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            current_menu = f.read()

    return render_template_string("""
        <div style="background:#111;color:#eee;padding:20px;font-family:sans-serif;direction:ltr;">
            <h2>Admin Panel</h2>
            <form method="post">
                <textarea name="csv_text" style="width:100%;height:300px;background:#222;color:white;">{{csv}}</textarea>
                <br><button type="submit" style="padding:10px 20px;background:orange;">Save Menu CSV</button>
            </form>
            <hr>
            <a href="/" style="color:white;">View Menu</a> | <a href="/logout" style="color:red;">Logout</a>
        </div>
    """, csv=current_menu)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/images/<filename>")
def send_gen_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/uploads/<filename>")
def send_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
