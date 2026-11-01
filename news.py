import html
import json
import os
import re
import time
import urllib.request

WEBHOOK = os.environ["WEBHOOK_NEWS"]
UA = "nba-discord-bot/1.0 (GitHub Actions; github.com/deveradirk/nba-discord-bot)"
STATE = "seen.json"

MIN_SCORE = 3000           # upvotes needed to count as "viral"
BREAKING_MIN_SCORE = 300   # upvotes needed for breaking-news style posts
MAX_POSTS = 6              # max posts per run
SOURCE_URL = "https://www.reddit.com/r/nba/hot.json?limit=50&raw_json=1"

IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")

BREAKING_WORDS = [
    "breaking", "trade", "traded", "waived", "released", "signs", "signing",
    "agrees to", "extension", "injury", "injured", "out for", "ruled out",
    "suspended", "fired", "hired", "retire", "buyout", "free agent",
    "per sources", "sources:",
]
INSIDERS = [
    "charania", "shams", "windhorst", "haynes", "stein", "wojnarowski",
    "woj", "fischer", "mcmenamin", "begley", "lowe", "scotto",
]


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def pick_image(p):
    imgs = (p.get("preview") or {}).get("images") or []
    if imgs:
        return html.unescape(imgs[0]["source"]["url"])
    url = p.get("url_overridden_by_dest") or p.get("url") or ""
    if url.lower().split("?")[0].endswith(IMG_EXT):
        return url
    thumb = p.get("thumbnail") or ""
    if thumb.startswith("http"):
        return thumb
    return None


def is_breaking(p):
    text = (p.get("title", "") + " " + (p.get("link_flair_text") or "")).lower()
    if any(w in text for w in BREAKING_WORDS):
        return True
    return any(re.search(rf"\b{name}\b", text) for name in INSIDERS)


first_run = not os.path.exists(STATE)
seen = [] if first_run else json.load(open(STATE))
seen_set = set(seen)

try:
    posts = [c["data"] for c in get_json(SOURCE_URL)["data"]["children"]]
except Exception as e:
    raise SystemExit(f"Could not load r/nba: {e}")

picked = []
for p in posts:
    if p.get("stickied") or p.get("over_18"):
        continue
    if "game thread" in p.get("title", "").lower():
        continue
    key = "reddit:" + p["id"]
    if key in seen_set:
        continue
    score = p.get("score", 0)
    if score >= MIN_SCORE:
        label = "🔥 VIRAL"
    elif score >= BREAKING_MIN_SCORE and is_breaking(p):
        label = "🚨 BREAKING"
    else:
        continue
    picked.append((key, label, p))

picked.sort(key=lambda x: x[2]["score"])  # hottest last
picked = picked[-MAX_POSTS:]

for key, label, p in picked:
    flair = f" • {p['link_flair_text']}" if p.get("link_flair_text") else ""
    embed = {
        "title": html.unescape(p["title"])[:256],
        "url": "https://www.reddit.com" + p["permalink"],
        "description": (f"{label}\n⬆️ **{p['score']:,}** upvotes • "
                        f"💬 **{p['num_comments']:,}** comments{flair}"),
        "color": 0xE03131 if "BREAKING" in label else 0xFF4500,
        "footer": {"text": "r/nba • hot posts"},
    }
    image = pick_image(p)
    if image:
        embed["image"] = {"url": image}
    post({"embeds": [embed]})
    seen.append(key)
    time.sleep(1.5)

json.dump(seen[-500:], open(STATE, "w"))
print(f"Posted {len(picked)} posts")
