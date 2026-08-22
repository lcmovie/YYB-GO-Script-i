#!/usr/bin/env node
/**
 * Microsoft Rewards Standalone Script
 *
 * 一个可在 Node.js 环境下直接运行的微软奖励自动化脚本。
 * 基于对 Microsoft-Rewards-Script (https://github.com/TheNetsky/Microsoft-Rewards-Script)
 * 项目的分析，重新实现核心功能：浏览器登录、OAuth 令牌获取、仪表盘数据拉取、
 * 每日任务完成、活动积分领取、Bing 搜索积分等。
 *
 * ---------------------------------------------------------------------------
 * 依赖：
 *   - playwright   (浏览器自动化，用于登录微软账户)
 *   - axios        (HTTP 请求)
 *
 * 安装依赖：
 *   npm install playwright axios
 *   npx playwright install chromium
 *
 * 使用方法：
 *   1. 在脚本底部 CONFIG 区域填写账户信息，或创建同目录 accounts.json
 *   2. node microsoft-rewards-standalone.js
 *   3. 可选参数：--headless / --no-headless 覆盖无头模式
 *
 * 使用方法：
 *   1. 在脚本底部 CONFIG 区域填写账户信息，或创建同目录 accounts.json
 *   2. node microsoft-rewards-standalone.js
 *   3. 可选参数：--headless / --no-headless 覆盖无头模式
 *
 * 使用方法：
 *   1. 在脚本底部 CONFIG 区域填写账户信息，或创建同目录 accounts.json
 *   2. node microsoft-rewards-standalone.js
 *   3. 可选参数：--headless / --no-headless 覆盖无头模式
 *
 * 配置说明：
 *   见脚本底部 CONFIG 对象和 createDefaultConfig() 函数。
 *
 * 免责声明：
 *   本脚本仅供学习和研究用途。使用本脚本可能违反微软服务条款，
 *   由此产生的一切后果由使用者自行承担。
 * ---------------------------------------------------------------------------
 */

'use strict'

const fs = require('fs')
const path = require('path')
const os = require('os')
const crypto = require('crypto')
const { URL, URLSearchParams } = require('url')

// ============================================================================
// 第三方依赖（延迟加载，便于在缺失时给出友好提示）
// ============================================================================
let axios = null
let axiosRetry = null
let playwright = null

function loadDependencies() {
    try {
        axios = require('axios')
    } catch {
        fatal('缺少依赖 "axios"，请运行: npm install axios')
    }
    try {
        axiosRetry = require('axios-retry')
    } catch {
        // axios-retry 可选，缺失时使用内置重试
        axiosRetry = null
    }
    try {
        playwright = require('playwright')
    } catch {
        try {
            // 尝试 patchright 作为备选
            playwright = require('patchright')
        } catch {
            fatal('缺少依赖 "playwright"，请运行: npm install playwright && npx playwright install chromium')
        }
    }
}

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 移动端机型池（来自 Script-4 UserAgent.ts MOBILE_MODELS）
 * 每次随机选取一款作为 sec-ch-ua-model 的值，使指纹更真实
 */
const MOBILE_MODELS = [
    'SM-S948B', 'SM-S947B', 'SM-S942B', 'SM-S938B', 'SM-S937B', 'SM-S936B', 'SM-S931B',
    'SM-S928B', 'SM-S926B', 'SM-S921B', 'SM-S918B', 'SM-S916B', 'SM-S911B',
    'SM-F966B', 'SM-F956B', 'SM-F946B', 'SM-F741B', 'SM-F731B',
    'SM-A566B', 'SM-A556B', 'SM-A546B', 'SM-A356B', 'SM-A346B', 'SM-A266B', 'SM-A256B', 'SM-A166B', 'SM-A156B',
    'Pixel 10 Pro Fold', 'Pixel 10 Pro XL', 'Pixel 10 Pro', 'Pixel 10', 'Pixel 10a',
    'Pixel 9 Pro Fold', 'Pixel 9 Pro XL', 'Pixel 9 Pro', 'Pixel 9', 'Pixel 9a',
    'Pixel 8 Pro', 'Pixel 8', 'Pixel 8a', 'Pixel 7 Pro', 'Pixel 7', 'Pixel 7a', 'Pixel Fold',
    'CPH2653', 'CPH2649', 'CPH2655', 'CPH2581', 'CPH2573', 'CPH2449', 'CPH2415',
    'A059', 'A059P', 'A142', 'A065',
    'motorola edge 50 pro', 'motorola edge 50 neo', 'motorola edge 40 pro', 'moto g85 5G', 'moto g84 5G', 'moto g54 5G'
]

/**
 * 从机型池中随机选取一款机型
 * @returns {string} 机型标识符
 */
function pickMobileModel() {
    return MOBILE_MODELS[Math.floor(Math.random() * MOBILE_MODELS.length)] || 'Pixel 8'
}

/**
 * 浏览器指纹头常量
 * 必须与浏览器 context 的 User-Agent 版本保持一致
 * 这些头信息对于 rewards.bing.com API 返回完整的促销数据至关重要
 *
 * 关键修复（2026-06-29）：
 * 1. Accept-Language 必须为英文（en-US），否则 API 返回 ZHstar 前缀活动（不获得积分），
 *    而非 ENstar 前缀活动（获得积分）。EXE 使用英文 Accept-Language，因此获得 ENstar 活动。
 * 2. User-Agent 版本必须与 EXE 一致（Chrome/150 EdgA/149），旧版本（Chrome/129）会导致 API
 *    返回精简数据，缺失 WW_Rewards_locked_level2_* 系列活动。
 * 3. sec-ch-ua 格式必须与 EXE 的 UserAgent.ts 中 updateFingerprintUserAgent 方法一致：
 *    品牌 "Not=A?Brand"、版本 "99"、顺序 Edge→NotBrand→Chromium。
 *
 * Script-4 整合（2026-07-07）：
 * 4. 补全 6 个 sec-ch-ua-* 客户端提示头（与 Script-4 UserAgent.ts 一致）：
 *    sec-ch-ua-platform-version、sec-ch-ua-arch、sec-ch-ua-bitness、sec-ch-ua-model
 *    缺失这些头会被服务端 UA-CH 一致性检测识破，导致积分任务返回不完整数据。
 * 5. sec-ch-ua-model 在移动端为真实机型（从 MOBILE_MODELS 随机选取），桌面端为空。
 */
const FINGERPRINT_HEADERS_MOBILE = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36 EdgA/149.0.4022.96',
    'sec-ch-ua': '"Microsoft Edge";v="149", "Not=A?Brand";v="99", "Chromium";v="150"',
    'sec-ch-ua-full-version-list': '"Microsoft Edge";v="149.0.4022.96", "Not=A?Brand";v="99.0.0.0", "Chromium";v="150.0.0.0"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-ch-ua-platform-version': '"13.0.0"',
    'sec-ch-ua-arch': '""',
    'sec-ch-ua-bitness': '""',
    'sec-ch-ua-model': '"Pixel 8"',
    'Upgrade-Insecure-Requests': '1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1'
}

const FINGERPRINT_HEADERS_DESKTOP = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/149.0.4022.96',
    'sec-ch-ua': '"Microsoft Edge";v="149", "Not=A?Brand";v="99", "Chromium";v="150"',
    'sec-ch-ua-full-version-list': '"Microsoft Edge";v="149.0.4022.96", "Not=A?Brand";v="99.0.0.0", "Chromium";v="150.0.0.0"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"15.0.0"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-model': '""',
    'Upgrade-Insecure-Requests': '1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1'
}

/**
 * 动态生成移动端指纹头（包含随机机型）
 * 每次调用会随机选取一个机型填入 sec-ch-ua-model
 * @returns {object} 包含完整指纹头的对象（深拷贝，可安全修改）
 */
function generateMobileFingerprintHeaders() {
    const headers = { ...FINGERPRINT_HEADERS_MOBILE }
    headers['sec-ch-ua-model'] = `"${pickMobileModel()}"`
    return headers
}

// 公共 Cookie 域名列表（用于 buildCookieHeader，多处复用）
const COMMON_COOKIE_DOMAINS = ['bing.com', 'live.com', 'microsoftonline.com']

// DAPI App API 请求中使用的固定 User-Agent（用于 App 促销、Read to Earn 等）
const DAPI_USER_AGENT = 'Bing/32.5.431027001 (com.microsoft.bing; build:431027001; iOS 17.6.1) Alamofire/5.10.2'

// 每日签到专用 User-Agent（Script-4 升级为 iPad Safari + BingSapphire 33.x）
// 来自 Script-4 constants/userAgents.ts 和 activities/app/DailyCheckIn.ts
const DAILY_CHECKIN_USER_AGENT = 'Mozilla/5.0 (iPad; CPU iPad OS 26_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.5 Mobile/15E148 Safari/605.1.15 BingSapphire/33.4.440603001'

// 每日签到专用 AppId（Script-4 升级版本号）
const DAILY_CHECKIN_APP_ID = 'SAIOS/33.4.440603001'

// URL 常量（来自 Script-4 constants/urls.ts，集中管理 API 端点）
const URLS = {
    rewards: {
        origin: 'https://rewards.bing.com',
        earn: 'https://rewards.bing.com/earn',
        earnStreaks: 'https://rewards.bing.com/earn?section=streaks',
        dashboard: 'https://rewards.bing.com/dashboard',
        userInfoApi: 'https://rewards.bing.com/api/getuserinfo',
        quest: (parentId) => `https://rewards.bing.com/earn/quest/${parentId}`,
        path: (p) => `https://rewards.bing.com${p}`
    },
    platform: {
        me: (channel) => `https://prod.rewardsplatform.microsoft.com/dapi/me?channel=${channel}&options=613`,
        meSAIOS: (channel) => `https://prod.rewardsplatform.microsoft.com/dapi/me?channel=${channel}&options=612`,
        activities: 'https://prod.rewardsplatform.microsoft.com/dapi/me/activities'
    },
    bing: {
        origin: 'https://cn.bing.com',
        search: (query, cvid) => `https://cn.bing.com/search?q=${encodeURIComponent(query)}&PC=U531&FORM=ANNTA1&cvid=${cvid}`
    }
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
}

function randomNumber(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min
}

function randomDelay(min, max) {
    return randomNumber(min, max)
}

function getFormattedDate(timestamp = Date.now()) {
    // 转换为 UTC+8（中国标准时间）
    const d = new Date(timestamp + 8 * 60 * 60 * 1000)
    const month = String(d.getUTCMonth() + 1).padStart(2, '0')
    const day = String(d.getUTCDate()).padStart(2, '0')
    const year = d.getUTCFullYear()
    return `${month}/${day}/${year}`
}

/**
 * 将日期格式化为 UTC+8（中国标准时间）的 "YYYY-MM-DD HH:mm:ss" 字符串
 */
function _formatCSTDate(date) {
    const d = new Date(date.getTime() + 8 * 60 * 60 * 1000)
    const year = d.getUTCFullYear()
    const month = String(d.getUTCMonth() + 1).padStart(2, '0')
    const day = String(d.getUTCDate()).padStart(2, '0')
    const hours = String(d.getUTCHours()).padStart(2, '0')
    const minutes = String(d.getUTCMinutes()).padStart(2, '0')
    const seconds = String(d.getUTCSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

function getEmailUsername(email) {
    return (email || '').split('@')[0] || 'Unknown'
}

function shuffleArray(arr) {
    const a = [...arr]
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[a[i], a[j]] = [a[j], a[i]]
    }
    return a
}

function chunkArray(arr, numChunks) {
    const chunkSize = Math.ceil(arr.length / numChunks) || 1
    const chunks = []
    for (let i = 0; i < arr.length; i += chunkSize) {
        chunks.push(arr.slice(i, i + chunkSize))
    }
    return chunks
}

// ============================================================================
// 日志系统
// ============================================================================
const COLORS = {
    reset: '\x1b[0m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    gray: '\x1b[90m'
}

class Logger {
    constructor(options = {}) {
        this.level = options.level || 'info'
        this.enableColors = options.colors !== false && process.stdout.isTTY
        this.logFile = options.logFile || null
        this.account = options.account || 'main'
        this.levels = { debug: 0, info: 1, warn: 2, error: 3 }
    }

    _format(level, tag, message, color) {
        const ts = _formatCSTDate(new Date())
        const prefix = `[${ts}] [${level.toUpperCase()}] [${this.account}] [${tag}]`
        const text = `${prefix} ${message}`
        if (this.enableColors && color) {
            return `${color}${text}${COLORS.reset}`
        }
        return text
    }

    _shouldLog(level) {
        return (this.levels[level] || 0) >= (this.levels[this.level] || 0)
    }

    _write(level, tag, message, color) {
        if (!this._shouldLog(level)) return
        const formatted = this._format(level, tag, message, color)
        console.log(formatted)
        if (this.logFile) {
            try {
                fs.appendFileSync(this.logFile, `${this._format(level, tag, message)}\n`)
            } catch {
                // 忽略文件写入错误
            }
        }
    }

    debug(tag, message) {
        this._write('debug', tag, message, COLORS.gray)
    }

    info(tag, message, color) {
        this._write('info', tag, message, color || COLORS.cyan)
    }

    warn(tag, message) {
        this._write('warn', tag, message, COLORS.yellow)
    }

    error(tag, message) {
        this._write('error', tag, message, COLORS.red)
    }

    success(tag, message) {
        this._write('info', tag, message, COLORS.green)
    }
}

// ============================================================================
// 配置管理
// ============================================================================
function createDefaultConfig() {
    return {
        // 基础设置
        baseURL: 'https://rewards.bing.com',
        sessionPath: 'sessions',
        headless: true,
        globalTimeout: 30000,
        debugLogs: false,

        // 浏览器设置
        browser: {
            // Chromium 可执行文件路径（留空则自动检测）
            // 如果自动检测失败，请手动指定，例如：
            //   Linux: '/root/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'
            //   Windows: 'C:\\Users\\<user>\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe'
            executablePath: '/usr/bin/chromium-browser',
            args: [
                '--no-sandbox',
                '--mute-audio',
                '--disable-setuid-sandbox',
                '--ignore-certificate-errors',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-web-authentication-ui',
                '--disable-blink-features=Attestation',
                '--disable-features=WebAuthentication,PasswordManager,Passkeys'
            ]
        },

        // 任务开关（Script-4 整合：新增 doActivateSearchPerk/doVisualSearch/doBonusSearches/doEnsureStreakProtection/autoClaimPunchcardRewards/skipNonPointTasks）
        workers: {
            doDailySet: true,
            doSpecialPromotions: true,        // 旧名保留（内部转发到 doActivateSearchPerk）
            doActivateSearchPerk: true,       // Script-4：激活搜索积分倍数特权
            doMorePromotions: true,
            doClaimBonusPoints: true,
            doOtherPromotions: true,
            doAppPromotions: true,
            doDailyCheckIn: true,
            doReadToEarn: true,
            doPunchCards: true,
            doVisualSearch: false,            // [已关闭] 视觉搜索（桌面端）—— kblob API 在中国地区因 TLS 指纹检测返回 400
            // 关闭原因：Script-3 使用 axios 作为 HTTP 客户端，无法模拟 Chrome 浏览器 TLS 指纹；
            //          Script-4 使用 Impit 库（new Impit({ browser: 'chrome' })）可成功通过 kblob API 检测。
            //          经 5 轮修复尝试（page.request/fetch/FormData/XHR/浏览器文件上传）均未能解决，
            //          kblob API 持续返回 400 空响应。待 Script-3 引入 Impit 或等效 TLS 模拟方案后再启用。
            doBonusSearches: true,            // Script-4：额外搜索 farming（maxBonusSearches>0 时启用）
            doEnsureStreakProtection: true,   // Script-4：连续登录保护（Server Action）
            autoClaimPunchcardRewards: true,  // Script-4：自动领取已完成 Punch Card 父任务奖励
            skipNonPointTasks: false,         // Script-4：跳过 0 积分子任务
            doMobileSearch: true,
            doDesktopSearch: true
        },

        // 搜索设置（Script-4 整合：新增 maxBonusSearches）
        search: {
            searchDelayMin: 30000,
            searchDelayMax: 60000,
            maxSearches: 100,
            stagnantLimit: 10,
            maxBonusSearches: 110             // Script-4：额外搜索 farming 最大次数（110=Script-4 默认值）
        },

        // Script-4 整合：连续登录保护 action id（手动指定，留空则尝试动态发现）
        streakProtectionActionId: '',

        // 日志设置
        logFile: null
    }
}

function loadConfigFile(filePath) {
    try {
        if (fs.existsSync(filePath)) {
            const raw = fs.readFileSync(filePath, 'utf-8')
            return JSON.parse(raw)
        }
    } catch (error) {
        console.error(`加载配置文件失败 ${filePath}: ${error.message}`)
    }
    return null
}

function loadAccountsFile(filePath) {
    try {
        if (fs.existsSync(filePath)) {
            const raw = fs.readFileSync(filePath, 'utf-8')
            const data = JSON.parse(raw)
            if (Array.isArray(data)) return data
            if (data.accounts && Array.isArray(data.accounts)) return data.accounts
        }
    } catch (error) {
        console.error(`加载账户文件失败 ${filePath}: ${error.message}`)
    }
    return null
}

// ============================================================================
// HTTP 客户端（带重试和代理）
// ============================================================================
class HttpClient {
    constructor(proxyConfig = null, logger) {
        this.logger = logger
        this.instance = axios.create({
            timeout: 60000,
            maxRedirects: 10
        })

        // 配置代理
        if (proxyConfig && proxyConfig.url) {
            try {
                const agent = this._createProxyAgent(proxyConfig)
                if (agent) {
                    this.instance.defaults.httpAgent = agent
                    this.instance.defaults.httpsAgent = agent
                    this.instance.defaults.proxy = false
                }
            } catch (error) {
                logger.warn('HTTP', `代理配置失败: ${error.message}`)
            }
        }

        // 配置重试
        if (axiosRetry) {
            axiosRetry(this.instance, {
                retries: 5,
                retryDelay: axiosRetry.exponentialDelay,
                shouldResetTimeout: true,
                retryCondition: error => {
                    if (axiosRetry.isNetworkError(error)) return true
                    if (!error.response) return true
                    const status = error.response.status
                    return status === 429 || (status >= 500 && status <= 599)
                }
            })
        }

        // 拦截器：记录请求
        this.instance.interceptors.request.use(
            config => {
                logger.debug('HTTP-REQ', `${config.method?.toUpperCase() || 'GET'} ${this._safeUrl(config.url)}`)
                return config
            },
            error => Promise.reject(error)
        )

        this.instance.interceptors.response.use(
            response => {
                logger.debug('HTTP-RES', `${response.status} ${this._safeUrl(response.config?.url)}`)
                return response
            },
            error => {
                if (error.response) {
                    logger.debug('HTTP-ERR', `${error.response.status} ${this._safeUrl(error.config?.url)}`)
                }
                return Promise.reject(error)
            }
        )
    }

    _safeUrl(url) {
        if (!url) return '?'
        try {
            const u = new URL(url)
            return `${u.hostname}${u.pathname}`
        } catch {
            return String(url).substring(0, 80)
        }
    }

    _createProxyAgent(proxyConfig) {
        const { url: baseUrl, port, username, password } = proxyConfig
        let urlObj
        try {
            urlObj = new URL(baseUrl)
        } catch {
            urlObj = new URL(`http://${baseUrl}`)
        }

        const protocol = urlObj.protocol.toLowerCase()
        if (username && password) {
            urlObj.username = encodeURIComponent(username)
            urlObj.password = encodeURIComponent(password)
        }
        if (port) urlObj.port = String(port)
        const proxyUrl = urlObj.toString()

        try {
            switch (protocol) {
                case 'http:': {
                    const { HttpProxyAgent } = require('http-proxy-agent')
                    return new HttpProxyAgent(proxyUrl)
                }
                case 'https:': {
                    const { HttpsProxyAgent } = require('https-proxy-agent')
                    return new HttpsProxyAgent(proxyUrl)
                }
                case 'socks4:':
                case 'socks5:': {
                    const { SocksProxyAgent } = require('socks-proxy-agent')
                    return new SocksProxyAgent(proxyUrl)
                }
                default:
                    this.logger.warn('HTTP', `不支持的代理协议: ${protocol}`)
                    return null
            }
        } catch (error) {
            this.logger.warn('HTTP', `创建代理 agent 失败: ${error.message}`)
            return null
        }
    }

    async request(config) {
        return this.instance.request(config)
    }
}

// ============================================================================
// 会话管理（Cookie 持久化）
// ============================================================================
class SessionManager {
    constructor(sessionPath, logger) {
        this.sessionPath = sessionPath
        this.logger = logger
    }

    _getSessionDir(email) {
        return path.join(this.sessionPath, email)
    }

    _getCookieFile(email, isMobile) {
        return path.join(this._getSessionDir(email), isMobile ? 'session_mobile.json' : 'session_desktop.json')
    }

    async loadCookies(email, isMobile) {
        try {
            const file = this._getCookieFile(email, isMobile)
            if (fs.existsSync(file)) {
                const data = await fs.promises.readFile(file, 'utf-8')
                return JSON.parse(data)
            }
        } catch (error) {
            this.logger.debug('SESSION', `加载 cookies 失败: ${error.message}`)
        }
        return []
    }

    async saveCookies(email, isMobile, cookies) {
        try {
            const dir = this._getSessionDir(email)
            if (!fs.existsSync(dir)) {
                await fs.promises.mkdir(dir, { recursive: true })
            }
            const file = this._getCookieFile(email, isMobile)
            await fs.promises.writeFile(file, JSON.stringify(cookies, null, 2))
            this.logger.debug('SESSION', `已保存 ${cookies.length} 个 cookies 到 ${file}`)
        } catch (error) {
            this.logger.warn('SESSION', `保存 cookies 失败: ${error.message}`)
        }
    }

    buildCookieHeader(cookies, allowedDomains) {
        const filtered = cookies.filter(c => {
            if (!allowedDomains || allowedDomains.length === 0) return true
            return (
                typeof c.domain === 'string' &&
                allowedDomains.some(d => c.domain.toLowerCase().endsWith(d.toLowerCase()))
            )
        })
        const unique = [...new Map(filtered.map(c => [c.name, c])).values()]
        return unique.map(c => `${c.name}=${c.value}`).join('; ')
    }
}

// ============================================================================
// React Server Components 解析器（移植自 Script-4 ReactFunc.ts）
// 从 /earn 和 /quest 页面 HTML 中提取实时 hash、offers、quest children 等
// ============================================================================
class ReactParser {
    constructor(logger) {
        this.logger = logger
    }

    // 拼接 __next_f flight chunks
    concatFlightChunks(html) {
        try {
            const pushRe = /self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)/g
            let combined = ''
            let count = 0
            for (const match of html.matchAll(pushRe)) {
                try {
                    combined += JSON.parse(`"${match[1]}"`)
                    count++
                } catch (err) {
                    this.logger?.debug('REACT-PARSE', `跳过无法解码的 flight chunk: ${err.message}`)
                }
            }
            if (count === 0) {
                this.logger?.warn('REACT-PARSE', '未找到 __next_f flight chunks - 页面可能不是 RSC 渲染或标记已变更')
            }
            return combined
        } catch (error) {
            this.logger?.error('REACT-PARSE', `拼接 flight chunks 失败: ${error.message}`)
            return ''
        }
    }

    // 通过锚点字符串定位并提取 JSON 对象
    extractObjects(combined, anchor) {
        const out = []
        let i = 0
        let failures = 0
        while ((i = combined.indexOf(anchor, i)) !== -1) {
            const start = combined.lastIndexOf('{', i)
            if (start === -1) { i += anchor.length; continue }
            let depth = 0
            let end = -1
            let inStr = false
            let esc = false
            for (let j = start; j < combined.length; j++) {
                const c = combined[j]
                if (esc) { esc = false; continue }
                if (c === '\\') { esc = true; continue }
                if (c === '"') { inStr = !inStr; continue }
                if (inStr) continue
                if (c === '{') depth++
                else if (c === '}') {
                    depth--
                    if (depth === 0) { end = j; break }
                }
            }
            if (end === -1) break
            const raw = combined.slice(start, end + 1)
            i = end
            try {
                out.push(JSON.parse(raw.replace(/"\$undefined"/g, 'null')))
            } catch {
                failures++
            }
        }
        if (failures > 0) {
            this.logger?.debug('REACT-PARSE', `extractObjects("${anchor}") 有 ${failures} 个无法解析的匹配`)
        }
        return out
    }

    // 解析所有 offers（从 /earn 页面）
    parseOffers(combined) {
        try {
            const seen = new Set()
            const today = this._todayStamp()
            const offers = []
            for (const obj of this.extractObjects(combined, '"offerId"')) {
                const offerId = obj.offerId
                if (!offerId || seen.has(offerId)) continue
                seen.add(offerId)
                const hash = obj.hash ?? null
                const isCompleted = (obj.isCompleted ?? obj.complete) === true
                const isLocked = obj.isLocked === true
                const date = this._normaliseDate(obj.date)
                const reportable = !!hash && !isCompleted && !isLocked && (date === null || date <= today)
                offers.push({
                    offerId,
                    hash,
                    title: obj.title ?? '',
                    description: obj.description ?? '',
                    points: obj.points ?? obj.pointProgressMax ?? 0,
                    promotionSubtype: obj.promotionSubtype ?? null,
                    destination: obj.destination ?? obj.destinationUrl ?? '',
                    isCompleted,
                    isPromotional: obj.isPromotional === true,
                    isLocked,
                    unlockCriteria: obj.unlockCriteria ?? null,
                    date,
                    activityType: null,
                    reportable
                })
            }
            return offers
        } catch (error) {
            this.logger?.error('REACT-PARSE', `解析 offers 失败: ${error.message}`)
            return []
        }
    }

    // 解析 streak protection 状态
    parseStreakProtection(combined) {
        try {
            const carriers = this.extractObjects(combined, '"isProtectionOn"').filter(o => 'isProtectionOn' in o)
            if (!carriers.length) return null
            const withDays = carriers.find(o => 'remainingDays' in o && typeof o.remainingDays === 'number')
            const withFlag = carriers.find(o => typeof o.isProtectionOn === 'boolean')
            return {
                isProtectionOn: (withDays?.isProtectionOn ?? withFlag?.isProtectionOn) === true,
                remainingDays: withDays ? withDays.remainingDays : null
            }
        } catch (error) {
            this.logger?.error('REACT-PARSE', `解析 streak protection 失败: ${error.message}`)
            return null
        }
    }

    // Script-4 ReactFunc.parseStreaks：解析 visual search 等连续活动状态
    parseStreaks(combined) {
        try {
            const streaks = this.extractObjects(combined, '"dailyPoints"')
                .filter(o => typeof o.partner === 'string' && Array.isArray(o.dailyPoints))
                .map(o => ({
                    partner: o.partner,
                    activitiesCompleted: o.activitiesCompleted ?? 0,
                    activitiesTotal: o.activitiesTotal ?? 0,
                    completedDays: o.completedDays ?? 0,
                    currentDay: o.currentDay ?? 0,
                    totalDays: o.totalDays ?? 0,
                    isCurrentDayCompleted: o.isCurrentDayCompleted === true,
                    isEnabled: o.isEnabled === true,
                    dailyPoints: o.dailyPoints
                }))
            const byPartner = new Map(streaks.map(s => [s.partner, s]))
            return [...byPartner.values()]
        } catch (error) {
            this.logger?.error('REACT-PARSE', `解析 streaks 失败: ${error.message}`)
            return []
        }
    }

    // 完整页面快照（offers + streaks + streak protection）
    snapshotPage(html) {
        const combined = this.concatFlightChunks(html)
        const offers = this.parseOffers(combined)
        const streaks = this.parseStreaks(combined)
        const streakProtection = this.parseStreakProtection(combined)
        this.logger?.info('REACT-PARSE', `快照完成 | offers=${offers.length} | reportable=${offers.filter(o => o.reportable).length} | streaks=${streaks.length} | protection=${streakProtection ? `on=${streakProtection.isProtectionOn}` : 'n/a'}`)
        return { offers, reportable: offers.filter(o => o.reportable), streaks, streakProtection }
    }

    // 从 /earn 或 /dashboard HTML 解析 parent quest 列表
    snapshotQuestList(...htmls) {
        try {
            const combined = htmls.map(h => this.concatFlightChunks(h)).join('')
            const anchors = []
            for (const match of combined.matchAll(/\/earn\/quest\/([A-Za-z0-9_]+)/g)) {
                anchors.push({ id: match[1], at: match.index ?? 0 })
            }
            for (const match of combined.matchAll(/"id":"quest_([A-Za-z0-9_]+)"/g)) {
                anchors.push({ id: match[1], at: match.index ?? 0 })
            }
            for (const match of combined.matchAll(/[A-Za-z0-9_]*pcparent[A-Za-z0-9_]*/gi)) {
                anchors.push({ id: match[0], at: match.index ?? 0 })
            }
            anchors.sort((a, b) => a.at - b.at)

            const byId = new Map()
            for (let k = 0; k < anchors.length; k++) {
                const { id, at } = anchors[k]
                if (!this._isParentQuestId(id)) continue
                const next = anchors[k + 1]?.at ?? combined.length
                const region = combined.slice(at, Math.min(next, at + 3000))
                const title = region.match(/"alt":"((?:[^"\\]|\\.)*)"/)?.[1] ?? region.match(/"title":"((?:[^"\\]|\\.)*)"/)?.[1] ?? ''
                const pointsMatch = region.match(/\["\+","([\d,]+)"\]/)
                const points = pointsMatch ? Number(pointsMatch[1].replace(/,/g, '')) : 0
                const taskM = region.match(/(\d+)\s*\/\s*(\d+)\s*tasks/)
                const complete = !!taskM && Number(taskM[1]) >= Number(taskM[2]) && Number(taskM[2]) > 0
                const prev = byId.get(id)
                byId.set(id, {
                    offerId: id,
                    title: prev?.title || title,
                    pointProgressMax: prev?.pointProgressMax || points,
                    complete: prev?.complete || complete
                })
            }
            const out = [...byId.values()]
            this.logger?.info('REACT-PARSE', `Quest 列表 | parents=${out.length} | incomplete=${out.filter(q => !q.complete).length}`)
            return out
        } catch (error) {
            this.logger?.error('REACT-PARSE', `解析 quest 列表失败: ${error.message}`)
            return []
        }
    }

    // 从 /earn/quest/{id} 页面解析子任务（pcchildren）
    snapshotQuestPage(html) {
        try {
            const combined = this.concatFlightChunks(html)
            const out = []
            const seen = new Set()
            for (const obj of this.extractObjects(combined, '"offerId"')) {
                const offerId = obj.offerId
                if (!offerId || !offerId.includes('pcchild') || seen.has(offerId)) continue
                seen.add(offerId)
                const hash = obj.hash ?? null
                const isCompleted = (obj.isCompleted ?? obj.complete) === true
                const isLocked = obj.isLocked === true
                const isDisabled = obj.isDisabled === true
                const reportable = !!hash && !isCompleted && !isLocked && !isDisabled
                out.push({
                    offerId,
                    hash,
                    points: obj.points ?? obj.pointProgressMax ?? 0,
                    isCompleted,
                    isLocked,
                    isDisabled,
                    reportable
                })
            }
            this.logger?.info('REACT-PARSE', `Quest 页快照 | children=${out.length} | reportable=${out.filter(c => c.reportable).length}`)
            return out
        } catch (error) {
            this.logger?.error('REACT-PARSE', `解析 quest 页失败: ${error.message}`)
            return []
        }
    }

    // 生成 /earn 页面的 React router state tree
    routerStateTree(segment) {
        const tree = ['', { children: ['(nav)', { children: [segment, { children: ['__PAGE__', {}, null, null, 0] }, null, null, 0] }, null, null, 0] }, null, null, 16]
        return encodeURIComponent(JSON.stringify(tree))
    }

    // 生成 /earn/quest/{id} 页面的 React router state tree
    questRouterStateTree(questId) {
        const tree = ['', { children: ['(nav)', { children: ['earn', { children: ['quest', { children: [['questId', questId, 'd', null], { children: ['__PAGE__', {}, null, null, 0] }, null, null, 0] }, null, null, 0] }, null, null, 0] }, null, null, 0] }, null, null, 16]
        return encodeURIComponent(JSON.stringify(tree))
    }

    // 从 JS chunk 提取 Server Action id（createServerReference）
    extractActionIds(jsText) {
        const byName = {}
        const all = new Set()
        const HEX = '[a-f0-9]{40,64}'
        const KNOWN_NON_NAMES = new Set(['callServer', 'findSourceMapURL', 'encodeFormAction'])
        try {
            const callRegex = new RegExp(`createServerReference\\s*\\)?\\s*\\(\\s*"(${HEX})"([\\s\\S]{0,400}?)\\)`, 'g')
            const strLitRe = /"([A-Za-z_$][\w$]*)"/g
            for (const m of jsText.matchAll(callRegex)) {
                const id = m[1]
                const argsBlock = m[2] ?? ''
                all.add(id)
                const candidates = [...argsBlock.matchAll(strLitRe)].map(x => x[1]).filter(n => !KNOWN_NON_NAMES.has(n))
                if (candidates.length) byName[candidates[candidates.length - 1]] = id
            }
            const bareRegex = new RegExp(`createServerReference\\s*\\)?\\s*\\(\\s*"(${HEX})"`, 'g')
            for (const m of jsText.matchAll(bareRegex)) all.add(m[1])
            const actionIdRe = new RegExp(`\\$ACTION_ID_(${HEX})`, 'g')
            for (const m of jsText.matchAll(actionIdRe)) all.add(m[1])
        } catch (error) {
            this.logger?.error('REACT-PARSE', `提取 action ids 失败: ${error.message}`)
        }
        return { byName, all: [...all] }
    }

    // 提取 buildId
    buildId(html) {
        const combined = this.concatFlightChunks(html)
        return combined.match(/"buildId":"([A-Za-z0-9_-]{21})"/)?.[1] ??
            combined.match(/"b":"([A-Za-z0-9_-]{21})"/)?.[1] ??
            html.match(/\/_next\/static\/([A-Za-z0-9_-]{21})\//)?.[1] ?? null
    }

    _isParentQuestId(offerId) {
        const id = offerId.toLowerCase()
        if (id.includes('pcchild')) return false
        return id.includes('pcparent') || id.includes('punchcard')
    }

    _todayStamp() {
        const d = new Date()
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }

    _normaliseDate(rawDate) {
        if (!rawDate) return null
        const m = rawDate.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
        if (!m) return null
        return `${m[3]}-${m[1]}-${m[2]}`
    }
}

// ============================================================================
// 浏览器管理
// ============================================================================
class BrowserManager {
    constructor(config, logger) {
        this.config = config
        this.logger = logger
    }

    async launchBrowser(account, isMobile = true) {
        const proxyConfig = account.proxy && account.proxy.url ? {
            server: this._formatProxyServer(account.proxy),
            ...(account.proxy.username && account.proxy.password ? {
                username: account.proxy.username,
                password: account.proxy.password
            } : {})
        } : undefined

        const launchOptions = {
            headless: this.config.headless,
            args: [...this.config.browser.args]
        }
        if (proxyConfig) launchOptions.proxy = proxyConfig

        // 显式指定 Chromium 可执行文件路径（解决 ENOENT 问题）
        if (this.config.browser.executablePath) {
            launchOptions.executablePath = this.config.browser.executablePath
            this.logger.info('BROWSER', `使用指定的 Chromium 路径: ${launchOptions.executablePath}`)
        } else {
            // 自动检测已安装的 Chromium
            const detectedPath = this._detectChromiumPath()
            if (detectedPath) {
                launchOptions.executablePath = detectedPath
                this.logger.info('BROWSER', `检测到 Chromium 路径: ${detectedPath}`)
            } else {
                this.logger.warn('BROWSER', '未检测到 Chromium，将使用 Playwright 默认路径')
                this._logPlaywrightCacheInfo()
            }
        }

        let browser
        try {
            browser = await playwright.chromium.launch(launchOptions)
        } catch (error) {
            this.logger.error('BROWSER', `浏览器启动失败: ${error.message}`)
            this.logger.error('BROWSER', `尝试的路径: ${launchOptions.executablePath || '(Playwright 默认)'}`)
            this._logPlaywrightCacheInfo()
            // 如果是 ENOENT 错误，检查动态链接库（Linux 常见问题）
            if (error.message.includes('ENOENT') && launchOptions.executablePath && process.platform !== 'win32') {
                this._checkSharedLibraries(launchOptions.executablePath)
            }
            throw error
        }

        const contextOptions = {
            ignoreHTTPSErrors: true,
            permissions: [],
            // 关键：locale 必须为 en-US，确保浏览器访问 rewards.bing.com 时设置的语言 cookie 为英文，
            // 否则后续 API 调用会返回 ZHstar 前缀活动（不获得积分）而非 ENstar 前缀活动（获得积分）
            locale: 'en-US'
        }

        // 移动端模拟
        // 注意：User-Agent 版本必须与 API 请求中的指纹头（sec-ch-ua 等）保持一致
        // 否则 rewards.bing.com API 会返回不完整的促销数据（例如缺失 Evergreen 类型的 More Promotions 活动）
        if (isMobile) {
            contextOptions.userAgent =
                'Mozilla/5.0 (Linux; Android 13; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36 EdgA/149.0.4022.96'
            contextOptions.viewport = { width: 412, height: 915 }
            contextOptions.deviceScaleFactor = 2.625
            contextOptions.isMobile = true
            contextOptions.hasTouch = true
        } else {
            contextOptions.userAgent =
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/149.0.4022.96'
            contextOptions.viewport = { width: 1920, height: 1080 }
        }

        const context = await browser.newContext(contextOptions)
        context.setDefaultTimeout(this.config.globalTimeout)

        // 禁用 WebAuthn
        await context.addInitScript(() => {
            try {
                Object.defineProperty(navigator, 'credentials', {
                    value: {
                        create: () => Promise.reject(new Error('WebAuthn disabled')),
                        get: () => Promise.reject(new Error('WebAuthn disabled'))
                    }
                })
            } catch {
                // 忽略
            }
        })

        return { browser, context }
    }

    /**
     * 自动检测已安装的 Chromium 可执行文件路径
     * 支持 Playwright 和 patchright 的默认安装位置
     */
    _detectChromiumPath() {
        // 常见的 Playwright 缓存目录
        const cacheDirs = [
            // Linux
            path.join(os.homedir(), '.cache', 'ms-playwright'),
            // Windows
            path.join(process.env.LOCALAPPDATA || '', 'ms-playwright'),
            // macOS
            path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright')
        ].filter(Boolean)

        // 候选路径列表（按优先级排序）
        const candidates = []

        for (const cacheDir of cacheDirs) {
            if (!fs.existsSync(cacheDir)) continue

            try {
                const entries = fs.readdirSync(cacheDir)

                // 标准 Chromium
                const chromiumDirs = entries
                    .filter(e => e.startsWith('chromium-') && !e.includes('headless'))
                    .sort()
                    .reverse()

                for (const dir of chromiumDirs) {
                    candidates.push(
                        { path: path.join(cacheDir, dir, 'chrome-linux64', 'chrome'), type: 'linux64' },
                        { path: path.join(cacheDir, dir, 'chrome-linux', 'chrome'), type: 'linux' },
                        { path: path.join(cacheDir, dir, 'chrome-win64', 'chrome.exe'), type: 'win64' },
                        { path: path.join(cacheDir, dir, 'chrome-win', 'chrome.exe'), type: 'win' },
                        { path: path.join(cacheDir, dir, 'chrome-mac', 'chrome'), type: 'mac' }
                    )
                }

                // Headless Shell（作为回退方案）
                const headlessDirs = entries
                    .filter(e => e.includes('chromium_headless_shell') || e.includes('chromium-headless-shell'))
                    .sort()
                    .reverse()

                for (const dir of headlessDirs) {
                    candidates.push(
                        { path: path.join(cacheDir, dir, 'chrome-headless-shell-linux64', 'chrome-headless-shell'), type: 'headless-linux64' },
                        { path: path.join(cacheDir, dir, 'chrome-linux64', 'chrome-headless-shell'), type: 'headless-linux64-alt' }
                    )
                }
            } catch {
                // 忽略读取错误
            }
        }

        // 筛选出存在且可执行的路径
        for (const candidate of candidates) {
            if (!fs.existsSync(candidate.path)) {
                continue
            }

            // 检查可执行权限（非 Windows）
            if (process.platform !== 'win32') {
                try {
                    fs.accessSync(candidate.path, fs.constants.X_OK)
                } catch {
                    // 尝试自动添加执行权限
                    try {
                        fs.chmodSync(candidate.path, 0o755)
                        fs.accessSync(candidate.path, fs.constants.X_OK)
                        this.logger.info('BROWSER', `已为 ${candidate.path} 添加执行权限`)
                    } catch (chmodErr) {
                        this.logger.warn('BROWSER', `${candidate.path} 存在但不可执行: ${chmodErr.message}`)
                        continue
                    }
                }
            }

            this.logger.debug('BROWSER', `找到可用的 Chromium: ${candidate.path} (${candidate.type})`)
            return candidate.path
        }

        return null
    }

    /**
     * 输出 Playwright 缓存目录的详细信息，用于诊断 ENOENT 问题
     */
    _logPlaywrightCacheInfo() {
        const cacheDirs = [
            path.join(os.homedir(), '.cache', 'ms-playwright'),
            path.join(process.env.LOCALAPPDATA || '', 'ms-playwright'),
            path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright')
        ].filter(Boolean)

        this.logger.error('BROWSER', '========== Chromium 诊断信息 ==========')

        for (const cacheDir of cacheDirs) {
            if (!fs.existsSync(cacheDir)) {
                this.logger.error('BROWSER', `目录不存在: ${cacheDir}`)
                continue
            }

            this.logger.error('BROWSER', `目录存在: ${cacheDir}`)
            try {
                const entries = fs.readdirSync(cacheDir)
                this.logger.error('BROWSER', `  内容: ${entries.join(', ') || '(空)'}`)

                // 检查每个 chromium 目录的内部结构
                const chromiumDirs = entries.filter(e => e.startsWith('chromium'))
                for (const dir of chromiumDirs) {
                    const fullDir = path.join(cacheDir, dir)
                    try {
                        const subEntries = fs.readdirSync(fullDir)
                        this.logger.error('BROWSER', `  ${dir}/ 内容: ${subEntries.join(', ')}`)

                        // 检查常见子目录
                        for (const subDir of ['chrome-linux64', 'chrome-linux', 'chrome-win64', 'chrome-win', 'chrome-mac']) {
                            const subPath = path.join(fullDir, subDir)
                            if (fs.existsSync(subPath)) {
                                const files = fs.readdirSync(subPath)
                                const execName = subDir.startsWith('chrome-win') ? 'chrome.exe' : 'chrome'
                                const hasExec = files.includes(execName)
                                this.logger.error('BROWSER', `    ${subDir}/ ${hasExec ? '✓ 包含 ' + execName : '✗ 缺少 ' + execName} | 文件: ${files.slice(0, 10).join(', ')}${files.length > 10 ? '...' : ''}`)
                            }
                        }
                    } catch (e) {
                        this.logger.error('BROWSER', `  ${dir}/ 读取失败: ${e.message}`)
                    }
                }
            } catch (e) {
                this.logger.error('BROWSER', `  读取失败: ${e.message}`)
            }
        }

        this.logger.error('BROWSER', '======================================')
        this.logger.error('BROWSER', '修复方法：')
        this.logger.error('BROWSER', '1. 运行: npx playwright install chromium')
        this.logger.error('BROWSER', '2. 或在 config.json 的 browser.executablePath 中手动指定路径')
        this.logger.error('BROWSER', '3. Linux 可能需要: npx playwright install-deps chromium')
    }

    /**
     * 检查可执行文件的动态链接库依赖（仅 Linux）
     * 当文件存在但 spawn 报 ENOENT 时，通常是缺少 .so 文件
     */
    _checkSharedLibraries(execPath) {
        const { execSync, spawnSync } = require('child_process')

        this.logger.error('BROWSER', '========== 动态链接库检查 ==========')
        this.logger.error('BROWSER', `检查文件: ${execPath}`)

        // 检查文件权限和类型
        try {
            const stats = fs.statSync(execPath)
            this.logger.error('BROWSER', `文件权限: ${(stats.mode & 0o777).toString(8)} | 大小: ${stats.size} 字节`)
        } catch (e) {
            this.logger.error('BROWSER', `无法获取文件信息: ${e.message}`)
            return
        }

        // 读取 ELF 头判断是否为 glibc 编译
        try {
            const fd = fs.openSync(execPath, 'r')
            const buffer = Buffer.alloc(64)
            fs.readSync(fd, buffer, 0, 64, 0)
            fs.closeSync(fd)

            // ELF magic: 0x7F 'E' 'L' 'F'
            const isElf = buffer[0] === 0x7F && buffer[1] === 0x45 && buffer[2] === 0x4C && buffer[3] === 0x46
            this.logger.error('BROWSER', `ELF 可执行文件: ${isElf ? '是' : '否'}`)

            if (isElf) {
                // 读取 ELF interpreter (动态链接器路径)
                // 对于 64 位 ELF，e_phoff 在 offset 32, e_phentsize 在 54, e_phnum 在 56
                const e_phoff = buffer.readUInt32LE(32)
                const e_phentsize = buffer.readUInt16LE(54)
                const e_phnum = buffer.readUInt16LE(56)

                // 读取程序头表，查找 PT_INTERP (类型 3)
                const headerBuf = Buffer.alloc(e_phentsize * e_phnum)
                const fd2 = fs.openSync(execPath, 'r')
                fs.readSync(fd2, headerBuf, 0, headerBuf.length, e_phoff)
                fs.closeSync(fd2)

                let interpreter = null
                for (let i = 0; i < e_phnum; i++) {
                    const offset = i * e_phentsize
                    const p_type = headerBuf.readUInt32LE(offset)
                    if (p_type === 3) { // PT_INTERP
                        const p_offset = headerBuf.readUInt32LE(offset + 8)
                        const p_filesz = headerBuf.readUInt32LE(offset + 32)
                        const interpBuf = Buffer.alloc(p_filesz)
                        const fd3 = fs.openSync(execPath, 'r')
                        fs.readSync(fd3, interpBuf, 0, p_filesz, p_offset)
                        fs.closeSync(fd3)
                        interpreter = interpBuf.toString('utf8').replace(/\0$/, '')
                        break
                    }
                }

                this.logger.error('BROWSER', `动态链接器: ${interpreter || '(未找到)'}`)

                if (interpreter) {
                    // 检查链接器是否存在
                    if (fs.existsSync(interpreter)) {
                        this.logger.error('BROWSER', `动态链接器存在: ${interpreter}`)
                    } else {
                        this.logger.error('BROWSER', `【根本原因】动态链接器不存在: ${interpreter}`)
                        this.logger.error('BROWSER', `这是典型的 glibc/musl 不兼容问题：`)
                        this.logger.error('BROWSER', `  - Chromium 需要 glibc 动态链接器 (ld-linux-x86-64.so.2)`)
                        this.logger.error('BROWSER', `  - 你的系统可能是 Alpine Linux (使用 musl libc)`)
                        this.logger.error('BROWSER', ``)
                        this.logger.error('BROWSER', `【解决方案】选择以下任一方式：`)
                        this.logger.error('BROWSER', `  方案1（推荐）：使用 glibc 兼容环境`)
                        this.logger.error('BROWSER', `    Alpine: apk add gcompat`)
                        this.logger.error('BROWSER', `  方案2：安装 glibc 到 Alpine`)
                        this.logger.error('BROWSER', `    apk add libstdc++ glib-dev`)
                        this.logger.error('BROWSER', `  方案3：使用 Docker 运行（最简单）`)
                        this.logger.error('BROWSER', `    docker run --rm -it -v "$PWD:/app" -w /app node:20-slim node microsoft-rewards-standalone.js`)
                        this.logger.error('BROWSER', `  方案4：安装 Chromium 系统包`)
                        this.logger.error('BROWSER', `    Alpine: apk add chromium nss freetype harfbuzz ttf-freefont`)
                        this.logger.error('BROWSER', `    然后在 config 中设置 executablePath 为 /usr/bin/chromium-browser`)
                        this.logger.error('BROWSER', ``)
                        this.logger.error('BROWSER', `【检测系统信息】`)
                        try {
                            const osRelease = fs.readFileSync('/etc/os-release', 'utf8')
                            this.logger.error('BROWSER', `系统信息:\n${osRelease}`)
                        } catch {
                            this.logger.error('BROWSER', '无法读取 /etc/os-release')
                        }
                        this.logger.error('BROWSER', '====================================')
                        return
                    }
                }
            }
        } catch (e) {
            this.logger.error('BROWSER', `ELF 头分析失败: ${e.message}`)
        }

        // 尝试 ldd（如果可用）
        try {
            const lddOutput = spawnSync('ldd', [execPath], { encoding: 'utf8', timeout: 5000 })
            if (lddOutput.error) {
                throw lddOutput.error
            }
            const output = (lddOutput.stdout || '') + (lddOutput.stderr || '')
            const lines = output.split('\n').filter(Boolean)
            const missingLibs = lines.filter(l => l.includes('not found'))

            this.logger.error('BROWSER', `ldd 检查: 依赖库 ${lines.length} 个 | 缺失 ${missingLibs.length} 个`)

            if (missingLibs.length > 0) {
                this.logger.error('BROWSER', '---------- 缺失的动态库 ----------')
                for (const lib of missingLibs) {
                    this.logger.error('BROWSER', `  ${lib.trim()}`)
                }
                this.logger.error('BROWSER', '--------------------------------')
                this.logger.error('BROWSER', '【解决方案】运行: npx playwright install-deps chromium')
                this.logger.error('BROWSER', '  或 Ubuntu/Debian: sudo apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0')
            } else {
                this.logger.error('BROWSER', '所有依赖库均已找到')
            }
        } catch (e) {
            this.logger.error('BROWSER', `ldd 命令不可用: ${e.message}`)
            this.logger.error('BROWSER', '你的系统可能是 Alpine Linux 或精简版，缺少 file/ldd 工具')
            this.logger.error('BROWSER', '建议使用 Docker 的 node:20-slim 镜像运行此脚本')
        }

        // 尝试直接运行
        try {
            const result = spawnSync(execPath, ['--version'], { encoding: 'utf8', timeout: 5000 })
            if (result.status === 0) {
                this.logger.error('BROWSER', `直接运行成功: ${result.stdout.trim()}`)
            } else {
                this.logger.error('BROWSER', `直接运行失败，状态码: ${result.status}`)
                if (result.stderr) this.logger.error('BROWSER', `错误输出: ${result.stderr.trim()}`)
                if (result.error) this.logger.error('BROWSER', `错误: ${result.error.message}`)
            }
        } catch (e) {
            this.logger.error('BROWSER', `直接运行异常: ${e.message}`)
        }

        this.logger.error('BROWSER', '====================================')
    }

    _formatProxyServer(proxy) {
        try {
            const urlObj = new URL(proxy.url)
            const protocol = urlObj.protocol.replace(':', '')
            return `${protocol}://${urlObj.hostname}:${proxy.port}`
        } catch {
            return `${proxy.url}:${proxy.port}`
        }
    }
}

// ============================================================================
// 登录管理（状态机）
// ============================================================================
class LoginManager {
    constructor(bot, logger) {
        this.bot = bot
        this.logger = logger

        this.selectors = {
            primaryButton: 'button[data-testid="primaryButton"]',
            secondaryButton: 'button[data-testid="secondaryButton"]',
            emailIcon: '[data-testid="tile"]:has(svg path[d*="M5.25 4h13.5a3.25"])',
            emailIconOld: 'img[data-testid="accessibleImg"][src*="picker_verify_email"]',
            recoveryEmail: '[data-testid="proof-confirmation"]',
            passwordIcon: '[data-testid="tile"]:has(svg path[d*="M11.78 10.22a.75.75"])',
            accountLocked: '#serviceAbuseLandingTitle',
            errorAlert: 'div[role="alert"]',
            passwordEntry: '[data-testid="passwordEntry"] input, input[type="password"], #i0118',
            emailEntry: 'input#usernameEntry',
            kmsiVideo: '[data-testid="kmsiVideo"]',
            passKeyVideo: '[data-testid="biometricVideo"]',
            passKeyError: '[data-testid="registrationImg"]',
            passwordlessCheck: '[data-testid="deviceShieldCheckmarkVideo"]',
            totpInput: 'input[name="otc"]',
            totpInputOld: 'form[name="OneTimeCodeViewForm"]',
            identityBanner: '[data-testid="identityBanner"]',
            viewFooter: '[data-testid="viewFooter"] >> [role="button"]',
            otherWaysToSignIn: '[data-testid="viewFooter"] span[role="button"]',
            otpCodeEntry: '[data-testid="codeEntry"]',
            backButton: '#back-button',
            requestToken: 'input[name="__RequestVerificationToken"]',
            requestTokenMeta: 'meta[name="__RequestVerificationToken"]',
            bingProfile: '#id_l, .b_caption, [id^="id_p"], .id_avatar, #b_id_li, .id_avatarContainer, #id_d'
        }
    }

    async login(page, account) {
        this.logger.info('LOGIN', `开始登录流程: ${account.email}`)

        await page
            .goto('https://rewards.bing.com/createuser?idru=%2F&userScenarioId=anonsignin', {
                waitUntil: 'domcontentloaded'
            })
            .catch(() => {})
        await wait(2000)
        // Script-4：检测 neterror 错误页并自动刷新
        await this._reloadBadPage(page)

        const maxIterations = 25
        let iteration = 0
        let previousState = 'UNKNOWN'
        let sameStateCount = 0

        while (iteration < maxIterations) {
            if (page.isClosed()) throw new Error('页面意外关闭')
            iteration++
            this.logger.debug('LOGIN', `状态检查 ${iteration}/${maxIterations}`)

            const state = await this._detectState(page, account)
            this.logger.debug('LOGIN', `当前状态: ${state}`)

            if (state === previousState && state !== 'LOGGED_IN' && state !== 'UNKNOWN') {
                sameStateCount++
                if (sameStateCount >= 4) {
                    this.logger.warn('LOGIN', `状态 "${state}" 卡住，刷新页面`)
                    await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {})
                    await wait(3000)
                    sameStateCount = 0
                    previousState = 'UNKNOWN'
                    continue
                }
            } else {
                sameStateCount = 0
            }
            previousState = state

            if (state === 'LOGGED_IN') {
                this.logger.success('LOGIN', '登录成功')
                break
            }

            const shouldContinue = await this._handleState(state, page, account)
            if (!shouldContinue) {
                throw new Error(`登录在状态 ${state} 失败`)
            }
            await wait(1000)
        }

        if (iteration >= maxIterations) {
            throw new Error('登录超时：超过最大迭代次数')
        }

        await this._finalizeLogin(page, account.email)
    }

    /**
     * Script-4 BrowserUtils.reloadBadPage：检测 neterror 错误页并自动刷新
     */
    async _reloadBadPage(page) {
        try {
            const html = await page.content()
            const isBadPage = /<body[^>]*\bclass=["'][^"']*\bneterror\b/i.test(html)
            if (isBadPage) {
                this.logger.warn('LOGIN', '检测到 neterror 错误页，刷新页面')
                await page.reload({ waitUntil: 'load' }).catch(() => {
                    page.reload().catch(() => {})
                })
                return true
            }
        } catch {
            // 忽略
        }
        return false
    }

    async _detectState(page, account) {
        await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
        let url
        try {
            url = new URL(page.url())
        } catch {
            return 'UNKNOWN'
        }

        if (url.hostname === 'chromewebdata') return 'CHROMEWEBDATA_ERROR'

        const isLocked = await this._checkSelector(page, this.selectors.accountLocked)
        if (isLocked) return 'ACCOUNT_LOCKED'

        if (url.hostname === 'rewards.bing.com' || url.hostname === 'account.microsoft.com') {
            return 'LOGGED_IN'
        }

        const stateChecks = [
            [this.selectors.errorAlert, 'ERROR_ALERT'],
            [this.selectors.passwordEntry, 'PASSWORD_INPUT'],
            [this.selectors.emailEntry, 'EMAIL_INPUT'],
            [this.selectors.recoveryEmail, 'RECOVERY_EMAIL_INPUT'],
            [this.selectors.kmsiVideo, 'KMSI_PROMPT'],
            [this.selectors.passKeyVideo, 'PASSKEY_VIDEO'],
            [this.selectors.passKeyError, 'PASSKEY_ERROR'],
            [this.selectors.passwordIcon, 'SIGN_IN_ANOTHER_WAY'],
            [this.selectors.emailIcon, 'SIGN_IN_ANOTHER_WAY_EMAIL'],
            [this.selectors.emailIconOld, 'SIGN_IN_ANOTHER_WAY_EMAIL'],
            [this.selectors.passwordlessCheck, 'LOGIN_PASSWORDLESS'],
            [this.selectors.totpInput, '2FA_TOTP'],
            [this.selectors.totpInputOld, '2FA_TOTP'],
            [this.selectors.otpCodeEntry, 'OTP_CODE_ENTRY']
        ]

        const results = await Promise.all(
            stateChecks.map(async ([sel, state]) => {
                const visible = await this._checkSelector(page, sel)
                return visible ? state : null
            })
        )

        let foundStates = results.filter(s => s !== null)

        if (foundStates.length === 0) return 'UNKNOWN'

        if (foundStates.includes('ERROR_ALERT')) {
            if (url.hostname !== 'login.live.com') {
                foundStates = foundStates.filter(s => s !== 'ERROR_ALERT')
            }
            if (foundStates.includes('2FA_TOTP')) {
                foundStates = foundStates.filter(s => s !== 'ERROR_ALERT')
            }
            if (foundStates.includes('ERROR_ALERT')) return 'ERROR_ALERT'
        }

        const priorities = [
            'ACCOUNT_LOCKED',
            'PASSKEY_VIDEO',
            'PASSKEY_ERROR',
            'KMSI_PROMPT',
            'PASSWORD_INPUT',
            'EMAIL_INPUT',
            'SIGN_IN_ANOTHER_WAY',
            'SIGN_IN_ANOTHER_WAY_EMAIL',
            'OTP_CODE_ENTRY',
            'LOGIN_PASSWORDLESS',
            '2FA_TOTP'
        ]

        for (const priority of priorities) {
            if (foundStates.includes(priority)) return priority
        }
        return foundStates[0]
    }

    async _checkSelector(page, selector) {
        try {
            await page.waitForSelector(selector, { state: 'visible', timeout: 200 })
            return true
        } catch {
            return false
        }
    }

    async _handleState(state, page, account) {
        switch (state) {
            case 'ACCOUNT_LOCKED': {
                this.logger.error('LOGIN', '账户已被锁定！请从配置中移除并重启！')
                throw new Error('账户已被锁定')
            }
            case 'ERROR_ALERT': {
                const errorMsg = await page.locator(this.selectors.errorAlert).innerText().catch(() => '未知错误')
                this.logger.error('LOGIN', `账户错误: ${errorMsg}`)
                throw new Error(`微软登录错误: ${errorMsg}`)
            }
            case 'LOGGED_IN':
                return true
            case 'EMAIL_INPUT': {
                this.logger.info('LOGIN', '输入邮箱')
                await page.fill(this.selectors.emailEntry, account.email)
                await wait(500)
                await page.click(this.selectors.primaryButton)
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            case 'PASSWORD_INPUT': {
                this.logger.info('LOGIN', '输入密码')
                await page.fill(this.selectors.passwordEntry, account.password)
                await wait(500)
                await page.click(this.selectors.primaryButton)
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            case 'KMSI_PROMPT': {
                this.logger.info('LOGIN', '处理 KMSI 提示（保持登录）')
                await page.click(this.selectors.primaryButton).catch(() => {})
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            case 'PASSKEY_VIDEO':
            case 'PASSKEY_ERROR': {
                this.logger.info('LOGIN', '跳过 Passkey 提示')
                await page.click(this.selectors.secondaryButton).catch(() => {})
                await wait(2000)
                return true
            }
            case '2FA_TOTP': {
                if (!account.totpSecret) {
                    this.logger.error('LOGIN', '需要 2FA 但未配置 totpSecret')
                    throw new Error('缺少 TOTP 密钥')
                }
                this.logger.info('LOGIN', '输入 TOTP 验证码')
                const code = this._generateTotp(account.totpSecret)
                const totpSelector = await this._checkSelector(page, this.selectors.totpInput)
                    ? this.selectors.totpInput
                    : this.selectors.totpInputOld
                await page.fill(totpSelector, code).catch(() => {})
                await page.click(this.selectors.primaryButton).catch(() => {})
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            case 'LOGIN_PASSWORDLESS': {
                // 微软 Authenticator 无密码登录：网页显示数字，需在手机上输入
                // 如果配置了 TOTP 密钥，切换到 TOTP 方式（可自动完成）
                if (account.totpSecret) {
                    this.logger.info('LOGIN', '检测到 Passwordless，切换到 TOTP 验证方式')
                    // 点击"其他登录方式"
                    await page.click(this.selectors.otherWaysToSignIn).catch(async () => {
                        // 备用选择器
                        await page.click('[data-testid="viewFooter"] >> [role="button"]').catch(() => {})
                    })
                    await wait(2000)

                    // 选择"使用验证码"方式（通常是第二个选项，包含 OTP 输入框的图标）
                    // 尝试点击验证码/OTP 选项
                    const otpOption = await page.locator('[data-testid="tile"]').filter({
                        has: page.locator('input[name="otc"], [data-testid="codeEntry"]')
                    }).first()
                    const otpVisible = await otpOption.isVisible().catch(() => false)

                    if (otpVisible) {
                        await otpOption.click()
                    } else {
                        // 尝试点击"验证码"选项（通常显示为电话或验证码图标）
                        await page.click('[data-testid="tile"]:nth-child(2)').catch(async () => {
                            // 尝试点击任何看起来像验证码选项的元素
                            const tiles = await page.locator('[data-testid="tile"]').count()
                            for (let i = 1; i <= tiles; i++) {
                                await page.click(`[data-testid="tile"]:nth-child(${i})`).catch(() => {})
                                await wait(1000)
                                const hasOtp = await this._checkSelector(page, this.selectors.totpInput)
                                if (hasOtp) break
                            }
                        })
                    }
                    await wait(2000)
                    return true
                }

                // 没有 TOTP 密钥：截图让用户查看网页上的验证码
                this.logger.warn('LOGIN', '检测到 Passwordless（无密码登录）')
                this.logger.warn('LOGIN', '请在手机 Authenticator 应用中批准登录请求')
                this.logger.warn('LOGIN', '如果需要输入数字，请查看下方截图文件')

                // 截图保存
                const screenshotPath = `passwordless-${account.email.replace(/[@.]/g, '_')}-${Date.now()}.png`
                try {
                    await page.screenshot({ path: screenshotPath, fullPage: true })
                    this.logger.warn('LOGIN', `截图已保存: ${screenshotPath}`)
                    this.logger.warn('LOGIN', `请查看截图获取验证码，在手机上输入对应数字`)

                    // 等待用户在手机上批准（最多 60 秒）
                    this.logger.warn('LOGIN', '等待 60 秒让你在手机上完成验证...')
                    await wait(60000)
                } catch (e) {
                    this.logger.error('LOGIN', `截图失败: ${e.message}`)
                    this.logger.warn('LOGIN', '请手动处理验证，等待 60 秒...')
                    await wait(60000)
                }
                return true
            }
            case 'OTP_CODE_ENTRY': {
                // OTP 验证码输入（可能是邮箱或短信验证码）
                if (!account.totpSecret) {
                    this.logger.warn('LOGIN', '需要输入验证码，但未配置 totpSecret')
                    this.logger.warn('LOGIN', '请查看邮箱或手机短信获取验证码')

                    // 截图
                    const screenshotPath = `otp-${account.email.replace(/[@.]/g, '_')}-${Date.now()}.png`
                    try {
                        await page.screenshot({ path: screenshotPath, fullPage: true })
                        this.logger.warn('LOGIN', `截图已保存: ${screenshotPath}`)
                    } catch {
                        // 忽略截图失败
                    }

                    // 等待用户手动输入（最多 120 秒）
                    this.logger.warn('LOGIN', '等待 120 秒让你手动处理...')
                    await wait(120000)
                    return true
                }

                this.logger.info('LOGIN', '输入 OTP 验证码')
                const code = this._generateTotp(account.totpSecret)
                await page.fill(this.selectors.otpCodeEntry, code).catch(async () => {
                    // 备用：尝试其他 OTP 输入框
                    await page.fill('input[type="tel"], input[type="text"][maxlength="6"]', code).catch(() => {})
                })
                await page.click(this.selectors.primaryButton).catch(() => {})
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            case 'CHROMEWEBDATA_ERROR': {
                this.logger.warn('LOGIN', '检测到 chromewebdata 错误，尝试恢复')
                // Script-4：先尝试 rewards.bing.com，失败则 fallback 到 login.live.com
                try {
                    await page.goto(this.bot.config.baseURL, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {})
                    await wait(3000)
                    // 检查是否仍处于 chromewebdata
                    let url
                    try { url = new URL(page.url()) } catch { url = null }
                    if (url && url.hostname === 'chromewebdata') {
                        throw new Error('still chromewebdata')
                    }
                    return true
                } catch {
                    this.logger.warn('LOGIN', 'rewards.bing.com 恢复失败，fallback 到 login.live.com')
                    await page.goto('https://login.live.com/', { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {})
                    await wait(3000)
                    return true
                }
            }
            case 'SIGN_IN_ANOTHER_WAY': {
                this.logger.info('LOGIN', '选择密码登录方式')
                await page.click(this.selectors.passwordIcon).catch(() => {})
                await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
                return true
            }
            default:
                this.logger.debug('LOGIN', `未处理的状态: ${state}`)
                return true
        }
    }

    _generateTotp(secret) {
        try {
            const otpauth = require('otpauth')
            const totp = new otpauth.TOTP({
                issuer: 'Microsoft',
                algorithm: 'SHA1',
                digits: 6,
                period: 30,
                secret: otpauth.Secret.fromBase32(secret)
            })
            return totp.generate()
        } catch (error) {
            this.logger.error('LOGIN', `TOTP 生成失败: ${error.message}`)
            throw error
        }
    }

    /**
     * 从浏览器上下文更新 bot.cookies，确保后续 API 调用使用最新的会话状态
     * @param {object} page 浏览器页面
     * @param {string} tag 日志标签
     * @param {string} desc cookies 描述（如 'Bing 会话'、'奖励会话'）
     */
    async _updateCookiesFromContext(page, tag, desc) {
        try {
            const freshCookies = await page.context().cookies()
            this.bot.cookies = freshCookies
            this.logger.debug(tag, `${desc} cookies 已更新 | cookies 数量: ${freshCookies.length}`)
        } catch (e) {
            this.logger.warn(tag, `更新 cookies 失败: ${e.message}`)
        }
    }

    async _finalizeLogin(page, email) {
        // 1. 验证 Bing 会话（访问 cn.bing.com 认证页面，设置 Bing 相关 cookies）
        await this._verifyBingSession(page)

        // 2. 初始化 Rewards 会话（访问 rewards.bing.com，设置奖励会话 cookies 并获取 requestToken）
        await this._getRewardsSession(page)
    }

    /**
     * 验证 Bing 会话
     * 访问 cn.bing.com 认证页面，确保 Bing 会话已建立
     * 这会设置必要的 cookies，使后续 API 调用返回完整数据
     */
    async _verifyBingSession(page) {
        const url = 'https://cn.bing.com/fd/auth/signin?action=interactive&provider=windows_live_id&return_url=https%3A%2F%2Fcn.bing.com%2F'
        this.logger.info('LOGIN-BING', '验证 Bing 会话')

        try {
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {})

            // 等待重定向到 Bing 首页
            for (let i = 0; i < 5; i++) {
                if (page.isClosed()) break

                try {
                    const u = new URL(page.url())
                    const atBingHome = u.hostname === 'cn.bing.com' && u.pathname === '/'

                    if (atBingHome) {
                        // 检查是否已登录（查找头像元素）
                        const signedIn = await page.$(this.selectors.bingProfile).catch(() => null)
                        if (signedIn) {
                            this.logger.info('LOGIN-BING', 'Bing 会话验证成功')
                            break
                        }
                    }
                } catch {
                    // URL 解析失败，继续等待
                }

                await wait(1000)
            }

            // 关键：更新 cookies，确保后续 API 调用使用最新的会话状态
            // 访问 cn.bing.com 后浏览器会设置 Bing 相关的 cookies（如 _SS_MUID、MUID 等）
            // 这些 cookies 对于 API 返回完整的促销数据至关重要
            await this._updateCookiesFromContext(page, 'LOGIN-BING', 'Bing 会话')
        } catch (error) {
            this.logger.warn('LOGIN-BING', `Bing 会话验证错误: ${error.message}`)
        }
    }

    /**
     * 初始化 Rewards 会话
     * 访问 rewards.bing.com 仪表盘页面，设置奖励会话 cookies 并获取 requestToken
     * 这是关键步骤：缺少此步骤会导致 getDashboardData API 返回不完整的促销数据
     * （例如缺失 Evergreen 类型的 More Promotions 活动）
     */
    async _getRewardsSession(page) {
        this.logger.info('GET-REWARD-SESSION', '获取请求令牌并初始化奖励会话')

        try {
            // 访问 rewards.bing.com 仪表盘页面（添加时间戳防止缓存）
            await page.goto(`${this.bot.config.baseURL}?_=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {})

            let reachedRewardHome = false
            for (let i = 0; i < 5; i++) {
                if (page.isClosed()) break

                try {
                    const u = new URL(page.url())
                    const atRewardHome = u.hostname === 'rewards.bing.com' && (u.pathname === '/' || u.pathname === '/dashboard')

                    if (atRewardHome) {
                        reachedRewardHome = true
                        // 尝试获取 requestToken
                        const tokenEl = await page.$(this.selectors.requestToken).catch(() => null)
                        if (tokenEl) {
                            this.bot.requestToken = await tokenEl.inputValue()
                        } else {
                            const metaEl = await page.$(this.selectors.requestTokenMeta).catch(() => null)
                            if (metaEl) {
                                this.bot.requestToken = await metaEl.getAttribute('content')
                            }
                        }

                        if (this.bot.requestToken) {
                            this.logger.info('GET-REWARD-SESSION', `请求令牌已获取: ${this.bot.requestToken.substring(0, 10)}...`)
                        } else {
                            // Script-4：现代 RSC 仪表盘不再在 HTML 中渲染 token input/meta 标签，
                            // 所有上报通过 Server Action 机制（Next-Action header），不依赖 RequestVerificationToken
                            this.logger.debug('GET-REWARD-SESSION', '未找到 RequestVerificationToken（现代仪表盘正常行为，使用 Server Action 替代）')
                        }

                        // 等待页面完全加载，确保所有 cookies 已设置
                        await wait(2000)
                        break
                    }
                } catch {
                    // URL 解析失败，继续等待
                }

                await wait(1000)
            }

            // 即使未到达 rewards 首页，也尝试获取 token
            if (!reachedRewardHome) {
                const tokenEl = await page.$(this.selectors.requestToken).catch(() => null)
                if (tokenEl) {
                    this.bot.requestToken = await tokenEl.inputValue()
                    this.logger.info('GET-REWARD-SESSION', `请求令牌已获取（备用）: ${this.bot.requestToken.substring(0, 10)}...`)
                }
                this.logger.warn('GET-REWARD-SESSION', '未到达奖励首页，会话初始化可能不完整')
            }

            // 关键：更新 cookies，确保后续 API 调用使用最新的会话状态
            // 访问 rewards.bing.com 后浏览器会设置奖励会话相关的 cookies
            // 这些 cookies 对于 getDashboardData API 返回完整的促销数据（包括 Evergreen 活动）至关重要
            // 缺少这些 cookies 会导致 API 返回精简数据，缺失 ENstar_Rewards_DailyGlobalOffer_Evergreen_* 系列活动
            await this._updateCookiesFromContext(page, 'GET-REWARD-SESSION', '奖励会话')

            this.logger.info('GET-REWARD-SESSION', '奖励会话初始化完成')
        } catch (error) {
            this.logger.warn('GET-REWARD-SESSION', `奖励会话初始化错误: ${error.message}`)
        }
    }

    async getAppAccessToken(page, email) {
        this.logger.info('AUTH', '请求移动应用访问令牌')

        const clientId = '0000000040170455'
        const authUrl = 'https://login.live.com/oauth20_authorize.srf'
        const redirectUrl = 'https://login.live.com/oauth20_desktop.srf'
        const tokenUrl = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/token'
        const scope = 'service::prod.rewardsplatform.microsoft.com::MBI_SSL'

        // 最多重试 3 次
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                this.logger.info('AUTH', `OAuth 尝试 ${attempt}/3`)
                const token = await this._tryGetAppAccessToken(page, email, clientId, authUrl, redirectUrl, tokenUrl, scope)
                if (token) {
                    return token
                }
                if (attempt < 3) {
                    this.logger.warn('AUTH', `OAuth 尝试 ${attempt} 失败，5 秒后重试...`)
                    await wait(5000)
                }
            } catch (error) {
                this.logger.warn('AUTH', `OAuth 尝试 ${attempt} 异常: ${error.message}`)
                if (attempt < 3) {
                    await wait(5000)
                }
            }
        }

        this.logger.error('AUTH', '获取访问令牌失败：3 次重试均失败')
        return ''
    }

    async _tryGetAppAccessToken(page, email, clientId, authUrl, redirectUrl, tokenUrl, scope) {
        const authorizeUrl = new URL(authUrl)
        authorizeUrl.searchParams.append('response_type', 'code')
        authorizeUrl.searchParams.append('client_id', clientId)
        authorizeUrl.searchParams.append('redirect_uri', redirectUrl)
        authorizeUrl.searchParams.append('scope', scope)
        authorizeUrl.searchParams.append('state', crypto.randomBytes(16).toString('hex'))
        authorizeUrl.searchParams.append('access_type', 'offline_access')
        authorizeUrl.searchParams.append('login_hint', email)

        // 使用更长的导航超时（60 秒）
        await page.goto(authorizeUrl.href, { timeout: 60000, waitUntil: 'domcontentloaded' }).catch(e => {
            this.logger.debug('AUTH', `OAuth 导航: ${e.message}`)
        })

        const start = Date.now()
        const maxTimeout = 120000  // 2 分钟
        let code = ''
        let lastUrl = ''

        while (Date.now() - start < maxTimeout) {
            const currentUrl = page.url()
            if (currentUrl !== lastUrl) {
                this.logger.debug('AUTH', `OAuth URL 变化: ${currentUrl}`)
                lastUrl = currentUrl
            }

            try {
                const url = new URL(currentUrl)
                if (url.hostname === 'login.live.com' && url.pathname === '/oauth20_desktop.srf') {
                    code = url.searchParams.get('code') || ''
                    if (code) {
                        this.logger.debug('AUTH', '检测到 OAuth 授权码')
                        break
                    }
                }

                // 处理 Passkey 提示
                const hasPasskey = await this._checkSelector(page, this.selectors.passKeyError)
                    || await this._checkSelector(page, this.selectors.passKeyVideo)
                if (hasPasskey) {
                    await page.click(this.selectors.secondaryButton).catch(() => {})
                    await wait(2000)
                }
            } catch {
                // 忽略无效 URL
            }
            await wait(1000)
        }

        if (!code) {
            this.logger.warn('AUTH', '等待 OAuth 授权码超时')
            return ''
        }

        const data = new URLSearchParams()
        data.append('grant_type', 'authorization_code')
        data.append('client_id', clientId)
        data.append('code', code)
        data.append('redirect_uri', redirectUrl)

        const response = await this.bot.httpClient.request({
            url: tokenUrl,
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            data: data.toString()
        })

        const token = response?.data?.access_token || ''
        if (token) {
            this.logger.success('AUTH', '移动应用访问令牌获取成功')
        } else {
            this.logger.warn('AUTH', '令牌响应中无 access_token')
        }
        return token
    }
}

// ============================================================================
// 奖励任务管理器
// ============================================================================
class RewardsManager {
    constructor(bot, logger) {
        this.bot = bot
        this.logger = logger
        this._bingJars = new Map()
    }

    /**
     * 获取桌面仪表盘数据
     */
    async getDashboardData() {
        // 如果有缓存且在 30 秒内，优先返回缓存（减少 API 调用，避免 ECONNRESET）
        const now = Date.now()
        if (this._dashboardCache && this._dashboardCacheTime && (now - this._dashboardCacheTime) < 30000) {
            this.logger.debug('DASHBOARD', '使用缓存的仪表盘数据')
            return this._dashboardCache
        }

        const cookieHeader = this.bot.sessionManager.buildCookieHeader(this.bot.cookies, COMMON_COOKIE_DOMAINS)

        // 使用完整的浏览器指纹头（与 EXE 一致）
        // 这些头对于 API 返回完整的促销数据至关重要（包括 Evergreen 类型的 More Promotions 活动）
        // Script-4 整合：使用 generateMobileFingerprintHeaders() 随机机型，避免固定 Pixel 8
        const fingerprintHeaders = generateMobileFingerprintHeaders()

        // 最多重试 3 次
        let lastError = null
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                const response = await this.bot.httpClient.request({
                    url: 'https://rewards.bing.com/api/getuserinfo?type=1',
                    method: 'GET',
                    headers: {
                        ...fingerprintHeaders,
                        Cookie: cookieHeader,
                        Referer: 'https://rewards.bing.com/',
                        Origin: 'https://rewards.bing.com'
                    }
                })

                if (response.data?.dashboard) {
                    // 缓存成功响应
                    this._dashboardCache = response.data.dashboard
                    this._dashboardCacheTime = Date.now()
                    // 输出关键活动信息，便于对比验证
                    const dash = response.data.dashboard
                    const mpCount = dash.morePromotions?.length || 0
                    const mpwpCount = dash.morePromotionsWithoutPromotionalItems?.length || 0
                    this.logger.info('DASHBOARD', `仪表盘数据: morePromotions=${mpCount}, morePromotionsWithoutPromotionalItems=${mpwpCount}`)
                    if (mpCount > 0) {
                        this.logger.info('DASHBOARD', `morePromotions 列表: ${dash.morePromotions.map(p => p.offerId).join(', ')}`)
                    }
                    if (mpwpCount > 0) {
                        this.logger.info('DASHBOARD', `morePromotionsWithoutPromotionalItems 列表: ${dash.morePromotionsWithoutPromotionalItems.map(p => p.offerId).join(', ')}`)
                    }
                    return response.data.dashboard
                }
                throw new Error('API 响应中缺少仪表盘数据')
            } catch (error) {
                lastError = error
                // Script-4：EAI_AGAIN/ECONNRESET 等网络错误是临时性的，重试是正常机制
                // 重试过程中的 WARN 降级为 DEBUG，避免误报；仅在最终全部失败时才输出 WARN
                const isTransient = /EAI_AGAIN|ECONNRESET|ETIMEDOUT|ENOTFOUND/i.test(error.message)
                if (isTransient) {
                    this.logger.debug('DASHBOARD', `API 获取失败 (尝试 ${attempt}/3): ${error.message}（临时网络错误，将重试）`)
                } else {
                    this.logger.warn('DASHBOARD', `API 获取失败 (尝试 ${attempt}/3): ${error.message}`)
                }
                if (attempt < 3) {
                    // Script-4：临时网络错误使用更长的退避时间（5/10/15 秒），给 DNS 恢复时间
                    const delay = isTransient ? 5000 * attempt : 2000 * attempt
                    await wait(delay)
                }
            }
        }

        // 所有重试失败，尝试 HTML 回退
        this.logger.warn('DASHBOARD', 'API 重试全部失败，尝试 HTML 回退')
        try {
            const response = await this.bot.httpClient.request({
                url: this.bot.config.baseURL,
                method: 'GET',
                headers: {
                    ...fingerprintHeaders,
                    Cookie: cookieHeader,
                    Referer: 'https://rewards.bing.com/'
                }
            })
            const html = String(response.data)
            // 尝试多种正则匹配（兼容新旧版仪表盘）
            const patterns = [
                /var\s+dashboard\s*=\s*({.*?});\s*<\/script>/s,
                /var\s+dashboard\s*=\s*({.*?});/s,
                /"dashboard"\s*:\s*({.*?})\s*[,}]/s,
                /window\.__NEXT_DATA__\s*=\s*({.*?});\s*<\/script>/s
            ]
            for (const pattern of patterns) {
                const match = html.match(pattern)
                if (match && match[1]) {
                    try {
                        const parsed = JSON.parse(match[1])
                        const dashboard = parsed.dashboard || parsed.props?.pageProps?.dashboard || parsed
                        if (dashboard.userStatus || dashboard.dailySetPromotions) {
                            this._dashboardCache = dashboard
                            this._dashboardCacheTime = Date.now()
                            return dashboard
                        }
                    } catch {
                        // 继续尝试下一个正则
                    }
                }
            }
            throw new Error('HTML 中未找到仪表盘脚本')
        } catch (fallbackError) {
            // 如果有旧缓存，返回旧缓存（降级处理，避免整个账户失败）
            if (this._dashboardCache) {
                // Script-4：有旧缓存可用时降级为 INFO，避免误报 WARN（降级机制正常工作）
                this.logger.info('DASHBOARD', `HTML 回退失败，使用旧缓存（降级正常）: ${fallbackError.message}`)
                return this._dashboardCache
            }
            this.logger.error('DASHBOARD', `获取仪表盘数据失败: ${fallbackError.message}`)
            throw fallbackError
        }
    }

    /**
     * 获取面板浮出数据
     */
    async getPanelFlyoutData() {
        try {
            const cookieHeader = this.bot.sessionManager.buildCookieHeader(this.bot.cookies, COMMON_COOKIE_DOMAINS)
            const response = await this.bot.httpClient.request({
                url: 'https://cn.bing.com/rewards/panelflyout/getuserinfo?channel=BingFlyout&partnerId=BingRewards',
                method: 'GET',
                headers: {
                    ...generateMobileFingerprintHeaders(),
                    Cookie: cookieHeader,
                    Origin: 'https://cn.bing.com'
                }
            })
            return response.data
        } catch (error) {
            this.logger.error('PANEL', `获取面板数据失败: ${error.message}`)
            throw error
        }
    }

    /**
     * 获取应用仪表盘数据
     */
    async getAppDashboardData() {
        if (!this.bot.accessToken) {
            this.logger.warn('APP-DASHBOARD', '跳过：应用访问令牌不可用')
            return null
        }
        try {
            const response = await this.bot.httpClient.request({
                url: 'https://prod.rewardsplatform.microsoft.com/dapi/me?channel=SAIOS&options=613',
                method: 'GET',
                headers: {
                    Authorization: `Bearer ${this.bot.accessToken}`,
                    'User-Agent': DAPI_USER_AGENT
                }
            })
            return response.data
        } catch (error) {
            this.logger.error('APP-DASHBOARD', `获取应用仪表盘数据失败: ${error.message}`)
            throw error
        }
    }

    /**
     * 获取当前积分
     */
    async getCurrentPoints() {
        try {
            const data = await this.getDashboardData()
            const points = data?.userStatus?.availablePoints ?? 0
            this.bot.currentPoints = points
            return points
        } catch (error) {
            this.logger.warn('DASHBOARD', `获取当前积分失败，使用缓存值: ${error.message}`)
            return this.bot.currentPoints ?? 0
        }
    }

    // ========================================================================
    // Script-4 Server Action 机制（bootstrap + reportServerAction + action id 发现）
    // ========================================================================

    /**
     * 初始化 rewards context：获取 /earn HTML、解析 reactSnapshot、发现 action ids
     * 移植自 Script-4 BrowserFunc.bootstrap
     */
    async bootstrap(page, isMobile = true) {
        try {
            this.logger.info('BOOTSTRAP', `初始化 rewards context | isMobile=${isMobile}`)
            await page.goto(URLS.rewards.earn, { waitUntil: 'domcontentloaded', timeout: 30000 })
            const earnHtml = await page.content()

            this.bot.nextRouterStateTree = this.bot.reactParser.routerStateTree('earn')
            this.bot.reactSnapshot = this.bot.reactParser.snapshotPage(earnHtml)

            // 获取 /dashboard HTML 以捕获 /earn 未显示的 chunks
            let dashboardHtml = ''
            try {
                const res = await page.request.get(URLS.rewards.dashboard)
                if (res.ok()) {
                    dashboardHtml = await res.text()
                } else {
                    this.logger.warn('BOOTSTRAP', `获取 /dashboard HTML 失败 | status=${res.status()}`)
                }
            } catch (error) {
                this.logger.warn('BOOTSTRAP', `获取 /dashboard HTML 失败: ${error.message}`)
            }

            // Script-4 扩展：获取 /earn?section=streaks HTML 以捕获 streak protection 相关 chunks
            let streaksHtml = ''
            try {
                const res = await page.request.get(URLS.rewards.earnStreaks)
                if (res.ok()) {
                    streaksHtml = await res.text()
                }
            } catch (error) {
                this.logger.debug('BOOTSTRAP', `获取 /earn?section=streaks HTML 失败: ${error.message}`)
            }

            // 从 chunks 中发现 action ids
            this.bot.nextActions = await this._resolveActionIds(page, [earnHtml, dashboardHtml, streaksHtml])

            const actionsCount = Object.keys(this.bot.nextActions).length
            const reportableCount = this.bot.reactSnapshot?.reportable?.length ?? 0
            this.logger.info('BOOTSTRAP', `Context 就绪 | actions=${actionsCount} | reportable=${reportableCount} | buildId=${this.bot.reactParser.buildId(earnHtml) ?? 'unknown'}`)
            this.logger.debug('BOOTSTRAP', `已发现 action ids: [${Object.keys(this.bot.nextActions).join(', ')}]`)

            if (!actionsCount) {
                this.logger.warn('BOOTSTRAP', '未发现 action ids - server-action 调用将失败')
            }
            if (!this.bot.reactSnapshot?.offers?.length) {
                this.logger.warn('BOOTSTRAP', '未解析到 offers - /earn 页面可能未渲染 RSC payload')
            }
        } catch (error) {
            this.logger.error('BOOTSTRAP', `初始化 rewards context 失败: ${error.message}`)
            throw error
        }
    }

    /**
     * 从 JS chunks 中提取 Server Action ids
     */
    async _resolveActionIds(page, htmls) {
        const result = {}
        try {
            const initialChunks = new Set()
            const chunkRegex = /(?:\/_next\/)?(static\/chunks\/[\w\-./()]+?\.js)/g
            for (const html of htmls) {
                if (!html) continue
                for (const match of html.matchAll(chunkRegex)) {
                    initialChunks.add('/_next/' + match[1])
                }
            }

            if (initialChunks.size === 0) {
                this.logger.warn('BOOTSTRAP', 'HTML 中未发现初始 chunks')
            }

            this.logger.debug('BOOTSTRAP', `获取 ${initialChunks.size} 个初始 JS chunks`)
            const jsByPath = await this._fetchJsChunks(page, [...initialChunks])

            // 动态导入的 chunks
            const dynamicPaths = []
            for (const js of jsByPath.values()) {
                for (const p of this._extractDynamicChunkPaths(js)) {
                    if (!jsByPath.has(p) && !dynamicPaths.includes(p)) {
                        dynamicPaths.push(p)
                    }
                }
            }
            if (dynamicPaths.length) {
                this.logger.debug('BOOTSTRAP', `获取 ${dynamicPaths.length} 个动态 chunks`)
                const moreJs = await this._fetchJsChunks(page, dynamicPaths)
                for (const [p, js] of moreJs) jsByPath.set(p, js)
            }

            for (const [path, js] of jsByPath) {
                const filename = path.split('/').pop() ?? path
                const ids = this.bot.reactParser.extractActionIds(js)
                const names = Object.keys(ids.byName)
                if (names.length) {
                    Object.assign(result, ids.byName)
                    this.logger.debug('BOOTSTRAP', `在 ${filename} 中发现 ${names.length} 个 action id: [${names.join(', ')}]`)
                }
            }
            this.logger.debug('BOOTSTRAP', `共发现 ${Object.keys(result).length} 个 action ids: [${Object.keys(result).join(', ')}]`)
        } catch (error) {
            this.logger.error('BOOTSTRAP', `解析 action ids 失败: ${error.message}`)
        }
        return result
    }

    async _fetchJsChunks(page, paths) {
        const result = new Map()
        await Promise.all(paths.map(async (p) => {
            try {
                const res = await page.request.get(URLS.rewards.path(p))
                if (res.ok()) result.set(p, await res.text())
            } catch (error) {
                this.logger.debug('BOOTSTRAP', `Chunk 获取失败 | path=${p} | ${error.message}`)
            }
        }))
        return result
    }

    _extractDynamicChunkPaths(js) {
        const seen = new Set()
        const builder = /static\/chunks\/"\s*\+\s*\w+\s*\+\s*"([-.])"\s*\+\s*\{([\s\S]*?)\}\s*\[/g
        for (const m of js.matchAll(builder)) {
            const sep = m[1]
            const body = m[2]
            const entryRe = /"([\w$-]+)":\s*"([^"]+)"/g
            for (const e of body.matchAll(entryRe)) {
                const path = `/_next/static/chunks/${e[2]}${sep}${e[1]}.js`
                seen.add(path)
            }
        }
        // Script-4：如果 builder 正则未匹配，全局扫描 id:hash 对作为 fallback
        // 这可以发现 builder 形状变化后的动态 chunks（如 streak protection action 所在 chunk）
        if (!seen.size) {
            const idHashRe = /\b(\d{2,6}):"([a-f0-9]{12,})"/g
            for (const m of js.matchAll(idHashRe)) {
                seen.add(`/_next/static/chunks/${m[1]}-${m[2]}.js`)
                seen.add(`/_next/static/chunks/${m[1]}.${m[2]}.js`)
            }
        }
        return [...seen]
    }

    /**
     * 调用 Next.js RSC Server Action（UrlReward / ClaimReward / PunchCard 共用）
     * 移植自 Script-4 BrowserFunc.reportServerAction
     */
    async reportServerAction(actionId, body, opts = {}, isMobile = true) {
        const url = opts.url ?? URLS.rewards.earn
        const referer = opts.referer ?? url
        const routerStateTree = opts.routerStateTree ?? this.bot.nextRouterStateTree

        const cookies = isMobile ? this.bot.cookies : this.bot.desktopCookies
        const cookieHeader = this.bot.sessionManager.buildCookieHeader(cookies, COMMON_COOKIE_DOMAINS)
        const fingerprintHeaders = isMobile ? generateMobileFingerprintHeaders() : { ...FINGERPRINT_HEADERS_DESKTOP }
        delete fingerprintHeaders['Cookie']
        delete fingerprintHeaders['cookie']

        const response = await this.bot.httpClient.request({
            url,
            method: 'POST',
            headers: {
                ...fingerprintHeaders,
                Cookie: cookieHeader,
                Referer: referer,
                Origin: URLS.rewards.origin,
                Accept: 'text/x-component',
                'Content-Type': 'text/plain;charset=UTF-8',
                'Next-Action': actionId,
                'Next-Router-State-Tree': routerStateTree
            },
            data: JSON.stringify(body)
        })

        const acknowledged = this._serverActionAcknowledged(response.data)
        return { status: response.status, acknowledged }
    }

    _serverActionAcknowledged(response) {
        const text = typeof response === 'string' ? response : String(response ?? '')
        return /^\d+:true\s*$/m.test(text)
    }

    /**
     * 获取搜索积分计数器
     */
    async getSearchPoints() {
        try {
            const data = await this.getDashboardData()
            return data?.userStatus?.counters ?? {}
        } catch (error) {
            this.logger.warn('DASHBOARD', `获取搜索积分失败，使用缓存值: ${error.message}`)
            return this._dashboardCache?.userStatus?.counters ?? {}
        }
    }

    /**
     * 计算缺失的搜索积分
     */
    missingSearchPoints(counters, isMobile) {
        const mobileData = counters.mobileSearch?.[0]
        const desktopData = counters.pcSearch?.[0]
        const edgeData = counters.pcSearch?.[1]

        const mobilePoints = mobileData ? Math.max(0, mobileData.pointProgressMax - mobileData.pointProgress) : 0
        const desktopPoints = desktopData ? Math.max(0, desktopData.pointProgressMax - desktopData.pointProgress) : 0
        const edgePoints = edgeData ? Math.max(0, edgeData.pointProgressMax - edgeData.pointProgress) : 0
        const totalPoints = isMobile ? mobilePoints : desktopPoints + edgePoints

        return { mobilePoints, desktopPoints, edgePoints, totalPoints }
    }

    /**
     * 启用连续登录保护
     */
    async ensureStreakProtection() {
        if (!this.bot.requestToken) {
            this.logger.warn('STREAK', '跳过：请求令牌不可用')
            return
        }
        try {
            const cookieHeader = this.bot.sessionManager.buildCookieHeader(this.bot.cookies, COMMON_COOKIE_DOMAINS)
            const formData = new URLSearchParams({
                isOn: 'true',
                activityAmount: '1',
                timeZone: this.bot.timezoneOffset,
                __RequestVerificationToken: this.bot.requestToken
            })
            await this.bot.httpClient.request({
                url: 'https://rewards.bing.com/api/togglestreakasync?X-Requested-With=XMLHttpRequest',
                method: 'POST',
                headers: {
                    ...generateMobileFingerprintHeaders(),
                    Cookie: cookieHeader,
                    Referer: 'https://rewards.bing.com/',
                    Origin: 'https://rewards.bing.com'
                },
                data: formData
            })
            this.logger.info('STREAK', '连续登录保护已启用')
        } catch (error) {
            this.logger.error('STREAK', `启用连续登录保护失败: ${error.message}`)
        }
    }

    /**
     * 完成每日任务集
     */
    async doDailySet(data, page, isMobile = true) {
        const todayKey = getFormattedDate()
        const todayData = data.dailySetPromotions?.[todayKey]
        const activities = (todayData || []).filter(x => !x?.complete && x.pointProgressMax > 0)

        if (!activities.length) {
            this.logger.info('DAILY-SET', '所有"每日任务"已完成')
            return
        }

        this.logger.info('DAILY-SET', `开始处理 ${activities.length} 个"每日任务"`)
        await this._solveActivities(activities, page, isMobile)
        this.logger.success('DAILY-SET', '"每日任务"全部完成')
    }

    /**
     * 完成"更多促销"任务
     */
    async doMorePromotions(data, page, isMobile = true) {
        // 刷新仪表盘数据，避免使用初始缓存的过期数据（确保获取最新的 morePromotions）
        let freshData = data
        try {
            this._dashboardCache = null // 清除缓存，强制重新获取
            freshData = await this.getDashboardData()
        } catch (e) {
            this.logger.warn('MORE-PROMOTIONS', `刷新仪表盘数据失败，使用初始数据: ${e.message}`)
        }

        // 合并 morePromotions 和 morePromotionsWithoutPromotionalItems，去重
        const rawMore = [...(freshData.morePromotions || []), ...(freshData.morePromotionsWithoutPromotionalItems || [])].filter(Boolean)
        const allMorePromotions = [
            ...new Map(
                rawMore.map(p => [p.offerId, p])
            ).values()
        ]

        this.logger.info('MORE-PROMOTIONS', `原始数据: morePromotions=${freshData.morePromotions?.length || 0}, morePromotionsWithoutPromotionalItems=${freshData.morePromotionsWithoutPromotionalItems?.length || 0}, 去重后=${allMorePromotions.length}`)
        if (allMorePromotions.length > 0) {
            this.logger.info('MORE-PROMOTIONS', `活动列表: ${allMorePromotions.map(p => p.offerId).join(', ')}`)
        }

        const activities = allMorePromotions.filter(x => {
            if (x.complete) return false
            if (x.pointProgressMax <= 0) return false
            if (x.exclusiveLockedFeatureStatus === 'locked') return false
            if (!x.promotionType) return false
            // Script-4 新增：排除负优先级未解锁项
            if (x.priority < 0 && x.exclusiveLockedFeatureStatus !== 'unlocked') return false
            // Script-4 新增：排除 promotional 项
            if (x.attributes?.promotional === 'True') return false
            return true
        })

        // 调试：记录被过滤掉的项目
        if (allMorePromotions.length > 0 && activities.length === 0) {
            for (const x of allMorePromotions) {
                const reasons = []
                if (x.complete) reasons.push('complete=true')
                if (x.pointProgressMax <= 0) reasons.push(`pointProgressMax=${x.pointProgressMax}`)
                if (x.exclusiveLockedFeatureStatus === 'locked') reasons.push('locked')
                if (!x.promotionType) reasons.push('no promotionType')
                this.logger.info('MORE-PROMOTIONS', `过滤: ${x.offerId} | ${reasons.join(', ')}`)
            }
        }

        if (!activities.length) {
            this.logger.info('MORE-PROMOTIONS', '所有"更多促销"已完成')
            return
        }

        this.logger.info('MORE-PROMOTIONS', `开始处理 ${activities.length} 个"更多促销"`)
        await this._solveActivities(activities, page, isMobile)
        this.logger.success('MORE-PROMOTIONS', '"更多促销"全部完成')
    }

    /**
     * 构建 DAPI 请求头（用于 App 促销、每日签到等 DAPI API 调用）
     * @param {boolean} isMobile 是否为移动端（影响 X-Rewards-IsMobile 值）
     * @param {boolean} withContentType 是否包含 Content-Type（POST 请求需要，GET 不需要）
     */
    _buildDapiHeaders(isMobile = false, withContentType = true) {
        const headers = {
            Authorization: `Bearer ${this.bot.accessToken}`,
            'User-Agent': DAPI_USER_AGENT,
            'X-Rewards-Country': this.bot.geoLocale,
            'X-Rewards-Language': 'zh',
            'X-Rewards-IsMobile': isMobile ? 'true' : '',
            'X-Rewards-AppId': 'SAIOS/32.5.431027001',
            'X-Rewards-PartnerId': 'startapp',
            'X-Rewards-Flights': 'rwgobig'
        }
        if (withContentType) {
            headers['Content-Type'] = 'application/json'
        }
        return headers
    }

    /**
     * 构建 DAPI 活动提交请求体
     * @param {number} type 活动类型
     * @param {object} attributes 活动属性
     */
    _buildDapiActivityBody(type, attributes = {}) {
        return {
            id: crypto.randomUUID(),
            amount: 1,
            type: type,
            attributes: attributes,
            country: this.bot.geoLocale,
            channel: 'SAIOS',
            risk_context: {}
        }
    }

    /**
     * 完成其他促销活动（通过 DAPI API）
     */
    async doOtherPromotions() {
        if (!this.bot.accessToken) {
            this.logger.warn('OTHER-PROMOTIONS', '跳过：应用访问令牌不可用，此活动需要它！')
            return
        }

        try {
            const response = await this.bot.httpClient.request({
                url: 'https://prod.rewardsplatform.microsoft.com/dapi/me?channel=SAIOS&options=612',
                method: 'GET',
                headers: this._buildDapiHeaders(false, false)
            })

            if (response.data.code != 0) {
                this.logger.warn('OTHER-PROMOTIONS', `API 返回非零代码: ${response.data.code}`)
                return
            }

            // 使用 UTC+8 时区的今天日期
            const nowCST = new Date(Date.now() + 8 * 60 * 60 * 1000)
            const today = new Date(Date.UTC(nowCST.getUTCFullYear(), nowCST.getUTCMonth(), nowCST.getUTCDate()))

            const activities = (response.data.response?.promotions || []).filter(x => {
                if (x.attributes.complete == 'True') return false
                if (x.attributes.max <= 0) return false
                if (x.attributes.State == 'locked') return false
                if (!x.attributes.type) return false
                if (x.attributes.hidden == 'True') return false
                if (x.attributes.type != 'urlreward') return false

                // 过滤掉未来的 daily_set_date 活动
                const dailySetDate = x.attributes.daily_set_date
                if (typeof dailySetDate === 'string') {
                    const [monthValue, dayValue, yearValue] = dailySetDate.split('/')
                    const month = Number(monthValue)
                    const day = Number(dayValue)
                    const year = Number(yearValue)
                    if (Number.isInteger(month) && Number.isInteger(day) && Number.isInteger(year)) {
                        const activityDate = new Date(year, month - 1, day)
                        if (activityDate > today) return false
                    }
                }
                return true
            })

            if (!activities.length) {
                this.logger.info('OTHER-PROMOTIONS', '所有"其他促销"已完成')
                return
            }

            this.logger.info('OTHER-PROMOTIONS', `开始处理 ${activities.length} 个"其他促销"`)

            let oldBalance = this.bot.currentPoints
            let totalGained = 0

            for (const activity of activities) {
                try {
                    const offerId = activity.attributes.offerid
                    this.logger.info('OTHER-PROMOTIONS', `处理活动: ${offerId}`)

                    const jsonData = this._buildDapiActivityBody(101, { offerid: offerId })

                    const resp = await this.bot.httpClient.request({
                        url: 'https://prod.rewardsplatform.microsoft.com/dapi/me/activities',
                        method: 'POST',
                        headers: this._buildDapiHeaders(),
                        data: JSON.stringify(jsonData)
                    })

                    const newBalance = Number(resp?.data?.response?.balance ?? oldBalance)
                    const gained = newBalance - oldBalance

                    if (gained > 0) {
                        totalGained += gained
                        this.bot.currentPoints = newBalance
                        this.bot.gainedPoints += gained
                        this.logger.success('OTHER-PROMOTIONS', `完成活动 ${offerId} | +${gained} 积分`)
                    } else {
                        this.logger.warn('OTHER-PROMOTIONS', `活动 ${offerId} 未获得积分`)
                    }
                    oldBalance = newBalance
                    await wait(randomDelay(5000, 15000))
                } catch (error) {
                    this.logger.error('OTHER-PROMOTIONS', `处理活动失败: ${error.message}`)
                }
            }

            this.logger.info('OTHER-PROMOTIONS', `"其他促销"完成 | 总计 +${totalGained} 积分`)
        } catch (error) {
            this.logger.warn('OTHER-PROMOTIONS', `API 调用失败: ${error.message}`)
        }
    }

    /**
     * 完成每日签到
     * Script-4 变化：type 固定 103（移除 101 fallback），UA 升级为 iPad Safari + BingSapphire 33.x
     */
    async doDailyCheckIn() {
        if (!this.bot.accessToken) {
            this.logger.warn('CHECK-IN', '跳过：应用访问令牌不可用')
            return
        }

        const oldBalance = Number(this.bot.currentPoints ?? 0)
        this.logger.info('CHECK-IN', `开始每日签到 | 当前积分: ${oldBalance}`)

        try {
            // Script-4：直接使用 type 103（移除 101 fallback）
            const gained = await this._submitDailyCheckIn(103, oldBalance)
            if (gained > 0) {
                this.logger.success('CHECK-IN', `每日签到完成 (type=103) | +${gained} 积分`)
            } else {
                // Script-4 行为一致：签到 API 成功但 balance 未变，通常因今日已签到过
                // 此为正常情况而非错误，降级为 INFO 避免误报
                this.logger.info('CHECK-IN', '每日签到完成但未获得积分（可能今日已签到过）')
            }
        } catch (error) {
            this.logger.error('CHECK-IN', `每日签到失败: ${error.message}`)
        }
    }

    /**
     * 提交每日签到请求
     * Script-4 变化：使用专用 UA（iPad Safari + BingSapphire 33.x）、AppId 升级、X-Rewards-IsMobile='true'
     */
    async _submitDailyCheckIn(type, oldBalance) {
        try {
            const jsonData = this._buildDapiActivityBody(type)

            // Script-4：使用每日签到专用请求头（UA 和 AppId 升级）
            const headers = {
                Authorization: `Bearer ${this.bot.accessToken}`,
                'User-Agent': DAILY_CHECKIN_USER_AGENT,
                'Content-Type': 'application/json',
                'X-Rewards-Country': this.bot.geoLocale,
                'X-Rewards-Language': 'zh',
                'X-Rewards-IsMobile': 'true',
                'X-Rewards-AppId': DAILY_CHECKIN_APP_ID,
                'X-Rewards-PartnerId': 'startapp',
                'X-Rewards-Flights': 'rwgobig',
                'Accept': '*/*'
            }

            const response = await this.bot.httpClient.request({
                url: URLS.platform.activities,
                method: 'POST',
                headers: headers,
                data: JSON.stringify(jsonData)
            })

            const newBalance = Number(response?.data?.response?.balance ?? oldBalance)
            const gained = newBalance - oldBalance
            if (gained > 0) {
                this.bot.currentPoints = newBalance
                this.bot.gainedPoints += gained
            }
            return gained
        } catch (error) {
            this.logger.error('CHECK-IN', `提交签到 (type=${type}) 失败: ${error.message}`)
            return 0
        }
    }

    /**
     * 领取奖励积分
     */
    async doClaimBonusPoints(data) {
        const pointsActivity = data.pointClaimBannerPromotion
        if (!pointsActivity) {
            this.logger.info('CLAIM-BONUS-POINTS', '未找到奖励积分横幅')
            return
        }
        if (pointsActivity.complete) {
            this.logger.info('CLAIM-BONUS-POINTS', `奖励积分已领取 | offerId=${pointsActivity.offerId}`)
            return
        }

        // Script-4：使用动态发现的 reportClaimAllPoints action id
        const actionId = this.bot.nextActions.reportClaimAllPoints
        if (!actionId) {
            this.logger.warn('CLAIM-BONUS-POINTS', '跳过：未发现 "reportClaimAllPoints" action id')
            return
        }

        const oldBalance = Number(this.bot.currentPoints ?? 0)
        this.logger.info('CLAIM-BONUS-POINTS', `开始领取奖励积分 | geo=${this.bot.geoLocale} | oldBalance=${oldBalance}`)

        try {
            // Script-4：调用 Server Action（body 为空数组）
            const { status, acknowledged } = await this.reportServerAction(actionId, [])

            const newBalance = await this.getCurrentPoints()
            const gainedPoints = newBalance - oldBalance

            this.logger.debug('CLAIM-BONUS-POINTS', `响应 | status=${status} | acknowledged=${acknowledged} | oldBalance=${oldBalance} | newBalance=${newBalance} | gainedPoints=${gainedPoints}`)

            if (acknowledged) {
                if (gainedPoints > 0) {
                    this.bot.currentPoints = newBalance
                    this.bot.gainedPoints += gainedPoints
                }
                this.logger.info('CLAIM-BONUS-POINTS', `领取完成 | acknowledged=true${gainedPoints > 0 ? ` | +${gainedPoints} 积分` : ''} | newBalance=${newBalance}`)
            } else {
                this.logger.info('CLAIM-BONUS-POINTS', `无可领取积分 | status=${status} | 余额不变: ${newBalance}`)
            }

            await wait(randomDelay(5000, 10000))
        } catch (error) {
            this.logger.error('CLAIM-BONUS-POINTS', `领取奖励积分失败: ${error.message}`)
        }
    }

    /**
     * 解决活动列表（URL 奖励类型）
     */
    async _solveActivities(activities, page, isMobile = true) {
        for (const activity of activities) {
            try {
                const type = activity.promotionType?.toLowerCase() || ''
                const offerId = activity.offerId
                this.logger.debug('ACTIVITY', `处理活动: ${activity.title} | type=${type} | offerId=${offerId}`)

                if (type === 'urlreward') {
                    await this._doUrlReward(activity, page, isMobile)
                } else if (type === 'quiz') {
                    this.logger.info('ACTIVITY', `测验活动（需浏览器交互）: ${activity.title}`)
                    // 测验活动需要复杂的浏览器交互，这里通过 URL 访问触发
                    if (activity.destinationUrl && page) {
                        await page.goto(activity.destinationUrl, { waitUntil: 'domcontentloaded' }).catch(() => {})
                        await wait(5000)
                    }
                } else {
                    this.logger.warn('ACTIVITY', `不支持的活动类型: ${type} | ${activity.title}`)
                }
                await wait(randomDelay(3000, 8000))
            } catch (error) {
                this.logger.error('ACTIVITY', `处理活动失败: ${error.message}`)
            }
        }
    }

    /**
     * 完成 URL 奖励活动（Script-4 方案：基于 Server Action + reactSnapshot）
     * 移植自 Script-4 UrlReward.ts
     * @param {object} promotion 活动对象
     * @param {object} page 浏览器页面（保留兼容，Server Action 方案不直接使用）
     * @param {boolean} isMobile 是否移动端（决定 cookies 和指纹头）
     */
    async _doUrlReward(promotion, page, isMobile = true) {
        const offerId = promotion.offerId

        // Script-4：使用动态发现的 reportActivity action id
        const actionId = this.bot.nextActions.reportActivity
        if (!actionId) {
            this.logger.warn('URL-REWARD', `跳过 ${offerId}: "reportActivity" action id 未发现`)
            return
        }

        // Script-4：从 reactSnapshot 中查找实时 hash
        const live = this.bot.reactSnapshot?.offers.find(o => o.offerId === offerId)
        if (!live) {
            this.logger.warn('URL-REWARD', `跳过 ${offerId}: 页面快照中未找到此活动`)
            return
        }
        if (!live.reportable) {
            this.logger.warn('URL-REWARD', `跳过 ${offerId}: 不可上报 (已完成/锁定/无hash/未来日期)`)
            return
        }

        // skipNonPointTasks：跳过 0 积分活动
        if (this.bot.config.workers?.skipNonPointTasks && this._isNonCrediting(live.points, live.promotionSubtype, live.title)) {
            this.logger.info('URL-REWARD', `跳过 ${offerId}: 无积分活动 (points=${live.points})`)
            return
        }

        const oldBalance = Number(this.bot.currentPoints ?? 0)
        const expectedPoints = live.points
        const activityType = Number(promotion.activityType ?? 11)

        this.logger.info('URL-REWARD', `开始 UrlReward | offerId=${offerId} | geo=${this.bot.geoLocale} | oldBalance=${oldBalance}`)

        try {
            // Script-4：调用 Server Action（而非 reportactivity API）
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [
                    live.hash,
                    activityType,
                    {
                        offerid: offerId,
                        isPromotional: live.isPromotional ? true : '$undefined',
                        timezoneOffset: this.bot.timezoneOffset
                    }
                ],
                {},
                isMobile
            )

            // Script-4 扩展：等待积分到账（Server Action 上报成功后积分可能有延迟）
            await wait(randomDelay(3000, 5000))
            let newBalance = await this.getCurrentPoints()
            let gainedPoints = newBalance - oldBalance

            // 如果第一次检查未获得积分，等待后重试一次（积分延迟到账的常见情况）
            if (gainedPoints <= 0 && acknowledged && expectedPoints > 0) {
                this.logger.debug('URL-REWARD', `首次检查未到账，等待重试 | offerId=${offerId} | acknowledged=${acknowledged}`)
                await wait(randomDelay(5000, 8000))
                newBalance = await this.getCurrentPoints()
                gainedPoints = newBalance - oldBalance
            }

            this.logger.debug('URL-REWARD', `响应 | offerId=${offerId} | status=${status} | acknowledged=${acknowledged} | gainedPoints=${gainedPoints}`)

            if (gainedPoints > 0) {
                this.bot.currentPoints = newBalance
                this.bot.gainedPoints += gainedPoints
                const shortfall = expectedPoints > 0 && gainedPoints < expectedPoints
                this.logger.success('URL-REWARD', `完成 UrlReward | offerId=${offerId} | +${gainedPoints}${expectedPoints > 0 ? `/${expectedPoints}` : ''} 积分${shortfall ? ' | 警告: 实际积分少于预期' : ''}`)
            } else if (acknowledged && expectedPoints === 0) {
                this.logger.info('URL-REWARD', `完成 UrlReward (无积分活动) | offerId=${offerId} | acknowledged=true`)
            } else {
                this.logger.warn('URL-REWARD', `UrlReward 未获得积分 | offerId=${offerId} | acknowledged=${acknowledged} | expected=${expectedPoints}`)
            }

            await wait(randomDelay(5000, 10000))
        } catch (error) {
            this.logger.error('URL-REWARD', `doUrlReward 错误 | offerId=${offerId} | ${error.message}`)
        }
    }

    /**
     * 判断活动是否无积分（free trial / subscription 等）
     */
    _isNonCrediting(points, subtype, title) {
        if (points > 0) return false
        const haystack = `${subtype ?? ''} ${title ?? ''}`.toLowerCase()
        return points === 0 || /free trial|trial|subscription|sign up|sign-up|signup/.test(haystack)
    }

    /**
     * Read to Earn - 阅读文章赚积分（通过 App API）
     * 每次阅读 +3 积分，最多 10 次 = +30 积分
     */
    async doReadToEarn() {
        if (!this.bot.accessToken) {
            this.logger.warn('READ-TO-EARN', '跳过：应用访问令牌不可用，此活动需要它！')
            return
        }

        const startBalance = Number(this.bot.currentPoints ?? 0)
        const delayMin = this.bot.config.search.searchDelayMin || 30000
        const delayMax = this.bot.config.search.searchDelayMax || 60000

        this.logger.info('READ-TO-EARN', `开始 Read to Earn | 地区: ${this.bot.geoLocale} | 延迟: ${delayMin}-${delayMax}ms | 当前积分: ${startBalance}`)

        try {
            const articleCount = 10
            let totalGained = 0
            let articlesRead = 0
            let oldBalance = startBalance

            for (let i = 0; i < articleCount; i++) {
                try {
                    // 每次生成新的随机 id
                    const jsonData = {
                        amount: 1,
                        id: crypto.randomBytes(64).toString('hex'),
                        type: 101,
                        attributes: {
                            offerid: 'ENUS_readarticle3_30points'
                        },
                        country: this.bot.geoLocale
                    }

                    const response = await this.bot.httpClient.request({
                        url: URLS.platform.activities,
                        method: 'POST',
                        headers: {
                            Authorization: `Bearer ${this.bot.accessToken}`,
                            'User-Agent': DAPI_USER_AGENT,
                            'Content-Type': 'application/json',
                            'X-Rewards-Country': this.bot.geoLocale,
                            // Script-4：Language 从 en 改为 zh
                            'X-Rewards-Language': 'zh',
                            'X-Rewards-ismobile': 'true'
                        },
                        data: JSON.stringify(jsonData)
                    })

                    const newBalance = Number(response?.data?.response?.balance ?? oldBalance)
                    const gainedPoints = newBalance - oldBalance

                    if (gainedPoints <= 0) {
                        this.logger.info('READ-TO-EARN', `无积分获得，停止阅读 | 文章 ${i + 1}/${articleCount} | 旧积分: ${oldBalance} | 新积分: ${newBalance}`)
                        break
                    }

                    // 更新积分跟踪
                    this.bot.currentPoints = newBalance
                    this.bot.gainedPoints += gainedPoints
                    totalGained += gainedPoints
                    articlesRead = i + 1
                    oldBalance = newBalance

                    this.logger.success('READ-TO-EARN', `阅读文章 ${i + 1}/${articleCount} | +${gainedPoints} 积分 | 新积分: ${newBalance}`)

                    // 文章间随机延迟
                    if (i < articleCount - 1) {
                        await wait(randomDelay(delayMin, delayMax))
                    }
                } catch (error) {
                    this.logger.error('READ-TO-EARN', `阅读文章 ${i + 1} 失败: ${error.message}`)
                    break
                }
            }

            const finalBalance = Number(this.bot.currentPoints ?? startBalance)
            this.logger.info('READ-TO-EARN', `Read to Earn 完成 | 阅读数: ${articlesRead} | 总获得: +${totalGained} | 起始: ${startBalance} | 最终: ${finalBalance}`)
        } catch (error) {
            this.logger.error('READ-TO-EARN', `Read to Earn 错误: ${error.message}`)
        }
    }

    /**
     * 完成 Punch Card（打卡任务）- Script-4 方案：基于 RSC 解析 + Server Action
     * 移植自 Script-4 Workers.doPunchCards
     *
     * 通过 /earn 页面 RSC 解析获取 parent quest 列表，
     * 通过 /earn/quest/{id} 页面解析子任务（pcchildren），
     * 用 Server Action 上报（而非 reportactivity API）。
     *
     * @param {object} data 仪表盘数据（用于补充 API 数据）
     * @param {object} page 浏览器页面（用于获取 /earn 和 /quest HTML）
     * @param {boolean} isMobile 是否移动端（决定 cookies 和指纹头）
     */
    async doPunchCards(data, page, isMobile = true) {
        let parents = []

        // Script-4：通过 /earn 页面 RSC 解析获取 parent quest 列表
        try {
            const earn = await page.request.get(URLS.rewards.earn)
            if (!earn.ok()) {
                this.logger.warn('PUNCHCARD', `/earn ${earn.status()} - 无法获取 quest 列表`)
                return
            }
            const html = await earn.text()
            parents = this.bot.reactParser.snapshotQuestList(html)

            // 某些部署只在 /dashboard 渲染轮播
            if (!parents.length) {
                const dash = await page.request.get(URLS.rewards.dashboard)
                if (dash.ok()) {
                    parents = this.bot.reactParser.snapshotQuestList(html, await dash.text())
                }
            }
        } catch (error) {
            this.logger.warn('PUNCHCARD', `获取 /earn quest 列表失败: ${error.message}`)
            return
        }

        // 合并 API 数据中的 parent quests（补充 RSC 未渲染的）
        const apiById = new Map(
            (data.punchCards || [])
                .filter(c => c.parentPromotion?.offerId)
                .map(c => [c.parentPromotion.offerId, c])
        )
        const seen = new Set(parents.map(p => p.offerId))
        for (const card of apiById.values()) {
            const pp = card.parentPromotion
            if (!pp?.offerId || seen.has(pp.offerId)) continue
            parents.push({
                offerId: pp.offerId,
                title: pp.title ?? '',
                pointProgressMax: pp.pointProgressMax ?? 0,
                complete: !!pp.complete
            })
            seen.add(pp.offerId)
        }

        // 补充 pointProgressMax
        for (const p of parents) {
            if (p.pointProgressMax <= 0) {
                p.pointProgressMax = apiById.get(p.offerId)?.parentPromotion?.pointProgressMax ?? p.pointProgressMax
            }
        }

        const skipNonPointTasks = this.bot.config.workers?.skipNonPointTasks === true
        const incomplete = parents.filter(p => {
            if (p.complete) return false
            if (skipNonPointTasks && p.pointProgressMax <= 0) return false
            return true
        })

        if (!incomplete.length) {
            this.logger.info('PUNCHCARD', '无可执行的 quest')
            return
        }

        this.logger.info('PUNCHCARD', `在 /earn 上发现 ${incomplete.length} 个未完成的 quest | api 匹配=${incomplete.filter(p => apiById.has(p.offerId)).length}`)

        for (const parent of incomplete) {
            try {
                await this._solvePunchCard(parent, apiById.get(parent.offerId), page, isMobile)
            } catch (error) {
                this.logger.error('PUNCHCARD', `解决 quest "${parent.title || parent.offerId}" 错误: ${error.message}`)
            }
        }

        this.logger.info('PUNCHCARD', 'Quest 处理完成')
    }

    /**
     * 解决单个 Punch Card - 移植自 Script-4 Workers.solvePunchCard
     * 通过 /earn/quest/{id} 页面解析子任务，用 Server Action 上报
     */
    async _solvePunchCard(parent, apiCard, page, isMobile = true) {
        const parentId = parent.offerId
        const title = parent.title || apiCard?.parentPromotion?.title || parentId

        // 通过 /earn/quest/{id} 页面解析子任务
        let questChildren = []
        try {
            const res = await page.request.get(URLS.rewards.quest(parentId))
            if (!res.ok()) {
                this.logger.warn('PUNCHCARD', `Quest 页面 ${res.status()} - "${title}" - 跳过`)
                return
            }
            questChildren = this.bot.reactParser.snapshotQuestPage(await res.text())
        } catch (error) {
            this.logger.warn('PUNCHCARD', `获取 quest 页面失败 "${title}": ${error.message}`)
            return
        }

        if (!questChildren.length) {
            this.logger.info('PUNCHCARD', `"${title}" 无可执行的子任务`)
            return
        }

        // 按 API priority 排序
        const apiChildById = new Map(
            (apiCard?.childPromotions || []).filter(c => c.offerId).map(c => [c.offerId, c])
        )
        const ordered = [...questChildren].sort((a, b) =>
            (apiChildById.get(a.offerId)?.priority ?? Number.MAX_SAFE_INTEGER) -
            (apiChildById.get(b.offerId)?.priority ?? Number.MAX_SAFE_INTEGER)
        )

        this.logger.info('PUNCHCARD', `解决 "${title}" | children=${ordered.length} | reportable=${ordered.filter(c => c.reportable).length}`)

        const startBalance = Number(this.bot.currentPoints ?? 0)
        let reported = 0
        let remaining = 0

        for (const child of ordered) {
            const offerId = child.offerId
            const api = apiChildById.get(offerId)

            if (!child.reportable) {
                remaining++
                this.logger.debug('PUNCHCARD', `跳过 ${offerId}: 不可上报 (locked=${child.isLocked} disabled=${child.isDisabled} done=${child.isCompleted} hash=${!!child.hash})`)
                continue
            }

            // 跳过多日搜索任务
            if (this._isSearchQuotaChild(offerId, api)) {
                remaining++
                this.logger.info('PUNCHCARD', `跳过 ${offerId}: 多日搜索任务`)
                continue
            }

            // 领取奖励类子任务
            if (this._isClaimChild(offerId, api)) {
                const autoClaim = this.bot.config.workers?.autoClaimPunchcardRewards !== false
                if (!autoClaim) {
                    remaining++
                    this.logger.info('PUNCHCARD', `"${title}" 奖励待领取（autoClaimPunchcardRewards=false）| ${offerId}`)
                    continue
                }
                await this._doClaimReward(child, parentId, page, isMobile)
                reported++
                continue
            }

            // 上报子任务
            await this._reportQuestChild(child, parentId, page, isMobile)
            reported++
            await wait(randomDelay(5000, 15000))
        }

        const gained = Number(this.bot.currentPoints ?? 0) - startBalance
        this.logger.info('PUNCHCARD', `Quest "${title}" ${remaining === 0 ? '完成' : '进行中'} | reported=${reported}${remaining ? ` | remaining=${remaining}` : ''} | +${gained}${parent.pointProgressMax > 0 ? `/${parent.pointProgressMax}` : ''} 积分`,
            gained > 0 ? 'success' : undefined)
    }

    /**
     * 上报 quest 子任务 - 移植自 Script-4 Workers.reportQuestChild
     * 用 Server Action 而非 reportactivity API
     */
    async _reportQuestChild(child, parentId, page, isMobile = true) {
        const offerId = child.offerId
        const actionId = this.bot.nextActions.reportActivity
        if (!actionId) {
            this.logger.warn('PUNCHCARD', `跳过 ${offerId}: "reportActivity" action id 未发现`)
            return
        }
        if (!child.hash) {
            this.logger.warn('PUNCHCARD', `跳过 ${offerId}: quest child 无实时 hash`)
            return
        }

        const oldBalance = Number(this.bot.currentPoints ?? 0)
        try {
            const questUrl = URLS.rewards.quest(parentId)
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [
                    child.hash,
                    11,
                    { offerid: offerId, isPromotional: '$undefined', timezoneOffset: this.bot.timezoneOffset }
                ],
                {
                    url: questUrl,
                    referer: questUrl,
                    routerStateTree: this.bot.reactParser.questRouterStateTree(parentId)
                },
                isMobile
            )

            const newBalance = await this.getCurrentPoints()
            const gained = newBalance - oldBalance
            if (gained > 0) {
                this.bot.currentPoints = newBalance
                this.bot.gainedPoints += gained
            }

            this.logger.info('PUNCHCARD', `上报 child | offerId=${offerId} | status=${status} | acknowledged=${acknowledged}${gained > 0 ? ` | +${gained} 积分` : ''}`,
                gained > 0 || acknowledged ? 'success' : undefined)
        } catch (error) {
            this.logger.error('PUNCHCARD', `上报 child 错误 | offerId=${offerId} | ${error.message}`)
        }
    }

    /**
     * 领取 quest 奖励 - 移植自 Script-4 ClaimReward.claimReward
     * 用 Server Action 领取 punchcard 父任务奖励
     */
    async _doClaimReward(child, parentId, page, isMobile = true) {
        const offerId = child.offerId
        const actionId = this.bot.nextActions.reportActivity
        if (!actionId) {
            this.logger.warn('CLAIM-REWARD', `跳过 ${offerId}: "reportActivity" action id 未发现`)
            return
        }
        if (!child.hash) {
            this.logger.warn('CLAIM-REWARD', `跳过 ${offerId}: 无实时 hash`)
            return
        }
        if (!child.reportable) {
            this.logger.warn('CLAIM-REWARD', `跳过 ${offerId}: 不可上报 (已完成/锁定/禁用)`)
            return
        }

        const oldBalance = Number(this.bot.currentPoints ?? 0)
        this.logger.info('CLAIM-REWARD', `领取奖励 | offerId=${offerId} | geo=${this.bot.geoLocale}`)

        try {
            const questUrl = URLS.rewards.quest(parentId)
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [
                    child.hash,
                    11,
                    { offerid: offerId, isPromotional: '$undefined', timezoneOffset: this.bot.timezoneOffset }
                ],
                {
                    url: questUrl,
                    referer: questUrl,
                    routerStateTree: this.bot.reactParser.questRouterStateTree(parentId)
                },
                isMobile
            )

            const newBalance = await this.getCurrentPoints()
            const gained = newBalance - oldBalance

            if (acknowledged) {
                if (gained > 0) {
                    this.bot.currentPoints = newBalance
                    this.bot.gainedPoints += gained
                }
                this.logger.success('CLAIM-REWARD', `奖励已领取 | offerId=${offerId} | status=${status}${gained > 0 ? ` | +${gained} 积分` : ''}`)
            } else {
                this.logger.warn('CLAIM-REWARD', `奖励未被服务器确认 | offerId=${offerId} | status=${status}`)
            }

            await wait(randomDelay(5000, 10000))
        } catch (error) {
            this.logger.error('CLAIM-REWARD', `领取奖励错误 | offerId=${offerId} | ${error.message}`)
        }
    }

    /**
     * 判断是否为多日搜索任务 - 移植自 Script-4 Workers.isSearchQuotaChild
     */
    _isSearchQuotaChild(offerId, api) {
        if (api) {
            const type = (api.promotionType ?? '').toLowerCase()
            const attrType = String(api.attributes?.type ?? '').toLowerCase()
            const progressMax = Number(api.activityProgressMax ?? 0)
            if (type === 'search' || attrType === 'search' || progressMax > 1) return true
        }
        return /search/i.test(offerId) && /(day|streak|\dx)/i.test(offerId)
    }

    /**
     * 判断是否为领取奖励类子任务 - 移植自 Script-4 Workers.isClaimChild
     */
    _isClaimChild(offerId, api) {
        const dest = (api?.destinationUrl ?? '').toLowerCase()
        if (/\/redeem\//.test(dest)) return true
        return /(redeem|claim|(?<!url)reward)/i.test(offerId)
    }

    /**
     * 完成 App 促销活动
     */
    async doAppPromotions(appData) {
        const appRewards = (appData?.response?.promotions || []).filter(x => {
            if (x.attributes?.complete?.toLowerCase() !== 'false') return false
            if (!x.attributes?.offerid) return false
            if (!x.attributes?.type) return false
            if (x.attributes.type !== 'sapphire') return false
            return true
        })

        if (!appRewards.length) {
            this.logger.info('APP-PROMOTIONS', '所有"App 促销"已完成')
            return
        }

        this.logger.info('APP-PROMOTIONS', `开始处理 ${appRewards.length} 个"App 促销"`)

        for (const reward of appRewards) {
            try {
                const offerId = reward.attributes.offerid
                const oldBalance = Number(this.bot.currentPoints ?? 0)

                const jsonData = this._buildDapiActivityBody(101, { offerid: offerId })

                const response = await this.bot.httpClient.request({
                    url: 'https://prod.rewardsplatform.microsoft.com/dapi/me/activities',
                    method: 'POST',
                    headers: this._buildDapiHeaders(true),
                    data: JSON.stringify(jsonData)
                })

                const newBalance = Number(response?.data?.response?.balance ?? oldBalance)
                const gained = newBalance - oldBalance
                if (gained > 0) {
                    this.bot.currentPoints = newBalance
                    this.bot.gainedPoints += gained
                    this.logger.success('APP-PROMOTIONS', `完成 ${offerId} | +${gained} 积分`)
                } else {
                    this.logger.warn('APP-PROMOTIONS', `完成 ${offerId} 但未获得积分`)
                }
                oldBalance = newBalance

                await wait(randomDelay(5000, 15000))
            } catch (error) {
                this.logger.error('APP-PROMOTIONS', `App 促销失败: ${error.message}`)
            }
        }

        this.logger.info('APP-PROMOTIONS', '"App 促销"全部完成')
    }

    /**
     * 检测搜索积分倍数特权（Script-4 detectSearchMultiplierPerk）
     * 三种识别方式：
     *   1. attributes.searchMultiplier 数值 > 1
     *   2. description 正则 /search\s*(\d+)\s*x\s*more/i
     *   3. offerId 正则 /optin[_-]?(\d+)x(?:[_-]|$)/i
     * @param {object} dashboard 仪表盘数据
     * @returns {{offerId: string, multiplier: number}|null}
     */
    _detectSearchMultiplierPerk(dashboard) {
        const candidates = [dashboard.promotionalItem, ...(dashboard.promotionalItems || [])]
        for (const item of candidates) {
            if (!item) continue
            const attributes = item.attributes || {}
            const offerId = item.offerId || attributes.offerid || ''
            const description = item.description || attributes.description || ''
            if (!offerId) continue

            const multiplierAttr = attributes.searchMultiplier
            const multiplierFromAttr = multiplierAttr != null ? Number(multiplierAttr) : NaN
            const fromDescription = /search\s*(\d+)\s*x\s*more/i.exec(description)
            const fromOfferId = /optin[_-]?(\d+)x(?:[_-]|$)/i.exec(offerId)

            const isSearchMultiplier =
                (Number.isFinite(multiplierFromAttr) && multiplierFromAttr > 1) ||
                fromDescription !== null ||
                fromOfferId !== null
            if (!isSearchMultiplier) continue

            const multiplier =
                Number.isFinite(multiplierFromAttr) && multiplierFromAttr > 1
                    ? multiplierFromAttr
                    : fromDescription
                      ? Number(fromDescription[1])
                      : fromOfferId
                        ? Number(fromOfferId[1])
                        : 2
            return { offerId, multiplier }
        }
        return null
    }

    /**
     * 激活搜索积分倍数特权（Script-4 ActivateSearchPerk.activate）
     * 移植自 Script-4 ActivateSearchPerk.ts
     * - 从 reactSnapshot 查找 live offer（含 hash）
     * - 检查 live.reportable 判断是否可激活
     * - 通过 reportServerAction 调用（isPromotional: 'true'）
     * @param {object} data 仪表盘数据
     * @param {object} page 浏览器页面（保留兼容，移动端阶段调用）
     */
    async doActivateSearchPerk(data, page) {
        const perk = this._detectSearchMultiplierPerk(data)
        if (!perk) {
            this.logger.debug('ACTIVATE-SEARCH-PERK', '未发现搜索积分倍数特权')
            return
        }

        // Script-4：从 reactSnapshot 查找 live offer（含实时 hash）
        const live = this.bot.reactSnapshot?.offers.find(o => o.offerId === perk.offerId)
        if (!live) {
            this.logger.warn('ACTIVATE-SEARCH-PERK', `${perk.multiplier}x 搜索特权存在于仪表盘但页面快照中未找到 - 无法激活 | offerId=${perk.offerId}`)
            return
        }

        if (!live.reportable) {
            this.logger.info('ACTIVATE-SEARCH-PERK', `${perk.multiplier}x 搜索特权已激活（或不可激活） | offerId=${perk.offerId}`)
            return
        }

        // Script-4：使用动态发现的 reportActivity action id
        const actionId = this.bot.nextActions.reportActivity
        if (!actionId) {
            this.logger.warn('ACTIVATE-SEARCH-PERK', '跳过：未发现 "reportActivity" action id')
            return
        }

        const activityType = Number(live.activityType ?? 11)

        this.logger.info('ACTIVATE-SEARCH-PERK', `激活 ${perk.multiplier}x 搜索特权 | offerId=${perk.offerId} | geo=${this.bot.geoLocale}`)

        try {
            // Script-4：直接调用 Server Action（isPromotional: 'true' 字符串）
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [
                    live.hash,
                    activityType,
                    {
                        offerid: perk.offerId,
                        isPromotional: 'true',
                        timezoneOffset: this.bot.timezoneOffset
                    }
                ]
            )

            this.logger.debug('ACTIVATE-SEARCH-PERK', `响应 | offerId=${perk.offerId} | status=${status} | acknowledged=${acknowledged}`)

            if (acknowledged) {
                this.logger.info('ACTIVATE-SEARCH-PERK', `已激活 ${perk.multiplier}x 搜索特权 | offerId=${perk.offerId} | 每日搜索上限已提升`)
            } else {
                this.logger.warn('ACTIVATE-SEARCH-PERK', `激活未确认 | offerId=${perk.offerId} | status=${status}`)
            }

            await wait(randomDelay(5000, 10000))
        } catch (error) {
            this.logger.error('ACTIVATE-SEARCH-PERK', `激活搜索特权失败 | offerId=${perk.offerId} | ${error.message}`)
        }
    }

    /**
     * 完成特殊促销活动（旧版兼容入口，已迁移至 doActivateSearchPerk）
     * @deprecated 保留以兼容旧配置，内部转发到 doActivateSearchPerk
     */
    async doSpecialPromotions(data, page) {
        await this.doActivateSearchPerk(data, page)
    }

    /**
     * 视觉搜索任务（Script-4 VisualSearch）
     * - 仅桌面端执行
     * - 检查 streak 是否已完成 → 激活 offer → kblob 获取 bcid → 访问 SERP 获取 IG → /rewardsapp/reportActivity 上报
     * 移植自 Script-4 VisualSearch.ts + BrowserFunc.acquireVisualSearch/reportVisualSearchActivity
     * @param {object} page 浏览器页面
     * @returns {Promise<number>} 获得的积分
     */
    async doVisualSearch(page) {
        if (!page) {
            this.logger.warn('VISUAL-SEARCH', '跳过：缺少浏览器页面')
            return 0
        }

        const VISUAL_SEARCH_IMAGE_URL = 'https://th.bing.com/th?id=OMR.VisualSearch.VNext.BackgroundImage.png&pid=Rewards'
        const VISUAL_SEARCH_ACTIVATION_OFFER = 'visualsearch_streak_activation_v2'
        const VISUAL_SEARCH_ACTIVITY_TYPE = 714
        const MAX_ATTEMPTS = 3

        this.logger.info('VISUAL-SEARCH', '开始视觉搜索任务（桌面端）')

        // Script-4：检查 visual search streak 是否今日已完成
        const streaks = this.bot.reactSnapshot?.streaks ?? []
        const streak = streaks.find(s => /visual.?search/i.test(s.partner))
        if (streak?.isCurrentDayCompleted) {
            this.logger.info('VISUAL-SEARCH', `今日已完成 | streak day ${streak.completedDays}/${streak.totalDays}`)
            return 0
        }

        // Script-4：激活 visual search offer（若需要）
        const activation = await this._activateVisualSearchOffer(page, VISUAL_SEARCH_ACTIVATION_OFFER, VISUAL_SEARCH_ACTIVITY_TYPE)
        const available = !!streak || activation === 'activated' || activation === 'already-active'
        if (!available) {
            this.logger.info('VISUAL-SEARCH', '此账户无视觉搜索活动，跳过')
            return 0
        }

        // Script-4：构建 bing cookie jar（从桌面端 cookies）
        const jar = this._getBingJar()

        let totalGained = 0
        for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                // 1. 通过 /images/kblob 获取 bcid
                const visual = await this._acquireVisualSearch(page, jar, VISUAL_SEARCH_IMAGE_URL)
                if (!visual) {
                    this.logger.warn('VISUAL-SEARCH', `无法获取 visual search (尝试 ${attempt}/${MAX_ATTEMPTS})`)
                    await wait(randomDelay(3000, 6000))
                    continue
                }

                // 2. 访问 SERP + 上报 reportActivity
                const res = await this._reportVisualSearchActivity(jar, visual)
                if (res.balance != null) this.bot.currentPoints = res.balance

                const gained = res.gained ?? 0
                if (gained > 0) {
                    this.bot.gainedPoints += gained
                    totalGained += gained
                    this.logger.success('VISUAL-SEARCH', `视觉搜索完成 | +${gained} 积分 | query="${visual.query}" | balance=${res.balance}`)
                    return totalGained
                }

                if (res.ig) {
                    this.logger.info('VISUAL-SEARCH', `已上报但无新积分 | query="${visual.query}" | 可能今日已完成`)
                    return 0
                }

                this.logger.warn('VISUAL-SEARCH', `上报无 IG (尝试 ${attempt}/${MAX_ATTEMPTS}) - 使用新图片重试`)
                await wait(randomDelay(3000, 6000))
            } catch (error) {
                this.logger.error('VISUAL-SEARCH', `视觉搜索失败 (尝试 ${attempt}/${MAX_ATTEMPTS}): ${error.message}`)
                await wait(randomDelay(3000, 6000))
            }
        }

        this.logger.warn('VISUAL-SEARCH', `视觉搜索 ${MAX_ATTEMPTS} 次尝试后未获得积分`)
        return totalGained
    }

    /**
     * Script-4 VisualSearch.activate：激活 visual search offer
     */
    async _activateVisualSearchOffer(page, activationOfferId, activityType) {
        const offers = this.bot.reactSnapshot?.offers ?? []
        const offer = offers.find(o => o.offerId === activationOfferId) ??
            offers.find(o => {
                const id = o.offerId.toLowerCase()
                return id.includes('visualsearch') && id.includes('activation')
            })

        if (!offer) {
            this.logger.debug('VISUAL-SEARCH', '仪表盘上无 visual search 激活 offer')
            return 'absent'
        }
        if (!offer.reportable) {
            this.logger.info('VISUAL-SEARCH', `visual search 已激活 | offerId=${offer.offerId}`)
            return 'already-active'
        }
        if (!offer.hash) {
            this.logger.warn('VISUAL-SEARCH', `激活 offer 存在但缺少 hash | offerId=${offer.offerId}`)
            return 'failed'
        }

        const actionId = this.bot.nextActions.reportActivity
        if (!actionId) {
            this.logger.warn('VISUAL-SEARCH', '跳过激活：未发现 reportActivity action id')
            return 'failed'
        }

        this.logger.info('VISUAL-SEARCH', `激活 visual search | offerId=${offer.offerId}`)
        try {
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [offer.hash, activityType, { offerid: offer.offerId, isPromotional: '$undefined', timezoneOffset: this.bot.timezoneOffset }],
                {},
                false
            )
            if (acknowledged) {
                this.logger.info('VISUAL-SEARCH', `已激活 | offerId=${offer.offerId} | status=${status}`)
                await wait(randomDelay(5000, 10000))
                return 'activated'
            }
            this.logger.warn('VISUAL-SEARCH', `激活未确认 | status=${status}`)
            return 'failed'
        } catch (error) {
            this.logger.error('VISUAL-SEARCH', `激活失败 | ${error.message}`)
            return 'failed'
        }
    }

    /**
     * Script-4 BrowserFunc.acquireVisualSearch：通过 kblob 获取 bcid
     * 增加 session 初始化 fallback：httpClient 返回 400 时先访问 /visualsearch 页面初始化 bing session，
     * 然后通过 page.request 重试（浏览器内请求自动携带完整新鲜 cookies）
     */
    async _acquireVisualSearch(page, jar, imageUrl) {
        try {
            const enc = encodeURIComponent(imageUrl)
            const url = `${URLS.bing.origin}/images/kblob?iss=sbi&form=SBIHMP&sbisrc=UrlPaste&vsimg=${enc}&imgurl=${enc}`

            const boundary = `----WebKitFormBoundary${crypto.randomBytes(8).toString('hex')}`
            const body = this._buildMultipart(boundary, [
                { name: 'cbir', value: 'sbi' },
                { name: 'imageBin', value: '' },
                { name: 'imgurl', value: '' }
            ])

            const baseHeaders = { ...FINGERPRINT_HEADERS_DESKTOP }
            delete baseHeaders['Cookie']
            delete baseHeaders['cookie']

            const requestHeaders = {
                ...baseHeaders,
                Cookie: this._jarToHeader(jar),
                Accept: 'application/json',
                'Content-Type': `multipart/form-data; boundary=${boundary}`,
                Referer: `${URLS.bing.origin}/visualsearch`,
                Origin: URLS.bing.origin,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin'
            }

            // 优先使用 httpClient（Script-4 原始方式）
            let res
            try {
                res = await this.bot.httpClient.request({
                    url,
                    method: 'POST',
                    headers: requestHeaders,
                    data: body
                })
            } catch (httpError) {
                // 提取 axios 400 错误的响应数据（用于诊断 kblob 拒绝原因）
                const errStatus = httpError.response?.status ?? 400
                const errData = httpError.response?.data ?? ''
                this.logger.warn('VISUAL-SEARCH', `kblob httpClient 异常 | status=${errStatus} | response: ${String(errData).slice(0, 300)}`)
                res = { status: errStatus, data: typeof errData === 'string' ? errData : JSON.stringify(errData), headers: httpError.response?.headers ?? {} }
            }

            // Script-4 扩展：httpClient 返回 400 时，通过浏览器上下文重试
            // （Script-4 使用 Impit 库模拟浏览器 TLS 指纹，Script-3 使用 axios 被 kblob API 拒绝；
            //   page.evaluate(XMLHttpRequest + FormData) 完全使用浏览器网络栈）
            // 关键：Script-4 使用 cn.bing.com（不是 www.bing.com），中国地区账户必须使用 cn.bing.com
            if (res.status === 400 && page && !page.isClosed()) {
                this.logger.info('VISUAL-SEARCH', 'kblob 返回 400，通过浏览器上下文重试')

                // 导航到 cn.bing.com/visualsearch 初始化 session 并设置正确的 Referer
                // Script-4 Referer: ${URLs.bing.origin}/visualsearch = https://cn.bing.com/visualsearch
                try {
                    await page.goto(`${URLS.bing.origin}/visualsearch`, {
                        waitUntil: 'domcontentloaded',
                        timeout: 15000
                    }).catch(() => {})
                    await wait(2000)
                    this.logger.info('VISUAL-SEARCH', `已导航到 visual search 页面 | hostname=${new URL(page.url()).hostname}`)
                } catch {
                    // 忽略导航错误
                }

                // 通过 page.evaluate(XMLHttpRequest) 在浏览器上下文中发送 kblob 请求
                // 使用手动构建的 multipart body（与 Script-4 buildMultipart 完全一致）
                // 而非 FormData API（FormData 生成的 boundary 格式可能不被 kblob API 接受）
                try {
                    const evalResult = await page.evaluate((params) => {
                        return new Promise((resolve) => {
                            const xhr = new XMLHttpRequest()
                            xhr.open('POST', params.url)
                            xhr.withCredentials = true
                            xhr.timeout = 15000
                            // 手动设置 Content-Type（与 Script-4 一致的 boundary 格式）
                            xhr.setRequestHeader('Accept', 'application/json')
                            xhr.setRequestHeader('Content-Type', `multipart/form-data; boundary=${params.boundary}`)
                            xhr.onload = () => resolve({ status: xhr.status, data: xhr.responseText })
                            xhr.onerror = () => resolve({ status: 0, data: 'XHR onerror (network/CORS)' })
                            xhr.ontimeout = () => resolve({ status: 0, data: 'XHR timeout' })
                            // 发送手动构建的 multipart body（与 Script-4 buildMultipart 一致）
                            xhr.send(params.body)
                        })
                    }, { url, body, boundary })

                    res = {
                        status: evalResult.status,
                        data: evalResult.data,
                        headers: {}
                    }

                    if (res.status === 0) {
                        this.logger.warn('VISUAL-SEARCH', `浏览器 XHR 失败: ${res.data}`)
                    } else if (res.status === 400) {
                        this.logger.warn('VISUAL-SEARCH', `浏览器 XHR 仍返回 400 | response: ${String(res.data).slice(0, 500)}`)
                    } else {
                        this.logger.info('VISUAL-SEARCH', `浏览器 XHR 成功 | status=${res.status}`)
                    }
                } catch (retryError) {
                    this.logger.warn('VISUAL-SEARCH', `page.evaluate(XHR) 异常: ${retryError.message}`)
                }
            }

            this._mergeSetCookies(jar, res.headers?.['set-cookie'])

            const redirectUrl = this._parseKblobRedirect(res.data)
            if (!redirectUrl) {
                const dump = typeof res.data === 'string' ? res.data : JSON.stringify(res.data ?? '')
                this.logger.warn('VISUAL-SEARCH', `kblob 未返回 redirectUrl | status=${res.status}`)
                this.logger.debug('VISUAL-SEARCH', `kblob response: ${dump.slice(0, 400)}`)

                // 最终 fallback：通过浏览器页面操作完成 visual search（上传图片 → 等待结果 → 提取 bcid）
                // 完全模拟真实用户行为，浏览器自动处理 kblob 请求（TLS 指纹 + cookies + session）
                if (page && !page.isClosed()) {
                    const uploadResult = await this._acquireVisualSearchViaUpload(page, imageUrl)
                    if (uploadResult) return uploadResult
                }
                return null
            }

            const qs = new URLSearchParams(redirectUrl.split('?')[1] ?? '')
            const bcid = qs.get('bcid')
            if (!bcid) {
                this.logger.warn('VISUAL-SEARCH', `重定向 URL 中无 bcid: ${redirectUrl}`)
                return null
            }
            const query = qs.get('q') ?? ''
            const serpUrl = `${URLS.bing.origin}${redirectUrl}`

            this.logger.info('VISUAL-SEARCH', `获取 bcid=${bcid.slice(0, 14)} | q="${query}" | status=${res.status}`)
            return { bcid, query, serpUrl }
        } catch (error) {
            this.logger.warn('VISUAL-SEARCH', `获取 visual search 失败: ${error.message}`)
            return null
        }
    }

    /**
     * 最终 fallback：通过浏览器页面操作完成 visual search
     * 下载图片 → 导航到 /visualsearch → setInputFiles 上传 → 等待搜索结果 → 提取 bcid
     * 完全模拟真实用户行为，浏览器自动处理 kblob 请求
     */
    async _acquireVisualSearchViaUpload(page, imageUrl) {
        try {
            this.logger.info('VISUAL-SEARCH', '通过浏览器文件上传方式获取 visual search')

            // 1. 下载图片到 Buffer（通过 httpClient）
            let imageBuffer
            try {
                const imgRes = await this.bot.httpClient.request({
                    url: imageUrl,
                    method: 'GET',
                    headers: { ...FINGERPRINT_HEADERS_DESKTOP },
                    responseType: 'arraybuffer',
                    timeout: 15000
                })
                imageBuffer = Buffer.from(imgRes.data)
                this.logger.debug('VISUAL-SEARCH', `图片下载成功 | size=${imageBuffer.length} bytes`)
            } catch (imgError) {
                this.logger.warn('VISUAL-SEARCH', `图片下载失败: ${imgError.message}`)
                return null
            }

            // 2. 导航到 cn.bing.com/visualsearch
            await page.goto(`${URLS.bing.origin}/visualsearch`, {
                waitUntil: 'load',
                timeout: 20000
            }).catch(() => {})
            await wait(3000)
            this.logger.info('VISUAL-SEARCH', `已导航到 visual search 页面 | url=${page.url().slice(0, 80)}`)

            // 3. 找到文件上传 input 并上传图片
            // bing.com/visualsearch 页面通常有 input[type="file"] 用于图片上传
            let fileInput = null
            try {
                fileInput = page.locator('input[type="file"]').first()
                const exists = await fileInput.count()
                if (exists === 0) {
                    this.logger.warn('VISUAL-SEARCH', 'visual search 页面未找到 input[type="file"]')
                    return null
                }
            } catch {
                this.logger.warn('VISUAL-SEARCH', '查找文件上传 input 失败')
                return null
            }

            // 4. 上传图片
            await fileInput.setInputFiles({
                name: 'visual_search.png',
                mimeType: 'image/png',
                buffer: imageBuffer
            })
            this.logger.info('VISUAL-SEARCH', '已上传图片，等待搜索结果...')

            // 5. 等待搜索结果页面加载（URL 变化，通常包含 /images/search 或 bcid）
            try {
                await page.waitForURL(url => {
                    const u = url.toString()
                    return u.includes('bcid=') || u.includes('/images/search') || u.includes('/visualsearch/preview')
                }, { timeout: 20000 })
            } catch {
                // 等待 URL 变化超时，检查当前 URL 是否包含 bcid
                this.logger.warn('VISUAL-SEARCH', `等待搜索结果页面超时 | url=${page.url().slice(0, 100)}`)
            }

            // 6. 从当前页面 URL 提取 bcid 和 query
            const resultUrl = page.url()
            this.logger.info('VISUAL-SEARCH', `搜索结果页面 URL: ${resultUrl.slice(0, 150)}`)

            const urlObj = new URL(resultUrl)
            const bcid = urlObj.searchParams.get('bcid')
            const query = urlObj.searchParams.get('q') ?? ''

            if (!bcid) {
                // 如果 URL 中没有 bcid，尝试从页面内容中提取
                this.logger.warn('VISUAL-SEARCH', 'URL 中未找到 bcid，尝试从页面内容提取')
                try {
                    const html = await page.content()
                    const bcidMatch = html.match(/bcid=([A-Za-z0-9]+)/)
                    if (bcidMatch) {
                        const extractedBcid = bcidMatch[1]
                        this.logger.info('VISUAL-SEARCH', `从页面内容提取 bcid=${extractedBcid.slice(0, 14)}`)
                        return { bcid: extractedBcid, query, serpUrl: resultUrl }
                    }
                } catch {
                    // 忽略
                }
                this.logger.warn('VISUAL-SEARCH', '无法从 URL 或页面内容中提取 bcid')
                return null
            }

            this.logger.info('VISUAL-SEARCH', `浏览器上传成功 | bcid=${bcid.slice(0, 14)} | q="${query}"`)
            return { bcid, query, serpUrl: resultUrl }
        } catch (error) {
            this.logger.warn('VISUAL-SEARCH', `浏览器文件上传失败: ${error.message}`)
            return null
        }
    }

    /**
     * Script-4 BrowserFunc.reportVisualSearchActivity：访问 SERP 获取 IG，再上报 reportActivity
     */
    async _reportVisualSearchActivity(jar, visual) {
        const { bcid, query, serpUrl } = visual
        const baseHeaders = { ...FINGERPRINT_HEADERS_DESKTOP }
        delete baseHeaders['Cookie']
        delete baseHeaders['cookie']

        const empty = { ig: null, balance: null, previousBalance: null, gained: null }

        // 1. 访问 SERP 获取 IG
        const searchRes = await this.bot.httpClient.request({
            url: serpUrl,
            method: 'GET',
            headers: {
                ...baseHeaders,
                Cookie: this._jarToHeader(jar),
                Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            }
        })
        this._mergeSetCookies(jar, searchRes.headers?.['set-cookie'])

        const ig = typeof searchRes.data === 'string'
            ? (searchRes.data.match(/\bIG:"([A-F0-9]{32})"/i) ??
               searchRes.data.match(/[?&]IG=([A-F0-9]{32})\b/i))?.[1] ?? null
            : null
        if (!ig) {
            this.logger.warn('VISUAL-SEARCH', `无 IG for "${query}" - SERP 未按预期返回`)
            return { ...empty, gained: null }
        }

        // 2. 上报 reportActivity（Script-4：/rewardsapp/reportActivity）
        const params = new URLSearchParams({
            IG: ig,
            IID: 'SERP.5064',
            q: query,
            bcid,
            FORM: 'SBIHMP',
            hq: '1',
            ajaxreq: '1'
        })
        const reportUrl = `${URLS.bing.origin}/rewardsapp/reportActivity?${params.toString()}`

        const reportRes = await this.bot.httpClient.request({
            url: reportUrl,
            method: 'POST',
            headers: {
                ...baseHeaders,
                Cookie: this._jarToHeader(jar),
                Accept: '*/*',
                'Content-Type': 'application/x-www-form-urlencoded',
                Referer: serpUrl,
                Origin: URLS.bing.origin,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'X-Requested-With': 'XMLHttpRequest'
            },
            data: `url=${encodeURIComponent(serpUrl)}&V=web`
        })
        this._mergeSetCookies(jar, reportRes.headers?.['set-cookie'])

        const parsed = this._parseReportResponse(reportRes.data)
        const gained = parsed.balance != null && parsed.previousBalance != null
            ? parsed.balance - parsed.previousBalance
            : null

        this.logger.debug('VISUAL-SEARCH', `上报 "${query}" | ig=${ig} | bcid=${bcid.slice(0, 12)} | gained=${gained ?? 'n/a'} | balance=${parsed.balance ?? 'n/a'}`)
        return { ig, ...parsed, gained }
    }

    /**
     * Script-4 BrowserFunc cookie jar 辅助方法
     */
    _getBingJar() {
        const src = this.bot.desktopCookies.length ? this.bot.desktopCookies : this.bot.cookies
        const key = `${src.find(c => c.name === '_U')?.value ?? ''}|desktop`
        let jar = this._bingJars.get(key)
        if (!jar) {
            jar = new Map()
            for (const c of src) {
                const domain = c.domain.replace(/^\./, '')
                if (domain === 'bing.com' || domain.endsWith('.bing.com')) {
                    jar.set(c.name, c.value)
                }
            }
            this._bingJars.set(key, jar)
        }
        return jar
    }

    _mergeSetCookies(jar, setCookie) {
        if (!setCookie) return
        const list = Array.isArray(setCookie) ? setCookie : [setCookie]
        for (const raw of list) {
            const pair = raw.split(';', 1)[0] ?? ''
            const eq = pair.indexOf('=')
            if (eq <= 0) continue
            const name = pair.slice(0, eq).trim()
            const value = pair.slice(eq + 1).trim()
            if (!name) continue
            if (value === '' || /expires=Thu,\s*01\s*Jan\s*1970/i.test(raw) || /\bmax-age=0\b/i.test(raw)) {
                jar.delete(name)
            } else {
                jar.set(name, value)
            }
        }
    }

    _jarToHeader(jar) {
        return [...jar.entries()].map(([n, v]) => `${n}=${v}`).join('; ')
    }

    _buildMultipart(boundary, fields) {
        const parts = []
        for (const f of fields) {
            parts.push(`--${boundary}\r\nContent-Disposition: form-data; name="${f.name}"\r\n\r\n${f.value}\r\n`)
        }
        parts.push(`--${boundary}--\r\n`)
        return parts.join('')
    }

    _parseKblobRedirect(data) {
        try {
            const obj = typeof data === 'string' ? JSON.parse(data) : data
            const url = obj?.redirectUrl
            if (typeof url === 'string' && url.includes('bcid=')) return url
        } catch { /* 忽略 */ }
        if (typeof data === 'string') {
            const m = data.match(/"redirectUrl"\s*:\s*"([^"]+)"/)
            const raw = m?.[1]
            if (raw && raw.includes('bcid=')) return raw.replace(/\\u002f/gi, '/').replace(/\\\//g, '/')
        }
        return null
    }

    _parseReportResponse(data) {
        const empty = { balance: null, previousBalance: null, searchPointsEarned: null, searchPointsLimit: null }
        if (typeof data !== 'string') return empty
        const m = data.match(/ModernRewards\.ReportActivity\((\{[\s\S]*?\})\)\s*;/)
        if (!m) return empty
        try {
            const s = JSON.parse(m[1] ?? '{}').RewardsSessionData ?? {}
            const num = v => (typeof v === 'number' ? v : null)
            return {
                balance: num(s.Balance),
                previousBalance: num(s.PreviousBalance),
                searchPointsEarned: num(s.DailySearchPointsEarned),
                searchPointsLimit: num(s.DailySearchPointsLimit)
            }
        } catch {
            return empty
        }
    }

    /**
     * Script-4 BrowserFunc.resetHttpJars：清除 bing cookie jar 缓存（账户切换时调用）
     */
    resetHttpJars() {
        this._bingJars.clear()
    }

    /**
     * 额外搜索 farming（Script-4 BonusTracker / doBonusSearches）
     * 识别仪表盘中"裸 Bing 搜索"类 urlreward 活动（destinationUrl 为 bing.com 根路径，
     * 仅含追踪参数 form/ocid/...），执行额外搜索以获取积分。
     * @param {object} page 浏览器页面
     * @param {boolean} isMobile 是否移动端
     * @returns {Promise<number>} 获得的积分
     */
    async doBonusSearches(page, isMobile) {
        const maxBonusSearches = Number(this.bot.config.search?.maxBonusSearches ?? 0)
        if (maxBonusSearches <= 0) {
            this.logger.info('SEARCH-BONUS', 'maxBonusSearches=0，跳过额外搜索 farming')
            return 0
        }
        if (!page) {
            this.logger.warn('SEARCH-BONUS', '跳过：缺少浏览器页面')
            return 0
        }

        // 1. 查找搜索 bonus 活动
        let dashboard
        try {
            this._dashboardCache = null
            dashboard = await this.getDashboardData()
        } catch (e) {
            this.logger.warn('SEARCH-BONUS', `获取仪表盘失败，跳过: ${e.message}`)
            return 0
        }

        const BING_TRACKING_PARAMS = new Set(['form', 'ocid', 'publ', 'crea', 'pc', 'channel', 'mkt', 'cc', 'setlang'])
        const pools = [
            ...(dashboard.morePromotions || []),
            ...(dashboard.morePromotionsWithoutPromotionalItems || []),
            ...(dashboard.promotionalItems || [])
        ].filter(Boolean)

        const isBareBingSearchDestination = (url) => {
            if (!url) return false
            try {
                const u = new URL(url)
                const isBingHost = /(^|\.)bing\.com$/i.test(u.hostname)
                const isRootPath = u.pathname === '' || u.pathname === '/'
                if (!isBingHost || !isRootPath) return false
                for (const key of u.searchParams.keys()) {
                    if (!BING_TRACKING_PARAMS.has(key.toLowerCase())) return false
                }
                return true
            } catch {
                return false
            }
        }

        const offer = pools.find(p => {
            if (!p || p.complete) return false
            if (!(p.pointProgressMax > p.pointProgress)) return false
            if ((p.promotionType || '').toLowerCase() !== 'urlreward') return false
            return isBareBingSearchDestination(p.destinationUrl)
        })

        if (!offer) {
            this.logger.info('SEARCH-BONUS', '未发现搜索 bonus 活动，跳过')
            return 0
        }

        const offerId = offer.offerId
        let current = offer.pointProgress
        const max = offer.pointProgressMax
        this.logger.info('SEARCH-BONUS', `发现搜索 bonus: ${offer.title} | offerId=${offerId} | 进度=${current}/${max} | 最大搜索=${maxBonusSearches}`)

        // 2. 执行额外搜索
        const searchManager = this.bot.searchManager
        const queries = searchManager._getQueries()
        const bingHome = isMobile ? 'https://cn.bing.com/?form=BNRDOI' : 'https://cn.bing.com'

        await page.goto(bingHome).catch(() => {})
        await searchManager._dismissMessages(page).catch(() => {})

        let totalGained = 0
        let stagnant = 0
        const stagnantLimit = 20

        for (let i = 0; i < Math.min(queries.length, maxBonusSearches); i++) {
            if (current >= max) {
                this.logger.success('SEARCH-BONUS', `搜索 bonus 已满 | 进度=${current}/${max}`)
                break
            }
            const query = queries[i]
            try {
                await searchManager._bingSearch(page, query, isMobile)
            } catch (e) {
                this.logger.warn('SEARCH-BONUS', `搜索失败 "${query}": ${e.message}`)
            }

            await wait(randomDelay(this.bot.config.search.searchDelayMin, this.bot.config.search.searchDelayMax))

            // 检查 bonus 进度
            try {
                this._dashboardCache = null
                const dash = await this.getDashboardData()
                const allOffers = [
                    ...(dash.morePromotions || []),
                    ...(dash.morePromotionsWithoutPromotionalItems || []),
                    ...(dash.promotionalItems || [])
                ].filter(Boolean)
                const cur = allOffers.find(o => o.offerId === offerId)
                if (!cur) {
                    this.logger.warn('SEARCH-BONUS', `活动 ${offerId} 已不在仪表盘中，停止`)
                    break
                }
                const gained = cur.pointProgress - current
                if (gained > 0) {
                    stagnant = 0
                    current = cur.pointProgress
                    totalGained += gained
                    this.bot.gainedPoints += gained
                    this.logger.success('SEARCH-BONUS', `+${gained} 积分 | "${query}" | 进度=${current}/${max}`)
                } else {
                    stagnant++
                    this.logger.info('SEARCH-BONUS', `无积分 ${stagnant}/${stagnantLimit} | "${query}" | 进度=${current}/${max}`)
                }

                // 更新账户总积分
                const newBalance = dash.userStatus?.availablePoints ?? this.bot.currentPoints
                if (newBalance > this.bot.currentPoints) {
                    this.bot.currentPoints = newBalance
                }

                if (stagnant >= stagnantLimit) {
                    this.logger.warn('SEARCH-BONUS', `连续 ${stagnantLimit} 次无积分，停止`)
                    break
                }
            } catch (e) {
                this.logger.debug('SEARCH-BONUS', `检查进度失败: ${e.message}`)
            }
        }

        this.logger.info('SEARCH-BONUS', `搜索 bonus 完成 | 获得: ${totalGained} 积分 | 最终进度=${current}/${max}`)
        return totalGained
    }

    /**
     * 启用连续登录保护（Script-4 EnsureStreakProtection）
     * 移植自 Script-4 EnsureStreakProtection.ts
     * - 从 bootstrap 已发现的 nextActions 中解析 action id
     * - 从 reactSnapshot.streakProtection 读取当前状态
     * - 通过 reportServerAction 调用，并重新读取状态验证
     * @param {object} page 浏览器页面（用于重新读取 streak 状态）
     */
    async doEnsureStreakProtection(page) {
        const STREAK_PROTECTION_ACTION_NAMES = [
            'reportSetStreakProtection',
            'reportToggleStreakProtection',
            'reportEnableStreakProtection',
            'setStreakProtection',
            'reportStreakProtection'
        ]

        // 1. 从 bootstrap 已发现的 nextActions 中解析 action id
        let actionId = this.bot.config.streakProtectionActionId || ''
        let actionName = 'config'
        if (!actionId) {
            for (const name of STREAK_PROTECTION_ACTION_NAMES) {
                if (this.bot.nextActions[name]) {
                    actionId = this.bot.nextActions[name]
                    actionName = name
                    break
                }
            }
            // 模糊匹配：键名包含 streak 和 protect
            if (!actionId) {
                const fuzzy = Object.keys(this.bot.nextActions).find(
                    k => /streak/i.test(k) && /protect/i.test(k)
                )
                if (fuzzy) {
                    actionId = this.bot.nextActions[fuzzy]
                    actionName = fuzzy
                }
            }
        }

        if (!actionId) {
            // Script-4 扩展：尝试从 /earn?section=streaks 页面重新发现 action ids
            if (page) {
                this.logger.info('ENABLE-STREAK-PROTECTION', '尝试从 /earn?section=streaks 页面发现 action ids')
                try {
                    const res = await page.request.get(URLS.rewards.earnStreaks)
                    if (res.ok()) {
                        const streaksHtml = await res.text()
                        const newActions = await this._resolveActionIds(page, [streaksHtml])
                        const newKeys = Object.keys(newActions)
                        if (newKeys.length) {
                            this.logger.debug('ENABLE-STREAK-PROTECTION', `从 streaks 页面发现 ${newKeys.length} 个新 action ids: [${newKeys.join(', ')}]`)
                            Object.assign(this.bot.nextActions, newActions)
                        }
                        // 重新查找
                        for (const name of STREAK_PROTECTION_ACTION_NAMES) {
                            if (this.bot.nextActions[name]) {
                                actionId = this.bot.nextActions[name]
                                actionName = name
                                break
                            }
                        }
                        if (!actionId) {
                            const fuzzy = Object.keys(this.bot.nextActions).find(
                                k => /streak/i.test(k) && /protect/i.test(k)
                            )
                            if (fuzzy) {
                                actionId = this.bot.nextActions[fuzzy]
                                actionName = fuzzy
                            }
                        }
                    }
                } catch (error) {
                    this.logger.debug('ENABLE-STREAK-PROTECTION', `从 streaks 页面发现 action ids 失败: ${error.message}`)
                }
            }
        }

        if (!actionId) {
            this.logger.warn(
                'ENABLE-STREAK-PROTECTION',
                `跳过：未发现 streak-protection action id（已查找 [${STREAK_PROTECTION_ACTION_NAMES.join(', ')}] 及模糊匹配，nextActions=[${Object.keys(this.bot.nextActions).join(', ')}]）`
            )
            return
        }

        // 2. 读取当前 streak protection 状态
        const before = this.bot.reactSnapshot?.streakProtection ?? null
        if (before?.isProtectionOn) {
            this.logger.info('ENABLE-STREAK-PROTECTION', `已启用 (remainingDays=${before.remainingDays ?? '?'})`)
            return
        }
        if (before && before.remainingDays === 0) {
            this.logger.info('ENABLE-STREAK-PROTECTION', '保护天数剩余 0 - 开关已禁用，跳过')
            return
        }

        const beforeDesc = before ? `on=${before.isProtectionOn},days=${before.remainingDays ?? '?'}` : 'unknown'
        this.logger.info('ENABLE-STREAK-PROTECTION', `开始启用 | action=${actionName} | before=${beforeDesc}`)

        try {
            // 3. 调用 Server Action（POST 到 /earn?section=streaks）
            const { status, acknowledged } = await this.reportServerAction(
                actionId,
                [true],
                { url: URLS.rewards.earnStreaks, referer: URLS.rewards.earnStreaks }
            )

            // 4. 重新读取 streak protection 状态验证
            const after = await this._readStreakProtection(page)

            if (after?.isProtectionOn) {
                this.logger.info('ENABLE-STREAK-PROTECTION', `完成 | isProtectionOn=true | remainingDays=${after.remainingDays ?? '?'} | status=${status}`)
            } else if (after === null) {
                this.logger.warn('ENABLE-STREAK-PROTECTION', `已触发但无法从新快照确认状态 | acknowledged=${acknowledged} | status=${status}`)
            } else {
                this.logger.warn('ENABLE-STREAK-PROTECTION', `开关未生效 - 仍为关闭 | status=${status}`)
            }

            await wait(randomDelay(5000, 10000))
        } catch (error) {
            this.logger.error('ENABLE-STREAK-PROTECTION', `启用连续登录保护失败: ${error.message}`)
        }
    }

    /**
     * 重新读取 streak protection 状态（Script-4 readStreakProtection）
     * @param {object} page 浏览器页面
     * @returns {Promise<object|null>} { isProtectionOn, remainingDays } 或 null
     */
    async _readStreakProtection(page) {
        try {
            if (!page) return null
            const res = await page.request.get(URLS.rewards.earn)
            if (!res.ok()) {
                this.logger.warn('ENABLE-STREAK-PROTECTION', `验证获取失败 | status=${res.status()}`)
                return null
            }
            const html = await res.text()
            return this.bot.reactParser.parseStreakProtection(this.bot.reactParser.concatFlightChunks(html))
        } catch (error) {
            this.logger.warn('ENABLE-STREAK-PROTECTION', `验证读取异常: ${error.message}`)
            return null
        }
    }
}

// ============================================================================
// 搜索管理器
// ============================================================================
class SearchManager {
    constructor(bot, logger) {
        this.bot = bot
        this.logger = logger

        // 内置搜索词库
        this.localQueries = [
            'weather today', 'news headlines', 'best restaurants near me', 'movie showtimes',
            'stock market today', 'how to cook rice', 'world cup results', 'tech news',
            'best smartphones 2024', 'python tutorial', 'healthy recipes', 'travel deals',
            'music streaming', 'exercise tips', 'book recommendations', 'space exploration',
            'climate change', 'ai breakthroughs', 'electric cars', 'photography tips',
            'garden ideas', 'home improvement', 'investment strategies', 'language learning',
            'history facts', 'science experiments', 'art museums', 'hiking trails',
            'coffee brands', 'fitness apps', 'meditation techniques', 'productivity tools',
            'best laptops', 'gaming news', 'crypto prices', 'real estate trends',
            'job interview tips', 'resume templates', 'online courses', 'documentary films',
            'podcast recommendations', 'best podcasts', 'tv series reviews', 'concert tickets',
            'local events', 'weather forecast', 'flight tracker', 'currency converter',
            'recipe ideas', 'workout plans', 'yoga for beginners', 'running tips',
            'healthy snacks', 'meal prep ideas', 'budget travel', 'road trip planner',
            'national parks', 'camping gear', 'fishing spots', 'bike trails',
            'best books 2024', 'kindle deals', 'library near me', 'study tips',
            'math problems', 'science news', 'space facts', 'ocean life',
            'wildlife photography', 'bird watching', 'plant care', 'gardening tips',
            'car maintenance', 'fuel prices', 'electric vehicles', 'hybrid cars'
        ]
    }

    /**
     * 执行搜索任务
     */
    async doSearches(page, isMobile) {
        let searchPoints, missing
        try {
            searchPoints = await this.bot.rewards.getSearchPoints()
            missing = this.bot.rewards.missingSearchPoints(searchPoints, isMobile)
        } catch (error) {
            this.logger.warn('SEARCH', `获取搜索积分失败，使用默认值: ${error.message}`)
            // 无法获取积分信息时，假设需要搜索（桌面端 30 积分）
            missing = { mobilePoints: 0, desktopPoints: isMobile ? 0 : 30, edgePoints: 0, totalPoints: isMobile ? 0 : 30 }
        }

        if (missing.totalPoints <= 0) {
            this.logger.info('SEARCH', `${isMobile ? '移动端' : '桌面端'}搜索积分已满`)
            return 0
        }

        this.logger.info('SEARCH', `${isMobile ? '移动端' : '桌面端'}搜索开始 | 缺失积分: ${missing.totalPoints}`)

        const queries = this._getQueries()
        const bingHome = isMobile ? 'https://cn.bing.com/?form=BNRDOI' : 'https://cn.bing.com'

        await page.goto(bingHome)
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
        await this._dismissMessages(page)

        let totalGained = 0
        let stagnantLoop = 0
        const stagnantLimit = this.bot.config.search.stagnantLimit
        let lastMissing = missing.totalPoints

        for (let i = 0; i < queries.length; i++) {
            const query = queries[i]

            try {
                await this._bingSearch(page, query, isMobile)
            } catch (error) {
                this.logger.warn('SEARCH', `搜索失败 "${query}": ${error.message}`)
            }

            // 检查积分变化
            try {
                const newCounters = await this.bot.rewards.getSearchPoints()
                const newMissing = this.bot.rewards.missingSearchPoints(newCounters, isMobile)
                const gained = Math.max(0, lastMissing - newMissing.totalPoints)
                lastMissing = newMissing.totalPoints

                if (gained > 0) {
                    stagnantLoop = 0
                    totalGained += gained
                    this.bot.currentPoints += gained
                    this.bot.gainedPoints += gained
                    this.logger.success('SEARCH', `+${gained} 积分 | "${query}" | 剩余: ${newMissing.totalPoints}`)
                } else {
                    stagnantLoop++
                    this.logger.info('SEARCH', `无积分 ${stagnantLoop}/${stagnantLimit} | "${query}" | 剩余: ${newMissing.totalPoints}`)
                }

                if (newMissing.totalPoints <= 0) {
                    this.logger.success('SEARCH', `${isMobile ? '移动端' : '桌面端'}搜索积分已满`)
                    break
                }

                if (stagnantLoop >= stagnantLimit) {
                    this.logger.warn('SEARCH', `连续 ${stagnantLimit} 次无积分，停止搜索`)
                    break
                }
            } catch (error) {
                this.logger.debug('SEARCH', `检查积分失败: ${error.message}`)
            }

            await wait(randomDelay(this.bot.config.search.searchDelayMin, this.bot.config.search.searchDelayMax))
        }

        this.logger.info('SEARCH', `${isMobile ? '移动端' : '桌面端'}搜索完成 | 获得: ${totalGained} 积分`)
        return totalGained
    }

    _getQueries() {
        return shuffleArray(this.localQueries)
    }

    async _bingSearch(page, query, isMobile) {
        const searchUrl = `https://cn.bing.com/search?q=${encodeURIComponent(query)}&form=QBLH`
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded' })
        await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})

        // 随机点击搜索结果（模拟真实行为）
        if (Math.random() > 0.5) {
            try {
                const results = await page.$$('a[href]')
                if (results.length > 0) {
                    const randomIndex = randomNumber(0, Math.min(results.length - 1, 5))
                    const link = results[randomIndex]
                    const href = await link.getAttribute('href')
                    if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                        await wait(randomDelay(2000, 5000))
                    }
                }
            } catch {
                // 忽略点击错误
            }
        }
    }

    async _dismissMessages(page) {
        const dismissSelectors = [
            '#acceptButton',
            '#bnp_btn_accept',
            'button[id="reward_pivot_2"]',
            '#bnp_close_link',
            '.bnp_btn_accept',
            'button:has-text("Accept")',
            'button:has-text("确定")',
            'button:has-text("同意")'
        ]
        for (const sel of dismissSelectors) {
            try {
                const el = await page.$(sel)
                if (el) {
                    await el.click().catch(() => {})
                    await wait(500)
                }
            } catch {
                // 忽略
            }
        }
    }
}

// ============================================================================
// 主机器人类
// ============================================================================
class MicrosoftRewardsBot {
    constructor(config, account, logger) {
        this.config = config
        this.account = account
        this.logger = logger

        // 用户数据
        this.geoLocale = 'US'
        this.langCode = account.langCode || 'en'
        this.timezoneOffset = String(-new Date().getTimezoneOffset())
        this.initialPoints = 0
        this.currentPoints = 0
        this.gainedPoints = 0

        // 认证数据
        this.accessToken = ''
        this.requestToken = ''
        this.cookies = []
        this.desktopCookies = []
        this.panelData = null

        // Script-4 Server Action 机制
        this.nextActions = {}
        this.nextRouterStateTree = ''
        this.reactSnapshot = null
        this.reactParser = new ReactParser(logger)

        // 子系统
        this.sessionManager = new SessionManager(config.sessionPath, logger)
        this.browserManager = new BrowserManager(config, logger)
        this.loginManager = new LoginManager(this, logger)
        this.rewards = new RewardsManager(this, logger)
        this.searchManager = new SearchManager(this, logger)
        this.httpClient = new HttpClient(account.proxy, logger)
    }

    /**
     * 运行单个账户的完整流程（Script-4 双浏览器架构）
     *
     * 流程：
     *   1. 移动端浏览器 → 登录 → bootstrap（reactSnapshot + action ids）
     *   2. 移动端任务：DailySet, MorePromotions, AppPromotions, OtherPromotions,
     *      DailyCheckIn, ReadToEarn, PunchCards(mobile), ActivateSearchPerk,
     *      EnsureStreakProtection, MobileSearch, BonusSearches(mobile)
     *   3. 桌面端浏览器 → 登录 → bootstrap（重新获取桌面端 reactSnapshot + action ids）
     *   4. 桌面端任务：PunchCards(desktop), DesktopSearch, VisualSearch, BonusSearches(desktop)
     *   5. ClaimBonusPoints（末尾）
     */
    async run() {
        const accountEmail = this.account.email
        this.logger.info('FLOW', `开始处理账户: ${accountEmail}`)

        // Script-4：清除上一个账户的 HTTP cookie jar 缓存
        this.rewards.resetHttpJars()

        let mobileBrowser = null
        let mobileContext = null
        let desktopBrowser = null
        let desktopContext = null

        try {
            // ==================================================================
            // 阶段 1：移动端浏览器 → 登录 → bootstrap
            // ==================================================================
            this.logger.info('FLOW', '启动移动端浏览器')
            const mobileSession = await this.browserManager.launchBrowser(this.account, true)
            mobileBrowser = mobileSession.browser
            mobileContext = mobileSession.context

            const savedCookies = await this.sessionManager.loadCookies(accountEmail, true)
            if (savedCookies.length > 0) {
                await mobileContext.addCookies(savedCookies)
                this.logger.debug('FLOW', `已加载 ${savedCookies.length} 个保存的 cookies`)
            }

            const mobilePage = await mobileContext.newPage()

            // 登录
            await this.loginManager.login(mobilePage, this.account)
            this.cookies = await mobileContext.cookies()
            await this.sessionManager.saveCookies(accountEmail, true, this.cookies)

            // 获取 OAuth 访问令牌
            try {
                this.accessToken = await this.loginManager.getAppAccessToken(mobilePage, accountEmail)
            } catch (error) {
                this.logger.warn('FLOW', `获取访问令牌失败: ${error.message}`)
            }

            // 获取仪表盘数据
            this.logger.info('FLOW', '获取仪表盘数据')
            const dashboardData = await this.rewards.getDashboardData()

            this.geoLocale =
                this.account.geoLocale === 'auto'
                    ? dashboardData.userProfile?.attributes?.country || 'US'
                    : this.account.geoLocale.toLowerCase()

            this.initialPoints = dashboardData.userStatus?.availablePoints ?? 0
            this.currentPoints = this.initialPoints
            this.logger.info('FLOW', `当前积分: ${this.initialPoints} | 地区: ${this.geoLocale}`)

            // 获取应用仪表盘数据（用于 App 促销）
            let appDashboardData = null
            try {
                appDashboardData = await this.rewards.getAppDashboardData()
            } catch (error) {
                this.logger.warn('FLOW', `获取应用仪表盘数据失败: ${error.message}`)
            }

            // Script-4：bootstrap（获取 /earn HTML → reactSnapshot + action ids）
            try {
                await this.rewards.bootstrap(mobilePage, true)
            } catch (error) {
                this.logger.warn('FLOW', `移动端 bootstrap 失败（非致命）: ${error.message}`)
            }

            // ==================================================================
            // 阶段 2：移动端任务
            // ==================================================================
            const workers = this.config.workers
            const _taskWait = async (taskName) => {
                const delaySec = randomNumber(15, 60)
                this.logger.info('FLOW', `任务 "${taskName}" 完成，等待 ${delaySec} 秒后继续下一个任务`)
                await wait(delaySec * 1000)
            }

            if (workers.doDailySet) {
                await this.rewards.doDailySet(dashboardData, mobilePage, true)
                await _taskWait('每日任务')
            }
            if (workers.doMorePromotions) {
                await this.rewards.doMorePromotions(dashboardData, mobilePage, true)
                await _taskWait('更多促销')
            }
            if (workers.doAppPromotions && appDashboardData) {
                await this.rewards.doAppPromotions(appDashboardData)
                await _taskWait('App 促销')
            }
            if (workers.doOtherPromotions) {
                await this.rewards.doOtherPromotions()
                await _taskWait('其他促销')
            }
            if (workers.doDailyCheckIn) {
                await this.rewards.doDailyCheckIn()
                await _taskWait('每日签到')
            }
            if (workers.doReadToEarn) {
                await this.rewards.doReadToEarn()
                await _taskWait('Read to Earn')
            }

            // Script-4：PunchCard 移动端阶段（处理移动端可完成的 quest）
            if (workers.doPunchCards) {
                try {
                    await this.rewards.doPunchCards(dashboardData, mobilePage, true)
                } catch (error) {
                    this.logger.error('FLOW', `PunchCard 移动端阶段失败: ${error.message}`)
                }
                await _taskWait('打卡任务(移动端)')
            }

            // 激活搜索积分倍数特权
            if (workers.doActivateSearchPerk || workers.doSpecialPromotions) {
                await this.rewards.doActivateSearchPerk(dashboardData, mobilePage)
                await _taskWait('激活搜索特权')
            }
            // 连续登录保护
            if (workers.doEnsureStreakProtection) {
                await this.rewards.doEnsureStreakProtection(mobilePage)
                await _taskWait('连续登录保护')
            }

            // 移动端搜索
            if (workers.doMobileSearch) {
                this.logger.info('FLOW', '开始移动端搜索')
                try {
                    const mobilePoints = await this.searchManager.doSearches(mobilePage, true)
                    this.logger.info('FLOW', `移动端搜索完成 | +${mobilePoints} 积分`)
                } catch (error) {
                    this.logger.error('FLOW', `移动端搜索失败: ${error.message}`)
                }
                await _taskWait('移动端搜索')
            }

            // 额外搜索 farming（移动端）
            if (workers.doBonusSearches && workers.doMobileSearch) {
                try {
                    await this.rewards.doBonusSearches(mobilePage, true)
                } catch (error) {
                    this.logger.error('FLOW', `额外搜索 farming(移动端) 失败: ${error.message}`)
                }
                await _taskWait('额外搜索 farming(移动端)')
            }

            // 刷新 cookies（移动端任务可能更新了 cookies）
            this.cookies = await mobileContext.cookies()

            // ==================================================================
            // 阶段 3：桌面端浏览器 → 登录 → bootstrap
            // 当需要 PunchCard 桌面端阶段 / 桌面端搜索 / 视觉搜索时创建
            // ==================================================================
            const desktopNeeded = workers.doPunchCards || workers.doDesktopSearch || workers.doVisualSearch

            if (desktopNeeded) {
                // Script-4：在启动桌面端浏览器前关闭移动端浏览器，释放资源避免 chromewebdata 错误
                this.logger.info('FLOW', '关闭移动端浏览器（桌面端阶段前）')
                try {
                    await this.sessionManager.saveCookies(accountEmail, true, this.cookies)
                } catch { /* 忽略 */ }
                try {
                    await mobileContext.close()
                } catch { /* 忽略 */ }
                try {
                    await mobileBrowser.close()
                } catch { /* 忽略 */ }
                mobileBrowser = null
                mobileContext = null
                await wait(2000)

                this.logger.info('FLOW', '启动桌面端浏览器')
                const desktopSession = await this.browserManager.launchBrowser(this.account, false)
                desktopBrowser = desktopSession.browser
                desktopContext = desktopSession.context

                // Script-4：通过 storageState 共享会话 - 优先加载已保存的桌面端 cookies，
                // 若无则注入移动端 cookies 避免完全从头登录
                const savedDesktopCookies = await this.sessionManager.loadCookies(accountEmail, false)
                if (savedDesktopCookies.length > 0) {
                    await desktopContext.addCookies(savedDesktopCookies)
                    this.logger.debug('FLOW', `已加载 ${savedDesktopCookies.length} 个桌面端 cookies`)
                } else if (this.cookies.length > 0) {
                    // Script-4：共享移动端 session，使桌面端浏览器以已认证状态启动
                    await desktopContext.addCookies(this.cookies)
                    this.logger.debug('FLOW', `注入 ${this.cookies.length} 个移动端 cookies 到桌面端 context`)
                }

                const desktopPage = await desktopContext.newPage()

                // 桌面端登录（若已通过共享 cookies 认证，login 会立即检测到 LOGGED_IN 状态）
                this.logger.info('FLOW', '桌面端登录')
                try {
                    await this.loginManager.login(desktopPage, this.account)
                    this.desktopCookies = await desktopContext.cookies()
                    await this.sessionManager.saveCookies(accountEmail, false, this.desktopCookies)
                } catch (error) {
                    this.logger.warn('FLOW', `桌面端登录失败（尝试复用移动端 cookies）: ${error.message}`)
                    this.desktopCookies = [...this.cookies]
                }

                // Script-4：桌面端 bootstrap（重新获取桌面端 reactSnapshot + action ids）
                try {
                    await this.rewards.bootstrap(desktopPage, false)
                } catch (error) {
                    this.logger.warn('FLOW', `桌面端 bootstrap 失败（非致命）: ${error.message}`)
                }

                // ==================================================================
                // 阶段 4：桌面端任务
                // ==================================================================

                // Script-4：PunchCard 桌面端阶段（PC 端 quest 在此完成）
                if (workers.doPunchCards) {
                    try {
                        // 重新获取桌面端 dashboard 数据
                        const desktopDashboardData = await this.rewards.getDashboardData()
                        await this.rewards.doPunchCards(desktopDashboardData, desktopPage, false)
                    } catch (error) {
                        this.logger.error('FLOW', `PunchCard 桌面端阶段失败: ${error.message}`)
                    }
                    await _taskWait('打卡任务(桌面端)')
                }

                // 桌面端搜索
                if (workers.doDesktopSearch) {
                    this.logger.info('FLOW', '开始桌面端搜索')
                    try {
                        const desktopPoints = await this.searchManager.doSearches(desktopPage, false)
                        this.logger.info('FLOW', `桌面端搜索完成 | +${desktopPoints} 积分`)
                    } catch (error) {
                        this.logger.error('FLOW', `桌面端搜索失败: ${error.message}`)
                    }
                    await _taskWait('桌面端搜索')
                }

                // 视觉搜索（仅桌面端）—— [已关闭] kblob API 在中国地区因 TLS 指纹检测返回 400，Script-3 axios 无法通过
                if (workers.doVisualSearch) {
                    try {
                        await this.rewards.doVisualSearch(desktopPage)
                    } catch (error) {
                        this.logger.error('FLOW', `视觉搜索失败: ${error.message}`)
                    }
                    await _taskWait('视觉搜索')
                } else {
                    this.logger.info('FLOW', '视觉搜索任务已关闭 | 原因：kblob API TLS 指纹检测无法通过（Script-3 使用 axios，需 Impit 等效方案）')
                }

                // 额外搜索 farming（桌面端）
                if (workers.doBonusSearches && workers.doDesktopSearch) {
                    try {
                        await this.rewards.doBonusSearches(desktopPage, false)
                    } catch (error) {
                        this.logger.error('FLOW', `额外搜索 farming(桌面端) 失败: ${error.message}`)
                    }
                    await _taskWait('额外搜索 farming(桌面端)')
                }

                // 刷新桌面端 cookies
                this.desktopCookies = await desktopContext.cookies()

                // 关闭桌面端浏览器
                try {
                    await desktopContext.close()
                } catch { /* 忽略 */ }
                try {
                    await desktopBrowser.close()
                } catch { /* 忽略 */ }
                desktopBrowser = null
                desktopContext = null
            }

            // ==================================================================
            // 阶段 5：领取奖励积分（末尾）
            // ==================================================================
            if (workers.doClaimBonusPoints) {
                await this.rewards.doClaimBonusPoints(dashboardData)
                await _taskWait('领取奖励积分')
            }

            // 获取最终积分
            const finalPoints = await this.rewards.getCurrentPoints()
            const collected = finalPoints - this.initialPoints

            this.logger.success(
                'FLOW',
                `账户 ${accountEmail} 完成 | 初始: ${this.initialPoints} | 最终: ${finalPoints} | 获得: +${collected} 积分`
            )

            return {
                email: accountEmail,
                initialPoints: this.initialPoints,
                finalPoints,
                collectedPoints: collected,
                success: true
            }
        } catch (error) {
            this.logger.error('FLOW', `账户 ${accountEmail} 失败: ${error.message}`)
            return {
                email: accountEmail,
                initialPoints: this.initialPoints,
                finalPoints: this.currentPoints,
                collectedPoints: this.gainedPoints,
                success: false,
                error: error.message
            }
        } finally {
            // 清理移动端浏览器资源
            if (mobileContext) {
                try {
                    const cookies = await mobileContext.cookies()
                    await this.sessionManager.saveCookies(accountEmail, true, cookies)
                } catch { /* 忽略 */ }
                try {
                    await mobileContext.close()
                } catch { /* 忽略 */ }
            }
            if (mobileBrowser) {
                try {
                    await mobileBrowser.close()
                } catch { /* 忽略 */ }
            }
            // 清理桌面端浏览器资源（如果尚未关闭）
            if (desktopContext) {
                try {
                    const cookies = await desktopContext.cookies()
                    await this.sessionManager.saveCookies(accountEmail, false, cookies)
                } catch { /* 忽略 */ }
                try {
                    await desktopContext.close()
                } catch { /* 忽略 */ }
            }
            if (desktopBrowser) {
                try {
                    await desktopBrowser.close()
                } catch { /* 忽略 */ }
            }
        }
    }
}

// ============================================================================
// 错误处理辅助
// ============================================================================
function fatal(message) {
    console.error(`${COLORS.red}[FATAL] ${message}${COLORS.reset}`)
    process.exit(1)
}

// ============================================================================
// 主入口
// ============================================================================
async function main() {
    // 加载依赖
    loadDependencies()

    // 解析命令行参数
    const args = process.argv.slice(2)
    const headlessFlag = args.includes('--headless')
    const noHeadlessFlag = args.includes('--no-headless')

    // 加载配置
    let config = createDefaultConfig()
    const configFromFile = loadConfigFile(path.join(__dirname, 'config.json'))
    if (configFromFile) {
        config = { ...config, ...configFromFile }
        if (configFromFile.workers) config.workers = { ...config.workers, ...configFromFile.workers }
        if (configFromFile.search) config.search = { ...config.search, ...configFromFile.search }
        if (configFromFile.browser) config.browser = { ...config.browser, ...configFromFile.browser }
    }

    // 命令行覆盖
    if (headlessFlag) config.headless = true
    if (noHeadlessFlag) config.headless = false

    // 加载账户
    let accounts = loadAccountsFile(path.join(__dirname, 'accounts.json'))
    if (!accounts) {
        // 使用脚本内嵌的示例账户（需用户填写）
        accounts = CONFIG.accounts
    }

    if (!accounts || accounts.length === 0) {
        fatal('未找到账户配置。请在脚本底部 CONFIG.accounts 中填写账户信息，或创建 accounts.json 文件。')
    }

    // 验证账户
    for (const account of accounts) {
        if (!account.email || !account.password) {
            fatal(`账户配置无效：email 和 password 为必填项。问题账户: ${account.email || '(空)'}`)
        }
    }

    // 创建主日志器
    const mainLogger = new Logger({
        level: config.debugLogs ? 'debug' : 'info',
        logFile: config.logFile
    })

    mainLogger.info('MAIN', `Microsoft Rewards 独立脚本启动 | 账户数: ${accounts.length} | 无头模式: ${config.headless}`)

    const runStartTime = Date.now()
    const allStats = []

    // 依次处理账户
    for (const account of accounts) {
        const accountLogger = new Logger({
            level: config.debugLogs ? 'debug' : 'info',
            logFile: config.logFile,
            account: getEmailUsername(account.email)
        })

        const bot = new MicrosoftRewardsBot(config, account, accountLogger)

        try {
            const stats = await bot.run()
            allStats.push(stats)
        } catch (error) {
            accountLogger.error('MAIN', `未捕获的错误: ${error.message}`)
            allStats.push({
                email: account.email,
                initialPoints: 0,
                finalPoints: 0,
                collectedPoints: 0,
                success: false,
                error: error.message
            })
        }

        // 账户间延迟（30-60 秒随机等待，降低多账号连续操作的风控风险）
        // 作用：当一个账号所有任务执行完成后，在开始下一个账号前进行随机等待，
        // 避免多个账号连续快速切换导致的异常检测，提高多账号运行的安全性。
        // 使用 randomNumber(30, 60) 生成 [30, 60] 区间内均匀分布的随机整数（含边界）。
        if (accounts.indexOf(account) < accounts.length - 1) {
            const accountSwitchDelay = randomNumber(30, 60)
            accountLogger.info('MAIN', `账号任务完成，等待 ${accountSwitchDelay} 秒后开始下一个账号...`)
            await wait(accountSwitchDelay * 1000)
        }
    }

    // 汇总报告
    const totalCollected = allStats.reduce((sum, s) => sum + s.collectedPoints, 0)
    const totalInitial = allStats.reduce((sum, s) => sum + s.initialPoints, 0)
    const totalFinal = allStats.reduce((sum, s) => sum + s.finalPoints, 0)
    const successCount = allStats.filter(s => s.success).length
    const durationMinutes = ((Date.now() - runStartTime) / 1000 / 60).toFixed(1)

    mainLogger.info('MAIN', '========== 运行汇总 ==========', COLORS.cyan)
    mainLogger.info('MAIN', `账户总数: ${allStats.length} | 成功: ${successCount} | 失败: ${allStats.length - successCount}`)
    mainLogger.info('MAIN', `初始积分总和: ${totalInitial}`)
    mainLogger.info('MAIN', `最终积分总和: ${totalFinal}`)
    mainLogger.info('MAIN', `获得积分总计: +${totalCollected}`)
    mainLogger.info('MAIN', `运行时长: ${durationMinutes} 分钟`)
    mainLogger.info('MAIN', '==============================', COLORS.cyan)

    // 打印每个账户的详情
    for (const stat of allStats) {
        const status = stat.success ? '成功' : '失败'
        const color = stat.success ? COLORS.green : COLORS.red
        mainLogger.info('MAIN', `${stat.email} | ${status} | +${stat.collectedPoints} 积分 | ${stat.initialPoints} → ${stat.finalPoints}`, color)
        if (stat.error) {
            mainLogger.warn('MAIN', `  错误: ${stat.error}`)
        }
    }

    // ============================================================================
    // sendNotify 推送通知（所有账户任务完成后触发）
    // ============================================================================
    try {
        mainLogger.info('MAIN', '开始执行推送通知...')

        // 账号脱敏函数：仅替换@前中间3-4位字符为*，保留首尾可见字符
        // 规则：长度<=4 替换1位；5-7位替换3位；>=8位替换4位
        const maskEmail = (email) => {
            const atIndex = email.indexOf('@')
            if (atIndex < 0) return email
            const local = email.substring(0, atIndex)
            const domain = email.substring(atIndex)
            const len = local.length
            if (len <= 1) return '*' + domain
            if (len <= 4) return local[0] + '*'.repeat(len - 1) + domain
            const maskLen = len >= 8 ? 4 : 3
            const keepStart = Math.ceil((len - maskLen) / 2)
            const keepEnd = len - maskLen - keepStart
            return local.substring(0, keepStart) + '*'.repeat(maskLen) + local.substring(len - keepEnd) + domain
        }

        // 构建推送内容：每个账号单独生成一段，按执行顺序排列
        let notifyBody = ''
        for (const stat of allStats) {
            notifyBody += `账号：${maskEmail(stat.email)}\n`
            notifyBody += `初始积分: ${stat.initialPoints}\n`
            notifyBody += `获得积分: ${stat.collectedPoints}\n`
            notifyBody += `最终积分: ${stat.finalPoints}\n`
            if (stat.error) {
                notifyBody += `错误: ${stat.error}\n`
            }
            notifyBody += '\n'
        }

        const notifyTitle = '微软积分奖励推送通知'

        // 尝试加载同目录下的 sendNotify 脚本（优先 .js，其次 .txt）
        let sendNotifyModule = null
        const notifyPaths = [
            path.join(__dirname, 'sendNotify.js'),
            path.join(__dirname, 'sendNotify.txt')
        ]

        for (const notifyPath of notifyPaths) {
            try {
                if (fs.existsSync(notifyPath)) {
                    sendNotifyModule = require(notifyPath)
                    mainLogger.info('MAIN', `已加载 sendNotify 模块: ${notifyPath}`)
                    break
                }
            } catch (loadError) {
                mainLogger.warn('MAIN', `加载 sendNotify 失败 (${notifyPath}): ${loadError.message}`)
            }
        }

        if (sendNotifyModule && typeof sendNotifyModule.sendNotify === 'function') {
            await sendNotifyModule.sendNotify(notifyTitle, notifyBody)
            mainLogger.info('MAIN', '推送通知发送完成')
        } else {
            mainLogger.warn('MAIN', '未找到可用的 sendNotify 模块，跳过推送通知。请确保同目录下存在 sendNotify.js 或 sendNotify.txt 文件。')
            mainLogger.info('MAIN', `推送内容预览:\n${notifyBody}`)
        }
    } catch (notifyError) {
        mainLogger.error('MAIN', `推送通知执行失败: ${notifyError.message}`)
    }

    process.exit(0)
}

// ============================================================================
// 进程事件处理
// ============================================================================
process.on('SIGINT', () => {
    console.log('\n收到 SIGINT，正在退出...')
    process.exit(130)
})

process.on('SIGTERM', () => {
    console.log('\n收到 SIGTERM，正在退出...')
    process.exit(143)
})

process.on('uncaughtException', error => {
    console.error(`${COLORS.red}[UNCAUGHT] ${error.stack || error.message}${COLORS.reset}`)
    process.exit(1)
})

process.on('unhandledRejection', (reason, promise) => {
    console.error(`${COLORS.red}[UNHANDLED] ${reason}${COLORS.reset}`)
})

// ============================================================================
// 配置区域 - 请在此填写你的账户信息
// ============================================================================
const CONFIG = {
    // 账户列表
    // 请将下面的示例替换为你自己的微软账户信息
    // 如果同目录下存在 accounts.json 文件，将优先使用该文件
    accounts: [
        {
            email: 'XXXXXX',
            password: 'XXXXXXX',
            totpSecret: '', // 如果启用了 TOTP 两步验证，填写密钥
            geoLocale: 'cn', // 'auto' 自动检测，或指定如 'us', 'cn', 'uk'
            langCode: 'en',
            proxy: {
                url: '', // 代理地址，如 'http://proxy.example.com' 或 'socks5://127.0.0.1'
                port: 0,
                username: '',
                password: ''
            }
        }
    ]
}

// ============================================================================
// 启动脚本
// ============================================================================
main().catch(error => {
    console.error(`${COLORS.red}[FATAL] ${error.stack || error.message}${COLORS.reset}`)
    process.exit(1)
})
