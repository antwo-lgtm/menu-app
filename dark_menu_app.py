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


TRANSLATIONS = {
    "en": {
        "menu": "Menu",
        "admin": "Admin",
        "public_menu": "Public Menu",
        "dashboard": "Dashboard",
        "import": "Import",
        "settings": "Settings",
        "items": "Items",
        "images": "Images",
        "logout": "Logout",
        "search": "Search",
        "section": "Section",
        "all_sections": "All Sections",
        "all": "All",
        "items_count": "items",
        "no_items": "No matching items found.",
        "login_title": "Admin Login",
        "login_sub": "Enter your admin password.",
        "password": "Password",
        "login": "Login",
        "wrong_password": "Wrong password.",
        "logged_in": "Logged in.",
        "logged_out": "Logged out.",
        "admin_dashboard": "Admin Dashboard",
        "admin_dashboard_sub": "Manage imports, settings, item images, and AI generation from here.",
        "uploaded_images": "Uploaded images",
        "ai_images": "AI images",
        "import_menu": "Import Menu",
        "required_columns": "Required columns: Category, Item Name, Description, Price",
        "from_csv": "From CSV",
        "csv_file": "CSV file",
        "import_csv": "Import CSV",
        "from_google_sheets": "From Google Sheets",
        "google_sheets_url": "Google Sheets URL",
        "paste_google_sheet": "Paste Google Sheets URL",
        "import_google_sheet": "Import Google Sheet",
        "choose_csv": "Choose a CSV file.",
        "paste_sheet_url": "Paste a Google Sheets URL.",
        "invalid_import_mode": "Invalid import mode.",
        "csv_imported": "CSV imported",
        "sheet_imported": "Google Sheet imported",
        "import_failed": "Import failed",
        "site_settings": "Site Settings",
        "main_title": "Main title",
        "subtitle": "Subtitle",
        "logo": "Logo",
        "save_settings": "Save Settings",
        "settings_updated": "Settings updated.",
        "item_images": "Item Images",
        "item_images_sub": "Upload a manual picture for any item. Manual upload overrides AI image.",
        "image": "Image",
        "item": "Item",
        "price": "Price",
        "upload": "Upload",
        "missing_item_or_image": "Missing item or image.",
        "image_uploaded_for": "Image uploaded for",
        "ai_images_title": "AI Images",
        "ai_images_sub": "This page is optional. Manual item upload works even if AI generation fails.",
        "how_many_images": "How many images",
        "options": "Options",
        "only_missing": "Only for items without image",
        "generate": "Generate",
        "preview": "Preview",
        "openai_key_missing": "OPENAI_API_KEY not found. Manual uploads will still work.",
        "images_generated": "Images generated",
        "skipped": "Skipped",
        "default_password_hint": "Default password is 1234 unless you change MENU_ADMIN_PASSWORD.",
        "uncategorized": "Uncategorized",
        "iqd": "IQD",
    },
    "ar": {
        "menu": "المنيو",
        "admin": "الإدارة",
        "public_menu": "المنيو العام",
        "dashboard": "لوحة التحكم",
        "import": "استيراد",
        "settings": "الإعدادات",
        "items": "الأصناف",
        "images": "الصور",
        "logout": "تسجيل الخروج",
        "search": "بحث",
        "section": "القسم",
        "all_sections": "كل الأقسام",
        "all": "الكل",
        "items_count": "صنف",
        "no_items": "لا توجد أصناف مطابقة.",
        "login_title": "تسجيل دخول الإدارة",
        "login_sub": "أدخل كلمة مرور الإدارة.",
        "password": "كلمة المرور",
        "login": "دخول",
        "wrong_password": "كلمة المرور غير صحيحة.",
        "logged_in": "تم تسجيل الدخول.",
        "logged_out": "تم تسجيل الخروج.",
        "admin_dashboard": "لوحة التحكم",
        "admin_dashboard_sub": "إدارة الاستيراد والإعدادات وصور الأصناف وتوليد الصور.",
        "uploaded_images": "صور مرفوعة",
        "ai_images": "صور ذكاء اصطناعي",
        "import_menu": "استيراد المنيو",
        "required_columns": "الأعمدة المطلوبة: Category, Item Name, Description, Price",
        "from_csv": "من CSV",
        "csv_file": "ملف CSV",
        "import_csv": "استيراد CSV",
        "from_google_sheets": "من Google Sheets",
        "google_sheets_url": "رابط Google Sheets",
        "paste_google_sheet": "ألصق رابط Google Sheets",
        "import_google_sheet": "استيراد Google Sheet",
        "choose_csv": "اختر ملف CSV.",
        "paste_sheet_url": "ألصق رابط Google Sheets.",
        "invalid_import_mode": "وضع استيراد غير صحيح.",
        "csv_imported": "تم استيراد CSV",
        "sheet_imported": "تم استيراد Google Sheet",
        "import_failed": "فشل الاستيراد",
        "site_settings": "إعدادات الموقع",
        "main_title": "العنوان الرئيسي",
        "subtitle": "العنوان الفرعي",
        "logo": "الشعار",
        "save_settings": "حفظ الإعدادات",
        "settings_updated": "تم تحديث الإعدادات.",
        "item_images": "صور الأصناف",
        "item_images_sub": "ارفع صورة يدوية لأي صنف. الصورة اليدوية تتجاوز صورة الذكاء الاصطناعي.",
        "image": "الصورة",
        "item": "الصنف",
        "price": "السعر",
        "upload": "رفع",
        "missing_item_or_image": "الصنف أو الصورة مفقود.",
        "image_uploaded_for": "تم رفع صورة لـ",
        "ai_images_title": "صور الذكاء الاصطناعي",
        "ai_images_sub": "هذه الصفحة اختيارية. رفع الصور اليدوي يعمل حتى لو فشل التوليد.",
        "how_many_images": "عدد الصور",
        "options": "خيارات",
        "only_missing": "فقط للأصناف بدون صورة",
        "generate": "توليد",
        "preview": "معاينة",
        "openai_key_missing": "لم يتم العثور على OPENAI_API_KEY. رفع الصور اليدوي سيظل يعمل.",
        "images_generated": "تم توليد الصور",
        "skipped": "تم التخطي",
        "default_password_hint": "كلمة المرور الافتراضية هي 1234 إلا إذا غيرت MENU_ADMIN_PASSWORD.",
        "uncategorized": "بدون قسم",
        "iqd": "د.ع",
    },
}


def get_lang():
    lang = request.args.get("lang", "").strip().lower()
    if lang in ("en", "ar"):
        session["lang"] = lang
        return lang
    return session.get("lang", "ar")


def t(key):
    lang = get_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS["ar"]).get(key, key)


def lang_url(endpoint, **kwargs):
    kwargs["lang"] = get_lang()
    return url_for(endpoint, **kwargs)


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
        return redirect(lang_url("admin_login"))
    return None


def build_item_view(item):
    return {
        **item,
        "ImageURL": best_image_url(item["Item Name"], item["Category"] or t("uncategorized")),
    }


BASE_HTML = r'''
<!doctype html>
<html lang="{{ lang }}" dir="{% if lang == 'ar' %}rtl{% else %}ltr{% endif %}">
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
      flex-wrap: wrap;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-badge {
      width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: black; font-weight: 900;
      overflow: hidden;
      flex-shrink: 0;
    }
    .brand-badge img { width: 100%; height: 100%; object-fit: cover; }
    .nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .nav a {
      padding: 10px 14px; border-radius: 999px; background: #17171a;
      border: 1px solid var(--line); color: #e4e4e7;
    }
    .nav a.lang-active {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #111;
      border-color: transparent;
      font-weight: 800;
    }
    .container { max-width: 1320px; margin: 0 auto; padding: 24px 16px 40px; }
    .hero { display: grid; grid-template-columns: 1fr; gap: 18px; margin-bottom: 22px; }
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
    .row { display: grid; grid-template-columns: 1.2fr .8fr; gap: 12px; align-items: end; }
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
    th, td { padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: start; vertical-align: top; }
    th { color: var(--muted); font-size: 13px; }
    .thumb { width: 56px; height: 56px; border-radius: 12px; object-fit: cover; background: #111; }
    .tiny { color: var(--muted); font-size: 12px; line-height: 1.7; }

    @media (max-width: 980px) {
      .row, .row2 { grid-template-columns: 1fr; }
      .stats { grid-template-columns: 1fr; }
    }
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
        {% if not public_nav %}
          <div style="font-size:12px;color:var(--muted)">{{ settings.site_subtitle }}</div>
        {% endif %}
      </div>
    </div>

    <div class="nav">
      <a href="{{ url_for(request.endpoint, **request.view_args, lang='ar', **request.args.to_dict(flat=True)) if request.endpoint else url_for('index', lang='ar') }}" class="{% if lang == 'ar' %}lang-active{% endif %}">العربية</a>
      <a href="{{ url_for(request.endpoint, **request.view_args, lang='en', **request.args.to_dict(flat=True)) if request.endpoint else url_for('index', lang='en') }}" class="{% if lang == 'en' %}lang-active{% endif %}">English</a>

      {% if not public_nav %}
        <a href="{{ lang_url('index') }}">{{ tr('public_menu') }}</a>
        <a href="{{ lang_url('admin_dashboard') }}">{{ tr('dashboard') }}</a>
        <a href="{{ lang_url('admin_import') }}">{{ tr('import') }}</a>
        <a href="{{ lang_url('admin_settings') }}">{{ tr('settings') }}</a>
        <a href="{{ lang_url('admin_items') }}">{{ tr('items') }}</a>
        <a href="{{ lang_url('generate_images_page') }}">{{ tr('images') }}</a>
        <a href="{{ lang_url('admin_logout') }}">{{ tr('logout') }}</a>
      {% else %}
        <a href="{{ lang_url('admin_login') }}">{{ tr('admin') }}</a>
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
  </div>
</body>
</html>
'''


def render_page(title, content, public_nav=True):
    return render_template_string(
        BASE_HTML,
        title=title,
        content=content,
        settings=load_settings(),
        public_nav=public_nav,
        lang=get_lang(),
        tr=t,
        lang_url=lang_url,
        request=request,
    )


@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/")
def index():
    lang = get_lang()
    uncategorized = t("uncategorized")

    items = load_menu()
    q = request.args.get("q", "").strip().lower()
    selected_category = request.args.get("category", "").strip()

    categories = []
    seen = set()
    for item in items:
        cat = item["Category"] or uncategorized
        if cat not in seen:
            seen.add(cat)
            categories.append(cat)

    filtered = []
    for item in items:
        blob = " ".join([
            item.get("Category", ""),
            item.get("Item Name", ""),
            item.get("Description", ""),
            item.get("Price", "")
        ]).lower()

        if q and q not in blob:
            continue

        actual_cat = item.get("Category") or uncategorized
        if selected_category and actual_cat != selected_category:
            continue

        filtered.append(item)

    grouped = OrderedDict()
    for item in filtered:
        cat = item["Category"] or uncategorized
        grouped.setdefault(cat, []).append(build_item_view(item))
    grouped = OrderedDict((cat, rows) for cat, rows in grouped.items() if rows)

    content = render_template_string('''
    <div class="hero">
      <div class="card search-card">
        <form method="get" id="menuFilterForm">
          <input type="hidden" name="lang" value="{{ lang }}">
          <div class="row">
            <div>
              <div class="field-label">{{ tr('search') }}</div>
              <input class="input" type="text" name="q" value="{{ q }}" placeholder="{{ tr('search') }}..." onkeydown="if(event.key==='Enter'){this.form.submit();}">
            </div>
            <div>
              <div class="field-label">{{ tr('section') }}</div>
              <select class="select" name="category" onchange="this.form.submit()">
                <option value="">{{ tr('all_sections') }}</option>
                {% for cat in categories %}
                  <option value="{{ cat }}" {% if cat == selected_category %}selected{% endif %}>{{ cat }}</option>
                {% endfor %}
              </select>
            </div>
          </div>
        </form>
      </div>
    </div>

    <div class="category-chips">
      <a class="chip {% if not selected_category %}active{% endif %}" href="{{ url_for('index', q=q, lang=lang) }}">{{ tr('all') }}</a>
      {% for cat in categories %}
        <a class="chip {% if cat == selected_category %}active{% endif %}" href="{{ url_for('index', q=q, category=cat, lang=lang) }}">{{ cat }}</a>
      {% endfor %}
    </div>

    {% if grouped %}
      {% for cat, rows in grouped.items() %}
        <div class="section-title">
          <h2>{{ cat }}</h2>
          <div class="count">{{ rows|length }} {{ tr('items_count') }}</div>
        </div>
        <div class="menu-grid">
          {% for item in rows %}
            <article class="menu-item">
              <img class="menu-image" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}">
              <div class="menu-body">
                <div class="menu-top">
                  <h3 class="menu-name">{{ item['Item Name'] }}</h3>
                  {% if item['Price'] %}
                    <div class="price">{{ item['Price'] }} {{ tr('iqd') }}</div>
                  {% endif %}
                </div>
                <p class="menu-desc">{{ item['Description'] or '' }}</p>
                <span class="menu-cat">{{ item['Category'] or tr('uncategorized') }}</span>
              </div>
            </article>
          {% endfor %}
        </div>
      {% endfor %}
    {% else %}
      <div class="card">{{ tr('no_items') }}</div>
    {% endif %}
    ''',
    q=q,
    selected_category=selected_category,
    categories=categories,
    grouped=grouped,
    lang=lang,
    tr=t)

    return render_page(t("menu"), content, public_nav=True)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    get_lang()

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash(t("logged_in"))
            return redirect(lang_url("admin_dashboard"))
        flash(t("wrong_password"))

    content = render_template_string('''
    <div class="card" style="max-width:500px;margin:60px auto;">
      <h1 style="margin-top:0">{{ tr('login_title') }}</h1>
      <p class="sub">{{ tr('login_sub') }}</p>
      <form method="post">
        <div class="field-label">{{ tr('password') }}</div>
        <input class="input" type="password" name="password" placeholder="{{ tr('password') }}">
        <button class="btn" type="submit">{{ tr('login') }}</button>
      </form>
      <p class="tiny">{{ tr('default_password_hint') }}</p>
    </div>
    ''', tr=t)

    return render_page(t("login_title"), content, public_nav=True)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash(t("logged_out"))
    return redirect(lang_url("index"))


@app.route("/admin")
def admin_dashboard():
    get_lang()
    guard = require_admin()
    if guard:
        return guard

    items = load_menu()
    content = render_template_string('''
    <div class="hero">
      <div class="card">
        <h1 class="headline">{{ tr('admin_dashboard') }}</h1>
        <p class="sub">{{ tr('admin_dashboard_sub') }}</p>
      </div>
      <div class="card">
        <div class="stats">
          <div class="stat"><div class="num">{{ items|length }}</div><div class="lbl">{{ tr('items') }}</div></div>
          <div class="stat"><div class="num">{{ with_uploads }}</div><div class="lbl">{{ tr('uploaded_images') }}</div></div>
          <div class="stat"><div class="num">{{ with_ai }}</div><div class="lbl">{{ tr('ai_images') }}</div></div>
        </div>
      </div>
    </div>

    <div class="row2">
      <a class="card" href="{{ lang_url('admin_import') }}"><h2 style="margin-top:0">{{ tr('import') }}</h2><p class="sub">{{ tr('import_menu') }}</p></a>
      <a class="card" href="{{ lang_url('admin_settings') }}"><h2 style="margin-top:0">{{ tr('settings') }}</h2><p class="sub">{{ tr('site_settings') }}</p></a>
      <a class="card" href="{{ lang_url('admin_items') }}"><h2 style="margin-top:0">{{ tr('item_images') }}</h2><p class="sub">{{ tr('item_images_sub') }}</p></a>
      <a class="card" href="{{ lang_url('generate_images_page') }}"><h2 style="margin-top:0">{{ tr('images') }}</h2><p class="sub">{{ tr('ai_images_sub') }}</p></a>
    </div>
    ''',
    items=items,
    with_uploads=sum(1 for item in items if user_uploaded_image_url(item["Item Name"])),
    with_ai=sum(1 for item in items if ai_generated_image_url(item["Item Name"])),
    tr=t,
    lang_url=lang_url)

    return render_page(t("admin_dashboard"), content, public_nav=False)


@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    get_lang()
    guard = require_admin()
    if guard:
        return guard

    if request.method == "POST":
        mode = request.form.get("mode")
        try:
            if mode == "csv":
                uploaded = request.files.get("csv_file")
                if not uploaded or not uploaded.filename:
                    raise ValueError(t("choose_csv"))
                text = uploaded.read().decode("utf-8-sig", errors="replace")
                items = parse_csv_text(text)
                save_menu(items)
                flash(f"{t('csv_imported')}: {len(items)}")

            elif mode == "sheet":
                sheet_url = request.form.get("sheet_url", "").strip()
                if not sheet_url:
                    raise ValueError(t("paste_sheet_url"))
                text = download_text(sheets_to_csv_url(sheet_url))
                items = parse_csv_text(text)
                save_menu(items)
                flash(f"{t('sheet_imported')}: {len(items)}")

            else:
                raise ValueError(t("invalid_import_mode"))

            return redirect(lang_url("admin_dashboard"))

        except Exception as e:
            flash(f"{t('import_failed')}: {e}")
            return redirect(lang_url("admin_import"))

    content = render_template_string('''
    <div class="card"><h1 style="margin-top:0">{{ tr('import_menu') }}</h1><p class="sub">{{ tr('required_columns') }}</p></div>

    <div class="row2">
      <div class="card">
        <h2 style="margin-top:0">{{ tr('from_csv') }}</h2>
        <form method="post" enctype="multipart/form-data">
          <input type="hidden" name="mode" value="csv">
          <div class="field-label">{{ tr('csv_file') }}</div>
          <input class="file" type="file" name="csv_file" accept=".csv">
          <button class="btn" type="submit">{{ tr('import_csv') }}</button>
        </form>
      </div>

      <div class="card">
        <h2 style="margin-top:0">{{ tr('from_google_sheets') }}</h2>
        <form method="post">
          <input type="hidden" name="mode" value="sheet">
          <div class="field-label">{{ tr('google_sheets_url') }}</div>
          <input class="input" type="url" name="sheet_url" placeholder="{{ tr('paste_google_sheet') }}">
          <button class="btn" type="submit">{{ tr('import_google_sheet') }}</button>
        </form>
      </div>
    </div>
    ''', tr=t)

    return render_page(t("import"), content, public_nav=False)


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    get_lang()
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
        flash(t("settings_updated"))
        return redirect(lang_url("admin_settings"))

    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">{{ tr('site_settings') }}</h1>
      <form method="post" enctype="multipart/form-data">
        <div class="row2">
          <div>
            <div class="field-label">{{ tr('main_title') }}</div>
            <input class="input" type="text" name="site_title" value="{{ settings.site_title }}">
          </div>
          <div>
            <div class="field-label">{{ tr('subtitle') }}</div>
            <input class="input" type="text" name="site_subtitle" value="{{ settings.site_subtitle }}">
          </div>
        </div>

        <div class="field-label" style="margin-top:10px;">{{ tr('logo') }}</div>
        <input class="file" type="file" name="logo_file" accept="image/*">

        {% if settings.logo_path %}
          <div style="margin:14px 0;">
            <img src="{{ settings.logo_path }}" alt="Logo" style="width:90px;height:90px;object-fit:cover;border-radius:16px;">
          </div>
        {% endif %}

        <button class="btn" type="submit">{{ tr('save_settings') }}</button>
      </form>
    </div>
    ''', settings=settings, tr=t)

    return render_page(t("settings"), content, public_nav=False)


@app.route("/admin/items", methods=["GET"])
def admin_items():
    get_lang()
    guard = require_admin()
    if guard:
        return guard

    items = [build_item_view(item) for item in load_menu()]
    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">{{ tr('item_images') }}</h1>
      <p class="sub">{{ tr('item_images_sub') }}</p>
    </div>

    <div class="card" style="overflow:auto;">
      <table>
        <thead>
          <tr>
            <th>{{ tr('image') }}</th>
            <th>{{ tr('item') }}</th>
            <th>{{ tr('section') }}</th>
            <th>{{ tr('price') }}</th>
            <th>{{ tr('upload') }}</th>
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
              <form method="post" action="{{ lang_url('admin_upload_item_image') }}" enctype="multipart/form-data">
                <input type="hidden" name="item_name" value="{{ item['Item Name'] }}">
                <input type="file" name="item_image" accept="image/*" required>
                <button class="btn secondary" type="submit" style="margin-top:8px;">{{ tr('upload') }}</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    ''', items=items, tr=t, lang_url=lang_url)

    return render_page(t("items"), content, public_nav=False)


@app.route("/admin/upload-item-image", methods=["POST"])
def admin_upload_item_image():
    get_lang()
    guard = require_admin()
    if guard:
        return guard

    item_name = request.form.get("item_name", "").strip()
    uploaded = request.files.get("item_image")
    if not item_name or not uploaded or not uploaded.filename:
        flash(t("missing_item_or_image"))
        return redirect(lang_url("admin_items"))

    filename = upload_filename_for_item(item_name, uploaded.filename)
    uploaded.save(os.path.join(UPLOAD_DIR, filename))
    flash(f"{t('image_uploaded_for')} {item_name}.")
    return redirect(lang_url("admin_items"))


@app.route("/admin/generate-images", methods=["GET", "POST"])
def generate_images_page():
    get_lang()
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
            flash(t("openai_key_missing"))
            return redirect(lang_url("generate_images_page"))

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

        flash(f"{t('images_generated')}: {generated}. {t('skipped')}: {skipped}.")
        return redirect(lang_url("generate_images_page"))

    preview = [build_item_view(item) for item in items[:12]]
    content = render_template_string('''
    <div class="card">
      <h1 style="margin-top:0">{{ tr('ai_images_title') }}</h1>
      <p class="sub">{{ tr('ai_images_sub') }}</p>
    </div>

    <div class="card">
      <form method="post">
        <div class="row2">
          <div>
            <div class="field-label">{{ tr('how_many_images') }}</div>
            <input class="input" type="text" name="limit" value="12">
          </div>
          <div>
            <div class="field-label">{{ tr('options') }}</div>
            <label style="display:flex;gap:8px;align-items:center;padding:14px;border-radius:16px;border:1px solid var(--line);background:#101014;">
              <input type="checkbox" name="only_missing" checked>
              <span>{{ tr('only_missing') }}</span>
            </label>
          </div>
        </div>
        <div style="margin-top:12px;">
          <button class="btn" type="submit">{{ tr('generate') }}</button>
        </div>
      </form>
    </div>

    <div class="section-title"><h2>{{ tr('preview') }}</h2><div class="count">{{ preview|length }} {{ tr('items_count') }}</div></div>

    <div class="menu-grid">
      {% for item in preview %}
      <article class="menu-item">
        <img class="menu-image" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}">
        <div class="menu-body">
          <div class="menu-top">
            <h3 class="menu-name">{{ item['Item Name'] }}</h3>
            {% if item['Price'] %}<div class="price">{{ item['Price'] }} {{ tr('iqd') }}</div>{% endif %}
          </div>
          <p class="menu-desc">{{ item['Description'] or '' }}</p>
          <span class="menu-cat">{{ item['Category'] or tr('uncategorized') }}</span>
        </div>
      </article>
      {% endfor %}
    </div>
    ''', preview=preview, tr=t)

    return render_page(t("images"), content, public_nav=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
