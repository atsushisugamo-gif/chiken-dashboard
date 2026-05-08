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

# ──────────────────────── Trial type helpers (added) ────────────────────────
def extract_outpatient_count(title):
    """Extract total 通院/通所/来院 count from title (for backward compat)."""
    if not title:
        return 0
    n = 0
    for m in re.finditer(r'通院\s*(\d+)\s*回?|(\d+)\s*通院\s*回?|通所\s*(\d+)\s*回?|来院\s*(\d+)\s*回?', title):
        n += next((int(g) for g in m.groups() if g), 0)
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
def extract_date(title):
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

# Filter: keep only trials starting today or later (drop past + undated)
_before_filter = len(items)
items = [it for it in items if it.get('_start_date') and it['_start_date'] >= TODAY]
print(f"Date filter: {_before_filter} -> {len(items)} items (kept future-starting only)")

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
    bar_items_html += f'''<div class="tl-bar-item" onclick="document.getElementById('month-{i}')?.scrollIntoView({{behavior:'smooth',block:'center'}})">
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
            <th>1泊単価</th>
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

    return f'''        <tr{row_class} data-ttype="{ttype}">
          <td class="{date_class}">{date_html}</td>
          <td><a href="{esc(e['url'])}" target="_blank">{title_esc}</a>{tt_badges}{status_html}</td>
          <td>{sites_html}</td>
          <td><span class="badge badge-area">{esc(e['prefecture'])}</span></td>
          <td class="comp">{fmt_comp(e['compensation_num'])}</td>
          <td class="nights">{inpatient_cell}</td>
          <td class="visits">{outpatient_cell}</td>
          <td class="ppn">{fmt_ppn(e['price_per_night'])}</td>
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

    html_parts.append(f'''        <tr class="month-header{collapsed}" id="month-{i}" style="background:rgba(26,39,68,0.8);" onclick="this.classList.toggle('collapsed');let s=this.nextElementSibling;while(s&&!s.classList.contains('month-header')){{s.classList.toggle('hidden');s=s.nextElementSibling;}}">
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
    '<th data-col="7">1泊単価</th>',
    '<th data-col="7">1泊単価</th>\n          <th data-col="8" style="text-align:center;width:70px;">👆</th>'
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


print("Added tracking JavaScript")

# ──────────────────────── Regenerate mainTable from data.json ────────────────────────
# Replace the existing mainTable tbody with fresh data
main_rows = []
for idx, item in enumerate(items, 1):
    title_esc = esc(item.get('title', '')[:100])
    url = esc(item.get('url', ''))
    site = esc(item.get('site', ''))
    prefecture = esc(item.get('prefecture', '不明'))
    comp_num = item.get('compensation_num', 0)
    comp_str = f"¥{comp_num:,}" if comp_num > 0 else "—"
    total_n = item.get('total_nights', 0) or item.get('nights', 0)
    nights_str = f"{total_n}泊" if total_n else "—"
    ppn = item.get('price_per_night', 0)
    ppn_str = f"¥{ppn:,}" if ppn else "—"
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
          <th data-col="7">1泊単価</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(main_rows)}
      </tbody>
    </table>"""

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
