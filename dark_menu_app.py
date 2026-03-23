import os, csv, io
from flask import Flask, request, redirect, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = "no_fail_menu_2026"

# --- CONFIG ---
DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploads"
ADMIN_PASS = "1234"
COLS = ["C_EN", "C_AR", "C_KU", "N_EN", "N_AR", "N_KU", "D_EN", "D_AR", "D_KU", "Price", "Img", "Status"]

if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

# --- DB HELPERS ---
def load_db():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            return [dict(row) for row in csv.DictReader(f)]
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

# --- HTML TEMPLATE ---
BASE_HTML = r'''
<!DOCTYPE html>
<html lang="{{l}}" dir="{{ 'rtl' if l in ['ar','ku'] else 'ltr' }}">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { background:#0a0a0b; color:#fff; font-family:sans-serif; margin:0; padding-bottom:50px; }
        .header { text-align:center; padding:30px; border-bottom:1px solid #222; }
        .logo { max-height: 70px; margin-bottom:10px; }
        .nav { display:flex; justify-content:center; gap:15px; margin: 15px 0; }
        .nav a { color:#666; text-decoration:none; font-size:13px; padding:5px 12px; border-radius:5px; border:1px solid #222; }
        .nav a.active { color:#c5a059; border-color:#c5a059; background:#111; }
        
        .cat-section { padding: 10px 20px; background: #111; color: #c5a059; font-weight: bold; position: sticky; top: 0; z-index: 5; border-bottom: 1px solid #222; text-transform: uppercase; letter-spacing: 1px; }
        .item { padding:15px; border-bottom:1px solid #1a1a1a; display:flex; gap:15px; align-items:center; max-width: 700px; margin: auto; }
        .item.out { opacity: 0.4; filter: grayscale(1); }
        .item img { width:85px; height:85px; object-fit:cover; border-radius:10px; background:#111; flex-shrink: 0; }
        .info { flex:1; }
        .price { color:#c5a059; font-weight:bold; font-size:1.1rem; white-space: nowrap; }
        h3 { margin:0; font-size:1.1rem; }
        p { color:#888; font-size:0.85rem; margin:4px 0 0 0; line-height: 1.4; }
        .sold-badge { font-size: 10px; background: red; color: white; padding: 2px 5px; border-radius: 3px; margin-left: 5px; }
    </style>
</head>
<body>
    <div class="header">
        {% set lp = logo_func() %}
        {% if lp %}<img src="{{ lp }}" class="logo">{% else %}<h1>MENU</h1>{% endif %}
        <div class="nav">
            <a href="?l=en" class="{{'active' if l=='en'}}">English</a>
            <a href="?l=ar" class="{{'active' if l=='ar'}}">عربي</a>
            <a href="?l=ku" class="{{'active' if l=='ku'}}">کوردی</a>
        </div>
    </div>

    {% set last_cat = [] %}
    {% for i in items %}
        {# Grouping Logic #}
        {% set current_cat = i['C_'~l|upper] or i['C_EN'] %}
        {% if current_cat != last_cat[-1] %}
            <div class="cat-section">{{ current_cat }}</div>
            {% if last_cat.append(current_cat) %}{% endif %}
        {% endif %}

        <div class="item {{ 'out' if i.Status == 'Sold Out' }}">
            {% if i.Img %}<img src="/uploads/{{i.Img}}">{% endif %}
            <div class="info">
                <div style="display:flex; justify-content:space-between; align-items: flex-start;">
                    <h3>
                        {# SAFETY FALLBACK: If translation is missing, use English Name #}
                        {{ i['N_'~l|upper] or i['N_EN'] }}
                        {% if i.Status == 'Sold Out' %}<span class="sold-badge">X</span>{% endif %}
                    </h3>
                    <span class="price">{{ i.Price }}</span>
                </div>
                {# SAFETY FALLBACK: If translation is missing, use English Description #}
                <p>{{ i['D_'~l|upper] or i['D_EN'] }}</p>
            </div>
        </div>
    {% endfor %}
</body>
</html>
'''

# --- ADMIN TEMPLATES ---
ADMIN_HTML = r'''
<body style="background:#000; color:#fff; font-family:sans-serif; padding:20px;">
    <h2>Admin Center</h2>
    <div style="display:flex; gap:15px; margin-bottom:20px;">
        <div style="background:#111; padding:15px; border-radius:8px; border:1px solid #333; flex:1;">
            <b>1. Upload Logo</b>
            <form action="/admin/logo" method="post" enctype="multipart/form-data">
                <input type="file" name="f" required style="margin-top:5px;"><br>
                <button style="background:gold; padding:5px 10px; margin-top:10px; border:none; cursor:pointer;">Save Logo</button>
            </form>
        </div>
        <div style="background:#111; padding:15px; border-radius:8px; border:1px solid #333; flex:2;">
            <b>2. Bulk Sync (Row Match)</b>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <form action="/sync/EN" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>EN</button></form>
                <form action="/sync/AR" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>AR</button></form>
                <form action="/sync/KU" method="post" enctype="multipart/form-data"><input type="file" name="f" required><button>KU</button></form>
            </div>
        </div>
    </div>
    <table style="width:100%; border-collapse:collapse; background:#111;">
        <tr style="background:#222; text-align:left;">
            <th style="padding:10px;">Item (EN)</th><th>Price</th><th>Photo</th><th>Action</th>
        </tr>
        {% for i in items %}
        <tr style="border-bottom:1px solid #222;">
            <td style="padding:10px;">{{ i.N_EN }} <br><small style="color:{{ 'red' if i.Status=='Sold Out' else 'green' }}">{{ i.Status }}</small></td>
            <td>{{ i.Price }}</td>
            <td>
                <form action="/photo/{{loop.index0}}" method="post" enctype="multipart/form-data">
                    <input type="file" name="f" style="font-size:10px;"><button>Update</button>
                </form>
            </td>
            <td>
                <a href="/edit/{{loop.index0}}" style="color:gold;">Edit Text</a> | 
                <a href="/del/{{loop.index0}}" style="color:red;" onclick="return confirm('Delete?')">Del</a>
            </td>
        </tr>
        {% endfor %}
    </table>
</body>
'''

EDIT_HTML = r'''
<body style="background:#000; color:#fff; font-family:sans-serif; padding:30px;">
    <h2>Edit Item Details</h2>
    <form method="post">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
            <div>EN Name: <input name="N_EN" value="{{i.N_EN}}" style="width:100%;"></div>
            <div>Price: <input name="Price" value="{{i.Price}}" style="width:100%;"></div>
            <div>AR Name: <input name="N_AR" value="{{i.N_AR}}" style="width:100%;"></div>
            <div>KU Name: <input name="N_KU" value="{{i.N_KU}}" style="width:100%;"></div>
            <div>Availability: 
                <select name="Status">
                    <option value="Available" {{ 'selected' if i.Status=='Available' }}>Available</option>
                    <option value="Sold Out" {{ 'selected' if i.Status=='Sold Out' }}>Sold Out</option>
                </select>
            </div>
        </div>
        <br><button style="background:gold; padding:10px 40px; border:none; cursor:pointer;">SAVE CHANGES</button>
        <a href="/admin" style="color:#888; margin-left:20px;">Back</a>
    </form>
</body>
'''

# --- ROUTES ---
@app.route("/")
def index():
    l = request.args.get("l", "en")
    db = load_db()
    # Sort items by category so they group together
    db.sort(key=lambda x: x.get(f'C_{l.upper()}') or x.get('C_EN', ''))
    return render_template_string(BASE_HTML, items=db, l=l, logo_func=get_logo)

@app.route("/admin")
def admin():
    if not session.get("auth"): return redirect("/login")
    return render_template_string(ADMIN_HTML, items=load_db())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and request.form.get("p") == ADMIN_PASS:
        session["auth"] = True; return redirect("/admin")
    return '<body style="background:#000; color:#fff; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post">Pass: <input type="password" name="p" autofocus><button>Login</button></form></body>'

@app.route("/sync/<lang>", methods=["POST"])
def sync(lang):
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
        if not db[i].get("Status"): db[i]["Status"] = "Available"
    save_db(db); return redirect("/admin")

@app.route("/edit/<int:idx>", methods=["GET", "POST"])
def edit(idx):
    db = load_db()
    if request.method == "POST":
        for k in request.form: db[idx][k] = request.form[k]
        save_db(db); return redirect("/admin")
    return render_template_string(EDIT_HTML, i=db[idx])

@app.route("/photo/<int:idx>", methods=["POST"])
def photo(idx):
    f = request.files.get("f")
    if f:
        name = f"item_{idx}.jpg"
        f.save(os.path.join(UPLOAD_DIR, name))
        db = load_db(); db[idx]["Img"] = name; save_db(db)
    return redirect("/admin")

@app.route("/admin/logo", methods=["POST"])
def logo_up():
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
    db = load_db(); db.pop(idx); save_db(db); return redirect("/admin")

@app.route("/uploads/<path:filename>")
def uploads(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_db([])
    app.run(debug=True)
