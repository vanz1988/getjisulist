#!/usr/bin/env python3

import os
import time
import logging
import random
import re
import requests
import base64
from datetime import datetime, timezone, timedelta
from DrissionPage import ChromiumPage, ChromiumOptions
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

CHROME_BINARY = os.getenv('CHROME_BINARY', '/root/ysbrowser-extracted/opt/chromium.org/chromium-unstable/chromium-browser-unstable')
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', '/root/ysbrowser-extracted/opt/chromium.org/chromium-unstable/chromedriver')
USER_DATA_DIR = os.getenv('USER_DATA_DIR', '/tmp/ysbrowser_profile')
FP_SEED = os.getenv('FP_SEED', '12lfisffwfaTYa')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Hong_Kong')
LANG = os.getenv('LANG', 'zh-CN')
ACCEPT_LANG = os.getenv('ACCEPT_LANG', 'en')
PROXY_AUTH = os.getenv('PROXY_AUTH', '')
WEBRTC_POLICY = os.getenv('WEBRTC_POLICY', 'disabled')
WEBRTC_PROXY_IP = os.getenv('WEBRTC_PROXY_IP', '')
CPU_CORES = os.getenv('CPU_CORES', '6')
PLATFORM_VERSION = os.getenv('PLATFORM_VERSION', '15.4.1')
CUSTOM_SCREEN = os.getenv('CUSTOM_SCREEN', '1792x1120,1792x1039')
GEO_LOCATION = os.getenv('GEO_LOCATION', '')
CHROME_VERSION = os.getenv('CHROME_VERSION', '140.0.7339.185')


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
        self.page = None
        self.session = None
        self.screenshot_path = None

    def setup_driver(self):
        co = ChromiumOptions()
        co.set_browser_path(CHROME_BINARY)
        co.set_local_port(rand_int(9222, 9322))
        co.auto_port()



        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--window-size=1280,720')
        co.set_argument('--nocrash')

        co.set_argument(f'--fpseed={FP_SEED}')
        co.set_argument(f'--webgl-seed={FP_SEED}')
        co.set_argument(f'--canvas-seed={FP_SEED}')
        co.set_argument(f'--quota-seed={FP_SEED}')
        co.set_argument(f'--css-seed={FP_SEED}')
        co.set_argument(f'--font-seed={FP_SEED}')
        co.set_argument(f'--audio-seed={FP_SEED}')
        co.set_argument(f'--svg-seed={FP_SEED}')
        co.set_argument(f'--speech-seed={FP_SEED}')
        co.set_argument(f'--rect-seed={FP_SEED}')
        co.set_argument(f'--gpu-seed={FP_SEED}')
        co.set_argument(f'--timezone={TIMEZONE}')
        co.set_argument(f'--lang={LANG}')
        co.set_argument(f'--accept-lang={ACCEPT_LANG}')
        co.set_argument(f'--chrome-version={CHROME_VERSION}')
        co.set_argument(f'--cpucores={CPU_CORES}')
        co.set_argument(f'--platformversion={PLATFORM_VERSION}')
        co.set_argument(f'--custom-screen={CUSTOM_SCREEN}')
        co.set_argument('--force-device-scale-factor=1')
        co.set_argument(f'--webrtc-ip-policy={WEBRTC_POLICY}')
        co.set_argument('--close-portscan')
        co.set_argument(f'--user-data-dir={USER_DATA_DIR}')

        if PROXY_SERVER:
            co.set_argument(f'--proxy-server={PROXY_SERVER}')
        if PROXY_AUTH:
            co.set_argument(f'--proxy-auth={PROXY_AUTH}')
        if WEBRTC_PROXY_IP:
            co.set_argument(f'--webrtc-proxy-ip={WEBRTC_PROXY_IP}')
        if GEO_LOCATION:
            co.set_argument(f'--custom-geolocation={GEO_LOCATION}')
        else:
            co.set_argument('--block-geolocation')

        logger.info(f"🛠️  - YSbrowser 驱动初始化 (binary={CHROME_BINARY}, driver={CHROMEDRIVER_PATH})")

        try:
            self.page = ChromiumPage(co)
            logger.info("- 驱动启动成功")
        except Exception as e:
            logger.error(f"- 驱动启动失败: {e}")
            raise

        self.page.set.window.size(1280, 720)

    def _handle_turnstile(self, context=""):
        try:
            container = self.page.ele(
                'xpath://div[contains(@style, "display: grid") and .//input[@name="cf-turnstile-response"]]',
                timeout=15
            )
            if not container:
                logger.warning(f"🖱️ - [{context}] 未找到 Turnstile 容器")
                return False

            logger.info("✅  - 找到元素了")

            size = container.rect.size
            base_offset_x = -(size[0] / 2) + (size[0] * 0.044)
            rand_x = base_offset_x + random.uniform(-5, 5)
            rand_y = random.uniform(-5, 5)

            logger.info(f"🖱️ - [{context}] 找到窗口")

            rect = container.rect
            center_x = rect.location[0] + rect.size[0] / 2
            center_y = rect.location[1] + rect.size[1] / 2
            click_x = center_x + rand_x
            click_y = center_y + rand_y

            click_x = round(click_x)
            click_y = round(click_y)

            logger.info(f"🖱️ - [{context}] 焦点马上点击")

            container.click(offset_x=rand_x, offset_y=rand_y)

            logger.info(f"🖱️ - [{context}] 执行偏移点击...{click_x},{click_y}")

            validated = False
            sleep(8000)
            for _ in range(10):
                token = self.page.run_js("""
                    function queryDeep(selector, root = document) {
                        const result = [];
                        const search = (node) => {
                            for (const el of node.querySelectorAll(selector)) result.push(el);
                            for (const el of node.querySelectorAll('*')) {
                                if (el.shadowRoot) search(el.shadowRoot);
                            }
                        };
                        search(root);
                        return result;
                    }
                    const els = queryDeep('input[name="cf-turnstile-response"]');
                    for (const el of els) {
                        if (el.value && el.value.length > 0) return el.value;
                    }
                    return '';
                """)

                if token:
                    logger.info("token 成功验证")
                    return True
                sleep(500)

            return validated
        except Exception as e:
            logger.error(f"❌  - [{context}] 验证交互失败: {e}")
            return False

    def _handle_turnstile_via_opshadow(self, context=""):
        try:
            cf_iframe = self.page.run_js("""
                var allEls = document.querySelectorAll('*');
                for (var i = 0; i < allEls.length; i++) {
                    var sr = allEls[i].opshadowRoot;
                    if (sr) {
                        var iframe = sr.querySelector('iframe[src*="challenges.cloudflare.com"]');
                        if (iframe) return iframe;
                    }
                }
                return null;
            """)

            if not cf_iframe:
                logger.warning(f"🖱️ - [{context}] opshadowRoot 内未找到 CF iframe")
                return False

            src = cf_iframe.attr('src') or ''
            logger.info(f"🖱️ - [{context}] 从 opshadowRoot 拿到 CF iframe: {src[:80]}")

            cf_page = self.page.get_frame(cf_iframe)

            iframe_info = cf_page.run_js("""
                var r = {total: document.querySelectorAll('*').length, tags: []};
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    r.tags.push(all[i].tagName + (all[i].id ? '#' + all[i].id : '') + (all[i].className ? '.' + all[i].className : ''));
                    if (all[i].opshadowRoot) {
                        var sr = all[i].opshadowRoot;
                        r.tags.push('  [shadow] children=' + sr.children.length + ' inner=' + (sr.innerHTML||'').substring(0,150));
                    }
                }
                return r;
            """)
            logger.info(f"🔍 CF iframe 内部: 元素数={iframe_info.get('total')}, 标签: {iframe_info.get('tags', [])[:30]}")

            # 在 JS 里找 checkbox 并返回其坐标（不点击，让 Python 用真实鼠标点）
            click_target = cf_page.run_js("""
                // 1. opshadowRoot 内找 checkbox（YSbrowser 定制功能）
                var allEls = document.querySelectorAll('*');
                for (var i = 0; i < allEls.length; i++) {
                    var sr = allEls[i].opshadowRoot;
                    if (sr) {
                        var cb = sr.querySelector('input[type="checkbox"]');
                        if (cb) {
                            var r = cb.getBoundingClientRect();
                            return {type: 'checkbox_in_shadow', rect: {x: r.left, y: r.top, w: r.width, h: r.height}};
                        }
                        var lbl = sr.querySelector('label');
                        if (lbl) {
                            var r = lbl.getBoundingClientRect();
                            return {type: 'label_in_shadow', rect: {x: r.left, y: r.top, w: r.width, h: r.height}};
                        }
                    }
                }

                // 2. 渲染为 checkbox 的 div（#KSUV2, #qkbk6 等）
                var checkboxDivs = [
                    document.getElementById('KSUV2'),
                    document.getElementById('qkbk6'),
                    document.querySelector('.NeJGf6'),
                    document.getElementById('CVHe3'),
                    document.querySelector('.BmNg2'),
                    document.querySelector('.MGZG4')
                ];
                for (var j = 0; j < checkboxDivs.length; j++) {
                    var div = checkboxDivs[j];
                    if (div) {
                        var r = div.getBoundingClientRect();
                        return {type: 'div_' + (div.id || div.className || 'unknown') + '_idx' + j, rect: {x: r.left, y: r.top, w: r.width, h: r.height}};
                    }
                }

                // 3. 普通 DOM checkbox
                var cb = document.querySelector('input[type="checkbox"]');
                if (cb) { var r = cb.getBoundingClientRect(); return {type: 'checkbox_direct', rect: {x: r.left, y: r.top, w: r.width, h: r.height}}; }

                // 4. body
                var body = document.querySelector('body');
                if (body) { var r = body.getBoundingClientRect(); return {type: 'body', rect: {x: r.left, y: r.top, w: r.width, h: r.height}}; }

                return null;
            """)

            if click_target:
                rect = click_target['rect']
                w, h = rect['w'], rect['h']
                ox = random.uniform(-3, 3) + (w - 3) * random.random()
                oy = random.uniform(-3, 3) + (h - 3) * random.random()
                cx = rect['x'] + ox
                cy = rect['y'] + oy

                logger.info(f"🖱️ - [{context}] 找到可点击元素: {click_target['type']}，点击坐标({cx:.0f}, {cy:.0f})")

                # 模拟真实鼠标：用 cf_page.actions 在 iframe 上下文里点
                try:
                    actions = cf_page.actions
                    start_x = rect['x'] + w * random.uniform(0.2, 0.8)
                    start_y = rect['y'] + h * random.uniform(0.2, 0.8)
                    actions.move_to((start_x, start_y))
                    time.sleep(random.uniform(0.2, 0.5))
                    actions.move(cx - start_x, cy - start_y)
                    time.sleep(random.uniform(0.1, 0.3))
                    actions.click()
                    logger.info(f"🖱️ - [{context}] 真实鼠标点击完成")
                    sleep(3000 + random.randint(0, 2000))
                    return True
                except Exception as e:
                    logger.error(f"🖱️ - [{context}] 鼠标点击失败: {e}")
                    return False
        except Exception as e:
            logger.error(f"❌ - [{context}] opshadowRoot 访问失败: {e}")
            return False

    def _build_session(self):
        cookies = self.page.cookies()
        ua = self.page.run_js('return navigator.userAgent')

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
        self.page.get(url)
        sleep(3000 + random.random() * 1000)

        if self.page.ele('.card-content-h1', timeout=5):
            logger.info("页面已加载，无需打码")
            self._build_session()
            return True

        for i in range(max_attempts):
            logger.info(f"手动打码第 {i+1} 次尝试...")
            self._handle_turnstile_via_opshadow(f"ManualPass-{i+1}")

            if self.page.ele('.card-content-h1', timeout=8):
                logger.info("手动打码成功！")
                self._build_session()
                return True

        logger.warning(f"所有打码方式失败，已尝试 {max_attempts} 次")
        return False

    def _get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                if self.session:
                    resp = self.session.get(url, timeout=15)
                    resp.raise_for_status()
                    return resp.text
                else:
                    self.page.get(url)
                    return self.page.html
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

        if not self.page:
            self.setup_driver()

        if not self._pass_turnstile(TURNSTILE_URL, 3):
            return False, "❌ Cloudflare 打码失败"

        if self.page:
            self.screenshot_path = "error-spider.png"
            try:
                self.page.get_screenshot(self.screenshot_path)
            except Exception as e:
                logger.warning(f"截图失败: {e}")
            self.page.quit()
            self.page = None

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
                if not self.page:
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
        if self.page:
            try:
                self.page.get_screenshot(self.screenshot_path)
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
