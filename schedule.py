import json
import os
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_SCHEDULE"]
PH = ZoneInfo("Asia/Manila")
UA = {"User-Agent": "Mozilla/5.0 (nba-discord-bot)"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **UA},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


target = (datetime.now(PH) + timedelta(days=1)).date()

# ESPN groups games by US date, so check the days around the PH target date
dates = [(target + timedelta(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
games = {}
for d in dates:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
    for ev in get_json(url).get("events", []):
        start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(PH)
        if start.date() != target:
            continue
        comps = ev["competitions"][0]["competitors"]
        home = next(c for c in comps if c["homeAway"] == "home")["team"]["displayName"]
        away = next(c for c in comps if c["homeAway"] == "away")["team"]["displayName"]
        games[ev["id"]] = (start, away, home)

title = f"🏀 NBA Games: {target.strftime('%A, %B %d, %Y')}"
if games:
    lines = [
        f"`{s.strftime('%I:%M %p').lstrip('0')}`  **{a}** @ **{h}**"
        for s, a, h in sorted(games.values())
    ]
    description = "\n".join(lines)
else:
    description = "No games scheduled."

post({
    "embeds": [{
        "title": title,
        "description": description,
        "color": 0xF58426,
        "footer": {"text": "All times in PH time (PHT)"},
    }]
})
print(f"Posted {len(games)} games for {target}")
