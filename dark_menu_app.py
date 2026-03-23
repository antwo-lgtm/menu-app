import os
import csv
import io
import re
import json
import hashlib
import urllib.parse
from collections import OrderedDict
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session, g
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-menu-secret")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
DATA_DIR = "data"
IMAGE_DIR = "uploaded_assets"          # all images go here (manual uploads only)
SETTINGS_FILE = "menu_settings.json"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "menu.db")

# Languages we support
LANGUAGES = {
    "en": {"name": "English", "table": "items_en", "labels": {
        "search": "Search",
        "category": "Category",
        "all_categories": "All Categories",
        "placeholder": "Search for dish or category...",
        "no_items": "No items found.",
        "price_suffix": "IQD",
        "categories_label": "Categories"
    }},
    "ar": {"name": "العربية", "table": "items_ar", "labels": {
        "search": "بحث",
        "category": "القسم",
        "all_categories": "كل الأقسام",
        "placeholder": "ابحث عن صنف أو قسم...",
        "no_items": "لا توجد أصناف مطابقة.",
        "price_suffix": "د.ع",
        "categories_label": "الأقسام"
    }},
    "ku": {"name": "Kurdî", "table": "items_ku", "labels": {
        "search": "Lêgerîn",
        "category": "Beş",
        "all_categories": "Hemû beş",
        "placeholder": "Navê xwarinê an beşê binivîse...",
        "no_items": "Tişt nehate dîtin.",
        "price_suffix": "IQD",
        "categories_label": "Beş"
    }}
}
DEFAULT_LANG = "en"

# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        init_db(db)
    return db

def init_db(db):
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
def load_settings():
    defaults = {
        "site_title": "Restaurant Menu",
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

def upload_filename_for_item(item_name, lang, original_name):
    ext = os.path.splitext(original_name)[1].lower() or ".png"
    digest = hashlib.sha1(f"{lang}:{item_name}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}{ext}"

def user_uploaded_image_url(item_name, lang):
    digest = hashlib.sha1(f"{lang}:{item_name}".encode("utf-8")).hexdigest()[:16]
    for name in os.listdir(IMAGE_DIR):
        if name.startswith(digest + "."):
            return f"/images/{name}"
    return None

def best_image_url(item_name, lang):
    uploaded = user_uploaded_image_url(item_name, lang)
    if uploaded:
        return uploaded
    # No fallback; show a placeholder via CSS or a default image
    return "/static/placeholder.png"   # we'll serve a default image

# We'll serve a default placeholder from static folder
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)

def is_admin():
    return session.get("is_admin") is True

def require_admin():
    if not is_admin():
        return redirect(url_for("admin_login"))

# ----------------------------------------------------------------------
# CSV helpers
# ----------------------------------------------------------------------
def parse_csv_text(text):
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
    items = parse_csv_text(file_content)
    db = get_db()
    table = LANGUAGES[lang]["table"]
    if mode == "replace":
        db.execute(f"DELETE FROM {table}")
        db.commit()
    for item in items:
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
        <p class="sub">Manage items, import CSV, upload logo, and upload images.</p>
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
      <a class="card" href="{{ url_for('admin_settings') }}"><h2 style="margin-top:0">Settings</h2><p class="sub">Change title, logo</p></a>
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
              <form method="post" action="{{ url_for('admin_upload_item_image', lang=lang, item_id=item.id) }}" enctype="multipart/form-data" style="display:inline-block;">
                <input type="file" name="item_image" accept="image/*" style="display:none;" onchange="this.form.submit()" id="file-{{ item.id }}">
                <button class="btn secondary small" type="button" onclick="document.getElementById('file-{{ item.id }}').click();">Upload</button>
              </form>
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
# Image upload for items
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
    uploaded.save(os.path.join(IMAGE_DIR, filename))
    flash(f"Image uploaded for {item['name']}.")
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
        }
        logo = request.files.get("logo_file")
        if logo and logo.filename:
            safe = secure_filename_local(logo.filename)
            ext = os.path.splitext(safe)[1].lower() or ".png"
            logo_name = f"site_logo{ext}"
            logo_path = os.path.join(IMAGE_DIR, logo_name)
            logo.save(logo_path)
            updates["logo_path"] = f"/images/{logo_name}"
        save_settings(updates)
        flash("Settings updated.")
        return redirect(url_for("admin_settings"))

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Site Settings</h1>
      <form method="post" enctype="multipart/form-data">
        <div class="field-label">Site title (used in browser tab)</div>
        <input class="input" type="text" name="site_title" value="{{ settings.site_title }}">
        <div class="field-label">Logo</div>
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
# Public menu
# ----------------------------------------------------------------------
@app.route("/")
def index():
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

    labels = LANGUAGES[lang]["labels"]

    # Render with auto-submit JavaScript
    content = render_template_string('''
    <div class="filters">
      <form method="get" id="filter-form">
        <input type="hidden" name="lang" value="{{ lang }}">
        <div class="filter-group">
          <label for="search">{{ labels.search }}</label>
          <input type="text" id="search" name="q" value="{{ q }}" placeholder="{{ labels.placeholder }}" class="filter-input">
        </div>
        <div class="filter-group">
          <label for="category">{{ labels.category }}</label>
          <select id="category" name="category" class="filter-select">
            <option value="">{{ labels.all_categories }}</option>
            {% for cat in categories %}
              <option value="{{ cat }}" {% if cat == selected_category %}selected{% endif %}>{{ cat }}</option>
            {% endfor %}
          </select>
        </div>
      </form>
    </div>

    <div class="language-tabs">
      {% for code, info in LANGUAGES.items() %}
        <a class="lang-chip {% if code == lang %}active{% endif %}" href="{{ url_for('index', lang=code, q=q, category=selected_category) }}">{{ info.name }}</a>
      {% endfor %}
    </div>

    {% if grouped %}
      {% for cat, rows in grouped.items() %}
        <div class="section-title">
          <h2>{{ cat }}</h2>
        </div>
        <div class="menu-grid">
          {% for item in rows %}
            <div class="menu-item">
              <img class="menu-image" src="{{ item.image_url }}" alt="{{ item.name }}">
              <div class="menu-body">
                <div class="menu-top">
                  <h3 class="menu-name">{{ item.name }}</h3>
                  {% if item.price %}
                    <div class="price">{{ item.price }} {{ labels.price_suffix }}</div>
                  {% endif %}
                </div>
                <p class="menu-desc">{{ item.description or '' }}</p>
              </div>
            </div>
          {% endfor %}
        </div>
      {% endfor %}
    {% else %}
      <div class="no-items">{{ labels.no_items }}</div>
    {% endif %}

    <script>
      // Auto-submit when search input changes (with debounce) or category select changes
      const form = document.getElementById('filter-form');
      const searchInput = document.getElementById('search');
      const categorySelect = document.getElementById('category');
      let timeout = null;

      function submitForm() {
        form.submit();
      }

      searchInput.addEventListener('input', function() {
        clearTimeout(timeout);
        timeout = setTimeout(submitForm, 500);
      });

      categorySelect.addEventListener('change', submitForm);
    </script>
    ''', lang=lang, q=q, selected_category=selected_category, categories=categories, grouped=grouped, labels=labels, LANGUAGES=LANGUAGES)
    return render_page("Menu", content, public_nav=True)

# ----------------------------------------------------------------------
# Static file serving
# ----------------------------------------------------------------------
@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

# Create a default placeholder image if it doesn't exist
os.makedirs("static", exist_ok=True)
placeholder_path = os.path.join("static", "placeholder.png")
if not os.path.exists(placeholder_path):
    from PIL import Image
    img = Image.new('RGB', (400, 400), color=(30, 30, 35))
    img.save(placeholder_path)

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
      --bg: #0a0a0c;
      --card-bg: #111113;
      --card-border: #1f1f23;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #eab308;
      --accent-dark: #ca8a04;
      --shadow: 0 8px 20px rgba(0,0,0,0.4);
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }
    a {
      text-decoration: none;
      color: inherit;
    }
    /* Header - centered logo */
    .topbar {
      background: var(--card-bg);
      border-bottom: 1px solid var(--card-border);
      padding: 20px;
      text-align: center;
    }
    .logo {
      max-height: 80px;
      width: auto;
      border-radius: 12px;
    }
    /* Container */
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 20px;
    }
    /* Filters row */
    .filters {
      background: var(--card-bg);
      border-radius: 24px;
      padding: 20px;
      margin-bottom: 32px;
      border: 1px solid var(--card-border);
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      justify-content: center;
    }
    .filter-group {
      flex: 1;
      min-width: 200px;
    }
    .filter-group label {
      display: block;
      margin-bottom: 8px;
      font-weight: 500;
      color: var(--text-muted);
      font-size: 0.9rem;
    }
    .filter-input, .filter-select {
      width: 100%;
      padding: 12px 16px;
      border-radius: 40px;
      border: 1px solid var(--card-border);
      background: #1a1a1e;
      color: var(--text);
      font-size: 1rem;
      transition: all 0.2s;
    }
    .filter-input:focus, .filter-select:focus {
      outline: none;
      border-color: var(--accent);
    }
    /* Language tabs */
    .language-tabs {
      display: flex;
      gap: 16px;
      justify-content: center;
      margin: 32px 0 24px;
    }
    .lang-chip {
      padding: 8px 24px;
      border-radius: 40px;
      background: #1a1a1e;
      border: 1px solid var(--card-border);
      font-weight: 600;
      transition: all 0.2s;
    }
    .lang-chip.active {
      background: var(--accent);
      color: #111;
      border-color: var(--accent);
    }
    /* Section title */
    .section-title {
      margin: 32px 0 20px;
      border-right: 4px solid var(--accent);
      padding-right: 16px;
    }
    .section-title h2 {
      font-size: 1.8rem;
      font-weight: 600;
    }
    /* Menu grid */
    .menu-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 24px;
    }
    .menu-item {
      background: var(--card-bg);
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid var(--card-border);
      transition: transform 0.2s, box-shadow 0.2s;
    }
    .menu-item:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow);
    }
    .menu-image {
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      background: #1a1a1e;
    }
    .menu-body {
      padding: 20px;
    }
    .menu-top {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 12px;
    }
    .menu-name {
      font-size: 1.25rem;
      font-weight: 600;
    }
    .price {
      background: rgba(234,179,8,0.15);
      padding: 4px 12px;
      border-radius: 40px;
      color: var(--accent);
      font-weight: 600;
      font-size: 0.9rem;
    }
    .menu-desc {
      color: var(--text-muted);
      font-size: 0.9rem;
      line-height: 1.5;
      margin-top: 8px;
    }
    .no-items {
      text-align: center;
      padding: 60px 20px;
      background: var(--card-bg);
      border-radius: 24px;
      color: var(--text-muted);
      font-size: 1.2rem;
    }
    /* Admin only styles (hidden from public) */
    .admin-only { display: none; }
    /* Footer */
    .footer {
      margin-top: 48px;
      text-align: center;
      color: var(--text-muted);
      font-size: 0.8rem;
      border-top: 1px solid var(--card-border);
      padding-top: 24px;
    }
    /* Responsive */
    @media (max-width: 768px) {
      .filters {
        flex-direction: column;
      }
      .menu-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="topbar">
    {% if settings.logo_path %}
      <img class="logo" src="{{ settings.logo_path }}" alt="Logo">
    {% else %}
      <div style="font-size: 28px; font-weight: bold;">🍽️</div>
    {% endif %}
  </div>
  <div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for msg in messages %}
          <div class="flash" style="background: #2d2a1a; color: #facc15; padding: 12px; border-radius: 12px; margin-bottom: 20px;">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ content|safe }}
    <div class="footer">
      &copy; {{ settings.site_title }}
    </div>
  </div>
</body>
</html>
'''

def render_page(title, content, public_nav=True):
    # public_nav is ignored because we removed admin link from public.
    return render_template_string(BASE_HTML, title=title, content=content, settings=load_settings())

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
