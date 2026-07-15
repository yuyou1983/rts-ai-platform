#!/usr/bin/env python3
"""简单的 OAuth 回调服务器 + Token 交换 + AgentOS Runtime"""
import json, os, time, requests, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Event

CLIENT_ID = "cb_7DChDyiVCJCNZywOAVAO"
CLIENT_SECRET = "Ks3jqillugf9YKZZF8ewdJKjYB7WXT3H"
REDIRECT_URI = "http://localhost:6001/callback"
AGENT_ID = "agent_01KWZZZ70MABFJ4CXHTBBBQQ9E"
DATA_DIR = os.path.expanduser("~/code/rts-ai-platform/tools/.codebuddy")
os.makedirs(DATA_DIR, exist_ok=True)

done = Event()
result = {"code": None}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/callback":
            q = parse_qs(p.query)
            code = q.get("code", [None])[0]
            result["code"] = code
            done.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("✅ 授权成功！可以关闭此页面。".encode())
            print(f"\n✅ 收到授权码: {code[:30]}...")
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a): pass

print("1️⃣ 启动回调服务器 :6001")
srv = HTTPServer(("127.0.0.1", 6001), H)

auth_url = (
    "https://www.codebuddy.cn/oauth2/authorize?"
    f"client_id={CLIENT_ID}&"
    f"redirect_uri={requests.utils.quote(REDIRECT_URI)}&"
    "response_type=code&scope=openid&state=hermes123&response_mode=query"
)
print(f"\n2️⃣ 浏览器应已打开授权页面，请扫码登录")
print(f"   如未打开，手动访问:\n   {auth_url}\n")

print("⏳ 等待回调...")
start = time.time()
while not done.is_set():
    srv.handle_request()
    if time.time() - start > 300:
        print("❌ 超时"); srv.server_close(); exit(1)
srv.server_close()

code = result["code"]
if not code:
    print("❌ 无授权码"); exit(1)

# 交换 Token
print(f"\n3️⃣ 交换用户级 Token...")
r = requests.post("https://www.codebuddy.cn/oauth2/token", data={
    "grant_type": "authorization_code",
    "code": code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
}, timeout=15)

if r.status_code != 200:
    print(f"❌ Token 失败: {r.status_code} {r.text[:300]}"); exit(1)

td = r.json()
print(f"✅ Token: {td['access_token'][:50]}...")
print(f"   scope: {td.get('scope','?')}, expires: {td.get('expires_in','?')}s")
if "openid" in td: print(f"   openid: {td['openid']}")

with open(os.path.join(DATA_DIR, "user_token.json"), "w") as f:
    json.dump(td, f, indent=2)

# 创建 Runtime
print(f"\n4️⃣ 创建 AgentOS Runtime...")
r2 = requests.post("https://www.codebuddy.cn/v2/agentos/runtimes", headers={
    "Authorization": f"Bearer {td['access_token']}",
    "X-Source-App": "hermes-crm",
    "Content-Type": "application/json",
}, json={
    "runtimeName": "crm-user-auth",
    "agentManifest": {
        "id": AGENT_ID,
        "name": "客户跟进CRM",
        "manifestVersion": "1.0",
        "secrets": [{"key": "CODEBUDDY_API_KEY", "value": td["access_token"]}],
    }
}, timeout=30)

if r2.status_code not in (200, 201):
    print(f"❌ Runtime 失败: {r2.status_code} {r2.text[:300]}"); exit(1)

rt = r2.json()["data"]
print(f"✅ Runtime {rt['id']} ({rt['status']})")
box_url = rt["links"]["acpLink"]["boxUrl"]
acp_url = rt["links"]["acpLink"]["url"]
acp_token = rt["links"]["acpLink"]["token"]
print(f"🌐 Box: {box_url}")

# 打开浏览器
import webbrowser
webbrowser.open(box_url)

# 等 sandbox 启动后 ACP 聊天
print(f"\n5️⃣ 等待沙箱 (12s)...")
time.sleep(12)

print(f"6️⃣ ACP 聊天...")
h_file = f"/tmp/acp_h_u_{int(time.time())}.txt"
s_file = f"/tmp/acp_sse_u_{int(time.time())}.txt"
proc = subprocess.Popen(
    ["curl", "-s", "-N", "--no-buffer", "-D", h_file, "-o", s_file,
     acp_url, "-H", f"Authorization: Bearer {acp_token}",
     "-H", "Accept: text/event-stream"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(3)
conn_id = None
with open(h_file) as f:
    for line in f:
        if "acp-connection-id" in line.lower():
            conn_id = line.split(":", 1)[1].strip(); break
print(f"   连接: {conn_id[:20]}..." if conn_id else "   ❌ 无连接ID")

ph = ["-H", f"Authorization: Bearer {acp_token}",
      "-H", f"Acp-Connection-Id: {conn_id}",
      "-H", "Content-Type: application/json",
      "-H", "Accept: application/json, text/event-stream"]

subprocess.run(["curl","-s","-X","POST",acp_url]+ph+["-d",
    json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"h","version":"1"}}})
], timeout=15, capture_output=True)
time.sleep(3)

subprocess.run(["curl","-s","-X","POST",acp_url]+ph+["-d",
    json.dumps({"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/workspace","mcpServers":[]}})
], timeout=15, capture_output=True)
time.sleep(5)

sid = None
with open(s_file) as f:
    for line in f.read().split("\n"):
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                if d.get("id") == 2 and "result" in d:
                    sid = d["result"].get("sessionId"); break
            except: pass
print(f"   Session: {sid}")

subprocess.run(["curl","-s","-X","POST",acp_url]+ph+["-d",
    json.dumps({"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{
        "sessionId":sid,"prompt":[{"role":"user","type":"text","content":"你好，请用1-2句话介绍你能做什么"}]
    }}, ensure_ascii=False)
], timeout=15, capture_output=True)

print(f"\n💬 等待回复 (30s)...")
time.sleep(30)

with open(s_file) as f:
    sse = f.read()

text = ""
for line in sse.split("\n"):
    if line.startswith("data: "):
        try:
            d = json.loads(line[6:])
            m = d.get("method","")
            u = d.get("params",{}).get("update",{})
            if "agent_message_chunk" in m or u.get("sessionUpdate") == "agent_message_chunk":
                t = u.get("content",{}).get("text","")
                if t: text += t; print(t, end="", flush=True)
            if "agent_message" in m:
                t = u.get("content",{}).get("text","")
                if t and not text: text = t; print(t, end="", flush=True)
            if d.get("id") == 3 and "result" in d:
                print(f"\n[完成: {d['result'].get('stopReason','?')}]")
            if "endTurn" in m:
                print(f"\n[endTurn: {d.get('params',{}).get('stopReason','?')}]")
        except: pass

proc.terminate()

if not text:
    for line in sse.split("\n"):
        if line.startswith("data: ") and "null" in line:
            try:
                d = json.loads(line[6:])
                u = d.get("params",{}).get("update",{})
                t = u.get("content",{}).get("text","")
                if "null" in t or "error" in t.lower():
                    print(f"\n⚠️ 错误: {t[:200]}")
            except: pass

print(f"\n\n{'='*60}")
print(f"用户级 Token: ✅" if td.get("access_token") else "❌")
print(f"AgentOS Runtime: ✅" if rt.get("id") else "❌")
print(f"ACP 聊天: {'✅' if text else '⚠️ (浏览器备选)'}")
print(f"浏览器: {box_url}")
