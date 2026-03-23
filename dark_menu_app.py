import os, csv, io
from flask import Flask, request, redirect, render_template_string, session, send_from_directory

app = Flask(__name__)
app.secret_key = "simple_secret_2026"

DATA_FILE = "menu_data.csv"
UPLOAD_DIR = "uploads"
ADMIN_PASS = "1234"
# The columns the app uses internally
COLS = ["C_EN", "C_AR", "C_KU", "N_EN", "N_AR", "N_KU", "D_EN", "D_AR", "D_KU", "Price", "Img"]

if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

def load_db():
    if not os.path.exists(DATA_FILE): return []
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(data)

# --- THE SYNC LOGIC ---
def sync_file(file_stream, lang):
    stream = io.StringIO(file_stream.read().decode("utf-8-sig"))
    rows = list(csv.reader(stream))[1:] # Skip header row
    db = load_db()
    
    # Make sure DB has enough rows
    while len(db) < len(rows):
        db.append({c: "" for c in COLS})
        
    for i, row in enumerate(rows):
        if len(row) < 2: continue
        db[i][f"C_{lang}"] = row[0].strip()
        db[i][f"N_{lang}"] = row[1].strip()
        db[i][f"D_{lang}"] = row[2].strip() if len(row) > 2 else ""
        if len(row) > 3 and row[3].strip(): db[i]["Price"] = row[3].strip()
    save_db(db)

# --- HTML ---
BASE_HTML = r'''
<!DOCTYPE html>
<html lang="{{l}}" dir="{{ 'rtl' if l in ['ar','ku'] else 'ltr' }}">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { background:#000; color:#fff; font-family:sans-serif; margin:0; }
        .nav { padding:20px; text-align:center; border-bottom:1px solid #333; }
        .nav a { color:#aaa; margin:0 10px; text-decoration:none; }
        .nav a.active { color:gold; font-weight:bold; }
        .item { padding:15px; border-bottom:1px solid #222; display:flex; gap:15px; }
        .item img { width:80px; height:80px; object-fit:cover; border-radius:8px; }
        .price { color:gold; font-weight:bold; }
        .admin-box { background:#111; padding:20px; margin:20px; border-radius:8px; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="?l=en" class="{{'active' if l=='en'}}">EN</a>
        <a href="?l=ar" class="{{'active' if l=='ar'}}">AR</a>
        <a href="?l=ku" class="{{'active' if l=='ku'}}">KU</a>
    </div>
    {% for i in items %}
    <div class="item">
        {% if i.Img %}<img src="/uploads/{{i.Img}}">{% endif %}
        <div style="flex:1">
            <div style="display:flex; justify-content:space-between">
                <b>{{ i['N_'~l|upper] }}</b>
                <span class="price">{{ i.Price }}</span>
            </div>
            <p style="color:#888; font-size:14px; margin:5px 0;">{{ i['D_'~l|upper] }}</p>
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

ADMIN_HTML = r'''
<body style="background:#111; color:#fff; font-family:sans-serif; padding:20px;">
    <h2>Admin - Sync CSVs</h2>
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px;">
        <form action="/sync/EN" method="post" enctype="multipart/form-data">
            EN CSV: <input type="file" name="f"><button>Sync</button>
        </form>
        <form action="/sync/AR" method="post" enctype="multipart/form-data">
            AR CSV: <input type="file" name="f"><button>Sync</button>
        </form>
        <form action="/sync/KU" method="post" enctype="multipart/form-data">
            KU CSV: <input type="file" name="f"><button>Sync</button>
        </form>
    </div>
    <hr>
    <h3>Items List (Upload Photos)</h3>
    {% for i in items %}
    <div style="padding:10px; border-bottom:1px solid #333;">
        {{ i.N_EN }} - 
        <form action="/photo/{{loop.index0}}" method="post" enctype="multipart/form-data" style="display:inline;">
            <input type="file" name="f"><button>Upload Photo</button>
        </form>
        <a href="/del/{{loop.index0}}" style="color:red; float:right;">Delete</a>
    </div>
    {% endfor %}
</body>
'''

@app.route("/")
def index():
    l = request.args.get("l", "en")
    return render_template_string(BASE_HTML, items=load_db(), l=l)

@app.route("/admin")
def admin():
    if not session.get("auth"): return redirect("/login")
    return render_template_string(ADMIN_HTML, items=load_db())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and request.form.get("p") == ADMIN_PASS:
        session["auth"] = True
        return redirect("/admin")
    return '<body><form method="post">Pass: <input type="password" name="p"><button>Go</button></form></body>'

@app.route("/sync/<lang>", methods=["POST"])
def do_sync(lang):
    f = request.files.get("f")
    if f: sync_file(f, lang.upper())
    return redirect("/admin")

@app.route("/photo/<int:idx>", methods=["POST"])
def do_photo(idx):
    f = request.files.get("f")
    if f:
        ext = f.filename.rsplit('.', 1)[1]
        name = f"img_{idx}.{ext}"
        f.save(os.path.join(UPLOAD_DIR, name))
        db = load_db()
        db[idx]["Img"] = name
        save_db(db)
    return redirect("/admin")

@app.route("/del/<int:idx>")
def do_del(idx):
    db = load_db()
    db.pop(idx)
    save_db(db)
    return redirect("/admin")

@app.route("/uploads/<path:filename>")
def get_file(filename): return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_db([])
    app.run(debug=True)
