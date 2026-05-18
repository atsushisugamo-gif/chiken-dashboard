#!/usr/bin/env python3
"""
治験入院案件スクレイパー（全10サイト対応）

対応サイト:
  生活向上WEB, JCVN, ニューイング, 治験ジャパン, 治験情報V-NET,
  治験ウェブ, ぺいるーと, 治験バンク, 治験ネット, クリニカルボランティアサポート

ホスティング: GitHub Pages (https://atsushisugamo-gif.github.io/chiken-dashboard/)
デプロイ方法: `git push` するだけで自動デプロイ

外部ライブラリ不要（urllib, re のみ使用）
出力: ユーザーフォルダの data.json

新しいサイトを追加する場合:
1. scrape_XXX() 関数を追加（既存の scrape_seikatsu_kojo() などを参考）
2. SITE_SCRAPERS リストにエントリ追加（True で実装済み扱い）
"""
import urllib.request, urllib.error, re, html, json, os, unicodedata, sys, time
from datetime import datetime
from urllib.parse import urljoin

UA = 'Mozilla/5.0 (compatible; ChikenBot/1.0)'
REQUEST_DELAY = 0.5  # seconds between requests (be polite)

# ──────────────────────── Locate user folder ────────────────────────
def find_user_folder():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if 'デイリー治験ダッシュボード' in unicodedata.normalize('NFC', os.path.basename(script_dir)):
        return script_dir
    base = '/sessions'
    if os.path.isdir(base):
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
    # Fallback: if the script sits next to data.json / credentials.json / scraper.py itself,
    # assume the script directory is the data root. This covers GitHub Actions runners,
    # CI environments, and local checkouts where the folder name differs.
    if any(os.path.exists(os.path.join(script_dir, f)) for f in ('data.json', 'credentials.json', 'add_timeline.py')):
        return script_dir
    return None

# ──────────────────────── HTTP helper ────────────────────────
def fetch(url, timeout=20):
    time.sleep(REQUEST_DELAY)
    # Use session opener if domain has authenticated session
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    # Normalize www prefix
    for key in list(_SESSIONS.keys()) if '_SESSIONS' in globals() else []:
        if domain == key or domain.endswith('.' + key) or key.endswith('.' + domain):
            opener = _SESSIONS[key]
            req = urllib.request.Request(url)
            with opener.open(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='ignore')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def safe_int(s, default=0):
    try:
        return int(str(s).replace(',', '').replace('円', '').strip())
    except (ValueError, TypeError):
        return default

def extract_amount_from_context(text, labels=None):
    """Extract compensation amount near priority labels (負担軽減費 first).
    Handles formats: 123,456円, 約53万円, 53.5万円, etc.
    Returns amount in yen, or 0 if not found."""
    labels = labels or ['負担軽減費', '試験参加', '治験協力費', '協力費', '謝礼（総額）', '謝礼(総額)', '謝礼', '報酬']
    for label in labels:
        # Search label then next ~500 chars (including HTML)
        for m in re.finditer(rf'{re.escape(label)}(.{{0,500}}?)(?:</dd>|</td>|</p>|</li>|<dt|<th)', text, re.DOTALL):
            snippet = m.group(1)
            # Strip HTML tags
            snippet_plain = re.sub(r'<[^>]+>', ' ', snippet)
            # Try: 約XX万円 or XX.X万円 (e.g., 53万円, 53.5万円)
            mm = re.search(r'(?:約)?\s*([\d.]+)\s*万\s*円', snippet_plain)
            if mm:
                try:
                    val = int(float(mm.group(1)) * 10000)
                    if val >= 30000:
                        return val
                except ValueError:
                    pass
            # Try: X,XXX円 format
            mm = re.search(r'([\d,]{5,})\s*円', snippet_plain)
            if mm:
                v = safe_int(mm.group(1))
                if v >= 30000:
                    return v
    # Fallback: 総額約NN万円 anywhere
    mm = re.search(r'総額[\s(約\[]*([\d.]+)\s*万\s*円', text)
    if mm:
        try:
            val = int(float(mm.group(1)) * 10000)
            if val >= 30000:
                return val
        except ValueError:
            pass
    return 0


# ──────────────────────── Authentication ────────────────────────
import http.cookiejar
import urllib.parse

# Global cookie jars per site
_SESSIONS = {}

def load_credentials():
    """Load credentials.json from user folder."""
    user_folder = find_user_folder()
    if not user_folder:
        return {}
    path = os.path.join(user_folder, 'credentials.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"WARN: could not load credentials.json: {e}", file=sys.stderr)
        return {}

def get_opener(domain):
    """Get urllib opener with cookie jar for a domain."""
    if domain not in _SESSIONS:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.addheaders = [('User-Agent', UA)]
        _SESSIONS[domain] = opener
    return _SESSIONS[domain]

def fetch_with_session(url, domain, timeout=20):
    """Fetch URL using the session opener for the given domain."""
    opener = get_opener(domain)
    time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(url)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def login_laravel(domain, login_url, email, password):
    """Laravel-style login: GET for CSRF, POST credentials."""
    try:
        c = fetch_with_session(login_url, domain)
        pat1 = 'name="_token"\\s+value="([^"]+)"'
        pat2 = "name='_token'\\s+value='([^']+)'"
        pat3 = 'name="csrf-token"\\s+content="([^"]+)"'
        m = re.search(pat1, c) or re.search(pat2, c) or re.search(pat3, c)
        if not m:
            print(f"[{domain}] CSRF token not found")
            return False
        token = m.group(1)
        data = urllib.parse.urlencode({'_token': token, 'email': email, 'password': password}).encode()
        opener = get_opener(domain)
        req = urllib.request.Request(login_url, data=data, headers={'User-Agent': UA,
                                     'Referer': login_url, 'Content-Type': 'application/x-www-form-urlencoded'})
        with opener.open(req, timeout=20) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            # Check login success: page redirected or logout link appears
            return 'logout' in body.lower() or 'ログアウト' in body or 'mypage' in (resp.url or '')
    except Exception as e:
        print(f"[{domain}] Laravel login failed: {e}", file=sys.stderr)
        return False

def login_wordpress(domain, login_url, username, password):
    """WordPress wp-login.php login with SSL retry."""
    # Ensure opener exists (will create if not)
    get_opener(domain)
    # Use direct www URL since wp-login.php is typically on www subdomain
    if not domain.startswith('www.'):
        www_domain = 'www.' + domain
    else:
        www_domain = domain
    action_url = f'https://{www_domain}/wp-login.php'
    try:
        # GET first to establish wordpress_test_cookie
        fetch_with_session(action_url, domain)
        data = urllib.parse.urlencode({
            'log': username, 'pwd': password,
            'wp-submit': 'Log In',
            'redirect_to': f'https://{www_domain}/mypage/',
            'testcookie': '1'
        }).encode()
        opener = get_opener(domain)
        req = urllib.request.Request(action_url, data=data, headers={
            'User-Agent': UA, 'Referer': action_url,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': 'wordpress_test_cookie=WP+Cookie+check'
        })
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            final_url = resp.url or ''
            if 'logout' in body.lower() or 'ログアウト' in body or '/mypage' in final_url:
                return True
            # Check error message
            err = re.search(r'<div[^>]*id=["\']login_error["\'][^>]*>(.+?)</div>', body, re.DOTALL)
            if err:
                msg = re.sub(r'<[^>]+>', '', err.group(1)).strip()
                print(f"[{domain}] Login error: {msg[:150]}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[{domain}] WordPress login failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False

def login_eccube(domain, login_url, email, password):
    """EC-CUBE login (治験ネット)."""
    try:
        c = fetch_with_session(login_url, domain)
        pat1 = 'name="_csrf_token"\\s+value="([^"]+)"'
        pat2 = "name='_csrf_token'\\s+value='([^']+)'"
        m = re.search(pat1, c) or re.search(pat2, c)
        if not m:
            print(f"[{domain}] CSRF token not found")
            return False
        token = m.group(1)
        action = 'https://' + domain + '/login_check'
        data = urllib.parse.urlencode({'_csrf_token': token, 'login_email': email, 'login_pass': password}).encode()
        opener = get_opener(domain)
        req = urllib.request.Request(action, data=data, headers={'User-Agent': UA,
                                     'Referer': login_url, 'Content-Type': 'application/x-www-form-urlencoded'})
        with opener.open(req, timeout=20) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            return 'ログアウト' in body or 'logout' in body.lower() or 'mypage' in (resp.url or '')
    except Exception as e:
        print(f"[{domain}] EC-CUBE login failed: {e}", file=sys.stderr)
        return False

# Site-to-login-fn mapping
LOGIN_CONFIG = {
    'chiken-japan.co.jp': ('https://chiken-japan.co.jp/login', login_laravel),
    'gogochiken.jp': ('https://gogochiken.jp/login', login_laravel),
    'jcvn.jp': ('https://www.jcvn.jp/login', login_wordpress),
    'chiken-net.site': ('https://chiken-net.site/mypage/login', login_eccube),
}

def try_login_all():
    """Attempt login for all sites with credentials. Returns dict of domain -> success bool."""
    creds = load_credentials()
    results = {}
    for domain, (default_url, login_fn) in LOGIN_CONFIG.items():
        if domain not in creds or domain.startswith('_'):
            continue
        info = creds[domain]
        email = info.get('email', '').strip()
        password = info.get('password', '').strip()
        if not email or not password:
            print(f"[{domain}] credentials not set, skipping login")
            results[domain] = False
            continue
        url = info.get('login_url', '').strip() or default_url
        print(f"[{domain}] Attempting login...")
        ok = login_fn(domain, url, email, password)
        print(f"[{domain}] Login: {'✅ success' if ok else '❌ failed'}")
        results[domain] = ok
    return results


# ──────────────────────── 1) 生活向上WEB ────────────────────────
def scrape_seikatsu_kojo():
    site_name = '生活向上WEB'
    base = 'https://www.seikatsu-kojo.jp'
    items = []
    try:
        index_html = fetch(base + '/')
        ids = sorted(set(re.findall(r'/clinical/(\d+)\.html', index_html)), reverse=True)
        print(f"[{site_name}] Found {len(ids)} IDs on main page")
    except Exception as e:
        print(f"[{site_name}] Index fetch failed: {e}", file=sys.stderr)
        return items
    
    for i, trial_id in enumerate(ids):
        url = f"{base}/clinical/{trial_id}.html"
        try:
            c = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            print(f"[{site_name}] {trial_id}: HTTP {e.code}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[{site_name}] {trial_id}: {e}", file=sys.stderr)
            continue

        title_m = re.search(r'<title>([^<]+)</title>', c)
        title = html.unescape(title_m.group(1)).split('|')[0].strip() if title_m else ''
        if not title:
            continue

        # Filter: include trials with 泊 (inpatient) OR 通院/通所/来院 (outpatient)
        if '泊' not in title and '通院' not in title and '通所' not in title and '来院' not in title:
            continue

        # Compensation: try multiple patterns (with/without 総額約 prefix)
        comp_num = 0
        for pat in [
            r'試験参加[:：]\s*総額[約]?([\d,]+)\s*円',  # 試験参加:総額約840,000円
            r'試験参加[:：]\s*([\d,]+)\s*円',             # 試験参加:229,000円
        ]:
            comp_m = re.search(pat, c)
            if comp_m:
                v = safe_int(comp_m.group(1))
                if v >= 30000:
                    comp_num = v
                    break
        # Fallback: use general extractor
        if comp_num == 0:
            comp_num = extract_amount_from_context(c)

        # Nights: extract all N泊 tokens and sum (handles "3泊+通院1回+3泊+通院2回" → 6泊)
        night_matches = re.findall(r'(\d+)泊', title)
        # Also handle N泊×M回 format
        multiplied = re.findall(r'(\d+)泊\s*[×x]\s*(\d+)', title)
        total_nights = 0
        desc_parts = []
        if multiplied:
            for n, times in multiplied:
                total_nights += int(n) * int(times)
                desc_parts.append(f'{n}泊×{times}回')
            # Remove already-counted patterns and sum remaining standalone 泊
            remaining = re.sub(r'\d+泊\s*[×x]\s*\d+', '', title)
            standalone = re.findall(r'(\d+)泊', remaining)
            for n in standalone:
                total_nights += int(n)
                desc_parts.append(f'{n}泊')
        else:
            total_nights = sum(int(n) for n in night_matches)
            if len(night_matches) > 1:
                desc_parts = [f'{n}泊' for n in night_matches]
        nights_desc = '+'.join(desc_parts) if len(desc_parts) > 1 else None

        # Prefecture / area
        prefecture = '不明'
        # Priority: 都道府県 > 市区町村
        for pat in [r'(北海道|[^\s☆◆]{1,4}[都府県])', r'([^\s☆◆]{1,4}[市区町村])']:
            pm = re.search(pat, title)
            if pm:
                prefecture = pm.group(1)
                break

        # Price per night
        ppn = int(comp_num / total_nights) if total_nights > 0 and comp_num > 0 else 0

        # Outpatient (通院/通所/来院) count from title
        outpatient_count = 0
        for m in re.finditer(r'通院\s*(\d+)\s*回?|(\d+)\s*通院\s*回?|通所\s*(\d+)\s*回?|来院\s*(\d+)\s*回?', title):
            n = next((int(g) for g in m.groups() if g), 0)
            outpatient_count += n
        has_outpatient = outpatient_count > 0 or '通院' in title or '通所' in title or '来院' in title
        has_inpatient = total_nights > 0
        # trial_type_combined for display/filter
        if has_inpatient and has_outpatient:
            trial_type_combined = '入院+通院'
        elif has_outpatient:
            trial_type_combined = '通院のみ'
        elif has_inpatient:
            trial_type_combined = '入院のみ'
        else:
            trial_type_combined = '不明'

        # Recruiting status
        is_closed = '募集終了' in c and '募集中' not in c

        # Try to extract date from detail page body if title doesn't have one
        scraped_start_date = extract_date_from_body(c)

        items.append({
            'title': title,
            'url': url,
            'prefecture': prefecture,
            'area': prefecture,
            'area_raw': prefecture,
            'compensation': f'総額約{comp_num:,}円' if comp_num else '不明',
            'compensation_num': comp_num,
            'scraped_start_date': scraped_start_date,
            'nights': total_nights,
            'nights_desc': nights_desc,
            'total_nights': total_nights,
            'outpatient_count': outpatient_count,
            'has_outpatient': has_outpatient,
            'has_inpatient': has_inpatient,
            'trial_type_combined': trial_type_combined,
            'price_per_night': ppn,
            'capacity': None,
            'detail': '',
            'trial_type': trial_type_combined,
            'site': site_name,
            'category': trial_type_combined,
            'source_sites': [site_name],
            'source_count': 1,
        })
        if (i + 1) % 20 == 0:
            print(f"[{site_name}] Processed {i+1}/{len(ids)} ({len(items)} hospitalization trials)")
    
    print(f"[{site_name}] Done: {len(items)} hospitalization trials")
    return items

# ──────────────────────── Generic helpers ────────────────────────
def clean_text(s):
    """Strip HTML tags and decode entities."""
    s = re.sub(r'<[^>]+>', '', s or '')
    return html.unescape(s).strip()

def extract_date_from_body(html_content, year=None):
    """Extract earliest plausible 入院/開始 date from detail page HTML.
    Returns ISO date string 'YYYY-MM-DD' or None."""
    from datetime import date, timedelta
    if year is None:
        year = date.today().year
    if not html_content:
        return None
    # Strip tags + decode entities
    text = re.sub(r'<[^>]*>', ' ', html_content)
    text = html.unescape(text)

    candidates = []
    # 2026年5月8日 or 2026/5/8 or 2026-5-8 or 2026.5.8
    for m in re.finditer(r'(\d{4})[年./\-](\d{1,2})[月./\-](\d{1,2})', text):
        try: candidates.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError: pass
    # 5月8日 (assume current year)
    for m in re.finditer(r'(?<!\d)(\d{1,2})月(\d{1,2})日', text):
        try: candidates.append(date(year, int(m.group(1)), int(m.group(2))))
        except ValueError: pass
    # 5/8(金) or 5/8（金）
    for m in re.finditer(r'(?<!\d)(\d{1,2})/(\d{1,2})\s*[(「（][月火水木金土日](?:」|[)）])', text):
        try: candidates.append(date(year, int(m.group(1)), int(m.group(2))))
        except ValueError: pass
    # 5/8 followed by 入院/開始/スタート/から
    for m in re.finditer(r'(?<!\d)(\d{1,2})/(\d{1,2})\s*[^/0-9]*?(?:入院|開始|スタート|から)', text):
        try: candidates.append(date(year, int(m.group(1)), int(m.group(2))))
        except ValueError: pass

    if not candidates:
        return None
    today = date.today()
    # Keep only future-ish dates (within -7 to +180 days)
    valid = [d for d in candidates if (today - timedelta(days=7)) <= d <= (today + timedelta(days=200))]
    if not valid:
        # Fall back to nearest future date
        future = [d for d in candidates if d >= today]
        if future:
            return min(future).isoformat()
        return None
    return min(valid).isoformat()

def extract_nights_from_title(title):
    """Extract ALL N泊 tokens from title and sum, handling:
    - N泊×M回 (multiplied)
    - N泊+M泊+L泊 (added)
    - N泊+通院X回+M泊 (mixed, sum all N泊)
    Returns (total, desc)."""
    if not title:
        return (0, None)
    # Find all N泊×M回 patterns first (consume these tokens)
    mult_matches = re.findall(r'(\d+)泊\s*[×xX]\s*(\d+)', title)
    total = 0
    desc_parts = []
    consumed = title
    for n, times in mult_matches:
        total += int(n) * int(times)
        desc_parts.append(f"{n}泊×{times}回")
        # Remove the "N泊×M" token (including 回 if present)
        consumed = re.sub(rf'{n}泊\s*[×xX]\s*{times}\s*回?', '', consumed, count=1)
    # Now collect remaining standalone N泊 tokens
    remaining = re.findall(r'(\d+)泊', consumed)
    for n in remaining:
        total += int(n)
        desc_parts.append(f"{n}泊")
    if total == 0:
        return (0, None)
    desc = '+'.join(desc_parts) if len(desc_parts) > 1 else None
    return (total, desc)

PREFECTURES_RE = r'(北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県)'

def extract_prefecture(text):
    """Extract prefecture/city from text (prefer full 都道府県)."""
    t = text or ''
    # Try full 都道府県 first
    m = re.search(PREFECTURES_RE, t)
    if m:
        return m.group(1)
    # Short forms: 都・府・県
    m = re.search(r'(?<![\w])(東京|大阪|京都|福岡|北海道|札幌|名古屋|横浜|神戸)(?![\w])', t)
    if m:
        mapping = {'東京':'東京都', '大阪':'大阪府', '京都':'京都府', '福岡':'福岡県',
                   '札幌':'北海道', '名古屋':'愛知県', '横浜':'神奈川県', '神戸':'兵庫県'}
        return mapping.get(m.group(1), m.group(1))
    # City-level
    m = re.search(r'(?<![\w])([一-龥]{2,4}(?:市|区))(?![\w])', t)
    if m:
        return m.group(1)
    return '不明'

def make_item(title, url, site, comp_num=0, total_nights=0, nights_desc=None, prefecture=None, scraped_start_date=None):
    """Build standardized item dict."""
    if prefecture is None:
        prefecture = extract_prefecture(title)
    ppn = int(comp_num / total_nights) if total_nights > 0 and comp_num > 0 else 0
    # Outpatient extraction
    outpatient_count = 0
    for m in re.finditer(r'通院\s*(\d+)\s*回?|(\d+)\s*通院\s*回?|通所\s*(\d+)\s*回?|来院\s*(\d+)\s*回?', title or ''):
        n = next((int(g) for g in m.groups() if g), 0)
        outpatient_count += n
    has_outpatient = outpatient_count > 0 or '通院' in (title or '') or '通所' in (title or '') or '来院' in (title or '')
    has_inpatient = total_nights > 0
    if has_inpatient and has_outpatient:
        ttc = '入院+通院'
    elif has_outpatient:
        ttc = '通院のみ'
    elif has_inpatient:
        ttc = '入院のみ'
    else:
        ttc = '不明'
    return {
        'title': title,
        'url': url,
        'prefecture': prefecture,
        'area': prefecture,
        'area_raw': prefecture,
        'compensation': f'総額約{comp_num:,}円' if comp_num else '不明',
        'compensation_num': comp_num,
        'scraped_start_date': scraped_start_date,
        'nights': total_nights,
        'nights_desc': nights_desc,
        'total_nights': total_nights,
        'outpatient_count': outpatient_count,
        'has_outpatient': has_outpatient,
        'has_inpatient': has_inpatient,
        'trial_type_combined': ttc,
        'price_per_night': ppn,
        'capacity': None,
        'detail': '',
        'trial_type': ttc,
        'site': site,
        'category': ttc,
        'source_sites': [site],
        'source_count': 1,
    }

def scrape_generic_site(site_name, index_url, detail_pattern, detail_prefix,
                        amount_patterns=None, require_nights=True):
    """Generic scraper: fetch index, then each detail page, extract fields from title + body."""
    items = []
    try:
        index_html = fetch(index_url)
    except Exception as e:
        print(f"[{site_name}] Index fetch failed: {e}", file=sys.stderr)
        return items

    # Extract detail URLs
    paths = sorted(set(re.findall(detail_pattern, index_html)))
    print(f"[{site_name}] Found {len(paths)} detail URLs")

    for i, p in enumerate(paths):
        url = detail_prefix + p
        try:
            c = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404: continue
            print(f"[{site_name}] {p}: HTTP {e.code}", file=sys.stderr); continue
        except Exception as e:
            print(f"[{site_name}] {p}: {e}", file=sys.stderr); continue

        # Title from og:title or title tag
        og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', c)
        if og:
            title = html.unescape(og.group(1)).strip()
        else:
            t = re.search(r'<title>([^<]+)</title>', c)
            title = html.unescape(t.group(1)).split('|')[0].strip() if t else ''
        if not title: continue

        # Filter: hospitalization only
        if require_nights and '泊' not in title:
            continue

        # Extract nights
        total_nights, nights_desc = extract_nights_from_title(title)

        # Extract amount using label-aware extractor
        comp_num = extract_amount_from_context(c)
        # If custom patterns were provided, try those as fallback
        if comp_num == 0 and amount_patterns:
            for pat in amount_patterns:
                for m in re.finditer(pat, c):
                    v = safe_int(m.group(1))
                    if v >= 30000:
                        comp_num = v
                        break
                if comp_num:
                    break

        scraped_start_date = extract_date_from_body(c)
        items.append(make_item(title, url, site_name, comp_num, total_nights, nights_desc, scraped_start_date=scraped_start_date))
        if (i + 1) % 10 == 0:
            print(f"[{site_name}] Processed {i+1}/{len(paths)} ({len(items)} hospitalization)")
    
    print(f"[{site_name}] Done: {len(items)} items")
    return items

# ──────────────────────── 2) JCVN ────────────────────────
def scrape_jcvn():
    return scrape_generic_site(
        'JCVN', 'https://www.jcvn.jp/',
        r'/mypage/detail/\?id=[A-Z0-9]+', 'https://www.jcvn.jp',
        amount_patterns=[],  # amount hidden for non-members
    )

# ──────────────────────── 3) ニューイング ────────────────────────
def scrape_newing():
    return scrape_generic_site(
        'ニューイング', 'https://new-ing.jp/',
        r'/recruited/\d+', 'https://new-ing.jp',
        amount_patterns=[r'([\d,]{5,})\s*円'],
    )

# ──────────────────────── 4) 治験ジャパン ────────────────────────
def scrape_chiken_japan():
    return scrape_generic_site(
        '治験ジャパン', 'https://chiken-japan.co.jp/',
        r'/project/\d+', 'https://chiken-japan.co.jp',
        amount_patterns=[],
    )

# ──────────────────────── 5) 治験情報V-NET ────────────────────────
def scrape_gogochiken():
    return scrape_generic_site(
        '治験情報V-NET', 'https://gogochiken.jp/',
        r'/project/\d+', 'https://gogochiken.jp',
        amount_patterns=[],
    )

# ──────────────────────── 6) 治験ウェブ ────────────────────────
def scrape_chikenweb():
    return scrape_generic_site(
        '治験ウェブ', 'https://www.chikenweb.jp/',
        r'/chiken_detail\.php\?id=-?\d+', 'https://www.chikenweb.jp',
        amount_patterns=[],
    )

# ──────────────────────── 7) ぺいるーと ────────────────────────
def scrape_paruit():
    return scrape_generic_site(
        'ぺいるーと', 'https://pa-ruit.jp/',
        r'/\d+-\d+[-\w]*-\d+/', 'https://pa-ruit.jp',
        amount_patterns=[r'謝礼\(総額\)[：:]\s*([\d,]+)\s*円'],
    )

# ──────────────────────── 8) 治験バンク ────────────────────────
def scrape_chiken_bank():
    return scrape_generic_site(
        '治験バンク', 'https://chiken-bank.com/',
        r'/case/detail\.php\?id=\d+', 'https://chiken-bank.com',
        amount_patterns=[r'([\d,]{5,})\s*円'],
    )

# ──────────────────────── 9) 治験ネット ────────────────────────
def scrape_chiken_net():
    return scrape_generic_site(
        '治験ネット', 'https://chiken-net.site/',
        r'/products/detail/\d+', 'https://chiken-net.site',
        amount_patterns=[r'謝礼[^\d]*([\d,]{5,})\s*円'],
    )

# ──────────────────────── 10) CVS ────────────────────────
def scrape_cvs():
    return scrape_generic_site(
        'クリニカルボランティアサポート', 'https://c-vs.jp/',
        r'/item_detail/[\w-]+/', 'https://c-vs.jp',
        amount_patterns=[r'謝礼[^\d]*([\d,]{5,})\s*円', r'([\d,]{5,})\s*円'],
    )

# (site_name, scraper_fn, implemented) — implemented=False keeps existing data from data.json
SITE_SCRAPERS = [
    ('生活向上WEB', scrape_seikatsu_kojo, True),
    ('JCVN', scrape_jcvn, True),
    ('ニューイング', scrape_newing, True),
    ('治験ジャパン', scrape_chiken_japan, True),
    ('治験情報V-NET', scrape_gogochiken, True),
    ('治験ウェブ', scrape_chikenweb, True),
    ('ぺいるーと', scrape_paruit, True),
    ('治験バンク', scrape_chiken_bank, True),
    ('治験ネット', scrape_chiken_net, True),
    ('クリニカルボランティアサポート', scrape_cvs, True),
]

# ──────────────────────── Merge / dedup ────────────────────────
def merge_items(all_items):
    """Dedup items with similar titles across sites."""
    def norm_title(t):
        # Normalize for dedup: remove whitespace, lowercase
        t = re.sub(r'\s+', '', t or '').lower()
        # Remove date markers for loose matching
        t = re.sub(r'\d+/\d+\(.\)', '', t)
        return t
    
    by_key = {}
    for item in all_items:
        key = norm_title(item['title'])[:40]  # first 40 chars as dedup key
        if key in by_key:
            existing = by_key[key]
            # Merge source sites
            if item['site'] not in existing['source_sites']:
                existing['source_sites'].append(item['site'])
                existing['source_count'] = len(existing['source_sites'])
        else:
            by_key[key] = item
    return list(by_key.values())

# ──────────────────────── Main (smart merge) ────────────────────────
def main():
    user_folder = find_user_folder()
    if not user_folder:
        print("ERROR: user folder not found", file=sys.stderr)
        sys.exit(1)
    print(f"User folder: {user_folder}")
    
    # Attempt logins (silently skips sites without credentials)
    print("\n─── Authentication ───")
    try_login_all()
    print("")
    
    data_path = os.path.join(user_folder, 'data.json')
    
    # Load existing data.json for smart merge
    existing = {'items': []}
    if os.path.exists(data_path):
        try:
            with open(data_path) as f:
                existing = json.load(f)
            print(f"Loaded existing data.json: {len(existing.get('items', []))} items")
        except Exception as e:
            print(f"WARN: could not load existing data.json: {e}")
    
    # Partition existing items by site AND index by URL for fallback
    existing_by_site = {}
    existing_by_url = {}
    for item in existing.get('items', []):
        site = item.get('site', '')
        existing_by_site.setdefault(site, []).append(item)
        existing_by_url[item.get('url', '')] = item
    
    all_items = []
    errors = []
    site_status = []  # [(site, source, count)]
    
    for site_name, scraper_fn, implemented in SITE_SCRAPERS:
        existing_for_site = existing_by_site.get(site_name, [])
        if implemented:
            try:
                scraped = scraper_fn()
                # Inherit compensation from existing by URL if missing
                for item in scraped:
                    if item.get('compensation_num', 0) == 0:
                        old = existing_by_url.get(item.get('url', ''))
                        if old and old.get('compensation_num', 0) > 0:
                            item['compensation_num'] = old['compensation_num']
                            item['compensation'] = old.get('compensation', f"総額約{old['compensation_num']:,}円")
                            if item.get('total_nights', 0) > 0:
                                item['price_per_night'] = int(item['compensation_num'] / item['total_nights'])
                
                # MERGE with existing site items: scraped URLs override, existing URLs not in scraped are kept
                scraped_urls = {item.get('url', '') for item in scraped}
                preserved = [item for item in existing_for_site if item.get('url', '') not in scraped_urls]
                merged_site_items = list(scraped) + preserved
                
                all_items.extend(merged_site_items)
                if preserved:
                    site_status.append((site_name, f'scraped+preserved', f"{len(scraped)} fresh + {len(preserved)} kept = {len(merged_site_items)}"))
                else:
                    site_status.append((site_name, 'scraped', len(merged_site_items)))
            except Exception as e:
                print(f"[ERROR] {site_name}: {e}", file=sys.stderr)
                errors.append(f"{site_name}: {e}")
                all_items.extend(existing_for_site)
                site_status.append((site_name, f'fallback (error)', len(existing_for_site)))
        else:
            all_items.extend(existing_for_site)
            site_status.append((site_name, 'kept from existing', len(existing_for_site)))
    
    merged = merge_items(all_items)
    print(f"\n─── Site status ───")
    for name, source, count in site_status:
        print(f"  {name}: {source} ({count}{' items' if isinstance(count, int) else ''})")
    print(f"\nTotal: {len(all_items)} raw -> {len(merged)} after dedup")
    
    # Safety: if result is suspiciously small, preserve existing
    if len(merged) < 10 and existing.get('items'):
        print(f"\n⚠️ Result too small ({len(merged)}); preserving existing data.json")
        return
    
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

if __name__ == '__main__':
    main()
