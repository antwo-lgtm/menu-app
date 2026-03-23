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
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session, g
import sqlite3
from contextlib import closing

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-menu-secret")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
DATA_DIR = "data"                     # folder for SQLite and CSVs
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")
OPENAI_IMAGE_MODEL = "dall-e-3"       # fixed to the correct model

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "menu.db")

# Languages we support
LANGUAGES = {
    "en": {"name": "English", "table": "items_en"},
    "ar": {"name": "العربية", "table": "items_ar"},
    "ku": {"name": "Kurdî", "table": "items_ku"}
}
DEFAULT_LANG = "en"

# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def get_db():
    """Return a database connection, creating tables if needed."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        init_db(db)
    return db

def init_db(db):
    """Create tables if they don't exist."""
    for lang, info in LANGUAGES.items():
        table = info["table"]
        db.execute(f'''
            CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                price TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)

def load_settings():
    defaults = {
        "site_title": "Restaurant Menu",
        "site_subtitle": "Local digital menu",
        "logo_path": "",
    }
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update({k: data.get(k, defaults[k]) for k in defaults})
        return defaults
    except Exception:
        return defaults

def save_settings(data):
    current = load_settings()
    current.update(data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

def secure_filename_local(filename):
    filename = os.path.basename(filename)
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    return filename or "file"

def image_filename_for_item(item_name, lang):
    """Generate a unique filename for an AI-generated image."""
    digest = hashlib.sha1(f"{lang}:{item_name}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}.png"

def upload_filename_for_item(item_name, lang, original_name):
    ext = os.path.splitext(original_name)[1].lower() or ".png"
    digest = hashlib.sha1(f"{lang}:{item_name}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}{ext}"

def user_uploaded_image_url(item_name, lang):
    """Return URL of uploaded image if exists."""
    digest = hashlib.sha1(f"{lang}:{item_name}".encode("utf-8")).hexdigest()[:16]
    for name in os.listdir(UPLOAD_DIR):
        if name.startswith(digest + "."):
            return f"/uploads/{name}"
    return None

def ai_generated_image_url(item_name, lang):
    """Return URL of AI-generated image if exists."""
    filename = image_filename_for_item(item_name, lang)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}"
    return None

def placeholder_svg_data_uri(title, subtitle="Menu Item"):
    """Fallback SVG placeholder."""
    title = html.escape(title)
    subtitle = html.escape(subtitle)
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='768' height='512'>
      <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='#171717'/>
          <stop offset='100%' stop-color='#27272a'/>
        </linearGradient>
      </defs>
      <rect width='100%' height='100%' fill='url(#bg)'/>
      <circle cx='640' cy='100' r='110' fill='#3f3f46' opacity='0.35'/>
      <circle cx='130' cy='420' r='140' fill='#52525b' opacity='0.25'/>
      <text x='50%' y='46%' dominant-baseline='middle' text-anchor='middle' fill='#fafafa' font-size='34' font-family='Tahoma, Arial'>{title}</text>
      <text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle' fill='#a1a1aa' font-size='20' font-family='Tahoma, Arial'>{subtitle}</text>
    </svg>
    """.strip()
    encoded = urllib.parse.quote(svg)
    return f"data:image/svg+xml;charset=utf-8,{encoded}"

def best_image_url(item_name, lang):
    uploaded = user_uploaded_image_url(item_name, lang)
    if uploaded:
        return uploaded
    generated = ai_generated_image_url(item_name, lang)
    if generated:
        return generated
    return placeholder_svg_data_uri(item_name, LANGUAGES[lang]["name"])

def generate_image_prompt(item_name, category, lang):
    """Create prompt for DALL-E, using English name for best results."""
    return (
        f"Restaurant menu photo of '{item_name}' from category '{category}'. "
        f"Dark elegant food photography, realistic plated presentation, centered composition, "
        f"premium restaurant style, studio lighting, clean background, no text, no watermark."
    )

def generate_item_image(item_name, category, lang):
    """Generate image using OpenAI DALL-E 3."""
    client = get_openai_client()
    if client is None:
        return None
    filename = image_filename_for_item(item_name, lang)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}"

    prompt = generate_image_prompt(item_name, category, lang)
    try:
        result = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        first = result.data[0]
        image_b64 = getattr(first, "b64_json", None) if not isinstance(first, dict) else first.get("b64_json")
        image_url = getattr(first, "url", None) if not isinstance(first, dict) else first.get("url")

        if image_b64:
            with open(path, "wb") as f:
                f.write(base64.b64decode(image_b64))
            return f"/images/{filename}"
        if image_url:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            return f"/images/{filename}"
    except Exception as e:
        app.logger.error(f"Image generation failed for {item_name} ({lang}): {e}")
    return None

def is_admin():
    return session.get("is_admin") is True

def require_admin():
    if not is_admin():
        return redirect(url_for("admin_login"))

# ----------------------------------------------------------------------
# CSV helpers
# ----------------------------------------------------------------------
def parse_csv_text(text):
    """Parse CSV and return list of dicts with expected columns."""
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [col for col in ["Category", "Item Name", "Description", "Price"] if col not in headers]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    items = []
    for row in reader:
        row = {k.strip(): v.strip() for k, v in row.items()}
        item = {
            "category": row.get("Category", ""),
            "name": row.get("Item Name", ""),
            "description": row.get("Description", ""),
            "price": row.get("Price", ""),
        }
        if not item["name"]:
            continue
        items.append(item)
    return items

def import_csv_to_db(lang, file_content, mode="replace"):
    """Import CSV into database for given language.
    mode: 'replace' (deletes all existing items for that language) or 'append' (adds new items,
          updating existing ones by name).
    """
    items = parse_csv_text(file_content)
    db = get_db()
    table = LANGUAGES[lang]["table"]

    if mode == "replace":
        db.execute(f"DELETE FROM {table}")
        db.commit()

    for item in items:
        # Check if item already exists (by name)
        cur = db.execute(f"SELECT id FROM {table} WHERE name = ?", (item["name"],))
        existing = cur.fetchone()
        if existing:
            db.execute(
                f"UPDATE {table} SET category = ?, description = ?, price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (item["category"], item["description"], item["price"], existing["id"])
            )
        else:
            db.execute(
                f"INSERT INTO {table} (category, name, description, price) VALUES (?, ?, ?, ?)",
                (item["category"], item["name"], item["description"], item["price"])
            )
    db.commit()

def export_db_to_csv(lang):
    """Return CSV content of all items for a language."""
    db = get_db()
    table = LANGUAGES[lang]["table"]
    rows = db.execute(f"SELECT category, name, description, price FROM {table} ORDER BY category, name").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Category", "Item Name", "Description", "Price"])
    for row in rows:
        writer.writerow([row["category"], row["name"], row["description"], row["price"]])
    return output.getvalue()

# ----------------------------------------------------------------------
# Admin authentication routes
# ----------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Logged in.")
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password.")
    content = render_template_string('''
    <div class="card" style="max-width:500px;margin:60px auto;">
      <h1 style="margin-top:0">Admin Login</h1>
      <p class="sub">Enter your admin password.</p>
      <form method="post">
        <div class="field-label">Password</div>
        <input class="input" type="password" name="password" placeholder="Password">
        <button class="btn" type="submit">Login</button>
      </form>
      <p class="tiny">Default password is 1234 unless you change MENU_ADMIN_PASSWORD.</p>
    </div>
    ''')
    return render_page("Admin Login", content, public_nav=True)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))

# ----------------------------------------------------------------------
# Admin dashboard and item management
# ----------------------------------------------------------------------
@app.route("/admin")
def admin_dashboard():
    guard = require_admin()
    if guard:
        return guard
    db = get_db()
    counts = {}
    for lang, info in LANGUAGES.items():
        count = db.execute(f"SELECT COUNT(*) as c FROM {info['table']}").fetchone()["c"]
        counts[lang] = count
    content = render_template_string('''
    <div class="hero">
      <div class="card">
        <h1 class="headline">Admin Dashboard</h1>
        <p class="sub">Manage items, import CSV, upload logo, and generate images.</p>
      </div>
      <div class="card">
        <div class="stats">
          <div class="stat"><div class="num">{{ counts.en }}</div><div class="lbl">English items</div></div>
          <div class="stat"><div class="num">{{ counts.ar }}</div><div class="lbl">العربية items</div></div>
          <div class="stat"><div class="num">{{ counts.ku }}</div><div class="lbl">Kurdî items</div></div>
        </div>
      </div>
    </div>
    <div class="row2">
      <a class="card" href="{{ url_for('admin_items', lang='en') }}"><h2 style="margin-top:0">English Menu</h2><p class="sub">View, edit, add, delete items</p></a>
      <a class="card" href="{{ url_for('admin_items', lang='ar') }}"><h2 style="margin-top:0">العربية Menu</h2><p class="sub">View, edit, add, delete items</p></a>
      <a class="card" href="{{ url_for('admin_items', lang='ku') }}"><h2 style="margin-top:0">Kurdî Menu</h2><p class="sub">View, edit, add, delete items</p></a>
      <a class="card" href="{{ url_for('admin_import') }}"><h2 style="margin-top:0">Import CSV</h2><p class="sub">Replace or append CSV for any language</p></a>
      <a class="card" href="{{ url_for('admin_export') }}"><h2 style="margin-top:0">Export CSV</h2><p class="sub">Download menu for any language</p></a>
      <a class="card" href="{{ url_for('admin_settings') }}"><h2 style="margin-top:0">Settings</h2><p class="sub">Change title, subtitle, logo</p></a>
      <a class="card" href="{{ url_for('generate_images_page') }}"><h2 style="margin-top:0">AI Images</h2><p class="sub">Generate images for items (per language)</p></a>
    </div>
    ''', counts=counts)
    return render_page("Admin Dashboard", content, public_nav=False)

@app.route("/admin/items/<lang>")
def admin_items(lang):
    if lang not in LANGUAGES:
        flash("Invalid language")
        return redirect(url_for("admin_dashboard"))
    guard = require_admin()
    if guard:
        return guard

    db = get_db()
    table = LANGUAGES[lang]["table"]
    rows = db.execute(f"SELECT * FROM {table} ORDER BY category, name").fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["image_url"] = best_image_url(item["name"], lang)
        items.append(item)

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Manage {{ lang_name }} Menu</h1>
      <p class="sub"><a href="{{ url_for('admin_add_item', lang=lang) }}" class="btn" style="display:inline-block;">+ Add New Item</a></p>
    </div>
    <div class="card" style="overflow:auto;">
      <table style="width:100%">
        <thead>
          <tr>
            <th>Image</th>
            <th>Category</th>
            <th>Name</th>
            <th>Description</th>
            <th>Price</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td><img class="thumb" src="{{ item.image_url }}" alt="{{ item.name }}"></td>
            <td>{{ item.category }}</td>
            <td>{{ item.name }}</td>
            <td>{{ item.description or '' }}</td>
            <td>{{ item.price or '' }}</td>
            <td>
              <a href="{{ url_for('admin_edit_item', lang=lang, item_id=item.id) }}" class="btn secondary small">Edit</a>
              <a href="{{ url_for('admin_delete_item', lang=lang, item_id=item.id) }}" class="btn secondary small" onclick="return confirm('Delete this item?')">Delete</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    ''', lang=lang, lang_name=LANGUAGES[lang]["name"], items=items)
    return render_page(f"Items ({LANGUAGES[lang]['name']})", content, public_nav=False)

@app.route("/admin/add_item/<lang>", methods=["GET", "POST"])
def admin_add_item(lang):
    if lang not in LANGUAGES:
        flash("Invalid language")
        return redirect(url_for("admin_dashboard"))
    guard = require_admin()
    if guard:
        return guard

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        if not name:
            flash("Name is required")
            return redirect(url_for("admin_add_item", lang=lang))
        db = get_db()
        table = LANGUAGES[lang]["table"]
        try:
            db.execute(f"INSERT INTO {table} (category, name, description, price) VALUES (?, ?, ?, ?)",
                       (category, name, description, price))
            db.commit()
            flash("Item added successfully.")
        except sqlite3.IntegrityError:
            flash("Item with this name already exists.")
        return redirect(url_for("admin_items", lang=lang))

    content = render_template_string('''
    <div class="card" style="max-width:800px;margin:0 auto;">
      <h1 style="margin-top:0">Add New Item ({{ lang_name }})</h1>
      <form method="post">
        <div class="field-label">Category</div>
        <input class="input" type="text" name="category" placeholder="e.g., Appetizers">
        <div class="field-label">Item Name *</div>
        <input class="input" type="text" name="name" required>
        <div class="field-label">Description</div>
        <textarea class="input" name="description" rows="3"></textarea>
        <div class="field-label">Price</div>
        <input class="input" type="text" name="price" placeholder="e.g., 10.00">
        <button class="btn" type="submit">Save Item</button>
        <a href="{{ url_for('admin_items', lang=lang) }}" class="btn secondary">Cancel</a>
      </form>
    </div>
    ''', lang=lang, lang_name=LANGUAGES[lang]["name"])
    return render_page(f"Add Item ({LANGUAGES[lang]['name']})", content, public_nav=False)

@app.route("/admin/edit_item/<lang>/<int:item_id>", methods=["GET", "POST"])
def admin_edit_item(lang, item_id):
    if lang not in LANGUAGES:
        flash("Invalid language")
        return redirect(url_for("admin_dashboard"))
    guard = require_admin()
    if guard:
        return guard

    db = get_db()
    table = LANGUAGES[lang]["table"]
    item = db.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if not item:
        flash("Item not found")
        return redirect(url_for("admin_items", lang=lang))

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        if not name:
            flash("Name is required")
            return redirect(url_for("admin_edit_item", lang=lang, item_id=item_id))
        try:
            db.execute(f"UPDATE {table} SET category = ?, name = ?, description = ?, price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                       (category, name, description, price, item_id))
            db.commit()
            flash("Item updated.")
        except sqlite3.IntegrityError:
            flash("Another item with this name already exists.")
        return redirect(url_for("admin_items", lang=lang))

    content = render_template_string('''
    <div class="card" style="max-width:800px;margin:0 auto;">
      <h1 style="margin-top:0">Edit Item ({{ lang_name }})</h1>
      <form method="post">
        <div class="field-label">Category</div>
        <input class="input" type="text" name="category" value="{{ item.category }}">
        <div class="field-label">Item Name *</div>
        <input class="input" type="text" name="name" value="{{ item.name }}" required>
        <div class="field-label">Description</div>
        <textarea class="input" name="description" rows="3">{{ item.description or '' }}</textarea>
        <div class="field-label">Price</div>
        <input class="input" type="text" name="price" value="{{ item.price or '' }}">
        <button class="btn" type="submit">Save Changes</button>
        <a href="{{ url_for('admin_items', lang=lang) }}" class="btn secondary">Cancel</a>
      </form>
    </div>
    ''', lang=lang, lang_name=LANGUAGES[lang]["name"], item=item)
    return render_page(f"Edit Item ({LANGUAGES[lang]['name']})", content, public_nav=False)

@app.route("/admin/delete_item/<lang>/<int:item_id>")
def admin_delete_item(lang, item_id):
    if lang not in LANGUAGES:
        flash("Invalid language")
        return redirect(url_for("admin_dashboard"))
    guard = require_admin()
    if guard:
        return guard
    db = get_db()
    table = LANGUAGES[lang]["table"]
    db.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
    db.commit()
    flash("Item deleted.")
    return redirect(url_for("admin_items", lang=lang))

# ----------------------------------------------------------------------
# CSV import/export
# ----------------------------------------------------------------------
@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    guard = require_admin()
    if guard:
        return guard

    if request.method == "POST":
        lang = request.form.get("lang")
        if lang not in LANGUAGES:
            flash("Invalid language")
            return redirect(url_for("admin_import"))
        mode = request.form.get("mode", "append")
        file = request.files.get("csv_file")
        if not file or not file.filename:
            flash("Please select a CSV file.")
            return redirect(url_for("admin_import"))
        content = file.read().decode("utf-8-sig", errors="replace")
        try:
            import_csv_to_db(lang, content, mode)
            flash(f"Imported {lang} menu successfully (mode: {mode}).")
        except Exception as e:
            flash(f"Import failed: {e}")
        return redirect(url_for("admin_import"))

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Import CSV</h1>
      <p class="sub">Upload a CSV file with columns: <strong>Category, Item Name, Description, Price</strong>.</p>
    </div>
    <div class="card">
      <form method="post" enctype="multipart/form-data">
        <div class="field-label">Language</div>
        <select class="select" name="lang">
          <option value="en">English</option>
          <option value="ar">العربية</option>
          <option value="ku">Kurdî</option>
        </select>
        <div class="field-label">Mode</div>
        <select class="select" name="mode">
          <option value="replace">Replace all items (delete existing)</option>
          <option value="append">Append/update (match by name, keep others)</option>
        </select>
        <div class="field-label">CSV file</div>
        <input class="file" type="file" name="csv_file" accept=".csv" required>
        <button class="btn" type="submit">Import</button>
      </form>
    </div>
    ''')
    return render_page("Import CSV", content, public_nav=False)

@app.route("/admin/export")
def admin_export():
    guard = require_admin()
    if guard:
        return guard
    lang = request.args.get("lang", "en")
    if lang not in LANGUAGES:
        flash("Invalid language")
        return redirect(url_for("admin_dashboard"))
    csv_data = export_db_to_csv(lang)
    response = app.response_class(
        response=csv_data,
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=menu_{lang}.csv"}
    )
    return response

# ----------------------------------------------------------------------
# Settings (logo, title)
# ----------------------------------------------------------------------
@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    guard = require_admin()
    if guard:
        return guard
    settings = load_settings()
    if request.method == "POST":
        updates = {
            "site_title": request.form.get("site_title", "").strip() or settings["site_title"],
            "site_subtitle": request.form.get("site_subtitle", "").strip() or settings["site_subtitle"],
        }
        logo = request.files.get("logo_file")
        if logo and logo.filename:
            safe = secure_filename_local(logo.filename)
            ext = os.path.splitext(safe)[1].lower() or ".png"
            logo_name = f"site_logo{ext}"
            logo_path = os.path.join(UPLOAD_DIR, logo_name)
            logo.save(logo_path)
            updates["logo_path"] = f"/uploads/{logo_name}"
        save_settings(updates)
        flash("Settings updated.")
        return redirect(url_for("admin_settings"))

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Site Settings</h1>
      <form method="post" enctype="multipart/form-data">
        <div class="row2">
          <div>
            <div class="field-label">Main title</div>
            <input class="input" type="text" name="site_title" value="{{ settings.site_title }}">
          </div>
          <div>
            <div class="field-label">Subtitle</div>
            <input class="input" type="text" name="site_subtitle" value="{{ settings.site_subtitle }}">
          </div>
        </div>
        <div class="field-label" style="margin-top:10px;">Logo</div>
        <input class="file" type="file" name="logo_file" accept="image/*">
        {% if settings.logo_path %}
          <div style="margin:14px 0;"><img src="{{ settings.logo_path }}" alt="Logo" style="width:90px;height:90px;object-fit:cover;border-radius:16px;"></div>
        {% endif %}
        <button class="btn" type="submit">Save Settings</button>
      </form>
    </div>
    ''', settings=settings)
    return render_page("Admin Settings", content, public_nav=False)

# ----------------------------------------------------------------------
# Image management (upload and AI generation)
# ----------------------------------------------------------------------
@app.route("/admin/upload-item-image/<lang>/<int:item_id>", methods=["POST"])
def admin_upload_item_image(lang, item_id):
    guard = require_admin()
    if guard:
        return guard
    db = get_db()
    table = LANGUAGES[lang]["table"]
    item = db.execute(f"SELECT name FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if not item:
        flash("Item not found")
        return redirect(url_for("admin_items", lang=lang))
    uploaded = request.files.get("item_image")
    if not uploaded or not uploaded.filename:
        flash("No image provided.")
        return redirect(url_for("admin_items", lang=lang))
    filename = upload_filename_for_item(item["name"], lang, uploaded.filename)
    uploaded.save(os.path.join(UPLOAD_DIR, filename))
    # Update the database with the image path (optional, we just rely on filename)
    flash(f"Image uploaded for {item['name']}.")
    return redirect(url_for("admin_items", lang=lang))

@app.route("/admin/generate-images", methods=["GET", "POST"])
def generate_images_page():
    guard = require_admin()
    if guard:
        return guard

    if request.method == "POST":
        lang = request.form.get("lang", "en")
        if lang not in LANGUAGES:
            flash("Invalid language")
            return redirect(url_for("generate_images_page"))
        limit_raw = request.form.get("limit", "12").strip()
        only_missing = request.form.get("only_missing") == "on"
        try:
            limit = max(1, min(100, int(limit_raw)))
        except Exception:
            limit = 12
        client = get_openai_client()
        if client is None:
            flash("OPENAI_API_KEY not found. Manual uploads still work.")
            return redirect(url_for("generate_images_page"))

        db = get_db()
        table = LANGUAGES[lang]["table"]
        # Fetch items that need images
        if only_missing:
            # We need to check for both uploaded and AI images
            items = db.execute(f"SELECT name, category FROM {table}").fetchall()
            missing = []
            for item in items:
                if not user_uploaded_image_url(item["name"], lang) and not ai_generated_image_url(item["name"], lang):
                    missing.append(item)
        else:
            missing = db.execute(f"SELECT name, category FROM {table}").fetchall()

        generated = 0
        for item in missing[:limit]:
            try:
                if generate_item_image(item["name"], item["category"], lang):
                    generated += 1
            except Exception as e:
                flash(f"Failed on {item['name']}: {e}")
                break
        flash(f"Images generated: {generated}. (Language: {LANGUAGES[lang]['name']})")
        return redirect(url_for("generate_images_page"))

    # Show preview of items with images (first 12)
    db = get_db()
    preview = []
    for lang_code, info in LANGUAGES.items():
        rows = db.execute(f"SELECT name, category, price FROM {info['table']} LIMIT 4").fetchall()
        for row in rows:
            preview.append({
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "image_url": best_image_url(row["name"], lang_code),
                "lang": lang_code
            })

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">AI Image Generation</h1>
      <p class="sub">Generate images using DALL-E 3. Images are stored per language (different names may produce different images).</p>
    </div>
    <div class="card">
      <form method="post">
        <div class="row">
          <div>
            <div class="field-label">Language</div>
            <select class="select" name="lang">
              <option value="en">English</option>
              <option value="ar">العربية</option>
              <option value="ku">Kurdî</option>
            </select>
          </div>
          <div>
            <div class="field-label">Limit</div>
            <input class="input" type="number" name="limit" value="12" min="1" max="100">
          </div>
          <div>
            <div class="field-label">Options</div>
            <label style="display:flex;gap:8px;align-items:center;padding:14px;border-radius:16px;border:1px solid var(--line);background:#101014;">
              <input type="checkbox" name="only_missing" checked>
              <span>Only items without image</span>
            </label>
          </div>
          <div>
            <div class="field-label">&nbsp;</div>
            <button class="btn" type="submit">Generate</button>
          </div>
        </div>
      </form>
    </div>
    <div class="section-title"><h2>Preview (4 per language)</h2></div>
    <div class="menu-grid">
      {% for item in preview %}
      <article class="menu-item">
        <img class="menu-image" src="{{ item.image_url }}" alt="{{ item.name }}">
        <div class="menu-body">
          <div class="menu-top">
            <h3 class="menu-name">{{ item.name }}</h3>
            {% if item.price %}<div class="price">{{ item.price }} د.ع</div>{% endif %}
          </div>
          <span class="menu-cat">{{ item.category or 'بدون قسم' }} ({{ LANGUAGES[item.lang].name }})</span>
        </div>
      </article>
      {% endfor %}
    </div>
    ''', preview=preview, LANGUAGES=LANGUAGES)
    return render_page("AI Images", content, public_nav=False)

# ----------------------------------------------------------------------
# Public menu with language selection
# ----------------------------------------------------------------------
@app.route("/")
def index():
    # Language selector from query string or default
    lang = request.args.get("lang", DEFAULT_LANG)
    if lang not in LANGUAGES:
        lang = DEFAULT_LANG

    db = get_db()
    table = LANGUAGES[lang]["table"]
    items = db.execute(f"SELECT * FROM {table} ORDER BY category, name").fetchall()
    q = request.args.get("q", "").strip().lower()
    selected_category = request.args.get("category", "").strip()

    # Build categories list
    categories = set()
    for item in items:
        cat = item["category"] or "بدون قسم"
        categories.add(cat)
    categories = sorted(categories)

    filtered = []
    for item in items:
        blob = " ".join([item["category"], item["name"], item["description"], item["price"]]).lower()
        if q and q not in blob:
            continue
        actual_cat = item["category"] or "بدون قسم"
        if selected_category and actual_cat != selected_category:
            continue
        filtered.append(dict(item))

    # Group by category
    grouped = OrderedDict()
    for item in filtered:
        cat = item["category"] or "بدون قسم"
        item["image_url"] = best_image_url(item["name"], lang)
        grouped.setdefault(cat, []).append(item)

    total_items = len(filtered)
    total_categories = len(grouped)
    with_images = sum(1 for item in filtered if user_uploaded_image_url(item["name"], lang) or ai_generated_image_url(item["name"], lang))

    content = render_template_string('''
    <div class="hero">
      <div class="card">
        <h1 class="headline">{{ settings.site_title }}</h1>
        <p class="sub">{{ settings.site_subtitle }}</p>
        <div class="stats">
          <div class="stat"><div class="num">{{ total_items }}</div><div class="lbl">عدد الأصناف</div></div>
          <div class="stat"><div class="num">{{ total_categories }}</div><div class="lbl">عدد الأقسام</div></div>
          <div class="stat"><div class="num">{{ with_images }}</div><div class="lbl">صور جاهزة</div></div>
        </div>
      </div>
      <div class="card search-card">
        <form method="get">
          <div class="row">
            <div>
              <div class="field-label">بحث</div>
              <input class="input" type="text" name="q" value="{{ q }}" placeholder="ابحث عن صنف أو قسم...">
            </div>
            <div>
              <div class="field-label">القسم</div>
              <select class="select" name="category">
                <option value="">كل الأقسام</option>
                {% for cat in categories %}
                  <option value="{{ cat }}" {% if cat == selected_category %}selected{% endif %}>{{ cat }}</option>
                {% endfor %}
              </select>
            </div>
            <div>
              <div class="field-label">&nbsp;</div>
              <button class="btn" type="submit">عرض</button>
            </div>
          </div>
          <input type="hidden" name="lang" value="{{ lang }}">
        </form>
      </div>
    </div>

    <div class="language-tabs">
      {% for code, info in LANGUAGES.items() %}
        <a class="lang-chip {% if code == lang %}active{% endif %}" href="{{ url_for('index', lang=code, q=q, category=selected_category) }}">{{ info.name }}</a>
      {% endfor %}
    </div>

    <div class="category-chips">
      <a class="chip {% if not selected_category %}active{% endif %}" href="{{ url_for('index', lang=lang, q=q) }}">الكل</a>
      {% for cat in categories %}
        <a class="chip {% if cat == selected_category %}active{% endif %}" href="{{ url_for('index', lang=lang, q=q, category=cat) }}">{{ cat }}</a>
      {% endfor %}
    </div>

    {% if grouped %}
      {% for cat, rows in grouped.items() %}
        <div class="section-title">
          <h2>{{ cat }}</h2>
          <div class="count">{{ rows|length }} صنف</div>
        </div>
        <div class="menu-grid">
          {% for item in rows %}
            <article class="menu-item">
              <img class="menu-image" src="{{ item.image_url }}" alt="{{ item.name }}">
              <div class="menu-body">
                <div class="menu-top">
                  <h3 class="menu-name">{{ item.name }}</h3>
                  {% if item.price %}
                    <div class="price">{{ item.price }} د.ع</div>
                  {% endif %}
                </div>
                <p class="menu-desc">{{ item.description or '' }}</p>
                <span class="menu-cat">{{ item.category or 'بدون قسم' }}</span>
              </div>
            </article>
          {% endfor %}
        </div>
      {% endfor %}
    {% else %}
      <div class="card">لا توجد أصناف مطابقة.</div>
    {% endif %}
    ''', settings=load_settings(), lang=lang, q=q, selected_category=selected_category,
        categories=categories, grouped=grouped, total_items=total_items,
        total_categories=total_categories, with_images=with_images, LANGUAGES=LANGUAGES)
    return render_page("Menu", content, public_nav=True)

# ----------------------------------------------------------------------
# Static file serving
# ----------------------------------------------------------------------
@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ----------------------------------------------------------------------
# Base template and rendering
# ----------------------------------------------------------------------
BASE_HTML = r'''
<!doctype html>
<html lang="en" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg: #09090b;
      --panel: #111113;
      --panel-2: #18181b;
      --line: #27272a;
      --text: #fafafa;
      --muted: #a1a1aa;
      --accent: #eab308;
      --accent-2: #f59e0b;
      --shadow: 0 10px 30px rgba(0,0,0,.28);
      --radius: 20px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Tahoma, Arial, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(234,179,8,.09), transparent 22%),
        radial-gradient(circle at left bottom, rgba(245,158,11,.06), transparent 20%),
        var(--bg);
      color: var(--text);
    }
    a { color: inherit; text-decoration: none; }
    .topbar {
      position: sticky; top: 0; z-index: 30;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 14px 20px; backdrop-filter: blur(14px);
      background: rgba(9,9,11,.72); border-bottom: 1px solid rgba(255,255,255,.06);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-badge {
      width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: black; font-weight: 900;
      overflow: hidden;
    }
    .brand-badge img { width: 100%; height: 100%; object-fit: cover; }
    .nav { display: flex; flex-wrap: wrap; gap: 10px; }
    .nav a {
      padding: 10px 14px; border-radius: 999px; background: #17171a;
      border: 1px solid var(--line); color: #e4e4e7;
    }
    .container { max-width: 1320px; margin: 0 auto; padding: 24px 16px 40px; }
    .hero { display: grid; grid-template-columns: 1.2fr .8fr; gap: 18px; margin-bottom: 22px; }
    .card {
      background: linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,.01));
      border: 1px solid rgba(255,255,255,.07); border-radius: var(--radius);
      box-shadow: var(--shadow); padding: 22px;
    }
    .headline { font-size: clamp(28px, 4vw, 48px); line-height: 1.05; margin: 0 0 10px; font-weight: 800; }
    .sub { margin: 0; color: var(--muted); line-height: 1.8; font-size: 15px; }
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }
    .stat { padding: 14px; border-radius: 16px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.06); }
    .stat .num { font-size: 24px; font-weight: 800; margin-bottom: 6px; }
    .stat .lbl { color: var(--muted); font-size: 13px; }
    .search-card { display: flex; flex-direction: column; justify-content: center; }
    .field-label { color: var(--muted); font-size: 13px; margin-bottom: 7px; }
    .row { display: grid; grid-template-columns: 1.2fr .8fr auto; gap: 12px; align-items: end; }
    .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .input, .select, .btn, .file, textarea {
      width: 100%; border-radius: 16px; border: 1px solid var(--line);
      background: #101014; color: var(--text); padding: 13px 14px; font-size: 15px; outline: none;
    }
    textarea { min-height: 120px; resize: vertical; }
    .btn {
      cursor: pointer; background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #111; font-weight: 800; border: none; min-width: 140px;
    }
    .btn.secondary { background: #17171a; color: var(--text); border: 1px solid var(--line); }
    .btn.small { padding: 6px 12px; min-width: auto; font-size: 12px; }
    .flash {
      background: rgba(234,179,8,.12); color: #fcd34d; border: 1px solid rgba(234,179,8,.25);
      padding: 12px 14px; border-radius: 14px; margin-bottom: 16px;
    }
    .category-chips { display: flex; gap: 10px; overflow: auto; padding-bottom: 4px; margin: 16px 0 18px; }
    .language-tabs { display: flex; gap: 12px; justify-content: center; margin: 20px 0 10px; }
    .lang-chip {
      background: #141418; border: 1px solid var(--line); border-radius: 40px;
      padding: 8px 18px; font-weight: bold; transition: all 0.2s;
    }
    .lang-chip.active { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #111; border-color: transparent; }
    .chip {
      white-space: nowrap; padding: 11px 15px; border-radius: 999px; background: #141418;
      border: 1px solid var(--line); color: #d4d4d8; display: inline-flex; align-items: center; gap: 8px;
    }
    .chip.active { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #111; border-color: transparent; font-weight: 800; }
    .section-title { margin: 34px 0 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .section-title h2 { margin: 0; font-size: 26px; }
    .section-title .count { color: var(--muted); font-size: 13px; }
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(245px, 1fr)); gap: 16px; }
    .menu-item {
      overflow: hidden; border-radius: 22px;
      background: linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,.01));
      border: 1px solid rgba(255,255,255,.07); box-shadow: var(--shadow);
    }
    .menu-image { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; display: block; background: #0f0f12; }
    .menu-body { padding: 14px 14px 16px; }
    .menu-top { display: flex; justify-content: space-between; gap: 10px; align-items: start; margin-bottom: 8px; }
    .menu-name { margin: 0; font-size: 18px; line-height: 1.5; font-weight: 800; }
    .price {
      white-space: nowrap; padding: 7px 10px; border-radius: 999px; background: rgba(234,179,8,.12);
      color: #fcd34d; border: 1px solid rgba(234,179,8,.18); font-weight: 800; font-size: 14px;
    }
    .menu-desc { margin: 0; color: var(--muted); line-height: 1.7; min-height: 24px; font-size: 14px; }
    .menu-cat {
      display: inline-block; margin-top: 12px; padding: 7px 10px; border-radius: 999px;
      background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.06); color: #d4d4d8; font-size: 12px;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: right; vertical-align: top; }
    th { color: var(--muted); font-size: 13px; }
    .thumb { width: 56px; height: 56px; border-radius: 12px; object-fit: cover; background: #111; }
    .tiny { color: var(--muted); font-size: 12px; line-height: 1.7; }
    .footer { margin-top: 28px; color: var(--muted); text-align: center; font-size: 13px; padding: 14px; }
    @media (max-width: 980px) { .hero, .row, .row2 { grid-template-columns: 1fr; } .stats { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge">
        {% if settings.logo_path %}
          <img src="{{ settings.logo_path }}" alt="Logo">
        {% else %}
          M
        {% endif %}
      </div>
      <div>
        <div style="font-weight:800">{{ settings.site_title }}</div>
        <div style="font-size:12px;color:var(--muted)">{{ settings.site_subtitle }}</div>
      </div>
    </div>
    <div class="nav">
      {% if public_nav %}
        <a href="{{ url_for('index') }}">Menu</a>
        <a href="{{ url_for('admin_login') }}">Admin</a>
      {% else %}
        <a href="{{ url_for('index') }}">Public Menu</a>
        <a href="{{ url_for('admin_dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin_import') }}">Import</a>
        <a href="{{ url_for('admin_settings') }}">Settings</a>
        <a href="{{ url_for('admin_items', lang='en') }}">Items (EN)</a>
        <a href="{{ url_for('admin_items', lang='ar') }}">Items (AR)</a>
        <a href="{{ url_for('admin_items', lang='ku') }}">Items (KU)</a>
        <a href="{{ url_for('generate_images_page') }}">Images</a>
        <a href="{{ url_for('admin_logout') }}">Logout</a>
      {% endif %}
    </div>
  </div>
  <div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for msg in messages %}
          <div class="flash">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ content|safe }}
    <div class="footer">Local first. Put it online later.</div>
  </div>
</body>
</html>
'''

def render_page(title, content, public_nav=True):
    return render_template_string(BASE_HTML, title=title, content=content, settings=load_settings(), public_nav=public_nav)

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
