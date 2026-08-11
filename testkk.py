#!/usr/bin/env python3

import os
import time
import logging
import random
import re
import requests
import base64
import subprocess
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from DrissionPage import ChromiumPage, ChromiumOptions
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testsomefunc import ocr_digits
from DrissionPage.common import Keys

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
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', '/root/ysbrowser-extracted/opt/chromium.org/chromium-unstable/chromedriver')
USER_DATA_DIR = os.getenv('USER_DATA_DIR', '/tmp/ysbrowser_profile')
FP_SEED = os.getenv('FP_SEED', '12ltrsfbwfaTYa')
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
        # co.set_argument('--user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"')
        # co.set_argument('--custom-brand="Microsoft Edge"')

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

    def _human_click(self, start_x, start_y, target_x, target_y):
        """
        生物力学级模拟：
        - Fitts' Law 时间-距离模型
        - 三阶段速度剖面（加速 → 巡航 → 减速）
        - 中段修正脉冲（saccadic micro-correction）
        - 8-12Hz 生理震颤
        - 过冲 + 不对称回调
        """
        dx = target_x - start_x
        dy = target_y - start_y
        distance = math.hypot(dx, dy)
        w = 30  # 目标宽度假设

        # === 1. Fitts' Law: MT = 0.4 + 0.1 × log2(2D/W) ===
        id = math.log2(2 * distance / max(w, 1))
        move_ms = 400 + 100 * id + random.uniform(-50, 80)
        move_ms = max(200, min(3500, move_ms))
        total_steps = max(20, min(80, int(move_ms / 16)))  # ~60fps 采样

        if distance < 8:
            self._xdotool_move(target_x, target_y)
            time.sleep(random.uniform(0.12, 0.35))
            self._xdotool_click(target_x, target_y)
            return

        ux = dx / distance
        uy = dy / distance

        self._xdotool_move(start_x, start_y)
        time.sleep(random.uniform(0.08, 0.25))

        # === 2. 启动微犹豫：1-3 次小范围抖动 ===
        amp0 = min(3, int(distance * 0.03))
        for _ in range(random.randint(1, 3)):
            self._xdotool_move(
                start_x + random.randint(-amp0, amp0),
                start_y + random.randint(-amp0, amp0),
            )
            time.sleep(random.uniform(0.015, 0.04))

        # === 3. 路径规划：带中段修正的 3 阶段 ===
        # 在 30%-65% 处随机插一个修正脉冲
        correct_idx = random.randint(int(total_steps * 0.25), int(total_steps * 0.5))
        correct_strength = random.uniform(3, 8)
        correct_angle = random.uniform(0.05, 0.25)
        perp_x, perp_y = -uy, ux  # 垂直方向

        px = float(start_x)
        py = float(start_y)
        last_t = 0
        move_ms_f = move_ms

        # 预生成整条轨迹
        points = []
        for step in range(total_steps + 1):
            t = step / total_steps

            # 三阶段速度：Beta 分布拟合 (accelerate=2.5, cruise=0.5, decelerate=3.5)
            if t < 0.25:
                # 加速段
                speed = (t / 0.25) ** 2.5
            elif t < 0.7:
                # 巡航段，略微波动
                speed = random.uniform(0.9, 1.15)
            else:
                # 减速段
                decelerate = (1 - t) / 0.3
                speed = decelerate ** 2.0 if decelerate > 0 else 0.0

            # 累计距离
            target_dist = t * distance
            step_dist = target_dist - last_t * distance

            # 路径角度：直线为主 + 低频弯曲
            path_angle = random.gauss(0, 0.06)
            ax = ux * math.cos(path_angle) - uy * math.sin(path_angle)
            ay = ux * math.sin(path_angle) + uy * math.cos(path_angle)

            # 应用修正脉冲
            if step == correct_idx:
                step_dist *= random.uniform(0.2, 0.5)
                ax += perp_x * correct_strength / distance
                ay += perp_y * correct_strength / distance

            nx = round(px + step_dist * ax * speed * random.uniform(0.7, 1.3) + random.gauss(0, 1.8))
            ny = round(py + step_dist * ay * speed * random.uniform(0.7, 1.3) + random.gauss(0, 1.8))

            points.append((nx, ny))
            last_t = t
            px, py = nx, ny

        # === 4. 执行 + 8-12Hz 震颤注入 ===
        base_delay = move_ms_f / (total_steps * 1000)
        for i, (nx, ny) in enumerate(points):
            t = i / total_steps

            # 高频震颤：10Hz ±2px，衰减于接近目标
            tremor_amp = 2.0 * (1 - t * 0.7)
            nx += int(random.gauss(0, tremor_amp * 0.5))
            ny += int(random.gauss(0, tremor_amp * 0.5))

            self._xdotool_move(nx, ny)

            # 时间步长：主体均匀 + 随机扰动 + 末段减速
            delay = base_delay * random.uniform(0.7, 1.3)
            if t > 0.7:
                delay *= 1.5 + random.uniform(0, 0.5)
            time.sleep(delay)

        # === 5. 过冲（方向性 + 非均匀分布）===
        overshoot = abs(np.random.gumbel(0, 8))  # Gumbel 分布：偏右、有长尾
        over_x = round(target_x + ux * overshoot + random.gauss(0, 2))
        over_y = round(target_y + uy * overshoot + random.gauss(0, 2))
        self._xdotool_move(over_x, over_y)
        time.sleep(random.uniform(0.02, 0.06))

        # === 6. 回调（通常回调不足，再小幅度过冲，形成"修正-修正"模式）===
        self._xdotool_move(target_x + random.randint(-3, 3), target_y + random.randint(-3, 3))
        time.sleep(random.uniform(0.03, 0.07))

        # 第二次小过冲（20% 概率）
        if random.random() < 0.2:
            self._xdotool_move(
                target_x + random.randint(2, 6),
                target_y + random.randint(2, 6),
            )
            time.sleep(random.uniform(0.02, 0.04))

        # === 7. 最终锚定：2-3 次 ±1px 修正 ===
        for _ in range(random.randint(2, 3)):
            self._xdotool_move(target_x + random.randint(-1, 1), target_y + random.randint(-1, 1))
            time.sleep(random.uniform(0.015, 0.04))
        self._xdotool_move(target_x, target_y)

        # === 8. 点击前等待（非均匀分布，模拟"确认+按"）===
        time.sleep(random.uniform(0.15, 0.5))
        self._xdotool_click(target_x, target_y)

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
                            return cb;
                        }
                    }
                }

                return null;
            """)

            if click_target:
                # 模拟真实鼠标：用 cf_page.actions 在 iframe 上下文里点
                try:


                    # w, h = click_target.rect.size
                    # screen_loc = click_target.rect.screen_location   # (sx, sy) 元素左上角
                    # sx = int(screen_loc[0])
                    # sy = int(screen_loc[1])

                    # # 元素内随机偏移
                    # ox = max(0, min(w, random.gauss(w/2, w/6)))
                    # oy = max(0, min(h, random.gauss(h/2, h/6)))
                    # cx = sx + int(ox)
                    # cy = sy + int(oy)

                    # # 起点：元素内另一个随机点
                    # start_x = sx + int(w * random.uniform(0.2, 0.8))
                    # start_y = sy + int(h * random.uniform(0.2, 0.8))

                    # logger.info(f"🖱️ - [{context}] 屏幕坐标({sx},{sy},{w},{h}) → 点击({cx},{cy}), 起点({start_x},{start_y})")
                    # self._human_click(start_x, start_y, cx, cy)


                    w, h = click_target.rect.size
                    screen_loc = click_target.rect.screen_location   # (sx, sy) 元素左上角
                    sx = int(screen_loc[0])
                    sy = int(screen_loc[1])

                    cx = sx + w / 2
                    cy = sy + h / 2
                    rx = random.gauss(cx, w / 4)
                    ry = random.gauss(cy, h / 4)
                    click_x = int(max(sx, min(sx + w, rx)))
                    click_y = int(max(sy, min(sy + h, ry)))
                    logger.info(f"🖱️ - [{context}] input rect=({sx},{sy}) size=({w:.1f},{h:.1f}) 点击点=({click_x},{click_y})")

                    # 从随机起点出发，走贝塞尔曲线模拟真人
                    start_x = max(1, click_x + random.randint(-300, -100))
                    start_y = max(1, click_y + random.randint(-200, -50))

                    logger.info(f"🖱️ - [{context}] 屏幕坐标({sx},{sy},{w},{h}) → 点击({click_x},{click_y}), 起点({start_x},{start_y})")
                    self._human_click(start_x, start_y, cx, cy)

                    sleep(3000 + random.randint(0, 2000))
                    return True
                except Exception as e:
                    logger.error(f"🖱️ - [{context}] 鼠标点击失败: {e}")
                    return False
            return True
        except Exception as e:
            logger.error(f"❌ - [{context}] opshadowRoot 访问失败: {e}")
            return False




    # def _handle_turnstile_via_opshadow(self, context=""):
    #     try:
    #         cf_iframe = self.page.run_js("""
    #             var allEls = document.querySelectorAll('*');
    #             for (var i = 0; i < allEls.length; i++) {
    #                 var sr = allEls[i].opshadowRoot;
    #                 if (sr) {
    #                     var iframe = sr.querySelector('iframe[src*="challenges.cloudflare.com"]');
    #                     if (iframe) return iframe;
    #                 }
    #             }
    #             return null;
    #         """)

    #         if not cf_iframe:
    #             logger.warning(f"🖱️ - [{context}] opshadowRoot 内未找到 CF iframe")
    #             return False

    #         src = cf_iframe.attr('src') or ''
    #         logger.info(f"🖱️ - [{context}] 从 opshadowRoot 拿到 CF iframe: {src[:80]}")

    #         cf_page = self.page.get_frame(cf_iframe)

    #         iframe_info = cf_page.run_js("""
    #             var r = {total: document.querySelectorAll('*').length, tags: []};
    #             var all = document.querySelectorAll('*');
    #             for (var i = 0; i < all.length; i++) {
    #                 r.tags.push(all[i].tagName + (all[i].id ? '#' + all[i].id : '') + (all[i].className ? '.' + all[i].className : ''));
    #                 if (all[i].opshadowRoot) {
    #                     var sr = all[i].opshadowRoot;
    #                     r.tags.push('  [shadow] children=' + sr.children.length + ' inner=' + (sr.innerHTML||'').substring(0,150));
    #                 }
    #             }
    #             return r;
    #         """)
    #         logger.info(f"🔍 CF iframe 内部: 元素数={iframe_info.get('total')}, 标签: {iframe_info.get('tags', [])[:30]}")

    #         # 在 JS 里找 checkbox 并返回其坐标（不点击，让 Python 用真实鼠标点）
    #         click_target = cf_page.run_js("""
    #             // 1. opshadowRoot 内找 checkbox（YSbrowser 定制功能）
    #             var allEls = document.querySelectorAll('*');
    #             for (var i = 0; i < allEls.length; i++) {
    #                 var sr = allEls[i].opshadowRoot;
    #                 if (sr) {
    #                     var cb = sr.querySelector('input[type="checkbox"]');
    #                     if (cb) {
    #                         var r = cb.getBoundingClientRect();
    #                         return {type: 'checkbox_in_shadow', rect: {x: r.left, y: r.top, w: r.width, h: r.height}};
    #                     }
    #                 }
    #             }

    #             return null;
    #         """)

    #         if click_target:
    #             rect = click_target['rect']
    #             w, h = rect['w'], rect['h']
    #             ox = random.gauss(w/2, w/6)   # 可调整标准差
    #             oy = random.gauss(h/2, h/6)
    #             ox = max(0, min(w, ox))       # 截断到 [0, w]
    #             oy = max(0, min(h, oy))
    #             cx = rect['x'] + ox
    #             cy = rect['y'] + oy
    #             logger.info(f"🖱️ - [{context}] 坐标({rect['x']:.0f}, {rect['y']:.0f}, {rect['w']:.0f}, {rect['h']:.0f})")
    #             #logger.info(f"🖱️ - [{context}] 找到可点击元素: {click_target['type']}，点击坐标({cx:.0f}, {cy:.0f})")

    #             # 模拟真实鼠标：用 cf_page.actions 在 iframe 上下文里点
    #             try:
    #                 actions = cf_page.actions
    #                 start_x = rect['x'] + w * random.uniform(0.2, 0.8)
    #                 start_y = rect['y'] + h * random.uniform(0.2, 0.8)
    #                 logger.info(f"🖱️ - [{context}] 找到可点击元素: {click_target['type']}，起点坐标({start_x:.0f}, {start_y:.0f}),点击坐标({cx:.0f}, {cy:.0f})")
    #                 actions.move_to((start_x, start_y))
    #                 time.sleep(random.uniform(0.2, 0.5))
    #                 actions.move(cx - start_x, cy - start_y)
    #                 time.sleep(random.uniform(0.1, 0.3))
    #                 actions.click()
    #                 logger.info(f"🖱️ - [{context}] 真实鼠标点击完成")
    #                 sleep(3000 + random.randint(0, 2000))
    #                 return True
    #             except Exception as e:
    #                 logger.error(f"🖱️ - [{context}] 鼠标点击失败: {e}")
    #                 return False
    #         return True
    #     except Exception as e:
    #         logger.error(f"❌ - [{context}] opshadowRoot 访问失败: {e}")
    #         return False

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

    def _handle_verify_ocr(self, attempt):
        try:
            img_elem = self.page.ele('.mac_verify_img', timeout=3)
            timestamp = int(time.time())
            img_path = f'/tmp/captcha_{timestamp}.png'
            res = self.page.listen.wait(timeout=10)

            if res:
                img_bytes = res.response.body
                with open(img_path, 'wb') as f:
                    f.write(img_bytes) 
            else:
                logger.warning(f"OCR: 未找到验证码图片元素")
                url = self.page.url
                self.page.browser.close_tabs(self.page.tab_id)
                sleep(500)
                self.page = self.page.browser.new_tab(url)
                sleep(2500)
                return False
                digit = ''.join(random.choices('0123456789', k=4))
                input_elem = self.page.ele("@name:verify", timeout=5)
                if not input_elem:
                    logger.warning(f"OCR: 未找到验证码输入框")
                    return False
                logger.info(f"已找到输入框, type={input_elem.attr('type')}")

                input_elem.clear(by_js=True)      # JS 直接设置 value=''
                input_elem.input(digit, by_js=True)
                logger.info(f"已输入验证码: {digit}")
                sleep(500)

                btn = self.page.ele('.verify_submit', timeout=5)
                if btn:
                    logger.info(f"已找到提交按钮, value={btn.attr('value')}")
                    btn.click()
                    logger.info(f"✅ 已点击提交按钮")
                else:
                    logger.warning(f"OCR: 未找到提交按钮，尝试JS点击")
                    self.page.run_js(
                        "var btns=document.querySelectorAll('.verify_submit'); if(btns.length) btns[0].click();")
                    logger.info(f"✅ 已通过JS触发提交")

                sleep(4500)

                # 检查是否有 alert 弹窗
                try:
                    if self.page.states.has_alert:
                        alert_text = self.page.handle_alert(accept=True)
                        sleep(3000)
                        logger.info(f"⚠️  - 捕获到弹窗提示: {alert_text}")
                    else:
                        logger.info(f"ℹ️  - 无alert弹窗")
                except Exception as e:
                    logger.warning(f"ℹ️  - 检查alert异常: {e}")
                return False

            if not img_elem:
                
                return False

            # img_path = '/tmp/captcha.png'
            # timestamp = int(time.time())
            # img_path = f'/tmp/captcha_{timestamp}.png'
            #img_elem.get_screenshot(path=img_path)
            logger.info(f"📷 已截取验证码图片")

            # mac_verify_img_elem = self.page.ele("@class:mac_verify_img", timeout=5)
            # if not mac_verify_img_elem:
            #     logger.warning("未找到验证码图片")
            #     return False
            # mac_verify_img_elem.click()
            # logger.info("已点击刷新验证码")

            # sleep(5000)
            # return False

            logger.info(f"🔢 OCR识别中...")
            digit = ocr_digits(img_path)

            if not digit:
                logger.warning(f"OCR识别为空")
                return False

            logger.info(f"🔢 OCR识别结果: {digit}")

            if len(digit)!=4:
                mac_verify_img_elem = self.page.ele("@class:mac_verify_img", timeout=5)
                if mac_verify_img_elem:
                    mac_verify_img_elem.click()
                    logger.info("已点击刷新验证码")
                    sleep(2000)
                    return False

            #input_elem = self.page.ele("input[name='verify']", timeout=5)
            input_elem = self.page.ele("@name:verify", timeout=5)
            if not input_elem:
                logger.warning(f"OCR: 未找到验证码输入框")
                return False
            logger.info(f"已找到输入框, type={input_elem.attr('type')}")





            input_elem.clear(by_js=True)      # JS 直接设置 value=''
            input_elem.input(digit, by_js=True)
            logger.info(f"已输入验证码: {digit}")
            sleep(500)

            btn = self.page.ele('.verify_submit', timeout=5)
            if btn:
                logger.info(f"已找到提交按钮, value={btn.attr('value')}")
                btn.click()
                logger.info(f"✅ 已点击提交按钮")
            else:
                logger.warning(f"OCR: 未找到提交按钮，尝试JS点击")
                self.page.run_js(
                    "var btns=document.querySelectorAll('.verify_submit'); if(btns.length) btns[0].click();")
                logger.info(f"✅ 已通过JS触发提交")

            sleep(4500)

            # 检查是否有 alert 弹窗
            try:
                if self.page.states.has_alert:
                    alert_text = self.page.handle_alert(accept=True)
                    sleep(3000)
                    logger.info(f"⚠️  - 捕获到弹窗提示: {alert_text}")
                else:
                    logger.info(f"ℹ️  - 无alert弹窗")
            except Exception as e:
                logger.warning(f"ℹ️  - 检查alert异常: {e}")




            if self.page.ele('.card-content-h1', timeout=5):
                logger.info("OCR打码成功！")
                return True

            logger.info(f"OCR打码失败，继续尝试...")
            return False

        except Exception as e:
            logger.warning(f"OCR打码异常: {e}")
            return False

    def _pass_turnstile(self, url, max_attempts=5):

        self.page.listen.start('https://www.jisuzy.com/index.php/verify/index.html')

        self.page.get(url)
        sleep(4000 + random.random() * 1000)

        if self.page.ele('.card-content-h1', timeout=5):
            logger.info("页面已加载，无需打码")
            sleep(3000)
            self._build_session()
            return True
        maxnumattempts=13
        for i in range(maxnumattempts):
            logger.info(f"OCR验证码识别第 {i+1} 次尝试...")
            if self._handle_verify_ocr(i):
                sleep(3000)
                self._build_session()
                return True
            sleep(2000)

        # for i in range(max_attempts):
        #     logger.info(f"手动打码第 {i+1} 次尝试...")
        #     self._handle_turnstile_via_opshadow(f"ManualPass-{i+1}")

        #     if self.page.ele('.card-content-h1', timeout=6):
        #         logger.info("页面已加载，打码成功")
        #         sleep(3000)
        #         self._build_session()
        #         return True
        #     sleep(5000)

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

        common_chars = "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严龙飞"
        captcha_text = random.choice(common_chars)

        captcha_code = ''.join(random.choices(common_chars, k=3))

        if not self._pass_turnstile(TURNSTILE_URL+captcha_code, 3):
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

