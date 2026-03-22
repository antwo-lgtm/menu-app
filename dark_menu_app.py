import os
import csv
import json
import hashlib
import urllib.parse
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "antwan-premium-777")

# --- CONFIG & STORAGE ---
DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

# Columns for English, Arabic, and Kurdish
EXPECTED_COLUMNS = [
    "Category_EN", "Category_AR", "Category_KU",
    "Item_EN", "Item_AR", "Item_KU",
    "Description_EN", "Description_AR", "Description_KU",
    "Price"
]

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- UTILITIES ---
def load_settings():
    defaults = {"site_title": "Digital Menu", "logo_path": ""}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f: return {**defaults, **json.load(f)}
        except: pass
    return defaults

def load_menu():
    if not os.path.exists(DATA_FILE): return []
    items = []
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({k.strip(): v.strip() for k, v in row.items()})
    return items

def save_menu(items):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        for item in items:
            row = {col: item.get(col, "") for col in EXPECTED_COLUMNS}
            writer.writerow(row)

def get_image_url(item_name_en):
    if not item_name_en: return "https://ui-avatars.com/api/?name=Menu&background=18181b&color=eab308"
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(digest + "."): return f"/uploads/{f}"
    if os.path.exists(os.path.join(IMAGE_DIR, f"{digest}.png")): return f"/images/{digest}.png"
    return f"https://ui-avatars.com/api/?name={urllib.parse.quote(item_name_en)}&background=18181b&color=eab308&size=512"

# --- TRANSLATIONS (Public UI Only) ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search...', 'all': 'All', 'staff': 'Staff Login', 'price_suffix': 'IQD'},
    'ar': {'dir': 'rtl', 'search': 'بحث...', 'all': 'الكل', 'staff': 'دخول الموظفين', 'price_suffix': 'د.ع'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان...', 'all': 'هەموو', 'staff': 'چوونەژوورەوەی ستاف', 'price_suffix': 'د.ع'}
}

# --- PUBLIC TEMPLATE ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ lang_data.dir }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ settings.site_title }}</title>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root { --bg: #050505; --card: #111113; --accent: #eab308; --text: #ffffff; --muted: #a1a1aa; --border: rgba(255,255,255,0.08); }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; outline: none; }
    body { margin: 0; font-family: 'Noto Sans Arabic', sans-serif; background: var(--bg); color: var(--text); overflow-x: hidden; }
    
    /* Header & Lang Switcher */
    .header { padding: 40px 20px 20px; text-align: center; }
    .logo { width: 90px; height: 90px; border-radius: 24px; object-fit: cover; border: 2px solid var(--accent); margin-bottom: 20px; }
    .lang-switcher { display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; }
    .lang-switcher a { color: var(--muted); text-decoration: none; font-size: 13px; font-weight: bold; letter-spacing: 1px; transition: 0.3s; }
    .lang-switcher a.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

    /* Search & Filter */
    .search-container { max-width: 500px; margin: 0 auto 25px; padding: 0 20px; }
    .search-input { width: 100%; background: var(--card); border: 1px solid var(--border); padding: 14px 22px; border-radius: 50px; color: white; font-size: 16px; transition: 0.3s; }
    .search-input:focus { border-color: var(--accent); }
    .categories { display: flex; gap: 12px; overflow-x: auto; padding: 0 20px 20px; scrollbar-width: none; }
    .categories::-webkit-scrollbar { display: none; }
    .cat-chip { white-space: nowrap; padding: 10px 22px; border-radius: 50px; background: var(--card); border: 1px solid var(--border); color: var(--muted); cursor: pointer; font-weight: 600; font-size: 14px; transition: 0.3s; }
    .cat-chip.active { background: var(--accent); color: black; border-color: var(--accent); }

    /* Grid */
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 0 20px 60px; max-width: 1200px; margin: 0 auto; }
    .menu-item { background: var(--card); border-radius: 28px; overflow: hidden; border: 1px solid var(--border); transition: 0.3s; }
    .menu-item img { width: 100%; aspect-ratio: 4/3; object-fit: cover; border-bottom: 1px solid var(--border); }
    .item-info { padding: 20px; }
    .item-header { display: flex; justify-content: space-between; align-items: start; gap: 10px; }
    .item-name { font-size: 1.25rem; font-weight: 700; margin: 0; }
    .item-price { color: var(--accent); font-weight: 800; font-size: 1.1rem; white-space: nowrap; }
    .item-desc { color: var(--muted); font-size: 0.95rem; margin-top: 10px; line-height: 1.5; min-height: 45px; }

    /* Staff Link */
    .footer { padding: 40px 20px; text-align: center; }
    .staff-link { opacity: 0.1; color: white; text-decoration: none; font-size: 11px; transition: 0.5s; }
    .staff-link:hover { opacity: 0.6; }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="header">
    {% if settings.logo_path %}<img src="{{ settings.logo_path }}" class="logo" alt="Logo">{% endif %}
    <div class="lang-switcher">
      <a href="?l=en" class="{% if lang == 'en' %}active{% endif %}">EN</a>
      <a href="?l=ar" class="{% if lang == 'ar' %}active{% endif %}">AR</a>
      <a href="?l=ku" class="{% if lang == 'ku' %}active{% endif %}">KU</a>
    </div>
  </div>

  <div class="search-container">
    <input type="text" id="searchInput" class="search-input" placeholder="{{ lang_data.search }}">
  </div>

  <div class="categories">
    <div class="cat-chip active" data-cat="all">{{ lang_data.all }}</div>
    {% for cat in categories %}
      <div class="cat-chip" data-cat="{{ cat }}">{{ cat }}</div>
    {% endfor %}
  </div>

  <div class="menu-grid" id="menuGrid">
    {% for item in items %}
    <div class="menu-item" 
         data-category="{{ item['Category_' ~ lang|upper] }}" 
         data-search="{{ item['Item_' ~ lang|upper] }} {{ item['Description_' ~ lang|upper] }}">
      <img src="{{ item.image }}" alt="Dish">
      <div class="item-info">
        <div class="item-header">
          <h3 class="item-name">{{ item['Item_' ~ lang|upper] }}</h3>
          <span class="item-price">{{ item.Price }} {{ lang_data.price_suffix }}</span>
        </div>
        <p class="item-desc">{{ item['Description_' ~ lang|upper] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="footer">
    <a href="{{ url_for('admin_login') }}" class="staff-link">{{ lang_data.staff }}</a>
  </div>

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

# --- ADMIN TEMPLATE ---
ADMIN_HTML = r'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><title>Admin Portal</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #0f172a; color: white; padding: 30px; }
    .card { background: #1e293b; padding: 25px; border-radius: 12px; margin-bottom: 25px; border: 1px solid #334155; }
    input, textarea { width: 100%; padding: 12px; margin: 10px 0; background: #0f172a; color: white; border: 1px solid #334155; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
    .btn { background: #eab308; color: black; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    .btn-red { background: #ef4444; color: white; padding: 6px 12px; text-decoration: none; border-radius: 6px; font-size: 12px; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th, td { text-align: left; padding: 14px; border-bottom: 1px solid #334155; }
    .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }
  </style>
</head>
<body>
  <div style="max-width: 1100px; margin: 0 auto;">
    <div style="display:flex; justify-content: space-between; align-items: center;">
      <h1>Admin Dashboard</h1>
      <div><a href="/" style="color: #eab308; margin-right: 20px;">Public Menu</a> <a href="/admin/logout" style="color: #ef4444;">Logout</a></div>
    </div>

    <div class="card">
      <h3>Add Item (Trilingual)</h3>
      <form action="/admin/add" method="post">
        <div class="grid">
          <div><label>Names</label>
            <input name="Item_EN" placeholder="Name (English)" required>
            <input name="Item_AR" placeholder="Name (Arabic)" required>
            <input name="Item_KU" placeholder="Name (Kurdish)" required>
          </div>
          <div><label>Categories</label>
            <input name="Category_EN" placeholder="Category (English)" required>
            <input name="Category_AR" placeholder="Category (Arabic)" required>
            <input name="Category_KU" placeholder="Category (Kurdish)" required>
          </div>
          <div><label>Descriptions</label>
            <textarea name="Description_EN" placeholder="English..."></textarea>
            <textarea name="Description_AR" placeholder="Arabic..."></textarea>
            <textarea name="Description_KU" placeholder="Kurdish..."></textarea>
          </div>
        </div>
        <input name="Price" placeholder="Price (e.g. 15,000)" style="width: 200px;" required>
        <br><button class="btn">Add to Menu</button>
      </form>
    </div>

    <div class="card">
      <h3>Current Menu Items</h3>
      <table>
        <tr><th>Name (EN)</th><th>Category</th><th>Price</th><th>Actions</th></tr>
        {% for item in items %}
        <tr>
          <td>{{ item.Item_EN }}</td>
          <td>{{ item.Category_EN }}</td>
          <td>{{ item.Price }}</td>
          <td><a href="/admin/delete/{{ loop.index0 }}" class="btn-red" onclick="return confirm('Remove item?')">Delete</a></td>
        </tr>
        {% endfor %}
      </table>
    </div>
  </div>
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
    for item in raw_items:
        item['image'] = get_image_url(item.get("Item_EN", ""))
    return render_template_string(PUBLIC_HTML, items=raw_items, categories=categories, lang=lang, lang_data=LANG_MAP[lang], settings=load_settings())

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
    return render_template_string('<body style="background:#0f172a; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post" style="background:#1e293b; padding:40px; border-radius:15px; text-align:center;"><h2>Admin Login</h2><input type="password" name="password" autofocus style="padding:12px; border-radius:8px; border:none;"><br><br><button style="background:#eab308; border:none; padding:12px 25px; border-radius:8px; font-weight:bold; cursor:pointer;">Enter Dashboard</button></form></body>')

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_HTML, items=load_menu())

@app.route("/admin/add", methods=["POST"])
def admin_add():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    items.append({col: request.form.get(col, "").strip() for col in EXPECTED_COLUMNS})
    save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete/<int:idx>")
def admin_delete(idx):
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    if 0 <= idx < len(items):
        items.pop(idx)
        save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/images/<filename>")
def serve_image(filename): return send_from_directory(IMAGE_DIR, filename)

@app.route("/uploads/<filename>")
def serve_upload(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_menu([])
    app.run(debug=True, port=5000)
