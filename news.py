import html
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as XML

WEBHOOK = os.environ["WEBHOOK_NEWS"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
STATE = "seen.json"
MAX_POSTS = 8

FEEDS = [
    ("ESPN", "https://www.espn.com/espn/rss/nba/news"),
    ("CBS Sports", "https://www.cbssports.com/rss/headlines/nba/"),
    ("Yahoo Sports", "https://sports.yahoo.com/nba/rss/"),
]


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def find_image(it):
    # Look for media:content, media:thumbnail, or an image enclosure
    for el in it.iter():
        tag = el.tag.split("}")[-1].lower()
        url = el.get("url")
        if tag in ("content", "thumbnail", "enclosure") and url and url.startswith("http"):
            typ = (el.get("type") or "").lower()
            medium = (el.get("medium") or "").lower()
            if tag == "enclosure" and typ and not typ.startswith("image"):
                continue
            if tag == "content" and typ and not typ.startswith("image") and medium != "image":
                continue
            return url
    # Fall back to an <img> tag inside the description
    m = re.search(r'<img[^>]+src="([^"]+)"', it.findtext("description") or "")
    if m and m.group(1).startswith("http"):
        return html.unescape(m.group(1))
    return None


first_run = not os.path.exists(STATE)
seen = [] if first_run else json.load(open(STATE))
seen_set = set(seen)

to_post = []
feeds_ok = 0
for source, url in FEEDS:
    try:
        root = XML.fromstring(fetch(url))
    except Exception as e:
        print(f"Feed failed ({source}): {e}")
        continue
    feeds_ok += 1
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        key = (it.findtext("guid") or link).strip()
        if not key:
            continue
        items.append({
            "key": key,
            "title": clean(it.findtext("title")),
            "link": link,
            "desc": clean(it.findtext("description"))[:200],
            "image": find_image(it),
            "source": source,
        })
    new = [i for i in items if i["key"] not in seen_set]
    if first_run:
        new = new[:3]  # don't flood the channel on the first run
    to_post.extend(new)
    seen.extend(i["key"] for i in items if i["key"] not in seen_set)
    seen_set.update(i["key"] for i in items)
    print(f"Feed OK ({source}): {len(items)} items, {len(new)} new")

if feeds_ok == 0:
    raise SystemExit("All news feeds failed")

for item in list(reversed(to_post))[-MAX_POSTS:]:
    embed = {
        "title": item["title"][:256],
        "url": item["link"],
        "description": item["desc"],
        "color": 0x1D428A,
        "footer": {"text": item["source"]},
    }
    if item["image"]:
        embed["image"] = {"url": item["image"]}
    post({"embeds": [embed]})
    time.sleep(1.5)

json.dump(seen[-500:], open(STATE, "w"))
print(f"Posted {min(len(to_post), MAX_POSTS)} news items")
