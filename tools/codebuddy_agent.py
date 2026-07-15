#!/usr/bin/env python3
"""
CodeBuddy Agent Caller — 通过浏览器自动化调用 CodeBuddy 共享 Agent
用于腾讯云销售分析等场景

使用方式:
    python3 codebuddy_agent.py "请分析腾讯云CVM近季度的销售趋势"
    python3 codebuddy_agent.py --setup   # 首次登录设置Cookie
    python3 codebuddy_agent.py --status # 检查Cookie是否有效

原理:
    CodeBuddy Cloud Agent 没有公开REST API，
    所以通过Selenium自动化浏览器操作来实现调用。
    首次使用需扫码登录保存Cookie，后续自动复用。
"""

import argparse
import json
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("codebuddy")

AGENT_SHARE_URL = "https://www.codebuddy.cn/agents/share/agent/agent_01KWZZZ70MABFJ4CXHTBBBQQ9E"
COOKIE_FILE = os.path.expanduser("~/code/rts-ai-platform/tools/codebuddy_cookies.json")
MAX_WAIT = 300  # 等待回复最大秒数


def _make_driver(headless=False):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # 独立用户数据目录，避免与现有Chrome实例冲突
    options.add_argument(f"--user-data-dir=/tmp/codebuddy_chrome_{os.getpid()}")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


def cmd_setup():
    """登录并保存Cookie"""
    driver = _make_driver(headless=False)
    driver.get(AGENT_SHARE_URL)

    print("\n" + "=" * 60)
    print("请在浏览器中完成微信扫码登录")
    print("登录完成后脚本会自动保存Cookie")
    print("=" * 60 + "\n")

    # 等到不再在登录页
    start = time.time()
    while time.time() - start < 300:
        time.sleep(3)
        if "/login" not in driver.current_url:
            logger.info("登录成功，保存Cookie...")
            time.sleep(5)
            cookies = driver.get_cookies()
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"Cookie 已保存 ({len(cookies)} 条)")
            break

    time.sleep(3)
    driver.quit()


def cmd_status():
    """检查Cookie是否有效"""
    if not os.path.isfile(COOKIE_FILE):
        print("❌ 未找到Cookie文件，请先运行 --setup")
        return False

    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    # 检查session cookie是否存在
    has_session = any(c["name"] in ("session", "session_2") for c in cookies)
    # 检查是否过期
    expired = []
    for c in cookies:
        if "expiry" in c and c["expiry"] < time.time():
            expired.append(c["name"])

    if has_session and not expired:
        print(f"✅ Cookie 有效 ({len(cookies)} 条)")
        return True
    elif has_session and expired:
        print(f"⚠️  Cookie 存在但部分已过期: {expired}")
        print("   可能需要重新运行 --setup")
        return False
    else:
        print("❌ Cookie 无效（缺少session），请运行 --setup")
        return False


def cmd_call(message: str, headless: bool = False, timeout: int = MAX_WAIT):
    """调用Agent：加载Cookie → 打开Agent页 → 发消息 → 获取回复"""
    if not os.path.isfile(COOKIE_FILE):
        logger.error("请先运行: python3 codebuddy_agent.py --setup")
        return None

    driver = _make_driver(headless=headless)
    try:
        # 加载Cookie
        driver.get("https://www.codebuddy.cn/home/")
        time.sleep(3)

        with open(COOKIE_FILE) as f:
            cookies = json.load(f)

        for c in cookies:
            try:
                sc = {"name": c["name"], "value": c["value"]}
                if "domain" in c: sc["domain"] = c["domain"]
                if "path" in c: sc["path"] = c["path"]
                if c.get("secure"): sc["secure"] = True
                if c.get("httpOnly"): sc["httpOnly"] = True
                if "expiry" in c:
                    try: sc["expiry"] = int(c["expiry"])
                    except: pass
                driver.add_cookie(sc)
            except:
                pass

        logger.info("已加载Cookie，导航到Agent页面...")

        # 导航到Agent分享页
        driver.get(AGENT_SHARE_URL)
        time.sleep(10)

        # 检查是否被踢回登录页
        if "/login" in driver.current_url:
            logger.error("Cookie已失效，请重新运行 --setup")
            driver.quit()
            return None

        logger.info("已进入Agent页面，发送消息...")

        # 发送消息
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        input_el = None
        selectors = [
            'textarea',
            '[contenteditable="true"]',
            '[class*="chat-input"]',
            '[class*="editor"]',
            '[class*="input-area"]',
            '[placeholder*="输入"]',
            '[placeholder*="Ask"]',
        ]

        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        input_el = el
                        break
            except:
                continue
            if input_el:
                break

        if not input_el:
            input_el = driver.execute_script("""
                const all = document.querySelectorAll('textarea, [contenteditable="true"], input[type="text"]');
                for (const el of all) {
                    if (el.offsetParent !== null && el.getBoundingClientRect().width > 50) return el;
                }
                return null;
            """)

        if not input_el:
            logger.error("找不到聊天输入框")
            driver.quit()
            return None

        input_el.click()
        time.sleep(0.3)

        tag = input_el.tag_name.lower()
        if tag in ("textarea", "input"):
            input_el.clear()
            input_el.send_keys(message)
            time.sleep(0.5)
            input_el.send_keys(Keys.RETURN)
        else:
            driver.execute_script(
                'arguments[0].focus(); document.execCommand("insertText", false, arguments[1]);',
                input_el, message,
            )
            time.sleep(0.5)
            input_el.send_keys(Keys.RETURN)

        logger.info("消息已发送，等待Agent回复...")

        # 等待回复完成
        start = time.time()
        last_text = ""
        stable_count = 0

        while time.time() - start < timeout:
            time.sleep(5)
            try:
                # 获取所有消息内容
                msg_selectors = [
                    '[class*="markdown-body"]',
                    '[class*="message-assistant"]',
                    '[class*="bot-"]',
                    '[class*="response"]',
                    '[class*="answer"]',
                    '[class*="chat-message"]',
                ]
                texts = []
                for sel in msg_selectors:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            t = el.text.strip()
                            if t:
                                texts.append(t)
                    except:
                        continue

                current = texts[-1] if texts else ""
                if current and current != last_text:
                    last_text = current
                    stable_count = 0
                    logger.info(f"部分回复 ({len(current)} 字)...")
                elif current:
                    stable_count += 1

                if stable_count >= 3 and last_text and len(last_text) > 10:
                    logger.info("回复完成!")
                    return last_text

            except:
                continue

        return last_text or "(超时未获取到回复)"

    except Exception as e:
        logger.error(f"调用失败: {e}")
        return None
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description="CodeBuddy Agent 调用工具 (腾讯云销售CRM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("message", nargs="?", help="发送给 Agent 的消息")
    parser.add_argument("--setup", action="store_true", help="扫码登录保存Cookie")
    parser.add_argument("--status", action="store_true", help="检查Cookie状态")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--timeout", type=int, default=MAX_WAIT, help=f"等待超时秒数 (默认{MAX_WAIT})")
    args = parser.parse_args()

    if args.setup:
        cmd_setup()
    elif args.status:
        cmd_status()
    elif args.message:
        result = cmd_call(args.message, headless=args.headless, timeout=args.timeout)
        if result:
            print(f"\n{'='*60}")
            print("📋 Agent 回复:")
            print(f"{'='*60}")
            print(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
