import os, re, json, hashlib
import feedparser
import requests
from datetime import datetime

RSS_SOURCES = {
    "setkab": "https://setkab.go.id/feed/",
    "kemenkeu": "https://www.kemenkeu.go.id/feed",
    "dpr": "https://www.dpr.go.id/rss",
    "setneg": "https://www.setneg.go.id/feed/",
    "bkn": "https://www.bkn.go.id/feed/",
    "kominfo": "https://www.kominfo.go.id/feed",
    "ekon": "https://ekon.go.id/feed/",
    "antaranews_politik": "https://www.antaranews.com/rss/politik",
}

IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)

def extract_image(entry):
    # 1. media_content / thumbnail
    if hasattr(entry, 'media_content'):
        for m in entry.media_content:
            if m.get('url'):
                return m['url']
    if hasattr(entry, 'media_thumbnail'):
        for m in entry.media_thumbnail:
            if m.get('url'):
                return m['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            url = enc.get('href') or enc.get('url')
            if url and any(url.lower().endswith(ext) for ext in ('.jpg','.jpeg','.png','.webp')):
                return url
    # 2. Dari description yang ada <img src>
    desc = entry.get('description','') or entry.get('summary','')
    m = IMG_RE.search(desc)
    if m:
        return m.group(1)
    if hasattr(entry, 'content'):
        for c in entry.content:
            m2 = IMG_RE.search(c.get('value',''))
            if m2:
                return m2.group(1)
    return None

def clean_description(html):
    if not html:
        return ""
    # Hapus img tag biar gak muncul seperti di screenshot kamu
    html = IMG_RE.sub('', html)
    # Strip semua tag HTML sisa
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300] + "..." if len(text) > 300 else text

def fetch_all():
    items = []
    for category, url in RSS_SOURCES.items():
        try:
            print(f"Fetching {category}: {url}")
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                img = extract_image(e)
                real_cat = category
                if "antaranews" in category:
                    t = (e.get('title','') + ' ' + e.get('description','')).lower()
                    if "kemenkeu" in t or "menkeu" in t or "keuangan" in t:
                        real_cat = "kemenkeu"
                    elif "dpr" in t:
                        real_cat = "dpr"
                    elif "kejaksaan" in t or "setneg" in t or "presiden" in t or "prabowo" in t:
                        real_cat = "setneg"
                    else:
                        real_cat = "setkab"
                guid = e.get('id') or e.get('link')
                # Fallback gambar unik kalau tetap gak ketemu
                if not img:
                    img = f"https://picsum.photos/seed/{hashlib.md5(guid.encode()).hexdigest()[:6]}/800/450"

                items.append({
                    "title": e.get('title','').strip(),
                    "link": e.get('link',''),
                    "guid": guid,
                    "pubDate": e.get('published','') or e.get('updated',''),
                    "description": clean_description(e.get('description','') or e.get('summary','')),
                    "source": e.get('link','').split('/')[2] if e.get('link') else category,
                    "category": real_cat,
                    "image": img
                })
        except Exception as ex:
            print(f"Error {category}: {ex}")

    seen = {}
    for it in items:
        key = it['guid'] or it['link']
        if key not in seen:
            seen[key] = it
    deduped = list(seen.values())
    def parse_date(s):
        try:
            return datetime.strptime(s[:25], "%a, %d %b %Y %H:%M:%S")
        except:
            return datetime.min
    deduped.sort(key=lambda x: parse_date(x['pubDate']), reverse=True)
    return deduped[:80]

def push_to_kv(items):
    account = os.environ.get("CF_ACCOUNT_ID")
    namespace = os.environ.get("CF_NAMESPACE_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not all([account, namespace, token]):
        print("Missing CF secrets, saving local only")
        with open("rekap-pemerintahan.json","w",encoding="utf-8") as f:
            json.dump({"last_updated": datetime.utcnow().isoformat(), "total": len(items), "items": items}, f, ensure_ascii=False, indent=2)
        return
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{namespace}/values/pemerintahan-rss"
    payload = {"last_updated": datetime.utcnow().isoformat(), "total": len(items), "items": items}
    r = requests.put(url, headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"}, data=json.dumps(payload))
    print(f"KV Push status: {r.status_code}")
    print(r.text[:500])
    if r.status_code != 200:
        raise Exception(f"KV Push failed: {r.text}")

if __name__ == "__main__":
    data = fetch_all()
    print(f"Total fetched: {len(data)}")
    push_to_kv(data)
