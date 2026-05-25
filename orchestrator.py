#!/usr/bin/env python3
"""Resumable orchestrator for the weekly chiken dashboard scrape.

WHY THIS EXISTS
  Cowork command windows are capped at ~45s, but scraping all 10 sites takes
  ~5 minutes, so scraper.py cannot finish in one window. This orchestrator
  runs in time-bounded chunks and checkpoints state.json after every page,
  so it can be invoked repeatedly until done.

USAGE
  Run `python3 orchestrator.py` repeatedly. Stop when output contains
  "READY_FOR_ASSEMBLY", then run `assemble.py` to write data.json.
  state.json carries run_date; a state file from a previous day is treated
  as stale and the scrape restarts automatically.

MAINTENANCE
  Replicates the per-site CONFIG + detail loop of scraper.py; extraction
  helpers are imported from scraper.py. Keep GENERIC_SITES below in sync if
  scraper.py's site list or detail-URL patterns change.
"""
import sys, os, re, json, time, unicodedata, urllib.error, html, datetime

OUT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(OUT, 'state.json')
TIME_BUDGET = 30.0  # seconds of detail-fetching per invocation

# ---- locate user folder + import scraper module ----
def find_user_folder():
    base = '/sessions'
    for sess in os.listdir(base):
        mnt = os.path.join(base, sess, 'mnt')
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
    print("FATAL: user folder not found")
    sys.exit(2)
sys.path.insert(0, USER_FOLDER)
import scraper  # noqa

# ---- generic-site config (mirrors scrape_*() calls in scraper.py) ----
GENERIC_SITES = {
    'JCVN': dict(index='https://www.jcvn.jp/', pat=r'/mypage/detail/\?id=[A-Z0-9]+',
                 prefix='https://www.jcvn.jp', amount=[], loc=None),
    'ニューイング': dict(index='https://new-ing.jp/', pat=r'/recruited/\d+',
                 prefix='https://new-ing.jp', amount=[r'([\d,]{5,})\s*円'],
                 loc=[r'実施医療機関.{0,30}?所在地\s*</th>\s*<td[^>]*>\s*<span[^>]*>([^<]+)</span>',
                      r'実施医療機関.{0,30}?所在地\s*</th>\s*<td[^>]*>([^<]+?)</td>']),
    '治験ジャパン': dict(index='https://chiken-japan.co.jp/', pat=r'/project/\d+',
                 prefix='https://chiken-japan.co.jp', amount=[], loc=None),
    '治験情報V-NET': dict(index='https://gogochiken.jp/', pat=r'/project/\d+',
                 prefix='https://gogochiken.jp', amount=[], loc=None),
    '治験ウェブ': dict(index='https://www.chikenweb.jp/', pat=r'/chiken_detail\.php\?id=-?\d+',
                 prefix='https://www.chikenweb.jp', amount=[], loc=None),
    'ぺいるーと': dict(index='https://pa-ruit.jp/', pat=r'/\d+-\d+[-\w]*-\d+/',
                 prefix='https://pa-ruit.jp', amount=[r'謝礼\(総額\)[：:]\s*([\d,]+)\s*円'],
                 loc=[r'<h2>\s*実施場所\s*</h2>\s*</th>\s*<td[^>]*>\s*<p[^>]*>([^<]+)</p>',
                      r'実施場所\s*</h2>[^<]*</th>\s*<td[^>]*>([^<]+?)</td>']),
    '治験バンク': dict(index='https://chiken-bank.com/', pat=r'/case/detail\.php\?id=\d+',
                 prefix='https://chiken-bank.com', amount=[r'([\d,]{5,})\s*円'], loc=None),
    '治験ネット': dict(index='https://chiken-net.site/', pat=r'/products/detail/\d+',
                 prefix='https://chiken-net.site', amount=[r'謝礼[^\d]*([\d,]{5,})\s*円'], loc=None),
    'クリニカルボランティアサポート': dict(index='https://c-vs.jp/', pat=r'/item_detail/[\w-]+/',
                 prefix='https://c-vs.jp',
                 amount=[r'謝礼[^\d]*([\d,]{5,})\s*円', r'([\d,]{5,})\s*円'], loc=None),
}
SEIKATSU_INDEX = 'https://www.seikatsu-kojo.jp/'
SEIKATSU_BASE = 'https://www.seikatsu-kojo.jp'
# Order must match scraper.SITE_SCRAPERS
SITE_ORDER = ['生活向上WEB', 'JCVN', 'ニューイング', '治験ジャパン', '治験情報V-NET',
              '治験ウェブ', 'ぺいるーと', '治験バンク', '治験ネット', 'クリニカルボランティアサポート']


def process_seikatsu_detail(url):
    try:
        c = scraper.fetch(url)
    except urllib.error.HTTPError as e:
        return None
    except Exception:
        return None
    title_m = re.search(r'<title>([^<]+)</title>', c)
    title = html.unescape(title_m.group(1)).split('|')[0].strip() if title_m else ''
    if not title:
        return None
    if '泊' not in title and '通院' not in title and '通所' not in title and '来院' not in title:
        return None
    comp_num = 0
    for pat in [r'試験参加[:：]\s*総額[約]?([\d,]+)\s*円', r'試験参加[:：]\s*([\d,]+)\s*円']:
        m = re.search(pat, c)
        if m:
            v = scraper.safe_int(m.group(1))
            if v >= 30000:
                comp_num = v
                break
    if comp_num == 0:
        comp_num = scraper.extract_amount_from_context(c)
    night_matches = re.findall(r'(\d+)泊', title)
    multiplied = re.findall(r'(\d+)泊\s*[×x]\s*(\d+)', title)
    total_nights = 0
    desc_parts = []
    if multiplied:
        for n, times in multiplied:
            total_nights += int(n) * int(times)
            desc_parts.append(f'{n}泊×{times}回')
        remaining = re.sub(r'\d+泊\s*[×x]\s*\d+', '', title)
        for n in re.findall(r'(\d+)泊', remaining):
            total_nights += int(n)
            desc_parts.append(f'{n}泊')
    else:
        total_nights = sum(int(n) for n in night_matches)
        if len(night_matches) > 1:
            desc_parts = [f'{n}泊' for n in night_matches]
    nights_desc = '+'.join(desc_parts) if len(desc_parts) > 1 else None
    prefecture = '不明'
    loc_raw = ''
    loc_m = re.search(r'<h2>\s*実施場所\s*</h2>\s*<p[^>]*search_detail_content[^>]*>\s*([^<]+?)\s*</p>', c)
    if loc_m:
        loc_text = html.unescape(loc_m.group(1)).strip()
        loc_text = re.sub(r'^\[[^\]]+\]\s*', '', loc_text).strip()
        loc_raw = loc_text
        if loc_text:
            prefecture = loc_text
    if prefecture == '不明':
        for pat in [r'(北海道|[^\s☆◆]{1,4}[都府県])', r'([^\s☆◆]{1,4}[市区町村])']:
            pm = re.search(pat, title)
            if pm:
                prefecture = pm.group(1)
                break
    ppn = int(comp_num / total_nights) if total_nights > 0 and comp_num > 0 else 0
    outpatient_count = 0
    for m in re.finditer(r'通院\s*(\d+)\s*回?|(\d+)\s*通院\s*回?|通所\s*(\d+)\s*回?|来院\s*(\d+)\s*回?', title):
        n = next((int(g) for g in m.groups() if g), 0)
        outpatient_count += n
    has_outpatient = outpatient_count > 0 or '通院' in title or '通所' in title or '来院' in title
    has_inpatient = total_nights > 0
    if has_inpatient and has_outpatient:
        ttc = '入院+通院'
    elif has_outpatient:
        ttc = '通院のみ'
    elif has_inpatient:
        ttc = '入院のみ'
    else:
        ttc = '不明'
    scraped_start_date = scraper.extract_date_from_body(c)
    return {
        'title': title, 'url': url, 'prefecture': prefecture, 'area': prefecture,
        'area_raw': loc_raw or prefecture,
        'compensation': f'総額約{comp_num:,}円' if comp_num else '不明',
        'compensation_num': comp_num, 'scraped_start_date': scraped_start_date,
        'nights': total_nights, 'nights_desc': nights_desc, 'total_nights': total_nights,
        'outpatient_count': outpatient_count, 'has_outpatient': has_outpatient,
        'has_inpatient': has_inpatient, 'trial_type_combined': ttc, 'price_per_night': ppn,
        'capacity': None, 'detail': '', 'trial_type': ttc, 'site': '生活向上WEB',
        'category': ttc, 'source_sites': ['生活向上WEB'], 'source_count': 1,
    }


def process_generic_detail(url, site_name, amount_patterns, location_patterns, require_nights=True):
    try:
        c = scraper.fetch(url)
    except urllib.error.HTTPError as e:
        return None
    except Exception:
        return None
    og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', c)
    if og:
        title = html.unescape(og.group(1)).strip()
    else:
        t = re.search(r'<title>([^<]+)</title>', c)
        title = html.unescape(t.group(1)).split('|')[0].strip() if t else ''
    if not title:
        return None
    if require_nights and '泊' not in title:
        return None
    total_nights, nights_desc = scraper.extract_nights_from_title(title)
    comp_num = scraper.extract_amount_from_context(c)
    if comp_num == 0 and amount_patterns:
        for pat in amount_patterns:
            for m in re.finditer(pat, c):
                v = scraper.safe_int(m.group(1))
                if v >= 30000:
                    comp_num = v
                    break
            if comp_num:
                break
    scraped_start_date = scraper.extract_date_from_body(c)
    body_loc = scraper.extract_location_from_body(c, location_patterns) if location_patterns else None
    return scraper.make_item(title, url, site_name, comp_num, total_nights, nights_desc,
                             prefecture=body_loc, scraped_start_date=scraped_start_date)


def save_state(state):
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def build_index(state):
    """First invocation: login + fetch every index page, record detail URLs."""
    print("=== Building index ===")
    try:
        scraper.try_login_all()
    except Exception as e:
        print("login warn:", e)
    state['sites'] = {}
    # seikatsu (custom)
    try:
        h = scraper.fetch(SEIKATSU_INDEX)
        ids = sorted(set(re.findall(r'/clinical/(\d+)\.html', h)), reverse=True)
        urls = [f"{SEIKATSU_BASE}/clinical/{i}.html" for i in ids]
        state['sites']['生活向上WEB'] = dict(kind='seikatsu', urls=urls, cursor=0,
                                          items=[], status='pending', error=None)
        print(f"  生活向上WEB: {len(urls)} urls")
    except Exception as e:
        state['sites']['生活向上WEB'] = dict(kind='seikatsu', urls=[], cursor=0,
                                          items=[], status='error', error=str(e))
        print(f"  生活向上WEB: INDEX ERROR {e}")
    # generic sites
    for name, cfg in GENERIC_SITES.items():
        try:
            h = scraper.fetch(cfg['index'])
            paths = sorted(set(re.findall(cfg['pat'], h)))
            urls = [cfg['prefix'] + p for p in paths]
            state['sites'][name] = dict(kind='generic', urls=urls, cursor=0,
                                        items=[], status='pending', error=None)
            print(f"  {name}: {len(urls)} urls")
        except Exception as e:
            state['sites'][name] = dict(kind='generic', urls=[], cursor=0,
                                        items=[], status='error', error=str(e))
            print(f"  {name}: INDEX ERROR {e}")
    state['phase'] = 'detail'
    save_state(state)


def run_detail(state):
    """Process detail pages until the time budget is exhausted."""
    try:
        scraper.try_login_all()
    except Exception as e:
        print("login warn:", e)
    start = time.time()
    processed = 0
    for name in SITE_ORDER:
        site = state['sites'][name]
        if site['status'] in ('error', 'done'):
            continue
        cfg = GENERIC_SITES.get(name)
        while site['cursor'] < len(site['urls']):
            if time.time() - start > TIME_BUDGET:
                save_state(state)
                print(f"time budget reached; processed {processed} pages this run")
                return False
            url = site['urls'][site['cursor']]
            try:
                if site['kind'] == 'seikatsu':
                    item = process_seikatsu_detail(url)
                else:
                    item = process_generic_detail(url, name, cfg['amount'], cfg['loc'])
            except Exception as e:
                item = None
            if item:
                site['items'].append(item)
            site['cursor'] += 1
            processed += 1
            if processed % 5 == 0:
                save_state(state)
        site['status'] = 'done'
        save_state(state)
        print(f"  [{name}] done: {len(site['items'])} items ({site['cursor']} pages)")
    save_state(state)
    print(f"ALL DETAIL DONE; processed {processed} pages this run")
    return True


def main():
    today = datetime.date.today().isoformat()
    state = None
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                state = json.load(f)
        except Exception:
            state = None
    # a state file from a previous day is stale -> restart the scrape
    if not state or state.get('run_date') != today:
        state = dict(phase='index', sites={}, run_date=today)

    if state['phase'] == 'index':
        build_index(state)

    if state['phase'] == 'detail':
        finished = run_detail(state)
        if finished:
            state['phase'] = 'detail_done'
            save_state(state)

    # progress report
    done = sum(1 for s in state['sites'].values() if s['status'] in ('done', 'error'))
    total_pages = sum(len(s['urls']) for s in state['sites'].values())
    done_pages = sum(s['cursor'] for s in state['sites'].values())
    total_items = sum(len(s['items']) for s in state['sites'].values())
    print(f"\nPHASE={state['phase']}  sites done {done}/{len(state['sites'])}  "
          f"pages {done_pages}/{total_pages}  items collected {total_items}")
    if state['phase'] == 'detail_done':
        print("READY_FOR_ASSEMBLY")


if __name__ == '__main__':
    main()
