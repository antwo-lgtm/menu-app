import os, csv, hashlib, urllib.parse, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "luxe-logo-v6-2026")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
# We reserve a specific filename for the restaurant logo
LOGO_FILENAME = "restaurant_logo_file" 
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

INTERNAL_COLS = [
    "Category_EN", "Category_AR", "Category_KU",
    "Item_EN", "Item_AR", "Item_KU",
    "Description_EN", "Description_AR", "Description_KU",
    "Price", "Status"
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- CORE UTILS ---
def load_menu():
    if not os.path.exists(DATA_FILE): return []
    items = []
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append({k: v.strip() for k, v in row.items()})
    except: pass
    return items

def save_menu(items):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INTERNAL_COLS)
        writer.writeheader()
        for item in items:
            row = {col: item.get(col, "") for col in INTERNAL_COLS}
            if not row.get("Status"): row["Status"] = "Available"
            writer.writerow(row)

def get_logo_url():
    # Check if any file starting with 'restaurant_logo_file' exists
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}")):
            return f"/uploads/{LOGO_FILENAME}.{ext}"
    return None

def get_image_url(item_name_en):
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{digest}.{ext}")):
            return f"/uploads/{digest}.{ext}"
    q = urllib.parse.quote(item_name_en + " food dish")
    return f"https://source.unsplash.com/800x800/?food,{q}"

def map_csv_row(row):
    res = {col: "" for col in INTERNAL_COLS}
    res["Status"] = "Available"
    for k, v in row.items():
        if not k: continue
        key, val = k.lower(), v.strip()
        if "item" in key or "name" in key:
            if "ar" in key or "عربي" in key: res["Item_AR"] = val
            elif "ku" in key or "کورد" in key: res["Item_KU"] = val
            else: res["Item_EN"] = val
        elif "cat" in key:
            if "ar" in key or "عربي" in key: res["Category_AR"] = val
            elif "ku" in key or "کورد" in key: res["Category_KU"] = val
            else: res["Category_EN"] = val
        elif any(x in key for x in ["price", "سعر", "نرخ"]):
            res["Price"] = val
    return res

# --- TRANSLATIONS ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search...', 'all': 'All', 'price': 'IQD', 'sold': 'SOLD OUT'},
    'ar': {'dir': 'rtl', 'search': 'بحث...', 'all': 'الكل', 'price': 'د.ع', 'sold': 'نفذت'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان...', 'all': 'هەموو', 'price': 'د.ع', 'sold': 'نەماوە'}
}

# --- HTML TEMPLATES ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ lang_data.dir }}">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Premium Dining</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Noto+Sans+Arabic:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root { --gold: #c5a059; --bg: #0c0c0d; --card: #141415; --text: #ffffff; --muted: #888; }
    body { background: var(--bg); color: var(--text); font-family: 'Noto Sans Arabic', sans-serif; margin: 0; }
    .header { text-align: center; padding: 40px 20px; border-bottom: 1px solid #222; }
    .logo-img { max-height: 120px; width: auto; margin-bottom: 10px; }
    .logo-text { font-family: 'Playfair Display', serif; font-size: 2.2rem; color: var(--gold); letter-spacing: 4px; text-transform: uppercase; margin: 0; }
    .lang-switcher { display: flex; justify-content: center; gap: 20px; margin-top: 15px; }
    .lang-switcher a { color: var(--muted); text-decoration: none; font-size: 13px; font-weight: bold; }
    .lang-switcher a.active { color: var(--gold); border-bottom: 2px solid var(--gold); }
    .search-box { width: 100%; max-width: 500px; margin: 20px auto; padding: 0 20px; position: sticky; top: 10px; z-index: 100; }
    .search-input { width: 100%; background: var(--card); border: 1px solid #333; padding: 14px 20px; border-radius: 50px; color: white; backdrop-filter: blur(10px); }
    .cats { display: flex; gap: 12px; overflow-x: auto; padding: 10px 20px; scrollbar-width: none; justify-content: center; }
    .cat-chip { padding: 8px 22px; border-radius: 50px; border: 1px solid #333; white-space: nowrap; cursor: pointer; color: var(--muted); }
    .cat-chip.active { background: var(--gold); color: black; border-color: var(--gold); font-weight: bold; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 25px; padding: 20px; max-width: 1400px; margin: auto; }
    .item-card { background: var(--card); border-radius: 20px; overflow: hidden; border: 1px solid #222; position: relative; }
    .item-card.sold-out { opacity: 0.4; filter: grayscale(1); }
    .item-card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; }
    .item-info { padding: 18px; }
    .price { color: var(--gold); font-weight: bold; }
    .sold-badge { position: absolute; top: 15px; right: 15px; background: red; color: white; padding: 3px 10px; border-radius: 6px; font-weight: bold; font-size: 11px; z-index: 10; }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="header">
    {% if logo_url %}
        <img src="{{ logo_url }}" class="logo-img" alt="Logo">
    {% else %}
        <h1 class="logo-text">Restaurant Name</h1>
    {% endif %}
    <div class="lang-switcher">
      <a href="?l=en" class="{{ 'active' if lang=='en' }}">EN</a>
      <a href="?l=ar" class="{{ 'active' if lang=='ar' }}">AR</a>
      <a href="?l=ku" class="{{ 'active' if lang=='ku' }}">KU</a>
    </div>
  </div>
  <div class="search-box"><input type="text" id="sq" class="search-input" placeholder="{{ lang_data.search }}"></div>
  <div class="cats">
    <div class="cat-chip active" data-c="all">{{ lang_data.all }}</div>
    {% for c in categories %}<div class="cat-chip" data-c="{{ c }}">{{ c }}</div>{% endfor %}
  </div>
  <div class="grid">
    {% for i in items %}
    <div class="item-card {{ 'sold-out' if i.Status != 'Available' }}" data-cat="{{ i['Category_' ~ lang|upper] }}" data-text="{{ i['Item_' ~ lang|upper] }}">
      {% if i.Status != 'Available' %}<div class="sold-badge">{{ lang_data.sold }}</div>{% endif %}
      <img src="{{ i.image }}" loading="lazy">
      <div class="item-info">
        <div style="display:flex; justify-content:space-between;">
          <h3 style="margin:0; font-size:1.1rem;">{{ i['Item_' ~ lang|upper] or i['Item_EN'] }}</h3>
          <span class="price">{{ i.Price }} <small>{{ lang_data.price }}</small></span>
        </div>
        <p style="color:var(--muted); font-size:0.85rem; margin-top:8px;">{{ i['Description_' ~ lang|upper] or i['Description_EN'] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>
  <script>
    const sq = document.getElementById('sq');
    const chips = document.querySelectorAll('.cat-chip');
    const cards = document.querySelectorAll('.item-card');
    let activeC = 'all';
    function filter() {
      const v = sq.value.toLowerCase();
      cards.forEach(c => {
        const mQ = c.getAttribute('data-text').toLowerCase().includes(v);
        const mC = activeC === 'all' || c.getAttribute('data-cat') === activeC;
        c.hidden = !(mQ && mC);
      });
    }
    sq.addEventListener('input', filter);
    chips.forEach(b => b.addEventListener('click', () => {
      chips.forEach(x => x.classList.remove('active'));
      b.classList.add('active'); activeC = b.getAttribute('data-c'); filter();
    }));
  </script>
</body>
</html>
'''

ADMIN_HTML = r'''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Admin Studio</title>
<style>
  body { font-family: sans-serif; background: #0a0a0a; color: white; padding: 20px; }
  .card { background: #161616; padding: 20px; border-radius: 12px; border: 1px solid #222; margin-bottom: 20px; }
  input, select, textarea { width: 100%; padding: 12px; margin: 8px 0; background: #000; color: white; border: 1px solid #333; border-radius: 8px; box-sizing: border-box; }
  .btn { background: #c5a059; color: black; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; }
  .row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  table { width: 100%; border-collapse: collapse; margin-top: 20px; }
  td, th { padding: 12px; border-bottom: 1px solid #222; text-align: left; }
</style>
</head>
<body>
  <div style="display:flex; justify-content:space-between;">
    <h1>Admin Panel</h1>
    <a href="/admin/logout" style="color:red; text-decoration:none;">Logout</a>
  </div>

  <div class="card" style="border-left: 5px solid #c5a059;">
    <h3>Step 1: Branding (Upload Logo)</h3>
    <form action="/admin/upload_logo" method="post" enctype="multipart/form-data">
      <div style="display:flex; gap:10px; align-items:center;">
        <input type="file" name="logo_file" accept="image/*" required>
        <button class="btn">Update Logo</button>
      </div>
      <p style="font-size:11px; color:#666;">Recommended: Transparent PNG (around 400px wide).</p>
    </form>
  </div>

  <div class="card">
    <h3 id="form-title">Step 2: Add / Edit Menu Items</h3>
    <form action="/admin/save" method="post" enctype="multipart/form-data">
      <input type="hidden" name="idx" id="idx" value="-1">
      <div class="row">
        <input name="Item_EN" id="i_en" placeholder="Name (EN)" required>
        <input name="Item_AR" id="i_ar" placeholder="Name (AR)">
        <input name="Item_KU" id="i_ku" placeholder="Name (KU)">
      </div>
      <div class="row">
        <input name="Category_EN" id="c_en" placeholder="Category (EN)" required>
        <input name="Price" id="price" placeholder="Price (e.g. 25,000)">
        <select name="Status" id="status">
            <option value="Available">Available</option>
            <option value="Sold Out">Sold Out</option>
        </select>
      </div>
      <div class="row">
        <div style="grid-column: span 2;"><input type="file" name="img"> <small style="color:#666">Item Photo</small></div>
      </div>
      <button class="btn" id="save-btn">Save Item</button>
      <button type="button" class="btn" style="background:#333; color:white;" onclick="location.reload()">Clear</button>
    </form>
  </div>

  <div class="card">
    <h3>Step 3: Bulk Import (CSV)</h3>
    <form action="/admin/upload_csv" method="post" enctype="multipart/form-data">
      <input type="file" name="csv_file" accept=".csv" required>
      <button class="btn" style="background:#2563eb; color:white;">Import CSV</button>
    </form>
  </div>

  <div class="card">
    <table>
      <thead><tr><th>Item</th><th>Category</th><th>Price</th><th>Action</th></tr></thead>
      <tbody>
        {% for item in items %}
        <tr>
          <td>{{ item.Item_EN }}</td>
          <td>{{ item.Category_EN }}</td>
          <td>{{ item.Price }}</td>
          <td>
            <button class="btn" style="padding:5px 10px; font-size:11px;" onclick='edit({{ loop.index0 }}, {{ item | tojson }})'>EDIT</button>
            <a href="/admin/delete/{{ loop.index0 }}" style="color:red; margin-left:10px; font-size:11px;" onclick="return confirm('Delete?')">DEL</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <script>
    function edit(idx, d) {
      document.getElementById('idx').value = idx;
      document.getElementById('i_en').value = d.Item_EN || '';
      document.getElementById('i_ar').value = d.Item_AR || '';
      document.getElementById('i_ku').value = d.Item_KU || '';
      document.getElementById('c_en').value = d.Category_EN || '';
      document.getElementById('price').value = d.Price || '';
      document.getElementById('status').value = d.Status || 'Available';
      document.getElementById('form-title').innerText = "Edit: " + d.Item_EN;
      document.getElementById('save-btn').innerText = "Update Product";
      window.scrollTo(0,0);
    }
  </script>
</body>
</html>
'''

# --- ROUTES ---
@app.route("/")
def index():
    lang = request.args.get("l", "en")
    if lang not in LANG_MAP: lang = "en"
    items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = []
    for i in items:
        c = i.get(cat_key)
        if c and c not in categories: categories.append(c)
    
    for i in items: i['image'] = get_image_url(i.get("Item_EN", ""))
    
    return render_template_string(PUBLIC_HTML, items=items, categories=categories, 
                                  lang=lang, lang_data=LANG_MAP[lang], 
                                  logo_url=get_logo_url())

@app.route("/admin/upload_logo", methods=["POST"])
def upload_logo():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("logo_file")
    if file and file.filename:
        # Delete old logo files to avoid conflict
        for ext in ALLOWED_EXTENSIONS:
            old_path = os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}")
            if os.path.exists(old_path): os.remove(old_path)
            
        ext = file.filename.rsplit('.', 1)[1].lower()
        file.save(os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}"))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
    return render_template_string('<body style="background:#0a0a0a; color:white; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post"><h2>Staff Entry</h2><input type="password" name="password" style="padding:10px;"><button>Go</button></form></body>')

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_HTML, items=load_menu())

@app.route("/admin/save", methods=["POST"])
def admin_save():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    idx = int(request.form.get("idx", -1))
    new_data = {col: request.form.get(col, "").strip() for col in INTERNAL_COLS}
    
    img = request.files.get("img")
    if img and img.filename:
        digest = hashlib.sha1(new_data["Item_EN"].encode("utf-8")).hexdigest()[:16]
        ext = img.filename.rsplit('.', 1)[1].lower()
        img.save(os.path.join(UPLOAD_DIR, f"{digest}.{ext}"))

    if idx == -1: items.append(new_data)
    else: items[idx] = new_data
    save_menu(items)
    return redirect(url_for("admin_dashboard"))

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

@app.route("/admin/delete/<int:idx>")
def admin_delete(idx):
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    items = load_menu()
    if 0 <= idx < len(items): items.pop(idx); save_menu(items)
    return redirect(url_for("admin_dashboard"))

@app.route("/uploads/<filename>")
def serve_upload(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_menu([])
    app.run(debug=True, port=5000)
