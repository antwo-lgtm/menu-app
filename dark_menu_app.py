import os, csv, hashlib, urllib.parse, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "premium-v3-key-77")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

INTERNAL_COLS = [
    "Category_EN", "Category_AR", "Category_KU",
    "Item_EN", "Item_AR", "Item_KU",
    "Description_EN", "Description_AR", "Description_KU",
    "Price", "Status" # Status will be 'Available' or 'Sold Out'
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
            writer.writerow({col: item.get(col, "Available" if col == "Status" else "") for col in INTERNAL_COLS})

def get_image_url(item_name_en):
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    # 1. Check for uploaded file
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{digest}.{ext}")):
            return f"/uploads/{digest}.{ext}"
    # 2. Smart Auto-Fetch (Unsplash Source - high quality food photography)
    clean_name = urllib.parse.quote(item_name_en.lower())
    return f"https://source.unsplash.com/featured/800x800?food,{clean_name}"

# --- TRANSLATIONS ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search delicacies...', 'all': 'All', 'price': 'IQD', 'sold_out': 'SOLD OUT'},
    'ar': {'dir': 'rtl', 'search': 'بحث عن أطباق...', 'all': 'الكل', 'price': 'د.ع', 'sold_out': 'نفذت الكمية'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان بۆ خواردن...', 'all': 'هەموو', 'price': 'د.ع', 'sold_out': 'نەماوە'}
}

# --- TEMPLATES ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ lang_data.dir }}">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Elite Dining</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Noto+Sans+Arabic:wght@300;500;700&display=swap" rel="stylesheet">
  <style>
    :root { --gold: #d4af37; --bg: #0a0a0b; --surface: #161618; --text: #f8f9fa; --muted: #a0a0a5; }
    body { background: var(--bg); color: var(--text); font-family: 'Noto Sans Arabic', sans-serif; margin: 0; padding-bottom: 50px; }
    .hero { height: 15vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(to bottom, #1a1a1c, var(--bg)); }
    .logo { font-family: 'Playfair Display', serif; color: var(--gold); font-size: 2.5rem; letter-spacing: 2px; }
    
    .search-bar { position: sticky; top: 0; z-index: 100; background: rgba(10,10,11,0.8); backdrop-filter: blur(10px); padding: 15px; }
    .search-input { width: 100%; max-width: 600px; display: block; margin: auto; background: var(--surface); border: 1px solid #333; padding: 15px 25px; border-radius: 50px; color: white; font-size: 1rem; }
    
    .cats { display: flex; gap: 10px; overflow-x: auto; padding: 15px 20px; scrollbar-width: none; }
    .cat-chip { padding: 8px 20px; border-radius: 50px; background: transparent; border: 1px solid #333; color: var(--muted); white-space: nowrap; cursor: pointer; transition: 0.3s; }
    .cat-chip.active { background: var(--gold); color: black; border-color: var(--gold); font-weight: bold; }

    .menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 25px; padding: 20px; max-width: 1300px; margin: auto; }
    .item-card { background: var(--surface); border-radius: 20px; overflow: hidden; position: relative; border: 1px solid #222; }
    .item-card.sold-out { opacity: 0.5; filter: grayscale(0.8); }
    .img-container { position: relative; width: 100%; aspect-ratio: 1/1; }
    .img-container img { width: 100%; height: 100%; object-fit: cover; }
    .sold-badge { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-15deg); background: rgba(255,0,0,0.8); color: white; padding: 5px 20px; font-weight: bold; border-radius: 5px; z-index: 10; border: 2px solid white; }
    
    .item-body { padding: 20px; }
    .item-top { display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px; }
    .item-title { font-size: 1.3rem; margin: 0; font-weight: 700; }
    .item-price { color: var(--gold); font-weight: 800; font-size: 1.2rem; }
    .item-desc { color: var(--muted); font-size: 0.95rem; line-height: 1.5; margin: 0; }
    
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="hero"><div class="logo">LUXE MENU</div></div>
  <div class="search-bar"><input type="text" id="q" class="search-input" placeholder="{{ lang_data.search }}"></div>
  <div class="cats">
    <div class="cat-chip active" data-c="all">{{ lang_data.all }}</div>
    {% for c in categories %}<div class="cat-chip" data-c="{{ c }}">{{ c }}</div>{% endfor %}
  </div>
  
  <div class="menu-grid" id="grid">
    {% for item in items %}
    <div class="item-card {% if item.Status == 'Sold Out' %}sold-out{% endif %}" data-cat="{{ item['Category_' ~ lang|upper] }}" data-text="{{ item['Item_' ~ lang|upper] }} {{ item['Description_' ~ lang|upper] }}">
      <div class="img-container">
        {% if item.Status == 'Sold Out' %}<div class="sold-badge">{{ lang_data.sold_out }}</div>{% endif %}
        <img src="{{ item.image }}" loading="lazy">
      </div>
      <div class="item-body">
        <div class="item-top">
          <h3 class="item-title">{{ item['Item_' ~ lang|upper] }}</h3>
          <span class="item-price">{{ item.Price }} <small>{{ lang_data.price }}</small></span>
        </div>
        <p class="item-desc">{{ item['Description_' ~ lang|upper] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>

  <script>
    const q = document.getElementById('q');
    const chips = document.querySelectorAll('.cat-chip');
    const cards = document.querySelectorAll('.item-card');
    let curCat = 'all';

    function filter() {
      const val = q.value.toLowerCase();
      cards.forEach(c => {
        const matchesQ = c.getAttribute('data-text').toLowerCase().includes(val);
        const matchesC = curCat === 'all' || c.getAttribute('data-cat') === curCat;
        c.hidden = !(matchesQ && matchesC);
      });
    }
    q.addEventListener('input', filter);
    chips.forEach(btn => btn.addEventListener('click', () => {
      chips.forEach(x => x.classList.remove('active'));
      btn.classList.add('active');
      curCat = btn.getAttribute('data-c');
      filter();
    }));
  </script>
</body>
</html>
'''

ADMIN_HTML = r'''
<!doctype html>
<html>
<head>
    <meta charset="utf-8"><title>Admin Studio</title>
    <style>
        body { font-family: sans-serif; background: #0f172a; color: white; padding: 20px; }
        .card { background: #1e293b; padding: 20px; border-radius: 15px; border: 1px solid #334155; margin-bottom: 20px; }
        input, textarea, select { width: 100%; padding: 12px; margin: 10px 0; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 8px; box-sizing: border-box; }
        .btn { background: #d4af37; color: black; border: none; padding: 12px 25px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 15px; border-bottom: 1px solid #334155; text-align: left; }
        .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .Available { background: #10b981; color: white; }
        .Sold.Out { background: #ef4444; color: white; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1>Dashboard</h1>
        <a href="/admin/logout" style="color:#ef4444;">Logout</a>
    </div>

    <div class="card">
        <h3>Add / Edit Item</h3>
        <form action="/admin/save" method="post" enctype="multipart/form-data">
            <input type="hidden" name="item_index" id="item_index" value="-1">
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px;">
                <input name="Item_EN" id="f_name" placeholder="Name (EN)" required>
                <input name="Category_EN" id="f_cat" placeholder="Category (EN)" required>
                <input name="Price" id="f_price" placeholder="Price (e.g. 15,000)" required>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                <select name="Status" id="f_status">
                    <option value="Available">Available</option>
                    <option value="Sold Out">Sold Out</option>
                </select>
                <input type="file" name="img" style="margin:0;">
            </div>
            <textarea name="Description_EN" id="f_desc" placeholder="Description"></textarea>
            <button class="btn" id="f_submit">Save Item</button>
            <button type="button" class="btn" style="background:#444; color:white;" onclick="resetForm()">Clear</button>
        </form>
    </div>

    <div class="card">
        <table>
            <tr><th>Item</th><th>Category</th><th>Price</th><th>Status</th><th>Actions</th></tr>
            {% for item in items %}
            <tr>
                <td>{{ item.Item_EN }}</td>
                <td>{{ item.Category_EN }}</td>
                <td>{{ item.Price }}</td>
                <td><span class="status-badge {{ item.Status }}">{{ item.Status }}</span></td>
                <td>
                    <button class="btn" style="padding:5px 10px; font-size:0.8rem;" 
                    onclick="editItem({{ loop.index0 }}, {{ item | tojson }})">Edit</button>
                    <a href="/admin/delete/{{ loop.index0 }}" style="color:#ef4444; margin-left:10px;" onclick="return confirm('Delete?')">Del</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <script>
        function editItem(idx, data) {
            document.getElementById('item_index').value = idx;
            document.getElementById('f_name').value = data.Item_EN;
            document.getElementById('f_cat').value = data.Category_EN;
            document.getElementById('f_price').value = data.Price;
            document.getElementById('f_status').value = data.Status;
            document.getElementById('f_desc').value = data.Description_EN;
            document.getElementById('f_submit').innerText = "Update Item";
            window.scrollTo(0,0);
        }
        function resetForm() {
            document.getElementById('item_index').value = "-1";
            document.getElementById('f_submit').innerText = "Save Item";
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
    return render_template_string('<body style="background:#0a0a0b; color:white; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;"><form method="post"><h2>Admin Key</h2><input type="password" name="password" style="padding:10px; border-radius:5px;"><button style="padding:10px; background:#d4af37; border:none; margin-left:10px; border-radius:5px;">Enter</button></form></body>')

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
    idx = int(request.form.get("item_index", -1))
    
    new_data = {col: request.form.get(col, "").strip() for col in INTERNAL_COLS}
    
    # Auto-fill missing categories and items for translations
    for suffix in ["AR", "KU"]:
        if not new_data[f"Category_{suffix}"]: new_data[f"Category_{suffix}"] = new_data["Category_EN"]
        if not new_data[f"Item_{suffix}"]: new_data[f"Item_{suffix}"] = new_data["Item_EN"]
        if not new_data[f"Description_{suffix}"]: new_data[f"Description_{suffix}"] = new_data["Description_EN"]

    # Image Handling
    img = request.files.get("img")
    if img and img.filename:
        digest = hashlib.sha1(new_data["Item_EN"].encode("utf-8")).hexdigest()[:16]
        ext = img.filename.rsplit('.', 1)[1].lower()
        img.save(os.path.join(UPLOAD_DIR, f"{digest}.{ext}"))

    if idx == -1:
        items.append(new_data)
    else:
        items[idx] = new_data
        
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

@app.route("/uploads/<filename>")
def serve_upload(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_menu([])
    app.run(debug=True, port=5000)
