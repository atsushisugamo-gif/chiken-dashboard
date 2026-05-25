#!/usr/bin/env python3
"""Assembly step: replicates scraper.py main()'s smart-merge and writes data.json."""
import sys, os, json, unicodedata
from datetime import datetime

OUT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(OUT, 'state.json')

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
sys.path.insert(0, USER_FOLDER)
import scraper

SITE_ORDER = ['生活向上WEB', 'JCVN', 'ニューイング', '治験ジャパン', '治験情報V-NET',
              '治験ウェブ', 'ぺいるーと', '治験バンク', '治験ネット', 'クリニカルボランティアサポート']

state = json.load(open(STATE_PATH))
data_path = os.path.join(USER_FOLDER, 'data.json')

existing = {'items': []}
if os.path.exists(data_path):
    try:
        existing = json.load(open(data_path))
        print(f"Loaded existing data.json: {len(existing.get('items', []))} items")
    except Exception as e:
        print(f"WARN: could not load existing data.json: {e}")

existing_by_site, existing_by_url = {}, {}
for item in existing.get('items', []):
    existing_by_site.setdefault(item.get('site', ''), []).append(item)
    existing_by_url[item.get('url', '')] = item

all_items, errors, site_status = [], [], []
for site_name in SITE_ORDER:
    existing_for_site = existing_by_site.get(site_name, [])
    st = state['sites'][site_name]
    if st['status'] == 'error':
        print(f"[ERROR] {site_name}: {st['error']}", file=sys.stderr)
        errors.append(f"{site_name}: {st['error']}")
        all_items.extend(existing_for_site)
        site_status.append((site_name, 'fallback (error)', len(existing_for_site)))
        continue
    scraped = st['items']
    for item in scraped:
        if item.get('compensation_num', 0) == 0:
            old = existing_by_url.get(item.get('url', ''))
            if old and old.get('compensation_num', 0) > 0:
                item['compensation_num'] = old['compensation_num']
                item['compensation'] = old.get('compensation', f"総額約{old['compensation_num']:,}円")
                if item.get('total_nights', 0) > 0:
                    item['price_per_night'] = int(item['compensation_num'] / item['total_nights'])
    scraped_urls = {i.get('url', '') for i in scraped}
    preserved = [i for i in existing_for_site if i.get('url', '') not in scraped_urls]
    merged_site_items = list(scraped) + preserved
    all_items.extend(merged_site_items)
    if preserved:
        site_status.append((site_name, 'scraped+preserved',
                            f"{len(scraped)} fresh + {len(preserved)} kept = {len(merged_site_items)}"))
    else:
        site_status.append((site_name, 'scraped', len(merged_site_items)))

merged = scraper.merge_items(all_items)
print("\n─── Site status ───")
for name, source, count in site_status:
    print(f"  {name}: {source} ({count})")
print(f"\nTotal: {len(all_items)} raw -> {len(merged)} after dedup")

if len(merged) < 10 and existing.get('items'):
    print(f"\n⚠️ Result too small ({len(merged)}); preserving existing data.json")
    print("ASSEMBLY_SKIPPED")
    sys.exit(0)

output = {
    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'total_count': len(merged),
    'errors': errors,
    'filter': '入院',
    'items': merged,
}
with open(data_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n✅ Wrote {len(merged)} items to {data_path}")
print(f"errors: {errors}")
print("ASSEMBLY_DONE")
