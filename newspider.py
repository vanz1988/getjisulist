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

# ===================== YSbrowser 配置 =====================
CHROME_BINARY = os.getenv('CHROME_BINARY', '/home/runner/.ysbrowser/chromium-140.0.7339.133/opt/chromium.org/chromium-unstable/chromium-browser-unstable')
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', '/home/runner/.ysbrowser/chromium-140.0.7339.133/opt/chromium.org/chromium-unstable/chromedriver')
USER_DATA_DIR = os.getenv('USER_DATA_DIR', '/tmp/ysbrowser_profile')
FP_SEED = os.getenv('FP_SEED', '12lfisffwfaTYa')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Hong_Kong')
LANG = os.getenv('LANG', 'zh-CN')
ACCEPT_LANG = os.getenv('ACCEPT_LANG', 'zh-CN,en')
PROXY_AUTH = os.getenv('PROXY_AUTH', '')
WEBRTC_POLICY = os.getenv('WEBRTC_POLICY', 'disabled')
WEBRTC_PROXY_IP = os.getenv('WEBRTC_PROXY_IP', '')
CPU_CORES = os.getenv('CPU_CORES', '6')
PLATFORM_VERSION = os.getenv('PLATFORM_VERSION', '15.4.1')
CUSTOM_SCREEN = os.getenv('CUSTOM_SCREEN', '1792x1120,1792x1039')
GEO_LOCATION = os.getenv('GEO_LOCATION', '')
CHROME_VERSION = os.getenv('CHROME_VERSION', '140.0.7339.185')

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
        if HEADLESS: 
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1280,720')
        chrome_options.add_argument('--nocrash')

        # YSbrowser 指纹与反检测参数
        chrome_options.add_argument(f'--fpseed={FP_SEED}')
        chrome_options.add_argument(f'--webgl-seed={FP_SEED}')
        chrome_options.add_argument(f'--canvas-seed={FP_SEED}')
        chrome_options.add_argument(f'--quota-seed={FP_SEED}')
        chrome_options.add_argument(f'--css-seed={FP_SEED}')
        chrome_options.add_argument(f'--font-seed={FP_SEED}')
        chrome_options.add_argument(f'--audio-seed={FP_SEED}')
        chrome_options.add_argument(f'--svg-seed={FP_SEED}')
        chrome_options.add_argument(f'--speech-seed={FP_SEED}')
        chrome_options.add_argument(f'--rect-seed={FP_SEED}')
        chrome_options.add_argument(f'--gpu-seed={FP_SEED}')
        chrome_options.add_argument(f'--timezone={TIMEZONE}')
        chrome_options.add_argument(f'--lang={LANG}')
        chrome_options.add_argument(f'--accept-lang={ACCEPT_LANG}')
        chrome_options.add_argument(f'--chrome-version={CHROME_VERSION}')
        chrome_options.add_argument(f'--cpucores={CPU_CORES}')
        chrome_options.add_argument(f'--platformversion={PLATFORM_VERSION}')
        chrome_options.add_argument(f'--custom-screen={CUSTOM_SCREEN}')
        chrome_options.add_argument(f'--force-device-scale-factor=1')
        chrome_options.add_argument(f'--webrtc-ip-policy={WEBRTC_POLICY}')
        chrome_options.add_argument(f'--close-portscan')
        chrome_options.add_argument(f'--user-data-dir={USER_DATA_DIR}')

        # 内置自动过 Cloudflare Turnstile + PX 验证码
        #chrome_options.add_argument('--enable-features=TurnstileClicker,PXAutoHold')

        if PROXY_SERVER:
            chrome_options.add_argument(f'--proxy-server={PROXY_SERVER}')
        if PROXY_AUTH:
            chrome_options.add_argument(f'--proxy-auth={PROXY_AUTH}')
        if WEBRTC_PROXY_IP:
            chrome_options.add_argument(f'--webrtc-proxy-ip={WEBRTC_PROXY_IP}')
        if GEO_LOCATION:
            chrome_options.add_argument(f'--custom-geolocation={GEO_LOCATION}')
        else:
            chrome_options.add_argument('--block-geolocation')

        chrome_options.binary_location = CHROME_BINARY

        logger.info(f"🛠️  - YSbrowser 驱动初始化 (binary={CHROME_BINARY}, driver={CHROMEDRIVER_PATH})")

        try:
            self.driver = uc.Chrome(
                options=chrome_options,
                headless=HEADLESS,
                use_subprocess=True,
                driver_executable_path=CHROMEDRIVER_PATH,
                version_main=140,
            )
            logger.info(f"- 驱动启动成功")
        except Exception as e:
            logger.error(f"- 驱动启动失败: {e}")
            raise
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
            sleep(8000) 
            for _ in range(10):
                token = self.driver.execute_script("""
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
                    logger.info(f"token 成功验证")
                    return True
                sleep(500) 

            return validated
        except Exception as e:
            logger.error(f"❌  - [{context}] 验证交互失败: {e}")
            return False

    def _diagnose_turnstile(self):
        try:
            info = self.driver.execute_script("""
                var result = {};
                // 主框架里的 iframe 信息
                var iframes = document.querySelectorAll('iframe');
                result.iframe_count = iframes.length;
                result.iframes = [];
                for (var i = 0; i < iframes.length; i++) {
                    var f = iframes[i];
                    result.iframes.push({
                        src: f.src || '',
                        id: f.id || '',
                        className: f.className || '',
                        width: f.width, height: f.height
                    });
                }
                // 主框架里有 opshadowRoot 的元素
                var allEls = document.querySelectorAll('*');
                var shadowHosts = [];
                for (var i = 0; i < allEls.length; i++) {
                    if (allEls[i].opshadowRoot) {
                        shadowHosts.push({
                            tag: allEls[i].tagName,
                            id: allEls[i].id,
                            className: allEls[i].className,
                            childCount: allEls[i].opshadowRoot.childNodes.length
                        });
                    }
                }
                result.shadow_hosts_in_main = shadowHosts;
                result.shadow_hosts_count = shadowHosts.length;
                return result;
            """)
            logger.info(f"🔍 诊断-主框架: iframe数={info.get('iframe_count')}, "
                        f"opshadowRoot宿主数={info.get('shadow_hosts_count')}")
            for iframe_info in info.get('iframes', []):
                logger.info(f"  📦 iframe: src={iframe_info.get('src','')[:80]}, "
                            f"id={iframe_info.get('id','')}, class={iframe_info.get('className','')}")
            for sh in info.get('shadow_hosts_in_main', []):
                logger.info(f"  🌑 shadow宿主: <{sh.get('tag')}> id={sh.get('id','')}, "
                            f"class={sh.get('className','')}, childNodes={sh.get('childCount')}")
        except Exception as e:
            logger.warning(f"诊断主框架失败: {e}")

        try:
            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            for idx, iframe_el in enumerate(iframes):
                src = iframe_el.get_attribute('src') or ''
                if 'challenges.cloudflare.com' in src or 'turnstile' in src.lower():
                    logger.info(f"🔍 切入 CF iframe[{idx}]: {src[:100]}")
                    self.driver.switch_to.frame(iframe_el)
                    iframe_info = self.driver.execute_script("""
                        var result = {};
                        var allEls = document.querySelectorAll('*');
                        result.total_elements = allEls.length;
                        result.body_html_length = document.body ? document.body.innerHTML.length : 0;
                        var shadowHosts = [];
                        for (var i = 0; i < allEls.length; i++) {
                            if (allEls[i].opshadowRoot) {
                                var sr = allEls[i].opshadowRoot;
                                var inner = sr.innerHTML ? sr.innerHTML.substring(0, 200) : '';
                                shadowHosts.push({
                                    tag: allEls[i].tagName,
                                    id: allEls[i].id || '',
                                    className: allEls[i].className || '',
                                    innerPreview: inner
                                });
                            }
                        }
                        result.shadow_hosts = shadowHosts;
                        result.shadow_hosts_count = shadowHosts.length;
                        // 也检查 checkbox / button
                        result.checkboxes = document.querySelectorAll('input[type="checkbox"]').length;
                        result.buttons = document.querySelectorAll('button').length;
                        return result;
                    """)
                    logger.info(f"🔍 诊断-CF iframe内部: 元素数={iframe_info.get('total_elements')}, "
                                f"HTML长度={iframe_info.get('body_html_length')}, "
                                f"checkbox数={iframe_info.get('checkboxes')}, "
                                f"button数={iframe_info.get('buttons')}, "
                                f"opshadowRoot宿主数={iframe_info.get('shadow_hosts_count')}")
                    for sh in iframe_info.get('shadow_hosts', []):
                        logger.info(f"    🌑 shadow宿主: <{sh.get('tag')}> id={sh.get('id','')}, "
                                    f"class={sh.get('className','')}, inner预览={sh.get('innerPreview','')[:100]}")
                    self.driver.switch_to.default_content()
                    return
            logger.info("🔍 未找到 CF iframe")
        except Exception as e:
            self.driver.switch_to.default_content()
            logger.warning(f"诊断 CF iframe 失败: {e}")

    def _handle_turnstile_via_opshadow(self, context=""):
        try:
            self._diagnose_turnstile()

            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            cf_iframe = None
            for iframe_el in iframes:
                src = iframe_el.get_attribute('src') or ''
                if 'challenges.cloudflare.com' in src or 'turnstile' in src.lower():
                    cf_iframe = iframe_el
                    break

            if not cf_iframe:
                logger.warning(f"🖱️ - [{context}] 未找到 CF Turnstile iframe")
                return False

            self.driver.switch_to.frame(cf_iframe)

            result = self.driver.execute_script("""
                var allEls = document.querySelectorAll('*');
                for (var i = 0; i < allEls.length; i++) {
                    var sr = allEls[i].opshadowRoot;
                    if (sr) {
                        var checkbox = sr.querySelector('input[type="checkbox"]');
                        if (checkbox) {
                            checkbox.click();
                            return 'clicked_checkbox_in_shadow';
                        }
                        var btn = sr.querySelector('button');
                        if (btn) {
                            btn.click();
                            return 'clicked_button_in_shadow';
                        }
                    }
                }
                // iframe 内无 shadow DOM 时，直接找 checkbox
                var cb = document.querySelector('input[type="checkbox"]');
                if (cb) { cb.click(); return 'clicked_checkbox_direct'; }
                var b = document.querySelector('button');
                if (b) { b.click(); return 'clicked_button_direct'; }

                return 'not_found';
            """)

            self.driver.switch_to.default_content()
            logger.info(f"🖱️ - [{context}] opshadowRoot 结果: {result}")
            return result != 'not_found'
        except Exception as e:
            self.driver.switch_to.default_content()
            logger.error(f"❌ - [{context}] opshadowRoot 访问失败: {e}")
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

        # YSbrowser 内置 TurnstileClicker 自动过 CF，直接等待页面放行即可
        if self._find_optional((By.CSS_SELECTOR, '.card-content-h1'), timeout=5):
            logger.info("页面已加载，无需打码")
            self._build_session()
            return True

        #for i in range(max_attempts):
        #    logger.info(f"等待 TurnstileClicker 自动过码，第 {i+1} 次轮询...")
        #    if self._find_optional((By.CSS_SELECTOR, '.card-content-h1'), timeout=10):
        #        logger.info("TurnstileClicker 自动打码成功！")
        #        self._build_session()
        #        return True

        #    logger.info(f"第 {i+1} 次等待未通过，重试...")

        #logger.warning(f"TurnstileClicker 自动打码失败，已尝试 {max_attempts} 次，回退手动打码")
        for i in range(max_attempts):
            logger.info(f"手动打码第 {i+1} 次尝试...")
            self._handle_turnstile_via_opshadow(f"ManualPass-{i+1}")

            if self._find_optional((By.CSS_SELECTOR, '.card-content-h1'), timeout=8):
                logger.info("手动打码成功！")
                self._build_session()
                return True

        logger.warning(f"所有打码方式失败，已尝试 {max_attempts * 2} 次")
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
            self.screenshot_path = "error-spider.png"
            try:
                self.driver.save_screenshot(self.screenshot_path)
            except Exception as e:
                logger.warning(f"截图失败: {e}")
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
