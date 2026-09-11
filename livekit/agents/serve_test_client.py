import http.server
import socketserver
import json
import threading
import urllib.request
import urllib.parse
import base64
from urllib.parse import urlparse, parse_qs
from livekit import api

import os
from dotenv import load_dotenv

load_dotenv()

PORT = 8080

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+19453058074")

def place_twilio_outbound_call(to_number, language="en-IN"):
    sip_uri = os.getenv("LIVEKIT_SIP_ENDPOINT") or "jkr-ai-calling-bfz7gt4b.sip.livekit.cloud"
    from_number = os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("TWILIO_FROM_NUMBER") or "+19453058074"

    # Connect the phone call directly to LiveKit AI agent via SIP bridge so AI actively talks and listens
    twiml = f'<Response><Dial callerId="{from_number}"><Sip>sip:{from_number}@{sip_uri};transport=tcp</Sip></Dial></Response>'

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"
    data = urllib.parse.urlencode({
        "To": to_number,
        "From": from_number,
        "Twiml": twiml
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data)
    auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    req.add_header("Authorization", f"Basic {b64_auth}")

    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)

def generate_token(room_name="test-voice-room", identity="caller-ui", name="Caller UI"):
    return (
        api.AccessToken("devkey", "secret")
        .with_identity(identity)
        .with_name(name)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

class TestClientHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dial":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            phone_number = data.get("phoneNumber", "").strip()
            language = data.get("language", "en-IN")
            speaker = data.get("speaker", "shubh")
            
            room_name = "test-voice-room"
            token = generate_token(room_name=room_name, identity="caller-ui", name="Dialer UI")

            twilio_status = "Dialing..."
            twilio_sid = None
            try:
                print(f"[Dialer] Triggering real Twilio phone call to {phone_number}...")
                tw_res = place_twilio_outbound_call(phone_number, language=language)
                twilio_sid = tw_res.get("sid")
                twilio_status = tw_res.get("status")
                print(f"[Dialer] Twilio Call Placed! SID: {twilio_sid}, Status: {twilio_status}")
            except Exception as e:
                print(f"[Dialer] Twilio Error: {e}")
                twilio_status = f"Error: {e}"

            res = {
                "success": True,
                "roomName": room_name,
                "phoneNumber": phone_number,
                "language": language,
                "speaker": speaker,
                "token": token,
                "twilioSid": twilio_sid,
                "twilioStatus": twilio_status,
                "wsUrl": "ws://localhost:7880",
                "message": f"Twilio call dispatched to {phone_number} ({twilio_status})",
            }

            response_data = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(response_data)))
            self.end_headers()
            self.wfile.write(response_data)
            return

        super().do_POST()

    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if parsed.path == "/token":
            query = parse_qs(parsed.query)
            room_name = query.get("room", ["test-voice-room"])[0]
            token = generate_token(room_name=room_name)

            response_data = json.dumps({"token": token, "wsUrl": "ws://localhost:7880"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(response_data)))
            self.end_headers()
            self.wfile.write(response_data)
            return

        if parsed.path == "/" or parsed.path.startswith("/?"):
            token = generate_token(room_name="test-voice-room")
            with open("test_browser_client.html", "r", encoding="utf-8") as f:
                html = f.read()
            
            html = html.replace(
                "let serverInjectedToken = \"\";",
                f"let serverInjectedToken = \"{token}\";"
            )
            
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        super().do_GET()

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TestClientHandler) as httpd:
        print(f"\n=======================================================")
        print(f" JKR AI Calling Dashboard: http://localhost:{PORT}")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dashboard server.")
