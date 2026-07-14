#!/usr/bin/env python3

import os
import time
import logging
import random
import re
import requests
import base64
from DrissionPage import Chromium, ChromiumOptions
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
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


def rand_int(min_val, max_val):
    return random.randint(min_val, max_val)


def sleep(ms):
    time.sleep(ms / 1000)


def human_delay():
    delay = 7000 + random.random() * 5000
    sleep(delay)


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
                requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": full_message}, files={'photo': photo}, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": full_message}, timeout=10)
        logger.info("✅ Telegram 通知发送成功")
    except Exception as e:
        logger.warning(f"⚠️ Telegram 发送失败: {e}")


class JisuSpider:
    def __init__(self, target_actors=None, page_urls=None):
        self.base_url = HOST_URL
        self.target_actors = target_actors or []
        self.page_urls = page_urls or []
        self.browser = None
        self.tab = None
        self.session = None
        self.screenshot_path = None

    def setup_driver(self):
        co = ChromiumOptions()
        if HEADLESS:
            co.headless(True)
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--window-size=1280,720')

        if PROXY_SERVER:
            co.set_proxy(PROXY_SERVER)

        logger.info("🛠️  - 驱动初始化")

        try:
            self.browser = Chromium(co)
            self.tab = self.browser.latest_tab
            self.tab.set.window.size(1280, 720)
            logger.info("- 驱动启动成功")
        except Exception as e:
            logger.error(f"- 驱动启动失败: {e}")
            raise

    def _handle_turnstile(self, context=""):
        try:
            container = self.tab.ele(
                "xpath://div[contains(@style, 'display: grid') and .//input[@name='cf-turnstile-response']]",
                timeout=15
            )
            if not container:
                logger.warning(f"❌ - [{context}] 未找到 turnstile 容器")
                return False

            logger.info("✅  - 找到元素了")

            page = self.browser.get_tabs()[-1]
            challengeSolution = page.ele("@name=cf-turnstile-response")
            challengeWrapper = challengeSolution.parent()
            challengeIframe = challengeWrapper.shadow_root.ele("tag:iframe")
            
            challengeIframe.run_js("""
window.dtp = 1
function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

// old method wouldn't work on 4k screens

let screenX = getRandomInt(800, 1200);
let screenY = getRandomInt(400, 600);

Object.defineProperty(MouseEvent.prototype, 'screenX', { value: screenX });

Object.defineProperty(MouseEvent.prototype, 'screenY', { value: screenY });
                        """)
            
            challengeIframeBody = challengeIframe.ele("tag:body").shadow_root
            challengeButton = challengeIframeBody.ele("tag:input")
            challengeButton.click()

            validated = False
            return validated
        except Exception as e:
            logger.error(f"❌  - [{context}] 验证交互失败: {e}")
            return False

    def _find_optional(self, selector, timeout=5):
        try:
            ele = self.tab.ele(selector, timeout=timeout)
            return ele if ele else None
        except Exception:
            return None

    def _build_session(self):
        cookies = self.tab.cookies()
        ua = self.tab.run_js("return navigator.userAgent")

        session = requests.Session()
        for c in cookies:
            session.cookies.set(c.get('name', ''), c.get('value', ''))
        session.headers.update({
            'User-Agent': ua,
            'Referer': self.base_url,
        })
        self.session = session
        logger.info(f"已构建 requests 会话，cookies: {len(cookies)} 个")

    def _pass_turnstile(self, url, max_attempts=5):


        page = self.browser.get_tabs()[-1]
        page.get(url)

        sleep(3000 + random.random() * 1000)

        if self._find_optional('css:.card-content-h1', timeout=5):
            logger.info("页面已加载，无需打码")
            sleep(200000)
            self._build_session()
            return True

        for i in range(max_attempts):
            logger.info(f"打码第 {i+1} 次尝试...")
            self._handle_turnstile(f"PassTurnstile-{i+1}")

            if self._find_optional('css:.card-content-h1', timeout=8):
                logger.info("打码成功！")
                self._build_session()
                return True

            logger.info(f"第 {i+1} 次打码未通过，重试...")

        logger.warning(f"打码失败，已尝试 {max_attempts} 次")
        return False

    def _get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                if self.session:
                    resp = self.session.get(url, timeout=15)
                    resp.raise_for_status()
                    return resp.text
                else:
                    self.tab.get(url)
                    return self.tab.html
            except Exception as e:
                logger.warning(f"访问失败 {url} (第{attempt+1}次): {e}")
                sleep(2000)
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

    def process(self):
        logger.info(f"🚀 开始抓取，列表页 {len(self.page_urls)} 个，目标IActors {len(self.target_actors)} 个")

        if not self.tab:
            self.setup_driver()

        if not self._pass_turnstile("https://www.jisuzy.com/index.php/vod/search.html?wd=2"):
            return False, "❌ Cloudflare 打码失败"

        if self.browser:
            self.browser.quit()
            self.browser = None
            self.tab = None

        all_dramas = []
        for page_url in self.page_urls:
            detail_urls = self.get_detail_urls(page_url)

            for i, detail_url in enumerate(detail_urls):
                if i > 0:
                    sleep(100)
                drama_info = self.get_drama_info(detail_url)
                if drama_info:
                    all_dramas.append(drama_info)

            logger.info(f"完成列表页: {page_url}, 累计抓取: {len(all_dramas)} 条数据")
            sleep(1000)

        summary = f"📊 抓取完成！共 {len(all_dramas)} 部\n\n"
        for i, drama in enumerate(all_dramas, 1):
            summary += f"{i}. {drama['title']} | IActors: {drama['actors']} | {drama['url']}\n"

        logger.info("\n" + "=" * 50)
        logger.info(f"抓取完成！共 {len(all_dramas)} 部")
        return True, summary

    def run(self, max_retries=3):
        last_error = ""

        for attempt in range(max_retries):
            try:
                if not self.tab:
                    self.setup_driver()

                if attempt > 0:
                    logger.info(f"🔄 正在进行第 {attempt + 1} 次尝试...")

                success, message = self.process()
                if success:
                    return True, message
                last_error = message

                if "打码失败" in message:
                    break

            except Exception as e:
                last_error = f"异常：{str(e)[:80]}"
                logger.error(f"❌ 第 {attempt + 1} 次执行出错: {e}")

            if attempt < max_retries - 1:
                sleep(5000 + random.random() * 5000)

        self.screenshot_path = "error-spider.png"
        if self.tab:
            try:
                self.tab.get_screenshot(self.screenshot_path)
            except Exception as e:
                logger.warning(f"截图失败: {e}")
        return False, f"❌ 历经 {max_retries} 次尝试仍失败: {last_error}"


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
