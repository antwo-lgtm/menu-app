import os, csv, hashlib, urllib.parse, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ultra-menu-sync-2026")

# --- CONFIGURATION ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
LOGO_FILENAME = "restaurant_logo_file"
ADMIN_PASSWORD = "1234" # Change this for production!
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

INTERNAL_COLS = [
    "Category_EN", "Category_AR", "Category_KU",
    "Item_EN", "Item_AR", "Item_KU",
    "Description_EN", "Description_AR", "Description_KU",
    "Price", "Status"
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- DATABASE UTILS ---
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
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}")):
            return f"/uploads/{LOGO_FILENAME}.{ext}"
    return None

def get_image_url(item_name_en):
    # Check for custom upload first
    digest = hashlib.sha1(item_name_en.encode("utf-8")).hexdigest()[:16]
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"{digest}.{ext}")):
            return f"/uploads/{digest}.{ext}"
    # Fallback to Unsplash
    q = urllib.parse.quote(item_name_en + " food")
    return f"https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500&q=80" # Default food placeholder

# --- SYNC ENGINE (Matches by Row Position) ---
def sync_language_csv(file_stream, lang_code):
    stream = io.StringIO(file_stream.read().decode("utf-8-sig"))
    reader = csv.reader(stream)
    next(reader, None) # Skip Header
    
    current_items = load_menu()
    rows = list(reader)
    
    # Ensure database has enough rows to match the CSV
    while len(current_items) < len(rows):
        current_items.append({col: "" for col in INTERNAL_COLS})

    for idx, row in enumerate(rows):
        if len(row) < 2: continue
        
        # Structure: 0:Category, 1:Name, 2:Description, 3:Price
        current_items[idx][f"Category_{lang_code}"] = row[0].strip()
        current_items[idx][f"Item_{lang_code}"] = row[1].strip()
        current_items[idx][f"Description_{lang_code}"] = row[2].strip() if len(row) > 2 else ""
        
        # Only English file or first upload usually sets the Price
        if len(row) > 3 and row[3].strip():
            current_items[idx]["Price"] = row[3].strip()
        
        if not current_items[idx]["Status"]:
            current_items[idx]["Status"] = "Available"

    save_menu(current_items)

# --- FRONTEND TEMPLATE ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ 'rtl' if lang in ['ar', 'ku'] else 'ltr' }}">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Premium Menu</title>
  <style>
    :root { --gold: #c5a059; --bg: #0c0c0d; --card: #141415; --text: #ffffff; --muted: #888; }
    body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; padding-bottom: 50px; }
    .header { text-align: center; padding: 40px 20px; border-bottom: 1px solid #222; }
    .logo-img { max-height: 100px; margin-bottom: 10px; }
    .lang-switcher { display: flex; justify-content: center; gap: 15px; margin-top: 15px; }
    .lang-switcher a { color: var(--muted); text-decoration: none; font-weight: bold; font-size: 14px; }
    .lang-switcher a.active { color: var(--gold); border-bottom: 2px solid var(--gold); }
    .cats { display: flex; gap: 10px; overflow-x: auto; padding: 20px; sticky; top: 0; background: var(--bg); z-index: 10; }
    .cat-chip { padding: 8px 20px; border-radius: 50px; border: 1px solid #333; white-space: nowrap; cursor: pointer; color: var(--muted); }
    .cat-chip.active { background: var(--gold); color: black; border-color: var(--gold); font-weight: bold; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 20px; }
    .item-card { background: var(--card); border-radius: 15px; overflow: hidden; border: 1px solid #222; position: relative; }
    .item-card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; }
    .item-info { padding: 15px; }
    .price { color: var(--gold); font-weight: bold; }
    .sold-out { opacity: 0.5; filter: grayscale(1); }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <div class="header">
    {% if logo_url %}<img src="{{ logo_url }}" class="logo-img">{% else %}<h1 style="color:var(--gold)">RESTAURANT</h1>{% endif %}
    <div class="lang-switcher">
      <a href="?l=en" class="{{ 'active' if lang=='en' }}">English</a>
      <a href="?l=ar" class="{{ 'active' if lang=='ar' }}">عربي</a>
      <a href="?l=ku" class="{{ 'active' if lang=='ku' }}">کوردی</a>
    </div>
  </div>
  <div class="cats">
    <div class="cat-chip active" data-c="all">All</div>
    {% for c in categories %}<div class="cat-chip" data-c="{{ c }}">{{ c }}</div>{% endfor %}
  </div>
  <div class="grid">
    {% for i in items %}
    <div class="item-card {{ 'sold-out' if i.Status != 'Available' }}" data-cat="{{ i['Category_' ~ lang|upper] }}">
      <img src="{{ i.image }}">
      <div class="item-info">
        <div style="display:flex; justify-content:space-between;">
          <h3 style="margin:0;">{{ i['Item_' ~ lang|upper] or i['Item_EN'] }}</h3>
          <span class="price">{{ i.Price }}</span>
        </div>
        <p style="color:var(--muted); font-size:14px;">{{ i['Description_' ~ lang|upper] or i['Description_EN'] }}</p>
      </div>
    </div>
    {% endfor %}
  </div>
  <script>
    const chips = document.querySelectorAll('.cat-chip');
    const cards = document.querySelectorAll('.item-card');
    chips.forEach(b => b.addEventListener('click', () => {
      chips.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const cat = b.dataset.c;
      cards.forEach(c => c.hidden = (cat !== 'all' && c.dataset.cat !== cat));
    }));
  </script>
</body>
</html>
'''

ADMIN_HTML = r'''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Admin Panel</title>
<style>
  body { font-family: sans-serif; background: #0a0a0b; color: white; padding: 40px; }
  .card { background: #161618; border: 1px solid #2a2a2c; padding: 25px; border-radius: 12px; margin-bottom: 20px; }
  .btn { padding: 12px 24px; border-radius: 6px; border: none; font-weight: bold; cursor: pointer; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
  input[type="file"] { background: #000; padding: 10px; width: 100%; box-sizing: border-box; border-radius: 6px; border: 1px solid #333; color: #888; }
  table { width: 100%; border-collapse: collapse; margin-top: 20px; }
  td, th { padding: 12px; border-bottom: 1px solid #222; text-align: left; }
</style>
</head>
<body>
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <h1>Admin Control</h1>
    <a href="/admin/logout" style="color:red;">Logout</a>
  </div>

  <div class="card">
    <h3>1. Restaurant Logo</h3>
    <form action="/admin/upload_logo" method="post" enctype="multipart/form-data">
      <input type="file" name="logo_file" required>
      <button class="btn" style="background:#c5a059; margin-top:10px;">Save Logo</button>
    </form>
  </div>

  <div class="card">
    <h3>2. Sync CSV Files</h3>
    <p style="color:#666">Format: Category, Name, Description, Price</p>
    <div class="grid">
      <form action="/admin/sync/EN" method="post" enctype="multipart/form-data" class="card" style="background:#111">
        <h4>English</h4>
        <input type="file" name="csv_file" required><br><br>
        <button class="btn" style="background:#3b82f6; color:white;">Sync English</button>
      </form>
      <form action="/admin/sync/AR" method="post" enctype="multipart/form-data" class="card" style="background:#111">
        <h4>Arabic</h4>
        <input type="file" name="csv_file" required><br><br>
        <button class="btn" style="background:#10b981; color:white;">Sync Arabic</button>
      </form>
      <form action="/admin/sync/KU" method="post" enctype="multipart/form-data" class="card" style="background:#111">
        <h4>Kurdish</h4>
        <input type="file" name="csv_file" required><br><br>
        <button class="btn" style="background:#f59e0b; color:white;">Sync Kurdish</button>
      </form>
    </div>
  </div>

  <div class="card">
    <h3>3. Current Items</h3>
    <table>
      <thead><tr><th>Name (EN)</th><th>Price</th><th>Action</th></tr></thead>
      <tbody>
        {% for item in items %}
        <tr>
          <td>{{ item.Item_EN }}</td>
          <td>{{ item.Price }}</td>
          <td>
            <a href="/admin/delete/{{ loop.index0 }}" style="color:red;">Delete</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</body>
</html>
'''

# --- ROUTES ---
@app.route("/")
def index():
    lang = request.args.get("l", "en")
    items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = []
    for i in items:
        c = i.get(cat_key)
        if c and c not in categories: categories.append(c)
    
    for i in items: i['image'] = get_image_url(i.get("Item_EN", ""))
    
    return render_template_string(PUBLIC_HTML, items=items, categories=categories, 
                                  lang=lang, logo_url=get_logo_url())

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST" and request.form.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))
    return '<body style="background:#0a0a0b; color:white; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post"><input type="password" name="password" placeholder="Key" style="padding:10px;"><button style="padding:10px;">Enter</button></form></body>'

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None); return redirect(url_for("index"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_HTML, items=load_menu())

@app.route("/admin/sync/<lang>", methods=["POST"])
def admin_sync(lang):
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("csv_file")
    if file: sync_language_csv(file, lang.upper())
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/upload_logo", methods=["POST"])
def upload_logo():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("logo_file")
    if file and file.filename:
        for ext in ALLOWED_EXTENSIONS:
            old_path = os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}")
            if os.path.exists(old_path): os.remove(old_path)
        ext = file.filename.rsplit('.', 1)[1].lower()
        file.save(os.path.join(UPLOAD_DIR, f"{LOGO_FILENAME}.{ext}"))
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
    app.run(debug=True, port=5000)
