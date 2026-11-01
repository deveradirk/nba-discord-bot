import html
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as XML

WEBHOOK = os.environ["WEBHOOK_NEWS"]
UA = {"User-Agent": "Mozilla/5.0 (nba-discord-bot)"}
STATE = "seen.json"
MAX_POSTS = 8

FEEDS = [
    ("ESPN", "https://www.espn.com/espn/rss/nba/news"),
    ("CBS Sports", "https://www.cbssports.com/rss/headlines/nba/"),
]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **UA},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


first_run = not os.path.exists(STATE)
seen = [] if first_run else json.load(open(STATE))
seen_set = set(seen)

to_post = []
for source, url in FEEDS:
    try:
        root = XML.fromstring(fetch(url))
    except Exception as e:
        print(f"Feed failed ({source}): {e}")
        continue
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
            "source": source,
        })
    new = [i for i in items if i["key"] not in seen_set]
    if first_run:
        new = new[:3]  # don't flood the channel on the first run
    to_post.extend(new)
    seen.extend(i["key"] for i in items if i["key"] not in seen_set)
    seen_set.update(i["key"] for i in items)

for item in list(reversed(to_post))[-MAX_POSTS:]:
    post({
        "embeds": [{
            "title": item["title"][:256],
            "url": item["link"],
            "description": item["desc"],
            "color": 0x1D428A,
            "footer": {"text": item["source"]},
        }]
    })
    time.sleep(1.5)

json.dump(seen[-500:], open(STATE, "w"))
print(f"Posted {min(len(to_post), MAX_POSTS)} news items")
