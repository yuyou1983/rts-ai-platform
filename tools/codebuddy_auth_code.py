#!/usr/bin/env python3
"""CodeBuddy Authorization Code + OIDC 流程"""

import json, os, time, webbrowser, subprocess, requests, signal, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Event

CLIENT_ID = "cb_7DChDyiVCJCNZywOAVAO"
CLIENT_SECRET = "Ks3jqillugf9YKZZF8ewdJKjYB7WXT3H"
REDIRECT_URI = "http://localhost:6001/callback"
AGENT_ID = "agent_01KWZZZ70MABFJ4CXHTBBBQQ9E"
AGENT_NAME = "客户跟进CRM"
PORT = 6001
STATE = "hermes_crm_" + str(int(time.time()))
DATA_DIR = os.path.expanduser("~/code/rts-ai-platform/tools/.codebuddy")
os.makedirs(DATA_DIR, exist_ok=True)

auth_event = Event()
auth_result = {"code": None, "state": None, "error": None}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            if error:
                auth_result["error"] = error
                self._respond("❌ 授权失败: " + error)
            elif code and state == STATE:
                auth_result["code"] = code
                auth_result["state"] = state
                self._respond("✅ 授权成功！可以关闭此页面。")
            elif code:
                auth_result["error"] = "state_mismatch"
                self._respond("❌ State 不匹配")
            else:
                auth_result["error"] = "no_code"
                self._respond("❌ 未收到授权码")
            auth_event.set()
        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, msg):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body><h1>{msg}</h1></body></html>".encode())

    def log_message(self, *a):
        pass


def main():
    print("=" * 60)
    print("CodeBuddy Authorization Code + OIDC 流程")
    print("=" * 60)

    # 1. Start server
    print(f"\n1️⃣ 启动回调服务器 (:{PORT})...")
    server = HTTPServer(("127.0.0.1", PORT), Handler)

    # 2. Open auth URL
    auth_url = (
        f"https://tencent.sso.copilot.tencent.com/authorize?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={requests.utils.quote(REDIRECT_URI)}&"
        f"response_type=code&"
        f"scope=openid+profile+api:read&"
        f"state={STATE}&"
        f"response_mode=query"
    )
    print(f"\n2️⃣ 打开浏览器授权页面...")
    print(f"   请扫码登录 CodeBuddy")
    webbrowser.open(auth_url)

    # 3. Wait for callback
    print(f"\n⏳ 等待授权回调 (最多5分钟)...")
    start = time.time()
    while not auth_event.is_set():
        server.handle_request()
        if time.time() - start > 300:
            print("❌ 超时")
            server.server_close()
            return

    server.server_close()

    if auth_result["error"]:
        print(f"❌ 授权错误: {auth_result['error']}")
        return

    code = auth_result["code"]
    print(f"\n✅ 收到授权码: {code[:20]}...")

    # 4. Exchange for tokens
    print(f"\n3️⃣ 交换用户级 Token...")
    try:
        resp = requests.post(
            "https://www.codebuddy.cn/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"❌ Token 交换失败: {resp.status_code}")
            print(f"   {resp.text[:300]}")
            return

        token_data = resp.json()
        print(f"   ✅ access_token: {token_data['access_token'][:50]}...")
        print(f"   token_type: {token_data.get('token_type', '?')}")
        print(f"   expires_in: {token_data.get('expires_in', '?')}s")
        print(f"   scope: {token_data.get('scope', '?')}")
        if "openid" in token_data:
            print(f"   openid: {token_data.get('openid', '?')}")

        # Save tokens
        token_path = os.path.join(DATA_DIR, "user_token.json")
        with open(token_path, "w") as f:
            json.dump(token_data, f, indent=2)
        print(f"   💾 已保存 → {token_path}")

    except Exception as e:
        print(f"❌ Token 交换异常: {e}")
        return

    # 5. Create runtime with USER-level token
    print(f"\n4️⃣ 创建 AgentOS Runtime (用户级 Token)...")
    try:
        resp = requests.post(
            "https://www.codebuddy.cn/v2/agentos/runtimes",
            headers={
                "Authorization": f"Bearer {token_data['access_token']}",
                "X-Source-App": "hermes-crm-user-auth",
                "Content-Type": "application/json",
            },
            json={
                "runtimeName": "crm-user-token",
                "agentManifest": {
                    "id": AGENT_ID,
                    "name": AGENT_NAME,
                    "manifestVersion": "1.0",
                    "secrets": [{"key": "CODEBUDDY_API_KEY", "value": token_data["access_token"]}],
                },
            },
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            print(f"❌ Runtime 创建失败: {resp.status_code}")
            print(f"   {resp.text[:300]}")
            return

        rt = resp.json()["data"]
        print(f"   ✅ Runtime {rt['id']} ({rt['status']})")
        box_url = rt["links"]["acpLink"]["boxUrl"]
        acp_url = rt["links"]["acpLink"]["url"]
        acp_token = rt["links"]["acpLink"]["token"]
        print(f"   🌐 Box URL: {box_url}")
        print(f"   📡 ACP URL: {acp_url}")

        # Save runtime
        rt_path = os.path.join(DATA_DIR, "user_runtime.json")
        with open(rt_path, "w") as f:
            json.dump({
                "runtime_id": rt["id"],
                "status": rt["status"],
                "acp_url": acp_url,
                "acp_token": acp_token,
                "box_url": box_url,
                "user_access_token": token_data["access_token"],
                "created_at": time.time(),
            }, f, indent=2)

    except Exception as e:
        print(f"❌ Runtime 创建异常: {e}")
        return

    # 6. Open browser + ACP chat
    print(f"\n5️⃣ 等待沙箱启动 (12s)...")
    time.sleep(12)

    # Open browser as backup
    webbrowser.open(box_url)
    print(f"   🌐 已打开浏览器备选: {box_url}")

    # 7. ACP chat
    print(f"\n6️⃣ ACP 聊天测试...")
    h_file = f"/tmp/acp_h_u_{int(time.time())}.txt"
    s_file = f"/tmp/acp_sse_u_{int(time.time())}.txt"

    sse_proc = subprocess.Popen(
        ["curl", "-s", "-N", "--no-buffer", "-D", h_file, "-o", s_file,
         acp_url, "-H", f"Authorization: Bearer {acp_token}",
         "-H", "Accept: text/event-stream"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)

    conn_id = None
    try:
        with open(h_file) as f:
            for line in f:
                if "acp-connection-id" in line.lower():
                    conn_id = line.split(":", 1)[1].strip()
                    break
    except:
        pass

    if not conn_id:
        print("❌ 未获取 Connection ID")
        sse_proc.terminate()
        return

    print(f"   ✅ 连接: {conn_id[:20]}...")

    ph = [
        "-H", f"Authorization: Bearer {acp_token}",
        "-H", f"Acp-Connection-Id: {conn_id}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream",
    ]

    # Initialize
    subprocess.run(
        ["curl", "-s", "-X", "POST", acp_url] + ph + [
            "-d", json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": True}, "terminal": True},
                    "clientInfo": {"name": "hermes-crm-user", "version": "1.0"},
                }
            })
        ], timeout=15, capture_output=True)
    time.sleep(3)

    # Session new
    subprocess.run(
        ["curl", "-s", "-X", "POST", acp_url] + ph + [
            "-d", json.dumps({
                "jsonrpc": "2.0", "id": 2, "method": "session/new",
                "params": {"cwd": "/workspace", "mcpServers": []}
            })
        ], timeout=15, capture_output=True)
    time.sleep(5)

    # Get session ID
    session_id = None
    with open(s_file) as f:
        for line in f.read().split("\n"):
            if line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                    if d.get("id") == 2 and "result" in d:
                        session_id = d["result"].get("sessionId")
                        break
                except:
                    pass

    print(f"   ✅ Session: {session_id}")

    # Prompt
    msg = "你好，请用1-2句话介绍你能做什么"
    subprocess.run(
        ["curl", "-s", "-X", "POST", acp_url] + ph + [
            "-d", json.dumps({
                "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"role": "user", "type": "text", "content": msg}],
                }
            }, ensure_ascii=False)
        ], timeout=15, capture_output=True)

    # Wait for response
    print(f"\n💬 等待 Agent 回复...")
    time.sleep(30)

    with open(s_file) as f:
        sse_data = f.read()

    full_text = ""
    for line in sse_data.split("\n"):
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                m = d.get("method", "")
                p = d.get("params", {})
                u = p.get("update", {})

                if "agent_message_chunk" in m or u.get("sessionUpdate") == "agent_message_chunk":
                    text = u.get("content", {}).get("text", "")
                    if text:
                        full_text += text
                        print(text, end="", flush=True)

                if "agent_message" in m or u.get("sessionUpdate") == "agent_message":
                    text = u.get("content", {}).get("text", "")
                    if text and not full_text:
                        full_text = text
                        print(text, end="", flush=True)

                if d.get("id") == 3 and "result" in d:
                    print(f"\n[完成: {d['result'].get('stopReason', '?')}]")

                if "endTurn" in m:
                    print(f"\n[endTurn: {p.get('stopReason', '?')}]")
            except:
                pass

    sse_proc.terminate()

    print(f"\n\n{'='*60}")
    if full_text:
        print(f"✅ 用户级 Token + ACP 聊天成功！")
        print(f"   Agent 回复 ({len(full_text)} 字)")
    else:
        # Check for error
        for line in sse_data.split("\n"):
            if line.startswith("data: ") and "null" in line:
                try:
                    d = json.loads(line[6:])
                    u = d.get("params", {}).get("update", {})
                    text = u.get("content", {}).get("text", "")
                    if "null" in text or "error" in text.lower():
                        print(f"⚠️ Agent 内部错误: {text[:200]}")
                except:
                    pass
        print(f"⚠️ ACP 未收到回复，请在浏览器中测试:")
        print(f"   {box_url}")


if __name__ == "__main__":
    main()
