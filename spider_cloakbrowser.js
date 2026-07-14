const axios = require('axios');
const fs = require('fs');
const path = require('path');
const http = require('http');
const cheerio = require('cheerio');
const express = require('express');
const winston = require('winston');

// ===================== 配置 =====================
const TELEGRAM_BOT_TOKEN = process.env.BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.CHAT_ID || '';
const TARGET_ACTORS_ENV = process.env.TARGET_ACTORS || '';
const PAGE_URLS_ENV = process.env.PAGE_URLS || '';
const TURNSTILE_URL = process.env.TURNSTILE_URL || 'https://www.ji.com';
const ENCODED_URL = process.env.HOST_URL || 'aHR0cHM6Ly93d3cuamkuY29t';
const HOST_URL = Buffer.from(ENCODED_URL, 'base64').toString('utf-8');
const HTTP_PROXY = process.env.HTTP_PROXY || '';
const CUSTOM_UA = process.env.CUSTOM_UA || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36';



const lang = process.argv.includes('--lang=en') ? 'en' : 'zh';

const i18n = {
  zh: {
    apiError: 'API 错误: ',
    serverRunning: '服务已启动，监听地址: http://localhost:',
    locError: '定位报错: ',
    locSuccess: '[定位成功] 原始外框: ',
    pageClosed: '页面已关闭',
    clickPos: '[执行点击] 落脚点: ',
    foundCaptcha: '发现 CloudFlare 验证码',
    fastModeSuccess: 'FastMode: 已获取到 cf_clearance，提前结束！',
    solved: '验证码已解决',
    noCaptcha: '未检测到验证码'
  },
  en: {
    apiError: 'API Error: ',
    serverRunning: 'Server is running at http://localhost:',
    locError: 'Locator Error: ',
    locSuccess: '[Locator Success] Box: ',
    pageClosed: 'Page closed',
    clickPos: '[Click Execution] Position: ',
    foundCaptcha: 'Found CloudFlare challenge',
    fastModeSuccess: 'FastMode: cf_clearance obtained, ending early!',
    solved: 'Challenge solved',
    noCaptcha: 'No challenge detected'
  }
};

const t = i18n[lang];

const logger = winston.createLogger({
  level: 'debug',
  format: winston.format.combine(
    winston.format.colorize(),
    winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
    winston.format.printf(info => `[${info.timestamp}] ${info.level}: ${info.message}`)
  ),
  transports: [new winston.transports.Console()]
});

process.env.NO_PROXY = 'localhost,127.0.0.1';

let PROXY_CONFIG = null;

if (HTTP_PROXY) {
    try {
        const proxyUrl = new URL(HTTP_PROXY);
        PROXY_CONFIG = {
            server: `${proxyUrl.protocol}//${proxyUrl.hostname}:${proxyUrl.port}`,
            username: proxyUrl.username ? decodeURIComponent(proxyUrl.username) : undefined,
            password: proxyUrl.password ? decodeURIComponent(proxyUrl.password) : undefined
        };
        console.log(`[代理] 检测到配置: 服务器=${PROXY_CONFIG.server}, 认证=${PROXY_CONFIG.username ? '是' : '否'}`);
    } catch (e) {
        console.error('[代理] HTTP_PROXY 格式无效。期望格式: http://user:pass@host:port 或 http://host:port');
        process.exit(1);
    }
}
let is_proxy_enable = false;


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

// 辅助函数：检测代理是否可用
async function checkProxy() {
    if (!PROXY_CONFIG) return true;

    console.log('[代理] 正在验证代理连接...');
    try {
        const axiosConfig = {
            proxy: {
                protocol: 'http',
                host: new URL(PROXY_CONFIG.server).hostname,
                port: new URL(PROXY_CONFIG.server).port,
            },
            timeout: 10000
        };

        if (PROXY_CONFIG.username && PROXY_CONFIG.password) {
            axiosConfig.proxy.auth = {
                username: PROXY_CONFIG.username,
                password: PROXY_CONFIG.password
            };
        }

        await axios.get('https://www.google.com', axiosConfig);
        console.log('[代理] 连接成功！');
        return true;
    } catch (error) {
        console.error(`[代理] 连接失败: ${error.message}`);
        return false;
    }
}

const checkTurnstile = ({ page }) => {
  return new Promise(async (resolve, reject) => {
    var waitInterval = setTimeout(() => { clearInterval(waitInterval); resolve(false) }, 5000);
    try {
      let box = null;

      try {
        const wrapper = await page.$('div:has(> div > div > input[name="cf-turnstile-response"])');
        if (wrapper) {
          const rect = await wrapper.boundingBox();
          if (rect && rect.width > 250 && rect.height > 40) {
            box = rect;
          }
        }
      } catch (err) {
        logger.error(`${t.locError}${err.message}`);
      }

      if (box) {
        logger.debug(`${t.locSuccess}x=${box.x.toFixed(1)}, y=${box.y.toFixed(1)}, w=${box.width.toFixed(1)}, h=${box.height.toFixed(1)}`);

        await new Promise(r => setTimeout(r, Math.random() * 1000 + 1500));
        
        if (page.isClosed()) {
          logger.debug(t.pageClosed);
          clearInterval(waitInterval);
          return resolve(false);
        }

        let x = box.x + 20 + (Math.random() * 6 - 3);
        let y = box.y + 30 + (Math.random() * 6 - 3);
        
        logger.debug(`${t.clickPos}x=${x.toFixed(1)}, y=${y.toFixed(1)}`);

        await page.mouse.click(x, y);
      }
      
      clearInterval(waitInterval);
      resolve(true);
    } catch (err) {
      clearInterval(waitInterval);
      resolve(false);
    }
  });
}



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
        console.log('🛠️  - 驱动初始化 (cloakbrowser/puppeteer)');
        try {
            const { launch } = await import('cloakbrowser/puppeteer');

            const launchArgs = [];

            if (CUSTOM_UA) {
                launchArgs.push(`--user-agent=${CUSTOM_UA}`);
                const uaLower = CUSTOM_UA.toLowerCase();

                if (uaLower.includes("mac os") || uaLower.includes("macintosh")) {
                    launchArgs.push("--fingerprint-platform=macos");
                } else if (uaLower.includes("android")) {
                    launchArgs.push("--fingerprint-platform=android");
                } else if (uaLower.includes("iphone") || uaLower.includes("ipad")) {
                    launchArgs.push("--fingerprint-platform=ios");
                } else if (uaLower.includes("linux")) {
                    launchArgs.push("--fingerprint-platform=linux");
                } else {
                    launchArgs.push("--fingerprint-platform=windows");
                }

                const chromeMatch = CUSTOM_UA.match(/Chrome\/(\d+)/i);
                if (chromeMatch) {
                    launchArgs.push(`--fingerprint-brand-version=${chromeMatch[1]}`);
                    launchArgs.push(`--fingerprint-brand=Chrome`);
                }
            }

            const launchOptions = {
                headless: false,
                humanize: true,
                args: launchArgs
            };

            if (HTTP_PROXY&&is_proxy_enable) {
                launchOptions.proxy = HTTP_PROXY;
                
            }

            launchOptions.geoip = true;

            this.browser = await launch(launchOptions);
            console.log('- 驱动启动成功');
        } catch (e) {
            console.error(`- 驱动启动失败: ${e.message}`);
            throw e;
        }

        try {
            const ipRes = await fetch('https://api.ip.sb/ip');
            if (ipRes.ok) {
                const ip = (await ipRes.text()).trim();
                console.log(`📍 当前出口IP: ${ip}`);
            } else {
                console.warn(`⚠️ 获取出站 IP 失败: HTTP ${ipRes.status}`);
            }
        } catch (e) {
            console.warn(`⚠️ 获取出站 IP 出错: ${e.message}`);
        }

        const pages = await this.browser.pages();
        this.page = pages.length > 0 ? pages[0] : await this.browser.newPage();
        await this.page.setViewport({ width: 1280, height: 720 });
        //await this.page.evaluateOnNewDocument(INJECT_SCRIPT);
    }

    async buildSession() {
        const cookies = await this.page.cookies();
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

    async passTurnstile(url, maxAttempts = 2) {
        console.log(`🌐 访问 Turnstile URL: ${url}`);

        await this.page.goto(url, { waitUntil: 'domcontentloaded' });
        await sleep(3000 + Math.random() * 1000);

        try {
            await this.page.waitForSelector('.card-content-h1', { timeout: 5000 });
            console.log('页面已加载，无需打码');
            await this.buildSession();
            return true;
        } catch {}

        let isSuccess = false;
        let cdpClickResult = false;
        for (let attempt = 0; attempt < maxAttempts; attempt++) {

            const content = await this.page.content();

            if (content.includes("challenge-platform") === true){
                console.log('检测到码');
                try {
                    await checkTurnstile({ page: this.page });
                } catch (err) { }
                cdpClickResult=true
            }

            

            if (cdpClickResult) {
                console.log('   >> 登录 CDP 点击生效。正在等待最多 10秒 Cloudflare 成功标志...');
                for (let waitSec = 0; waitSec < 20; waitSec++) {
                    const frames = this.page.frames();

                    for (const f of frames) {
                        if (f.url().includes('cloudflare')) {
                            try {
                                const visible = await f.evaluate(() => {
                                    const el = document.querySelector('.mark-success, [aria-label="Success"]');
                                    return el ? el.offsetParent !== null : false;
                                }).catch(() => false);
                                if (visible) {
                                    isSuccess = true;
                                    break;
                                }
                            } catch (e) { }
                        }
                    }

                    try {
                        const token = await this.page.evaluate(() => {
                            const els = document.querySelectorAll(
                                'input[name="cf-turnstile-response"]'
                            );
                            for (const el of els) {
                                if (el.value && el.value.length > 2) return el.value;
                            }
                            return '';
                        });
                        if (token) {
                            isSuccess = true;
                            console.log('   >> token Turnstile 验证成功。');
                        }
                    } catch { }

            
                    const frames2 = this.page.frames();
                    for (const f of frames2) {
                        if (f.url().includes('cloudflare')) {
                            try {
                                if (await f.getByText('Success!', { exact: false }).isVisible({ timeout: 500 })) {
                                    isSuccess = true;
                                    console.log('   >> frames2 Turnstile 验证成功。');
                                    break;
                                }
                            } catch (e) { }
                        }
                    }
                    
                    

                    if (!isSuccess) {
                        try {
                            isSuccess = await this.page.evaluate(() => !!document.querySelector('.card-content-h1'));
                        } catch (e) { }
                    }
                    if (isSuccess) {
                        console.log('   >> 登录前 Turnstile 验证成功。');
                        break;
                    }
                    await sleep(1000);
                }
            } else {
                try {
                    isSuccess = await this.page.evaluate(() => !!document.querySelector('.card-content-h1'));
                    if (isSuccess) {
                        console.log('   >> 登录前 Turnstile 验证成功。');
                        break;
                    }
                } catch (e) { }
                console.log('   >> 登录前未检测到或未点击 Turnstile，继续操作...');
            }

            if (isSuccess) {
                break;
            }
        }

        if (!isSuccess) {
            console.log('打码可能失败了');
        } else {
            await this.buildSession();
        }
        return isSuccess;
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

(async () => {

    is_proxy_enable = await checkProxy();

    if (HTTP_PROXY&&is_proxy_enable) {
        try {
            const { ProxyAgent, setGlobalDispatcher } = require('undici');
            setGlobalDispatcher(new ProxyAgent(HTTP_PROXY));
            console.log(`✅ fetch 代理已启用: ${HTTP_PROXY}`);
        } catch (e) {
            console.warn(`⚠️ 无法加载 undici 代理模块，fetch 将直连: ${e.message}`);
        }
    }

    const spider = new JisuSpider();
    const [success, msg] = await spider.run();

    console.log(`汇总:\n ${msg}`);

    await sendTelegram(msg, spider.screenshotPath);

    if (success && spider.screenshotPath && fs.existsSync(spider.screenshotPath)) {
        try { fs.unlinkSync(spider.screenshotPath); } catch {}
    }

    console.log('\n✅ 抓取流程结束！');
    process.exit(0);
})();
