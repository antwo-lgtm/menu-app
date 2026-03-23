import os, csv, hashlib, urllib.parse, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "triple-gold-uniform-2026")

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
LOGO_FILENAME = "restaurant_logo_file" 
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

# Internal Database columns
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

# --- THE UNIFORM SYNC LOGIC ---
def process_uniform_csv(file_stream, lang_code):
    """
    Processes CSV with structure: Category, Name, Description, Price
    lang_code: 'EN', 'AR', or 'KU'
    """
    stream = io.StringIO(file_stream.read().decode("utf-8-sig"))
    reader = csv.reader(stream)
    next(reader, None) # Skip Header Row
    
    current_items = load_menu()
    
    for row in reader:
        if len(row) < 2: continue # Ensure it has at least Category and Name
        
        in_cat = row[0].strip()
        in_name = row[1].strip()
        in_desc = row[2].strip() if len(row) > 2 else ""
        in_price = row[3].strip() if len(row) > 3 else ""

        found = False
        # Try to find existing item to merge
        for item in current_items:
            # We always match against the English Name (Item_EN) 
            # This assumes your AR/KU files use the English name in the 'Name' column 
            # to identify which item they are translating.
            if item["Item_EN"].lower() == in_name.lower():
                item[f"Category_{lang_code}"] = in_cat
                item[f"Item_{lang_code}"] = in_name # This stores the translated name
                item[f"Description_{lang_code}"] = in_desc
                if in_price: item["Price"] = in_price
                found = True
                break
        
        if not found:
            # Item doesn't exist, create it.
            new_item = {col: "" for col in INTERNAL_COLS}
            new_item[f"Category_{lang_code}"] = in_cat
            new_item[f"Item_{lang_code}"] = in_name
            new_item[f"Description_{lang_code}"] = in_desc
            new_item["Price"] = in_price
            new_item["Status"] = "Available"
            
            # If this is the EN file, it becomes the Master ID
            if lang_code == "EN":
                new_item["Item_EN"] = in_name
            else:
                # If uploading translations first, we still need a Master ID
                new_item["Item_EN"] = in_name 
                
            current_items.append(new_item)
            
    save_menu(current_items)

# --- TRANSLATION MAP ---
LANG_MAP = {
    'en': {'dir': 'ltr', 'search': 'Search...', 'all': 'All', 'price': 'IQD', 'sold': 'SOLD OUT'},
    'ar': {'dir': 'rtl', 'search': 'بحث...', 'all': 'الكل', 'price': 'د.ع', 'sold': 'نفذت'},
    'ku': {'dir': 'rtl', 'search': 'گەڕان...', 'all': 'هەموو', 'price': 'د.ع', 'sold': 'نەماوە'}
}

# --- HTML TEMPLATES ---
# (Includes the Sidebar/Layout logic from previous versions)

ADMIN_HTML = r'''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Restaurant Admin Gold</title>
<style>
    body { font-family: sans-serif; background: #0a0a0b; color: #eee; padding: 30px; line-height: 1.6; }
    .container { max-width: 1000px; margin: auto; }
    .card { background: #161618; border: 1px solid #2a2a2c; padding: 25px; border-radius: 12px; margin-bottom: 25px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
    .btn { padding: 12px; border-radius: 6px; border: none; font-weight: bold; cursor: pointer; width: 100%; transition: 0.2s; }
    .btn:hover { opacity: 0.8; }
    .en { background: #3b82f6; color: white; }
    .ar { background: #10b981; color: white; }
    .ku { background: #f59e0b; color: white; }
    .logo-btn { background: #c5a059; color: black; margin-top: 10px; width: auto; padding: 10px 30px; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { text-align: left; font-size: 12px; color: #666; padding: 10px; border-bottom: 2px solid #222; }
    td { padding: 15px; border-bottom: 1px solid #222; font-size: 14px; }
    .status-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; background: #333; }
</style>
</head>
<body>
    <div class="container">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h1>Menu Control Center</h1>
            <a href="/admin/logout" style="color:#ef4444; text-decoration:none; font-weight:bold;">Exit</a>
        </div>

        <div class="card">
            <h3>1. Branding</h3>
            <form action="/admin/upload_logo" method="post" enctype="multipart/form-data">
                <input type="file" name="logo_file" accept="image/*" required>
                <button class="btn logo-btn">Upload Header Logo</button>
            </form>
        </div>

        <div class="card">
            <h3>2. Triple CSV Sync (Uniform Structure)</h3>
            <p style="color:#888; font-size:13px;">Requirement: 4 columns in each file (Category, Name, Description, Price).</p>
            <div class="grid">
                <div class="card" style="background:#1c1c1e;">
                    <h4 style="margin-top:0;">English (Master)</h4>
                    <form action="/admin/sync/EN" method="post" enctype="multipart/form-data">
                        <input type="file" name="csv_file" required>
                        <button class="btn en">Sync EN</button>
                    </form>
                </div>
                <div class="card" style="background:#1c1c1e;">
                    <h4 style="margin-top:0;">Arabic</h4>
                    <form action="/admin/sync/AR" method="post" enctype="multipart/form-data">
                        <input type="file" name="csv_file" required>
                        <button class="btn ar">Sync AR</button>
                    </form>
                </div>
                <div class="card" style="background:#1c1c1e;">
                    <h4 style="margin-top:0;">Kurdish</h4>
                    <form action="/admin/sync/KU" method="post" enctype="multipart/form-data">
                        <input type="file" name="csv_file" required>
                        <button class="btn ku">Sync KU</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="card">
            <h3>3. Menu Overview</h3>
            <table>
                <thead><tr><th>Name (EN)</th><th>Category</th><th>Price</th><th>Action</th></tr></thead>
                <tbody>
                    {% for item in items %}
                    <tr>
                        <td><b>{{ item.Item_EN }}</b></td>
                        <td>{{ item.Category_EN }}</td>
                        <td>{{ item.Price }}</td>
                        <td><a href="/admin/delete/{{ loop.index0 }}" style="color:#ef4444; font-size:12px;">Delete</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
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
    items = load_menu()
    cat_key = f"Category_{lang.upper()}"
    categories = []
    for i in items:
        c = i.get(cat_key)
        if c and c not in categories: categories.append(c)
    for i in items: i['image'] = get_image_url(i.get("Item_EN", ""))
    return render_template_string(PUBLIC_HTML, items=items, categories=categories, lang=lang, lang_data=LANG_MAP[lang], logo_url=get_logo_url())

@app.route("/admin/sync/<lang>", methods=["POST"])
def admin_sync(lang):
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    file = request.files.get("csv_file")
    if file: process_uniform_csv(file, lang.upper())
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

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST" and request.form.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))
    return '<body style="background:#0a0a0b; color:white; display:flex; flex-direction:column; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;"><h2>Admin Access</h2><form method="post"><input type="password" name="password" style="padding:15px; border-radius:8px; border:1px solid #333; background:#111; color:white;"><br><br><button style="width:100%; padding:10px; background:#c5a059; border:none; border-radius:8px; font-weight:bold; cursor:pointer;">Enter</button></form></body>'

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_HTML, items=load_menu())

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
