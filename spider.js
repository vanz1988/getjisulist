const { chromium } = require('playwright');
const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');

// ===================== 配置 =====================
const TELEGRAM_BOT_TOKEN = process.env.BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.CHAT_ID || '';
const TARGET_ACTORS_ENV = process.env.TARGET_ACTORS || '';
const PAGE_URLS_ENV = process.env.PAGE_URLS || '';
const TURNSTILE_URL = process.env.TURNSTILE_URL || 'https://www.ji.com';
const ENCODED_URL = process.env.HOST_URL || 'aHR0cHM6Ly93d3cuamkuY29t';
const HOST_URL = Buffer.from(ENCODED_URL, 'base64').toString('utf-8');
const CDP_PORT = 9222;

function parseList(envVal, defaultList) {
    if (!envVal) return [...defaultList];
    return envVal.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);
}

const defaultActors = [];
const defaultPages = [];
const TARGET_ACTORS = parseList(TARGET_ACTORS_ENV, defaultActors);
const PAGE_URLS = parseList(PAGE_URLS_ENV, defaultPages);

// ===================== 工具函数 =====================
function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

// ===================== Telegram 通知 =====================
async function sendTelegram(message, screenshotPath) {
    if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) return;
    const timeStr = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Hong_Kong' }) + ' HKT';
    const fullMessage = `🎉 短剧 \n\n：${timeStr}\n\n${message}`;
    try {
        if (screenshotPath && fs.existsSync(screenshotPath)) {
            const fileBuffer = fs.readFileSync(screenshotPath);
            const formData = new FormData();
            formData.append('chat_id', TELEGRAM_CHAT_ID);
            formData.append('caption', fullMessage);
            formData.append('photo', new Blob([fileBuffer]), path.basename(screenshotPath));
            await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto`, {
                method: 'POST',
                body: formData,
            });
        } else {
            await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: TELEGRAM_CHAT_ID, text: fullMessage }),
            });
        }
        console.log('✅ Telegram 通知发送成功');
    } catch (e) {
        console.log(`⚠️ Telegram 发送失败: ${e.message}`);
    }
}



// ===================== 工具：通过 CDP 派发鼠标点击 =====================
async function dispatchCdpClick(page, x, y) {
    const client = await page.context().newCDPSession(page);
    try {
        await client.send('Input.dispatchMouseEvent', {
            type: 'mousePressed',
            x, y,
            button: 'left',
            clickCount: 1
        });
        await new Promise(r => setTimeout(r, 50 + Math.random() * 100));
        await client.send('Input.dispatchMouseEvent', {
            type: 'mouseReleased',
            x, y,
            button: 'left',
            clickCount: 1
        });
        console.log(`>> CDP 点击 (${x.toFixed(2)}, ${y.toFixed(2)})`);
        return true;
    } catch (e) {
        console.log('CDP 点击失败:', e.message);
        return false;
    } finally {
        await client.detach().catch(() => {});
    }
}

// ===================== Turnstile 检测与解决 =====================
async function hasTurnstileFrame(page) {
    try {
        const count = await page.locator('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"]').count();
        return count > 0;
    } catch { return false; }
}

async function checkTurnstileSuccess(page) {
    try {
        const token = await page.evaluate(() => {
            const el = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
            return el ? el.value : '';
        });
        if (token && token.length > 20) return true;
    } catch {}
    // 检查 frame 中的 "Success!"
    const frames = page.frames();
    for (const f of frames) {
        if (f.url().includes('cloudflare')) {
            try {
                const visible = await f.getByText('Success!', { exact: false }).isVisible({ timeout: 500 });
                if (visible) return true;
            } catch {}
        }
    }
    return false;
}


async function attemptTurnstileCdp(page) {
    const frames = page.frames();
    for (const frame of frames) {
        try {
            const data = await frame.evaluate(() => window.__turnstile_data).catch(() => null);

            if (data) {
                console.log('>> 在 frame 中发现 Turnstile。比例:', data);

                const iframeElement = await frame.frameElement();
                if (!iframeElement) continue;

                const box = await iframeElement.boundingBox();
                if (!box) continue;

                const clickX = box.x + (box.width * data.xRatio);
                const clickY = box.y + (box.height * data.yRatio);

                console.log(`>> 计算点击坐标: (${clickX.toFixed(2)}, ${clickY.toFixed(2)})`);

                const client = await page.context().newCDPSession(page);

                await client.send('Input.dispatchMouseEvent', {
                    type: 'mousePressed',
                    x: clickX,
                    y: clickY,
                    button: 'left',
                    clickCount: 1
                });

                await new Promise(r => setTimeout(r, 50 + Math.random() * 100));

                await client.send('Input.dispatchMouseEvent', {
                    type: 'mouseReleased',
                    x: clickX,
                    y: clickY,
                    button: 'left',
                    clickCount: 1
                });

                console.log('>> CDP 点击已发送。');
                await client.detach();
                return true;
            }
        } catch (e) { }
    }
    return false;
}


async function solveTurnstile(page, stageName = '爬虫', maxAttempts = 10, waitAfterClick = 5000) {
    console.log(`[${stageName}] 开始检测 Turnstile...`);
    let saw = false;
    for (let i = 0; i < maxAttempts; i++) {
        if (await hasTurnstileFrame(page)) saw = true;
        if (await checkTurnstileSuccess(page)) {
            console.log(`[${stageName}] ✅ Turnstile 已通过`);
            return true;
        }
        const clicked = await attemptTurnstileCdp(page);
        if (clicked) {
            saw = true;
            console.log(`[${stageName}] 点击了 Turnstile，等待 ${waitAfterClick}ms...`);
            await page.waitForTimeout(waitAfterClick);
            if (await checkTurnstileSuccess(page)) {
                console.log(`[${stageName}] ✅ Turnstile 验证成功`);
                return true;
            }
            console.log(`[${stageName}] ⚠️ 验证未通过，重试...`);
        }
        if (i < maxAttempts - 1) await page.waitForTimeout(1000);
    }
    if (!saw) {
        console.log(`[${stageName}] 未检测到 Turnstile`);
        return true;
    }
    console.log(`[${stageName}] ❌ Turnstile 处理超时`);
    return false;
}

// ===================== 注入脚本（获取 Turnstile 复选框坐标） =====================
const INJECT_SCRIPT = `
(function() {
    if (window.self === window.top) return;

    // 1. 模拟鼠标屏幕坐标
    try {
        function getRandomInt(min, max) {
            return Math.floor(Math.random() * (max - min + 1)) + min;
        }
        let screenX = getRandomInt(800, 1200);
        let screenY = getRandomInt(400, 600);
        
        Object.defineProperty(MouseEvent.prototype, 'screenX', { value: screenX });
        Object.defineProperty(MouseEvent.prototype, 'screenY', { value: screenY });
    } catch (e) { }

    // 2. 简单的 attachShadow Hook
    try {
        const originalAttachShadow = Element.prototype.attachShadow;
        
        Element.prototype.attachShadow = function(init) {
            const shadowRoot = originalAttachShadow.call(this, init);
            
            if (shadowRoot) {
                const checkAndReport = () => {
                    const checkbox = shadowRoot.querySelector('input[type="checkbox"]');
                    if (checkbox) {
                        const rect = checkbox.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.innerWidth > 0 && window.innerHeight > 0) {
                            const xRatio = (rect.left + rect.width / 2) / window.innerWidth;
                            const yRatio = (rect.top + rect.height / 2) / window.innerHeight;
                            window.__turnstile_data = { xRatio, yRatio };
                            return true;
                        }
                    }
                    return false;
                };

                if (!checkAndReport()) {
                    const observer = new MutationObserver(() => {
                        if (checkAndReport()) observer.disconnect();
                    });
                    observer.observe(shadowRoot, { childList: true, subtree: true });
                }
            }
            return shadowRoot;
        };
    } catch (e) {
        console.error('[注入] Hook attachShadow 失败:', e);
    }
})();
`;

// ===================== 爬虫核心类 =====================
class JisuSpider {
    constructor() {
        this.baseUrl = HOST_URL;
        this.targetActors = TARGET_ACTORS;
        this.pageUrls = PAGE_URLS;
        this.browser = null;
        this.page = null;
        this.session = null;
        this.screenshotPath = null;
    }

    async setupDriver() {
        console.log('🛠️  - 驱动初始化');
        try {
            this.browser = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
            console.log('- 驱动启动成功');
        } catch (e) {
            console.error(`- 驱动启动失败: ${e.message}`);
            throw e;
        }
        const context = this.browser.contexts()[0];
        if (!context) {
            throw new Error('无法获取浏览器上下文');
        }
        this.page = context.pages().length > 0 ? context.pages()[0] : await context.newPage();
        await this.page.setViewportSize({ width: 1280, height: 720 });
        await this.page.addInitScript(INJECT_SCRIPT);
    }

    async buildSession() {
        const cookies = await this.page.context().cookies();
        const ua = await this.page.evaluate(() => navigator.userAgent);

        const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
        this.session = axios.create({
            headers: {
                'User-Agent': ua,
                'Referer': this.baseUrl,
                'Cookie': cookieStr,
            },
            timeout: 15000,
        });
        console.log(`已构建 axios 会话，cookies: ${cookies.length} 个`);
    }

    async passTurnstile(url, maxAttempts = 5) {
        console.log(`🌐 访问 Turnstile URL: ${url}`);

        await this.page.goto(url, { waitUntil: 'domcontentloaded' });
        await sleep(3000 + Math.random() * 1000);

        try {
            await this.page.waitForSelector('.card-content-h1', { timeout: 5000 });
            console.log('页面已加载，无需打码');
            await this.buildSession();
            return true;
        } catch {}

        let cdpClickResult = false;
        for (let findAttempt = 0; findAttempt < 15; findAttempt++) {
            cdpClickResult = await attemptTurnstileCdp(this.page);
            if (cdpClickResult) break;
            await this.page.waitForTimeout(1000);
        }

        if (cdpClickResult) {
            console.log('   >> 登录 CDP 点击生效。正在等待最多 10秒 Cloudflare 成功标志...');
            for (let waitSec = 0; waitSec < 10; waitSec++) {
                const frames = this.page.frames();
                let isSuccess = false;
                for (const f of frames) {
                    if (f.url().includes('cloudflare')) {
                        try {
                            if (await f.getByText('Success!', { exact: false }).isVisible({ timeout: 500 })) {
                                isSuccess = true;
                                break;
                            }
                        } catch (e) { }
                    }
                }
                if (isSuccess) {
                    console.log('   >> 登录前 Turnstile 验证成功。');
                    break;
                }
                await this.page.waitForTimeout(1000);
            }
        } else {
            console.log('   >> 登录前未检测到或未点击 Turnstile，继续操作...');
        }

        for (let i = 0; i < maxAttempts; i++) {
            console.log(`打码第 ${i + 1} 次尝试...`);
            if (await solveTurnstile(this.page, `PassTurnstile-${i + 1}`, 5, 3000)) {
                try {
                    await this.page.waitForSelector('.card-content-h1', { timeout: 8000 });
                    console.log('打码成功！');
                    await this.buildSession();
                    return true;
                } catch {}
            }
            console.log(`第 ${i + 1} 次打码未通过，重试...`);
        }

        console.log(`打码失败，已尝试 ${maxAttempts} 次`);
        return false;
    }

    async getPage(url, retries = 3) {
        for (let attempt = 0; attempt < retries; attempt++) {
            try {
                if (this.session) {
                    const resp = await this.session.get(url);
                    return typeof resp.data === 'string' ? resp.data : String(resp.data);
                }
            } catch (e) {
                console.log(`访问失败 ${url} (第${attempt + 1}次): ${e.message}`);
                await sleep(2000);
            }
        }
        return null;
    }

    async getDetailUrls(pageUrl) {
        const detailUrls = [];
        const html = await this.getPage(pageUrl);
        if (!html) return detailUrls;

        const $ = cheerio.load(html);
        $('.list-item').each((_, item) => {
            const link = $(item).find('a').attr('href');
            if (link) {
                const fullUrl = link.startsWith('/') ? this.baseUrl + link : link;
                detailUrls.push(fullUrl);
            }
        });

        console.log(`从 ${pageUrl} 获取到 ${detailUrls.length} 个详情链接`);
        return detailUrls;
    }

    async getDramaInfo(detailUrl) {
        try {
            const html = await this.getPage(detailUrl);
            if (!html) return null;

            const $ = cheerio.load(html);

            let title = null;
            const titleTag = $('div.vod-title h2');
            if (titleTag.length) title = titleTag.text().trim();
            if (!title) {
                const match = html.match(/<h2>(.*?)<\/h2>/);
                if (match) title = match[1];
            }

            let actors = null;
            $('li').each((_, li) => {
                const text = $(li).text();
                if (text && text.includes('主演：')) {
                    actors = text.split('主演：')[1]?.trim() || null;
                    return false;
                }
            });
            if (!actors) {
                const match = html.match(/主演：<span>(.*?)<\/span>/);
                if (match) actors = match[1];
            }

            if (!title || !actors) {
                console.log(`详情页数据不完整: ${detailUrl}`);
                return null;
            }

            if (this.targetActors.length > 0) {
                const matched = this.targetActors.some(actor => actors.includes(actor));
                if (!matched) {
                    console.log(`跳过 ${title}，IActors ${actors} 不包含目标IActors`);
                    return null;
                }
            }

            console.log(`成功抓取: ${title} - IActors: ${actors}`);
            return { title, actors, url: detailUrl };
        } catch (e) {
            console.log(`获取详情页失败 ${detailUrl}: ${e.message}`);
            return null;
        }
    }

    async process() {
        console.log(`🚀 开始抓取，列表页 ${this.pageUrls.length} 个，目标IActors ${this.targetActors.length} 个`);

        if (!this.page) await this.setupDriver();

        if (!await this.passTurnstile(TURNSTILE_URL)) {
            return [false, '❌ Cloudflare 打码失败'];
        }

        if (this.browser) {
            await this.browser.close().catch(() => {});
            this.browser = null;
            this.page = null;
        }

        const allDramas = [];
        for (const pageUrl of this.pageUrls) {
            const detailUrls = await this.getDetailUrls(pageUrl);

            for (let i = 0; i < detailUrls.length; i++) {
                if (i > 0) await sleep(100);
                const dramaInfo = await this.getDramaInfo(detailUrls[i]);
                if (dramaInfo) allDramas.push(dramaInfo);
            }

            console.log(`完成列表页: ${pageUrl}, 累计抓取: ${allDramas.length} 条数据`);
            await sleep(1000);
        }

        let summary = `📊 抓取完成！共 ${allDramas.length} 部\n\n`;
        allDramas.forEach((drama, idx) => {
            summary += `${idx + 1}. ${drama.title} | IActors: ${drama.actors} | ${drama.url}\n`;
        });

        console.log('\n' + '='.repeat(50));
        console.log(`抓取完成！共 ${allDramas.length} 部`);
        return [true, summary];
    }

    async run(maxRetries = 3) {
        let lastError = '';

        for (let attempt = 0; attempt < maxRetries; attempt++) {
            try {
                if (!this.page) await this.setupDriver();

                if (attempt > 0) {
                    console.log(`🔄 正在进行第 ${attempt + 1} 次尝试...`);
                }

                const [success, message] = await this.process();
                if (success) return [true, message];
                lastError = message;

                if (message.includes('打码失败')) break;
            } catch (e) {
                lastError = `异常：${e.message.slice(0, 80)}`;
                console.log(`❌ 第 ${attempt + 1} 次执行出错: ${e.message}`);
            }

            if (attempt < maxRetries - 1) {
                await sleep(5000 + Math.random() * 5000);
            }
        }

        this.screenshotPath = 'error-spider.png';
        if (this.page) {
            try {
                await this.page.screenshot({ path: this.screenshotPath });
            } catch (e) {
                console.log(`截图失败: ${e.message}`);
            }
        }
        return [false, `❌ 历经 ${maxRetries} 次尝试仍失败: ${lastError}`];
    }
}

// ===================== 主入口 =====================
async function main() {
    const spider = new JisuSpider();
    const [success, msg] = await spider.run();

    console.log(`汇总:\n ${msg}`);

    await sendTelegram(msg, spider.screenshotPath);

    if (success && spider.screenshotPath && fs.existsSync(spider.screenshotPath)) {
        try { fs.unlinkSync(spider.screenshotPath); } catch {}
    }

    console.log('\n✅ 抓取流程结束！');
}

main().catch(err => {
    console.error('发生错误:', err);
    process.exit(1);
});
