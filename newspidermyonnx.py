#!/usr/bin/env python3

import math
import os
import sys
import time
import logging
import random
import re
import requests
import subprocess
import base64
import numpy as np

try:
    import onnxruntime as ort
except Exception:
    ort = None

#import pyautogui
from datetime import datetime, timezone, timedelta
from DrissionPage import ChromiumPage, ChromiumOptions
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADLESS = os.getenv('HEADLESS', 'false').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID', '')
PROXY_SERVER = os.getenv('HTTP_PROXY', '')
TARGET_ACTORS_ENV = os.getenv('TARGET_ACTORS', '')
PAGE_URLS_ENV = os.getenv('PAGE_URLS', '')
TURNSTILE_URL = os.getenv('TURNSTILE_URL', 'https://www.ji.com')
encoded_url = os.getenv('HOST_URL', 'aHR0cHM6Ly93d3cuamkuY29t')
HOST_URL = base64.b64decode(encoded_url).decode('utf-8')

CHROME_BINARY = os.getenv('CHROME_BINARY', '/root/ysbrowser-extracted/opt/chromium.org/chromium-unstable/chromium-browser-unstable')
#CHROME_BINARY = os.getenv('CHROME_BINARY', '')
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', '/root/ysbrowser-extracted/opt/chromium.org/chromium-unstable/chromedriver')
USER_DATA_DIR = os.getenv('USER_DATA_DIR', '/tmp/ysbrowser_profile')
FP_SEED = os.getenv('FP_SEED', '12lfisfbwfaTYa')
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


def _activate_window():
    for cls in ["chromium-browser-unstable", "chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.3)
                return True
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _xdotool_click(screen_x, screen_y):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(screen_x), str(screen_y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        subprocess.run(f"xdotool mousemove {screen_x} {screen_y} click 1 2>/dev/null", shell=True)
        return False


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

        #co.headless()

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
        try:
            self.page.get('https://api.ip.sb/ip')
            ip = self.page('tag:body').text.strip()
            logger.info(f"📍 当前出口IP: {ip[:60]}")
        except Exception as e:
            logger.error(f"❌  获取当前出口IP失败: {e}")

    def _check_turnstile_status(self,  max_attempts=8):
        try:
            for i in range(max_attempts):
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
                    logger.warning(f"验证可能跳过了")
                    return True
    
                src = cf_iframe.attr('src') or ''
                logger.info(f"从 opshadowRoot 拿到 CF iframe: {src[:80]}")
    
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
                        if (el.value && el.value.length > 20) return el.value;
                    }
                    return '';
                """)
    
                if token:
                    logger.info("token 成功验证")
                    return True

                sleep(1000)


            return False
        except Exception as e:
            logger.error(f"❌  验证交互失败: {e}")
            return False

    def _xdotool_move(self, x, y):
        """用 xdotool 移动鼠标"""
        try:
            subprocess.run(
                ["xdotool", "mousemove", str(x), str(y)],
                check=True, capture_output=True, timeout=2
            )
        except Exception:
            pass

    def _xdotool_click(self, x, y):
        """用 xdotool 点击"""
        try:
            subprocess.run(
                ["xdotool", "mousemove", str(x), str(y), "click", "1"],
                check=True, capture_output=True, timeout=3
            )
        except Exception as e:
            logger.error(f"🖱️ - xdotool click 失败: {e}")

    def _smooth_points(self, points, window=5):
        if len(points) <= 2 or window < 3:
            return points
        half = window // 2
        result = [points[0]]
        for i in range(1, len(points) - 1):
            left = max(0, i - half)
            right = min(len(points), i + half + 1)
            chunk = points[left:right]
            xs = sum(p[0] for p in chunk) / len(chunk)
            ys = sum(p[1] for p in chunk) / len(chunk)
            result.append((xs, ys))
        result.append(points[-1])
        return result

    def _get_remove_indices(self, n, gap_min=1, gap_max=3):
        remove = set()
        for _ in range(n // 4):
            idx = random.randint(gap_min, n - gap_max - 1)
            remove.add(idx)
            if idx > 0:
                remove.discard(idx - 1)
            if idx < n - 1:
                remove.discard(idx + 1)
        return remove

    def _ai_mouse_path(self, begin_x, begin_y, end_x, end_y):
        """用 123.onnx 生成轨迹、返回 [(x, y, delay_ms), ...]"""
        if not hasattr(self, '_mouse_sess') or self._mouse_sess is None:
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '123.onnx'
            )
            if ort is not None and os.path.exists(model_path):
                self._mouse_sess = ort.InferenceSession(model_path)
                self._mouse_inp_name = self._mouse_sess.get_inputs()[0].name
                self._mouse_out_name = self._mouse_sess.get_outputs()[0].name
                logger.info("AI mouse model loaded: " + model_path)
            else:
                logger.warning("AI mouse model not available")
                return None

        ddx = end_x - begin_x
        ddy = end_y - begin_y
        dist = math.hypot(ddx, ddy)
        if dist < 1:
            return [(int(end_x), int(end_y), 0)]

        cos_a = ddx / dist
        sin_a = ddy / dist

        input_data = np.array([[[float(dist), 2.0]]], dtype=np.float32)
        output = self._mouse_sess.run(
            [self._mouse_out_name],
            {self._mouse_inp_name: input_data}
        )[0]
        out = output[0]

        n_steps = out.shape[0]
        if n_steps > 30:
            remove = self._get_remove_indices(n_steps, 1, 3)
        else:
            remove = set()

        last_t = 0.0
        path = []
        for i in range(n_steps):
            # if i in remove:
            #     continue
            lx = out[i, 0]
            ly = out[i, 1]
            raw_t = out[i, 2]
            delay = raw_t - last_t
            last_t = raw_t
            if delay <= 0:
                delay = 0.001
            px = lx * cos_a - ly * sin_a + begin_x
            py = lx * sin_a + ly * cos_a + begin_y
            delay_ms = int(delay * 200.0)
            path.append((int(round(px)), int(round(py)), delay_ms))

        path.append((int(round(end_x)), int(round(end_y)), 0))
        return path

    def _human_click(self, start_x, start_y, target_x, target_y):
        path = self._ai_mouse_path(start_x, start_y, target_x, target_y)
        if not path or len(path) < 3:
            path = [(int(target_x), int(target_y), 0)]
        return path

    def _handle_turnstile_via_opshadow(self, context=""):
        try:

            t_elem = self.page.ele("@name=cf-turnstile-response", timeout=5)
            if not t_elem:
                logger.warning(f"🖱️ - [{context}] 未找到 cf-turnstile-response")
                return False

            try:
                sr = t_elem.parent().shadow_root
                frame = sr.ele("tag:iframe", timeout=5)
                input_e = frame.ele("tag:body").shadow_root.ele("tag:input", timeout=5)
                logger.info(f"🖱️ - [{context}] 找到 input 元素")

                # 所有可能的坐标源


                sl = input_e.rect.screen_location
                vl = input_e.rect.viewport_location
                page_loc = input_e.rect.location
                sm = input_e.rect.screen_midpoint
                size = input_e.rect.size
                frame_vl = frame.rect.viewport_location
                frame_loc = frame.rect.location
                frame_sl = frame.rect.screen_location
                logger.info(f"🖱️ - [{context}] input: screen_loc={sl} viewport_loc={vl} page_loc={page_loc} screen_mid={sm} size={size}")
                logger.info(f"🖱️ - [{context}] frame: viewport_loc={frame_vl} page_loc={frame_loc} screen_loc={frame_sl}")

                # 手动计算：window.screenX/Y + chromeTop + iframe在页面上的位置 + input在iframe内的位置
                win_info = self.page.run_js("""
                    return {
                        screenX: window.screenX,
                        screenY: window.screenY,
                        chromeTop: window.outerHeight - window.innerHeight,
                        scrollX: window.scrollX,
                        scrollY: window.scrollY
                    };
                """)
                logger.info(f"🖱️ - [{context}] window: screenX={win_info['screenX']} screenY={win_info['screenY']} chromeTop={win_info['chromeTop']} scroll=({win_info['scrollX']},{win_info['scrollY']})")

                # 用手动坐标做点击
                manual_x = int(win_info['screenX'] + frame_vl[0] + vl[0])
                manual_y = int(win_info['screenY'] + win_info['chromeTop'] + frame_vl[1] + vl[1])
                logger.info(f"🖱️ - [{context}] 手动计算屏幕坐标: ({manual_x},{manual_y})")
                logger.info(f"🖱️ - [{context}] DrissionPage screen_loc: ({int(sl[0])},{int(sl[1])})")

                # 用 DrissionPage 算好的 input 屏幕中心点
                click_x = manual_x+size[1]*random.uniform(0.2, 0.6)
                click_y = manual_y+size[1]*random.uniform(0.2, 0.6)
                logger.info(f"🖱️ - [{context}] 目标点击坐标: ({click_x},{click_y})")

                # 从随机起点出发，走贝塞尔曲线模拟真人
                start_x = max(1, click_x + random.randint(-300, -100))
                start_y = max(1, click_y + random.randint(-200, -50))

                path = self._human_click(start_x, start_y, click_x, click_y)
                tmpx = start_x
                tmpy = start_y
                self._xdotool_move(start_x, start_y)
                time.sleep(random.uniform(0.1, 0.3))
                nindex=3
                if path:
                    print(f"步数: {len(path)}")
                    maxindex=0
                    # if len(path)>49:
                    #     maxindex=13
                    for i, (x, y, delay_ms) in enumerate(path):
                        nindex=nindex+1
                        if nindex>maxindex:
                            nindex=0
                            print(f"  {i}: ({x}, {y}) delay={delay_ms}ms")
                            self._xdotool_move(x, y)
                            tmpx=x
                            tmpy=y
                            time.sleep(delay_ms/1000.0)


                #self._xdotool_move(click_x, click_y)
                #time.sleep(random.uniform(0.2, 0.5))
                self._xdotool_click(click_x, click_y)

                return True

            except Exception as e:
                logger.error(f"🖱️ - [{context}] shadow_root 路径失败: {e}")
                return False

        except Exception as e:
            logger.error(f"❌ - [{context}] turnstile 处理失败: {e}")
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
        sleep(4000 + random.random() * 1000)

        if self.page.ele('.card-content-h1', timeout=5):
            logger.info("页面已加载，无需打码")
            sleep(3000)
            self._build_session()
            return True

        #if self._check_turnstile_status(1):
        #    logger.info("页面已加载，无需打码")
        #    self._build_session()
        #    return True

        for i in range(max_attempts):
            logger.info(f"手动打码第 {i+1} 次尝试...")
            self._handle_turnstile_via_opshadow(f"ManualPass-{i+1}")

            if self.page.ele('.card-content-h1', timeout=8):
                logger.info("页面已加载，打码成功")
                sleep(3000)
                self._build_session()
                return True
            sleep(5000)

        sleep(3000)
        self._build_session()
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

        if not self._pass_turnstile(TURNSTILE_URL, 1):
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
        # for page_url in self.page_urls:
        #     detail_urls = self.get_detail_urls(page_url)

        #     for i, detail_url in enumerate(detail_urls):
        #         if i > 0:
        #             sleep(100)
        #         drama_info = self.get_drama_info(detail_url)
        #         if drama_info:
        #             all_dramas.append(drama_info)

        #     logger.info(f"完成列表页: {page_url}, 累计抓取: {len(all_dramas)} 条数据")
        #     sleep(1000)

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