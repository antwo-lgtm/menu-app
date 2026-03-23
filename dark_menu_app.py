import os, csv, io
from flask import Flask, request, redirect, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = "restaurant_final_2026"

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploads"
ADMIN_PASS = "1234" # CHANGE THIS BEFORE GOING LIVE
COLS = ["C_EN", "C_AR", "C_KU", "N_EN", "N_AR", "N_KU", "D_EN", "D_AR", "D_KU", "Price", "Img"]

if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

# --- DATABASE HELPERS ---
def load_db():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except: return []

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(data)

def get_logo():
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        if os.path.exists(os.path.join(UPLOAD_DIR, f"logo.{ext}")):
            return f"/uploads/logo.{ext}"
    return None

# --- HTML TEMPLATES ---
BASE_HTML = r'''
<!DOCTYPE html>
<html lang="{{l}}" dir="{{ 'rtl' if l in ['ar','ku'] else 'ltr' }}">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { background:#0a0a0b; color:#fff; font-family:sans-serif; margin:0; padding-bottom:50px; line-height:1.5; }
        .header { text-align:center; padding:30px; border-bottom:1px solid #222; }
        .logo { max-height: 80px; margin-bottom:15px; }
        .nav { display:flex; justify-content:center; gap:20px; margin: 20px 0; }
        .nav a { color:#666; text-decoration:none; font-weight:bold; font-size:14px; padding: 5px 10px; border-radius: 5px; }
        .nav a.active { color:#c5a059; background: #1a1a1a; }
        .item { padding:15px; border-bottom:1px solid #1a1a1a; display:flex; gap:15px; align-items:center; max-width: 800px; margin: auto; }
        .item img { width:90px; height:90px; object-fit:cover; border-radius:10px; background:#111; flex-shrink: 0; }
        .info { flex:1; }
        .price { color:#c5a059; font-weight:bold; font-size:1.1rem; }
        h3 { margin:0; font-size:1.1rem; color: #eee; }
        p { color:#888; font-size:0.9rem; margin:5px 0 0 0; }
    </style>
</head>
<body>
    <div class="header">
        {% set lp = logo_func() %}
        {% if lp %}<img src="{{ lp }}" class="logo">{% else %}<h1>RESTAURANT MENU</h1>{% endif %}
        <div class="nav">
            <a href="?l=en" class="{{'active' if l=='en'}}">EN</a>
            <a href="?l=ar" class="{{'active' if l=='ar'}}">AR</a>
            <a href="?l=ku" class="{{'active' if l=='ku'}}">KU</a>
        </div>
    </div>
    {% for i in items %}
    <div class="item">
        {% if i.Img %}<img src="/uploads/{{i.Img}}">{% endif %}
        <div class="info">
            <div style="display:flex; justify-content:space-between">
                <h3>{{ i['N_'~l|upper] or i['N_EN'] }}</h3>
                <span class="price">{{ i.Price }}</span>
            </div>
            <p>{{ i['D_'~l|upper] or i['D_EN'] }}</p>
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

ADMIN_HTML = r'''
<body style="background:#000; color:#fff; font-family:sans-serif; padding:30px;">
    <h2>Admin Dashboard</h2>
    <div style="display:flex; gap:20px; margin-bottom:30px;">
        <div style="background:#111; padding:20px; border-radius:8px; flex:1; border:1px solid #333;">
            <h3>1. Logo</h3>
            <form action="/admin/logo" method="post" enctype="multipart/form-data">
                <input type="file" name="f" required>
                <button style="background:gold; border:none; padding:8px 15px; cursor:pointer; font-weight:bold; margin-top:10px;">Upload Logo</button>
            </form>
        </div>
        <div style="background:#111; padding:20px; border-radius:8px; flex:2; border:1px solid #333;">
            <h3>2. Sync CSV (Cat, Name, Desc, Price)</h3>
            <div style="display:flex; gap:10px;">
                <form action="/sync/EN" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>Sync EN</button></form>
                <form action="/sync/AR" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>Sync AR</button></form>
                <form action="/sync/KU" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>Sync KU</button></form>
            </div>
        </div>
    </div>

    <h3>3. Menu Management</h3>
    <table style="width:100%; border-collapse:collapse;">
        <tr style="text-align:left; background:#222; border-bottom: 2px solid #444;"><th>Name (EN)</th><th>Price</th><th>Photo</th><th>Actions</th></tr>
        {% for i in items %}
        <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">{{ i.N_EN }}</td>
            <td>{{ i.Price }}</td>
            <td>
                <form action="/photo/{{loop.index0}}" method="post" enctype="multipart/form-data">
                    <input type="file" name="f" style="font-size:10px;"><button>Update</button>
                </form>
            </td>
            <td>
                <a href="/edit/{{loop.index0}}" style="color:gold; text-decoration:none; font-weight:bold;">EDIT</a> | 
                <a href="/del/{{loop.index0}}" style="color:red; text-decoration:none;" onclick="return confirm('Delete this?')">DEL</a>
            </td>
        </tr>
        {% endfor %}
    </table>
</body>
'''

EDIT_HTML = r'''
<body style="background:#000; color:#fff; font-family:sans-serif; padding:40px;">
    <h2>Manual Edit</h2>
    <form method="post">
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px;">
            <div>EN Name: <input name="N_EN" value="{{i.N_EN}}" style="width:100%; padding:10px;"></div>
            <div>AR Name: <input name="N_AR" value="{{i.N_AR}}" style="width:100%; padding:10px;"></div>
            <div>KU Name: <input name="N_KU" value="{{i.N_KU}}" style="width:100%; padding:10px;"></div>
        </div>
        <br>
        Price: <input name="Price" value="{{i.Price}}" style="padding:10px;"><br><br>
        <button style="background:gold; padding:15px 40px; font-weight:bold; cursor:pointer;">SAVE CHANGES</button>
        <a href="/admin" style="color:#888; margin-left:20px;">Cancel</a>
    </form>
</body>
'''

# --- ROUTES ---
@app.route("/")
def index():
    l = request.args.get("l", "en")
    return render_template_string(BASE_HTML, items=load_db(), l=l, logo_func=get_logo)

@app.route("/admin")
def admin():
    if not session.get("auth"): return redirect("/login")
    return render_template_string(ADMIN_HTML, items=load_db())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and request.form.get("p") == ADMIN_PASS:
        session["auth"] = True
        return redirect("/admin")
    return '<body style="background:#000; color:#fff; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post">Password: <input type="password" name="p" autofocus><button>Login</button></form></body>'

@app.route("/sync/<lang>", methods=["POST"])
def sync(lang):
    if not session.get("auth"): return redirect("/login")
    f = request.files.get("f")
    if not f: return redirect("/admin")
    stream = io.StringIO(f.read().decode("utf-8-sig"))
    rows = list(csv.reader(stream))[1:]
    db = load_db()
    while len(db) < len(rows): db.append({c: "" for c in COLS})
    for i, row in enumerate(rows):
        if len(row) < 2: continue
        db[i][f"C_{lang}"] = row[0].strip()
        db[i][f"N_{lang}"] = row[1].strip()
        db[i][f"D_{lang}"] = row[2].strip() if len(row) > 2 else ""
        if len(row) > 3: db[i]["Price"] = row[3].strip()
    save_db(db)
    return redirect("/admin")

@app.route("/edit/<int:idx>", methods=["GET", "POST"])
def edit(idx):
    if not session.get("auth"): return redirect("/login")
    db = load_db()
    if request.method == "POST":
        for k in request.form: db[idx][k] = request.form[k]
        save_db(db)
        return redirect("/admin")
    return render_template_string(EDIT_HTML, i=db[idx])

@app.route("/photo/<int:idx>", methods=["POST"])
def photo(idx):
    if not session.get("auth"): return redirect("/login")
    f = request.files.get("f")
    if f:
        ext = f.filename.rsplit('.', 1)[-1].lower()
        name = f"item_{idx}.{ext}"
        f.save(os.path.join(UPLOAD_DIR, name))
        db = load_db()
        db[idx]["Img"] = name
        save_db(db)
    return redirect("/admin")

@app.route("/admin/logo", methods=["POST"])
def logo_upload():
    if not session.get("auth"): return redirect("/login")
    f = request.files.get("f")
    if f:
        ext = f.filename.rsplit('.', 1)[-1].lower()
        for e in ['png','jpg','jpeg','webp']:
            old = os.path.join(UPLOAD_DIR, f"logo.{e}")
            if os.path.exists(old): os.remove(old)
        f.save(os.path.join(UPLOAD_DIR, f"logo.{ext}"))
    return redirect("/admin")

@app.route("/del/<int:idx>")
def delete(idx):
    if not session.get("auth"): return redirect("/login")
    db = load_db(); db.pop(idx); save_db(db)
    return redirect("/admin")

@app.route("/admin/logout")
def logout():
    session.pop("auth", None); return redirect("/")

@app.route("/uploads/<path:filename>")
def uploads(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_db([])
    app.run(debug=True, port=5000)
