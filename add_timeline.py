#!/usr/bin/env python3
"""
Dashboard generator: transforms dashboard_hospitalization.html (base template)
using data.json, outputting dashboard.html and index.html.

Session-portable: auto-detects user folder from any /sessions/*/mnt/.
No hardcoded session names. Self-contained.
"""
import json, re, os, unicodedata, shutil, hashlib, sys
from datetime import datetime, date
from collections import OrderedDict

# ──────────────────────── Locate user folder ────────────────────────
def find_user_folder():
    """Auto-detect the user folder regardless of current session name."""
    # 1) Try the folder where this script lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) and 'デイリー治験ダッシュボード' in unicodedata.normalize('NFC', os.path.basename(script_dir)):
        return script_dir
    # 2) Scan /sessions/*/mnt/ for the folder
    sessions_root = '/sessions'
    if os.path.isdir(sessions_root):
        for sess in os.listdir(sessions_root):
            mnt = os.path.join(sessions_root, sess, 'mnt')
            if not os.path.isdir(mnt):
                continue
            try:
                for e in os.listdir(mnt):
                    if 'デイリー治験ダッシュボード' in unicodedata.normalize('NFC', e):
                        return os.path.join(mnt, e)
            except PermissionError:
                continue
    return None

USER_FOLDER = find_user_folder()
if not USER_FOLDER:
    print("ERROR: could not locate デイリー治験ダッシュボード folder", file=sys.stderr)
    sys.exit(1)
print(f"User folder: {USER_FOLDER}")

# ──────────────────────── Paths ────────────────────────
DATA_PATH = os.path.join(USER_FOLDER, 'data.json')
PREV_PATH = os.path.join(USER_FOLDER, 'prev_data.json')
BASE_HTML_PATH = os.path.join(USER_FOLDER, 'dashboard_hospitalization.html')  # clean template
OUT_DASHBOARD = os.path.join(USER_FOLDER, 'dashboard.html')
OUT_INDEX = os.path.join(USER_FOLDER, 'index.html')

# ──────────────────────── Load data ────────────────────────
if not os.path.exists(DATA_PATH):
    print(f"ERROR: {DATA_PATH} not found", file=sys.stderr)
    sys.exit(1)
if not os.path.exists(BASE_HTML_PATH):
    print(f"ERROR: base template {BASE_HTML_PATH} not found", file=sys.stderr)
    sys.exit(1)

with open(DATA_PATH) as f:
    data = json.load(f)
items = data['items']

YEAR = 2026
TODAY = date.today()

# ──────────────────────── Detect new/updated ────────────────────────
prev_items = {}
if os.path.exists(PREV_PATH):
    with open(PREV_PATH) as f:
        prev_data = json.load(f)
    for pi in prev_data.get('items', []):
        prev_items[pi['url']] = pi

new_count = 0
updated_count = 0
for item in items:
    url = item['url']
    if url not in prev_items:
        item['_status'] = 'new'
        new_count += 1
    else:
        old = prev_items[url]
        changes = []
        if item.get('compensation_num') != old.get('compensation_num'):
            changes.append('compensation')
        if item.get('total_nights') != old.get('total_nights'):
            changes.append('nights')
        if item.get('title') != old.get('title'):
            changes.append('title')
        if changes:
            item['_status'] = 'updated'
            item['_changes'] = changes
            updated_count += 1
        else:
            item['_status'] = 'unchanged'

if not prev_items:
    for item in items:
        item['_status'] = 'first_run'
    new_count = 0
    updated_count = 0

# Save current as prev for next run
shutil.copy2(DATA_PATH, PREV_PATH)
print("Saved prev_data.json for next comparison")

print(f"New: {new_count}, Updated: {updated_count}, Unchanged: {len(items)-new_count-updated_count}")

# ──────────────────────── Location extraction (added) ────────────────────────
_PREFS = ('北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
          '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
          '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
          '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
          '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
          '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
          '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県')

# District/locality → ward/city mapping for non-suffix area names
_DISTRICT_TO_WARD = {
    # 東京23区 popular districts → ward
    '浅草': '台東区', '上野': '台東区',
    '池袋': '豊島区', '巣鴨': '豊島区', '大塚': '豊島区',
    '渋谷': '渋谷区', '原宿': '渋谷区', '恵比寿': '渋谷区',
    '新宿': '新宿区', '神楽坂': '新宿区',
    '銀座': '中央区', '日本橋': '中央区', '築地': '中央区',
    '六本木': '港区', '赤坂': '港区', '青山': '港区', '麻布': '港区', '虎ノ門': '港区',
    '品川': '品川区', '大崎': '品川区',
    '秋葉原': '千代田区', '丸の内': '千代田区', '神田': '千代田区',
    'みなとみらい': '横浜市', '元町': '横浜市',
    '梅田': '大阪市', '心斎橋': '大阪市', '難波': '大阪市', '天王寺': '大阪市',
    '祇園': '京都市', '河原町': '京都市',
    '三宮': '神戸市',
    'すすきの': '札幌市',
    '栄': '名古屋市', '名駅': '名古屋市',
    '博多': '福岡市', '天神': '福岡市',
}

_SHORT_TO_CITY = {
    '東京': '東京都', '横浜': '横浜市', '京都': '京都市', '神戸': '神戸市', '札幌': '札幌市',
    '名古屋': '名古屋市', '仙台': '仙台市', '広島': '広島市', '奈良': '奈良市',
    '熊本': '熊本市', '福岡': '福岡市', '大阪': '大阪府',
}

_REGION_BROAD = {
    '都内': '東京都', '関東': '関東', '関西': '関西', '九州': '九州',
}

_NOISY_PREFIX_RE = re.compile(r'^[^一-龥]+')

def _extract_location_from_text(text):
    """Try multiple patterns to extract a city/ward/town/prefecture from arbitrary text."""
    if not text:
        return None
    # 1) 都道府県+市区町村 combined → return city only
    m = re.search(r'(?:北海道|[一-龥]{1,4}(?:都|府|県))([一-龥]{1,5}(?:市|区|町|村))', text)
    if m:
        return m.group(1)
    # 2) Standalone 市区町村 — strip pref-name prefix from result if present
    for m in re.finditer(r'([一-龥]{1,5})(市|区|町|村)', text):
        prefix = m.group(1)
        if not prefix:
            continue
        result = prefix + m.group(2)
        stripped = _strip_pref_prefix(result)
        if stripped and stripped != result and re.match(r'^[一-龥]{1,5}(?:市|区|町|村)$', stripped):
            return stripped
        return result
    # 3) Known district name → ward
    for k, v in _DISTRICT_TO_WARD.items():
        if k in text:
            return v
    # 4) 都道府県 alone
    for p in _PREFS:
        if p in text:
            return p
    # 5) Short city keyword
    for k, v in _SHORT_TO_CITY.items():
        if k in text:
            return v
    # 6) Broad region (last resort)
    for k, v in _REGION_BROAD.items():
        if k in text:
            return v
    return None

_SHORT_PREF_NAMES = ('東京', '大阪', '京都', '神奈川', '北海道', '兵庫', '愛知',
                     '埼玉', '千葉', '福岡', '熊本', '奈良', '広島', '宮城', '静岡')

def _strip_pref_prefix(s):
    """Strip leading 都道府県 or short pref name, returning the city portion."""
    if not s:
        return s
    for p in _PREFS:
        if s.startswith(p):
            return s[len(p):]
    for sp in _SHORT_PREF_NAMES:
        if s.startswith(sp):
            return s[len(sp):]
    return s

def smart_location(item):
    """Best-effort location for an item, prioritizing 市区町村 > 都道府県."""
    pref = (item.get('prefecture') or '').strip()
    title = item.get('title', '') or ''

    _BROAD = {'関東', '関西', '中部', '九州', '九州・沖縄', '東北', '中国', '四国', '中国・四国', '北海道', 'その他', '都内'}
    if pref and pref != '不明':
        # 0) If pref is just a broad region, try to upgrade with title-derived specific location
        if pref in _BROAD:
            ext = _extract_location_from_text(title)
            if ext and ext not in _BROAD and ext != pref:
                return ext
            return pref
        # 1) Strip pref prefix to expose city (handles "神奈川横浜市" → "横浜市", "東京台東区" → "台東区")
        stripped = _strip_pref_prefix(pref)
        if stripped and stripped != pref:
            m = re.match(r'^([一-龥]{1,5})(市|区|町|村)$', stripped)
            if m:
                return stripped

        # 2) Find ANY 市区町村 in pref (handles noisy prefixes like "登場★港区")
        # Take the LAST (most specific) match
        matches = list(re.finditer(r'([一-龥]{1,5})(市|区|町|村)', pref))
        if matches:
            m = matches[-1]
            return m.group(1) + m.group(2)

        # 3) If pref is a clean 都道府県, try to upgrade with title (only if ext is more specific)
        if pref in _PREFS:
            ext = _extract_location_from_text(title)
            # Only swap if ext is a 市区町村 (more specific), not a broad region
            if ext and ext not in _PREFS and ext not in _BROAD and ext != pref:
                return ext
            return pref

        # 4) Strip noise and return
        cleaned = _NOISY_PREFIX_RE.sub('', pref)
        if cleaned:
            return cleaned

    # 5) No useful pref → extract from title
    ext = _extract_location_from_text(title)
    return ext or '不明'

# ──────────────────────── Trial type helpers (added) ────────────────────────
def recalc_nights_from_title(title):
    """Re-derive total nights from title, handling all multiplier forms.
    Returns (total_nights, desc_str_or_None).
    Patterns:
      N泊M日×K回   (e.g. 6泊7日×2回)  -> N*K
      N泊×K回                       -> N*K
      N泊K回 (implicit, NOT after 通院/来院/通所) -> N*K
      Plain N泊                      -> N
    """
    if not title:
        return 0, None
    total = 0
    desc = []
    used = []  # list of (start, end) consumed ranges
    def overlap(s, e):
        return any(us <= s < ue or s <= us < e for us, ue in used)
    # 1) N泊M日×K回
    for m in re.finditer(r'(\d+)泊\d+日\s*[×xX]\s*(\d+)\s*回?', title):
        n, k = int(m.group(1)), int(m.group(2))
        total += n * k
        desc.append(f'{n}泊×{k}回')
        used.append((m.start(), m.end()))
    # 2) N泊×K回
    for m in re.finditer(r'(\d+)泊\s*[×xX]\s*(\d+)\s*回?', title):
        if overlap(m.start(), m.end()): continue
        n, k = int(m.group(1)), int(m.group(2))
        total += n * k
        desc.append(f'{n}泊×{k}回')
        used.append((m.start(), m.end()))
    # 3) N泊K回 (implicit), but skip if preceded by 通院/来院/通所
    for m in re.finditer(r'(\d+)泊\s*(\d+)\s*回', title):
        if overlap(m.start(), m.end()): continue
        before = title[max(0, m.start()-3):m.start()]
        if any(kw in before for kw in ('通院', '来院', '通所')): continue
        n, k = int(m.group(1)), int(m.group(2))
        total += n * k
        desc.append(f'{n}泊×{k}回')
        used.append((m.start(), m.end()))
    # 4) Standalone N泊 (after removing consumed parts)
    cleaned = list(title)
    for s, e in used:
        for i in range(s, e):
            cleaned[i] = ' '
    standalone = re.findall(r'(\d+)泊', ''.join(cleaned))
    for n in standalone:
        total += int(n)
        desc.append(f'{n}泊')
    return total, ('+'.join(desc) if len(desc) > 1 else None)

def extract_outpatient_count(title):
    """Extract total 通院/通所/来院/来所 count from title."""
    if not title:
        return 0
    n = 0
    for m in re.finditer(r'通院\s*(\d+)\s*回?|(\d+)\s*通院\s*回?|通所\s*(\d+)\s*回?|来院\s*(\d+)\s*回?|来所\s*(\d+)\s*回?', title):
        n += next((int(g) for g in m.groups() if g), 0)
    # If keyword present but no number was extracted, count as 1
    if n == 0 and any(k in title for k in ('通院', '通所', '来院', '来所')):
        n = 1
    return n

def extract_pre_check_count(title):
    """Pre-trial check (事前検査) count. Default 1 when keyword present without number."""
    if not title:
        return 0
    n = 0
    for m in re.finditer(r'事前検査\s*(\d+)\s*回?', title):
        n += int(m.group(1))
    if n == 0 and '事前検査' in title:
        n = 1
    return n

def extract_post_check_count(title):
    """Post-trial check (事後検査) count. Default 1 when keyword present without number."""
    if not title:
        return 0
    n = 0
    for m in re.finditer(r'事後検査\s*(\d+)\s*回?', title):
        n += int(m.group(1))
    if n == 0 and '事後検査' in title:
        n = 1
    return n

def has_outpatient_in_title(title):
    return bool(title) and any(k in title for k in ('通院', '通所', '来院'))

def derive_trial_type(item):
    """Compute trial_type_combined from item (uses fields if present, else falls back to title)."""
    has_in = bool(item.get('has_inpatient')) or (item.get('total_nights') or item.get('nights') or 0) > 0
    has_out = bool(item.get('has_outpatient')) or has_outpatient_in_title(item.get('title', ''))
    if has_in and has_out: return '入院+通院'
    if has_out: return '通院のみ'
    if has_in: return '入院のみ'
    return '不明'

def build_composition_str(item):
    """Build display string like '5泊' / '3泊+通院1回' / '通院2回' (legacy single-cell)."""
    n = item.get('total_nights') or item.get('nights') or 0
    oc = item.get('outpatient_count')
    if oc is None:
        oc = extract_outpatient_count(item.get('title', ''))
    has_out = bool(item.get('has_outpatient')) or has_outpatient_in_title(item.get('title', ''))
    parts = []
    if n: parts.append(f'{n}泊')
    if oc: parts.append(f'通院{oc}回')
    elif has_out: parts.append('通院あり')
    return '+'.join(parts) if parts else '—'

def extract_admission_count(title):
    """Count distinct inpatient sessions from title.
    '3泊+3泊' -> 2, '4泊×2回' -> 2, '15泊' -> 1, '通院のみ' -> 0."""
    if not title:
        return 0
    count = 0
    # Multiplied form: N泊×M回 (counts as M sessions)
    for m in re.finditer(r'\d+泊\s*[×xX]\s*(\d+)', title):
        count += int(m.group(1))
    cleaned = re.sub(r'\d+泊\s*[×xX]\s*\d+\s*回?', '', title)
    # Standalone N泊 (each = 1 session)
    standalone = re.findall(r'\d+泊', cleaned)
    count += len(standalone)
    return count

def build_inpatient_cell(item):
    """Display content for inpatient column. Shows e.g. '6泊', '3泊+3泊', '4泊×2回 (8泊)', or '—'."""
    title = item.get('title', '') or ''
    n = item.get('total_nights') or item.get('nights') or 0
    if not n:
        return '—'
    nd = item.get('nights_desc')
    if nd:
        # nights_desc already shows pattern like '3泊+3泊' or '4泊×2回'
        admissions = extract_admission_count(title)
        if admissions > 1 and 'x' not in nd.lower() and '×' not in nd:
            return f'{nd} <span class="sub-count">({admissions}回)</span>'
        return nd
    return f'{n}泊'

def build_outpatient_cell(item):
    """Display content for outpatient column."""
    oc = item.get('outpatient_count')
    if oc is None:
        oc = extract_outpatient_count(item.get('title', ''))
    has_out = bool(item.get('has_outpatient')) or has_outpatient_in_title(item.get('title', ''))
    if oc and oc > 0:
        return f'{oc}回'
    if has_out:
        return 'あり'
    return '—'


def is_at_home_trial(item):
    """Detect 在宅モニター/在宅試験 — these don't fit the per-day model."""
    t = (item.get('title') or '')
    return any(k in t for k in ('在宅モニター', '在宅試験', '在宅治験', '通信モニター'))

OUTPATIENT_FEE = 10000  # 通院/通所/来院/来所 1回 = ¥10,000
PRE_CHECK_FEE  = 3000   # 事前検査 1回 = ¥3,000
POST_CHECK_FEE = 5000   # 事後検査 1回 = ¥5,000

def daily_rate(item):
    """Per-night inpatient rate after deducting outpatient + check costs.
    
    rate = (compensation
            − 通院/通所/来院/来所 × ¥10,000
            − 事前検査 × ¥3,000
            − 事後検査 × ¥5,000) / 入院泊数
    
    Returns 0 (displayed as '—') for:
      - At-home / 在宅 trials
      - Trials with no nights (visit-only)
      - After deductions, remaining ≤ 0 or out of sanity bounds [3K, 100K]/泊
    """
    if is_at_home_trial(item):
        return 0
    title = item.get('title', '') or ''
    n = item.get('total_nights') or item.get('nights') or 0
    oc = item.get('outpatient_count')
    if oc is None:
        oc = extract_outpatient_count(title)
    pre  = extract_pre_check_count(title)
    post = extract_post_check_count(title)
    comp = item.get('compensation_num', 0) or 0
    if not n or comp <= 0:
        return 0
    inpatient_comp = (comp
                      - (oc or 0) * OUTPATIENT_FEE
                      - pre * PRE_CHECK_FEE
                      - post * POST_CHECK_FEE)
    if inpatient_comp <= 0:
        return 0
    rate = inpatient_comp // n
    if rate < 3000 or rate > 100000:
        return 0
    return rate

def trial_type_badges(item):
    """Tiny badges shown next to title. Returns HTML."""
    tt = derive_trial_type(item)
    if tt == '入院+通院':
        return '<span class="tt-badge tt-in">🏥入院</span><span class="tt-badge tt-out">🚶通院</span>'
    if tt == '通院のみ':
        return '<span class="tt-badge tt-out">🚶通院のみ</span>'
    if tt == '入院のみ':
        return '<span class="tt-badge tt-in">🏥入院のみ</span>'
    return ''

# ──────────────────────── Date extraction ────────────────────────
def extract_date(title_or_item):
    """Extract date from title string OR fall back to item['scraped_start_date']."""
    title = title_or_item if isinstance(title_or_item, str) else title_or_item.get('title','')
    m = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', title)
    if m:
        try: return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: pass
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', title)
    if m:
        try: return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: pass
    matches = re.findall(r'(\d{1,2})/(\d{1,2})\s*\(.\)', title)
    if matches:
        dates = []
        for mm, dd in matches:
            try: dates.append(date(YEAR, int(mm), int(dd)))
            except ValueError: pass
        if dates: return min(dates)
    m = re.search(r'(\d{1,2})/(\d{1,2})(?:入院|開始|スタート|から)', title)
    if m:
        try: return date(YEAR, int(m.group(1)), int(m.group(2)))
        except ValueError: pass
    m = re.search(r'(\d{1,2})月(\d{1,2})日', title)
    if m:
        try: return date(YEAR, int(m.group(1)), int(m.group(2)))
        except ValueError: pass
    return None

for item in items:
    item['_start_date'] = extract_date(item['title'])
    # Fallback: if title didn't yield a date, try scraped_start_date from body
    if not item['_start_date'] and item.get('scraped_start_date'):
        try:
            from datetime import date as _date
            _y, _m, _d = item['scraped_start_date'].split('-')
            item['_start_date'] = _date(int(_y), int(_m), int(_d))
        except Exception:
            pass
    item['prefecture'] = smart_location(item)
    item['area'] = item['prefecture']
    # Re-derive nights from title to fix patterns like '6泊2回' / '6泊7日×2回' that scraper missed
    _new_n, _new_desc = recalc_nights_from_title(item.get('title', ''))
    if _new_n > 0:
        item['total_nights'] = _new_n
        item['nights'] = _new_n
        if _new_desc:
            item['nights_desc'] = _new_desc

# Filter: drop past-dated trials only. Keep undated items (they're typically active recruits without explicit start dates).
_before_filter = len(items)
items = [it for it in items if (not it.get('_start_date')) or it['_start_date'] >= TODAY]
print(f"Date filter: {_before_filter} -> {len(items)} items (dropped past, kept future + undated)")

# ──────────────────────── Build timeline data ────────────────────────
timeline_items = []
for item in items:
    timeline_items.append({
        'title': item['title'],
        'url': item['url'],
        'prefecture': item.get('prefecture', '不明'),
        'compensation_num': item.get('compensation_num', 0),
        'nights': item.get('total_nights') or item.get('nights'),
        'total_nights': item.get('total_nights') or item.get('nights'),
        'outpatient_count': item.get('outpatient_count'),
        'has_outpatient': item.get('has_outpatient'),
        'has_inpatient': item.get('has_inpatient'),
        'price_per_night': item.get('price_per_night'),
        'site': item.get('site', ''),
        'source_sites': item.get('source_sites', [item.get('site', '')]),
        'source_count': item.get('source_count', 1),
        'start_date': item['_start_date'],
        'status': item.get('_status', 'unchanged'),
    })

dated = sorted([e for e in timeline_items if e['start_date']], key=lambda e: e['start_date'])
undated = sorted([e for e in timeline_items if not e['start_date']], key=lambda e: -(e['compensation_num'] or 0))

months = OrderedDict()
for e in dated:
    key = f"{e['start_date'].year}年{e['start_date'].month}月"
    months.setdefault(key, []).append(e)

nearest_month = None
for key, entries in months.items():
    if any(e['start_date'] >= TODAY for e in entries):
        nearest_month = key
        break
if nearest_month is None and months:
    nearest_month = list(months.keys())[-1]

dated_count = len(dated)
undated_count = len(undated)
multi_site_count = sum(1 for e in timeline_items if e['source_count'] > 1)

# ──────────────────────── Helpers ────────────────────────
def fmt_comp(num):
    if num and num > 0: return f"¥{num:,.0f}"
    return "—"
def fmt_ppn(val):
    if val and val > 0: return f"¥{val:,.0f}"
    return "—"
def fmt_date(d):
    weekdays = ['月','火','水','木','金','土','日']
    return f"{d.month}/{d.day}({weekdays[d.weekday()]})"
def esc(s):
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def status_badge(status):
    if status == 'new':
        return '<span class="badge badge-new">NEW</span>'
    elif status == 'updated':
        return '<span class="badge badge-updated">更新</span>'
    return ''

# ──────────────────────── New CSS (full replacement) ────────────────────────
NEW_CSS = '''* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, 'SF Pro Display', 'Hiragino Mincho ProN', 'Yu Mincho', 'Yu Gothic', sans-serif;
  background: radial-gradient(ellipse at top, #102845 0%, #0a1c33 35%, #061325 70%, #030a18 100%);
  background-attachment: fixed;
  color: #e9d9b8;
  line-height: 1.6;
  min-height: 100vh;
  letter-spacing: 0.01em;
}

::selection { background: rgba(201,165,88,0.4); color: #fff; }

.header {
  background: linear-gradient(135deg, rgba(201,165,88,0.12) 0%, rgba(30,58,95,0.25) 50%, rgba(13,28,46,0.4) 100%);
  backdrop-filter: blur(14px);
  padding: 22px 36px;
  border-bottom: 1px solid rgba(201,165,88,0.3);
  box-shadow: 0 1px 0 rgba(201,165,88,0.08), 0 8px 24px rgba(0,0,0,0.4);
  display: flex; justify-content: space-between; align-items: center;
}
.header h1 {
  font-size: 1.5rem;
  font-weight: 300;
  color: #f1e4c6;
  letter-spacing: 0.08em;
  background: linear-gradient(135deg, #e0bb73 0%, #f1e4c6 50%, #c9a558 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.header .meta { color: #a8b8d0; font-size: 0.78rem; letter-spacing: 0.05em; }
.header .meta .pipe { color: rgba(201,165,88,0.4); margin: 0 8px; }

.container { padding: 28px 32px 60px; max-width: 1400px; margin: 0 auto; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-bottom: 24px; }
.kpi-card {
  background: linear-gradient(145deg, rgba(20,38,67,0.8) 0%, rgba(11,24,44,0.9) 100%);
  border: 1px solid rgba(201,165,88,0.25);
  border-radius: 12px;
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  box-shadow:
    0 4px 20px rgba(0,0,0,0.4),
    inset 0 1px 0 rgba(201,165,88,0.18);
  transition: all 0.3s ease;
}
.kpi-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(201,165,88,0.5), transparent);
}
.kpi-card:hover {
  transform: translateY(-2px);
  border-color: rgba(201,165,88,0.45);
  box-shadow: 0 8px 28px rgba(0,0,0,0.5), inset 0 1px 0 rgba(201,165,88,0.3);
}
.kpi-card .label { color: #a8b8d0; font-size: 0.72rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 8px; }
.kpi-card .value {
  font-size: 1.8rem;
  font-weight: 200;
  background: linear-gradient(135deg, #f1e4c6 0%, #c9a558 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: 0.02em;
}
.kpi-card .value.green { background: linear-gradient(135deg, #b8e2c4 0%, #6db896 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.kpi-card .value.purple { background: linear-gradient(135deg, #d4c5e8 0%, #a78bfa 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }

.charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 18px; margin-bottom: 28px; }
.chart-card {
  background: linear-gradient(145deg, rgba(15,30,52,0.85) 0%, rgba(8,20,38,0.92) 100%);
  border: 1px solid rgba(201,165,88,0.18);
  border-radius: 14px;
  padding: 22px 24px;
  backdrop-filter: blur(8px);
  box-shadow: 0 6px 28px rgba(0,0,0,0.4), inset 0 1px 0 rgba(201,165,88,0.1);
}
.chart-card h3 {
  font-size: 0.82rem;
  font-weight: 500;
  color: #c9a558;
  margin-bottom: 16px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(201,165,88,0.2);
}

.timeline-hero {
  background: linear-gradient(145deg, rgba(15,30,52,0.85), rgba(8,20,38,0.92));
  border: 1px solid rgba(201,165,88,0.22);
  border-radius: 14px;
  padding: 24px 28px;
  margin-bottom: 24px;
  box-shadow: 0 6px 28px rgba(0,0,0,0.4);
}
.timeline-hero h3 { color: #c9a558; font-size: 0.95rem; font-weight: 500; margin-bottom: 16px; letter-spacing: 0.1em; }
.tl-stats { display: flex; gap: 24px; margin-bottom: 18px; flex-wrap: wrap; }
.tl-stat { display: flex; align-items: baseline; gap: 8px; font-size: 0.82rem; }
.tl-stat .num { font-weight: 300; font-size: 1.3rem; }
.tl-stat .num.blue { color: #93c5fd; }
.tl-stat .num.gray { color: #a8b8d0; }
.tl-stat .num.gold { color: #c9a558; }
.tl-stat .num.green { color: #86efac; }

.tt-badge { display: inline-block; padding: 2px 7px; margin-left: 5px; border-radius: 3px; font-size: 0.66rem; font-weight: 600; vertical-align: middle; letter-spacing: 0.05em; }
.tt-in { background: rgba(147,197,253,0.14); color: #93c5fd; border: 1px solid rgba(147,197,253,0.35); }
.tt-out { background: rgba(201,165,88,0.18); color: #e0bb73; border: 1px solid rgba(201,165,88,0.4); }

.trial-type-tabs { display: flex; gap: 8px; margin: 14px 0 10px; flex-wrap: wrap; }
.ttab {
  background: linear-gradient(145deg, rgba(15,30,52,0.6), rgba(8,20,38,0.7));
  color: #cbd5e1; border: 1px solid rgba(201,165,88,0.18); border-radius: 8px;
  padding: 8px 18px; font-size: 0.82rem; cursor: pointer;
  transition: all 0.2s; letter-spacing: 0.04em;
}
.ttab:hover { background: linear-gradient(145deg, rgba(20,38,67,0.8), rgba(11,24,44,0.9)); border-color: rgba(201,165,88,0.45); }
.ttab.active {
  background: linear-gradient(135deg, rgba(201,165,88,0.28) 0%, rgba(201,165,88,0.12) 100%);
  border-color: #c9a558; color: #f1e4c6; font-weight: 500;
  box-shadow: 0 2px 12px rgba(201,165,88,0.2), inset 0 1px 0 rgba(201,165,88,0.3);
}
.ttab .count { opacity: 0.7; margin-left: 6px; font-size: 0.72rem; }
.ttype-hidden { display: none !important; }

.filters {
  background: linear-gradient(145deg, rgba(15,30,52,0.7), rgba(8,20,38,0.85));
  border: 1px solid rgba(201,165,88,0.18);
  border-radius: 12px; padding: 14px 18px; margin-bottom: 18px;
  display: flex; gap: 14px; flex-wrap: wrap; align-items: center;
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.filters label { color: #a8b8d0; font-size: 0.78rem; letter-spacing: 0.05em; }
.filters select, .filters input {
  background: rgba(8,20,38,0.85); color: #e9d9b8;
  border: 1px solid rgba(201,165,88,0.25); border-radius: 8px;
  padding: 8px 12px; font-size: 0.82rem;
  transition: border-color 0.2s;
}
.filters select:focus, .filters input:focus { border-color: rgba(201,165,88,0.55); outline: none; }
.filters input { width: 240px; }

table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  background: linear-gradient(145deg, rgba(15,30,52,0.65), rgba(8,20,38,0.85));
  border: 1px solid rgba(201,165,88,0.18);
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.45);
}
table thead {
  background: linear-gradient(135deg, rgba(20,38,67,0.95), rgba(11,24,44,0.98));
  border-bottom: 1px solid rgba(201,165,88,0.3);
}
table th {
  padding: 14px 14px; text-align: left;
  color: #c9a558; font-weight: 500; font-size: 0.74rem;
  text-transform: uppercase; letter-spacing: 0.12em;
  cursor: pointer; user-select: none;
  border-bottom: 1px solid rgba(201,165,88,0.2);
}
table th:hover { color: #e0bb73; background: rgba(201,165,88,0.06); }
table td {
  padding: 12px 14px; border-bottom: 1px solid rgba(201,165,88,0.08);
  font-size: 0.85rem; color: #e9d9b8;
}
table tr:hover td { background: rgba(201,165,88,0.04); }
table tr:last-child td { border-bottom: none; }

table a { color: #f1e4c6; text-decoration: none; transition: color 0.15s; }
table a:hover { color: #c9a558; }
table a.unvisited { color: #f1e4c6; }
table a.unvisited::before { content: '● '; color: #c9a558; font-size: 0.6rem; vertical-align: middle; }

td.comp { color: #c9a558; font-weight: 500; font-variant-numeric: tabular-nums; }
td.nights { color: #a8b8d0; font-size: 0.8rem; }
td.ppn { color: #93c5fd; font-variant-numeric: tabular-nums; font-size: 0.82rem; }
td.date-cell { font-variant-numeric: tabular-nums; font-weight: 500; font-size: 0.82rem; text-align: center; color: #f1e4c6; }
td.date-cell.past { color: #6b7c93; opacity: 0.5; }
td.date-cell.soon { color: #fcd34d; font-weight: 600; }
td.date-cell.undated { color: #6b7c93; font-style: italic; opacity: 0.6; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 500; letter-spacing: 0.04em; }
.badge-area { background: rgba(201,165,88,0.14); color: #e0bb73; border: 1px solid rgba(201,165,88,0.32); }
.badge-site { background: rgba(147,197,253,0.12); color: #93c5fd; border: 1px solid rgba(147,197,253,0.3); margin-right: 4px; }
.badge-dup { background: rgba(167,139,250,0.15); color: #c4b5fd; border: 1px solid rgba(167,139,250,0.3); }
.badge-new { background: rgba(134,239,172,0.18); color: #86efac; border: 1px solid rgba(134,239,172,0.4); margin-left: 6px; }
.badge-updated { background: rgba(252,211,77,0.18); color: #fcd34d; border: 1px solid rgba(252,211,77,0.4); margin-left: 6px; }

.row-new { background: rgba(134,239,172,0.05); }
.row-updated { background: rgba(252,211,77,0.05); }
.hidden { display: none !important; }

.month-header td {
  background: linear-gradient(90deg, rgba(201,165,88,0.12), rgba(20,38,67,0.6));
  color: #c9a558;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 12px 14px;
  font-size: 0.85rem;
  cursor: pointer;
  border-top: 1px solid rgba(201,165,88,0.2);
}

.click-count {
  display: inline-block; padding: 1px 7px; border-radius: 10px;
  font-size: 0.7rem; font-weight: 500; min-width: 20px; text-align: center;
}
.click-count.zero { background: rgba(107,124,147,0.15); color: #6b7c93; }
.click-count.low { background: rgba(147,197,253,0.18); color: #93c5fd; }
.click-count.mid { background: rgba(201,165,88,0.2); color: #e0bb73; }
.click-count.high { background: rgba(252,211,77,0.25); color: #fcd34d; }

@media (max-width: 768px) {
  .header { padding: 14px 18px; }
  .header h1 { font-size: 1.1rem; }
  .container { padding: 18px 14px 40px; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .kpi-card { padding: 12px 14px; }
  .kpi-card .value { font-size: 1.4rem; }
  .charts-grid { grid-template-columns: 1fr; }
  .filters { flex-direction: column; align-items: stretch; }
  .filters input { width: 100%; }
  table { font-size: 0.76rem; }
  table th, table td { padding: 8px 6px; }
}


/* ── Timeline month bar ── */
.tl-bar-wrap {
  display: flex; gap: 12px; align-items: flex-end;
  margin: 16px 0 18px; padding: 14px 18px;
  background: linear-gradient(145deg, rgba(8,20,38,0.6), rgba(15,30,52,0.4));
  border: 1px solid rgba(201,165,88,0.15);
  border-radius: 10px;
  overflow-x: auto;
}
.tl-bar-item {
  min-width: 64px; flex: 0 0 auto;
  display: flex; flex-direction: column; align-items: center;
  gap: 6px; cursor: pointer; transition: transform 0.15s;
}
.tl-bar-item:hover { transform: translateY(-2px); }
.tl-bar-count { font-size: 0.95rem; font-weight: 500; color: #f1e4c6; font-variant-numeric: tabular-nums; }
.tl-bar-col {
  width: 32px; min-height: 18px; border-radius: 4px;
  background: linear-gradient(180deg, #c9a558, #8a6f30) !important;
  box-shadow: 0 2px 8px rgba(201,165,88,0.25);
}
.tl-bar-label { font-size: 0.72rem; color: #a8b8d0; letter-spacing: 0.05em; }

.status-legend { display: flex; gap: 14px; margin: 8px 0 12px; flex-wrap: wrap; font-size: 0.74rem; color: #a8b8d0; }
.status-legend-item { display: flex; align-items: center; gap: 6px; }
.legend-dot { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.legend-dot.dup { background: rgba(167,139,250,0.6); }
.legend-dot.new { background: rgba(134,239,172,0.6); }
.legend-dot.updated { background: rgba(252,211,77,0.6); }

.table-wrap { overflow: auto; border: 1px solid rgba(201,165,88,0.15); }

/* ── Month header rows (collapsible) ── */
.month-header td {
  cursor: pointer; user-select: none;
  position: relative;
}
.month-header.collapsed td::after { content: ' ▶'; opacity: 0.6; }
.month-header td::after { content: ' ▼'; opacity: 0.6; transition: transform 0.2s; }

/* ── Click tracking column ── */
.tl-click-col { text-align: center; padding: 8px 6px !important; }

/* ── Charts canvas containment ── */
.chart-card canvas { max-height: 280px; }


td.visits { color: #e0bb73; font-variant-numeric: tabular-nums; font-size: 0.82rem; }
.sub-count { color: #a8b8d0; opacity: 0.7; font-size: 0.78rem; margin-left: 3px; }

/* ── Kanto featured ── */
.kanto-featured {
  background: linear-gradient(135deg, rgba(201,165,88,0.12) 0%, rgba(20,38,67,0.7) 50%, rgba(201,165,88,0.08) 100%);
  border: 1.5px solid rgba(201,165,88,0.45);
  border-radius: 18px;
  padding: 28px 32px;
  margin-bottom: 28px;
  position: relative;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0,0,0,0.5), 0 4px 24px rgba(201,165,88,0.12), inset 0 1px 0 rgba(241,228,198,0.18);
}
.kanto-featured::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent 0%, #c9a558 25%, #f1e4c6 50%, #c9a558 75%, transparent 100%);
}
.kanto-banner { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.kanto-banner h2 {
  font-size: 1.45rem; font-weight: 300; letter-spacing: 0.12em; line-height: 1.2;
  background: linear-gradient(135deg, #f1e4c6 0%, #c9a558 50%, #f1e4c6 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.kanto-subtitle { color: #cbd5e1; font-size: 0.78rem; opacity: 0.85; letter-spacing: 0.04em; }
.kanto-badge { background: rgba(201,165,88,0.22); color: #f1e4c6; padding: 4px 12px; border-radius: 20px; font-size: 0.72rem; border: 1px solid rgba(201,165,88,0.5); letter-spacing: 0.06em; }
.kanto-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px; }
.kanto-card {
  display: block; background: linear-gradient(145deg, rgba(11,24,44,0.82), rgba(8,20,38,0.95));
  border: 1px solid rgba(201,165,88,0.22); border-radius: 12px; padding: 14px 16px;
  text-decoration: none; color: #e9d9b8; transition: all 0.2s; position: relative;
}
.kanto-card:hover {
  transform: translateY(-3px); border-color: #c9a558;
  box-shadow: 0 10px 28px rgba(201,165,88,0.22), 0 4px 16px rgba(0,0,0,0.4);
}
.kanto-card-date { color: #c9a558; font-size: 0.78rem; font-weight: 600; margin-bottom: 6px; letter-spacing: 0.06em; }
.kanto-card-title { color: #f1e4c6; font-size: 0.86rem; line-height: 1.45; margin-bottom: 10px; min-height: 2.6em; }
.kanto-card-meta { display: flex; gap: 10px; flex-wrap: wrap; font-size: 0.7rem; margin-bottom: 10px; }
.kanto-card-area { color: #93c5fd; }
.kanto-card-site { color: #a8b8d0; }
.kanto-card-foot { display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid rgba(201,165,88,0.14); }
.kanto-card-comp { color: #c9a558; font-weight: 600; font-variant-numeric: tabular-nums; font-size: 0.92rem; }
.kanto-card-spec { color: #a8b8d0; font-size: 0.72rem; }

/* ── Architecture / 仕組み ── */
.arch-section {
  background: linear-gradient(145deg, rgba(15,30,52,0.85), rgba(8,20,38,0.95));
  border: 1px solid rgba(201,165,88,0.18); border-radius: 14px;
  padding: 28px 32px; margin: 30px 0 24px;
  box-shadow: 0 6px 28px rgba(0,0,0,0.4);
}
.arch-section h2 {
  color: #c9a558; font-size: 1.1rem; font-weight: 500; letter-spacing: 0.12em;
  margin-bottom: 8px; padding-bottom: 12px; border-bottom: 1px solid rgba(201,165,88,0.2);
}
.arch-desc { color: #cbd5e1; font-size: 0.86rem; margin-bottom: 22px; line-height: 1.7; }
.arch-svg { width: 100%; height: auto; max-height: 720px; display: block; margin: 0 auto; }
.arch-note { color: #a8b8d0; font-size: 0.78rem; margin-top: 18px; padding: 14px 16px; background: rgba(8,20,38,0.6); border-left: 3px solid #c9a558; border-radius: 4px; line-height: 1.7; }

@media (max-width: 768px) {
  .kanto-featured { padding: 18px 16px; }
  .kanto-banner h2 { font-size: 1.15rem; }
  .kanto-grid { grid-template-columns: 1fr; }
  .arch-section { padding: 18px 16px; }
}


/* ── Mini calendar grid ── */
.tl-cal-wrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin: 14px 0 18px; }
.tl-cal { background: linear-gradient(145deg, rgba(8,20,38,0.65), rgba(15,30,52,0.8)); border: 1px solid rgba(201,165,88,0.22); border-radius: 12px; padding: 14px 12px 12px; }
.tl-cal-title { color: #c9a558; font-size: 0.86rem; font-weight: 700; letter-spacing: 0.12em; margin-bottom: 10px; text-align: center; padding-bottom: 8px; border-bottom: 1px solid rgba(201,165,88,0.18); }
.tl-cal-title .total { color: #a8b8d0; font-weight: 400; font-size: 0.74rem; margin-left: 8px; letter-spacing: 0.04em; }
.tl-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.tl-cal-head { font-size: 0.66rem; color: #7c8db5; text-align: center; padding: 4px 0 6px; letter-spacing: 0.06em; font-weight: 600; }
.tl-cal-head.sun { color: #fca5a5; }
.tl-cal-head.sat { color: #93c5fd; }
.tl-cal-day { font-size: 0.72rem; color: #4a5568; padding: 6px 0 4px; min-height: 38px; text-align: center; border-radius: 5px; position: relative; line-height: 1.1; }
.tl-cal-day.has-trials { background: rgba(201,165,88,0.18); color: #f1e4c6; cursor: pointer; transition: all 0.15s; border: 1px solid rgba(201,165,88,0.18); }
.tl-cal-day.has-trials:hover { background: rgba(201,165,88,0.45); transform: scale(1.05); border-color: #c9a558; box-shadow: 0 2px 8px rgba(201,165,88,0.3); }
.tl-cal-day.lvl-2 { background: rgba(201,165,88,0.30); }
.tl-cal-day.lvl-3 { background: rgba(201,165,88,0.48); border-color: rgba(201,165,88,0.4); }
.tl-cal-day.lvl-4 { background: rgba(201,165,88,0.68); border-color: rgba(241,228,198,0.5); color: #fff; }
.tl-cal-day.lvl-5 { background: rgba(241,228,198,0.88); border-color: #f1e4c6; color: #0a1c33; font-weight: 600; }
.tl-cal-day .cal-num { font-weight: 600; font-size: 0.78rem; }
.tl-cal-day .cal-count { font-size: 0.62rem; color: #c9a558; font-weight: 700; display: block; margin-top: 1px; letter-spacing: 0.04em; }
.tl-cal-day.lvl-4 .cal-count, .tl-cal-day.lvl-5 .cal-count { color: #0a1c33; }
.tl-cal-day .cal-dup { position: absolute; top: 3px; right: 4px; width: 6px; height: 6px; border-radius: 50%; background: #c4b5fd; box-shadow: 0 0 5px rgba(167,139,250,0.7); }
.tl-cal-day.today { outline: 2px solid #c9a558; outline-offset: -1px; }
.tl-cal-legend { display: flex; align-items: center; gap: 12px; margin-top: 10px; font-size: 0.7rem; color: #a8b8d0; flex-wrap: wrap; padding: 8px 4px 0; border-top: 1px solid rgba(201,165,88,0.12); }
.tl-cal-legend-scale { display: flex; align-items: center; gap: 4px; }
.tl-cal-legend-cell { width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(201,165,88,0.2); }
.tl-cal-legend-dot { width: 7px; height: 7px; border-radius: 50%; background: #c4b5fd; box-shadow: 0 0 4px rgba(167,139,250,0.6); }

@media (max-width: 768px) {
  .tl-cal-wrap { grid-template-columns: 1fr; }
  .tl-cal-day { min-height: 32px; font-size: 0.68rem; }
}


.kanto-card-rate { display: inline-block; margin-left: 6px; padding: 1px 6px; background: rgba(147,197,253,0.14); color: #93c5fd; border: 1px solid rgba(147,197,253,0.3); border-radius: 3px; font-size: 0.7rem; font-weight: 500; vertical-align: middle; }

.formula-note { margin: 4px 0 14px; padding: 8px 12px; background: rgba(8,20,38,0.55); border-left: 2px solid #c9a558; border-radius: 4px; }
.formula-note .formula { display: block; color: #f1e4c6; font-family: 'SF Mono', Menlo, monospace; font-size: 0.78rem; letter-spacing: 0.04em; margin-bottom: 3px; }
.formula-note .formula-desc { display: block; color: #a8b8d0; font-size: 0.7rem; line-height: 1.4; }

'''

# ──────────────────────── Build timeline HTML ────────────────────────
bar_colors = [
    'linear-gradient(180deg, #60a5fa, #3b82f6)',
    'linear-gradient(180deg, #818cf8, #6366f1)',
    'linear-gradient(180deg, #a78bfa, #8b5cf6)',
    'linear-gradient(180deg, #c084fc, #a855f7)',
    'linear-gradient(180deg, #e879f9, #d946ef)',
    'linear-gradient(180deg, #f472b6, #ec4899)',
]
max_count = max((len(v) for v in months.values()), default=1)

bar_items_html = ''
for i, (mk, mv) in enumerate(months.items()):
    height_pct = max(25, int(len(mv) / max_count * 100))
    bg = bar_colors[i % len(bar_colors)]
    short_label = mk.replace('2026年', '').replace('月', '')
    _bar_ymid = mv[0]['start_date'].strftime('%Y-%m') if mv and mv[0].get('start_date') else f'i{i}'
    bar_items_html += f'''<div class="tl-bar-item" onclick="document.getElementById('month-{_bar_ymid}')?.scrollIntoView({{behavior:'smooth',block:'center'}})">
      <div class="tl-bar-count">{len(mv)}</div>
      <div class="tl-bar-col" style="height:{height_pct}%;background:{bg};"></div>
      <div class="tl-bar-label">{short_label}月</div>
    </div>'''
if undated:
    height_pct = max(25, int(len(undated) / max_count * 100))
    bar_items_html += f'''<div class="tl-bar-item" onclick="document.getElementById('month-undated')?.scrollIntoView({{behavior:'smooth',block:'center'}})">
      <div class="tl-bar-count">{len(undated)}</div>
      <div class="tl-bar-col" style="height:{height_pct}%;background:linear-gradient(180deg, #64748b, #475569);"></div>
      <div class="tl-bar-label">未定</div>
    </div>'''

# Status legend
legend_html = '''<div class="status-legend">
      <div class="status-legend-item"><div class="legend-dot new"></div> 新規案件</div>
      <div class="status-legend-item"><div class="legend-dot updated"></div> 更新あり</div>
      <div class="status-legend-item"><div class="legend-dot dup"></div> 複数サイト重複</div>
    </div>''' if (new_count > 0 or updated_count > 0) else '''<div class="status-legend">
      <div class="status-legend-item"><div class="legend-dot dup"></div> 複数サイト重複</div>
    </div>'''

# Stats row - conditionally include new/updated counts
stat_new_html = f'''<div class="tl-stat">
        <span style="color:#7c8db5;">新規</span> <span class="num red">{new_count}件</span>
      </div>''' if new_count > 0 else ''
stat_upd_html = f'''<div class="tl-stat">
        <span style="color:#7c8db5;">更新</span> <span class="num orange">{updated_count}件</span>
      </div>''' if updated_count > 0 else ''

# Build mini calendar HTML for each month with trials
from calendar import monthrange as _monthrange
from collections import defaultdict as _defaultdict

_by_date = _defaultdict(list)
for _it in items:
    _d = _it.get('_start_date')
    if _d:
        _by_date[_d].append(_it)

_months_set = sorted(set((d.year, d.month) for d in _by_date.keys()))

def _level_for(n):
    if n <= 1: return ''
    if n <= 3: return 'lvl-2'
    if n <= 6: return 'lvl-3'
    if n <= 10: return 'lvl-4'
    return 'lvl-5'

_cal_blocks = []
for _y, _mn in _months_set:
    _first_wd, _ndays = _monthrange(_y, _mn)
    # Python weekday: Mon=0..Sun=6. Sunday-start grid: leading = (Mon-based + 1) % 7
    _leading = (_first_wd + 1) % 7
    _month_count = sum(1 for d in _by_date if d.year == _y and d.month == _mn)
    _cells = []
    for _ in range(_leading):
        _cells.append('<div class="tl-cal-day"></div>')
    for _day in range(1, _ndays + 1):
        _dt = date(_y, _mn, _day)
        _trials = _by_date.get(_dt, [])
        _wd_idx = (_first_wd + (_day - 1)) % 7
        _is_sun = _wd_idx == 6
        _is_sat = _wd_idx == 5
        _today_cls = ' today' if _dt == TODAY else ''
        if _trials:
            _n = len(_trials)
            _has_dup = any((it.get('source_count', 1) or 1) > 1 for it in _trials)
            _lvl = _level_for(_n)
            _cls = ('has-trials ' + _lvl).strip() + _today_cls
            _dup = '<span class="cal-dup" title="複数サイト重複あり"></span>' if _has_dup else ''
            _ymid = _dt.strftime('%Y-%m')
            _cells.append(f'<div class="tl-cal-day {_cls}" title="{_y}/{_mn}/{_day} {_n}件" onclick="calCellClick(\'{_ymid}\',\'{_dt.isoformat()}\')"><span class="cal-num">{_day}</span><span class="cal-count">{_n}件</span>{_dup}</div>')
        else:
            _color = ' style="color:#fca5a5;"' if _is_sun else (' style="color:#7c8db5;"' if _is_sat else '')
            _cells.append(f'<div class="tl-cal-day{_today_cls}"{_color}><span class="cal-num">{_day}</span></div>')
    _heads = '<div class="tl-cal-head sun">日</div><div class="tl-cal-head">月</div><div class="tl-cal-head">火</div><div class="tl-cal-head">水</div><div class="tl-cal-head">木</div><div class="tl-cal-head">金</div><div class="tl-cal-head sat">土</div>'
    _cal_blocks.append(f'<div class="tl-cal"><div class="tl-cal-title">{_y}年{_mn}月<span class="total">— {_month_count}日に予定</span></div><div class="tl-cal-grid">{_heads}{chr(10).join(_cells)}</div></div>')

_cal_html = '<div class="tl-cal-wrap">' + ''.join(_cal_blocks) + '</div>' if _cal_blocks else ''
_cal_legend_html = '''<div class="tl-cal-legend">
  <span style="color:#c9a558;font-weight:600;letter-spacing:0.06em;">凡例</span>
  <div class="tl-cal-legend-scale"><div class="tl-cal-legend-cell" style="background:rgba(201,165,88,0.18);"></div><span>1件</span></div>
  <div class="tl-cal-legend-scale"><div class="tl-cal-legend-cell" style="background:rgba(201,165,88,0.30);"></div><span>2-3件</span></div>
  <div class="tl-cal-legend-scale"><div class="tl-cal-legend-cell" style="background:rgba(201,165,88,0.48);"></div><span>4-6件</span></div>
  <div class="tl-cal-legend-scale"><div class="tl-cal-legend-cell" style="background:rgba(201,165,88,0.68);"></div><span>7-10件</span></div>
  <div class="tl-cal-legend-scale"><div class="tl-cal-legend-cell" style="background:rgba(241,228,198,0.88);"></div><span>11件以上</span></div>
  <div class="tl-cal-legend-scale" style="margin-left:12px;"><div class="tl-cal-legend-dot"></div><span>複数サイト重複あり</span></div>
</div>'''

html_parts = [f'''
  <!-- 入院日カレンダー v3 -->
  <div class="timeline-hero" id="timelineSection">
    <h3>📅 入院開始日カレンダー</h3>
    <div class="tl-stats">
      <div class="tl-stat">
        <span style="color:#7c8db5;">日付判明</span> <span class="num blue">{dated_count}件</span>
      </div>
      <div class="tl-stat">
        <span style="color:#7c8db5;">日付未定</span> <span class="num gray">{undated_count}件</span>
      </div>
      <div class="tl-stat">
        <span style="color:#7c8db5;">複数サイト重複</span> <span class="num purple">{multi_site_count}件</span>
      </div>
      {stat_new_html}
      {stat_upd_html}
    </div>
    <div class="tl-bar-wrap">{bar_items_html}</div>
    {_cal_html}
    {_cal_legend_html}
    {legend_html}
    <div class="table-wrap" style="max-height:55vh;border-radius:10px;">
      <table>
        <thead>
          <tr>
            <th style="width:90px;text-align:center;">入院開始日</th>
            <th>案件名</th>
            <th>掲載サイト</th>
            <th>地域</th>
            <th>負担軽減費</th>
            <th>入院</th>
            <th>通院</th>
            <th title="(報酬 − 通院×¥10,000 − 事前検査×¥3,000 − 事後検査×¥5,000) ÷ 入院泊数">1泊単価 ⓘ</th>
          </tr>
        </thead>
        <tbody>
''']

def build_row(e, date_html, date_class, hidden=False):
    title_esc = esc(e['title'][:80])
    status_html = status_badge(e['status'])
    tt_badges = trial_type_badges(e)
    ttype = derive_trial_type(e)
    classes = []
    if e['status'] == 'new': classes.append('row-new')
    elif e['status'] == 'updated': classes.append('row-updated')
    if hidden: classes.append('hidden')
    row_class = f' class="{" ".join(classes)}"' if classes else ''

    if e['source_count'] > 1:
        sites_html = ' '.join(f'<span class="badge badge-site">{esc(s)}</span>' for s in e['source_sites'])
        sites_html += f' <span class="badge badge-dup">{e["source_count"]}サイト重複</span>'
    else:
        sites_html = f'<span class="badge badge-site">{esc(e["site"])}</span>'

    inpatient_cell = build_inpatient_cell(e)
    outpatient_cell = build_outpatient_cell(e)

    _row_date = e['start_date'].strftime('%Y-%m-%d') if e.get('start_date') else ''
    _row_date_attr = f' data-row-date="{_row_date}"' if _row_date else ''
    return f'''        <tr{row_class} data-ttype="{ttype}"{_row_date_attr}>
          <td class="{date_class}">{date_html}</td>
          <td><a href="{esc(e['url'])}" target="_blank">{title_esc}</a>{tt_badges}{status_html}</td>
          <td>{sites_html}</td>
          <td><span class="badge badge-area">{esc(e['prefecture'])}</span></td>
          <td class="comp">{fmt_comp(e['compensation_num'])}</td>
          <td class="nights">{inpatient_cell}</td>
          <td class="visits">{outpatient_cell}</td>
          <td class="ppn">{fmt_ppn(daily_rate(e))}</td>
        </tr>
'''

for i, (month_label, entries) in enumerate(months.items()):
    is_expanded = (month_label == nearest_month)
    collapsed = '' if is_expanded else ' collapsed'
    is_past = all(e['start_date'] < TODAY for e in entries)
    badge_cls = 'month-badge past' if is_past else 'month-badge'
    new_in_month = sum(1 for e in entries if e['status'] == 'new')
    upd_in_month = sum(1 for e in entries if e['status'] == 'updated')
    extra = ''
    if new_in_month > 0:
        extra += f' <span class="badge badge-new">{new_in_month} NEW</span>'
    if upd_in_month > 0:
        extra += f' <span class="badge badge-updated">{upd_in_month} 更新</span>'

    _ymid = entries[0]['start_date'].strftime('%Y-%m') if entries and entries[0].get('start_date') else f'i{i}'
    html_parts.append(f'''        <tr class="month-header{collapsed}" id="month-{_ymid}" style="background:rgba(26,39,68,0.8);" onclick="this.classList.toggle('collapsed');let s=this.nextElementSibling;while(s&&!s.classList.contains('month-header')){{s.classList.toggle('hidden');s=s.nextElementSibling;}}">
          <td colspan="7"><span class="{badge_cls}">{month_label}</span><span class="month-count">{len(entries)}件</span>{extra}<span class="month-toggle">▼</span></td>
        </tr>
''')
    for e in entries:
        d_str = fmt_date(e['start_date'])
        if e['start_date'] < TODAY: dc = 'date-cell past'
        elif (e['start_date'] - TODAY).days <= 7: dc = 'date-cell soon'
        else: dc = 'date-cell future'
        html_parts.append(build_row(e, d_str, dc, hidden=not is_expanded))

if undated:
    new_in_und = sum(1 for e in undated if e['status'] == 'new')
    upd_in_und = sum(1 for e in undated if e['status'] == 'updated')
    extra_und = ''
    if new_in_und > 0: extra_und += f' <span class="badge badge-new">{new_in_und} NEW</span>'
    if upd_in_und > 0: extra_und += f' <span class="badge badge-updated">{upd_in_und} 更新</span>'

    html_parts.append(f'''        <tr class="month-header collapsed" id="month-undated" style="background:rgba(26,39,68,0.8);" onclick="this.classList.toggle('collapsed');let s=this.nextElementSibling;while(s&&!s.classList.contains('month-header')){{s.classList.toggle('hidden');s=s.nextElementSibling;}}">
          <td colspan="7"><span class="month-badge past">日付未定</span><span class="month-count">{len(undated)}件</span>{extra_und}<span class="month-toggle">▼</span></td>
        </tr>
''')
    for e in undated:
        html_parts.append(build_row(e, '未定', 'date-cell undated', hidden=True))

html_parts.append('''        </tbody>
      </table>
    </div>
  </div>
''')

timeline_html = ''.join(html_parts)

# ──────────────────────── Apply to dashboard ────────────────────────
with open(BASE_HTML_PATH, 'r') as f:
    dashboard = f.read()

# Replace CSS
import re as re_mod
css_match = re_mod.search(r'<style>\s*(.*?)\s*</style>', dashboard, re_mod.DOTALL)
if css_match:
    dashboard = dashboard[:css_match.start(1)] + NEW_CSS + dashboard[css_match.end(1):]
    print("Replaced CSS with gradient theme")

# Insert timeline before filters
insert_marker = '  <!-- Filters -->'
if insert_marker in dashboard:
    dashboard = dashboard.replace(insert_marker, '\n' + timeline_html + '\n' + insert_marker)
    print("Inserted timeline section")

# Fix sort JS: limit to #mainTable only
dashboard = dashboard.replace(
    "document.querySelectorAll('thead th').forEach(th => {\n  th.addEventListener('click', () => {",
    "document.querySelectorAll('#mainTable thead th').forEach(th => {\n  th.addEventListener('click', () => {"
)
dashboard = dashboard.replace(
    "document.querySelectorAll('thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));",
    "document.querySelectorAll('#mainTable thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));"
)
print("Fixed sort JS to #mainTable only")

# ──── Add PV/Click tracking KPIs ────
kpi_end = '    <div class="kpi"><div class="label">都道府県</div>'
if kpi_end in dashboard:
    idx = dashboard.index(kpi_end)
    end_idx = dashboard.index('</div>\n  </div>', idx)
    dashboard = dashboard[:end_idx] + '''</div>
    <div class="kpi" style="border-color:rgba(59,130,246,0.4);"><div class="label">📊 ダッシュボード PV</div><div class="value" id="kpiPv" style="background:linear-gradient(135deg,#60a5fa,#3b82f6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">—</div><div class="sub" id="kpiPvSub"></div></div>
    <div class="kpi" style="border-color:rgba(236,72,153,0.4);"><div class="label">👆 総クリック数</div><div class="value" id="kpiClicks" style="background:linear-gradient(135deg,#f472b6,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">—</div><div class="sub" id="kpiClicksSub"></div></div>
  </div>''' + dashboard[end_idx + len('</div>\n  </div>'):]
    print("Added PV/Click KPI cards")

# ──── Add click count header to mainTable ────
dashboard = dashboard.replace(
    '<th data-col="7" title="(報酬 − 通院×¥10,000 − 事前検査×¥3,000 − 事後検査×¥5,000) ÷ 入院泊数">1泊単価 ⓘ</th>',
    '<th data-col="7" title="(報酬 − 通院×¥10,000 − 事前検査×¥3,000 − 事後検査×¥5,000) ÷ 入院泊数">1泊単価 ⓘ</th>\n          <th data-col="8" style="text-align:center;width:70px;">👆</th>'
)
print("Added click column header to mainTable")

# ──── Add click tracking CSS ────
TRACKING_CSS = '''
/* Click tracking */
.click-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 28px; height: 22px; padding: 0 6px;
  border-radius: 12px; font-size: 0.72rem; font-weight: 700; text-align: center;
}
.click-count.zero { background: rgba(71,85,105,0.3); color: #64748b; }
.click-count.low { background: linear-gradient(135deg, rgba(59,130,246,0.25), rgba(99,102,241,0.2)); color: #93c5fd; }
.click-count.mid { background: linear-gradient(135deg, rgba(168,85,247,0.3), rgba(236,72,153,0.2)); color: #d8b4fe; }
.click-count.high { background: linear-gradient(135deg, rgba(239,68,68,0.3), rgba(249,115,22,0.2)); color: #fca5a5; animation: pulse-hot 2s ease-in-out infinite; }
@keyframes pulse-hot { 0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.3); } 50% { box-shadow: 0 0 6px 2px rgba(239,68,68,0.15); } }
a.unvisited { position: relative; }
a.unvisited::before { content: ''; display: inline-block; width: 6px; height: 6px; background: #3b82f6; border-radius: 50%; margin-right: 5px; vertical-align: middle; box-shadow: 0 0 4px rgba(59,130,246,0.5); }
.tl-click-col { text-align: center; width: 60px; }
'''
dashboard = dashboard.replace('@media (max-width: 768px)', TRACKING_CSS + '\n@media (max-width: 768px)')
print("Added click tracking CSS")

# ──── Add tracking JavaScript before </script> ────
TRACKING_JS = '''
// ═══════════════════════════════════════════
// PV & Click Tracking (localStorage)
// ═══════════════════════════════════════════
(function() {
  const STORAGE_KEY = 'chiken_tracker';
  function getData() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || { pv: 0, pvHistory: [], clicks: {} }; }
    catch(e) { return { pv: 0, pvHistory: [], clicks: {} }; }
  }
  function saveData(d) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(d)); } catch(e) {} }
  const data = getData();
  data.pv = (data.pv || 0) + 1;
  if (!data.pvHistory) data.pvHistory = [];
  const today = new Date().toISOString().slice(0, 10);
  const lastEntry = data.pvHistory[data.pvHistory.length - 1];
  if (lastEntry && lastEntry.date === today) { lastEntry.count++; }
  else { data.pvHistory.push({ date: today, count: 1 }); if (data.pvHistory.length > 90) data.pvHistory.shift(); }
  saveData(data);
  const kpiPv = document.getElementById('kpiPv');
  const kpiPvSub = document.getElementById('kpiPvSub');
  if (kpiPv) kpiPv.textContent = data.pv.toLocaleString();
  if (kpiPvSub) { const todayPv = data.pvHistory.find(e => e.date === today)?.count || 0; kpiPvSub.textContent = '本日 ' + todayPv + ' PV'; }
  const totalClicks = Object.values(data.clicks).reduce((s, c) => s + (c.count || 0), 0);
  const kpiClicks = document.getElementById('kpiClicks');
  const kpiClicksSub = document.getElementById('kpiClicksSub');
  if (kpiClicks) kpiClicks.textContent = totalClicks.toLocaleString();
  if (kpiClicksSub) { const cu = Object.keys(data.clicks).length; const allL = document.querySelectorAll('a[target="_blank"]'); const uu = new Set(); allL.forEach(a => uu.add(a.href)); kpiClicksSub.textContent = cu + '/' + uu.size + ' 件閲覧済'; }
  function getClickClass(c) { if (c === 0) return 'zero'; if (c <= 2) return 'low'; if (c <= 5) return 'mid'; return 'high'; }
  function renderBadge(c) { return '<span class="click-count ' + getClickClass(c) + '">' + c + '</span>'; }
  const mainTable = document.getElementById('mainTable');
  if (mainTable) { mainTable.querySelectorAll('tbody tr').forEach(row => { const link = row.querySelector('a[target="_blank"]'); const td = document.createElement('td'); td.style.textAlign = 'center'; if (link) { const cd = data.clicks[link.href] || { count: 0 }; td.innerHTML = renderBadge(cd.count); if (cd.count === 0) link.classList.add('unvisited'); } row.appendChild(td); }); }
  const tl = document.getElementById('timelineSection');
  if (tl) { const th = document.createElement('th'); th.textContent = '👆'; th.style.textAlign = 'center'; th.style.width = '60px'; th.style.cursor = 'default'; const tlTh = tl.querySelector('thead tr'); if (tlTh) tlTh.appendChild(th); tl.querySelectorAll('.month-header td[colspan]').forEach(td => { td.setAttribute('colspan', parseInt(td.getAttribute('colspan')) + 1); }); tl.querySelectorAll('tbody tr:not(.month-header)').forEach(row => { const link = row.querySelector('a[target="_blank"]'); const td = document.createElement('td'); td.className = 'tl-click-col'; if (link) { const cd = data.clicks[link.href] || { count: 0 }; td.innerHTML = renderBadge(cd.count); if (cd.count === 0) link.classList.add('unvisited'); } row.appendChild(td); }); }
  document.addEventListener('click', function(e) { const link = e.target.closest('a[target="_blank"]'); if (!link) return; const url = link.href; const d = getData(); if (!d.clicks[url]) d.clicks[url] = { count: 0, first: new Date().toISOString(), last: null }; d.clicks[url].count++; d.clicks[url].last = new Date().toISOString(); saveData(d); link.classList.remove('unvisited'); document.querySelectorAll('a[target="_blank"]').forEach(a => { if (a.href === url) { a.classList.remove('unvisited'); const tr = a.closest('tr'); if (tr) { const ct = tr.querySelector('.click-count')?.parentElement || tr.querySelector('.tl-click-col'); if (ct) ct.innerHTML = renderBadge(d.clicks[url].count); } } }); const tc = Object.values(d.clicks).reduce((s, c) => s + (c.count || 0), 0); const kc = document.getElementById('kpiClicks'); if (kc) kc.textContent = tc.toLocaleString(); const ks = document.getElementById('kpiClicksSub'); if (ks) { const cu2 = Object.keys(d.clicks).length; const allL2 = document.querySelectorAll('a[target="_blank"]'); const uu2 = new Set(); allL2.forEach(a => uu2.add(a.href)); ks.textContent = cu2 + '/' + uu2.size + ' 件閲覧済'; } });
})();
'''
dashboard = dashboard.replace('</script>\n</body>', TRACKING_JS + '</script>\n</body>')

TTAB_JS = '''
<script>
(function(){
  function applyFilter(t){
    document.querySelectorAll('#ttypeTabs .ttab').forEach(b => b.classList.toggle('active', b.dataset.ttype === t));
    document.querySelectorAll('#mainTable tbody tr').forEach(r => {
      const tt = r.dataset.ttype || '';
      r.style.display = (t === 'all' || tt === t) ? '' : 'none';
    });
    // Also filter timeline rows (skip month-header rows)
    document.querySelectorAll('#timelineSection tbody tr').forEach(r => {
      if (r.classList.contains('month-header')) return;
      const tt = r.dataset.ttype || '';
      // Don't fight the existing collapse/hidden logic; just add a separate ttype-hidden
      if (t === 'all' || tt === t) r.classList.remove('ttype-hidden');
      else r.classList.add('ttype-hidden');
    });
  }
  function init(){
    const tabs = document.getElementById('ttypeTabs');
    if (!tabs) return;
    tabs.addEventListener('click', e => {
      const b = e.target.closest('.ttab');
      if (!b) return;
      applyFilter(b.dataset.ttype);
    });
    // CSS for ttype-hidden (in case not in stylesheet)
    const s = document.createElement('style');
    s.textContent = '.ttype-hidden{display:none !important;}';
    document.head.appendChild(s);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
</script>
'''
dashboard = dashboard.replace('</script>\n</body>', '</script>\n' + TTAB_JS + '\n</body>')

CAL_JS = '''
<script>
(function(){
  window.calCellClick = function(ymid, dateStr) {
    const monthRow = document.getElementById('month-' + ymid);
    if (monthRow && monthRow.classList.contains('collapsed')) {
      monthRow.click();
    }
    setTimeout(function(){
      const target = document.querySelector('tr[data-row-date="' + dateStr + '"]');
      if (!target) {
        if (monthRow) monthRow.scrollIntoView({behavior: 'smooth', block: 'center'});
        return;
      }
      // 1) Scroll the inner table-wrap container so target is visible inside it
      const container = target.closest('.table-wrap');
      if (container) {
        const tRect = target.getBoundingClientRect();
        const cRect = container.getBoundingClientRect();
        const targetTopInContainer = (tRect.top - cRect.top) + container.scrollTop;
        container.scrollTo({ top: Math.max(0, targetTopInContainer - 40), behavior: 'auto' });
      }
      // 2) Smooth-scroll the page so timeline-hero is visible (after inner scroll completes)
      requestAnimationFrame(function(){
        const hero = document.getElementById('timelineSection');
        if (hero) {
          const heroRect = hero.getBoundingClientRect();
          const pageY = (heroRect.top + window.scrollY) - 40;
          window.scrollTo({ top: pageY, behavior: 'smooth' });
        }
        // Highlight all matching rows
        const all = document.querySelectorAll('tr[data-row-date="' + dateStr + '"]');
        all.forEach(function(r){
          r.classList.add('flash-highlight');
          setTimeout(function(){ r.classList.remove('flash-highlight'); }, 2400);
        });
      });
    }, 100);
  };
  // Inject highlight CSS
  const s = document.createElement('style');
  s.textContent = '@keyframes flashHL{0%,100%{background:rgba(201,165,88,0.04);}25%,75%{background:rgba(201,165,88,0.42);}50%{background:rgba(241,228,198,0.35);}} .flash-highlight td{animation:flashHL 1.2s ease-in-out 2;}';
  document.head.appendChild(s);
})();
</script>
'''
dashboard = dashboard.replace('</body>', CAL_JS + '\n</body>')



print("Added tracking JavaScript")

# ──────────────────────── Regenerate mainTable from data.json ────────────────────────
# Replace the existing mainTable tbody with fresh data
# Default sort for 全件: compensation_num descending (highest reward first)
_items_for_main = sorted(items, key=lambda x: -(x.get('compensation_num') or 0))
main_rows = []
for idx, item in enumerate(_items_for_main, 1):
    title_esc = esc(item.get('title', '')[:100])
    url = esc(item.get('url', ''))
    site = esc(item.get('site', ''))
    prefecture = esc(item.get('prefecture', '不明'))
    comp_num = item.get('compensation_num', 0)
    comp_str = f"¥{comp_num:,}" if comp_num > 0 else "—"
    total_n = item.get('total_nights', 0) or item.get('nights', 0)
    nights_str = f"{total_n}泊" if total_n else "—"
    _dr = daily_rate(item)
    ppn_str = f"¥{_dr:,}" if _dr else "—"
    status = item.get('_status', 'unchanged')
    status_html = status_badge(status)
    
    row_class_parts = ['item-row']
    if status == 'new': row_class_parts.append('row-new')
    elif status == 'updated': row_class_parts.append('row-updated')
    row_class = ' '.join(row_class_parts)
    
    # Multi-site badge
    if item.get('source_count', 1) > 1:
        sites_html = ' '.join(f'<span class="badge badge-site">{esc(s)}</span>' for s in item.get('source_sites', [site]))
        sites_html += f' <span class="badge badge-dup">{item["source_count"]}サイト重複</span>'
    else:
        sites_html = f'<span class="badge badge-site">{site}</span>'
    
    # Trial type info (uses fields if present, else derives from title)
    _ttype = derive_trial_type(item)
    _badges = trial_type_badges(item)
    _inpatient = build_inpatient_cell(item)
    _outpatient = build_outpatient_cell(item)

    main_rows.append(f"""        <tr class="{row_class}" data-site="{site}" data-area="{prefecture}" data-ttype="{_ttype}">
          <td>{idx}</td>
          <td><a href="{url}" target="_blank" rel="noopener">{title_esc}</a>{_badges}{status_html}</td>
          <td>{sites_html}</td>
          <td><span class="badge badge-area">{prefecture}</span></td>
          <td class="comp">{comp_str}</td>
          <td class="nights">{_inpatient}</td>
          <td class="visits">{_outpatient}</td>
          <td class="ppn">{ppn_str}</td>
        </tr>""")

# Build trial-type tabs with counts
_ttype_counts = {'all': len(items), '入院のみ': 0, '入院+通院': 0, '通院のみ': 0}
for _it in items:
    _tt = derive_trial_type(_it)
    if _tt in _ttype_counts:
        _ttype_counts[_tt] += 1
_tabs_html = (
    '<div class="trial-type-tabs" id="ttypeTabs">'
    f'<button class="ttab active" data-ttype="all">全件<span class="count">{_ttype_counts["all"]}</span></button>'
    f'<button class="ttab" data-ttype="入院のみ">入院のみ<span class="count">{_ttype_counts["入院のみ"]}</span></button>'
    f'<button class="ttab" data-ttype="入院+通院">入院+通院<span class="count">{_ttype_counts["入院+通院"]}</span></button>'
    f'<button class="ttab" data-ttype="通院のみ">通院のみ<span class="count">{_ttype_counts["通院のみ"]}</span></button>'
    '</div>'
)

new_main_html = f"""{_tabs_html}<table id="mainTable">
      <thead>
        <tr>
          <th data-col="0">#</th>
          <th data-col="1">案件名</th>
          <th data-col="2">サイト</th>
          <th data-col="3">地域</th>
          <th data-col="4">負担軽減費</th>
          <th data-col="5">入院</th>
          <th data-col="6">通院</th>
          <th data-col="7" title="(報酬 − 通院×¥10,000 − 事前検査×¥3,000 − 事後検査×¥5,000) ÷ 入院泊数">1泊単価 ⓘ</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(main_rows)}
      </tbody>
    </table>"""

# Remove 定員合計 KPI card (no useful data; user asked to remove)
import re as _rerm
dashboard = _rerm.sub(
    r'<div class="kpi"><div class="label">定員合計[^<]*</div><div class="value[^"]*"[^>]*>[^<]*</div></div>\s*',
    '', dashboard)
print('Removed 定員合計 KPI')

# Replace existing mainTable in dashboard HTML
main_table_re = re_mod.compile(r'<table[^>]*id="mainTable".*?</table>', re_mod.DOTALL)
if main_table_re.search(dashboard):
    dashboard = main_table_re.sub(new_main_html, dashboard, count=1)
    print(f"Regenerated mainTable with {len(items)} items")

# ──────────────────────── Regenerate KPI values from data.json ────────────────────────
comps = [i.get('compensation_num', 0) for i in items if i.get('compensation_num', 0) > 0]
avg_comp = int(sum(comps) / len(comps)) if comps else 0
max_comp = max(comps) if comps else 0
sites = set(i.get('site', '') for i in items if i.get('site', ''))
total_sites = len(sites)

# Update KPI values — matches actual base template labels
kpi_patterns = [
    (r'(<div class="label">総案件数</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', str(len(items))),
    (r'(<div class="label">対象サイト</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', str(total_sites)),
    (r'(<div class="label">平均負担軽減費</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', f'{avg_comp:,}円' if avg_comp else '—'),
    (r'(<div class="label">最高負担軽減費</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', f'{max_comp:,}円' if max_comp else '—'),
    # Fallback labels
    (r'(<div class="label">入院案件数</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', str(len(items))),
    (r'(<div class="label">報酬判明</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', str(len(comps))),
    (r'(<div class="label">平均報酬</div><div class="value[^"]*"[^>]*>)([^<]+)(</div>)', f'¥{avg_comp:,}' if avg_comp else '—'),
]
for pat, new_val in kpi_patterns:
    m = re_mod.search(pat, dashboard)
    if m:
        dashboard = dashboard[:m.start(2)] + new_val + dashboard[m.end(2):]

# ──────────────────────── Update header text ────────────────────────
updated_at_new = data.get('updated_at', '')
# 最終更新: XXX-XX-XX XX:XX:XX ｜ 全NNN件 ｜ NNサイト統合
header_pattern = r'(最終更新[:：]\s*)([\d\-\s:]+)(\s*[｜|]\s*全\s*)(\d+)(\s*件\s*[｜|]\s*)(\d+)(\s*サイト統合)'
def replace_header(m):
    return f"{m.group(1)}{updated_at_new or m.group(2)}{m.group(3)}{len(items)}{m.group(5)}{total_sites}{m.group(7)}"
dashboard = re_mod.sub(header_pattern, replace_header, dashboard, count=1)

# Also update "治験・モニター案件" → "治験入院案件"
dashboard = dashboard.replace('治験・モニター案件', '治験入院案件', 1)

# ──────────────────────── Regenerate charts dynamically (added) ────────────────────────
# Region grouping: prefix-match prefecture string to canonical region
_REGION_MAP = [
    ('北海道', '北海道'),
    ('青森県', '東北'), ('岩手県', '東北'), ('宮城県', '東北'), ('秋田県', '東北'), ('山形県', '東北'), ('福島県', '東北'),
    ('茨城県', '関東'), ('栃木県', '関東'), ('群馬県', '関東'), ('埼玉県', '関東'), ('千葉県', '関東'), ('東京都', '関東'), ('神奈川県', '関東'),
    ('新潟県', '中部'), ('富山県', '中部'), ('石川県', '中部'), ('福井県', '中部'), ('山梨県', '中部'), ('長野県', '中部'), ('岐阜県', '中部'), ('静岡県', '中部'), ('愛知県', '中部'),
    ('三重県', '関西'), ('滋賀県', '関西'), ('京都府', '関西'), ('大阪府', '関西'), ('兵庫県', '関西'), ('奈良県', '関西'), ('和歌山県', '関西'),
    ('鳥取県', '中国・四国'), ('島根県', '中国・四国'), ('岡山県', '中国・四国'), ('広島県', '中国・四国'), ('山口県', '中国・四国'),
    ('徳島県', '中国・四国'), ('香川県', '中国・四国'), ('愛媛県', '中国・四国'), ('高知県', '中国・四国'),
    ('福岡県', '九州・沖縄'), ('佐賀県', '九州・沖縄'), ('長崎県', '九州・沖縄'), ('熊本県', '九州・沖縄'), ('大分県', '九州・沖縄'), ('宮崎県', '九州・沖縄'), ('鹿児島県', '九州・沖縄'), ('沖縄県', '九州・沖縄'),
    # short forms / city-only
    ('東京', '関東'), ('横浜', '関東'), ('新宿', '関東'), ('港区', '関東'), ('渋谷', '関東'), ('品川', '関東'), ('墨田', '関東'), ('豊島', '関東'), ('台東', '関東'), ('浅草', '関東'), ('池袋', '関東'),
    ('大阪', '関西'), ('京都', '関西'), ('神戸', '関西'), ('奈良', '関西'),
    ('福岡', '九州・沖縄'), ('熊本', '九州・沖縄'), ('長崎', '九州・沖縄'),
    ('名古屋', '中部'), ('愛知', '中部'),
    ('札幌', '北海道'),
]

def _region_of(item):
    pref = item.get('prefecture', '') or ''
    title = item.get('title', '') or ''
    text = f"{pref} {title}"
    for needle, region in _REGION_MAP:
        if needle in text:
            return region
    return '不明'

# Build distributions
from collections import Counter as _Counter
_area_counts = _Counter(_region_of(it) for it in items)
_area_order = ['関東', '関西', '中部', '九州・沖縄', '中国・四国', '東北', '北海道', '不明']
_area_labels = [r for r in _area_order if _area_counts.get(r, 0) > 0]
_area_data = [_area_counts.get(r, 0) for r in _area_labels]

# Compensation buckets
_comp_buckets = [('〜5万', 0, 50000), ('5〜10万', 50000, 100000), ('10〜20万', 100000, 200000),
                 ('20〜50万', 200000, 500000), ('50万〜', 500000, 10**9)]
_comp_data = []
_comp_labels = []
_unknown = 0
for it in items:
    c = it.get('compensation_num', 0) or 0
    if c <= 0:
        _unknown += 1
for label, lo, hi in _comp_buckets:
    cnt = sum(1 for it in items if lo <= (it.get('compensation_num', 0) or 0) < hi)
    _comp_labels.append(label); _comp_data.append(cnt)
if _unknown > 0:
    _comp_labels.append('不明'); _comp_data.append(_unknown)

# Site distribution (sorted by count desc)
_site_counter = _Counter(it.get('site', '') for it in items if it.get('site'))
_site_pairs = _site_counter.most_common()
_site_labels = [s for s, _ in _site_pairs]
_site_data = [n for _, n in _site_pairs]

import json as _json
def _js(arr):
    return _json.dumps(arr, ensure_ascii=False)

# Replace each chart's `new Chart(...)` block via regex
_chart_replacers = [
    ('areaCtx', f"""new Chart(areaCtx, {{
  type: 'doughnut',
  data: {{
    labels: {_js(_area_labels)},
    datasets: [{{ data: {_js(_area_data)}, backgroundColor: ['#c9a558','#e0bb73','#93c5fd','#a78bfa','#86efac','#fcd34d','#f472b6','#a8b8d0'] }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'right', labels: {{ color: '#cbd5e1', font: {{ size: 11 }} }} }} }} }}
}});"""),
    ('compCtx', f"""new Chart(compCtx, {{
  type: 'bar',
  data: {{
    labels: {_js(_comp_labels)},
    datasets: [{{ label: '件数', data: {_js(_comp_data)}, backgroundColor: '#c9a558', borderColor: '#e0bb73', borderWidth: 1, borderRadius: 4 }}]
  }},
  options: {{ responsive: true, scales: {{ y: {{ ticks: {{ color: '#a8b8d0' }}, grid: {{ color: 'rgba(201,165,88,0.08)' }} }}, x: {{ ticks: {{ color: '#a8b8d0' }}, grid: {{ display: false }} }} }}, plugins: {{ legend: {{ display: false }} }} }}
}});"""),
    ('siteCtx', f"""new Chart(siteCtx, {{
  type: 'bar',
  data: {{
    labels: {_js(_site_labels)},
    datasets: [{{ label: '件数', data: {_js(_site_data)}, backgroundColor: '#93c5fd', borderColor: '#bfdbfe', borderWidth: 1, borderRadius: 4 }}]
  }},
  options: {{ indexAxis: 'y', responsive: true, scales: {{ x: {{ ticks: {{ color: '#a8b8d0' }}, grid: {{ color: 'rgba(201,165,88,0.08)' }} }}, y: {{ ticks: {{ color: '#a8b8d0', font: {{ size: 10 }} }}, grid: {{ display: false }} }} }}, plugins: {{ legend: {{ display: false }} }} }}
}});"""),
]

import re as _re
for ctx_name, new_block in _chart_replacers:
    pat = _re.compile(rf"new Chart\({ctx_name},\s*\{{[\s\S]*?\}}\)\s*;", _re.MULTILINE)
    new_dashboard, n = pat.subn(new_block, dashboard, count=1)
    if n:
        dashboard = new_dashboard
        print(f"Updated chart {ctx_name}")
    else:
        print(f"WARN: chart {ctx_name} pattern not found")

# Remove catChart: drop its <canvas> wrapper card and JS block
dashboard = _re.sub(
    r'<div class="chart-card">\s*<h3>カテゴリ別 案件数</h3>\s*<canvas id="catChart"></canvas>\s*</div>',
    '', dashboard)
dashboard = _re.sub(
    r"const catCtx = document\.getElementById\('catChart'\)\.getContext\('2d'\);\s*new Chart\(catCtx,\s*\{[\s\S]*?\}\)\s*;",
    '', dashboard)
print("Removed catChart card + JS")

# ──────────────────────── Kanto featured + Architecture ────────────────────────
def _is_kanto(item):
    pref = (item.get('prefecture') or '')
    title = (item.get('title') or '')
    text = pref + ' ' + title
    keys = ('東京', '墨田', '港区', '新宿', '渋谷', '台東', '豊島', '品川',
            '埼玉', '千葉', '神奈川', '横浜', '茨城', '栃木', '群馬',
            '上野', '浅草', '池袋', '関東', '都内')
    return any(k in text for k in keys)

_kanto_items = [it for it in items if _is_kanto(it)]
_kanto_items = sorted(_kanto_items, key=lambda x: x.get('_start_date') or date.today())

_kanto_cards = []
for _it in _kanto_items[:18]:
    _d = _it.get('_start_date')
    _wd = ['月','火','水','木','金','土','日']
    _d_str = f"{_d.month}/{_d.day}({_wd[_d.weekday()]})" if _d else '日付未定'
    _title = esc((_it.get('title') or '')[:60])
    _url = esc(_it.get('url') or '')
    _pref = esc(_it.get('prefecture') or '')
    _site = esc(_it.get('site') or '')
    _comp = _it.get('compensation_num', 0) or 0
    _comp_str = f'¥{_comp:,}' if _comp else '—'
    _dr = daily_rate(_it)
    _dr_str = f'<span class="kanto-card-rate">¥{_dr:,}/日</span>' if _dr else ''
    _n = _it.get('total_nights', 0) or 0
    _oc = _it.get('outpatient_count', 0) or extract_outpatient_count(_it.get('title',''))
    _spec = []
    if _n: _spec.append(f'🏥 {_n}泊')
    if _oc: _spec.append(f'🚶 通院{_oc}回')
    _spec_html = ' / '.join(_spec) if _spec else ''
    _kanto_cards.append(f"""<a class="kanto-card" href="{_url}" target="_blank" rel="noopener">
      <div class="kanto-card-date">{_d_str}</div>
      <div class="kanto-card-title">{_title}</div>
      <div class="kanto-card-meta">
        <span class="kanto-card-area">📍 {_pref}</span>
        <span class="kanto-card-site">{_site}</span>
      </div>
      <div class="kanto-card-foot">
        <span class="kanto-card-comp">{_comp_str}{_dr_str}</span>
        <span class="kanto-card-spec">{_spec_html}</span>
      </div>
    </a>""")

_kanto_html = f"""<div class="kanto-featured">
  <div class="kanto-banner">
    <div>
      <h2>🌟 関東エリア特集</h2>
      
    </div>
    <div class="kanto-badge">全 {len(_kanto_items)} 件</div>
  </div>
  <div class="kanto-grid">
    {chr(10).join(_kanto_cards)}
  </div>
</div>
"""

# Inject Kanto featured BEFORE charts-grid
dashboard = dashboard.replace('<div class="charts-grid">', _kanto_html + '<div class="charts-grid">', 1)
print(f"Inserted Kanto featured ({len(_kanto_items)} items)")

# Architecture diagram (SVG flow)
_arch_html = """<div class="arch-section">
  <h2>🛠️ このダッシュボードの仕組み</h2>
  <p class="arch-desc">毎週月曜の朝9時、コンピュータが自動で10サイトの治験募集ページを巡回して情報を集め、見やすい一覧ページを作成します。あなたは何もしなくてOK。Slackに「更新しました」とURLが届きます。</p>
  <svg class="arch-svg" viewBox="0 0 820 720" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arrowGold" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto">
        <path d="M0,0 L0,8 L10,4 z" fill="#c9a558"/>
      </marker>
      <linearGradient id="boxGold" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="rgba(201,165,88,0.22)"/>
        <stop offset="100%" stop-color="rgba(201,165,88,0.08)"/>
      </linearGradient>
      <linearGradient id="boxNavy" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="rgba(20,38,67,0.85)"/>
        <stop offset="100%" stop-color="rgba(11,24,44,0.95)"/>
      </linearGradient>
      <linearGradient id="boxBlue" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="rgba(147,197,253,0.18)"/>
        <stop offset="100%" stop-color="rgba(147,197,253,0.06)"/>
      </linearGradient>
    </defs>

    <!-- Step 1: 治験サイト10社 -->
    <g>
      <rect x="60" y="30" width="700" height="100" rx="14" fill="url(#boxNavy)" stroke="rgba(201,165,88,0.45)" stroke-width="1.5"/>
      <circle cx="100" cy="60" r="18" fill="#c9a558"/>
      <text x="100" y="66" fill="#0a1c33" font-size="18" font-weight="700" text-anchor="middle">1</text>
      <text x="135" y="62" fill="#f1e4c6" font-size="16" font-weight="500">📋 治験募集サイト  10社</text>
      <text x="100" y="100" fill="#a8b8d0" font-size="12">生活向上WEB ・ JCVN ・ 治験ジャパン ・ ニューイング ・ ぺいるーと</text>
      <text x="100" y="118" fill="#a8b8d0" font-size="12">治験ネット ・ 治験バンク ・ 治験ウェブ ・ 治験情報V-NET ・ ボランティアサーチ</text>
    </g>
    <line x1="410" y1="135" x2="410" y2="170" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>
    <text x="430" y="158" fill="#c9a558" font-size="12" font-weight="500">📅 毎週月曜  朝9時に自動実行</text>

    <!-- Step 2: scraper -->
    <g>
      <rect x="160" y="180" width="500" height="84" rx="14" fill="url(#boxGold)" stroke="#c9a558" stroke-width="1.5"/>
      <circle cx="200" cy="210" r="18" fill="#c9a558"/>
      <text x="200" y="216" fill="#0a1c33" font-size="18" font-weight="700" text-anchor="middle">2</text>
      <text x="235" y="212" fill="#f1e4c6" font-size="16" font-weight="500">🤖 自動巡回 (scraper.py)</text>
      <text x="200" y="244" fill="#a8b8d0" font-size="12">案件名・開始日・報酬額・入院/通院回数を抽出</text>
    </g>
    <line x1="410" y1="265" x2="410" y2="300" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>

    <!-- Step 3: data.json -->
    <g>
      <rect x="160" y="310" width="500" height="84" rx="14" fill="url(#boxNavy)" stroke="rgba(147,197,253,0.4)" stroke-width="1.5"/>
      <circle cx="200" cy="340" r="18" fill="#93c5fd"/>
      <text x="200" y="346" fill="#0a1c33" font-size="18" font-weight="700" text-anchor="middle">3</text>
      <text x="235" y="342" fill="#f1e4c6" font-size="16" font-weight="500">💾 データ統合 (data.json)</text>
      <text x="200" y="374" fill="#a8b8d0" font-size="12">サイト間重複を排除 ・ 地域名を整形 ・ 入院/通院を分類</text>
    </g>
    <line x1="410" y1="395" x2="410" y2="430" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>

    <!-- Step 4: dashboard generation -->
    <g>
      <rect x="160" y="440" width="500" height="84" rx="14" fill="url(#boxGold)" stroke="#c9a558" stroke-width="1.5"/>
      <circle cx="200" cy="470" r="18" fill="#c9a558"/>
      <text x="200" y="476" fill="#0a1c33" font-size="18" font-weight="700" text-anchor="middle">4</text>
      <text x="235" y="472" fill="#f1e4c6" font-size="16" font-weight="500">🎨 ダッシュボード生成</text>
      <text x="200" y="504" fill="#a8b8d0" font-size="12">関東特集・タイムライン・グラフ・タブを組み立て (index.html)</text>
    </g>
    <line x1="410" y1="525" x2="410" y2="560" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>

    <!-- Step 5: GitHub Pages -->
    <g>
      <rect x="160" y="570" width="500" height="84" rx="14" fill="url(#boxBlue)" stroke="rgba(147,197,253,0.5)" stroke-width="1.5"/>
      <circle cx="200" cy="600" r="18" fill="#93c5fd"/>
      <text x="200" y="606" fill="#0a1c33" font-size="18" font-weight="700" text-anchor="middle">5</text>
      <text x="235" y="602" fill="#f1e4c6" font-size="16" font-weight="500">🌐 GitHub Pages で公開</text>
      <text x="200" y="634" fill="#a8b8d0" font-size="11">https://atsushisugamo-gif.github.io/chiken-dashboard/</text>
    </g>

    <!-- Final user + Slack -->
    <line x1="270" y1="654" x2="200" y2="688" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>
    <line x1="550" y1="654" x2="620" y2="688" stroke="#c9a558" stroke-width="2.5" marker-end="url(#arrowGold)"/>
    <text x="200" y="710" fill="#f1e4c6" font-size="14" text-anchor="middle">👀 ブラウザで閲覧</text>
    <text x="620" y="710" fill="#f1e4c6" font-size="14" text-anchor="middle">📱 Slack で通知</text>
  </svg>
  <div class="arch-note">
    <strong style="color:#c9a558;">💡 ポイント:</strong> あなたは Slack 通知を見て URL をタップするだけ。データの取得・集計・整形・公開はすべて自動。1サイトずつ手動で見て回る必要が無くなります。手作業だと約30分かかる作業が、毎週同じ品質で自動的に届きます。
  </div>
</div>
"""

# Architecture diagram is now a separate file (architecture.html / architecture.png)
# (intentionally NOT injecting into dashboard)
print("Architecture: separate file (skipped dashboard injection)")


# ──────────────────────── 地域別 1泊単価 (added) ────────────────────────
def _region_for_chart(it):
    """Bucket items into chart regions, splitting 東京 out from rest of 関東."""
    pref = (it.get('prefecture') or '') or ''
    title = (it.get('title') or '') or ''
    text = pref + ' ' + title
    # Tokyo first (highlighted)
    if any(k in text for k in ('東京', '墨田', '新宿', '渋谷', '港区', '台東', '豊島', '品川', '浅草', '池袋', '上野', '都内')):
        return '東京'
    if any(k in text for k in ('神奈川', '横浜', '川崎', '埼玉', '上尾', '越谷', '千葉', '茨城', '栃木', '群馬', '関東')):
        return '関東(その他)'
    if any(k in text for k in ('大阪', '京都', '神戸', '兵庫', '奈良', '滋賀', '和歌山', '関西')):
        return '関西'
    if any(k in text for k in ('福岡', '熊本', '鹿児島', '長崎', '佐賀', '大分', '宮崎', '沖縄', '九州')):
        return '九州・沖縄'
    if any(k in text for k in ('愛知', '名古屋', '静岡', '岐阜', '三重', '新潟', '富山', '石川', '福井', '長野', '山梨')):
        return '中部'
    if any(k in text for k in ('北海道', '札幌', '清田', '厚別')):
        return '北海道'
    if any(k in text for k in ('広島', '岡山', '島根', '鳥取', '山口', '香川', '愛媛', '徳島', '高知')):
        return '中国・四国'
    if any(k in text for k in ('青森', '秋田', '岩手', '山形', '宮城', '福島', '東北', '仙台')):
        return '東北'
    return 'その他'

_ppn_by_region = {}
for _it in items:
    if is_at_home_trial(_it):
        continue
    _title = _it.get('title','') or ''
    _n = _it.get('total_nights') or _it.get('nights') or 0
    _oc = _it.get('outpatient_count')
    if _oc is None:
        _oc = extract_outpatient_count(_title)
    _pre  = extract_pre_check_count(_title)
    _post = extract_post_check_count(_title)
    _comp = _it.get('compensation_num', 0) or 0
    if not _n or _comp <= 0:
        continue
    _inpatient_comp = (_comp
                       - (_oc or 0) * OUTPATIENT_FEE
                       - _pre * PRE_CHECK_FEE
                       - _post * POST_CHECK_FEE)
    if _inpatient_comp <= 0:
        continue
    _r = _region_for_chart(_it)
    _ppn_by_region.setdefault(_r, {'comp': 0, 'nights': 0, 'count': 0})
    _ppn_by_region[_r]['comp'] += _inpatient_comp
    _ppn_by_region[_r]['nights'] += _n
    _ppn_by_region[_r]['count'] += 1

# Weighted average: total inpatient_comp / total nights
_ppn_avg = [(r, int(v['comp'] / v['nights']) if v['nights'] > 0 else 0, v['count']) for r, v in _ppn_by_region.items()]
_ppn_avg = [(r, a, n) for r, a, n in _ppn_avg if n >= 1]
_ppn_avg.sort(key=lambda x: -x[1])

_ppn_labels = [f'{r} (n={n})' for r, _, n in _ppn_avg]
_ppn_data = [a for _, a, _ in _ppn_avg]
# Tokyo bar in gold, others in muted blue
_ppn_colors = ['#c9a558' if r == '東京' else '#6b8db8' for r, _, _ in _ppn_avg]
_ppn_borders = ['#f1e4c6' if r == '東京' else '#93c5fd' for r, _, _ in _ppn_avg]

_ppn_chart_card = """    <div class="chart-card">
      <h3>地域別 1泊単価 — 東京 強調</h3>
      <div class="formula-note">
        <span class="formula">(報酬 − 通院×¥10K − 事前検査×¥3K − 事後検査×¥5K) ÷ 入院泊数</span>
        <span class="formula-desc">通院費・検査費を分離した純粋な泊単価（地域の加重平均）。<br>通院/通所/来院/来所=¥10,000 ・ 事前検査=¥3,000 ・ 事後検査=¥5,000 で控除。</span>
      </div>
      <canvas id="ppnChart"></canvas>
    </div>"""

_ppn_chart_js = f"""const ppnCtx = document.getElementById('ppnChart').getContext('2d');
new Chart(ppnCtx, {{
  type: 'bar',
  data: {{
    labels: {_json.dumps(_ppn_labels, ensure_ascii=False)},
    datasets: [{{
      label: '1泊単価 (¥/泊・通院費控除後)',
      data: {_json.dumps(_ppn_data)},
      backgroundColor: {_json.dumps(_ppn_colors)},
      borderColor: {_json.dumps(_ppn_borders)},
      borderWidth: 1.5, borderRadius: 4
    }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true,
    scales: {{
      x: {{ ticks: {{ color: '#a8b8d0', callback: function(v){{ return '¥' + v.toLocaleString(); }} }}, grid: {{ color: 'rgba(201,165,88,0.08)' }} }},
      y: {{ ticks: {{ color: '#e9d9b8', font: {{ size: 11 }} }}, grid: {{ display: false }} }}
    }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: function(ctx){{ return '¥' + ctx.parsed.x.toLocaleString() + ' / 泊'; }} }} }}
    }}
  }}
}});"""

# Inject the new chart card BEFORE the サイト別 案件数 card
dashboard = dashboard.replace('<div class="chart-card">\n      <h3>サイト別 案件数</h3>',
                              _ppn_chart_card + '\n    <div class="chart-card">\n      <h3>サイト別 案件数</h3>', 1)
# Inject the new Chart() JS BEFORE the siteCtx Chart code
dashboard = dashboard.replace("const siteCtx = document.getElementById('siteChart')",
                              _ppn_chart_js + "\n\nconst siteCtx = document.getElementById('siteChart')", 1)

print(f"Added PPN chart with {len(_ppn_avg)} regions: {[r for r,_,_ in _ppn_avg]}")

# ──────────────────────── 簡易閲覧パスワードゲート (Plan B) ────────────────────────
# 同フォルダの auth-gate.js を読み込ませる <script> タグを <head> に注入。
# パスワード本体は auth-gate.js の AUTH_PASSWORD で管理する（ここでは扱わない）。
_AUTH_GATE_TAG = '<script src="auth-gate.js"></script>\n'
if _AUTH_GATE_TAG.strip() not in dashboard:
    if '</title>' in dashboard:
        dashboard = dashboard.replace('</title>', '</title>\n' + _AUTH_GATE_TAG, 1)
        print("Injected auth-gate.js <script> tag after <title>")
    else:
        print("WARNING: <title> not found, auth-gate.js was not injected")

# ──────────────────────── Write outputs ────────────────────────
with open(OUT_DASHBOARD, 'w') as f:
    f.write(dashboard)
with open(OUT_INDEX, 'w') as f:
    f.write(dashboard)

print(f"\n✅ Output written to:")
print(f"   {OUT_DASHBOARD} ({len(dashboard):,} bytes)")
print(f"   {OUT_INDEX}")
print(f"\nStats:")
print(f"  Dated: {dated_count}, Undated: {undated_count}")
print(f"  New: {new_count}, Updated: {updated_count}")
for mk, mv in months.items():
    nn = sum(1 for e in mv if e['status']=='new')
    uu = sum(1 for e in mv if e['status']=='updated')
    print(f"    {mk}: {len(mv)}件 (new:{nn} upd:{uu})")
