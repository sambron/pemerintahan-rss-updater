# .github/scripts/update_kv.py
# Jalan di GitHub Actions (IP GitHub, bukan Cloudflare Worker, jadi lolos anti-bot Cloudflare)
# Tugas: fetch 5 feed terverifikasi lalu push ke KV pemerintahan-cache

import requests, os, json
from datetime import datetime
import feedparser

FEEDS = [
  "https://setkab.go.id/feed/",
  "https://www.cnnindonesia.com/nasional/rss",
  "https://www.antaranews.com/rss/politik",
  "https://www.antaranews.com/rss/hukum",
  "https://www.antaranews.com/rss/ekonomi"
]

KEYWORDS = {
  "kemenkeu": ["kemenkeu","keuangan","apbn","pajak","sri mulyani","purbaya"],
  "dpr": ["dpr","parlemen","legislator","senayan","ruu","rapat paripurna"],
  "setneg": ["setneg","sekretariat negara","istana","presiden prabowo","keppres","perpres"],
  "komdigi": ["komdigi","kominfo","digital","internet","judi online","literasi digital"],
  "asn": ["menpan","panrb","asn","pppk","cpns","bkn","berakhlak"],
  "setkab": ["setkab","sekretariat kabinet","kabinet","sidang kabinet","asta cita"],
  "ekonomi": ["perekonomian","airlangga","ekonomi","investasi","inflasi","umkm"]
}

def classify(text):
    t = text.lower()
    for cat, kws in KEYWORDS.items():
        for kw in kws:
            if kw in t:
                return cat
    return "setkab"

def label_for(cat):
    m = {"kemenkeu":"Kemenkeu","setneg":"Setneg","dpr":"DPR RI","setkab":"Setkab","asn":"MenPAN-RB","komdigi":"Komdigi","ekonomi":"Perekonomian"}
    return m.get(cat,"Setkab")

def image_for(cat):
    base = "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800"
    return base

all_items = []
for feed_url in FEEDS:
    try:
        print(f"Fetching {feed_url}")
        d = feedparser.parse(feed_url)
        for e in d.entries[:15]:
            title = e.get('title','')
            if not title: continue
            desc = e.get('description', title)
            link = e.get('link','')
            pub = e.get('published', datetime.utcnow().isoformat())
            cat = classify(title + " " + desc)
            all_items.append({
                "title": title,
                "description": desc[:220],
                "link": link,
                "pubDate": pub,
                "guid": link,
                "source": label_for(cat),
                "category": cat,
                "image": image_for(cat)
            })
        print(f"  -> {len(d.entries)} entries")
    except Exception as ex:
        print(f"  FAIL {feed_url}: {ex}")

# de-duplicate & sort terbaru di atas
seen=set()
uniq=[]
# sort by pubDate descending (simple string sort is ok)
for it in sorted(all_items, key=lambda x: x['pubDate'], reverse=True):
    if it['guid'] not in seen:
        seen.add(it['guid'])
        uniq.append(it)
    if len(uniq)>=80:
        break

print(f"Total uniq {len(uniq)}")

# Push ke Cloudflare KV
ACCOUNT_ID = os.environ['CF_ACCOUNT_ID']
NAMESPACE_ID = os.environ['CF_NAMESPACE_ID']
API_TOKEN = os.environ['CF_API_TOKEN']
KV_KEY = "pemerintahan_agregat_v9"

payload = {
    "items": uniq,
    "lastUpdate": datetime.utcnow().isoformat(),
    "total": len(uniq),
    "source": "github-actions"
}

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/{KV_KEY}"
headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type":"application/json"}
r = requests.put(url, headers=headers, data=json.dumps(payload))
print(f"KV push status {r.status_code}")
print(r.text[:500])
if r.status_code != 200:
    raise SystemExit("KV push failed - cek API Token & ID")
print("SUKSES!")
