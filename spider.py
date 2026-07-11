#!/usr/bin/env python3

import os
import time
import logging
import random
import re
import subprocess
import requests
import base64
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from seleniumbase import SB
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID', '')
PROXY_SERVER = os.getenv('HTTP_PROXY', '')
TARGET_ACTORS_ENV = os.getenv('TARGET_ACTORS', '')
PAGE_URLS_ENV = os.getenv('PAGE_URLS', '')
TURNSTILE_URL = os.getenv('TURNSTILE_URL', 'https://www.ji.com')
encoded_url = os.getenv('HOST_URL', 'aHR0cHM6Ly93d3cuamkuY29t')
HOST_URL = base64.b64decode(encoded_url).decode('utf-8')

# ===================== Turnstile JS =====================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

# ===================== xdotool 工具 =====================
def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls],
                               capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]],
                               timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)],
                       timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(random.uniform(0.08, 0.2))
        subprocess.run(["xdotool", "click", "1"],
                       timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

# ===================== Telegram =====================
def send_telegram(message, screenshot_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    tz_offset = timezone(timedelta(hours=8))
    time_str = datetime.now(tz_offset).strftime("%Y-%m-%d %H:%M:%S") + " HKT"
    full_message = f"🎉 短剧 \n\n：{time_str}\n\n{message}"
    try:
        if screenshot_path and os.path.exists(screenshot_path):
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(screenshot_path, 'rb') as photo:
                requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": full_message},
                              files={'photo': photo}, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": full_message}, timeout=10)
        logger.info("✅ Telegram 通知发送成功")
    except Exception as e:
        logger.warning(f"⚠️ Telegram 发送失败: {e}")

# ===================== Turnstile 处理 =====================
def handle_turnstile(sb, max_attempts=6):
    logger.info("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    if sb.execute_script(_SOLVED_JS):
        logger.info("✅ 已静默通过")
        return True

    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(max_attempts):
        if sb.execute_script(_SOLVED_JS):
            logger.info(f"✅ Turnstile 通过（第 {attempt} 次尝试）")
            return True

        logger.info(f"🖱️ 第 {attempt + 1} 次调用 uc_gui_click_captcha...")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            logger.warning(f"uc_gui_click_captcha 异常: {e}")
            try:
                container = sb.find_element(
                    "xpath", "//div[contains(@style, 'display: grid') and .//input[@name='cf-turnstile-response']]"
                )
                rect = sb.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {left: rect.left, top: rect.top, width: rect.width, height: rect.height};
                """, container)
                win = sb.execute_script(_WININFO_JS)
                bar = win['oh'] - win['ih']
                cx = round(rect['left'] + rect['width'] / 2 + win['sx'])
                cy = round(rect['top'] + rect['height'] / 2 + win['sy'] + bar)
                logger.info(f"🖱️ 降级 xdotool 点击 ({cx}, {cy})")
                _xdotool_click(cx, cy)
            except Exception as e2:
                logger.warning(f"xdotool 降级也失败: {e2}")

        for _ in range(16):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                logger.info(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True

        logger.info(f"⚠️ 第 {attempt + 1} 次未通过，重试...")

    logger.warning("❌ Turnstile 多次尝试均失败")
    return False

# ===================== 核心爬虫 =====================
class JisuSpider:
    def __init__(self, target_actors=None, page_urls=None):
        self.base_url = HOST_URL
        self.target_actors = target_actors or []
        self.page_urls = page_urls or []
        self.session = None
        self.screenshot_path = None

    def _build_session(self, sb):
        driver = sb.driver
        cookies = driver.get_cookies()
        ua = driver.execute_script('return navigator.userAgent')
        session = requests.Session()
        for c in cookies:
            session.cookies.set(c.get('name', ''), c.get('value', ''))
        session.headers.update({
            'User-Agent': ua,
            'Referer': self.base_url,
        })
        self.session = session
        logger.info(f"已构建 requests 会话，cookies: {len(cookies)} 个")

    def _get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                if self.session:
                    resp = self.session.get(url, timeout=15)
                    resp.raise_for_status()
                    return resp.text
            except Exception as e:
                logger.warning(f"访问失败 {url} (第{attempt+1}次): {e}")
                time.sleep(2)
        return None

    def get_detail_urls(self, page_url):
        detail_urls = []
        html = self._get_page(page_url)
        if not html:
            return detail_urls
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', class_='list-item')
        for item in items:
            link_tag = item.find('a')
            if link_tag and link_tag.get('href'):
                href = link_tag['href']
                full_url = self.base_url + href if href.startswith('/') else href
                detail_urls.append(full_url)
        logger.info(f"从 {page_url} 获取到 {len(detail_urls)} 个详情链接")
        return detail_urls

    def get_drama_info(self, detail_url):
        try:
            html = self._get_page(detail_url)
            if not html:
                return None
            soup = BeautifulSoup(html, 'html.parser')

            title = None
            title_tag = soup.find('div', class_='vod-title')
            if title_tag:
                h2_tag = title_tag.find('h2')
                if h2_tag:
                    title = h2_tag.get_text(strip=True)
            if not title:
                title_match = re.search(r'<h2>(.*?)</h2>', html)
                if title_match:
                    title = title_match.group(1)

            actors = None
            all_lis = soup.find_all('li')
            for li in all_lis:
                text = li.get_text()
                if 'IActors：' in text:
                    actors_text = text.split('主演：')[-1].strip()
                    actors = actors_text
                    break
            if not actors:
                actors_match = re.search(r'主演：<span>(.*?)</span>', html)
                if actors_match:
                    actors = actors_match.group(1)

            if not title or not actors:
                logger.warning(f"详情页数据不完整: {detail_url}")
                return None

            if self.target_actors:
                matched = any(actor in actors for actor in self.target_actors)
                if not matched:
                    logger.info(f"跳过 {title}，IActors {actors} 不包含目标IActors")
                    return None

            logger.info(f"成功抓取: {title} - IActors: {actors}")
            return {'title': title, 'actors': actors, 'url': detail_url}

        except Exception as e:
            logger.warning(f"获取详情页失败 {detail_url}: {e}")
            return None

    def process(self, sb):
        sb.uc_open_with_reconnect(TURNSTILE_URL, reconnect_time=8)
        time.sleep(3 + random.random() * 2)

        passed = False
        for _ in range(5):
            try:
                sb.find_element('.card-content-h1', timeout=5)
                logger.info("页面已加载，无需打码")
                passed = True
                break
            except Exception:
                break

        if not passed:
            passed = handle_turnstile(sb)

        if not passed:
            try:
                sb.open("https://api.ip.sb/ip")
            except Exception:
                pass
            return False, "❌ Cloudflare 打码失败"

        self._build_session(sb)
        logger.info(f"🚀 开始抓取，列表页 {len(self.page_urls)} 个，目标IActors {len(self.target_actors)} 个")

        all_dramas = []
        for page_url in self.page_urls:
            detail_urls = self.get_detail_urls(page_url)
            for i, detail_url in enumerate(detail_urls):
                if i > 0:
                    time.sleep(0.1)
                drama_info = self.get_drama_info(detail_url)
                if drama_info:
                    all_dramas.append(drama_info)
            logger.info(f"完成列表页: {page_url}, 累计抓取: {len(all_dramas)} 条数据")
            time.sleep(1)

        summary = f"📊 抓取完成！共 {len(all_dramas)} 部\n\n"
        for i, drama in enumerate(all_dramas, 1):
            summary += f"{i}. {drama['title']} | IActors: {drama['actors']} | {drama['url']}\n"

        logger.info("\n" + "=" * 50)
        logger.info(f"抓取完成！共 {len(all_dramas)} 部")
        return True, summary

    def run(self, max_retries=3):
        last_error = ""

        for attempt in range(max_retries):
            sb_kwargs = {"uc": True, "headless": HEADLESS}
            if PROXY_SERVER:
                sb_kwargs["proxy"] = PROXY_SERVER

            try:
                with SB(**sb_kwargs) as sb:
                    if attempt > 0:
                        logger.info(f"🔄 正在进行第 {attempt + 1} 次尝试...")
                    success, message = self.process(sb)
                    if success:
                        return True, message
                    last_error = message
                    if "打码失败" in message:
                        break
                    try:
                        sb.save_screenshot("error-spider.png")
                        self.screenshot_path = "error-spider.png"
                    except Exception:
                        pass
            except Exception as e:
                last_error = f"异常：{str(e)[:80]}"
                logger.error(f"❌ 第 {attempt + 1} 次执行出错: {e}")
                self.screenshot_path = "error-spider.png"

            if attempt < max_retries - 1:
                time.sleep(5 + random.random() * 5)

        if not self.screenshot_path:
            self.screenshot_path = "error-spider.png"
        return False, f"❌ 历经 {max_retries} 次尝试仍失败: {last_error}"


# ===================== 主入口 =====================
def _parse_list(env_val, default_list, sep=r'[,;\n]'):
    if not env_val:
        return list(default_list)
    return [x.strip() for x in re.split(sep, env_val) if x.strip()]


def main():
    default_actors = []
    default_pages = []

    target_actors = _parse_list(TARGET_ACTORS_ENV, default_actors)
    page_urls = _parse_list(PAGE_URLS_ENV, default_pages)

    spider = JisuSpider(target_actors=target_actors, page_urls=page_urls)
    success, msg = spider.run()

    logger.info(f"汇总:\n {msg}")
    send_telegram(msg, spider.screenshot_path)

    if success and spider.screenshot_path and os.path.exists(spider.screenshot_path):
        try:
            os.remove(spider.screenshot_path)
        except OSError:
            pass

    logger.info("\n✅ 抓取流程结束！")


if __name__ == "__main__":
    try:
        main()
    finally:
        os._exit(0)
