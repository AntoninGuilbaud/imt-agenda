import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from flask import Flask, Response, abort, jsonify, request

app = Flask(__name__)
cache_lock = threading.Lock()
cached_ics = None
cached_at = None


def api_request(path, method="GET", body=None, token=None):
    base_url = os.environ["REX_BASE_URL"].rstrip("/")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{base_url}/api/v2{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"REX API returned HTTP {error.code}: {detail[:300]}") from error


def login():
    result = api_request(
        "/auth/login",
        "POST",
        {
            "identifiant": os.environ["REX_IDENTIFIANT"],
            "password": os.environ["REX_MOT_DE_PASSE"],
        },
    )
    for key in ("accessToken", "access_token", "token", "jwt"):
        if isinstance(result.get(key), str):
            return result[key]
    raise RuntimeError("La réponse de connexion REX ne contient pas de jeton.")


def event_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "programme", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise RuntimeError("Format de programme REX inattendu.")


def value(event, *names):
    return next((event[name] for name in names if event.get(name) not in (None, "")), "")


def parse_datetime(raw):
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000 if raw > 10**11 else raw)
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(raw, pattern)
            except ValueError:
                continue
    return None


def escape_ics(raw):
    return str(raw).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fetch_ics():
    token = login()
    start = date.today().replace(day=1)
    end = (start + timedelta(days=370)).replace(day=1)
    query = urllib.parse.urlencode({"start": start.isoformat(), "end": end.isoformat()})
    events = event_list(api_request(f"/programme?{query}", token=token))
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//REX Mines Ales//Programme//FR",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Programme REX",
    ]
    for index, event in enumerate(events):
        start_value = value(event, "start", "dateDebut", "debut", "startDate", "date_start")
        end_value = value(event, "end", "dateFin", "fin", "endDate", "date_end")
        start_dt = parse_datetime(start_value)
        if not start_dt:
            continue
        end_dt = parse_datetime(end_value) or (start_dt + timedelta(hours=1))
        uid = value(event, "id", "uuid") or f"{start_dt.isoformat()}-{index}"
        title = value(event, "title", "cours", "matiere", "name", "label") or "Cours"
        location = value(event, "location", "salle", "room", "lieu")
        description = value(event, "description", "enseignant", "professeur", "teacher")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{escape_ics(uid)}@rex-mines-ales",
                f"DTSTAMP:{now}",
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{escape_ics(title)}",
                f"LOCATION:{escape_ics(location)}",
                f"DESCRIPTION:{escape_ics(description)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def get_cached_ics():
    global cached_ics, cached_at
    max_age = int(os.getenv("CACHE_MINUTES", "60")) * 60
    with cache_lock:
        if cached_ics is None or cached_at is None or (datetime.now() - cached_at).total_seconds() >= max_age:
            cached_ics = fetch_ics()
            cached_at = datetime.now()
        return cached_ics


@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "rex-agenda"})


@app.get("/agenda.ics")
def agenda():
    expected = os.environ.get("AGENDA_TOKEN")
    if not expected or not secrets.compare_digest(request.args.get("token", ""), expected):
        abort(404)
    try:
        content = get_cached_ics()
    except (KeyError, RuntimeError, urllib.error.URLError) as error:
        app.logger.error("Agenda refresh failed: %s", error)
        return Response("Agenda temporairement indisponible", status=503)
    return Response(
        content,
        mimetype="text/calendar",
        headers={"Cache-Control": "public, max-age=3600"},
    )
