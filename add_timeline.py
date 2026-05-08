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

# ──────────────────────── Build timeline data ────────────────────────
timeline_items = []
for item in items:
    timeline_items.append({
        'title': item['title'],
        'url': item['url'],
        'prefecture': item.get('prefecture', '不明'),
        'compensation_num': item.get('compensation_num', 0),
        'nights': item.get('total_nights') or item.get('nights'),
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
  font-family: -apple-system, 'Segoe UI', 'Hiragino Kaku Gothic ProN', 'Yu Gothic', sans-serif;
  background: linear-gradient(160deg, #0a0e27 0%, #0f1b3d 30%, #141230 60%, #0d0f1a 100%);
  background-attachment: fixed;
  color: #e2e8f0;
  line-height: 1.6;
  min-height: 100vh;
}

.header {
  background: linear-gradient(135deg, rgba(59,130,246,0.15) 0%, rgba(139,92,246,0.12) 50%, rgba(236,72,153,0.08) 100%);
  backdrop-filter: blur(12px);
  padding: 20px 32px;
  border-bottom: 1px solid rgba(139,92,246,0.25);
  display: flex; justify-content: space-between; align-items: center;
}
.header h1 {
  font-size: 1.3rem;
  background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.header .meta { color: #7c8db5; font-size: 0.8rem; }
.container { max-width: 1440px; margin: 0 auto; padding: 20px; }

/* KPI Cards */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
.kpi {
  background: linear-gradient(145deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9));
  border-radius: 12px; padding: 16px;
  border: 1px solid rgba(100,116,139,0.2);
  backdrop-filter: blur(8px);
  transition: transform 0.2s, border-color 0.2s;
}
.kpi:hover { transform: translateY(-2px); border-color: rgba(139,92,246,0.4); }
.kpi .label { font-size: 0.72rem; color: #7c8db5; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi .value { font-size: 1.7rem; font-weight: 700; color: #60a5fa; margin-top: 2px; }
.kpi .value.green { color: #4ade80; }
.kpi .value.amber { background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.kpi .value.purple { background: linear-gradient(135deg, #a78bfa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.kpi .sub { font-size: 0.72rem; color: #7c8db5; margin-top: 2px; }

/* Section */
.section {
  background: linear-gradient(145deg, rgba(30,41,59,0.7), rgba(15,23,42,0.8));
  border-radius: 12px; padding: 18px;
  border: 1px solid rgba(100,116,139,0.2);
  margin-bottom: 16px;
  backdrop-filter: blur(8px);
}
.section h3 { font-size: 0.95rem; color: #f1f5f9; margin-bottom: 12px; border-bottom: 1px solid rgba(100,116,139,0.2); padding-bottom: 8px; }

/* Charts */
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.chart-card {
  background: linear-gradient(145deg, rgba(30,41,59,0.7), rgba(15,23,42,0.8));
  border-radius: 12px; padding: 16px;
  border: 1px solid rgba(100,116,139,0.2);
  backdrop-filter: blur(8px);
}
.chart-card h3 { font-size: 0.9rem; color: #f1f5f9; margin-bottom: 10px; }
canvas { max-height: 260px; }

/* Stats Table */
.stats-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.stats-table th { background: linear-gradient(135deg, rgba(51,65,85,0.8), rgba(30,41,59,0.8)); color: #94a3b8; padding: 8px 12px; text-align: center; font-weight: 600; }
.stats-table td { padding: 8px 12px; border-bottom: 1px solid rgba(41,53,72,0.5); text-align: center; }
.stats-table tr:hover { background: rgba(59,130,246,0.08); }

/* Filters */
.filters {
  background: linear-gradient(145deg, rgba(30,41,59,0.7), rgba(15,23,42,0.8));
  border-radius: 12px; padding: 12px 16px; margin-bottom: 14px;
  border: 1px solid rgba(100,116,139,0.2);
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  backdrop-filter: blur(8px);
}
.filters label { color: #7c8db5; font-size: 0.8rem; }
.filters select, .filters input { background: rgba(15,23,42,0.8); color: #e2e8f0; border: 1px solid rgba(71,85,105,0.5); border-radius: 6px; padding: 6px 10px; font-size: 0.82rem; }
.filters input { width: 220px; }
.result-count { margin-left: auto; color: #7c8db5; font-size: 0.8rem; }

/* Table */
.table-wrap {
  background: linear-gradient(145deg, rgba(30,41,59,0.6), rgba(15,23,42,0.7));
  border-radius: 12px; overflow: auto;
  border: 1px solid rgba(100,116,139,0.2); max-height: 70vh;
}
table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
thead th {
  background: linear-gradient(135deg, rgba(51,65,85,0.9), rgba(30,41,59,0.9));
  color: #94a3b8; padding: 10px 12px; text-align: left; font-weight: 600;
  position: sticky; top: 0; cursor: default; white-space: nowrap; z-index: 1;
}
#mainTable thead th { cursor: pointer; }
#mainTable thead th:hover { color: #e2e8f0; }
#mainTable thead th.sorted-asc::after { content: ' ▲'; font-size: 0.7rem; }
#mainTable thead th.sorted-desc::after { content: ' ▼'; font-size: 0.7rem; }
tbody td { padding: 8px 12px; border-bottom: 1px solid rgba(30,41,59,0.5); }
tbody tr { background: transparent; transition: background 0.2s; }
tbody tr:hover { background: rgba(59,130,246,0.08); }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; color: #93c5fd; }
.badge { display: inline-block; padding: 2px 7px; border-radius: 5px; font-size: 0.7rem; font-weight: 500; }
.badge-area { background: linear-gradient(135deg, rgba(30,58,95,0.8), rgba(30,64,115,0.6)); color: #7dd3fc; }
.badge-site { background: linear-gradient(135deg, rgba(28,56,41,0.8), rgba(20,70,45,0.6)); color: #86efac; }
.badge-dup { background: linear-gradient(135deg, rgba(74,29,94,0.8), rgba(88,28,135,0.6)); color: #d8b4fe; margin-left: 6px; }
.badge-new {
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff; font-weight: 700; font-size: 0.65rem;
  padding: 2px 8px; border-radius: 4px; margin-left: 6px;
  animation: pulse-new 2s ease-in-out infinite;
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}
.badge-updated {
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  color: #fff; font-weight: 700; font-size: 0.65rem;
  padding: 2px 8px; border-radius: 4px; margin-left: 6px;
  animation: pulse-upd 2.5s ease-in-out infinite;
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}
@keyframes pulse-new {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.5); }
  50% { box-shadow: 0 0 8px 3px rgba(239,68,68,0.3); }
}
@keyframes pulse-upd {
  0%, 100% { box-shadow: 0 0 0 0 rgba(139,92,246,0.5); }
  50% { box-shadow: 0 0 8px 3px rgba(139,92,246,0.3); }
}
tr.row-new { border-left: 3px solid #ef4444; }
tr.row-updated { border-left: 3px solid #8b5cf6; }

.comp { font-weight: 600; color: #fbbf24; white-space: nowrap; }
.ppn { font-weight: 600; color: #34d399; white-space: nowrap; }
.nights { color: #94a3b8; white-space: nowrap; }
.error-box { background: rgba(69,26,3,0.8); border: 1px solid #78350f; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; color: #fbbf24; font-size: 0.82rem; }
.hidden { display: none; }

/* Timeline Calendar */
.timeline-hero {
  background: linear-gradient(135deg, rgba(30,58,95,0.6) 0%, rgba(88,28,135,0.25) 40%, rgba(236,72,153,0.1) 80%, rgba(15,23,42,0.7) 100%);
  border-radius: 14px;
  padding: 24px;
  border: 1px solid rgba(139,92,246,0.3);
  margin-bottom: 16px;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);
}
.timeline-hero::before {
  content: '';
  position: absolute;
  top: -30%; right: -10%;
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%);
  pointer-events: none;
}
.timeline-hero::after {
  content: '';
  position: absolute;
  bottom: -20%; left: -5%;
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(59,130,246,0.06) 0%, transparent 70%);
  pointer-events: none;
}
.timeline-hero h3 {
  font-size: 1.15rem;
  margin-bottom: 16px;
  border-bottom: none; padding-bottom: 0;
  display: flex; align-items: center; gap: 8px;
  background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.tl-stats {
  display: flex; gap: 12px; margin-bottom: 18px; flex-wrap: wrap;
}
.tl-stat {
  background: rgba(15,23,42,0.5);
  border-radius: 8px; padding: 8px 14px; font-size: 0.82rem;
  border: 1px solid rgba(255,255,255,0.06);
  backdrop-filter: blur(4px);
}
.tl-stat .num { font-weight: 700; }
.tl-stat .num.blue { color: #60a5fa; }
.tl-stat .num.gray { color: #94a3b8; }
.tl-stat .num.purple { color: #c084fc; }
.tl-stat .num.red { color: #f87171; }
.tl-stat .num.orange { color: #fb923c; }

.tl-bar-wrap {
  display: flex; gap: 4px; margin-bottom: 18px;
  align-items: flex-end; height: 56px; padding: 0 2px;
}
.tl-bar-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
  cursor: pointer; transition: transform 0.15s;
}
.tl-bar-item:hover { transform: translateY(-3px); }
.tl-bar-col {
  width: 100%; min-width: 28px;
  border-radius: 6px 6px 0 0;
  transition: opacity 0.15s;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.15);
}
.tl-bar-item:hover .tl-bar-col { opacity: 0.85; }
.tl-bar-label { font-size: 0.7rem; color: #94a3b8; white-space: nowrap; }
.tl-bar-count { font-size: 0.72rem; font-weight: 700; color: #e2e8f0; }

.month-header {
  cursor: pointer; transition: background 0.15s; user-select: none;
}
.month-header:hover { background: rgba(59,130,246,0.12) !important; }
.month-header td { padding: 12px 16px !important; }
.month-badge {
  display: inline-block;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  color: #fff; font-weight: 700; font-size: 0.9rem;
  padding: 4px 14px; border-radius: 8px; margin-right: 10px;
  box-shadow: 0 2px 8px rgba(59,130,246,0.3);
}
.month-badge.past {
  background: linear-gradient(135deg, #475569, #64748b);
  box-shadow: none;
}
.month-count { font-weight: 400; color: #94a3b8; font-size: 0.8rem; }
.month-toggle { float: right; color: #7c8db5; font-size: 0.8rem; transition: transform 0.2s; }
.month-header.collapsed .month-toggle { transform: rotate(-90deg); }
.date-cell { white-space: nowrap; font-weight: 700; font-size: 0.88rem; text-align: center; }
.date-cell.future { color: #fbbf24; }
.date-cell.past { color: #64748b; }
.date-cell.soon { color: #f87171; text-shadow: 0 0 6px rgba(248,113,113,0.4); }
.date-cell.undated { color: #475569; font-weight: 400; font-style: italic; }

/* Legend for new/updated */
.status-legend {
  display: flex; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;
}
.status-legend-item {
  display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: #94a3b8;
}
.legend-dot {
  width: 10px; height: 10px; border-radius: 50%;
}
.legend-dot.new { background: linear-gradient(135deg, #ef4444, #f97316); }
.legend-dot.updated { background: linear-gradient(135deg, #3b82f6, #8b5cf6); }
.legend-dot.dup { background: linear-gradient(135deg, #a855f7, #d946ef); }

@media (max-width: 768px) {
  .charts-grid { grid-template-columns: 1fr; }
  .filters { flex-direction: column; }
  .filters input { width: 100%; }
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
  .tl-stats { gap: 6px; }
  .tl-stat { padding: 6px 10px; font-size: 0.75rem; }
  .tl-bar-wrap { height: 40px; }
}'''

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
            <th>泊数</th>
            <th>1泊単価</th>
          </tr>
        </thead>
        <tbody>
''']

def build_row(e, date_html, date_class, hidden=False):
    title_esc = esc(e['title'][:80])
    status_html = status_badge(e['status'])
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

    nights_str = f'{e["nights"]}泊' if e['nights'] else '—'

    return f'''        <tr{row_class}>
          <td class="{date_class}">{date_html}</td>
          <td><a href="{esc(e['url'])}" target="_blank">{title_esc}</a>{status_html}</td>
          <td>{sites_html}</td>
          <td><span class="badge badge-area">{esc(e['prefecture'])}</span></td>
          <td class="comp">{fmt_comp(e['compensation_num'])}</td>
          <td class="nights">{nights_str}</td>
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
    '<th data-col="6">1泊単価</th>',
    '<th data-col="6">1泊単価</th>\n          <th data-col="7" style="text-align:center;width:70px;">👆</th>'
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
    
    main_rows.append(f"""        <tr class="{row_class}" data-site="{site}" data-area="{prefecture}">
          <td>{idx}</td>
          <td><a href="{url}" target="_blank" rel="noopener">{title_esc}</a>{status_html}</td>
          <td>{sites_html}</td>
          <td><span class="badge badge-area">{prefecture}</span></td>
          <td class="comp">{comp_str}</td>
          <td class="nights">{nights_str}</td>
          <td class="ppn">{ppn_str}</td>
        </tr>""")

new_main_html = f"""<table id="mainTable">
      <thead>
        <tr>
          <th data-col="0">#</th>
          <th data-col="1">案件名</th>
          <th data-col="2">サイト</th>
          <th data-col="3">地域</th>
          <th data-col="4">負担軽減費</th>
          <th data-col="5">泊数</th>
          <th data-col="6">1泊単価</th>
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
