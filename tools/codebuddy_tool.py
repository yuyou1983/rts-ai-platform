#!/usr/bin/env python3
"""
CodeBuddy CRM Agent — AgentOS Runtime + ACP 协议 (完整版)

已验证完整流程:
  ✅ OAuth Token (Client Credentials Grant)
  ✅ 创建 AgentOS Runtime
  ✅ ACP Initialize → 202 Accepted
  ✅ ACP Session/New → 202 Accepted (返回 sessionId)
  ✅ ACP Session/Prompt → 200 OK (流式响应)

使用方式:
    # 与 CRM Agent 聊天
    python3 codebuddy_tool.py chat "请分析腾讯云CVM的Q2销售趋势"
    
    # 仅创建 Runtime
    python3 codebuddy_tool.py create
    
    # 列出 Runtime
    python3 codebuddy_tool.py list

环境变量:
    CODEBUDDY_CLIENT_ID       (默认内置)
    CODEBUDDY_CLIENT_SECRET   (默认内置)
"""

import argparse
import json
import os
import sys
import time
import base64
import requests
import webbrowser
import asyncio
import httpx

# ========== 配置 ==========
OAUTH_URL = "https://www.codebuddy.cn/oauth2/token"
RUNTIME_API = "https://www.codebuddy.cn/v2/agentos/runtimes"
AGENT_ID = "agent_01KWZZZ70MABFJ4CXHTBBBQQ9E"
AGENT_NAME = "客户跟进CRM"

CLIENT_ID = os.environ.get("CODEBUDDY_CLIENT_ID", "cb_7DChDyiVCJCNZywOAVAO")
CLIENT_SECRET = os.environ.get(
    "CODEBUDDY_CLIENT_SECRET", "Ks3jqillugf9YKZZF8ewdJKjYB7WXT3H"
)

DATA_DIR = os.path.expanduser("~/code/rts-ai-platform/tools/.codebuddy")
os.makedirs(DATA_DIR, exist_ok=True)


def get_access_token():
    resp = requests.post(OAUTH_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_runtime(token, name="crm-session"):
    resp = requests.post(RUNTIME_API, headers={
        "Authorization": f"Bearer {token}",
        "X-Source-App": "hermes-crm-agent",
        "Content-Type": "application/json",
    }, json={
        "runtimeName": name,
        "agentManifest": {
            "id": AGENT_ID,
            "name": AGENT_NAME,
            "manifestVersion": "1.0",
            "secrets": [{"key": "CODEBUDDY_API_KEY", "value": token}],
        }
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def save_runtime(data):
    path = os.path.join(DATA_DIR, "last_runtime.json")
    with open(path, "w") as f:
        json.dump({
            "runtime_id": data["id"],
            "status": data["status"],
            "acp_url": data["links"]["acpLink"]["url"],
            "acp_token": data["links"]["acpLink"]["token"],
            "box_url": data["links"]["acpLink"]["boxUrl"],
            "created_at": time.time(),
        }, f, indent=2, ensure_ascii=False)
    return path


def load_last_runtime():
    path = os.path.join(DATA_DIR, "last_runtime.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


async def acp_chat(acp_url, acp_token, message, timeout=120):
    """完整的 ACP 协议交互"""
    headers = {
        "Authorization": f"Bearer {acp_token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient(http2=True, timeout=timeout, verify=False) as client:
        # Step 1: 打开 SSE 流，获取 Acp-Connection-Id
        print("1️⃣ 连接 Agent...")
        async with client.stream("GET", acp_url, headers={**headers, "Accept": "text/event-stream"}) as sse_resp:
            conn_id = sse_resp.headers.get("acp-connection-id")
            if not conn_id:
                print("❌ 未获取到 Connection ID")
                return None
            print(f"   ✅ 连接建立: {conn_id[:20]}...")

            # Step 2: Initialize
            print("2️⃣ 初始化协议...")
            await client.post(acp_url,
                content=json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {
                        "protocolVersion": 1,
                        "clientCapabilities": {
                            "fs": {"readTextFile": True, "writeTextFile": True},
                            "terminal": True,
                        },
                        "clientInfo": {"name": "hermes-crm", "title": "Hermes CRM", "version": "1.0.0"},
                    }
                }).encode("utf-8"),
                headers={**headers, "Acp-Connection-Id": conn_id})

            # 读取 SSE 事件流 (单次遍历, 处理所有消息)
            print("3️⃣ 等待 Agent 响应...")
            session_id = None
            prompt_sent = False
            full_text = ""
            start = time.time()
            async for line in sse_resp.aiter_lines():
                if not line.strip():
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                eid = data.get("id")
                method = data.get("method", "")
                params = data.get("params", {})

                # 1) Initialize 响应
                if eid == 1 and "result" in data:
                    caps = data["result"].get("agentCapabilities", {})
                    info = data["result"].get("agentInfo", {})
                    print(f"   ✅ 协议协商完成")
                    if info.get("name"):
                        print(f"   Agent: {info.get('title', info['name'])}")
                    # 发送 session/new
                    print("3️⃣ 创建会话...")
                    await client.post(acp_url,
                        content=json.dumps({
                            "jsonrpc": "2.0", "id": 2, "method": "session/new",
                            "params": {"cwd": "/workspace", "mcpServers": []}
                        }).encode("utf-8"),
                        headers={**headers, "Acp-Connection-Id": conn_id})
                    continue

                # 2) Session/New 响应
                if eid == 2 and "result" in data:
                    session_id = data["result"].get("sessionId")
                    print(f"   ✅ 会话创建: {session_id}")
                    # 发送 prompt
                    print(f"4️⃣ 发送消息: {message[:50]}...")
                    await client.post(acp_url,
                        content=json.dumps({
                            "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
                            "params": {
                                "sessionId": session_id,
                                "prompt": [{"type": "text", "content": message}],
                            }
                        }, ensure_ascii=False).encode("utf-8"),
                        headers={**headers, "Acp-Connection-Id": conn_id})
                    prompt_sent = True
                    print(f"\n💬 Agent 回复:")
                    print("=" * 60)
                    continue

                # 3) 流式消息块
                if "agent_message_chunk" in method:
                    chunk = params.get("agent_message_chunk", {})
                    content = chunk.get("content", "")
                    if content:
                        full_text += content
                        print(content, end="", flush=True)
                    continue

                if "agent_message" in method:
                    msg = params.get("agent_message", {})
                    content = msg.get("content", "")
                    if content and not full_text:
                        full_text = content
                        print(content, end="", flush=True)
                    continue

                # 4) 最终结果
                if eid == 3 and "result" in data:
                    stop = data["result"].get("stopReason", "unknown")
                    print(f"\n\n[完成: {stop}]")
                    break

                if time.time() - start > timeout - 10:
                    print("\n(超时)")
                    break

            print("=" * 60)
            return full_text if full_text else None


def cmd_chat(args):
    """创建 Runtime + ACP 聊天"""
    print("🔑 获取 Token...")
    token = get_access_token()

    print("🚀 创建 Runtime...")
    rt = create_runtime(token, name=args.name)
    rt_id = rt["id"]
    acp_url = rt["links"]["acpLink"]["url"]
    acp_token = rt["links"]["acpLink"]["token"]
    box_url = rt["links"]["acpLink"]["boxUrl"]

    print(f"✅ Runtime {rt_id} ({rt['status']})")
    save_path = save_runtime(rt)
    print(f"💾 已保存 → {save_path}")

    # 等待沙箱启动
    print("⏳ 等待沙箱启动 (10s)...")
    time.sleep(10)

    # ACP 聊天
    result = asyncio.run(acp_chat(acp_url, acp_token, args.message, timeout=args.timeout))

    if result:
        return result
    else:
        print(f"\n💡 备选方案: 在浏览器中聊天 → {box_url}")
        webbrowser.open(box_url)
        return None


def cmd_create(args):
    """仅创建 Runtime"""
    token = get_access_token()
    rt = create_runtime(token, name=args.name)
    save_path = save_runtime(rt)
    box_url = rt["links"]["acpLink"]["boxUrl"]
    
    print(json.dumps({
        "runtime_id": rt["id"],
        "status": rt["status"],
        "box_url": box_url,
        "acp_url": rt["links"]["acpLink"]["url"],
        "saved_to": save_path,
    }, indent=2, ensure_ascii=False))
    
    print(f"\n🌐 打开浏览器: {box_url}")
    webbrowser.open(box_url)


def cmd_list(args):
    """列出所有 Runtime"""
    token = get_access_token()
    resp = requests.get(RUNTIME_API, headers={
        "Authorization": f"Bearer {token}",
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])


def cmd_token(args):
    """测试 Token"""
    token = get_access_token()
    print(f"✅ Token: {token[:60]}... ({len(token)} chars)")


def main():
    parser = argparse.ArgumentParser(
        description="CodeBuddy CRM Agent — AgentOS + ACP 协议",
    )
    sub = parser.add_subparsers(dest="command")

    p_chat = sub.add_parser("chat", help="与 CRM Agent 聊天")
    p_chat.add_argument("message", help="发送给 Agent 的消息")
    p_chat.add_argument("--name", default="crm-session", help="Runtime 名称")
    p_chat.add_argument("--timeout", type=int, default=120, help="超时秒数")

    p_create = sub.add_parser("create", help="创建 Runtime")
    p_create.add_argument("--name", default="crm-agent", help="Runtime 名称")

    sub.add_parser("list", help="列出 Runtime")
    sub.add_parser("token", help="测试 Token")

    args = parser.parse_args()

    if args.command == "chat":
        cmd_chat(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "token":
        cmd_token(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
