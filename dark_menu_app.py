import os, csv, hashlib, urllib.parse, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "premium-v4-ultra-secure")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
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
            # Ensure Status exists
            if "Status" not in item or not item["Status"]: item["Status"] = "Available"
            writer.writerow({col: item.get(col, "") for col in INTERNAL_COLS})

def get_image_url(item_name_en):
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{digest}.{ext}")):
            return f"/uploads/{digest}.{ext}"
    # Auto-fetch high-quality food photography based on name
    clean_name = urllib.parse.quote(item_name_en.lower())
    return f"https://source.unsplash.com/featured/800x800?food,{clean_name}"

def map_csv_row(row):
    """Smart mapping for CSV imports"""
    new_row = {col: "" for col in INTERNAL_COLS}
    new_row["Status"] = "Available"
    for key, val in row.items():
        if not key: continue
        k, v = key.lower(), val.strip() if val else ""
        if any(x in k for x in ["item", "name"]):
            if "ar" in k or "عربي" in k: new_row["Item_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Item_KU"] = v
            else: new_row["Item_EN"] = v
        elif "cat" in k:
            if "ar" in k or "عربي" in k: new_row["Category_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Category_KU"] = v
            else: new_row["Category_EN"] = v
        elif "desc" in k:
            if "ar" in k or "عربي" in k: new_row["Description_AR"] = v
            elif "ku" in k or "کورد" in k: new_row["Description_KU"] = v
            else: new_row["Description_EN"] = v
        elif any(x in k for x in ["price", "سعر", "نرخ"]):
            new_row["Price"] = v
    
    # Fill gaps
    if not new_row["Category_AR"]: new_row["Category_AR"] = new_row["Category_EN"]
    if not new_row["Category_KU"]: new_row["Category_KU"] = new_row["Category_EN"]
    return new_row

# --- TRANSLATIONS ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search...', 'all': 'All', 'price': 'IQD', 'sold_out': 'SOLD OUT'},
    'ar': {'dir': 'rtl', 'search': 'بحث...', 'all': 'الكل', 'price': 'د.ع', 'sold_out': 'نفذت الكمية'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان...', 'all': 'هەموو', 'price': 'د.ع', 'sold_out': 'نەماوە'}
}

# --- TEMPLATES ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ lang_data.dir }}">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Luxe Menu</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Noto+Sans+Arabic:wght@300;500;700&display=swap" rel="stylesheet">
  <style>
    :root { --gold: #d4af37; --bg: #0a0a0b; --surface: #161618; --text: #f8f9fa; --muted: #a0a0a5; }
    body { background: var(--bg); color: var(--text); font-family: 'Noto Sans Arabic', sans-serif; margin: 0; }
    .hero { height: 120px; display: flex; align-items: center; justify-content: center; background: linear-gradient(to bottom, #1a1a1c, var(--bg)); border-bottom: 1px solid #222; }
    .logo { font-family: 'Playfair Display', serif; color: var(--gold); font-size: 2.2rem; letter-spacing: 3px; }
    .lang-nav { display: flex; justify-content: center; gap: 15px; padding: 10px; }
    .lang-nav a { color: var(--muted); text-decoration: none; font-size: 0.8rem; text-transform: uppercase; }
    .lang-nav a.active { color: var(--gold); border-bottom: 1px solid var(--gold); }
    .search-bar { position: sticky; top: 0; z-index: 100; background: rgba(10,10,11,0.9); backdrop-filter: blur(15px); padding: 15px; }
    .search-input { width: 100%; max-width: 500px; display: block; margin: auto; background: var(--surface); border: 1px solid #333; padding: 12px 20px; border-radius: 50px; color: white; }
    .cats { display: flex; gap: 10px; overflow-x: auto; padding: 10px 20px; scrollbar-width: none; }
    .cat-chip { padding: 8px 18px; border-radius: 50px; background: transparent; border: 1px solid #333; color: var(--muted); white-space: nowrap; cursor: pointer; font-size: 0.9rem; }
    .cat-chip.active { background: var(--gold); color: black; border-color: var(--gold); font-weight: bold; }
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 20px; max-width: 1200px; margin: auto; }
    .item-card { background: var(--surface); border-radius: 15px; overflow: hidden; border: 1px solid #222; position: relative; }
    .item-card.sold-out { opacity: 0.4; filter: grayscale(1); }
    .sold-label { position: absolute; top: 15px; right: 15px; background: red; color: white; padding: 2px 10px; border-radius: 4px; font-weight: bold; font-size: 0.7rem; z-index: 5; }
    .item-card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; }
    .item-info { padding: 15px; }
    .item-title { font-size: 1.2rem; margin: 0; display: flex; justify-content: space-between; align-items: baseline; }
    .item-price { color: var(--gold); font-weight: bold; }
    .item-desc { color: var(--muted); font-size: 0.85rem; margin-top: 8px; line-height: 1.4; }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="hero"><div class="logo">LUXE</div></div>
  <div class="lang-nav">
    <a href="?l=en" class="{% if lang=='en' %}active{% endif %}">EN</a>
    <a href="?l=ar" class="{% if lang=='ar' %}active{% endif %}">AR</a>
    <a href="?l=ku" class="{% if lang=='ku' %}active{% endif %}">KU</a>
  </div>
  <div class="search-bar"><input type="text" id="sq" class="search-input" placeholder="{{ lang_data.search }}"></div>
  <div class="cats">
    <div class="cat-chip active" data-c="all">{{ lang_data.all }}</div>
    {% for c in categories %}<div class="cat-chip" data-c="{{ c }}">{{ c }}</div>{% endfor %}
  </div>
  <div class="menu-grid">
    {% for i in items %}
    <div class="item-card {% if i.Status == 'Sold Out' %}sold-out{% endif %}" data-cat="{{ i['Category_' ~ lang|upper] }}" data-text="{{ i['Item_' ~ lang|upper] }}">
      {% if i.Status == 'Sold Out' %}<div class="sold-label">{{ lang_data.sold_out }}</div>{% endif %}
      <img src="{{ i.image }}" loading="lazy">
      <div class="item-info">
        <div class="item-title">
            <span>{{ i['Item_' ~ lang|upper] }}</span>
            <span class="item-price">{{ i.Price }} <small>{{ lang_data.price }}</small></span>
        </div>
        <p class="item-desc">{{ i['Description_' ~ lang|upper] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>
  <div style="text-align:center; padding: 40px;"><a href="/admin" style="color:#333; text-decoration:none; font-size:0.7rem;">Staff Only</a></div>
  <script>
    const sq = document.getElementById('sq');
    const chips = document.querySelectorAll('.cat-chip');
    const cards = document.querySelectorAll('.item-card');
    let curC = 'all';
    function filter() {
      const val = sq.value.toLowerCase();
      cards.forEach(c => {
        const mQ = c.getAttribute('data-text').toLowerCase().includes(val);
        const mC = curC === 'all' || c.getAttribute('data-cat') === curC;
        c.hidden = !(mQ && mC);
      });
    }
    sq.addEventListener('input', filter);
    chips.forEach(b => b.addEventListener('click', () => {
      chips.forEach(x => x.classList.remove('active'));
      b.classList.add('active'); curC = b.getAttribute('data-c'); filter();
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
    body { font-family: sans-serif; background: #0f172a; color: white; padding: 20px; max-width: 1100px; margin: auto; }
    .card { background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 25px; }
    input, select, textarea { width: 100%; padding: 12px; margin: 8px 0; background: #0f172a; border: 1px solid #444; color: white; border-radius: 6px; box-sizing: border-box; }
    .btn { background: #d4af37; color: black; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; }
    .btn-blue { background: #3b82f6; color: white; }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    th, td { padding: 12px; border-bottom: 1px solid #334155; text-align: left; }
    .badge { padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; }
    .Available { background: #065f46; } .Sold-Out { background: #991b1b; }
</style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1>Menu Studio</h1>
        <a href="/admin/logout" style="color:#ef4444; text-decoration:none;">Logout</a>
    </div>

    <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 20px;">
        <div class="card">
            <h3>Add / Edit Item</h3>
            <form action="/admin/save" method="post" enctype="multipart/form-data">
                <input type="hidden" name="idx" id="idx" value="-1">
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <input name="Item_EN" id="i_name" placeholder="Name (English)" required>
                    <input name="Category_EN" id="i_cat" placeholder="Category (English)" required>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                    <input name="Price" id="i_price" placeholder="Price (e.g. 12,000)" required>
                    <select name="Status" id="i_status">
                        <option value="Available">Available</option>
                        <option value="Sold Out">Sold Out</option>
                    </select>
                    <div style="padding-top:8px;"><input type="file" name="img" style="margin:0; font-size:10px;"></div>
                </div>
                <textarea name="Description_EN" id="i_desc" placeholder="Brief description..."></textarea>
                <button class="btn" id="i_submit">Add Item</button>
                <button type="button" class="btn" style="background:#333; color:white;" onclick="resetF()">Clear</button>
            </form>
        </div>

        <div class="card">
            <h3>CSV Bulk Import</h3>
            <p style="font-size:0.8rem; color:#94a3b8;">Upload .csv to sync menu instantly.</p>
            <form action="/admin/upload_csv" method="post" enctype="multipart/form-data">
                <input type="file" name="csv_file" accept=".csv" required>
                <button class="btn btn-blue">Upload & Sync</button>
            </form>
        </div>
    </div>

    <div class="card">
        <h3>Menu Inventory</h3>
        <table>
            <tr><th>Item</th><th>Category</th><th>Price</th><th>Status</th><th>Action</th></tr>
            {% for item in items %}
            <tr>
                <td>{{ item.Item_EN }}</td>
                <td>{{ item.Category_EN }}</td>
                <td>{{ item.Price }}</td>
                <td><span class="badge {{ item.Status|replace(' ','-') }}">{{ item.Status }}</span></td>
                <td>
                    <button class="btn" style="padding:5px 10px; font-size:0.7rem;" onclick="editI({{ loop.index0 }}, {{ item | tojson }})">Edit</button>
                    <a href="/admin/delete/{{ loop.index0 }}" style="color:#ef4444; margin-left:10px; font-size:0.7rem;" onclick="return confirm('Delete?')">Remove</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <script>
        function editI(idx, data) {
            document.getElementById('idx').value = idx;
            document.getElementById('i_name').value = data.Item_EN;
            document.getElementById('i_cat').value = data.Category_EN;
            document.getElementById('i_price').value = data.Price;
            document.getElementById('i_status').value = data.Status;
            document.getElementById('i_desc').value = data.Description_EN;
            document.getElementById('i_submit').innerText = "Update Item";
            window.scrollTo(0,0);
        }
        function resetF() {
            document.getElementById('idx').value = "-1";
            document.getElementById('i_submit').innerText = "Add Item";
            document.querySelector('form').reset();
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
    raw_items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = sorted(list(set(item.get(cat_key, "") for item in raw_items if item.get(cat_key))))
    for item in raw_items: 
        item['image'] = get_image_url(item.get("Item_EN", ""))
    return render_template_string(PUBLIC_HTML, items=raw_items, categories=categories, lang=lang, lang_data=LANG_MAP[lang])

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
    return render_template_string('<body style="background:#0f172a; color:white; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post"><h2>Admin Key</h2><input type="password" name="password" style="padding:10px; border-radius:5px;"><button style="padding:10px; background:#d4af37; border:none; border-radius:5px; margin-left:10px; cursor:pointer;">Enter</button></form></body>')

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
    
    # Sync translations automatically
    for s in ["AR", "KU"]:
        if not new_data[f"Category_{s}"]: new_data[f"Category_{s}"] = new_data["Category_EN"]
        if not new_data[f"Item_{s}"]: new_data[f"Item_{s}"] = new_data["Item_EN"]
        if not new_data[f"Description_{s}"]: new_data[f"Description_{s}"] = new_data["Description_EN"]

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
        items = load_menu()
        
        for row in reader:
            mapped = map_csv_row(row)
            # Check for existing item by English Name to update instead of duplicate
            found = False
            for i, existing in enumerate(items):
                if existing["Item_EN"] == mapped["Item_EN"]:
                    items[i] = mapped
                    found = True
                    break
            if not found: items.append(mapped)
            
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
