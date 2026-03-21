import os
import csv
import io
import re
import json
import base64
import hashlib
import html
import urllib.request
import urllib.parse
from collections import OrderedDict
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_from_directory, session

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-menu-secret")

DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
EXPECTED_COLUMNS = ["Category", "Item Name", "Description", "Price"]
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)


def load_settings():
    defaults = {
        "site_title": "Restaurant Menu",
        "site_subtitle": "Local digital menu",
        "logo_path": "",
    }
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update({k: data.get(k, defaults[k]) for k in defaults})
        return defaults
    except Exception:
        return defaults


def save_settings(data):
    current = load_settings()
    current.update(data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def normalize_headers(row):
    fixed = {}
    for k, v in row.items():
        nk = k.strip() if isinstance(k, str) else k
        nv = v.strip() if isinstance(v, str) else v
        fixed[nk] = nv
    return fixed


def clean_item(item):
    return {
        "Category": str(item.get("Category", "") or "").strip(),
        "Item Name": str(item.get("Item Name", "") or "").strip(),
        "Description": str(item.get("Description", "") or "").strip(),
        "Price": str(item.get("Price", "") or "").strip(),
    }


def load_menu():
    if not os.path.exists(DATA_FILE):
        return []
    items = []
    with open(DATA_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = normalize_headers(row)
            item = clean_item(row)
            if not item["Item Name"]:
                continue
            items.append(item)
    return items


def save_menu(items):
    with open(DATA_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        for item in items:
            writer.writerow(clean_item(item))


def parse_csv_text(text):
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [col for col in EXPECTED_COLUMNS if col not in headers]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    items = []
    for row in reader:
        row = normalize_headers(row)
        item = clean_item(row)
        if not item["Item Name"]:
            continue
        items.append(item)
    return items


def sheets_to_csv_url(url):
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "docs.google.com" not in parsed.netloc:
        return url
    parts = parsed.path.strip("/").split("/")
    if "spreadsheets" not in parts:
        return url
    try:
        d_index = parts.index("d")
        sheet_id = parts[d_index + 1]
    except (ValueError, IndexError):
        return url

    gid = "0"
    if "gid" in qs and qs["gid"]:
        gid = qs["gid"][0]
    elif parsed.fragment.startswith("gid="):
        gid = parsed.fragment.replace("gid=", "", 1)

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def download_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def secure_filename_local(filename):
    filename = os.path.basename(filename)
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    return filename or "file"


def image_filename_for_item(item_name):
    digest = hashlib.sha1(item_name.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.png"


def upload_filename_for_item(item_name, original_name):
    ext = os.path.splitext(original_name)[1].lower() or ".png"
    digest = hashlib.sha1(item_name.encode("utf-8")).hexdigest()[:16]
    return f"{digest}{ext}"


def placeholder_svg_data_uri(title, subtitle="Menu Item"):
    title = html.escape(title)
    subtitle = html.escape(subtitle)
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='768' height='512'>
      <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='#171717'/>
          <stop offset='100%' stop-color='#27272a'/>
        </linearGradient>
      </defs>
      <rect width='100%' height='100%' fill='url(#bg)'/>
      <circle cx='640' cy='100' r='110' fill='#3f3f46' opacity='0.35'/>
      <circle cx='130' cy='420' r='140' fill='#52525b' opacity='0.25'/>
      <text x='50%' y='46%' dominant-baseline='middle' text-anchor='middle' fill='#fafafa' font-size='34' font-family='Tahoma, Arial'>{title}</text>
      <text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle' fill='#a1a1aa' font-size='20' font-family='Tahoma, Arial'>{subtitle}</text>
    </svg>
    """.strip()
    encoded = urllib.parse.quote(svg)
    return f"data:image/svg+xml;charset=utf-8,{encoded}"


def user_uploaded_image_url(item_name):
    digest = hashlib.sha1(item_name.encode("utf-8")).hexdigest()[:16]
    for name in os.listdir(UPLOAD_DIR):
        if name.startswith(digest + "."):
            return f"/uploads/{name}"
    return None


def ai_generated_image_url(item_name):
    filename = image_filename_for_item(item_name)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}"
    return None


def best_image_url(item_name, category):
    uploaded = user_uploaded_image_url(item_name)
    if uploaded:
        return uploaded
    generated = ai_generated_image_url(item_name)
    if generated:
        return generated
    return placeholder_svg_data_uri(item_name, category)


def generate_image_prompt(item_name, category):
    return (
        f"Restaurant menu photo of '{item_name}' from category '{category}'. "
        f"Dark elegant food photography, realistic plated presentation, centered composition, "
        f"premium restaurant style, studio lighting, clean background, no text, no watermark."
    )


def generate_item_image(item_name, category):
    client = get_openai_client()
    if client is None:
        return None
    filename = image_filename_for_item(item_name)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}"

    result = client.images.generate(
        model=OPENAI_IMAGE_MODEL,
        prompt=generate_image_prompt(item_name, category),
        size="1024x1024"
    )

    first = result.data[0]
    image_b64 = getattr(first, "b64_json", None) if not isinstance(first, dict) else first.get("b64_json")
    image_url = getattr(first, "url", None) if not isinstance(first, dict) else first.get("url")

    if image_b64:
        with open(path, "wb") as f:
            f.write(base64.b64decode(image_b64))
        return f"/images/{filename}"
    if image_url:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return f"/images/{filename}"
    return None


def is_admin():
    return session.get("is_admin") is True


def require_admin():
    if not is_admin():
        return redirect(url_for("admin_login"))
    return None


def build_item_view(item):
    return {
        **item,
        "ImageURL": best_image_url(item["Item Name"], item["Category"] or "بدون قسم"),
    }


BASE_HTML = r'''
<!doctype html>
<html lang="en" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg: #09090b;
      --panel: #111113;
      --panel-2: #18181b;
      --line: #27272a;
      --text: #fafafa;
      --muted: #a1a1aa;
      --accent: #eab308;
      --accent-2: #f59e0b;
      --shadow: 0 10px 30px rgba(0,0,0,.28);
      --radius: 20px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Tahoma, Arial, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(234,179,8,.09), transparent 22%),
        radial-gradient(circle at left bottom, rgba(245,158,11,.06), transparent 20%),
        var(--bg);
      color: var(--text);
    }
    a { color: inherit; text-decoration: none; }
    .topbar {
      position: sticky; top: 0; z-index: 30;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 14px 20px; backdrop-filter: blur(14px);
      background: rgba(9,9,11,.72); border-bottom: 1px solid rgba(255,255,255,.06);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-badge {
      width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: black; font-weight: 900;
      overflow: hidden;
    }
    .brand-badge img { width: 100%; height: 100%; object-fit: cover; }
    .nav { display: flex; flex-wrap: wrap; gap: 10px; }
    .nav a {
      padding: 10px 14px; border-radius: 999px; background: #17171a;
      border: 1px solid var(--line); color: #e4e4e7;
    }
    .container { max-width: 1320px; margin: 0 auto; padding: 24px 16px 40px; }
    .hero { display: grid; grid-template-columns: 1.2fr .8fr; gap: 18px; margin-bottom: 22px; }
    .card {
      background: linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,.01));
      border: 1px solid rgba(255,255,255,.07); border-radius: var(--radius);
      box-shadow: var(--shadow); padding: 22px;
    }
    .headline { font-size: clamp(28px, 4vw, 48px); line-height: 1.05; margin: 0 0 10px; font-weight: 800; }
    .sub { margin: 0; color: var(--muted); line-height: 1.8; font-size: 15px; }
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }
    .stat { padding: 14px; border-radius: 16px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.06); }
    .stat .num { font-size: 24px; font-weight: 800; margin-bottom: 6px; }
    .stat .lbl { color: var(--muted); font-size: 13px; }
    .search-card { display: flex; flex-direction: column; justify-content: center; }
    .field-label { color: var(--muted); font-size: 13px; margin-bottom: 7px; }
    .row { display: grid; grid-template-columns: 1.2fr .8fr auto; gap: 12px; align-items: end; }
    .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .input, .select, .btn, .file, textarea {
      width: 100%; border-radius: 16px; border: 1px solid var(--line);
      background: #101014; color: var(--text); padding: 13px 14px; font-size: 15px; outline: none;
    }
    textarea { min-height: 120px; resize: vertical; }
    .btn {
      cursor: pointer; background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #111; font-weight: 800; border: none; min-width: 140px;
    }
    .btn.secondary { background: #17171a; color: var(--text); border: 1px solid var(--line); }
    .flash {
      background: rgba(234,179,8,.12); color: #fcd34d; border: 1px solid rgba(234,179,8,.25);
      padding: 12px 14px; border-radius: 14px; margin-bottom: 16px;
    }
    .category-chips { display: flex; gap: 10px; overflow: auto; padding-bottom: 4px; margin: 16px 0 18px; }
    .chip {
      white-space: nowrap; padding: 11px 15px; border-radius: 999px; background: #141418;
      border: 1px solid var(--line); color: #d4d4d8; display: inline-flex; align-items: center; gap: 8px;
    }
    .chip.active { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #111; border-color: transparent; font-weight: 800; }
    .section-title { margin: 34px 0 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .section-title h2 { margin: 0; font-size: 26px; }
    .section-title .count { color: var(--muted); font-size: 13px; }
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(245px, 1fr)); gap: 16px; }
    .menu-item {
      overflow: hidden; border-radius: 22px;
      background: linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,.01));
      border: 1px solid rgba(255,255,255,.07); box-shadow: var(--shadow);
    }
    .menu-image { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; display: block; background: #0f0f12; }
    .menu-body { padding: 14px 14px 16px; }
    .menu-top { display: flex; justify-content: space-between; gap: 10px; align-items: start; margin-bottom: 8px; }
    .menu-name { margin: 0; font-size: 18px; line-height: 1.5; font-weight: 800; }
    .price {
      white-space: nowrap; padding: 7px 10px; border-radius: 999px; background: rgba(234,179,8,.12);
      color: #fcd34d; border: 1px solid rgba(234,179,8,.18); font-weight: 800; font-size: 14px;
    }
    .menu-desc { margin: 0; color: var(--muted); line-height: 1.7; min-height: 24px; font-size: 14px; }
    .menu-cat {
      display: inline-block; margin-top: 12px; padding: 7px 10px; border-radius: 999px;
      background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.06); color: #d4d4d8; font-size: 12px;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: right; vertical-align: top; }
    th { color: var(--muted); font-size: 13px; }
    .thumb { width: 56px; height: 56px; border-radius: 12px; object-fit: cover; background: #111; }
    .tiny { color: var(--muted); font-size: 12px; line-height: 1.7; }
    .footer { margin-top: 28px; color: var(--muted); text-align: center; font-size: 13px; padding: 14px; }
    @media (max-width: 980px) { .hero, .row, .row2 { grid-template-columns: 1fr; } .stats { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge">
        {% if settings.logo_path %}
          <img src="{{ settings.logo_path }}" alt="Logo">
        {% else %}
          M
        {% endif %}
      </div>
      <div>
        <div style="font-weight:800">{{ settings.site_title }}</div>
        <div style="font-size:12px;color:var(--muted)">{{ settings.site_subtitle }}</div>
      </div>
    </div>
    <div class="nav">
      {% if public_nav %}
        <a href="{{ url_for('index') }}">Menu</a>
        <a href="{{ url_for('admin_login') }}">Admin</a>
      {% else %}
        <a href="{{ url_for('index') }}">Public Menu</a>
        <a href="{{ url_for('admin_dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin_import') }}">Import</a>
        <a href="{{ url_for('admin_settings') }}">Settings</a>
        <a href="{{ url_for('admin_items') }}">Items</a>
        <a href="{{ url_for('generate_images_page') }}">Images</a>
        <a href="{{ url_for('admin_logout') }}">Logout</a>
      {% endif %}
    </div>
  </div>
  <div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for msg in messages %}
          <div class="flash">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ content|safe }}
    <div class="footer">Local first. Put it online later.</div>
  </div>
</body>
</html>
'''


def render_page(title, content, public_nav=True):
    return render_template_string(BASE_HTML, title=title, content=content, settings=load_settings(), public_nav=public_nav)


@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/")
def index():
    items = load_menu()
    q = request.args.get("q", "").strip().lower()
    selected_category = request.args.get("category", "").strip()

    categories = []
    seen = set()
    for item in items:
        cat = item["Category"] or "بدون قسم"
        if cat not in seen:
            seen.add(cat)
            categories.append(cat)

    filtered = []
    for item in items:
        blob = " ".join([item.get("Category", ""), item.get("Item Name", ""), item.get("Description", ""), item.get("Price", "")]).lower()
        if q and q not in blob:
            continue
        actual_cat = item.get("Category") or "بدون قسم"
        if selected_category and actual_cat != selected_category:
            continue
        filtered.append(item)

    grouped = OrderedDict()
    for item in filtered:
        cat = item["Category"] or "بدون قسم"
        grouped.setdefault(cat, []).append(build_item_view(item))
    grouped = OrderedDict((cat, rows) for cat, rows in grouped.items() if rows)

    content = render_template_string('''
    <div class="hero">
      <div class="card">
        <h1 class="headline">{{ settings.site_title }}</h1>
        <p class="sub">{{ settings.site_subtitle }}</p>
        <div class="stats">
          <div class="stat"><div class="num">{{ total_items }}</div><div class="lbl">عدد الأصناف</div></div>
          <div class="stat"><div class="num">{{ total_categories }}</div><div class="lbl">عدد الأقسام</div></div>
          <div class="stat"><div class="num">{{ with_images }}</div><div class="lbl">صور جاهزة</div></div>
        </div>
      </div>
      <div class="card search-card">
        <form method="get">
          <div class="row">
            <div>
              <div class="field-label">بحث</div>
              <input class="input" type="text" name="q" value="{{ q }}" placeholder="ابحث عن صنف أو قسم...">
            </div>
            <div>
              <div class="field-label">القسم</div>
              <select class="select" name="category">
                <option value="">كل الأقسام</option>
                {% for cat in categories %}
                  <option value="{{ cat }}" {% if cat == selected_category %}selected{% endif %}>{{ cat }}</option>
                {% endfor %}
              </select>
            </div>
            <div>
              <div class="field-label">&nbsp;</div>
              <button class="btn" type="submit">عرض</button>
            </div>
          </div>
        </form>
      </div>
    </div>

    <div class="category-chips">
      <a class="chip {% if not selected_category %}active{% endif %}" href="{{ url_for('index', q=q) }}">الكل</a>
      {% for cat in categories %}
        <a class="chip {% if cat == selected_category %}active{% endif %}" href="{{ url_for('index', q=q, category=cat) }}">{{ cat }}</a>
      {% endfor %}
    </div>

    {% if grouped %}
      {% for cat, rows in grouped.items() %}
        <div class="section-title">
          <h2>{{ cat }}</h2>
          <div class="count">{{ rows|length }} صنف</div>
        </div>
        <div class="menu-grid">
          {% for item in rows %}
            <article class="menu-item">
              <img class="menu-image" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}">
              <div class="menu-body">
                <div class="menu-top">
                  <h3 class="menu-name">{{ item['Item Name'] }}</h3>
                  {% if item['Price'] %}
                    <div class="price">{{ item['Price'] }} د.ع</div>
                  {% endif %}
                </div>
                <p class="menu-desc">{{ item['Description'] or '' }}</p>
                <span class="menu-cat">{{ item['Category'] or 'بدون قسم' }}</span>
              </div>
            </article>
          {% endfor %}
        </div>
      {% endfor %}
    {% else %}
      <div class="card">لا توجد أصناف مطابقة.</div>
    {% endif %}
    ''', settings=load_settings(), q=q, selected_category=selected_category, categories=categories, grouped=grouped, total_items=len(items), total_categories=len(categories), with_images=sum(1 for item in items if user_uploaded_image_url(item["Item Name"]) or ai_generated_image_url(item["Item Name"])))
    return render_page("Menu", content, public_nav=True)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Logged in.")
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password.")
    content = render_template_string('''
    <div class="card" style="max-width:500px;margin:60px auto;">
      <h1 style="margin-top:0">Admin Login</h1>
      <p class="sub">Enter your admin password.</p>
      <form method="post">
        <div class="field-label">Password</div>
        <input class="input" type="password" name="password" placeholder="Password">
        <button class="btn" type="submit">Login</button>
      </form>
      <p class="tiny">Default password is 1234 unless you change MENU_ADMIN_PASSWORD.</p>
    </div>
    ''')
    return render_page("Admin Login", content, public_nav=True)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))


@app.route("/admin")
def admin_dashboard():
    guard = require_admin()
    if guard:
        return guard
    items = load_menu()
    content = render_template_string('''
    <div class="hero">
      <div class="card">
        <h1 class="headline">Admin Dashboard</h1>
        <p class="sub">Manage imports, settings, item images, and AI generation from here.</p>
      </div>
      <div class="card">
        <div class="stats">
          <div class="stat"><div class="num">{{ items|length }}</div><div class="lbl">Items</div></div>
          <div class="stat"><div class="num">{{ with_uploads }}</div><div class="lbl">Uploaded images</div></div>
          <div class="stat"><div class="num">{{ with_ai }}</div><div class="lbl">AI images</div></div>
        </div>
      </div>
    </div>
    <div class="row2">
      <a class="card" href="{{ url_for('admin_import') }}"><h2 style="margin-top:0">Import</h2><p class="sub">Import CSV or Google Sheets.</p></a>
      <a class="card" href="{{ url_for('admin_settings') }}"><h2 style="margin-top:0">Settings</h2><p class="sub">Change title, subtitle, and logo.</p></a>
      <a class="card" href="{{ url_for('admin_items') }}"><h2 style="margin-top:0">Item Images</h2><p class="sub">Upload manual pictures for each menu item.</p></a>
      <a class="card" href="{{ url_for('generate_images_page') }}"><h2 style="margin-top:0">AI Images</h2><p class="sub">Generate images automatically if API key works.</p></a>
    </div>
    ''', items=items, with_uploads=sum(1 for item in items if user_uploaded_image_url(item["Item Name"])), with_ai=sum(1 for item in items if ai_generated_image_url(item["Item Name"])))
    return render_page("Admin Dashboard", content, public_nav=False)


@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    guard = require_admin()
    if guard:
        return guard
    if request.method == "POST":
        mode = request.form.get("mode")
        try:
            if mode == "csv":
                uploaded = request.files.get("csv_file")
                if not uploaded or not uploaded.filename:
                    raise ValueError("Choose a CSV file.")
                text = uploaded.read().decode("utf-8-sig", errors="replace")
                items = parse_csv_text(text)
                save_menu(items)
                flash(f"CSV imported: {len(items)} items.")
            elif mode == "sheet":
                sheet_url = request.form.get("sheet_url", "").strip()
                if not sheet_url:
                    raise ValueError("Paste a Google Sheets URL.")
                text = download_text(sheets_to_csv_url(sheet_url))
                items = parse_csv_text(text)
                save_menu(items)
                flash(f"Google Sheet imported: {len(items)} items.")
            else:
                raise ValueError("Invalid import mode.")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash(f"Import failed: {e}")
            return redirect(url_for("admin_import"))

    content = render_template_string('''
    <div class="card"><h1 style="margin-top:0">Import Menu</h1><p class="sub">Required columns: Category, Item Name, Description, Price</p></div>
    <div class="row2">
      <div class="card">
        <h2 style="margin-top:0">From CSV</h2>
        <form method="post" enctype="multipart/form-data">
          <input type="hidden" name="mode" value="csv">
          <div class="field-label">CSV file</div>
          <input class="file" type="file" name="csv_file" accept=".csv">
          <button class="btn" type="submit">Import CSV</button>
        </form>
      </div>
      <div class="card">
        <h2 style="margin-top:0">From Google Sheets</h2>
        <form method="post">
          <input type="hidden" name="mode" value="sheet">
          <div class="field-label">Google Sheets URL</div>
          <input class="input" type="url" name="sheet_url" placeholder="Paste Google Sheets URL">
          <button class="btn" type="submit">Import Google Sheet</button>
        </form>
      </div>
    </div>
    ''')
    return render_page("Admin Import", content, public_nav=False)


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    guard = require_admin()
    if guard:
        return guard
    settings = load_settings()
    if request.method == "POST":
        updates = {
            "site_title": request.form.get("site_title", "").strip() or settings["site_title"],
            "site_subtitle": request.form.get("site_subtitle", "").strip() or settings["site_subtitle"],
        }
        logo = request.files.get("logo_file")
        if logo and logo.filename:
            safe = secure_filename_local(logo.filename)
            ext = os.path.splitext(safe)[1].lower() or ".png"
            logo_name = f"site_logo{ext}"
            logo_path = os.path.join(UPLOAD_DIR, logo_name)
            logo.save(logo_path)
            updates["logo_path"] = f"/uploads/{logo_name}"
        save_settings(updates)
        flash("Settings updated.")
        return redirect(url_for("admin_settings"))

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Site Settings</h1>
      <form method="post" enctype="multipart/form-data">
        <div class="row2">
          <div>
            <div class="field-label">Main title</div>
            <input class="input" type="text" name="site_title" value="{{ settings.site_title }}">
          </div>
          <div>
            <div class="field-label">Subtitle</div>
            <input class="input" type="text" name="site_subtitle" value="{{ settings.site_subtitle }}">
          </div>
        </div>
        <div class="field-label" style="margin-top:10px;">Logo</div>
        <input class="file" type="file" name="logo_file" accept="image/*">
        {% if settings.logo_path %}
          <div style="margin:14px 0;"><img src="{{ settings.logo_path }}" alt="Logo" style="width:90px;height:90px;object-fit:cover;border-radius:16px;"></div>
        {% endif %}
        <button class="btn" type="submit">Save Settings</button>
      </form>
    </div>
    ''', settings=settings)
    return render_page("Admin Settings", content, public_nav=False)


@app.route("/admin/items", methods=["GET"])
def admin_items():
    guard = require_admin()
    if guard:
        return guard
    items = [build_item_view(item) for item in load_menu()]
    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">Item Images</h1>
      <p class="sub">Upload a manual picture for any item. Manual upload overrides AI image.</p>
    </div>
    <div class="card" style="overflow:auto;">
      <table>
        <thead>
          <tr>
            <th>Image</th>
            <th>Item</th>
            <th>Category</th>
            <th>Price</th>
            <th>Upload</th>
          </tr>
        </thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td><img class="thumb" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}"></td>
            <td>{{ item['Item Name'] }}</td>
            <td>{{ item['Category'] }}</td>
            <td>{{ item['Price'] }}</td>
            <td>
              <form method="post" action="{{ url_for('admin_upload_item_image') }}" enctype="multipart/form-data">
                <input type="hidden" name="item_name" value="{{ item['Item Name'] }}">
                <input type="file" name="item_image" accept="image/*" required>
                <button class="btn secondary" type="submit" style="margin-top:8px;">Upload</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    ''', items=items)
    return render_page("Admin Items", content, public_nav=False)


@app.route("/admin/upload-item-image", methods=["POST"])
def admin_upload_item_image():
    guard = require_admin()
    if guard:
        return guard
    item_name = request.form.get("item_name", "").strip()
    uploaded = request.files.get("item_image")
    if not item_name or not uploaded or not uploaded.filename:
        flash("Missing item or image.")
        return redirect(url_for("admin_items"))
    filename = upload_filename_for_item(item_name, uploaded.filename)
    uploaded.save(os.path.join(UPLOAD_DIR, filename))
    flash(f"Image uploaded for {item_name}.")
    return redirect(url_for("admin_items"))


@app.route("/admin/generate-images", methods=["GET", "POST"])
def generate_images_page():
    guard = require_admin()
    if guard:
        return guard
    items = load_menu()
    if request.method == "POST":
        limit_raw = request.form.get("limit", "12").strip()
        only_missing = request.form.get("only_missing") == "on"
        try:
            limit = max(1, min(100, int(limit_raw)))
        except Exception:
            limit = 12
        client = get_openai_client()
        if client is None:
            flash("OPENAI_API_KEY not found. Manual uploads will still work.")
            return redirect(url_for("generate_images_page"))

        generated = 0
        skipped = 0
        for item in items:
            if generated >= limit:
                break
            if only_missing and (user_uploaded_image_url(item["Item Name"]) or ai_generated_image_url(item["Item Name"])):
                skipped += 1
                continue
            try:
                if generate_item_image(item["Item Name"], item["Category"]):
                    generated += 1
            except Exception as e:
                flash(f"Failed on {item['Item Name']}: {e}")
                break
        flash(f"Images generated: {generated}. Skipped: {skipped}.")
        return redirect(url_for("generate_images_page"))

    preview = [build_item_view(item) for item in items[:12]]
    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">AI Images</h1>
      <p class="sub">This page is optional. Manual item upload works even if AI generation fails.</p>
    </div>
    <div class="card">
      <form method="post">
        <div class="row">
          <div>
            <div class="field-label">How many images</div>
            <input class="input" type="text" name="limit" value="12">
          </div>
          <div>
            <div class="field-label">Options</div>
            <label style="display:flex;gap:8px;align-items:center;padding:14px;border-radius:16px;border:1px solid var(--line);background:#101014;">
              <input type="checkbox" name="only_missing" checked>
              <span>Only for items without image</span>
            </label>
          </div>
          <div>
            <div class="field-label">&nbsp;</div>
            <button class="btn" type="submit">Generate</button>
          </div>
        </div>
      </form>
    </div>
    <div class="section-title"><h2>Preview</h2><div class="count">{{ preview|length }} items</div></div>
    <div class="menu-grid">
      {% for item in preview %}
      <article class="menu-item">
        <img class="menu-image" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}">
        <div class="menu-body">
          <div class="menu-top">
            <h3 class="menu-name">{{ item['Item Name'] }}</h3>
            {% if item['Price'] %}<div class="price">{{ item['Price'] }} د.ع</div>{% endif %}
          </div>
          <p class="menu-desc">{{ item['Description'] or '' }}</p>
          <span class="menu-cat">{{ item['Category'] or 'بدون قسم' }}</span>
        </div>
      </article>
      {% endfor %}
    </div>
    ''', preview=preview)
    return render_page("AI Images", content, public_nav=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
