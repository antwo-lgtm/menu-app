
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


app = Flask(__name__)

# Railway / deployment config
port = int(os.environ.get("PORT", 8000))
host = "0.0.0.0"
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-menu-key")

DATA_FILE = os.environ.get("MENU_DATA_FILE", "menu_data.csv")
IMAGE_DIR = os.environ.get("MENU_IMAGE_DIR", "generated_images")
UPLOAD_DIR = os.environ.get("MENU_UPLOAD_DIR", "uploaded_assets")
SETTINGS_FILE = os.environ.get("MENU_SETTINGS_FILE", "menu_settings.json")
EXPECTED_COLUMNS = ["Category", "Item Name", "Description", "Price"]
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
ADMIN_PASSWORD = os.environ.get("MENU_ADMIN_PASSWORD", "1234")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------- Helpers ----------

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)


def load_settings():
    defaults = {
        "site_title_ar": "قائمة المطعم",
        "site_title_en": "Restaurant Menu",
        "site_subtitle_ar": "قائمة رقمية حديثة",
        "site_subtitle_en": "Modern digital menu",
        "logo_path": "",
        "currency_ar": "د.ع",
        "currency_en": "IQD",
        "hero_note_ar": "اختر القسم وشاهد الأصناف مباشرة",
        "hero_note_en": "Pick a section and items appear instantly",
    }
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            defaults.update({k: data.get(k, defaults[k]) for k in defaults})
    except Exception:
        pass
    return defaults


def save_settings(new_data):
    current = load_settings()
    current.update(new_data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def normalize_headers(row):
    clean = {}
    for k, v in row.items():
        key = (k or "").strip()
        clean[key] = v.strip() if isinstance(v, str) else v
    return clean


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
            if item["Item Name"]:
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
        if item["Item Name"]:
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
    try:
        for name in os.listdir(UPLOAD_DIR):
            if name.startswith(digest + "."):
                return f"/uploads/{name}"
    except FileNotFoundError:
        return None
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
    return placeholder_svg_data_uri(item_name, category or "Menu Item")


def generate_image_prompt(item_name, category):
    return (
        f"Restaurant menu photo of '{item_name}' from category '{category}'. "
        "Elegant food photography, realistic plated presentation, centered composition, "
        "premium restaurant style, studio lighting, clean background, no text, no watermark."
    )


def generate_item_image(item_name, category):
    client = get_openai_client()
    if client is None:
        return None, "OpenAI API key is missing."
    filename = image_filename_for_item(item_name)
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        return f"/images/{filename}", None

    try:
        result = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=generate_image_prompt(item_name, category),
            size="1024x1024",
        )
        first = result.data[0]
        image_b64 = getattr(first, "b64_json", None)
        image_url = getattr(first, "url", None)

        if image_b64:
            with open(path, "wb") as f:
                f.write(base64.b64decode(image_b64))
            return f"/images/{filename}", None
        if image_url:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            return f"/images/{filename}", None
        return None, "Image API returned no image."
    except Exception as e:
        print(f"[Image gen error] {e}")
        return None, str(e)


def is_admin():
    return session.get("is_admin") is True


def require_admin():
    if not is_admin():
        return redirect(url_for("admin_login"))
    return None


def build_item_view(item):
    return {
        **item,
        "ImageURL": best_image_url(item["Item Name"], item["Category"] or "Menu Item"),
    }


def grouped_items(items):
    groups = OrderedDict()
    for item in items:
        cat = item["Category"] or "Other"
        groups.setdefault(cat, [])
        groups[cat].append(build_item_view(item))
    return groups


def menu_stats(items):
    categories = sorted({(i["Category"] or "Other") for i in items})
    return {
        "item_count": len(items),
        "category_count": len(categories),
        "categories": categories,
    }


def get_lang():
    lang = request.args.get("lang", "").strip().lower()
    if lang not in {"ar", "en"}:
        lang = session.get("lang", "ar")
    session["lang"] = lang
    return lang


def tr(lang, ar, en):
    return ar if lang == "ar" else en


def page_direction(lang):
    return "rtl" if lang == "ar" else "ltr"


def text_align(lang):
    return "right" if lang == "ar" else "left"


def format_price(price, lang, settings):
    price = (price or "").strip()
    if not price:
        return ""
    currency = settings["currency_ar"] if lang == "ar" else settings["currency_en"]
    return f"{price} {currency}"


def save_uploaded_logo(file_storage):
    if not file_storage or not file_storage.filename:
        return ""
    filename = "logo_" + secure_filename_local(file_storage.filename)
    path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(path)
    return f"/uploads/{filename}"


def save_item_image(item_name, file_storage):
    if not file_storage or not file_storage.filename:
        return None
    filename = upload_filename_for_item(item_name, file_storage.filename)
    path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(path)
    return f"/uploads/{filename}"


# ---------- Templates ----------

BASE_HTML = r"""
<!doctype html>
<html lang="{{ lang }}" dir="{{ direction }}">
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
      --danger: #ef4444;
      --ok: #22c55e;
      --shadow: 0 10px 30px rgba(0,0,0,.24);
      --radius: 20px;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: Tahoma, Arial, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(234,179,8,.09), transparent 22%),
        radial-gradient(circle at left bottom, rgba(245,158,11,.06), transparent 20%),
        var(--bg);
      color: var(--text);
      direction: {{ direction }};
      text-align: {{ align }};
    }
    a { color: inherit; text-decoration: none; }
    .topbar {
      position: sticky; top: 0; z-index: 30;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 14px 20px; backdrop-filter: blur(14px);
      background: rgba(9,9,11,.78); border-bottom: 1px solid rgba(255,255,255,.06);
    }
    .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .brand-badge {
      width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: black; font-weight: 900; overflow: hidden; flex: 0 0 44px;
    }
    .brand-badge img { width: 100%; height: 100%; object-fit: cover; border-radius: 14px; }
    .brand-text { min-width: 0; }
    .brand-title { margin: 0; font-size: 18px; font-weight: 800; }
    .brand-subtitle { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
    .nav { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .nav a, .nav button {
      padding: 10px 14px; border-radius: 999px; background: #17171a;
      border: 1px solid var(--line); color: #e4e4e7; font-size: 14px; cursor: pointer;
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
    .hero-note { margin-top: 16px; color: #fde68a; font-size: 14px; }
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
    .btn.danger { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; }
    .flash {
      padding: 12px 14px; border-radius: 14px; margin-bottom: 16px;
      border: 1px solid rgba(255,255,255,.08);
      background: rgba(255,255,255,.04);
    }
    .flash.error { color: #fecaca; background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.26);}
    .flash.success { color: #bbf7d0; background: rgba(34,197,94,.12); border-color: rgba(34,197,94,.26);}
    .flash.info { color: #fde68a; background: rgba(234,179,8,.12); border-color: rgba(234,179,8,.26);}
    .category-chips {
      display: flex; gap: 10px; overflow: auto; padding-bottom: 4px; margin: 16px 0 18px;
      scroll-snap-type: x proximity;
    }
    .chip {
      white-space: nowrap; padding: 11px 15px; border-radius: 999px; background: #141418;
      border: 1px solid var(--line); color: #d4d4d8; display: inline-flex; align-items: center; gap: 8px;
      scroll-snap-align: start;
    }
    .chip.active {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #111; border-color: transparent; font-weight: 800;
    }
    .section-title {
      margin: 30px 0 16px; font-size: clamp(22px, 3vw, 30px); font-weight: 800;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }
    .section-count {
      font-size: 13px; color: var(--muted); background: rgba(255,255,255,.04);
      padding: 8px 12px; border-radius: 999px; border: 1px solid rgba(255,255,255,.06);
    }
    .grid {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px;
    }
    .item {
      overflow: hidden; padding: 0;
      display: flex; flex-direction: column;
    }
    .item-image {
      width: 100%; aspect-ratio: 4 / 3; object-fit: cover; display: block; background: #18181b;
    }
    .item-body { padding: 18px; display: flex; flex-direction: column; gap: 12px; }
    .item-top {
      display: flex; align-items: start; justify-content: space-between; gap: 12px;
    }
    .item-name { margin: 0; font-size: 20px; font-weight: 800; }
    .item-price {
      padding: 9px 12px; border-radius: 999px;
      background: rgba(234,179,8,.13); color: #fde68a; font-weight: 800; white-space: nowrap;
      border: 1px solid rgba(234,179,8,.22);
    }
    .item-desc { margin: 0; color: var(--muted); line-height: 1.8; font-size: 14px; min-height: 48px; }
    .admin-table-wrap { overflow: auto; }
    table {
      width: 100%; border-collapse: collapse; min-width: 720px;
      background: rgba(255,255,255,.02); border: 1px solid rgba(255,255,255,.06); border-radius: 16px; overflow: hidden;
    }
    th, td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,.06); vertical-align: top; }
    th { color: #fde68a; background: rgba(255,255,255,.03); }
    td.actions form { display: inline-block; margin: 0 0 8px 8px; }
    .toolbar {
      display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px;
    }
    .muted { color: var(--muted); }
    .center-empty {
      text-align: center; padding: 40px 20px; color: var(--muted);
      border: 1px dashed rgba(255,255,255,.12); border-radius: 20px; margin-top: 14px;
    }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .footer-space { height: 20px; }
    .login-box { max-width: 480px; margin: 70px auto; }
    .small { font-size: 12px; color: var(--muted); }
    @media (max-width: 980px) {
      .hero, .split, .row, .row2, .grid { grid-template-columns: 1fr; }
      .stats { grid-template-columns: 1fr 1fr 1fr; }
    }
    @media (max-width: 680px) {
      .topbar { padding: 12px; }
      .nav { gap: 8px; }
      .nav a, .nav button { padding: 9px 12px; font-size: 13px; }
      .stats { grid-template-columns: 1fr; }
      .container { padding: 18px 12px 30px; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge">
        {% if settings.logo_path %}
          <img src="{{ settings.logo_path }}" alt="logo">
        {% else %}
          <span>🍽</span>
        {% endif %}
      </div>
      <div class="brand-text">
        <h1 class="brand-title">{{ settings.site_title_ar if lang == 'ar' else settings.site_title_en }}</h1>
        <p class="brand-subtitle">{{ settings.site_subtitle_ar if lang == 'ar' else settings.site_subtitle_en }}</p>
      </div>
    </div>
    <div class="nav">
      <a href="{{ lang_switch_url }}">{{ "English" if lang == "ar" else "العربية" }}</a>
      {% if is_admin %}
        <a href="{{ url_for('admin_dashboard', lang=lang) }}">{{ "لوحة التحكم" if lang == "ar" else "Dashboard" }}</a>
        <a href="{{ url_for('admin_logout', lang=lang) }}">{{ "خروج" if lang == "ar" else "Logout" }}</a>
      {% endif %}
    </div>
  </div>

  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {{ content|safe }}
  </div>
  <div class="footer-space"></div>
</body>
</html>
"""


# ---------- Routes ----------

@app.route("/")
def public_menu():
    lang = get_lang()
    settings = load_settings()
    items = load_menu()
    stats = menu_stats(items)
    active = request.args.get("category", "").strip()
    grouped = grouped_items(items)
    if active and active not in grouped:
        active = ""

    categories = list(grouped.keys())
    shown_groups = grouped if not active else OrderedDict([(active, grouped.get(active, []))])

    content = render_template_string(
        r"""
        <div class="hero">
          <div class="card">
            <h2 class="headline">{{ settings.site_title_ar if lang == 'ar' else settings.site_title_en }}</h2>
            <p class="sub">{{ settings.site_subtitle_ar if lang == 'ar' else settings.site_subtitle_en }}</p>
            <p class="hero-note">{{ settings.hero_note_ar if lang == 'ar' else settings.hero_note_en }}</p>
            <div class="stats">
              <div class="stat">
                <div class="num">{{ stats.item_count }}</div>
                <div class="lbl">{{ "عدد الأصناف" if lang == "ar" else "Items" }}</div>
              </div>
              <div class="stat">
                <div class="num">{{ stats.category_count }}</div>
                <div class="lbl">{{ "عدد الأقسام" if lang == "ar" else "Categories" }}</div>
              </div>
              <div class="stat">
                <div class="num">{{ categories|length }}</div>
                <div class="lbl">{{ "الأقسام الظاهرة" if lang == "ar" else "Visible sections" }}</div>
              </div>
            </div>
          </div>

          <div class="card search-card">
            <form method="get" action="{{ url_for('public_menu') }}">
              <input type="hidden" name="lang" value="{{ lang }}">
              <label class="field-label">{{ "اختر القسم" if lang == "ar" else "Choose section" }}</label>
              <div class="row">
                <select name="category" class="select" onchange="this.form.submit()">
                  <option value="">{{ "كل الأقسام" if lang == "ar" else "All categories" }}</option>
                  {% for cat in categories %}
                    <option value="{{ cat }}" {% if active == cat %}selected{% endif %}>{{ cat }}</option>
                  {% endfor %}
                </select>
                <input class="input" type="search" id="menuSearch" placeholder="{{ 'ابحث عن صنف...' if lang == 'ar' else 'Search item...' }}">
                <a class="btn secondary" href="{{ url_for('public_menu', lang=lang) }}">{{ "إعادة ضبط" if lang == "ar" else "Reset" }}</a>
              </div>
            </form>
          </div>
        </div>

        {% if categories %}
          <div class="category-chips">
            <a class="chip {% if not active %}active{% endif %}" href="{{ url_for('public_menu', lang=lang) }}">
              {{ "الكل" if lang == "ar" else "All" }}
            </a>
            {% for cat in categories %}
              <a class="chip {% if active == cat %}active{% endif %}" href="{{ url_for('public_menu', category=cat, lang=lang) }}">{{ cat }}</a>
            {% endfor %}
          </div>
        {% endif %}

        {% if shown_groups %}
          {% for cat, cat_items in shown_groups.items() %}
            <section class="menu-section" data-category="{{ cat }}">
              <div class="section-title">
                <span>{{ cat }}</span>
                <span class="section-count">{{ cat_items|length }} {{ "صنف" if lang == "ar" else "items" }}</span>
              </div>
              <div class="grid">
                {% for item in cat_items %}
                  <article class="card item menu-card" data-name="{{ item['Item Name']|lower }}" data-desc="{{ item['Description']|lower }}">
                    <img class="item-image" src="{{ item['ImageURL'] }}" alt="{{ item['Item Name'] }}">
                    <div class="item-body">
                      <div class="item-top">
                        <h3 class="item-name">{{ item["Item Name"] }}</h3>
                        {% if item["Price"] %}
                          <div class="item-price">{{ format_price(item["Price"], lang, settings) }}</div>
                        {% endif %}
                      </div>
                      <p class="item-desc">{{ item["Description"] or ("لا يوجد وصف" if lang == "ar" else "No description") }}</p>
                    </div>
                  </article>
                {% endfor %}
              </div>
            </section>
          {% endfor %}
        {% else %}
          <div class="center-empty">{{ "لا توجد أصناف حالياً" if lang == "ar" else "No menu items yet" }}</div>
        {% endif %}

        <script>
          const searchInput = document.getElementById("menuSearch");
          if (searchInput) {
            searchInput.addEventListener("input", function () {
              const q = this.value.trim().toLowerCase();
              document.querySelectorAll(".menu-card").forEach(card => {
                const hay = (card.dataset.name + " " + card.dataset.desc).toLowerCase();
                card.style.display = (!q || hay.includes(q)) ? "" : "none";
              });
            });
          }
        </script>
        """,
        settings=settings,
        stats=stats,
        categories=categories,
        grouped=grouped,
        shown_groups=shown_groups,
        active=active,
        lang=lang,
        format_price=format_price,
    )

    return render_template_string(
        BASE_HTML,
        title=settings["site_title_ar"] if lang == "ar" else settings["site_title_en"],
        content=content,
        lang=lang,
        direction=page_direction(lang),
        align=text_align(lang),
        settings=settings,
        is_admin=is_admin(),
        lang_switch_url=url_for("public_menu", category=active or None, lang=("en" if lang == "ar" else "ar")),
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    lang = get_lang()
    settings = load_settings()
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("تم تسجيل الدخول بنجاح." if lang == "ar" else "Logged in successfully.", "success")
            return redirect(url_for("admin_dashboard", lang=lang))
        flash("كلمة المرور غير صحيحة." if lang == "ar" else "Wrong password.", "error")

    content = render_template_string(
        r"""
        <div class="login-box">
          <div class="card">
            <h2 class="headline" style="font-size:32px;">{{ "دخول الإدارة" if lang == "ar" else "Admin Login" }}</h2>
            <p class="sub">{{ "أدخل كلمة المرور للوصول للوحة التحكم" if lang == "ar" else "Enter the password to access the dashboard" }}</p>
            <form method="post" style="margin-top:18px;">
              <label class="field-label">{{ "كلمة المرور" if lang == "ar" else "Password" }}</label>
              <input class="input" type="password" name="password" required>
              <div style="margin-top:14px;">
                <button class="btn" type="submit">{{ "دخول" if lang == "ar" else "Login" }}</button>
              </div>
            </form>
          </div>
        </div>
        """,
        lang=lang,
    )
    return render_template_string(
        BASE_HTML,
        title=("دخول الإدارة" if lang == "ar" else "Admin Login"),
        content=content,
        lang=lang,
        direction=page_direction(lang),
        align=text_align(lang),
        settings=settings,
        is_admin=is_admin(),
        lang_switch_url=url_for("admin_login", lang=("en" if lang == "ar" else "ar")),
    )


@app.route("/admin/logout")
def admin_logout():
    lang = get_lang()
    session.pop("is_admin", None)
    flash("تم تسجيل الخروج." if lang == "ar" else "Logged out.", "success")
    return redirect(url_for("public_menu", lang=lang))


@app.route("/admin")
def admin_dashboard():
    guard = require_admin()
    if guard:
        return guard

    lang = get_lang()
    settings = load_settings()
    items = load_menu()

    content = render_template_string(
        r"""
        <div class="toolbar">
          <a class="btn secondary" href="{{ url_for('public_menu', lang=lang) }}">{{ "عرض القائمة" if lang == "ar" else "View menu" }}</a>
        </div>

        <div class="split">
          <div class="card">
            <h2 class="section-title" style="margin-top:0;">{{ "إضافة صنف" if lang == "ar" else "Add item" }}</h2>
            <form method="post" action="{{ url_for('add_item', lang=lang) }}" enctype="multipart/form-data">
              <div class="row2">
                <div>
                  <label class="field-label">{{ "القسم" if lang == "ar" else "Category" }}</label>
                  <input class="input" name="category" required>
                </div>
                <div>
                  <label class="field-label">{{ "السعر" if lang == "ar" else "Price" }}</label>
                  <input class="input" name="price">
                </div>
              </div>
              <div style="margin-top:12px;">
                <label class="field-label">{{ "اسم الصنف" if lang == "ar" else "Item name" }}</label>
                <input class="input" name="item_name" required>
              </div>
              <div style="margin-top:12px;">
                <label class="field-label">{{ "الوصف" if lang == "ar" else "Description" }}</label>
                <textarea name="description"></textarea>
              </div>
              <div style="margin-top:12px;">
                <label class="field-label">{{ "صورة للصنف" if lang == "ar" else "Item image" }}</label>
                <input class="file" type="file" name="item_image" accept="image/*">
              </div>
              <div style="margin-top:14px;">
                <button class="btn" type="submit">{{ "إضافة" if lang == "ar" else "Add" }}</button>
              </div>
            </form>
          </div>

          <div class="card">
            <h2 class="section-title" style="margin-top:0;">{{ "استيراد البيانات" if lang == "ar" else "Import data" }}</h2>
            <form method="post" action="{{ url_for('import_csv_text', lang=lang) }}">
              <label class="field-label">CSV</label>
              <textarea name="csv_text" placeholder="Category,Item Name,Description,Price"></textarea>
              <div style="margin-top:14px;">
                <button class="btn" type="submit">{{ "استيراد النص" if lang == "ar" else "Import text" }}</button>
              </div>
            </form>
            <hr style="border-color:rgba(255,255,255,.08); margin:20px 0;">
            <form method="post" action="{{ url_for('import_sheet', lang=lang) }}">
              <label class="field-label">{{ "رابط Google Sheets" if lang == "ar" else "Google Sheets URL" }}</label>
              <input class="input" name="sheet_url" placeholder="https://docs.google.com/spreadsheets/...">
              <div style="margin-top:14px;">
                <button class="btn secondary" type="submit">{{ "استيراد من الرابط" if lang == "ar" else "Import from URL" }}</button>
              </div>
            </form>
          </div>
        </div>

        <div class="split" style="margin-top:18px;">
          <div class="card">
            <h2 class="section-title" style="margin-top:0;">{{ "الإعدادات" if lang == "ar" else "Settings" }}</h2>
            <form method="post" action="{{ url_for('save_site_settings', lang=lang) }}" enctype="multipart/form-data">
              <div class="row2">
                <div>
                  <label class="field-label">{{ "العنوان بالعربية" if lang == "ar" else "Arabic title" }}</label>
                  <input class="input" name="site_title_ar" value="{{ settings.site_title_ar }}">
                </div>
                <div>
                  <label class="field-label">{{ "English title" }}</label>
                  <input class="input" name="site_title_en" value="{{ settings.site_title_en }}">
                </div>
              </div>
              <div class="row2" style="margin-top:12px;">
                <div>
                  <label class="field-label">{{ "الوصف بالعربية" if lang == "ar" else "Arabic subtitle" }}</label>
                  <input class="input" name="site_subtitle_ar" value="{{ settings.site_subtitle_ar }}">
                </div>
                <div>
                  <label class="field-label">English subtitle</label>
                  <input class="input" name="site_subtitle_en" value="{{ settings.site_subtitle_en }}">
                </div>
              </div>
              <div class="row2" style="margin-top:12px;">
                <div>
                  <label class="field-label">{{ "عملة العربية" if lang == "ar" else "Arabic currency" }}</label>
                  <input class="input" name="currency_ar" value="{{ settings.currency_ar }}">
                </div>
                <div>
                  <label class="field-label">{{ "English currency" }}</label>
                  <input class="input" name="currency_en" value="{{ settings.currency_en }}">
                </div>
              </div>
              <div style="margin-top:12px;">
                <label class="field-label">{{ "الشعار" if lang == "ar" else "Logo image" }}</label>
                <input class="file" type="file" name="logo" accept="image/*">
                {% if settings.logo_path %}
                  <div class="small" style="margin-top:8px;">{{ settings.logo_path }}</div>
                {% endif %}
              </div>
              <div style="margin-top:14px;">
                <button class="btn" type="submit">{{ "حفظ الإعدادات" if lang == "ar" else "Save settings" }}</button>
              </div>
            </form>
          </div>

          <div class="card">
            <h2 class="section-title" style="margin-top:0;">{{ "نصائح" if lang == "ar" else "Notes" }}</h2>
            <p class="sub">
              {{ "الأعمدة المطلوبة في CSV هي: Category, Item Name, Description, Price" if lang == "ar"
                else "Required CSV columns: Category, Item Name, Description, Price" }}
            </p>
            <p class="sub" style="margin-top:12px;">
              {{ "توليد الصور بالذكاء الاصطناعي يحتاج OPENAI_API_KEY" if lang == "ar"
                else "AI image generation needs OPENAI_API_KEY" }}
            </p>
          </div>
        </div>

        <div class="card" style="margin-top:18px;">
          <h2 class="section-title" style="margin-top:0;">
            <span>{{ "الأصناف الحالية" if lang == "ar" else "Current items" }}</span>
            <span class="section-count">{{ items|length }}</span>
          </h2>
          {% if items %}
            <div class="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{{ "القسم" if lang == "ar" else "Category" }}</th>
                    <th>{{ "الاسم" if lang == "ar" else "Name" }}</th>
                    <th>{{ "الوصف" if lang == "ar" else "Description" }}</th>
                    <th>{{ "السعر" if lang == "ar" else "Price" }}</th>
                    <th>{{ "الإجراءات" if lang == "ar" else "Actions" }}</th>
                  </tr>
                </thead>
                <tbody>
                  {% for item in items %}
                    <tr>
                      <td>{{ item["Category"] }}</td>
                      <td>{{ item["Item Name"] }}</td>
                      <td>{{ item["Description"] }}</td>
                      <td>{{ item["Price"] }}</td>
                      <td class="actions">
                        <form method="post" action="{{ url_for('generate_image_for_item', lang=lang) }}">
                          <input type="hidden" name="item_name" value="{{ item['Item Name'] }}">
                          <input type="hidden" name="category" value="{{ item['Category'] }}">
                          <button class="btn secondary" type="submit">{{ "توليد صورة" if lang == "ar" else "Generate image" }}</button>
                        </form>
                        <form method="get" action="{{ url_for('edit_item_page') }}">
                          <input type="hidden" name="item_name" value="{{ item['Item Name'] }}">
                          <input type="hidden" name="lang" value="{{ lang }}">
                          <button class="btn secondary" type="submit">{{ "تعديل" if lang == "ar" else "Edit" }}</button>
                        </form>
                        <form method="post" action="{{ url_for('delete_item', lang=lang) }}" onsubmit="return confirm('{{ 'حذف الصنف؟' if lang == 'ar' else 'Delete item?' }}')">
                          <input type="hidden" name="item_name" value="{{ item['Item Name'] }}">
                          <button class="btn danger" type="submit">{{ "حذف" if lang == "ar" else "Delete" }}</button>
                        </form>
                      </td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="center-empty">{{ "لا توجد أصناف بعد" if lang == "ar" else "No items yet" }}</div>
          {% endif %}
        </div>
        """,
        lang=lang,
        settings=settings,
        items=items,
    )

    return render_template_string(
        BASE_HTML,
        title=("لوحة التحكم" if lang == "ar" else "Dashboard"),
        content=content,
        lang=lang,
        direction=page_direction(lang),
        align=text_align(lang),
        settings=settings,
        is_admin=is_admin(),
        lang_switch_url=url_for("admin_dashboard", lang=("en" if lang == "ar" else "ar")),
    )


@app.route("/admin/item/add", methods=["POST"])
def add_item():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    items = load_menu()

    item = {
        "Category": request.form.get("category", "").strip(),
        "Item Name": request.form.get("item_name", "").strip(),
        "Description": request.form.get("description", "").strip(),
        "Price": request.form.get("price", "").strip(),
    }
    if not item["Category"] or not item["Item Name"]:
        flash("القسم واسم الصنف مطلوبان." if lang == "ar" else "Category and item name are required.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))

    # replace if same name exists
    replaced = False
    for idx, old in enumerate(items):
        if old["Item Name"].strip().lower() == item["Item Name"].strip().lower():
            items[idx] = item
            replaced = True
            break
    if not replaced:
        items.append(item)

    image = request.files.get("item_image")
    if image and image.filename:
        save_item_image(item["Item Name"], image)

    save_menu(items)
    flash("تم حفظ الصنف." if lang == "ar" else "Item saved.", "success")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/item/edit")
def edit_item_page():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    settings = load_settings()
    item_name = request.args.get("item_name", "").strip()
    items = load_menu()
    item = next((x for x in items if x["Item Name"] == item_name), None)
    if not item:
        flash("الصنف غير موجود." if lang == "ar" else "Item not found.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))

    content = render_template_string(
        r"""
        <div class="card">
          <h2 class="section-title" style="margin-top:0;">{{ "تعديل الصنف" if lang == "ar" else "Edit item" }}</h2>
          <form method="post" action="{{ url_for('edit_item', lang=lang) }}" enctype="multipart/form-data">
            <input type="hidden" name="original_item_name" value="{{ item['Item Name'] }}">
            <div class="row2">
              <div>
                <label class="field-label">{{ "القسم" if lang == "ar" else "Category" }}</label>
                <input class="input" name="category" value="{{ item['Category'] }}" required>
              </div>
              <div>
                <label class="field-label">{{ "السعر" if lang == "ar" else "Price" }}</label>
                <input class="input" name="price" value="{{ item['Price'] }}">
              </div>
            </div>
            <div style="margin-top:12px;">
              <label class="field-label">{{ "اسم الصنف" if lang == "ar" else "Item name" }}</label>
              <input class="input" name="item_name" value="{{ item['Item Name'] }}" required>
            </div>
            <div style="margin-top:12px;">
              <label class="field-label">{{ "الوصف" if lang == "ar" else "Description" }}</label>
              <textarea name="description">{{ item['Description'] }}</textarea>
            </div>
            <div style="margin-top:12px;">
              <label class="field-label">{{ "تغيير الصورة" if lang == "ar" else "Replace image" }}</label>
              <input class="file" type="file" name="item_image" accept="image/*">
            </div>
            <div style="margin-top:14px;" class="toolbar">
              <button class="btn" type="submit">{{ "حفظ" if lang == "ar" else "Save" }}</button>
              <a class="btn secondary" href="{{ url_for('admin_dashboard', lang=lang) }}">{{ "رجوع" if lang == "ar" else "Back" }}</a>
            </div>
          </form>
        </div>
        """,
        lang=lang,
        item=item,
    )
    return render_template_string(
        BASE_HTML,
        title=("تعديل الصنف" if lang == "ar" else "Edit item"),
        content=content,
        lang=lang,
        direction=page_direction(lang),
        align=text_align(lang),
        settings=settings,
        is_admin=is_admin(),
        lang_switch_url=url_for("edit_item_page", item_name=item_name, lang=("en" if lang == "ar" else "ar")),
    )


@app.route("/admin/item/edit", methods=["POST"])
def edit_item():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    original = request.form.get("original_item_name", "").strip()
    new_item = {
        "Category": request.form.get("category", "").strip(),
        "Item Name": request.form.get("item_name", "").strip(),
        "Description": request.form.get("description", "").strip(),
        "Price": request.form.get("price", "").strip(),
    }
    items = load_menu()
    updated = False
    for idx, item in enumerate(items):
        if item["Item Name"] == original:
            items[idx] = new_item
            updated = True
            break
    if not updated:
        flash("الصنف غير موجود." if lang == "ar" else "Item not found.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))

    image = request.files.get("item_image")
    if image and image.filename:
        save_item_image(new_item["Item Name"], image)

    save_menu(items)
    flash("تم تحديث الصنف." if lang == "ar" else "Item updated.", "success")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/item/delete", methods=["POST"])
def delete_item():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    item_name = request.form.get("item_name", "").strip()
    items = load_menu()
    new_items = [x for x in items if x["Item Name"] != item_name]
    save_menu(new_items)
    flash("تم حذف الصنف." if lang == "ar" else "Item deleted.", "success")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/import/csv-text", methods=["POST"])
def import_csv_text():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    text = request.form.get("csv_text", "").strip()
    if not text:
        flash("ألصق نص CSV أولاً." if lang == "ar" else "Paste CSV text first.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))
    try:
        items = parse_csv_text(text)
        save_menu(items)
        flash("تم استيراد البيانات." if lang == "ar" else "Data imported.", "success")
    except Exception as e:
        flash((f"فشل الاستيراد: {e}") if lang == "ar" else f"Import failed: {e}", "error")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/import/sheet", methods=["POST"])
def import_sheet():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    url = request.form.get("sheet_url", "").strip()
    if not url:
        flash("أدخل الرابط أولاً." if lang == "ar" else "Enter the URL first.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))
    try:
        csv_url = sheets_to_csv_url(url)
        text = download_text(csv_url)
        items = parse_csv_text(text)
        save_menu(items)
        flash("تم الاستيراد من Google Sheets." if lang == "ar" else "Imported from Google Sheets.", "success")
    except Exception as e:
        flash((f"فشل الاستيراد: {e}") if lang == "ar" else f"Import failed: {e}", "error")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/settings/save", methods=["POST"])
def save_site_settings():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    data = {
        "site_title_ar": request.form.get("site_title_ar", "").strip() or "قائمة المطعم",
        "site_title_en": request.form.get("site_title_en", "").strip() or "Restaurant Menu",
        "site_subtitle_ar": request.form.get("site_subtitle_ar", "").strip() or "قائمة رقمية حديثة",
        "site_subtitle_en": request.form.get("site_subtitle_en", "").strip() or "Modern digital menu",
        "currency_ar": request.form.get("currency_ar", "").strip() or "د.ع",
        "currency_en": request.form.get("currency_en", "").strip() or "IQD",
    }
    logo = request.files.get("logo")
    if logo and logo.filename:
        data["logo_path"] = save_uploaded_logo(logo)
    save_settings(data)
    flash("تم حفظ الإعدادات." if lang == "ar" else "Settings saved.", "success")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/admin/item/generate-image", methods=["POST"])
def generate_image_for_item():
    guard = require_admin()
    if guard:
        return guard
    lang = get_lang()
    item_name = request.form.get("item_name", "").strip()
    category = request.form.get("category", "").strip()
    if not item_name:
        flash("اسم الصنف مطلوب." if lang == "ar" else "Item name is required.", "error")
        return redirect(url_for("admin_dashboard", lang=lang))
    _, err = generate_item_image(item_name, category)
    if err:
        flash((f"فشل توليد الصورة: {err}") if lang == "ar" else f"Image generation failed: {err}", "error")
    else:
        flash("تم توليد الصورة." if lang == "ar" else "Image generated.", "success")
    return redirect(url_for("admin_dashboard", lang=lang))


@app.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/health")
def health():
    return {"ok": True, "items": len(load_menu())}


if __name__ == "__main__":
    app.run(host=host, port=port, debug=False)
