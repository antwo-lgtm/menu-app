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

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    render_template_string,
    flash,
    send_from_directory,
    session,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ========== Railway / environment setup ==========
app = Flask(__name__)
port = int(os.environ.get("PORT", 8000))
host = "0.0.0.0"
secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-menu-key")
app.secret_key = secret_key

DATA_FILE = "menu_data.csv"
IMAGE_DIR = "generated_images"
UPLOAD_DIR = "uploaded_assets"
SETTINGS_FILE = "menu_settings.json"
EXPECTED_COLUMNS = ["Category", "Item Name", "Description", "Price"]
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "dall-e-3")
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ========== Helpers ==========
def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)

def load_settings():
    defaults = {
        "site_title": "قائمة المطعم",
        "site_subtitle": "قائمة رقمية حديثة",
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

def save_settings(new_data):
    current = load_settings()
    current.update(new_data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

def normalize_headers(row):
    return {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; menu/1.0)"},
    )
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
    ext = os.path.splitext(original_name)[1].lower()
    if not ext:
        ext = ".png"
    digest = hashlib.sha1(item_name.encode("utf-8")).hexdigest()[:16]
    return f"{digest}{ext}"

def placeholder_svg_data_uri(title, subtitle="صنف من القائمة"):
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
      <text x='50%' y='46%' dominant-baseline='middle' text-anchor='middle'
            fill='#fafafa' font-size='34' font-family='Tahoma, Arial'>{title}</text>
      <text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle'
            fill='#a1a1aa' font-size='20' font-family='Tahoma, Arial'>{subtitle}</text>
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
    return placeholder_svg_data_uri(item_name, category or "صنف فارغ")

def generate_image_prompt(item_name, category):
    return (
        f"Restaurant menu photo of '{item_name}' from category '{category}'. "
        "Dark elegant food photography, realistic plated presentation, centered composition, "
        "premium restaurant style, studio lighting, clean background, no text, no watermark."
    )

def generate_item_image(item_name, category):
    client = get_openai_client()
    if client is None:
        return None
    filename = image_filename_for_item(item_name)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}"

    try:
        result = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=generate_image_prompt(item_name, category),
            size="1024x1024",
            response_format="b64_json",
        )

        first = result.data[0]
        image_b64 = getattr(first, "b64_json", None)
        image_url = getattr(first, "url", None)

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
    except Exception as e:
        print(f"[Image gen error] {e}")
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
        "ImageURL": best_image_url(
            item["Item Name"], item["Category"] or "بدون قسم"
        ),
    }

# ========== Routes ==========
@app.route("/")
def index():
    settings = load_settings()
    items = load_menu()
    # Group by category
    categories = {}
    for item in items:
        cat = item["Category"] or "أخرى"
        categories.setdefault(cat, []).append(build_item_view(item))

    # Sort categories and items alphabetically
    sorted_categories = sorted(categories.items(), key=lambda x: x[0])
    for cat, cat_items in sorted_categories:
        cat_items.sort(key=lambda x: x["Item Name"])

    # Stats
    total_items = len(items)
    unique_cats = len(categories)

    return render_template_string(
        MAIN_TEMPLATE,
        title=settings["site_title"],
        subtitle=settings["site_subtitle"],
        logo_path=settings["logo_path"],
        categories=sorted_categories,
        total_items=total_items,
        unique_cats=unique_cats,
        is_admin=is_admin(),
    )

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("تم تسجيل الدخول بنجاح", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("كلمة المرور غير صحيحة", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("تم تسجيل الخروج", "info")
    return redirect(url_for("index"))

@app.route("/admin")
def admin_dashboard():
    resp = require_admin()
    if resp:
        return resp
    items = load_menu()
    settings = load_settings()
    return render_template_string(
        DASHBOARD_TEMPLATE,
        items=items,
        settings=settings,
    )

@app.route("/admin/import_csv", methods=["POST"])
def admin_import_csv():
    resp = require_admin()
    if resp:
        return resp

    source = request.form.get("source", "file")
    try:
        if source == "file":
            file = request.files.get("csv_file")
            if not file or not file.filename:
                flash("الرجاء اختيار ملف CSV", "error")
                return redirect(url_for("admin_dashboard"))
            text = file.read().decode("utf-8-sig", errors="replace")
        elif source == "url":
            url = request.form.get("url", "").strip()
            if not url:
                flash("الرجاء إدخال رابط", "error")
                return redirect(url_for("admin_dashboard"))
            if "docs.google.com" in url:
                url = sheets_to_csv_url(url)
            text = download_text(url)
        elif source == "text":
            text = request.form.get("csv_text", "")
            if not text:
                flash("الرجاء إدخال نص CSV", "error")
                return redirect(url_for("admin_dashboard"))
        else:
            flash("مصدر غير صالح", "error")
            return redirect(url_for("admin_dashboard"))

        new_items = parse_csv_text(text)
        if not new_items:
            flash("لم يتم العثور على أصناف صالحة في الملف", "error")
            return redirect(url_for("admin_dashboard"))

        # Replace entire menu
        save_menu(new_items)
        flash(f"تم استيراد {len(new_items)} صنفاً بنجاح", "success")
    except Exception as e:
        flash(f"خطأ أثناء الاستيراد: {str(e)}", "error")

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/add_item", methods=["POST"])
def admin_add_item():
    resp = require_admin()
    if resp:
        return resp

    item = clean_item({
        "Category": request.form.get("category", ""),
        "Item Name": request.form.get("name", ""),
        "Description": request.form.get("description", ""),
        "Price": request.form.get("price", ""),
    })
    if not item["Item Name"]:
        flash("اسم الصنف مطلوب", "error")
        return redirect(url_for("admin_dashboard"))

    items = load_menu()
    items.append(item)
    save_menu(items)
    flash(f"تمت إضافة '{item['Item Name']}'", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit_item/<path:item_name>", methods=["POST"])
def admin_edit_item(item_name):
    resp = require_admin()
    if resp:
        return resp

    items = load_menu()
    found = None
    for it in items:
        if it["Item Name"] == item_name:
            found = it
            break
    if not found:
        flash("الصنف غير موجود", "error")
        return redirect(url_for("admin_dashboard"))

    found["Category"] = request.form.get("category", "").strip()
    found["Item Name"] = request.form.get("name", "").strip()
    found["Description"] = request.form.get("description", "").strip()
    found["Price"] = request.form.get("price", "").strip()
    if not found["Item Name"]:
        flash("اسم الصنف لا يمكن أن يكون فارغاً", "error")
        return redirect(url_for("admin_dashboard"))

    save_menu(items)
    flash(f"تم تعديل '{item_name}' بنجاح", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_item/<path:item_name>")
def admin_delete_item(item_name):
    resp = require_admin()
    if resp:
        return resp

    items = load_menu()
    new_items = [it for it in items if it["Item Name"] != item_name]
    if len(new_items) == len(items):
        flash("الصنف غير موجود", "error")
    else:
        save_menu(new_items)
        flash(f"تم حذف '{item_name}'", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/generate_all_images")
def admin_generate_all_images():
    resp = require_admin()
    if resp:
        return resp

    items = load_menu()
    client = get_openai_client()
    if client is None:
        flash("OpenAI API key غير مضبوط أو مكتبة OpenAI غير مثبتة", "error")
        return redirect(url_for("admin_dashboard"))

    generated = 0
    for item in items:
        if not ai_generated_image_url(item["Item Name"]):
            url = generate_item_image(item["Item Name"], item["Category"] or "طعام")
            if url:
                generated += 1
    flash(f"تم إنشاء {generated} صورة جديدة", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/upload_image/<path:item_name>", methods=["POST"])
def admin_upload_image(item_name):
    resp = require_admin()
    if resp:
        return resp

    file = request.files.get("image")
    if not file or not file.filename:
        flash("الرجاء اختيار صورة", "error")
        return redirect(url_for("admin_dashboard"))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        flash("امتداد الصورة غير مدعوم (png, jpg, jpeg, gif, webp)", "error")
        return redirect(url_for("admin_dashboard"))

    filename = upload_filename_for_item(item_name, file.filename)
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)
    flash(f"تم رفع الصورة للصنف '{item_name}'", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/settings", methods=["POST"])
def admin_settings():
    resp = require_admin()
    if resp:
        return resp

    new_settings = {
        "site_title": request.form.get("site_title", "").strip(),
        "site_subtitle": request.form.get("site_subtitle", "").strip(),
    }
    if not new_settings["site_title"]:
        new_settings["site_title"] = "قائمة المطعم"

    # Handle logo upload
    logo_file = request.files.get("logo")
    if logo_file and logo_file.filename:
        logo_name = "logo" + os.path.splitext(logo_file.filename)[1].lower()
        logo_path = os.path.join(UPLOAD_DIR, logo_name)
        logo_file.save(logo_path)
        new_settings["logo_path"] = f"/uploads/{logo_name}"
    else:
        # Keep existing logo path
        current = load_settings()
        new_settings["logo_path"] = current.get("logo_path", "")

    save_settings(new_settings)
    flash("تم حفظ الإعدادات", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/export_csv")
def admin_export_csv():
    resp = require_admin()
    if resp:
        return resp

    items = load_menu()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPECTED_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(clean_item(item))
    response = app.response_class(
        response=output.getvalue(),
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=menu.csv"},
    )
    return response

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ========== HTML Templates ==========
MAIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
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
      --shadow: 0 10px 30px rgba(0,0,0,.24);
      --radius: 20px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, 'Segoe UI', Tahoma, Arial, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(234,179,8,.09), transparent 22%),
        radial-gradient(circle at left bottom, rgba(245,158,11,.06), transparent 20%),
        var(--bg);
      color: var(--text);
      direction: rtl;
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
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: black; font-weight: 900; overflow: hidden;
    }
    .brand-badge img { width: 100%; height: 100%; object-fit: cover; border-radius: 14px; }
    .nav { display: flex; flex-wrap: wrap; gap: 10px; }
    .nav a {
      padding: 10px 14px; border-radius: 999px; background: #17171a;
      border: 1px solid var(--line); color: #e4e4e7; font-size: 14px;
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
    .input, .select, .btn, .file, textarea {
      width: 100%; border-radius: 16px; border: 1px solid var(--line);
      background: #101014; color: var(--text); padding: 13px 14px; font-size: 15px; outline: none;
    }
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
    .chip.active {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #111; border-color: transparent; font-weight: 800;
    }
    .section-title {
      margin: 34px 0 16px; font-size: 28px; font-weight: 700; border-right: 4px solid var(--accent);
      padding-right: 14px;
    }
    .menu-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px;
    }
    .item-card {
      background: var(--panel); border-radius: 28px; border: 1px solid rgba(255,255,255,.05);
      overflow: hidden; transition: transform 0.2s, box-shadow 0.2s;
    }
    .item-card:hover { transform: translateY(-4px); box-shadow: 0 20px 35px -10px black; }
    .item-img {
      width: 100%; height: 210px; object-fit: cover; background: #1f1f22;
    }
    .item-info { padding: 18px; }
    .item-name { font-size: 1.4rem; font-weight: 800; margin: 0 0 6px; }
    .item-desc { font-size: 0.9rem; color: var(--muted); margin-bottom: 12px; line-height: 1.5; }
    .item-price { font-weight: 800; font-size: 1.3rem; color: var(--accent); }
    .empty-msg { text-align: center; color: var(--muted); padding: 50px; }
    footer { text-align: center; margin-top: 48px; padding: 24px; color: var(--muted); border-top: 1px solid var(--line); }
    @media (max-width: 680px) {
      .hero { grid-template-columns: 1fr; }
      .row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge">
        {% if logo_path %}
        <img src="{{ logo_path }}" alt="logo">
        {% else %}
        🍽️
        {% endif %}
      </div>
      <span class="headline" style="font-size:1.5rem; margin:0;">{{ title }}</span>
    </div>
    <div class="nav">
      <a href="/">الرئيسية</a>
      {% if is_admin %}
      <a href="{{ url_for('admin_dashboard') }}">لوحة التحكم</a>
      <a href="{{ url_for('admin_logout') }}">خروج</a>
      {% else %}
      <a href="{{ url_for('admin_login') }}">دخول المشرف</a>
      {% endif %}
    </div>
  </div>
  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="hero">
      <div class="card">
        <h1 class="headline">{{ title }}</h1>
        <p class="sub">{{ subtitle }}</p>
        <div class="stats">
          <div class="stat"><div class="num">{{ total_items }}</div><div class="lbl">أصناف</div></div>
          <div class="stat"><div class="num">{{ unique_cats }}</div><div class="lbl">أقسام</div></div>
          <div class="stat"><div class="num">✨</div><div class="lbl">جودة عالية</div></div>
        </div>
      </div>
      <div class="card search-card">
        <div class="field-label">🔍 ابحث في القائمة</div>
        <input type="text" id="searchInput" class="input" placeholder="اسم الصنف، الوصف..." onkeyup="filterItems()">
      </div>
    </div>

    <div class="category-chips" id="categoryChips">
      <div class="chip active" data-cat="all">الكل</div>
      {% for cat, _ in categories %}
      <div class="chip" data-cat="{{ cat }}">{{ cat }}</div>
      {% endfor %}
    </div>

    {% for cat, items in categories %}
    <div class="category-section" data-category="{{ cat }}">
      <h2 class="section-title">{{ cat }}</h2>
      <div class="menu-grid">
        {% for item in items %}
        <div class="item-card" data-name="{{ item['Item Name']|lower }}" data-desc="{{ item['Description']|lower }}">
          <img class="item-img" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}" loading="lazy">
          <div class="item-info">
            <div class="item-name">{{ item['Item Name'] }}</div>
            <div class="item-desc">{{ item['Description'] or 'لا يوجد وصف' }}</div>
            <div class="item-price">{{ item['Price'] or '—' }}</div>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
    {% else %}
    <div class="empty-msg">لا توجد أصناف مضافة بعد. قم بتسجيل الدخول لإضافة قائمة.</div>
    {% endfor %}
  </div>
  <footer>
    {{ title }} — قائمة رقمية ذكية
  </footer>
  <script>
    function filterItems() {
      const searchTerm = document.getElementById('searchInput').value.toLowerCase();
      const sections = document.querySelectorAll('.category-section');
      sections.forEach(section => {
        let hasVisible = false;
        const cards = section.querySelectorAll('.item-card');
        cards.forEach(card => {
          const name = card.getAttribute('data-name') || '';
          const desc = card.getAttribute('data-desc') || '';
          const matches = name.includes(searchTerm) || desc.includes(searchTerm);
          card.style.display = matches ? '' : 'none';
          if (matches) hasVisible = true;
        });
        section.style.display = hasVisible ? '' : 'none';
      });
    }

    // Category filter
    const chips = document.querySelectorAll('.chip');
    const sections = document.querySelectorAll('.category-section');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        const selected = chip.getAttribute('data-cat');
        if (selected === 'all') {
          sections.forEach(s => s.style.display = '');
        } else {
          sections.forEach(s => {
            if (s.getAttribute('data-category') === selected) {
              s.style.display = '';
            } else {
              s.style.display = 'none';
            }
          });
        }
      });
    });
  </script>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>دخول المشرف</title>
  <style>
    body {
      background: #09090b;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; font-family: system-ui; margin: 0;
    }
    .login-card {
      background: #111113; border: 1px solid #27272a; border-radius: 32px;
      padding: 32px; width: 100%; max-width: 380px;
    }
    .input { width: 100%; padding: 12px; border-radius: 16px; border: 1px solid #27272a; background: #18181b; color: white; margin-bottom: 16px; }
    .btn { width: 100%; padding: 12px; border-radius: 999px; background: #eab308; color: black; font-weight: bold; border: none; cursor: pointer; }
    .flash { background: rgba(234,179,8,.12); color: #fcd34d; border-radius: 14px; padding: 10px; margin-bottom: 16px; text-align: center; }
  </style>
</head>
<body>
  <div class="login-card">
    <h2 style="margin-top:0">دخول المشرف</h2>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    <form method="post">
      <input type="password" name="password" class="input" placeholder="كلمة المرور" autofocus>
      <button type="submit" class="btn">تسجيل الدخول</button>
    </form>
  </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>لوحة التحكم</title>
  <style>
    * { box-sizing: border-box; }
    body {
      background: #09090b; color: #fafafa; font-family: system-ui; margin: 0; padding: 20px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    .card {
      background: #111113; border: 1px solid #27272a; border-radius: 24px;
      padding: 24px; margin-bottom: 24px;
    }
    h2 { margin-top: 0; }
    .form-group { margin-bottom: 16px; }
    .input, .select, textarea, .file-input {
      width: 100%; padding: 12px; border-radius: 16px; border: 1px solid #27272a;
      background: #18181b; color: white;
    }
    .btn {
      background: #eab308; color: black; padding: 10px 18px; border-radius: 999px;
      border: none; font-weight: bold; cursor: pointer; display: inline-block; margin-top: 8px;
    }
    .btn-danger { background: #dc2626; color: white; }
    .btn-secondary { background: #3f3f46; color: white; }
    .table-responsive { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: right; padding: 12px 8px; border-bottom: 1px solid #27272a; }
    th { color: #a1a1aa; }
    .flash { background: rgba(234,179,8,.12); color: #fcd34d; padding: 12px; border-radius: 14px; margin-bottom: 16px; }
    .nav { display: flex; gap: 16px; margin-bottom: 20px; }
    .nav a { color: #eab308; text-decoration: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="nav">
      <a href="/">العودة للقائمة</a>
      <a href="{{ url_for('admin_logout') }}">تسجيل الخروج</a>
      <a href="{{ url_for('admin_export_csv') }}">تصدير CSV</a>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="card">
      <h2>استيراد CSV</h2>
      <form method="post" action="{{ url_for('admin_import_csv') }}" enctype="multipart/form-data">
        <div class="form-group">
          <select name="source" class="select" onchange="toggleSource(this.value)">
            <option value="file">رفع ملف CSV</option>
            <option value="url">رابط CSV أو Google Sheets</option>
            <option value="text">لصق نص CSV</option>
          </select>
        </div>
        <div id="fileSource">
          <input type="file" name="csv_file" accept=".csv" class="file-input">
        </div>
        <div id="urlSource" style="display:none">
          <input type="text" name="url" class="input" placeholder="https://...">
        </div>
        <div id="textSource" style="display:none">
          <textarea name="csv_text" rows="5" class="input" placeholder="العمود الأول: Category,Item Name,Description,Price..."></textarea>
        </div>
        <button type="submit" class="btn">استيراد واستبدال القائمة</button>
      </form>
    </div>

    <div class="card">
      <h2>إضافة صنف جديد</h2>
      <form method="post" action="{{ url_for('admin_add_item') }}">
        <div class="form-group"><input type="text" name="name" class="input" placeholder="اسم الصنف *" required></div>
        <div class="form-group"><input type="text" name="category" class="input" placeholder="القسم (مثل: مقبلات)"></div>
        <div class="form-group"><textarea name="description" class="input" placeholder="وصف"></textarea></div>
        <div class="form-group"><input type="text" name="price" class="input" placeholder="السعر"></div>
        <button type="submit" class="btn">إضافة</button>
      </form>
    </div>

    <div class="card">
      <h2>إعدادات الموقع</h2>
      <form method="post" action="{{ url_for('admin_settings') }}" enctype="multipart/form-data">
        <div class="form-group"><input type="text" name="site_title" class="input" placeholder="عنوان الموقع" value="{{ settings.site_title }}"></div>
        <div class="form-group"><input type="text" name="site_subtitle" class="input" placeholder="النص الفرعي" value="{{ settings.site_subtitle }}"></div>
        <div class="form-group">
          <label>شعار الموقع</label>
          <input type="file" name="logo" accept="image/*" class="file-input">
          {% if settings.logo_path %}<div class="flash" style="margin-top:8px">الشعار الحالي: {{ settings.logo_path }}</div>{% endif %}
        </div>
        <button type="submit" class="btn">حفظ الإعدادات</button>
      </form>
    </div>

    <div class="card">
      <h2>إدارة الأصناف</h2>
      <div class="table-responsive">
        <table>
          <thead><tr><th>الصنف</th><th>القسم</th><th>السعر</th><th>صورة</th><th>إجراءات</th></tr></thead>
          <tbody>
            {% for item in items %}
            <tr>
              <form method="post" action="{{ url_for('admin_edit_item', item_name=item['Item Name']) }}">
                <td><input type="text" name="name" value="{{ item['Item Name'] }}" class="input" style="min-width:140px"></td>
                <td><input type="text" name="category" value="{{ item['Category'] }}" class="input"></td>
                <td><input type="text" name="price" value="{{ item['Price'] }}" class="input"></td>
                <td>
                  <input type="file" name="image" form="upload-{{ loop.index }}" style="display:none" id="file-{{ loop.index }}">
                  <button type="button" class="btn-secondary" onclick="document.getElementById('file-{{ loop.index }}').click()">رفع</button>
                  <form id="upload-{{ loop.index }}" method="post" action="{{ url_for('admin_upload_image', item_name=item['Item Name']) }}" enctype="multipart/form-data"></form>
                </td>
                <td style="display:flex; gap:6px">
                  <button type="submit" class="btn-secondary">تعديل</button>
                  <a href="{{ url_for('admin_delete_item', item_name=item['Item Name']) }}" class="btn-danger" style="background:#dc2626; padding:6px 12px; border-radius:20px; color:white">حذف</a>
                </td>
              </form>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <div style="margin-top:20px">
        <a href="{{ url_for('admin_generate_all_images') }}" class="btn">توليد جميع الصور (AI)</a>
      </div>
    </div>
  </div>

  <script>
    function toggleSource(val) {
      document.getElementById('fileSource').style.display = val === 'file' ? 'block' : 'none';
      document.getElementById('urlSource').style.display = val === 'url' ? 'block' : 'none';
      document.getElementById('textSource').style.display = val === 'text' ? 'block' : 'none';
    }
    toggleSource('file');
  </script>
</body>
</html>
"""

# ========== Run ==========
if __name__ == "__main__":
    app.run(host=host, port=port, debug=False)
