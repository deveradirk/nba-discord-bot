import io
import json
import os
import statistics
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

WEBHOOK = os.environ["WEBHOOK_SCHEDULE"]
API_KEY = os.environ["BALLDONTLIE_API_KEY"]
ODDS_KEY = os.environ.get("ODDS_API_KEY", "").strip()
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"
GAMES_PER_MESSAGE = 5  # each game uses 2 embeds, Discord allows 10 per message

# balldontlie abbreviation -> ESPN logo code
LOGO_CODES = {"GSW": "gs", "NOP": "no", "NYK": "ny", "SAS": "sa",
              "UTA": "utah", "WAS": "wsh"}


def logo_url(abbr):
    code = LOGO_CODES.get(abbr, (abbr or "nba").lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{code}.png"


def get_json(url, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def post(embeds, files=None, content=None):
    payload = {"embeds": embeds}
    if content:
        payload["content"] = content
    if not files:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "User-Agent": UA}
    else:
        payload["attachments"] = [
            {"id": i, "filename": name} for i, (name, _) in enumerate(files)
        ]
        boundary = uuid.uuid4().hex
        body = io.BytesIO()
        body.write(("--" + boundary + "\r\n").encode())
        body.write(b'Content-Disposition: form-data; name="payload_json"\r\n')
        body.write(b"Content-Type: application/json\r\n\r\n")
        body.write(json.dumps(payload).encode())
        body.write(b"\r\n")
        for i, (name, blob) in enumerate(files):
            body.write(("--" + boundary + "\r\n").encode())
            body.write(
                ('Content-Disposition: form-data; name="files[%d]"; filename="%s"\r\n'
                 % (i, name)).encode()
            )
            body.write(b"Content-Type: image/png\r\n\r\n")
            body.write(blob)
            body.write(b"\r\n")
        body.write(("--" + boundary + "--\r\n").encode())
        data = body.getvalue()
        headers = {
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "User-Agent": UA,
        }
    req = urllib.request.Request(WEBHOOK, data=data, headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=60).read()


def parse_time(g):
    for key in ("datetime", "status"):
        val = g.get(key)
        if isinstance(val, str) and "T" in val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(PH)
            except ValueError:
                pass
    return None


def nick(name):
    return name.split()[-1].lower()


def load_font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def make_image(away_abbr, home_abbr):
    try:
        w, h = 640, 200
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for abbr, cx in ((away_abbr, 130), (home_abbr, w - 130)):
            logo = Image.open(io.BytesIO(fetch_bytes(logo_url(abbr)))).convert("RGBA")
            logo.thumbnail((170, 170), Image.LANCZOS)
            canvas.paste(logo, (cx - logo.width // 2, (h - logo.height) // 2), logo)
        draw = ImageDraw.Draw(canvas)
        draw.text((w // 2, h // 2), "VS", font=load_font(54),
                  fill=(160, 165, 175, 255), anchor="mm")
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"Image failed ({away_abbr} @ {home_abbr}): {e}")
        return None


def load_odds():
    if not ODDS_KEY:
        print("No ODDS_API_KEY set, skipping lines")
        return {}
    try:
        q = urllib.parse.urlencode({
            "apiKey": ODDS_KEY, "regions": "us",
            "markets": "spreads,totals", "oddsFormat": "american",
        })
        events = get_json(f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds?{q}")
    except Exception as e:
        print(f"Odds failed: {e}")
        return {}
    out = {}
    for ev in events:
        home, away = ev["home_team"], ev["away_team"]
        spreads, totals = [], []
        for bk in ev.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] == "spreads":
                    for o in m.get("outcomes", []):
                        if o["name"] == home and o.get("point") is not None:
                            spreads.append(o["point"])
                elif m["key"] == "totals":
                    for o in m.get("outcomes", []):
                        if o["name"] == "Over" and o.get("point") is not None:
                            totals.append(o["point"])
        out[(nick(home), nick(away))] = (
            statistics.median(spreads) if spreads else None,
            statistics.median(totals) if totals else None,
        )
    return out


def fmt_spread(h, home_abbr, away_abbr):
    if h is None:
        return "N/A"
    if h == 0:
        return "PK (pick'em)"
    if h < 0:
        return f"{home_abbr} {h:g} / {away_abbr} +{-h:g}"
    return f"{away_abbr} -{h:g} / {home_abbr} +{h:g}"


target = (datetime.now(PH) + timedelta(days=1)).date()

dates = [(target + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]
query = urllib.parse.urlencode([("dates[]", d) for d in dates] + [("per_page", 100)])
data = get_json(f"https://api.balldontlie.io/v1/games?{query}", {"Authorization": API_KEY})

games = {}
for g in data.get("data", []):
    start = parse_time(g)
    if start is None or start.date() != target:
        continue
    games[g["id"]] = (start, g["visitor_team"], g["home_team"])

heading = f"🏀 **NBA Games: {target.strftime('%A, %B %d, %Y')}**"

if not games:
    post([], content=heading + "\nNo games scheduled.")
    print("No games")
    raise SystemExit(0)

odds = load_odds()
items = sorted(games.values(), key=lambda x: x[0])
total_games = len(items)

for n, chunk_start in enumerate(range(0, total_games, GAMES_PER_MESSAGE)):
    chunk = items[chunk_start:chunk_start + GAMES_PER_MESSAGE]
    embeds, files = [], []
    for j, (start, away, home) in enumerate(chunk):
        a_abbr = away.get("abbreviation")
        h_abbr = home.get("abbreviation")
        spread, total = odds.get((nick(home["full_name"]), nick(away["full_name"])), (None, None))
        info = {
            "description": (
                f"🕒 **{start.strftime('%I:%M %p').lstrip('0')}** PH time\n"
                f"✈️ **Away:** {away['full_name']}\n"
                f"🏠 **Home:** {home['full_name']} (home court)\n"
                f"📏 **Spread:** {fmt_spread(spread, h_abbr, a_abbr)}\n"
                f"🔢 **Total (O/U):** {'N/A' if total is None else format(total, 'g')}"
            ),
            "color": 0xF58426,
        }
        img = make_image(a_abbr, h_abbr)
        if img:
            name = f"game{len(files)}.png"
            files.append((name, img))
            embeds.append({"image": {"url": f"attachment://{name}"}, "color": 0xF58426})
        else:
            info["thumbnail"] = {"url": logo_url(h_abbr)}
        embeds.append(info)
    is_last_message = chunk_start + GAMES_PER_MESSAGE >= total_games
    if is_last_message:
        embeds[-1]["footer"] = {
            "text": "Lines = sportsbook consensus (US books), not a prediction. Bet responsibly. 18+"
        }
    content = f"{heading} • {total_games} game(s)" if n == 0 else None
    post(embeds, files or None, content)
    time.sleep(1.5)

print(f"Posted {total_games} games for {target}")
