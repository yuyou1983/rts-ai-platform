#!/usr/bin/env python3
"""
CodeBuddy Login Helper — 打开浏览器让你扫码登录，然后保存 Cookie 供后续复用

使用方式:
    python3 codebuddy_login.py

登录成功后 Cookie 会保存到 ~/code/rts-ai-platform/tools/codebuddy_cookies.json
后续 codebuddy_agent.py 会自动加载这个文件
"""

import json
import os
import sys
import time
import signal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

AGENT_URL = "https://www.codebuddy.cn/agents/share/agent/agent_01KWZZZ70MABFJ4CXHTBBBQQ9E"
COOKIE_FILE = os.path.expanduser("~/code/rts-ai-platform/tools/codebuddy_cookies.json")
POLL_INTERVAL = 3  # 每3秒检查一次登录状态
MAX_WAIT = 300  # 最多等5分钟


def _is_logged_in(driver):
    """检查是否已登录（页面不再是登录页）"""
    try:
        url = driver.current_url
        if "login" not in url.lower():
            # 进一步检查是否有聊天输入框
            inputs = driver.find_elements("css selector", 'textarea, [contenteditable="true"], [class*="chat-input"], [class*="editor"]')
            if any(el.is_displayed() for el in inputs):
                return True
        # 检查页面文本
        body_text = driver.execute_script('return document.body.innerText.substring(0, 500)') or ""
        if "微信登录" not in body_text and "扫码" not in body_text:
            return True
    except Exception:
        pass
    return False


def main():
    options = Options()
    # 非无头模式 — 你能看到浏览器窗口扫码
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--lang=zh-CN")

    print("=" * 60)
    print("🔐 CodeBuddy 登录助手")
    print("=" * 60)
    print(f"📂 Cookie 保存路径: {COOKIE_FILE}")
    print("")
    print("请操作:")
    print("  1. 浏览器窗口即将打开 CodeBuddy 登录页")
    print("  2. 使用微信扫码登录")
    print("  3. 确认服务条款")
    print("  4. 等待进入 Agent 聊天界面")
    print("  5. 脚本会自动检测登录状态并保存 Cookie")
    print("")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)

    print("🌐 正在打开浏览器...")
    driver.get(AGENT_URL)

    print("⏳ 等待登录中... (最多5分钟)")
    print("   请在浏览器窗口中扫码登录")

    start = time.time()
    logged_in = False
    while time.time() - start < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        if _is_logged_in(driver):
            logged_in = True
            break
        elapsed = int(time.time() - start)
        print(f"   ⏳ 仍在等待登录... ({elapsed}s)")

    if not logged_in:
        # 再给一次机会 — 5分钟到了可能页面渲染慢
        print("⚠️  超时，做最后一次 Cookie 保存尝试...")
    else:
        print("✅ 检测到已登录！")

    # 保存 Cookie
    cookies = driver.get_cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

    print(f"💾 Cookie 已保存 ({len(cookies)} 条)")
    print(f"   路径: {COOKIE_FILE}")

    # 验证
    current_url = driver.current_url
    print(f"📍 当前 URL: {current_url}")

    if logged_in:
        print("\n✅ 登录成功！后续 codebuddy_agent.py 会自动加载 Cookie。")
        print("   使用: python3 codebuddy_agent.py \"你的问题\"")
    else:
        print("\n⚠️  未能确认登录。Cookie 已保存但可能无效。")
        print("   如果无效，请重新运行此脚本。")

    # 不急着关闭，给你看一下
    print("\n浏览器将在 10 秒后自动关闭...")
    time.sleep(10)
    driver.quit()
    print("完成！")


if __name__ == "__main__":
    main()
