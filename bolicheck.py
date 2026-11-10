"""Local demo server and dispatch count checks for BoliCheck."""

import argparse
from getpass import getpass
import io
import json
import os
from pathlib import Path
import re
from secrets import compare_digest
import socket
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
STT_URL = "https://api.vachana.ai/stt/v3"
MODEL = os.getenv("GNANI_MODEL", "prisma-v3.0")
MAX_AUDIO_BYTES = 1_000_000
MANIFEST = {
    "crates": {"label": "Blue crates", "expected": 24},
    "cartons": {"label": "Sealed cartons", "expected": 12},
}
ITEM_WORDS = {
    "crates": set("blue crate crates ब्लू क्रेट क्रेट्स नीले नीला नीली".split()),
    "cartons": set("sealed carton cartons सील सील्ड कार्टन कार्टन्स कार्टनस".split()),
}
FILLER = set("count total actual pieces piece units unit for the is are there we have hain hai है हैं का की के में हमारे गिनती कुल पीस नग यूनिट sir जी बस only".split())
HINDI_COUNTS = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्नासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
)
ENGLISH_SMALL = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
ENGLISH_TENS = "twenty thirty forty fifty sixty seventy eighty ninety"
COUNT_WORDS = {word: count for count, word in enumerate(HINDI_COUNTS.split())}
COUNT_WORDS.update({word: count for count, word in enumerate(ENGLISH_SMALL.split())})
COUNT_WORDS.update({word: count * 10 for count, word in enumerate(ENGLISH_TENS.split(), 2)})
TENS = set(ENGLISH_TENS.split())
UNITS = set(ENGLISH_SMALL.split()[1:10])
for count, aliases in {
    0: "जीरो ज़ीरो shunya", 1: "ek", 2: "do", 3: "teen", 4: "chaar char",
    5: "पांच panch paanch", 6: "छः छे chhe cheh", 7: "saat", 8: "aath", 9: "nau",
    10: "das", 11: "gyarah gyaarah", 12: "baarah barah baraah",
    13: "terah tera", 14: "chaudah chaudha choudah", 15: "पन्द्रह pandrah",
    16: "solah", 17: "satrah", 18: "atharah athaarah", 19: "unnees unnis",
    20: "bees bis", 21: "ikkees ikkis", 22: "बाइस baais bais", 23: "teis teiis",
    24: "चौबिस chaubees chaubis choubees choubis", 25: "pachees pachis",
    26: "chhabbees chhabbis", 27: "sattais sattaaees", 28: "अठाईस atthais athais",
    29: "untees", 30: "tees", 40: "chalees", 50: "pachaas", 60: "saath",
    70: "sattar", 80: "assee", 90: "nabbe",
}.items():
    COUNT_WORDS.update({unicodedata.normalize("NFKC", word): count for word in aliases.split()})


def read_count(transcript, item):
    """Accept one exact quantity in a short count phrase for the selected item."""
    normalized = unicodedata.normalize("NFKC", transcript).casefold().strip()
    if re.search(r"[+−~±%/?？]|[.,](?=\d)|(?<=\d)[:-](?=\d)|(?<!\w)[-–—]\s*\d", normalized):
        return None, "Say one whole count from 0 to 99."
    tokens = re.sub(r"[.,।!;:–—-]", " ", normalized).split()
    allowed = ITEM_WORDS[item] | FILLER
    counts = []
    position = 0
    while position < len(tokens):
        word = tokens[position]
        position += 1
        if word.isdecimal() and len(word) <= 2:
            counts.append(int(word))
        elif word in COUNT_WORDS:
            count = COUNT_WORDS[word]
            if word in TENS and position < len(tokens) and tokens[position] in UNITS:
                count += COUNT_WORDS[tokens[position]]
                position += 1
            counts.append(count)
        elif word not in allowed:
            return None, "Say only the selected item’s final count."
    if len(counts) != 1:
        return None, "Say one final count for this item."
    return counts[0], None


def compare(transcript, item):
    count, reason = read_count(transcript, item)
    expected = MANIFEST[item]["expected"]
    if count is None:
        return {"state": "recount", "heard": None, "detail": reason}
    difference = count - expected
    if difference:
        direction = "short" if difference < 0 else "over"
        return {"state": "mismatch", "heard": count, "detail": f"{abs(difference)} {direction}. Recount this item."}
    return {"state": "match", "heard": count, "detail": "Matches the manifest."}


def check_audio(audio):
    try:
        with wave.open(io.BytesIO(audio), "rb") as clip:
            frames = clip.getnframes()
            if (clip.getnchannels(), clip.getsampwidth(), clip.getframerate()) != (1, 2, 16000):
                raise ValueError
            if not 0 < frames <= 30 * 16000 or len(clip.readframes(frames)) != frames * 2:
                raise ValueError
    except (wave.Error, EOFError, ValueError) as exc:
        raise ValueError("Use a valid recording between 0 and 30 seconds.") from exc


def speech_request(audio, key):
    boundary = uuid4().hex
    fields = {"language_code": "hi-IN", "format": "transcribe"}
    if MODEL == "prisma-v3.0":
        fields.update(model=MODEL, language_code="hi-IN,en-IN")
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.extend([
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio_file"; filename="count.wav"\r\n'
        'Content-Type: audio/wav\r\n\r\n'.encode(),
        audio,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return Request(STT_URL, data=b"".join(parts), headers={
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "BoliCheck/1.0",
        "X-API-Key-ID": key,
    })


def transcribe(audio, key):
    with urlopen(speech_request(audio, key), timeout=35) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Gnani returned an unexpected response.")
    transcript = payload.get("transcript")
    if payload.get("success") is not True or not isinstance(transcript, str):
        raise ValueError("Gnani returned no usable transcript. Try a shorter recording.")
    return transcript.strip(), payload.get("model") or MODEL


def local_api_key():
    path = ROOT / ".env"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "GNANI_API_KEY":
            return value.strip()
    return ""


class Handler(BaseHTTPRequestHandler):
    hosted = False

    def route(self):
        request = urlsplit(self.path)
        if request.path != "/api/dispatch":
            return request.path
        query = parse_qs(request.query)
        action = query.get("action", [""])[0]
        if action == "config":
            return "/api/config"
        return f"/api/{action}/{query.get('item', [''])[0]}"

    def reply(self, status, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = self.route()
        if route == "/api/config":
            live = bool(os.getenv("GNANI_API_KEY")) and (not self.hosted or bool(os.getenv("BOLICHECK_VOICE_CODE")))
            self.reply(200, {"manifest": MANIFEST, "live": live, "model": MODEL, "hosted": self.hosted})
            return
        assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
        asset = assets.get(route)
        if asset is None:
            self.reply(404, {"error": "Page not found."})
            return
        filename, mime = asset
        self.reply(200, (ROOT / "web" / filename).read_bytes(), f"{mime}; charset=utf-8")

    def do_POST(self):
        endpoint, _, item = self.route().rpartition("/")
        if endpoint not in {"/api/count", "/api/voice"} or item not in MANIFEST:
            self.reply(404, {"error": "Unknown manifest item."})
            return
        voice = endpoint == "/api/voice"
        if voice:
            key = os.getenv("GNANI_API_KEY")
            code = os.getenv("BOLICHECK_VOICE_CODE")
            if not key or (self.hosted and not code):
                message = "Live speech is not configured for this deployment." if self.hosted else "Set GNANI_API_KEY and restart the app to use live speech."
                self.reply(503, {"error": message})
                return
            if self.hosted and not compare_digest(self.headers.get("X-BoliCheck-Voice-Code", "").encode(), code.encode()):
                self.reply(403, {"error": "Enter the demo access code to use live speech."})
                return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= (MAX_AUDIO_BYTES if voice else 2000):
                self.reply(413, {"error": "The input is empty or too large."})
                return
            mime = self.headers.get_content_type()
            required = "audio/wav" if voice else "application/json"
            if mime != required:
                self.reply(415, {"error": "Unsupported input format."})
                return
            body = self.rfile.read(size)
            if voice:
                check_audio(body)
                transcript, model = transcribe(body, key)
                source = f"Gnani {model}"
            else:
                payload = json.loads(body)
                transcript = payload.get("transcript") if isinstance(payload, dict) else None
                if not isinstance(transcript, str) or len(transcript) > 180:
                    raise ValueError("Enter a short count phrase (up to 180 characters).")
                source = "Practice transcript"
        except HTTPError as exc:
            status_messages = {
                401: "Gnani rejected the API key. Check the key in the console.",
                403: "Gnani refused the speech request. Check the key’s Speech-to-Text permissions in the Gnani console.",
                429: "Gnani is rate limiting requests. Wait briefly and try again.",
            }
            self.reply(502, {"error": status_messages.get(exc.code, f"Gnani returned HTTP {exc.code}. Check the recording and API access.")})
            return
        except (URLError, socket.timeout):
            self.reply(502, {"error": "Could not reach Gnani. Check the connection and retry."})
            return
        except ValueError as exc:
            message = "Invalid input or unreadable API response." if isinstance(exc, (json.JSONDecodeError, UnicodeError)) else str(exc)
            self.reply(400, {"error": message})
            return
        self.reply(200, {**compare(transcript, item), "transcript": transcript, "source": source})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--live", action="store_true", help="Prompt privately for the Gnani API key if needed")
    args = parser.parse_args()
    if MODEL not in {"prisma-v2.5", "prisma-v3.0"}:
        parser.error("GNANI_MODEL must be prisma-v3.0 or prisma-v2.5")
    if args.live and not os.getenv("GNANI_API_KEY"):
        key = local_api_key() or getpass("Gnani API key (hidden): ").strip()
        if not key:
            parser.error("Enter a Gnani API key to start in live mode")
        os.environ["GNANI_API_KEY"] = key
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"BoliCheck is ready at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
