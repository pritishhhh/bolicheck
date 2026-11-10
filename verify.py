"""Check count decisions and the local API without spending Gnani credits."""

from email import policy
from email.parser import BytesParser
from http.client import HTTPConnection
import io
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
import wave

import bolicheck
from api.dispatch import handler as HostedHandler


class CountChecks(unittest.TestCase):
    def test_transcript_cases(self):
        cases = [
            ("crates", "Blue crates चौदह हैं", "mismatch", 14),
            ("crates", "Blue crates count is २४", "match", 24),
            ("crates", "Blue crates चौबीस हैं।", "match", 24),
            ("crates", "twenty-four", "match", 24),
            ("crates", "नीले क्रेट chaubees हैं", "match", 24),
            ("crates", "Twenty five crates", "mismatch", 25),
            ("crates", "0", "mismatch", 0),
            ("crates", "चौदह नहीं, चौबीस", "recount", None),
            ("crates", "24 14", "recount", None),
            ("crates", "about 24 crates", "recount", None),
            ("crates", "not 24", "recount", None),
            ("crates", "24 cartons", "recount", None),
            ("crates", "count:-24", "recount", None),
            ("crates", "–24", "recount", None),
            ("crates", "24.5", "recount", None),
            ("crates", ".24", "recount", None),
            ("crates", "one hundred twenty four", "recount", None),
            ("crates", "", "recount", None),
            ("cartons", "Sealed cartons बारह हैं", "match", 12),
            ("cartons", "सील्ड कार्टन 10 हैं", "mismatch", 10),
            ("cartons", "बारह?", "recount", None),
        ]
        for item, text, state, heard in cases:
            with self.subTest(item=item, text=text):
                result = bolicheck.compare(text, item)
                self.assertEqual((result["state"], result["heard"]), (state, heard))


class LocalAPI(unittest.TestCase):
    def setUp(self):
        self.server = bolicheck.ThreadingHTTPServer(("127.0.0.1", 0), bolicheck.Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.connection.close)

    def request(self, method, path, body=None, mime="application/json", headers=None):
        self.connection.request(method, path, body, {"Content-Type": mime, **(headers or {})})
        response = self.connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if response.headers.get_content_type() == "application/json" else raw

    def test_practice_route(self):
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Dispatch manifest", page)
        self.assertTrue(Path(bolicheck.ROOT / "web" / "app.js").is_file())
        status, result = self.request("POST", "/api/count/crates", b'{"transcript":"14"}')
        self.assertEqual((status, result["state"], result["source"]), (200, "mismatch", "Practice transcript"))
        self.assertIn("10 short", result["detail"])

    def test_hosted_voice_requires_code(self):
        self.server.RequestHandlerClass = HostedHandler
        path = "/api/dispatch?action=voice&item=crates"
        with patch.dict(bolicheck.os.environ, {"GNANI_API_KEY": "test-key", "BOLICHECK_VOICE_CODE": ""}):
            status, config = self.request("GET", "/api/dispatch?action=config")
            self.assertEqual((status, config["hosted"], config["live"]), (200, True, False))
            self.assertEqual(self.request("POST", path, b"bad wav", "audio/wav")[0], 503)
        with patch.dict(bolicheck.os.environ, {"GNANI_API_KEY": "test-key", "BOLICHECK_VOICE_CODE": "test-code"}):
            self.assertEqual(self.request("POST", path, b"bad wav", "audio/wav")[0], 403)
            status, _ = self.request("POST", path, b"bad wav", "audio/wav", {"X-BoliCheck-Voice-Code": "test-code"})
            self.assertEqual(status, 400)
            status, result = self.request("POST", "/api/dispatch?action=count&item=crates", b'{"transcript":"24"}')
            self.assertEqual((status, result["state"]), (200, "match"))

    def test_voice_route_and_gnani_request_contract(self):
        # The zeroed WAV is for wire-format validation. The transcript is stubbed.
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as clip:
            clip.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            clip.writeframes(b"\0" * 3200)
        audio = buffer.getvalue()

        def gnani_stub(request, timeout):
            self.assertEqual(request.full_url, bolicheck.STT_URL)
            self.assertEqual(request.get_header("X-api-key-id"), "test-key")
            self.assertEqual(request.get_header("User-agent"), "BoliCheck/1.0")
            mime = request.get_header("Content-type")
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {mime}\r\nMIME-Version: 1.0\r\n\r\n".encode() + request.data
            )
            parts = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                     for part in message.iter_parts()}
            self.assertEqual(parts, {"language_code": b"hi-IN,en-IN", "format": b"transcribe",
                                     "model": b"prisma-v3.0", "audio_file": audio})
            return io.BytesIO(b'{"success":true,"transcript":"Blue crates 24","model":"prisma-v3.0"}')

        with patch.dict(bolicheck.os.environ, {"GNANI_API_KEY": "test-key"}), \
             patch.object(bolicheck, "MODEL", "prisma-v3.0"), patch.object(bolicheck, "urlopen", gnani_stub):
            status, result = self.request("POST", "/api/voice/crates", audio, "audio/wav")
            self.assertEqual((status, result["state"], result["source"]), (200, "match", "Gnani prisma-v3.0"))
            status, _ = self.request("POST", "/api/voice/crates", b"bad wav", "audio/wav")
            self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
