#!/usr/bin/env python3

import os
import time
import logging
import random
import re
import requests
import base64
import undetected_chromedriver as uc
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, WebDriverException
from dotenv import load_dotenv

load_dotenv()

# ===================== 配置日志 =====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== 全局配置 =====================
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID', '')
PROXY_SERVER = os.getenv('HTTP_PROXY', '')
# 抓取目标：IActors列表与列表页（逗号/分号分隔，留空则用默认值）
TARGET_ACTORS_ENV = os.getenv('TARGET_ACTORS', '')
PAGE_URLS_ENV = os.getenv('PAGE_URLS', '')
# 打码入口 URL（用于过 CF 拿 cookie）
TURNSTILE_URL = os.getenv('TURNSTILE_URL', 'https://www.ji.com')
encoded_url = os.getenv('HOST_URL', 'aHR0cHM6Ly93d3cuamkuY29t')
HOST_URL = base64.b64decode(encoded_url).decode('utf-8')

# ===================== 工具函数 =====================
def rand_int(min_val, max_val):
    return random.randint(min_val, max_val)

def sleep(ms):
    time.sleep(ms / 1000)

def human_delay():
    delay = 7000 + random.random() * 5000
    sleep(delay)

def human_type(driver, selector_type, selector_value, text):
    try:
        element = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((selector_type, selector_value))
        )
        element.clear()
        for char in text:
            element.send_keys(char)
            sleep(rand_int(50, 150))
        return True
    except Exception as e:
        logger.warning(f"打字失败: {e}")
        return False

# ===================== Telegram 通知 =====================
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

# ===================== 爬虫核心类 =====================
class JisuSpider:
    def __init__(self, target_actors=None, page_urls=None):
        self.base_url = HOST_URL
        self.target_actors = target_actors or []
        self.page_urls = page_urls or []
        self.driver = None
        self.session = None
        self.screenshot_path = None

    # ---------- 浏览器初始化 ----------
    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS: chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        if PROXY_SERVER:
            chrome_options.add_argument(f'--proxy-server={PROXY_SERVER}')
        v_env = os.getenv('CHROME_VERSION', '')
        v_main = int(v_env) if v_env.isdigit() else None
        logger.info(f"🛠️ 驱动初始化 - 指定大版本: {v_main or '自动探测'}")
        try:
            self.driver = uc.Chrome(options=chrome_options, headless=HEADLESS, version_main=v_main, use_subprocess=True)
        except Exception as e:
            logger.warning(f"⚠️ 强制版本启动失败，尝试降级启动: {e}")
            self.driver = uc.Chrome(options=chrome_options, headless=HEADLESS)
        self.driver.set_window_size(1280, 720)

    # ---------- Cloudflare Turnstile 验证（Katabump 框架化方案）----------
    def _handle_turnstile(self, context=""):
        """优化后的 Cloudflare 验证逻辑"""
        try:

            container = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@style, 'display: grid') and .//input[@name='cf-turnstile-response']]")
                )
            )

            logger.info(f"✅  - 找到元素了")

            size = container.size
            base_offset_x = -(size['width'] / 2) + (size['width'] * 0.044)
            rand_x = base_offset_x + random.uniform(-5, 5)
            rand_y = random.uniform(-5, 5)

            logger.info(f"🖱️ - [{context}] 找到窗口")

            rect = self.driver.execute_script("""
                var rect = arguments[0].getBoundingClientRect();
                return {left: rect.left, top: rect.top, width: rect.width, height: rect.height};
            """, container)
            center_x = rect['left'] + rect['width'] / 2
            center_y = rect['top'] + rect['height'] / 2
            click_x = center_x + rand_x
            click_y = center_y + rand_y

            click_x = round(click_x)
            click_y = round(click_y)

            self.driver.execute_script("arguments[0].focus();", container)

            sleep(500)

            logger.info(f"🖱️ - [{context}] 焦点马上点击")

            actions = ActionChains(self.driver)
            actions.move_to_element(container)
            actions.pause(random.uniform(0.5, 0.8))
            actions.move_to_element_with_offset(container, rand_x, rand_y)
            actions.click_and_hold()
            actions.pause(random.uniform(0.1, 0.25))
            actions.release()
            actions.perform() 
            
            logger.info(f"🖱️ - [{context}] 执行偏移点击...{click_x},{click_y}")
            
            # 轮询检查 Token
            validated = False
            return validated
        except Exception as e:
            logger.error(f"❌  - [{context}] 验证交互失败: {e}")
            return False

    def _find_optional(self, locator, timeout=5):
        """查找元素，找不到返回 None 而不抛异常。"""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
        except TimeoutException:
            return None

    # ---------- 通过 turnstile 并构建 requests 会话 ----------
    def _build_session(self):
        cookies = self.driver.get_cookies()
        ua = self.driver.execute_script('return navigator.userAgent')

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
        self.driver.get(url)
        sleep(3000 + random.random() * 1000)

        # 已直接放行则无需打码
        if self._find_optional((By.CSS_SELECTOR, '.card-content-h1'), timeout=5):
            logger.info("页面已加载，无需打码")
            self._build_session()
            return True

        for i in range(max_attempts):
            logger.info(f"打码第 {i+1} 次尝试...")
            self._handle_turnstile(f"PassTurnstile-{i+1}")

            if self._find_optional((By.CSS_SELECTOR, '.card-content-h1'), timeout=8):
                logger.info("打码成功！")
                self._build_session()
                return True

            logger.info(f"第 {i+1} 次打码未通过，重试...")

        logger.warning(f"打码失败，已尝试 {max_attempts} 次")
        return False

    # ---------- 页面获取 ----------
    def _get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                if self.session:
                    resp = self.session.get(url, timeout=15)
                    resp.raise_for_status()
                    return resp.text
                else:
                    self.driver.get(url)
                    return self.driver.page_source
            except Exception as e:
                logger.warning(f"访问失败 {url} (第{attempt+1}次): {e}")
                sleep(2000)
        return None

    # ---------- 解析详情链接 ----------
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

    # ---------- 解析单部 ----------
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

    # ---------- 核心抓取流程 ----------
    def process(self):
        logger.info(f"🚀 开始抓取，列表页 {len(self.page_urls)} 个，目标IActors {len(self.target_actors)} 个")

        if not self.driver:
            self.setup_driver()

        # 过 CF 拿 cookie，构建 requests 会话
        if not self._pass_turnstile(TURNSTILE_URL):
            return False, "❌ Cloudflare 打码失败"

        # 打码完成后关闭浏览器，后续用 requests 跑
        if self.driver:
            self.driver.quit()
            self.driver = None

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

    # ---------- 带重试与截图的运行入口 ----------
    def run(self, max_retries=3):
        last_error = ""

        for attempt in range(max_retries):
            try:
                if not self.driver:
                    self.setup_driver()

                if attempt > 0:
                    logger.info(f"🔄 正在进行第 {attempt + 1} 次尝试...")

                success, message = self.process()
                if success:
                    return True, message
                last_error = message

                # 打码失败不重试（重试也是同样的 CF）
                if "打码失败" in message:
                    break

            except Exception as e:
                last_error = f"异常：{str(e)[:80]}"
                logger.error(f"❌ 第 {attempt + 1} 次执行出错: {e}")

            if attempt < max_retries - 1:
                sleep(5000 + random.random() * 5000)

        # 最终失败处理：截图
        self.screenshot_path = "error-spider.png"
        if self.driver:
            try:
                self.driver.save_screenshot(self.screenshot_path)
            except Exception as e:
                logger.warning(f"截图失败: {e}")
        return False, f"❌ 历经 {max_retries} 次尝试仍失败: {last_error}"


# ===================== 主入口 =====================
def _parse_list(env_val, default_list, sep=r'[,;\n]'):
    if not env_val:
        return list(default_list)
    return [x.strip() for x in re.split(sep, env_val) if x.strip()]


def main():
    default_actors = []
    default_pages = [
    ]

    target_actors = _parse_list(TARGET_ACTORS_ENV, default_actors)
    page_urls = _parse_list(PAGE_URLS_ENV, default_pages)

    spider = JisuSpider(target_actors=target_actors, page_urls=page_urls)
    success, msg = spider.run()


    logger.info(f"汇总:\n {msg}")

    send_telegram(msg, spider.screenshot_path)

    # 成功后清理错误截图
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
