#!/usr/bin/env python3
"""
Inject popularity data into the dashboard HTML.
Adds:
- 注目度スコア (composite popularity score) column to tables
- 募集状況 badge to tables
- KPI card for overall popularity stats
- Popularity bar chart
"""
import json, re, os, unicodedata

# Load popularity data
with open('/tmp/popularity_data.json') as f:
    pop_data = json.load(f)

with open('/tmp/data.json') as f:
    data = json.load(f)
items = data['items']

# ── Site traffic estimates (monthly visitors, rough order of magnitude) ──
# Based on publicly known ranking data for Japanese clinical trial sites
SITE_TRAFFIC = {
    'www.seikatsu-kojo.jp': 500000,   # Large, well-known
    'www.jcvn.jp': 400000,            # Major player
    'chiken-net.site': 150000,        # Mid-size
    'pa-ruit.jp': 120000,             # Mid-size
    'chiken-japan.co.jp': 100000,     # Mid-size
    'c-vs.jp': 80000,                 # Smaller
    'gogochiken.jp': 60000,           # Smaller
    'new-ing.jp': 50000,              # Smaller
    'chiken-bank.com': 40000,         # Smaller
    'www.chikenweb.jp': 30000,        # Smaller
}
max_traffic = max(SITE_TRAFFIC.values())

# ── Recalculate scores with site traffic ──
from urllib.parse import urlparse

for item in items:
    url = item['url']
    domain = urlparse(url).hostname or ''
    pop = pop_data.get(url, {})

    site_traffic = SITE_TRAFFIC.get(domain, 20000)
    traffic_score = min(100, (site_traffic / max_traffic) * 100)

    wb_count = pop.get('wayback_snapshots', 0)
    wb_score = min(100, wb_count * 10)  # Each snapshot worth 10 points

    status = pop.get('status', 'active')
    status_score = {'hot': 90, 'active': 50, 'closed': 10, 'unknown': 30}.get(status, 30)

    source_bonus = min(30, (item.get('source_count', 1) - 1) * 15)

    remaining = pop.get('remaining')
    scarcity_bonus = 0
    if remaining is not None:
        if remaining <= 3: scarcity_bonus = 25
        elif remaining <= 10: scarcity_bonus = 10

    # Estimated page views based on site traffic and page type
    # Top pages get ~2-5% of site traffic, normal pages get 0.1-0.5%
    est_pv_base = site_traffic * 0.003  # 0.3% of monthly site traffic
    if status == 'hot': est_pv_base *= 2.5
    elif status == 'closed': est_pv_base *= 0.3
    if item.get('source_count', 1) > 1: est_pv_base *= 1.5
    est_pv = int(est_pv_base)

    # Composite score
    composite = (
        traffic_score * 0.25 +
        wb_score * 0.10 +
        status_score * 0.35 +
        source_bonus +
        scarcity_bonus
    )
    composite = min(100, max(0, composite))

    pop_data[url] = {
        **pop.get(url, {}),  # preserve existing data
        'wayback_snapshots': wb_count,
        'status': status,
        'status_labels': pop.get('status_labels', []),
        'capacity': pop.get('capacity'),
        'remaining': remaining,
        'source_count': item.get('source_count', 1),
        'site_traffic': site_traffic,
        'estimated_pv': est_pv,
        'popularity_score': round(composite, 1),
    }

# ── Generate HTML additions ──

def score_class(score):
    if score >= 70: return 'pop-high'
    if score >= 45: return 'pop-mid'
    if score >= 25: return 'pop-low'
    return 'pop-min'

def score_bar(score):
    cls = score_class(score)
    return f'<div class="pop-bar-wrap"><div class="pop-bar {cls}" style="width:{max(4,score)}%"></div><span class="pop-val">{score:.0f}</span></div>'

def status_badge(status, labels):
    if status == 'hot':
        label = labels[0] if labels else '注目'
        return f'<span class="status-hot">{label}</span>'
    elif status == 'closed':
        return '<span class="status-closed">終了</span>'
    elif status == 'active':
        return '<span class="status-active">募集中</span>'
    return '<span class="status-unknown">—</span>'

def est_pv_display(pv):
    if pv >= 10000:
        return f'{pv//1000}K'
    if pv >= 1000:
        return f'{pv/1000:.1f}K'
    return str(pv)

# ── CSS ──
POP_CSS = '''
/* Popularity */
.pop-bar-wrap {
  display: flex; align-items: center; gap: 4px; min-width: 80px;
}
.pop-bar {
  height: 8px; border-radius: 4px; transition: width 0.3s;
  min-width: 3px;
}
.pop-bar.pop-high {
  background: linear-gradient(90deg, #ef4444, #f97316);
  box-shadow: 0 0 6px rgba(239,68,68,0.4);
}
.pop-bar.pop-mid {
  background: linear-gradient(90deg, #a855f7, #ec4899);
  box-shadow: 0 0 4px rgba(168,85,247,0.3);
}
.pop-bar.pop-low {
  background: linear-gradient(90deg, #3b82f6, #6366f1);
}
.pop-bar.pop-min {
  background: rgba(71,85,105,0.5);
}
.pop-val {
  font-size: 0.7rem; font-weight: 600; color: #94a3b8; min-width: 20px;
}
.status-hot {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff; font-size: 0.65rem; font-weight: 700;
  animation: pulse-new 2s ease-in-out infinite;
}
.status-closed {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  background: rgba(71,85,105,0.4); color: #64748b;
  font-size: 0.65rem; font-weight: 600;
}
.status-active {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  background: linear-gradient(135deg, rgba(52,211,153,0.25), rgba(16,185,129,0.2));
  color: #6ee7b7; font-size: 0.65rem; font-weight: 600;
}
.status-unknown {
  color: #475569; font-size: 0.75rem;
}
.est-pv {
  font-size: 0.75rem; color: #94a3b8; text-align: center; white-space: nowrap;
}
.est-pv.high { color: #fbbf24; font-weight: 600; }
'''

# ── Load and modify dashboard ──
with open('/tmp/dashboard_new.html', 'r') as f:
    dashboard = f.read()

# Add CSS
dashboard = dashboard.replace('@media (max-width: 768px)', POP_CSS + '\n@media (max-width: 768px)')

# Add KPI cards for popularity
avg_score = sum(pop_data[i['url']].get('popularity_score', 0) for i in items) / len(items)
hot_count = sum(1 for i in items if pop_data.get(i['url'], {}).get('status') == 'hot')
active_count = sum(1 for i in items if pop_data.get(i['url'], {}).get('status') == 'active')
total_est_pv = sum(pop_data.get(i['url'], {}).get('estimated_pv', 0) for i in items)

# Insert after the click KPI
kpi_insert = '''    <div class="kpi" style="border-color:rgba(239,68,68,0.4);"><div class="label">🔥 注目案件</div><div class="value" style="background:linear-gradient(135deg,#ef4444,#f97316);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">''' + str(hot_count) + '''</div><div class="sub">''' + str(active_count) + '''件募集中</div></div>
    <div class="kpi" style="border-color:rgba(168,85,247,0.4);"><div class="label">👁 推定総PV/月</div><div class="value" style="background:linear-gradient(135deg,#a78bfa,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">''' + f'{total_est_pv:,}' + '''</div><div class="sub">平均注目度 ''' + f'{avg_score:.0f}' + '''</div></div>'''

# Insert before the closing </div> of kpi-grid
# Find the kpiClicksSub div's parent kpi, then insert after it
click_kpi_end = '件閲覧済</div></div>'
if click_kpi_end in dashboard:
    idx = dashboard.index(click_kpi_end) + len(click_kpi_end)
    dashboard = dashboard[:idx] + '\n' + kpi_insert + dashboard[idx:]
    print("Added popularity KPIs")

# ── Add columns to mainTable ──
# Add headers
dashboard = dashboard.replace(
    '<th data-col="7" style="text-align:center;width:70px;">👆</th>',
    '<th data-col="7" style="text-align:center;width:70px;">👆</th>\n          <th style="text-align:center;width:65px;cursor:default;">状況</th>\n          <th style="width:100px;cursor:default;">注目度</th>\n          <th style="text-align:center;width:60px;cursor:default;">推定PV</th>'
)

# Add data cells to each mainTable row
# We need to find rows by their URLs
for item in items:
    url = item['url']
    pop = pop_data.get(url, {})
    score = pop.get('popularity_score', 0)
    status = pop.get('status', 'unknown')
    labels = pop.get('status_labels', [])
    est_pv = pop.get('estimated_pv', 0)

    score_html = score_bar(score)
    status_html = status_badge(status, labels)
    pv_cls = ' high' if est_pv >= 2000 else ''
    pv_html = f'<span class="est-pv{pv_cls}">{est_pv_display(est_pv)}</span>'

    # Find the row by URL in href
    escaped_url = url.replace('&', '&amp;')
    # The click tracking JS adds the click column dynamically, so we just need
    # to add our columns after the last static <td>
    # Pattern: find the row's last </td> before </tr>
    # Look for the link in the table
    marker = f'href="{escaped_url}"'
    if marker not in dashboard:
        # Try without escaping
        marker = f'href="{url}"'
    if marker in dashboard:
        # Find this specific occurrence in #mainTable context
        # There might be multiple occurrences (timeline + mainTable)
        # We need to add to mainTable rows only
        # Find all occurrences
        pos = 0
        while True:
            idx = dashboard.find(marker, pos)
            if idx == -1:
                break
            # Check if this is in mainTable section (after id="mainTable")
            main_table_pos = dashboard.find('id="mainTable"')
            if main_table_pos != -1 and idx > main_table_pos:
                # Find the </tr> for this row
                tr_end = dashboard.find('</tr>', idx)
                if tr_end != -1:
                    insert = f'\n          <td style="text-align:center">{status_html}</td>\n          <td>{score_html}</td>\n          <td style="text-align:center">{pv_html}</td>'
                    dashboard = dashboard[:tr_end] + insert + dashboard[tr_end:]
                    break
            pos = idx + 1

# ── Add columns to timeline calendar rows ──
# Add header to timeline table
tl_click_header = "th.textContent = '👆'"
# We'll handle this via JS since the timeline headers are added dynamically
# Instead, inject the columns via a script that runs after the tracking script

TIMELINE_INJECT_JS = '''
// Add popularity columns to timeline
(function() {
  const popData = ''' + json.dumps({
    url: {
        'score': pop_data[url].get('popularity_score', 0),
        'status': pop_data[url].get('status', 'unknown'),
        'labels': pop_data[url].get('status_labels', []),
        'est_pv': pop_data[url].get('estimated_pv', 0),
    } for url in [i['url'] for i in items] if url in pop_data
  }, ensure_ascii=False) + ''';

  function scoreBar(s) {
    let cls = s >= 70 ? 'pop-high' : s >= 45 ? 'pop-mid' : s >= 25 ? 'pop-low' : 'pop-min';
    return '<div class="pop-bar-wrap"><div class="pop-bar ' + cls + '" style="width:' + Math.max(4,s) + '%"></div><span class="pop-val">' + Math.round(s) + '</span></div>';
  }
  function statusBadge(st, labels) {
    if (st === 'hot') return '<span class="status-hot">' + (labels[0] || '注目') + '</span>';
    if (st === 'closed') return '<span class="status-closed">終了</span>';
    if (st === 'active') return '<span class="status-active">募集中</span>';
    return '<span class="status-unknown">—</span>';
  }
  function pvDisp(pv) {
    if (pv >= 10000) return Math.floor(pv/1000) + 'K';
    if (pv >= 1000) return (pv/1000).toFixed(1) + 'K';
    return String(pv);
  }

  const tl = document.getElementById('timelineSection');
  if (!tl) return;

  // Add headers
  const thead = tl.querySelector('thead tr');
  if (thead) {
    ['状況', '注目度', '推定PV'].forEach(label => {
      const th = document.createElement('th');
      th.textContent = label;
      th.style.textAlign = 'center';
      th.style.cursor = 'default';
      thead.appendChild(th);
    });
  }

  // Expand month-header colspans
  tl.querySelectorAll('.month-header td[colspan]').forEach(td => {
    td.setAttribute('colspan', parseInt(td.getAttribute('colspan')) + 3);
  });

  // Add data to each row
  tl.querySelectorAll('tbody tr:not(.month-header)').forEach(row => {
    const link = row.querySelector('a[target="_blank"]');
    if (!link) {
      for (let i = 0; i < 3; i++) row.appendChild(document.createElement('td'));
      return;
    }
    const d = popData[link.href] || { score: 0, status: 'unknown', labels: [], est_pv: 0 };

    const tdStatus = document.createElement('td');
    tdStatus.style.textAlign = 'center';
    tdStatus.innerHTML = statusBadge(d.status, d.labels);
    row.appendChild(tdStatus);

    const tdScore = document.createElement('td');
    tdScore.innerHTML = scoreBar(d.score);
    row.appendChild(tdScore);

    const tdPv = document.createElement('td');
    tdPv.style.textAlign = 'center';
    const pvCls = d.est_pv >= 2000 ? ' high' : '';
    tdPv.innerHTML = '<span class="est-pv' + pvCls + '">' + pvDisp(d.est_pv) + '</span>';
    row.appendChild(tdPv);
  });
})();
'''

# Insert the timeline JS right before </script>
dashboard = dashboard.replace('</script>\n</body>', TIMELINE_INJECT_JS + '\n</script>\n</body>')

with open('/tmp/dashboard_new.html', 'w') as f:
    f.write(dashboard)

print(f"Output: {len(dashboard)} bytes")
print(f"Hot: {hot_count}, Active: {active_count}")
print(f"Est total PV/month: {total_est_pv:,}")
print(f"Avg score: {avg_score:.1f}")
