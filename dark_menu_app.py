import os, csv, io
from flask import Flask, request, redirect, url_for, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = "strict-menu-2026"

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploaded_assets"
LOGO_FILENAME = "logo"
ADMIN_PASSWORD = "1234" # Change this!

# Database Columns
COLS = [
    "Cat_EN", "Cat_AR", "Cat_KU",
    "Name_EN", "Name_AR", "Name_KU",
    "Desc_EN", "Desc_AR", "Desc_KU",
    "Price", "Image_File"
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- DATABASE LOGIC ---
def load_menu():
    if not os.path.exists(DATA_FILE): return []
    items = []
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader: items.append(row)
    except: pass
    return items

def save_menu(items):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLS)
        writer.writeheader()
        for i in items:
            row = {c: i.get(c, "") for c in COLS}
            writer.writerow(row)

def get_logo():
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"logo.{ext}")):
            return f"/uploads/logo.{ext}"
    return None

# --- SYNC BY ROW POSITION ---
def sync_csv(file_stream, lang):
    stream = io.StringIO(file_stream.read().decode("utf-8-sig"))
    reader = list(csv.reader(stream))
    rows = reader[1:] # Skip header
    
    db = load_menu()
    while len(db) < len(rows):
        db.append({c: "" for c in COLS})

    for idx, row in enumerate(rows):
        if len(row) < 2: continue
        db[idx][f"Cat_{lang}"] = row[0].strip()
        db[idx][f"Name_{lang}"] = row[1].strip()
        db[idx][f"Desc_{lang}"] = row[2].strip() if len(row) > 2 else ""
        if len(row) > 3 and row[3].strip():
            db[idx]["Price"] = row[3].strip()
            
    save_menu(db)

# --- TEMPLATES ---
PUBLIC_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{{ 'rtl' if lang in ['ar', 'ku'] else 'ltr' }}">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Menu</title>
    <style>
        body { background: #0a0a0b; color: #fff; font-family: sans-serif; margin: 0; padding-bottom: 60px; }
        .header { text-align: center; padding: 30px; border-bottom: 1px solid #222; }
        .logo { max-height: 80px; }
        .langs { display: flex; justify-content: center; gap: 20px; margin: 20px 0; }
        .langs a { color: #888; text-decoration: none; font-weight: bold; }
        .langs a.active { color: #c5a059; border-bottom: 2px solid #c5a059; }
        .cats { display: flex; gap: 10px; overflow-x: auto; padding: 15px; sticky; top: 0; background: #0a0a0b; z-index: 10; border-bottom: 1px solid #222; }
        .cat-btn { padding: 8px 18px; border-radius: 20px; border: 1px solid #333; white-space: nowrap; cursor: pointer; color: #888; }
        .cat-btn.active { background: #c5a059; color: #000; font-weight: bold; }
        .item-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; padding: 20px; }
        .card { background: #141416; border-radius: 12px; overflow: hidden; border: 1px solid #222; display: flex; flex-direction: column; }
        .card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; background: #222; }
        .info { padding: 15px; }
        .price { color: #c5a059; font-weight: bold; font-size: 1.1rem; }
        [hidden] { display: none !important; }
    </style>
</head>
<body>
    <div class="header">
        {% if logo %}<img src="{{ logo }}" class="logo">{% else %}<h1>RESTAURANT</h1>{% endif %}
        <div class="langs">
            <a href="?l=en" class="{{ 'active' if lang=='en' }}">EN</a>
            <a href="?l=ar" class="{{ 'active' if lang=='ar' }}">AR</a>
            <a href="?l=ku" class="{{ 'active' if lang=='ku' }}">KU</a>
        </div>
    </div>
    <div class="cats">
        <div class="cat-btn active" data-c="all">All</div>
        {% for c in categories %}<div class="cat-btn" data-c="{{ c }}">{{ c }}</div>{% endfor %}
    </div>
    <div class="item-grid">
        {% for i in items %}
        <div class="card" data-cat="{{ i['Cat_' ~ lang|upper] }}">
            {% if i.Image_File %}<img src="/uploads/{{ i.Image_File }}">{% endif %}
            <div class="info">
                <div style="display:flex; justify-content:space-between; align-items:start;">
                    <h3 style="margin:0;">{{ i['Name_' ~ lang|upper] or i['Name_EN'] }}</h3>
                    <span class="price">{{ i.Price }}</span>
                </div>
                <p style="color:#888; font-size:0.9rem;">{{ i['Desc_' ~ lang|upper] or i['Desc_EN'] }}</p>
            </div>
        </div>
        {% endfor %}
    </div>
    <script>
        const btns = document.querySelectorAll('.cat-btn');
        const cards = document.querySelectorAll('.card');
        btns.forEach(b => b.addEventListener('click', () => {
            btns.forEach(x => x.classList.remove('active'));
            b.classList.add('active');
            cards.forEach(c => c.hidden = (b.dataset.c !== 'all' && c.dataset.cat !== b.dataset.c));
        }));
    </script>
</body>
</html>
'''

ADMIN_HTML = r'''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Admin</title>
<style>
    body { font-family: sans-serif; background: #0a0a0a; color: #eee; padding: 20px; }
    .box { background: #161616; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #222; }
    input, select { padding: 10px; margin: 5px 0; width: 100%; box-sizing: border-box; background: #000; color: #fff; border: 1px solid #333; }
    .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; background: #c5a059; }
    table { width: 100%; border-collapse: collapse; }
    td, th { padding: 12px; border-bottom: 1px solid #222; text-align: left; }
</style>
</head>
<body>
    <div style="display:flex; justify-content:space-between;">
        <h2>Menu Manager</h2>
        <a href="/admin/logout" style="color:red;">Logout</a>
    </div>

    <div class="box">
        <h3>1. Logo</h3>
        <form action="/admin/logo" method="post" enctype="multipart/form-data">
            <input type="file" name="f" required>
            <button class="btn">Upload Logo</button>
        </form>
    </div>

    <div class="box">
        <h3>2. Sync CSV (Cat-Name-Desc-Price)</h3>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
            <form action="/admin/sync/EN" method="post" enctype="multipart/form-data">
                <input type="file" name="f" required><button class="btn" style="width:100%">Sync EN</button>
            </form>
            <form action="/admin/sync/AR" method="post" enctype="multipart/form-data">
                <input type="file" name="f" required><button class="btn" style="width:100%; background:#10b981;">Sync AR</button>
            </form>
            <form action="/admin/sync/KU" method="post" enctype="multipart/form-data">
                <input type="file" name="f" required><button class="btn" style="width:100%; background:#f59e0b;">Sync KU</button>
            </form>
        </div>
    </div>

    <div class="box">
        <h3>3. Item List (Upload Photos)</h3>
        <table>
            <tr><th>Name (EN)</th><th>Price</th><th>Photo</th><th>Action</th></tr>
            {% for item in items %}
            <tr>
                <td>{{ item.Name_EN }}</td>
                <td>{{ item.Price }}</td>
                <td>
                    <form action="/admin/photo/{{ loop.index0 }}" method="post" enctype="multipart/form-data" style="display:flex; gap:5px;">
                        <input type="file" name="f" required style="width:150px; font-size:10px;">
                        <button class="btn" style="padding:5px 10px;">Upload</button>
                    </form>
                </td>
                <td><a href="/admin/del/{{ loop.index0 }}" style="color:red;">Del</a></td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
'''

# --- ROUTES ---
@app.route("/")
def index():
    lang = request.args.get("l", "en")
    db = load_menu()
    cat_key = f"Cat_{lang.upper()}"
    cats = []
    for i in db:
        if i.get(cat_key) and i[cat_key] not in cats: cats.append(i[cat_key])
    return render_template_string(PUBLIC_HTML, items=db, categories=cats, lang=lang, logo=get_logo())

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and request.form.get("p") == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect("/admin")
    return '<body><form method="post"><input type="password" name="p"><button>Login</button></form></body>'

@app.route("/admin")
def admin():
    if not session.get("admin"): return redirect("/admin/login")
    return render_template_string(ADMIN_HTML, items=load_menu())

@app.route("/admin/sync/<l>", methods=["POST"])
def sync(l):
    if not session.get("admin"): return redirect("/")
    f = request.files.get("f")
    if f: sync_csv(f, l.upper())
    return redirect("/admin")

@app.route("/admin/photo/<int:idx>", methods=["POST"])
def upload_photo(idx):
    if not session.get("admin"): return redirect("/")
    f = request.files.get("f")
    if f:
        ext = f.filename.rsplit('.', 1)[1].lower()
        fname = f"item_{idx}.{ext}"
        f.save(os.path.join(UPLOAD_DIR, fname))
        db = load_menu()
        db[idx]["Image_File"] = fname
        save_menu(db)
    return redirect("/admin")

@app.route("/admin/logo", methods=["POST"])
def upload_logo():
    if not session.get("admin"): return redirect("/")
    f = request.files.get("f")
    if f:
        ext = f.filename.rsplit('.', 1)[1].lower()
        for e in ['png','jpg','jpeg','webp']:
            if os.path.exists(os.path.join(UPLOAD_DIR, f"logo.{e}")): os.remove(os.path.join(UPLOAD_DIR, f"logo.{e}"))
        f.save(os.path.join(UPLOAD_DIR, f"logo.{ext}"))
    return redirect("/admin")

@app.route("/admin/del/<int:idx>")
def delete(idx):
    if not session.get("admin"): return redirect("/")
    db = load_menu()
    if 0 <= idx < len(db): db.pop(idx); save_menu(db)
    return redirect("/admin")

@app.route("/admin/logout")
def logout():
    session.pop("admin", None); return redirect("/")

@app.route("/uploads/<f>")
def uploads(f): return send_from_directory(UPLOAD_DIR, f)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
