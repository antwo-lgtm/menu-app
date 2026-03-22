import os
import csv
import json
import hashlib
import urllib.parse
import io
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "antwan-smart-final-99")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

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
    if not item_name_en: item_name_en = "Item"
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(digest + "."): return f"/uploads/{f}"
    if os.path.exists(os.path.join(IMAGE_DIR, f"{digest}.png")): return f"/images/{digest}.png"
    return f"https://ui-avatars.com/api/?name={urllib.parse.quote(item_name_en)}&background=18181b&color=eab308&size=512"

def map_csv_row(row):
    """Smart mapping: tries to guess which column is which regardless of header name."""
    new_row = {col: "" for col in INTERNAL_COLS}
    for key, val in row.items():
        if not key: continue
        k = key.lower()
        v = val.strip() if val else ""
        # Names
        if any(x in k for x in ["item", "name", "title"]):
            if "ar" in k or "عربي" in k: new_row["Item_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Item_KU"] = v
            else: new_row["Item_EN"] = v
        # Categories
        elif "cat" in k:
            if "ar" in k or "عربي" in k: new_row["Category_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Category_KU"] = v
            else: new_row["Category_EN"] = v
        # Descriptions
        elif "desc" in k:
            if "ar" in k or "عربي" in k: new_row["Description_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Description_KU"] = v
            else: new_row["Description_EN"] = v
        # Price
        elif any(x in k for x in ["price", "سعر", "نرخ"]):
            new_row["Price"] = v
    return new_row

# --- TRANSLATIONS ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search...', 'all': 'All', 'staff': 'Staff Access', 'price_suffix': 'IQD'},
    'ar': {'dir': 'rtl', 'search': 'بحث...', 'all': 'الكل', 'staff': 'دخول الموظفين', 'price_suffix': 'د.ع'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان...', 'all': 'هەموو', 'staff': 'بۆ کارمەندان', 'price_suffix': 'د.ع'}
}

# --- TEMPLATES ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ lang_data.dir }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Premium Menu</title>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #050505; --card: #111113; --accent: #eab308; --text: #ffffff; --muted: #a1a1aa; --border: rgba(255,255,255,0.08); }
    * { box-sizing: border-box; outline: none; }
    body { margin: 0; font-family: 'Noto Sans Arabic', sans-serif; background: var(--bg); color: var(--text); }
    .header { padding: 40px 20px; text-align: center; }
    .lang-switcher { display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; }
    .lang-switcher a { color: var(--muted); text-decoration: none; font-size: 13px; font-weight: bold; }
    .lang-switcher a.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
    .search-container { max-width: 500px; margin: 0 auto 25px; padding: 0 20px; }
    .search-input { width: 100%; background: var(--card); border: 1px solid var(--border); padding: 14px 22px; border-radius: 50px; color: white; font-size: 16px; }
    .categories { display: flex; gap: 12px; overflow-x: auto; padding: 0 20px 20px; scrollbar-width: none; }
    .cat-chip { white-space: nowrap; padding: 10px 22px; border-radius: 50px; background: var(--card); border: 1px solid var(--border); color: var(--muted); cursor: pointer; font-weight: 600; font-size: 14px; }
    .cat-chip.active { background: var(--accent); color: black; }
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 20px; max-width: 1200px; margin: 0 auto; }
    .menu-item { background: var(--card); border-radius: 28px; overflow: hidden; border: 1px solid var(--border); }
    .menu-item img { width: 100%; aspect-ratio: 4/3; object-fit: cover; }
    .item-info { padding: 20px; }
    .item-header { display: flex; justify-content: space-between; align-items: start; }
    .item-price { color: var(--accent); font-weight: 800; }
    .footer { padding: 40px; text-align: center; opacity: 0.2; }
    .staff-link { color: white; text-decoration: none; font-size: 11px; }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="header">
    <div class="lang-switcher">
      <a href="?l=en" class="{% if lang == 'en' %}active{% endif %}">EN</a>
      <a href="?l=ar" class="{% if lang == 'ar' %}active{% endif %}">AR</a>
      <a href="?l=ku" class="{% if lang == 'ku' %}active{% endif %}">KU</a>
    </div>
  </div>
  <div class="search-container"><input type="text" id="searchInput" class="search-input" placeholder="{{ lang_data.search }}"></div>
  <div class="categories">
    <div class="cat-chip active" data-cat="all">{{ lang_data.all }}</div>
    {% for cat in categories %}<div class="cat-chip" data-cat="{{ cat }}">{{ cat }}</div>{% endfor %}
  </div>
  <div class="menu-grid" id="menuGrid">
    {% for item in items %}
    <div class="menu-item" data-category="{{ item['Category_' ~ lang|upper] }}" data-search="{{ item['Item_' ~ lang|upper] }} {{ item['Description_' ~ lang|upper] }}">
      <img src="{{ item.image }}">
      <div class="item-info">
        <div class="item-header">
          <h3 style="margin:0">{{ item['Item_' ~ lang|upper] }}</h3>
          <span class="item-price">{{ item.Price }} {{ lang_data.price_suffix }}</span>
        </div>
        <p style="color:var(--muted); font-size:0.9rem; margin-top:10px;">{{ item['Description_' ~ lang|upper] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>
  <div class="footer"><a href="{{ url_for('admin_login') }}" class="staff-link">{{ lang_data.staff }}</a></div>
  <script>
    const search = document.getElementById('searchInput');
    const chips = document.querySelectorAll('.cat-chip');
    const items = document.querySelectorAll('.menu-item');
    let activeCat = 'all';
    function filter() {
      const q = search.value.toLowerCase();
      items.forEach(el => {
        const matchesSearch = el.getAttribute('data-search').toLowerCase().includes(q);
        const matchesCat = activeCat === 'all' || el.getAttribute('data-category') === activeCat;
        el.hidden = !(matchesSearch && matchesCat);
      });
    }
    search.addEventListener('input', filter);
    chips.forEach(c => {
      c.addEventListener('click', () => {
        chips.forEach(x => x.classList.remove('active'));
        c.classList.add('active');
        activeCat = c.getAttribute('data-cat');
        filter();
      });
    });
  </script>
</body>
</html>
'''

ADMIN_HTML = r'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><title>Admin Portal</title>
  <style>
    body { font-family: sans-serif; background: #0f172a; color: white; padding: 20px; }
    .card { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    input, textarea { width: 100%; padding: 10px; margin: 8px 0; background: #0f172a; color: white; border: 1px solid #334155; border-radius: 6px; }
    .btn { background: #eab308; color: black; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
  </style>
</head>
<body>
  <h1>Admin Dashboard</h1>
  <div class="card">
    <h3>Smart CSV Import</h3>
    <form action="/admin/upload_csv" method="post" enctype="multipart/form-data">
      <input type="file" name="csv_file" accept=".csv" required>
      <button class="btn" style="background:#3b82f6; color:white;">Upload & Map Automatically</button>
    </form>
  </div>
  <div class="card">
    <h3>Add Item</h3>
    <form action="/admin/add" method="post">
      <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px;">
        <input name="Item_EN" placeholder="Name (EN)" required>
        <input name="Item_AR" placeholder="Name (AR)">
        <input name="Item_KU" placeholder="Name (KU)">
      </div>
      <input name="Category_EN" placeholder="Category (EN)" required>
      <input name="Price" placeholder="Price" required>
      <button class="btn">Add Item</button>
    </form>
  </div>
  <div class="card">
    <table>
      <tr><th>Name</th><th>Category</th><th>Action</th></tr>
      {% for item in items %}
      <tr><td>{{ item.Item_EN }}</td><td>{{ item.Category_EN }}</td><td><a href="/admin/delete/{{ loop.index0 }}" style="color:#ef4444;">Delete</a></td></tr>
      {% endfor %}
    </table>
  </div>
  <a href="/" style="color:#eab308;">Back to Menu</a>
</body>
</html>
'''

# --- ROUTES ---
@app.route("/")
def index():
    lang = request.args.get("l", "en")
    if lang not in LANG_MAP: lang = "en"
    raw_items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = sorted(list(set(item.get(cat_key, "") for item in raw_items if item.get(cat_key))))
    for item in raw_items: item['image'] = get_image_url(item.get("Item_EN", ""))
    return render_template_string(PUBLIC_HTML, items=raw_items, categories=categories, lang=lang, lang_data=LANG_MAP[lang])

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
    return render_template_string('<body style="background:#0f172a; color:white; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post"><input type="password" name="password" placeholder="Pass"><button>Go</button></form></body>')

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_HTML, items=load_menu())

@app.route("/admin/upload_csv", methods=["POST"])
def upload_csv():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("csv_file")
    if file:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        items = [map_csv_row(row) for row in reader]
        save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/add", methods=["POST"])
def admin_add():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    items.append({col: request.form.get(col, "").strip() for col in INTERNAL_COLS})
    save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete/<int:idx>")
def admin_delete(idx):
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    if 0 <= idx < len(items): items.pop(idx); save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/images/<filename>")
def serve_image(filename): return send_from_directory(IMAGE_DIR, filename)

@app.route("/uploads/<filename>")
def serve_upload(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_menu([])
    app.run(debug=True, port=5000)
