/*
 * # 合并版：绿树田园（广告任务 + 签到任务）
 *
 * 环境变量：
 *   TREECOIN_AUTH       授权码（优先，格式 authCode 或 authCode#deviceFP，多账号用换行/&/, 分隔）
 *   TREECOIN_AUTH_CODE  兼容旧变量名（同上）
 *   TREECOIN_PROXY_API  代理池 API（默认 https://treecoin.cn/api，置空则直连）
 *   TREECOIN_OPENID     微信 openid（可选，仅当 WX_ID 未配对时回退）
 *   WX_ID               共享微信协议账号池（与其他脚本一致，双协议：牛子 wxid_xxx / 应用宝 openid 或 openid#序号）
 *                       按【行索引】与 TREECOIN_AUTH 的每个账号一一对应（第1个绿树账号用第1个 WX_ID）
 *
 *   TREECOIN_AUTH 每行格式：authCode 或 authCode#deviceFP
 *     - deviceFP 可选（不填自动生成）；多账号用换行 / & / , 分隔
 *     - 广告领奖所需的微信 code 取自共享 WX_ID 池中同索引的账号；若某行想单独指定，可加第3字段 authCode#deviceFP#wxid 覆盖
 *
 * 依赖：axios（已在 package.json）；crypto 内置；sendNotify（仓库统一推送）；getCode（统一取码，双协议路由）
 *
 * cron: 30 8 * * *   （广告+签到同跑，每日一次即可）
 */

const crypto = require('crypto');
const axios = require('axios');
const { sendNotify } = require('./sendNotify');

// 统一微信协议（牛子/应用宝双协议，复用仓库 getCode）
let getSingleCode = null;
try {
    ({ getSingleCode } = require('./getCode'));
} catch (e) {
    getSingleCode = null;
}

// 青龙通知汇总
const notifyLines = [];
function notifyLog(msg) {
    console.log(msg);
    notifyLines.push(msg);
}

// ========== 环境变量配置 ==========
const ENV_VAR = process.env.TREECOIN_AUTH || process.env.TREECOIN_AUTH_CODE || '';
const PROXY_API_URL = process.env.TREECOIN_PROXY_API || 'https://treecoin.cn/api';
const ENV_OPENID = process.env.TREECOIN_OPENID || '';
// 共享微信协议账号池（与其他脚本一致）：牛子 wxid_xxx / 应用宝 openid 或 openid#序号；按索引与 TREECOIN_AUTH 配对
const WX_IDS_RAW = (process.env.WX_ID || '').trim();

const INVITE_CODE = 'NGLNCW5W';
const ENABLE_BIND_INVITER = true;

const MAX_PROXY_RETRIES = 5;
const MAX_AD_CONCURRENT = 4; // 广告最大并发
const PROXY_BATCH_NUM = 5;

// ========== 全局代理池 ==========
let proxyIpPool = [];

const RETRY_CONFIG = {
    maxRetries: 3,
    baseDelay: 1000,
    timeout: 15000
};

const RISK_CONFIG = {
    accountDelayMin: 5000,
    accountDelayMax: 10000,
    actionDelayMin: 600,
    actionDelayMax: 1800,
    signStepDelayMin: 300,
    signStepDelayMax: 1000,
    adDelayMin: 3000,
    adDelayMax: 6000,
    uaPool: [
        'Mozilla/5.0 (Linux; Android 14; 24069RA21C Build/UKQ1.240116.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.178 Mobile Safari/537.36 XWEB/1460217 MMWEBSDK/20260202 MMWEBID/1137 MicroMessenger/8.0.71.3080(0x28004750) WeChat/arm64 Weixin NetType/4G Language/zh_CN ABI/arm64',
        'Mozilla/5.0 (Linux; Android 13; MI 13 Build/TKQ1.220829.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7645.166 Mobile Safari/537.36 XWEB/1420097 MMWEBSDK/20251201 MMWEBID/2048 MicroMessenger/8.0.70.2660(0x28004638) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
        'Mozilla/5.0 (Linux; Android 12; OPPO Find X6 Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7622.121 Mobile Safari/537.36 XWEB/1380156 MMWEBSDK/20251001 MMWEBID/3312 MicroMessenger/8.0.69.2520(0x28004532) WeChat/arm64 Weixin NetType/4G Language/zh_CN ABI/arm64',
        'Mozilla/5.0 (Linux; Android 15; Pixel 9 Build/AP31.240905.013; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/148.0.7700.201 Mobile Safari/537.36 XWEB/1480032 MMWEBSDK/20260301 MMWEBID/789 MicroMessenger/8.0.72.3200(0x28004855) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
        'Mozilla/5.0 (Linux; Android 11; HUAWEI Mate 40 Pro Build/HUAWEINOH-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.116 Mobile Safari/537.36 XWEB/1300211 MMWEBSDK/20250601 MMWEBID/1567 MicroMessenger/8.0.65.2200(0x28004130) WeChat/arm64 Weixin NetType/4G Language/zh_CN ABI/arm64'
    ]
};

const BASE_URL = 'https://treecoin.cn/api';
const GCM_KEY = Buffer.from('asldhlfhdshkfashfluksdahfkjsadhfkjsdhfjshjkfhlakjshfjsdhfhsadflh'.substring(0, 32), 'utf8');

// ========== 工具函数 ==========
function parseAccounts() {
    if (!ENV_VAR) return [];
    const lines = ENV_VAR.split(/[\n&,]/).map(s => s.trim()).filter(Boolean);
    return lines.map(line => {
        const [authCode, deviceFP, wxid] = line.split('#');
        return {
            authCode: authCode.trim(),
            deviceFP: deviceFP ? deviceFP.trim() : genDeviceFP(),
            wxid: wxid ? wxid.trim() : '' // 第3字段可选，覆盖 WX_ID 按索引的配对
        };
    });
}

function parseWxIds() {
    if (!WX_IDS_RAW) return [];
    return WX_IDS_RAW.split(/[\n&|]/).map(s => s.trim()).filter(Boolean);
}

function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function genDeviceFP() {
    return `BROWSER_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function randomDelay(min, max) {
    const ms = Math.floor(Math.random() * (max - min + 1)) + min;
    return sleep(ms);
}

async function getBatchProxyIps() {
    try {
        const res = await axios.get(PROXY_API_URL, {
            timeout: 10000,
            params: { count: PROXY_BATCH_NUM, num: PROXY_BATCH_NUM }
        });
        let ipList = [];
        const raw = res.data;

        if (Array.isArray(raw)) {
            ipList = raw.map(item => String(item).trim());
        } else if (typeof raw === 'string') {
            ipList = raw.split(/[\r\n]+/).map(s => s.trim());
        }

        const validIps = ipList.filter(ip => {
            if (!ip) return false;
            if (ip.includes('错误') || ip.includes('失败') || ip.includes('剩余') || ip.includes('余额')) return false;
            return /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$/.test(ip);
        });

        if (validIps.length === 0) return [];
        validIps.sort(() => Math.random() - 0.5);
        return validIps;
    } catch (err) {
        return [];
    }
}

async function getOneProxyFromPool() {
    if (proxyIpPool.length === 0) {
        const newIps = await getBatchProxyIps();
        proxyIpPool = [...newIps];
    }
    return proxyIpPool.shift() || null;
}

// 统一走仓库 getCode（牛子/应用宝双协议），identifier 用 openid 或 deviceFP
// 带失败重试：广告领奖每次需新 code（一次性凭证），故仅重试不缓存，避免「code 已使用」
async function getWxCode(identifier, maxRetry = 3) {
    if (!getSingleCode) {
        throw new Error("未找到 ./getCode（请将其放在同一目录）");
    }
    const id = identifier || ENV_OPENID || '';
    let lastErr;
    for (let attempt = 1; attempt <= maxRetry; attempt++) {
        try {
            const code = await getSingleCode("wx1cc3b7be9bf56740", id);
            if (!code) throw new Error("getCode 返回空 code");
            return code;
        } catch (e) {
            lastErr = e;
            if (attempt < maxRetry) {
                const wait = 1000 * attempt; // 1s, 2s 退避
                console.log(`⚠️ 取 wx code 失败 (${attempt}/${maxRetry})，${wait}ms 后重试: ${e.message}`);
                await sleep(wait);
            }
        }
    }
    throw lastErr || new Error("取 wx code 失败");
}

// ========== 核心账号类 ==========
class TreeCoin {
    constructor(authCode, deviceFP, proxy = null, wxid = '') {
        this.authCode = authCode;
        this.deviceFP = deviceFP;
        this.proxy = proxy;
        this.wxid = wxid; // 微信协议账号标识（牛子 wxid_xxx / 应用宝 openid 或 openid#序号），用于取 wx code
        this.sessionId = null;
        this.cbcKey = null;
        this.userInfo = null;
        this.openid = ''; // 登录后从 userInfo 取
        this.userAgent = RISK_CONFIG.uaPool[Math.floor(Math.random() * RISK_CONFIG.uaPool.length)];
    }

    _getHeaders() {
        return {
            'User-Agent': this.userAgent,
            'Referer': 'https://treecoin.cn/home',
            'Origin': 'https://treecoin.cn',
            'X-Requested-With': 'com.tencent.mm',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'X-Device-Fingerprint': this.deviceFP
        };
    }

    _getRequestConfig() {
        const config = {
            headers: this._getHeaders(),
            timeout: RETRY_CONFIG.timeout
        };
        if (this.proxy && this.proxy !== 'DIRECT') {
            const [host, port] = this.proxy.split(':');
            config.proxy = { host, port: parseInt(port, 10) };
        }
        return config;
    }

    updateProxy(proxy) {
        this.proxy = proxy;
    }

    async login() {
        const res = await axios.post(`${BASE_URL}/auth/login-by-auth-code`, {
            authCode: this.authCode,
            device_fingerprint: this.deviceFP
        }, this._getRequestConfig());

        if (res.data.c !== 1) {
            const err = new Error(res.data.msg || '登录失败');
            err.businessError = true;
            throw err;
        }

        this.sessionId = res.data.data.session.sessionId;
        this.cbcKey = Buffer.from(res.data.data.session.sessionKey, 'base64');
        this.userInfo = res.data.data.user.dataValues;
        this.openid = this.userInfo.openid || this.userInfo.wxOpenid || this.userInfo.open_id || this.deviceFP;
        return this.userInfo;
    }

    cbcEncrypt(obj) {
        const plain = Buffer.from(JSON.stringify(obj), 'utf8');
        const iv = crypto.randomBytes(16);
        const cipher = crypto.createCipheriv('aes-256-cbc', this.cbcKey, iv);
        const encrypted = Buffer.concat([cipher.update(plain), cipher.final()]);
        return Buffer.concat([iv, encrypted]).toString('base64');
    }

    cbcDecrypt(b64) {
        const raw = Buffer.from(b64, 'base64');
        const decipher = crypto.createDecipheriv('aes-256-cbc', this.cbcKey, raw.slice(0, 16));
        const decrypted = Buffer.concat([decipher.update(raw.slice(16)), decipher.final()]);
        return JSON.parse(decrypted.toString('utf8'));
    }

    gcmEncrypt(obj) {
        const plain = Buffer.from(JSON.stringify(obj), 'utf8');
        const iv = crypto.randomBytes(12);
        const cipher = crypto.createCipheriv('aes-256-gcm', GCM_KEY, iv);
        const encrypted = Buffer.concat([cipher.update(plain), cipher.final()]);
        return {
            data: Buffer.concat([encrypted, cipher.getAuthTag()]).toString('hex'),
            iv: iv.toString('hex')
        };
    }

    async request(path, data = {}, isEncrypt = true) {
        let payload;
        if (isEncrypt) {
            payload = {
                sessionId: this.sessionId,
                encryptedData: this.cbcEncrypt(data),
                nonce: uuid(),
                timestamp: Date.now()
            };
        } else {
            payload = data; // 兼容不需要加密的接口（如 claimAd）
        }
        const res = await axios.post(`${BASE_URL}${path}`, payload, this._getRequestConfig());
        return res.data.encrypted ? this.cbcDecrypt(res.data.data) : res.data;
    }

    async prepareAd() {
        return await this.request('/app/ad-reward/prepare', {});
    }

    async claimAd(token) {
        // 取码标识优先级：账号自带 wxid（微信协议标识）> 登录后 openid > deviceFP > 全局 ENV_OPENID
        const identifier = this.wxid || this.openid || this.deviceFP || ENV_OPENID;
        const code = await getWxCode(identifier);
        console.log(`🌐 微信code: ${code}`);
        // 该接口不加密，传明文
        return await this.request('/app/ad-reward/claim', { token: token, wxCode: code }, true);
    }

    async signIn() {
        await this.request('/app/t', { deviceId: this.deviceFP });
        await randomDelay(RISK_CONFIG.signStepDelayMin, RISK_CONFIG.signStepDelayMax);

        const inner = this.gcmEncrypt({ token: '', deviceId: this.deviceFP });
        const outer = this.cbcEncrypt({ encryptedData: inner.data, iv: inner.iv });

        const payload = {
            sessionId: this.sessionId,
            encryptedData: outer,
            nonce: uuid(),
            timestamp: Date.now()
        };
        const res = await axios.post(`${BASE_URL}/app/signin`, payload, this._getRequestConfig());
        const result = res.data.encrypted ? this.cbcDecrypt(res.data.data) : res.data;

        if (result.c !== 1) {
            const err = new Error(result.msg || '签到失败');
            err.businessError = true;
            err.code = result.c;
            err.result = result;
            throw err;
        }
        return result;
    }

    async bindInviter(inviteCode) {
        return await this.request('/app/user/bind-inviter', { inviteCode: inviteCode });
    }

    isAdExhaustedError(msg) {
        if (!msg) return false;
        return /次数已用完|已用完|明天|刷新|没有更多|暂无|额外奖励/.test(msg);
    }

    isRateLimitError(msg) {
        if (!msg) return false;
        return /休息|等待|稍后再|频繁|过快|限流/.test(msg);
    }

    isProxyError(err) {
        if (!err) return false;
        const codes = ['ECONNRESET', 'ECONNREFUSED', 'EHOSTUNREACH', 'EPIPE', 'ECONNABORTED', 'ETIMEDOUT'];
        if (err.code && codes.includes(err.code)) return true;
        if (/timeout|ECONNRESET|ECONNREFUSED/i.test(err.message || '')) return true;
        return false;
    }
}

// ========== 广告任务逻辑 ==========
// 解析服务端冷却提示中的等待时长，如 "约4分55秒" / "5分钟" / "30秒"
function parseCooldownMs(msg) {
    if (!msg) return 0;
    let ms = 0;
    const min = msg.match(/(\d+)\s*分/);
    const sec = msg.match(/(\d+)\s*秒/);
    if (min) ms += parseInt(min[1], 10) * 60000;
    if (sec) ms += parseInt(sec[1], 10) * 1000;
    return ms;
}

async function watchAds(client, accountIdx, useProxy) {
    let totalReward = 0;
    let watchedCount = 0;
    let consecutiveErrors = 0;
    let proxyRetryCount = 0;
    let cooldownCount = 0;
    const log = (msg) => console.log(`[账号${accountIdx}] ${msg}`);

    for (let i = 1; i <= 5; i++) {
        let adCompleted = false;
        let retryCount = 0;

        // 冷却/限流不限重试次数（但设上限防死循环），其他错误最多重试 3 次
        while (!adCompleted && (retryCount < 3 || cooldownCount < 12)) {
            try {
                log(`📺 正在获取第 ${i}/5 个广告${retryCount > 0 ? ` (重试${retryCount})` : ''}...`);
                const prepareResult = await client.prepareAd();

                if (prepareResult.c !== 1) {
                    const errorMsg = prepareResult.msg || '未知错误';
                    if (client.isAdExhaustedError(errorMsg)) {
                        log(`⚠️ 今日广告奖励次数已用完`);
                        return { watchedCount, totalReward: totalReward.toFixed(2) };
                    }
                    // 冷却/限流：解析时长并等待，不计入失败次数
                    if (client.isRateLimitError(errorMsg)) {
                        cooldownCount++;
                        if (cooldownCount >= 12) {
                            log(`⚠️ 持续冷却/限流，放弃后续广告`);
                            return { watchedCount, totalReward: totalReward.toFixed(2) };
                        }
                        const cd = parseCooldownMs(errorMsg) || 60000;
                        log(`⏸️ 触发冷却/限流，等待 ${(cd / 1000).toFixed(0)}s 后继续...`);
                        await sleep(cd + Math.floor(Math.random() * 3000));
                        continue;
                    }
                    log(`⚠️ 获取广告失败: ${errorMsg}`);
                    retryCount++;
                    consecutiveErrors++;
                    await randomDelay(2000, 4000);
                    continue;
                }

                const { token, remaining, used, total } = prepareResult.data;
                if (remaining === 0) {
                    log(`⚠️ 今日广告已看完 (${used}/${total})`);
                    return { watchedCount, totalReward: totalReward.toFixed(2) };
                }

                log(`✅ 获取广告成功 (已看 ${used}/${total}, 剩余 ${remaining})`);
                const watchTime = Math.floor(Math.random() * 3000) + 3000;
                log(`⏳ 模拟观看 ${(watchTime / 1000).toFixed(1)} 秒...`);
                await sleep(watchTime);

                const claimResult = await client.claimAd(token);
                if (claimResult.c === 1) {
                    const reward = claimResult.data.reward;
                    totalReward += reward;
                    watchedCount++;
                    consecutiveErrors = 0;
                    adCompleted = true;
                    log(`🎉 获得奖励: +${reward} 树苗 (累计: +${totalReward.toFixed(2)})`);
                } else {
                    const claimMsg = claimResult.msg || '未知错误';
                    if (client.isAdExhaustedError(claimMsg)) {
                        log(`⚠️ 今日广告奖励次数已用完`);
                        return { watchedCount, totalReward: totalReward.toFixed(2) };
                    }
                    log(`⚠️ 领取奖励失败: ${claimMsg}`);
                    retryCount++;
                    consecutiveErrors++;
                    await randomDelay(2000, 4000);
                }
            } catch (err) {
                if (useProxy && client.isProxyError(err) && proxyRetryCount < MAX_PROXY_RETRIES) {
                    proxyRetryCount++;
                    log(`🔄 代理异常，第 ${proxyRetryCount} 次更换IP...`);
                    const newProxy = await getOneProxyFromPool();
                    if (newProxy) {
                        client.updateProxy(newProxy);
                        continue;
                    }
                }
                log(`❌ 出错: ${err.message}`);
                consecutiveErrors++;
                retryCount++;
                await randomDelay(2000, 4000);
            }
        }
        if (i < 5 && adCompleted) {
            await randomDelay(RISK_CONFIG.adDelayMin, RISK_CONFIG.adDelayMax);
        }
    }
    return { watchedCount, totalReward: totalReward.toFixed(2) };
}

// ========== 并发限制函数 ==========
async function limitedParallel(tasks, limit) {
    const results = [];
    const running = [];
    for (const task of tasks) {
        const p = Promise.resolve().then(task);
        results.push(p);
        if (running.push(p) > limit) {
            await Promise.race(running);
            running.splice(running.findIndex(r => r !== p), 1);
        }
    }
    return Promise.allSettled(results);
}

// ========== 主程序流程 ==========
(async () => {
    process.on('unhandledRejection', (reason) => {
        console.error(`❌ 全局未捕获异常: ${reason?.message || reason}`);
    });

    const accounts = parseAccounts();
    if (accounts.length === 0) {
        console.log('❌ 未配置环境变量 TREECOIN_AUTH / TREECOIN_AUTH_CODE');
        process.exit(1);
    }

    // 共享微信协议账号池，按索引与绿树账号配对
    const wxIds = parseWxIds();
    if (wxIds.length === 0) {
        console.log('⚠️ 未配置 WX_ID，广告领奖将回退到 openid/deviceFP（可能共用同一微信号）');
    } else if (wxIds.length < accounts.length) {
        console.log(`⚠️ WX_ID 共 ${wxIds.length} 个，少于绿树账号 ${accounts.length} 个，多出的账号将复用第1个 WX_ID`);
    }

    const useProxy = !!PROXY_API_URL;
    console.log(`🌲 绿树田园综合任务启动（先广告，后签到）`);
    console.log(`📋 账号总数：${accounts.length}`);
    console.log(`🌐 代理模式：${useProxy ? '启用' : '直连'}`);
    console.log();

    // ──────────────────────────────────────────
    // 第一阶段：依次登录所有账号
    // ──────────────────────────────────────────
    console.log('═══════════════════════════════════');
    console.log('📌 第一阶段：依次登录账号并初始化');
    console.log('═══════════════════════════════════');
    console.log();

    const clients = [];
    let loginSuccess = 0, loginFail = 0;

    for (let i = 0; i < accounts.length; i++) {
        const idx = i + 1;
        console.log(`───── 账号 ${idx}/${accounts.length} ─────`);
        let proxy = useProxy ? await getOneProxyFromPool() : 'DIRECT';
        // 取码标识：优先账号自带 wxid（TREECOIN_AUTH 第3字段），否则按索引取共享 WX_ID 同位置账号
        const wxid = accounts[i].wxid || wxIds[i] || (wxIds.length ? wxIds[0] : '');
        let client = new TreeCoin(accounts[i].authCode, accounts[i].deviceFP, proxy, wxid);

        try {
            console.log('🔑 登录中...');
            await client.login();
            console.log(`✅ 登录成功 | 昵称: ${client.userInfo.nickName} | 树苗: ${client.userInfo.vitality}`);
            loginSuccess++;
            clients.push({ client, idx });
        } catch (e) {
            console.log(`❌ 登录失败: ${e.message}`);
            loginFail++;
        }

        console.log();
        if (i < accounts.length - 1) {
            await randomDelay(RISK_CONFIG.accountDelayMin, RISK_CONFIG.accountDelayMax);
        }
    }

    notifyLog(`📊 登录汇总：成功 ${loginSuccess} | 失败 ${loginFail}`);
    console.log();

    if (clients.length === 0) {
        console.log('❌ 没有可用账号，任务终止');
        return;
    }

    // ──────────────────────────────────────────
    // 第二阶段：刷完所有广告任务
    // ──────────────────────────────────────────
    console.log('═══════════════════════════════════');
    console.log('📌 第二阶段：开始观看广告（受控并发）');
    console.log('═══════════════════════════════════');
    console.log();

    const adTaskList = clients.map(({ client, idx }) => async () => {
        return await watchAds(client, idx, useProxy);
    });

    const adResults = await limitedParallel(adTaskList, MAX_AD_CONCURRENT);
    let totalAdWatched = 0;
    let totalAdReward = 0;

    console.log('───────────────────────────────────');
    adResults.forEach((result, i) => {
        const idx = clients[i].idx;
        if (result.status === 'fulfilled') {
            const { watchedCount, totalReward } = result.value;
            totalAdWatched += watchedCount;
            totalAdReward += parseFloat(totalReward);
            console.log(`[账号${idx}] 观看 ${watchedCount}/5 个, 获得 +${totalReward} 树苗`);
        } else {
            console.log(`[账号${idx}] 广告任务异常: ${result.reason?.message || '未知错误'}`);
        }
    });
    console.log('───────────────────────────────────');
    notifyLog(`📊 广告汇总：共观看 ${totalAdWatched} 个, 总计 +${totalAdReward.toFixed(2)} 树苗`);
    console.log();

    // ──────────────────────────────────────────
    // 第三阶段：广告全部完成后，执行签到与绑定邀请码
    // ──────────────────────────────────────────
    console.log('═══════════════════════════════════');
    console.log('📌 第三阶段：开始执行签到及绑定邀请码');
    console.log('═══════════════════════════════════');
    console.log();

    let signSuccess = 0, signFail = 0;

    for (let i = 0; i < clients.length; i++) {
        const { client, idx } = clients[i];
        console.log(`───── 账号 ${idx}/${clients.length} 签到 ─────`);

        try {
            // 绑定邀请码
            if (ENABLE_BIND_INVITER && INVITE_CODE) {
                console.log(`🔗 绑定邀请码 ${INVITE_CODE} ...`);
                try {
                    const bindResult = await client.bindInviter(INVITE_CODE);
                    if (bindResult.c === 1) {
                        console.log('✅ 邀请码绑定成功');
                    } else {
                        console.log(`🔒 邀请码绑定提示: ${bindResult.msg || '已绑定或无需绑定'}`);
                    }
                } catch (bindErr) {
                    console.log(`🔒 邀请码绑定跳过: ${bindErr.message}`);
                }
                await randomDelay(RISK_CONFIG.actionDelayMin, RISK_CONFIG.actionDelayMax);
            }

            // 签到
            console.log('📝 签到中...');
            const signResult = await client.signIn();
            if (signResult.c === 1) {
                const data = signResult.data || signResult;
                console.log('🎉 签到成功');
                if (data.increase) console.log(`🌱 获得树苗: +${data.increase}`);
                if (data.continuousReward) console.log(`🎁 连续奖励: +${data.continuousReward}`);
                signSuccess++;
            }
        } catch (e) {
            if (e.message && /已签/.test(e.message)) {
                console.log('⚠️ 今日已签到');
                signSuccess++;
            } else {
                console.log(`❌ 签到失败: ${e.message}`);
                signFail++;
            }
        }

        console.log();
        if (i < clients.length - 1) {
            await randomDelay(RISK_CONFIG.accountDelayMin, RISK_CONFIG.accountDelayMax);
        }
    }

    console.log('═══════════════════════════════════');
    notifyLog(`📊 签到汇总：成功 ${signSuccess} | 失败 ${signFail}`);
    console.log('✅ 全部账号任务完整执行完毕');
    console.log('═══════════════════════════════════');

    // ── 青龙推送通知 ──
    try {
        if (typeof sendNotify === 'function' && notifyLines.length > 0) {
            await sendNotify('🌲 绿树田园', notifyLines.join('\n'));
        }
    } catch (e) {
        console.log(`⚠️ 通知发送失败: ${e.message}`);
    }
})();
