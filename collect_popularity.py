#!/usr/bin/env python3
"""
Collect popularity signals from multiple external systems:
1. Wayback Machine CDX API — snapshot count per URL (crawl frequency = importance)
2. Refined page scraping — recruitment status from main content only
3. Site-level domain popularity via Wayback (domain total snapshots)
Outputs a merged popularity JSON.
"""
import asyncio, aiohttp, json, re, os, unicodedata, time
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from collections import defaultdict

with open('/tmp/data.json') as f:
    data = json.load(f)
items = data['items']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'ja,en;q=0.9',
}

# ════════════════════════════════════════
# 1. Wayback Machine CDX API
# ════════════════════════════════════════
async def wayback_count(session, url, semaphore):
    """Get snapshot count for a URL from Wayback Machine."""
    cdx_url = f"https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=500&fl=timestamp"
    async with semaphore:
        try:
            async with session.get(cdx_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    # First row is header, rest are snapshots
                    count = max(0, len(data) - 1) if isinstance(data, list) else 0
                    return url, count, None
                return url, 0, f"HTTP {resp.status}"
        except Exception as e:
            return url, 0, str(e)[:60]

async def wayback_domain_count(session, domain, semaphore):
    """Get total snapshot count for a domain."""
    cdx_url = f"https://web.archive.org/cdx/search/cdx?url={domain}/*&output=json&limit=1&showNumPages=true"
    async with semaphore:
        try:
            async with session.get(cdx_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    try:
                        count = int(text.strip())
                        return domain, count, None
                    except:
                        return domain, 0, "parse error"
                return domain, 0, f"HTTP {resp.status}"
        except Exception as e:
            return domain, 0, str(e)[:60]

# ════════════════════════════════════════
# 2. Refined page scraping (main content only)
# ════════════════════════════════════════
SITE_MAIN_SELECTORS = {
    'seikatsu-kojo.jp': ['.detail-main', '.clinical-detail', '#main', 'main', '.content'],
    'jcvn.jp': ['.detail-content', '.project-detail', '#main', 'main'],
    'chiken-net.site': ['.product-detail', '.main-content', '#main', 'main'],
    'chiken-japan.co.jp': ['.project-detail', '.entry-content', '#main', 'main'],
    'gogochiken.jp': ['.project-detail', '#main', 'main'],
    'pa-ruit.jp': ['.entry-content', '#main', 'main', 'article'],
    'chiken-bank.com': ['.detail', '#main', 'main'],
    'c-vs.jp': ['.item-detail', '#main', 'main'],
    'new-ing.jp': ['.entry-content', '#main', 'main'],
    'chikenweb.jp': ['.detail', '#main', 'main'],
}

HOT_KEYWORDS = ['残りわずか', '残り僅か', '急募', '追加募集', '追加日程', '緊急']
ACTIVE_KEYWORDS = ['募集中', '受付中', 'エントリー受付中']
CLOSED_KEYWORDS = ['募集終了', '受付終了', '定員に達しました', '満員御礼']

CAPACITY_PATS = [
    (r'定員[：:\s]*(\d+)\s*名', 'capacity'),
    (r'募集人数[：:\s]*(\d+)', 'capacity'),
    (r'残り\s*(\d+)\s*(?:名|枠)', 'remaining'),
    (r'あと\s*(\d+)\s*(?:名|枠)', 'remaining'),
]

async def fetch_and_analyze(session, url, semaphore):
    """Fetch page and extract recruitment status from main content."""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                   headers=HEADERS, ssl=False) as resp:
                if resp.status != 200:
                    return url, {'status': 'unknown', 'labels': [], 'capacity': None, 'remaining': None}
                html = await resp.text(errors='replace')
        except Exception as e:
            return url, {'status': 'unknown', 'labels': [], 'capacity': None, 'remaining': None}

    soup = BeautifulSoup(html, 'html.parser')
    domain = urlparse(url).hostname or ''

    # Find main content area
    main_text = None
    for base_domain, selectors in SITE_MAIN_SELECTORS.items():
        if base_domain in domain:
            for sel in selectors:
                el = soup.select_one(sel)
                if el:
                    main_text = el.get_text(separator=' ', strip=True)
                    break
            break

    if not main_text:
        # Fallback: get body text but exclude nav/footer/sidebar
        for tag in soup.find_all(['nav', 'footer', 'aside', 'header']):
            tag.decompose()
        main_text = soup.get_text(separator=' ', strip=True)

    # Also check the page title and H1
    title_text = ''
    h1 = soup.find('h1')
    if h1: title_text = h1.get_text(strip=True)
    title_tag = soup.find('title')
    if title_tag: title_text += ' ' + title_tag.get_text(strip=True)

    combined = title_text + ' ' + (main_text or '')[:3000]

    result = {'status': 'active', 'labels': [], 'capacity': None, 'remaining': None}

    # Check status in title first (most reliable)
    for kw in HOT_KEYWORDS:
        if kw in title_text:
            result['labels'].append(kw)
            result['status'] = 'hot'
    for kw in CLOSED_KEYWORDS:
        if kw in title_text:
            result['labels'].append(kw)
            result['status'] = 'closed'

    # Check in main content (less weight than title)
    for kw in HOT_KEYWORDS:
        if kw in combined and kw not in result['labels']:
            result['labels'].append(kw)
            if result['status'] != 'closed':
                result['status'] = 'hot'
    for kw in ACTIVE_KEYWORDS:
        if kw in combined and kw not in result['labels']:
            result['labels'].append(kw)

    # Extract capacity
    for pat, field in CAPACITY_PATS:
        m = re.search(pat, combined)
        if m:
            result[field] = int(m.group(1))
            break

    return url, result

# ════════════════════════════════════════
# Main
# ════════════════════════════════════════
async def main():
    urls = [item['url'] for item in items]
    domains = list(set(urlparse(u).hostname for u in urls))

    print(f"=== Collecting data for {len(urls)} URLs across {len(domains)} domains ===\n")

    sem_wb = asyncio.Semaphore(3)  # Wayback is rate-limited
    sem_page = asyncio.Semaphore(10)

    connector = aiohttp.TCPConnector(limit=15, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Wayback per-URL counts (in parallel with page scraping)
        print("[1/3] Wayback Machine: per-URL snapshot counts...")
        wb_tasks = [wayback_count(session, url, sem_wb) for url in urls]

        # 2. Page scraping
        print("[2/3] Source pages: recruitment status scraping...")
        page_tasks = [fetch_and_analyze(session, url, sem_page) for url in urls]

        # Run both in parallel
        wb_results_raw, page_results_raw = await asyncio.gather(
            asyncio.gather(*wb_tasks),
            asyncio.gather(*page_tasks)
        )

        # 3. Wayback domain-level counts
        print("[3/3] Wayback Machine: domain-level popularity...")
        domain_tasks = [wayback_domain_count(session, d, sem_wb) for d in domains]
        domain_results_raw = await asyncio.gather(*domain_tasks)

    # Process Wayback per-URL
    wb_data = {}
    wb_errors = 0
    for url, count, err in wb_results_raw:
        wb_data[url] = count
        if err: wb_errors += 1
    print(f"  Wayback URL: {len(wb_data)} results ({wb_errors} errors)")

    # Process domain counts
    domain_data = {}
    for domain, count, err in domain_results_raw:
        domain_data[domain] = count
    print(f"  Domain popularity: {domain_data}")

    # Process page scraping
    page_data = {}
    for url, result in page_results_raw:
        page_data[url] = result

    status_counts = defaultdict(int)
    for r in page_data.values():
        status_counts[r['status']] += 1
    print(f"  Page status: {dict(status_counts)}")

    # ════════════════════════════════════════
    # Compute composite popularity score
    # ════════════════════════════════════════
    # Normalize Wayback counts
    max_wb = max(wb_data.values()) if wb_data.values() else 1
    max_wb = max(max_wb, 1)

    # Normalize domain popularity
    max_domain = max(domain_data.values()) if domain_data.values() else 1
    max_domain = max(max_domain, 1)

    merged = {}
    for item in items:
        url = item['url']
        domain = urlparse(url).hostname or ''
        wb_count = wb_data.get(url, 0)
        dom_count = domain_data.get(domain, 0)
        page = page_data.get(url, {})

        # Score components (each 0-100)
        wb_score = min(100, (wb_count / max_wb) * 100) if max_wb > 0 else 0
        dom_score = min(100, (dom_count / max_domain) * 100) if max_domain > 0 else 0

        status_score = 0
        if page.get('status') == 'hot': status_score = 80
        elif page.get('status') == 'active': status_score = 50
        elif page.get('status') == 'closed': status_score = 10

        # Source count bonus (multi-site = popular)
        source_bonus = min(30, (item.get('source_count', 1) - 1) * 15)

        # Remaining slots bonus
        remaining = page.get('remaining')
        remaining_bonus = 0
        if remaining is not None:
            if remaining <= 3: remaining_bonus = 30
            elif remaining <= 10: remaining_bonus = 15

        # Composite score (weighted)
        composite = (
            wb_score * 0.25 +       # Wayback archival frequency
            dom_score * 0.10 +       # Domain overall popularity
            status_score * 0.35 +    # Recruitment status signals
            source_bonus +           # Multi-site listing bonus
            remaining_bonus          # Scarcity bonus
        )
        composite = min(100, max(0, composite))

        merged[url] = {
            'wayback_snapshots': wb_count,
            'domain_pages': dom_count,
            'status': page.get('status', 'unknown'),
            'status_labels': page.get('labels', []),
            'capacity': page.get('capacity'),
            'remaining': page.get('remaining'),
            'source_count': item.get('source_count', 1),
            'popularity_score': round(composite, 1),
        }

    # Save
    with open('/tmp/popularity_data.json', 'w') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Summary
    scores = [m['popularity_score'] for m in merged.values()]
    scores.sort(reverse=True)
    print(f"\n=== Results ===")
    print(f"Score range: {min(scores):.0f} - {max(scores):.0f}")
    print(f"Average: {sum(scores)/len(scores):.1f}")
    print(f"Top 10 scores: {[f'{s:.0f}' for s in scores[:10]]}")

    # Show top items
    top_items = sorted(merged.items(), key=lambda x: -x[1]['popularity_score'])[:10]
    print(f"\nTop 10 most popular:")
    for url, m in top_items:
        title = next((i['title'][:50] for i in items if i['url'] == url), '?')
        print(f"  {m['popularity_score']:5.1f} | WB:{m['wayback_snapshots']:3d} | {m['status']:7s} | {m['status_labels'][:3]} | {title}")

    print(f"\nSaved to /tmp/popularity_data.json")

asyncio.run(main())
