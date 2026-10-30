// name:红色火箭
// cron: 1 9,13 * * *
//  红色火箭（华泰基金指慧家）

//  环境变量：
//    YYB_SERVER         必填，格式：地址@账号ref，多账号换行
//    YYB_API_KEY / YYB_PROTOCOL_TOKEN  可选，启用协议鉴权时配置
//    WX_ID              可选，仅运行指定ref，格式：ref#备注，多账号换行或 & 分隔
//    WECHAT_SERVER      可选，旧微信协议服务回退地址
//    HSJJ_NOTIFY        可选，0关闭通知；默认调用青龙sendNotify，仅推送账号汇总
//    2026-10-30 手动领取版：签到、口令兑换、积分与红包记录查询。
//    获得现金红包后请到小程序手动领取；不包含自动提现、领取或H5授权代码。


'use strict';

const axios = require('axios');
const fs = require('fs');
const pathMod = require('path');

// ==================== 内置 YYB-Go-Enhanced 适配 ====================
function getYybEntries() {
    return String(process.env.YYB_SERVER || '')
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(Boolean)
        .map(line => {
            const at = line.lastIndexOf('@');
            if (at < 1) return null;
            let server = line.slice(0, at).trim().replace(/\/+$/, '');
            const ref = line.slice(at + 1).trim();
            if (!server || !ref) return null;
            if (!/^https?:\/\//i.test(server)) server = `http://${server}`;
            return { server, ref };
        })
        .filter(Boolean);
}

const YYB_ENTRIES = getYybEntries();
if (!process.env.WX_ID && YYB_ENTRIES.length) {
    process.env.WX_ID = YYB_ENTRIES.map(item => item.ref).join('\n');
}

function findYybEntry(identifier) {
    const raw = String(identifier || '').split('#')[0].trim();
    return YYB_ENTRIES.find(item => item.ref === raw || `${item.server}@${item.ref}` === raw) || null;
}

function selectYybEntry(identifier) {
    if (!YYB_ENTRIES.length) {
        throw new Error('未配置 YYB_SERVER，格式：地址@账号ref，多账号换行');
    }
    const raw = String(identifier || '').split('#')[0].trim();
    const found = findYybEntry(raw);
    if (found) return found;
    if (YYB_ENTRIES.length === 1) return YYB_ENTRIES[0];
    throw new Error(`YYB_SERVER 中找不到账号ref：${raw}`);
}

function _yybAuthHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const token = String(process.env.YYB_API_KEY || '').trim() || String(process.env.YYB_PROTOCOL_TOKEN || '').trim();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
}

async function yybPost(identifier, appId, route, payload) {
    const item = selectYybEntry(identifier);
    const body = { ref: item.ref, app_id: appId };
    if (payload !== undefined) body.payload = payload;
    const response = await axios.post(`${item.server}${route}`, body, {
        timeout: 30000,
        proxy: false,
        validateStatus: () => true,
        headers: _yybAuthHeaders(),
    });
    const data = response.data || {};
    if (response.status < 200 || response.status >= 300) {
        throw new Error(data.error || data.msg || `YYB请求失败（HTTP ${response.status}）`);
    }
    if (Object.prototype.hasOwnProperty.call(data, 'code') && ![0, '0', null, undefined].includes(data.code)) {
        throw new Error(data.error || data.msg || 'YYB请求失败');
    }
    const result = data.result || (data.data && data.data.result);
    if (!result || typeof result !== 'object') throw new Error('YYB响应缺少result');
    return result;
}

async function getSingleCode(appId, identifier) {
    try {
        const result = await yybPost(identifier, appId, '/wxapp/getCode');
        if (!result.code) throw new Error('YYB未返回有效code');
        return result.code;
    } catch (error) {
        throw new Error('小程序取码失败：' + error.message);
    }
}

const getWxCode = (wxid, appid) => getSingleCode(appid, String(wxid).split('#')[0].trim());

const BASE_URL = 'https://index.amcfortune.com';

// ==================== 配置区 ====================
let ckName = "WX_ID";
let taskVar = process.env.WX_ID || '';
const WECHAT_SERVER = (process.env.WECHAT_SERVER || '').replace(/\/$/, '');
const debug = process.env.debug || 0;
const APPID = 'wx1b44c3ad181bde16';
const ACTIVITY_PAGE_ID = process.env.HSJJ_ACTIVITY_PAGE_ID || '7541';

const CACHE_DIR = pathMod.join(__dirname, '.cache');
const ACCOUNT_CACHE_FILE = pathMod.join(CACHE_DIR, 'hsjj_accounts.json');

// ==================== 青龙通知：正文仅包含账号汇总 ====================
function log(str) { console.log(str); }

function loadQinglongNotifier() {
    // 仅影响本脚本进程，避免青龙通知模块追加随机句子。
    process.env.HITOKOTO = 'false';
    const candidates = [
        '/ql/data/scripts/sendNotify.js', '/ql/data/deps/sendNotify.js', '/ql/scripts/sendNotify.js',
        pathMod.join(__dirname, 'sendNotify.js'), pathMod.join(__dirname, '..', 'sendNotify.js'),
        pathMod.join(__dirname, '..', '..', 'sendNotify.js'), 'sendNotify',
    ];
    for (const filename of candidates) {
        try {
            const notifier = require(filename);
            if (typeof notifier?.sendNotify === 'function') return notifier;
        } catch {}
    }
    return null;
}

function formatAccountSummary(account) {
    const display = account.note || account.wxid;
    if (!account.completed) return '当前账号: ' + display + ' 执行失败，余额未验证（不记为0）';
    const currentPoint = account.currentPoint ?? '查询失败';
    const historyAmount = Math.max(account.historyRedPacketAmount || 0, account.redPacketAmount || 0);
    const pendingAmount = account.pendingRedPacketAmount || 0;
    return '当前账号: ' + display + ' 当前积分: ' + currentPoint
        + ' 后端红包记录累计:' + formatMoney(historyAmount) + '元'
        + ' 需手动领取红包: ' + formatMoney(pendingAmount) + '元'
        + (account.ok === false ? '（部分任务未完成）' : '');
}

async function push_notification(summaryLines = []) {
    if (process.env.HSJJ_NOTIFY === '0') return;
    if (!summaryLines.length) { log('ℹ️ 没有账号汇总，跳过通知'); return; }
    const notifier = loadQinglongNotifier();
    if (!notifier) { log('⚠️ 未找到可用的青龙sendNotify模块，账号汇总保留在运行日志'); return; }
    const title = '红色火箭（华泰基金）';
    const content = ['📋 账号汇总:', ...summaryLines].join('\n');
    try {
        await notifier.sendNotify(title, content);
        log('✅ 账号汇总已提交青龙通知模块');
    } catch (error) {
        log('⚠️ 青龙通知调用失败: ' + (error.code || '通知模块异常'));
    }
}

// ==================== SM4 加密（从逆向代码移植） ====================
const SM4_SBOX = [214,144,233,254,204,225,61,183,22,182,20,194,40,251,44,5,43,103,154,118,42,190,4,195,170,68,19,38,73,134,6,153,156,66,80,244,145,239,152,122,51,84,11,67,237,207,172,98,228,179,28,169,201,8,232,149,128,223,148,250,117,143,63,166,71,7,167,252,243,115,23,186,131,89,60,25,230,133,79,168,104,107,129,178,113,100,218,139,248,235,15,75,112,86,157,53,30,36,14,94,99,88,209,162,37,34,124,59,1,33,120,135,212,0,70,87,159,211,39,82,76,54,2,231,160,196,200,158,234,191,138,210,64,199,56,181,163,247,242,206,249,97,21,161,224,174,93,164,155,52,26,85,173,147,50,48,245,140,177,227,29,246,226,46,130,102,202,96,192,41,35,171,13,83,78,111,213,219,55,69,222,253,142,47,3,255,106,114,109,108,91,81,141,27,175,146,187,221,188,127,17,217,92,65,31,16,90,216,10,193,49,136,165,205,123,189,45,116,208,18,184,229,180,176,137,105,151,74,12,150,119,126,101,185,241,9,197,110,198,132,24,240,125,236,58,220,77,32,121,238,95,62,215,203,57,72];

function sm4Rotl32(x, n) {
    return ((x << n) | (x >>> (32 - n))) >>> 0;
}

function sm4Sbox(x) {
    return (255 & SM4_SBOX[x >>> 24 & 255]) << 24 |
           (255 & SM4_SBOX[x >>> 16 & 255]) << 16 |
           (255 & SM4_SBOX[x >>> 8 & 255]) << 8 |
           (255 & SM4_SBOX[255 & x]);
}

function sm4L(x) {
    return (x ^ sm4Rotl32(x, 2) ^ sm4Rotl32(x, 10) ^ sm4Rotl32(x, 18) ^ sm4Rotl32(x, 24)) >>> 0;
}

function sm4L2(x) {
    return (x ^ sm4Rotl32(x, 13) ^ sm4Rotl32(x, 23)) >>> 0;
}

function sm4KeyExp(key) {
    const CK = [462357,472066609,943670861,1415275113,1886879365,2358483617,2830087869,3301692121,3773296373,4228057617,404694573,876298825,1347903077,1819507329,2291111581,2762715833,3234320085,3705924337,4177462797,337322537,808926789,1280531041,1752135293,2223739545,2695343797,3166948049,3638552301,4110090761,269950501,741554753,1213159005,1684763257];
    const MK = [2746333894, 1453994832, 1736282519, 2993693404];

    const K = new Array(36);
    for (let i = 0; i < 4; i++) {
        K[i] = ((key[4*i] << 24) | (key[4*i+1] << 16) | (key[4*i+2] << 8) | key[4*i+3]) >>> 0;
        K[i] = (K[i] ^ MK[i]) >>> 0;
    }

    const rk = new Array(32);
    for (let i = 0; i < 32; i++) {
        const tmp = (K[i+1] ^ K[i+2] ^ K[i+3] ^ CK[i]) >>> 0;
        K[i+4] = (K[i] ^ sm4L2(sm4Sbox(tmp))) >>> 0;
        rk[i] = K[i+4];
    }
    return rk;
}

function sm4EncryptBlock(block, rk) {
    const X = new Array(4);
    for (let i = 0; i < 4; i++) {
        X[i] = ((block[4*i] << 24) | (block[4*i+1] << 16) | (block[4*i+2] << 8) | block[4*i+3]) >>> 0;
    }

    for (let i = 0; i < 32; i += 4) {
        let tmp;
        tmp = (X[1] ^ X[2] ^ X[3] ^ rk[i]) >>> 0;
        X[0] = (X[0] ^ sm4L(sm4Sbox(tmp))) >>> 0;
        tmp = (X[2] ^ X[3] ^ X[0] ^ rk[i+1]) >>> 0;
        X[1] = (X[1] ^ sm4L(sm4Sbox(tmp))) >>> 0;
        tmp = (X[3] ^ X[0] ^ X[1] ^ rk[i+2]) >>> 0;
        X[2] = (X[2] ^ sm4L(sm4Sbox(tmp))) >>> 0;
        tmp = (X[0] ^ X[1] ^ X[2] ^ rk[i+3]) >>> 0;
        X[3] = (X[3] ^ sm4L(sm4Sbox(tmp))) >>> 0;
    }

    const out = new Array(16);
    for (let i = 0; i < 4; i++) {
        out[4*(3-i)] = X[i] >>> 24 & 255;
        out[4*(3-i)+1] = X[i] >>> 16 & 255;
        out[4*(3-i)+2] = X[i] >>> 8 & 255;
        out[4*(3-i)+3] = 255 & X[i];
    }
    return out;
}

function sm4Pkcs7Pad(data) {
    const padLen = 16 - (data.length % 16);
    return [...data, ...new Array(padLen).fill(padLen)];
}

function sm4Encrypt(plaintext, keyBytes) {
    const rk = sm4KeyExp(keyBytes);
    const padded = sm4Pkcs7Pad(Buffer.from(plaintext, 'utf8'));
    let result = [];
    for (let i = 0; i < padded.length; i += 16) {
        const block = padded.slice(i, i + 16);
        result = result.concat(sm4EncryptBlock(block, rk));
    }
    return result.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ==================== 通用函数 ====================
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function randomInt(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
function ensureCacheDir() { if (!fs.existsSync(CACHE_DIR)) fs.mkdirSync(CACHE_DIR, { recursive: true }); }

// 金额格式化：避免 JS 浮点数出现 3.379999999 这类显示问题。
function formatMoney(n) {
    const value = Number(n || 0);
    return (Math.round(value * 100) / 100).toFixed(2).replace(/\.?0+$/, '');
}

function hexToBytes(hex) {
    const bytes = [];
    for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
    return bytes;
}

// 签名算法：排序参数 -> 拼接 -> MD5 -> Base64
function buildSignature(params) {
    const sortedKeys = Object.keys(params).sort();
    const sortedStr = sortedKeys.map(k => k + '=' + params[k]).join('&');
    const md5Hash = require('crypto').createHash('md5').update(sortedStr).digest('hex');
    return Buffer.from(md5Hash).toString('base64');
}

function todayMMdd() {
    return new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit' }).format(new Date()).split('/').reverse().join('');
}

function buildDailyRegisterChannel() {
    return `&s=red&m=daily&c=${todayMMdd()}`;
}

/**
 * 从首页内容里动态发现红色火箭对口令活动入口。
 * HAR 中页面 ID 来源是 findPageContent 返回的 skipAddr：
 * amcfundex://product/fanactivity?id= 7541&s=red&m=daily&c=0623
 */
function extractFanActivityFromHome(data) {
    const today = todayMMdd();
    const candidates = [];
    const walk = (node) => {
        if (!node) return;
        if (typeof node === 'string') {
            if (/fanactivity/i.test(node) && /s=red/i.test(node) && /m=daily/i.test(node)) {
                candidates.push(node);
            }
            return;
        }
        if (Array.isArray(node)) return node.forEach(walk);
        if (typeof node === 'object') Object.values(node).forEach(walk);
    };
    walk(data);
    const preferred = candidates.find(x => new RegExp(`c\\s*=\\s*${today}`).test(x)) || candidates[0] || '';
    const idMatch = preferred.match(/[?&]id\s*=\s*([0-9]+)/i);
    const cMatch = preferred.match(/[?&]c\s*=\s*([0-9]{4})/i);
    return {
        pageId: idMatch ? idMatch[1] : '',
        registerChannel: cMatch ? `&s=red&m=daily&c=${cMatch[1]}` : buildDailyRegisterChannel(),
        skipAddr: preferred,
    };
}

function buildHeaders(data, token, encryptVer, openId, userId, appSecret, options = {}) {
    const timestamp = '' + Date.now();
    const nonce = '' + (1e6 * Math.random()).toFixed(0) + (1e6 * Math.random()).toFixed(0);
    const signParams = { ...data, nonce, timestamp, appSecret: appSecret || '', ticket: token || '' };
    return {
        'Content-Type': 'application/json',
        'timestamp': timestamp,
        'nonce': nonce,
        'signature': buildSignature(signParams),
        'key_version': encryptVer || '',
        'openid': openId || '',
        'pro': 'RedRocket',
        'Bank-Type': 'main',
        // 0624 抓包为 Windows 小程序环境；保持和真实运行态一致，避免部分接口返回 7005。
        'pla': 'rr_windows',
        'ver': '1.48.7',
        'mini_program': 'wechat',
        // 默认空；doExchange 这类活动接口再按当天动态传入，例如 &s=red&m=daily&c=0623。
        'register_channel': options.registerChannel || '',
        'click_id': '',
        'user_id': userId || '',
        'Referer': 'https://servicewechat.com/' + APPID + '/205/page-frame.html',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254186b) XWEB/19841',
        'key_version': String(encryptVer || ''),
        'openid': openId || '',
        'ticket': token || '',
    };
}

// ==================== 缓存层 ====================
function loadCache() {
    try { return JSON.parse(fs.readFileSync(ACCOUNT_CACHE_FILE, 'utf8')) || {}; }
    catch { return {}; }
}
function saveCache(data) {
    try { ensureCacheDir(); const temp = ACCOUNT_CACHE_FILE + '.tmp'; fs.writeFileSync(temp, JSON.stringify(data, null, 2), { encoding: 'utf8', mode: 0o600 }); fs.renameSync(temp, ACCOUNT_CACHE_FILE); fs.chmodSync(ACCOUNT_CACHE_FILE, 0o600); return true; }
    catch (e) { log('保存缓存失败: ' + (e.code || '文件写入失败')); return false; }
}

function getCache(cache, key) {
    const v = cache[key];
    return (v && typeof v === 'object') ? v : null;
}
function putCache(cache, key, value) {
    cache[key] = { ...cache[key], ...value, updateTime: new Date().toISOString() };
}
/**
 * 缓存微信平台返回的 encryptKey/version。
 * 前端 handleCryptoData 会把 encryptKey 按 version 放进 encryptioVerCfg；这里同步保存，
 * 下次优先使用缓存，只有缺失时才重新调用协议服务。
 */
function getEncryptKeyCache(cache, key) {
    const cached = getCache(cache, key);
    if (!cached) return { encryptKey: '', version: '' };
    if (cached.encryptExpireTime && Number(cached.encryptExpireTime) <= Date.now()) return { encryptKey: '', version: '' };
    if (cached.encryptKey && cached.encryptVer) {
        return { encryptKey: cached.encryptKey, version: String(cached.encryptVer), expireTime: cached.encryptExpireTime || '' };
    }
    const cfg = cached.encryptKeyCfg || {};
    const versions = Object.keys(cfg);
    if (!versions.length) return { encryptKey: '', version: '' };
    const version = String(cached.encryptVer || versions[versions.length - 1]);
    return { encryptKey: cfg[version] || '', version, expireTime: cached.encryptExpireTime || '' };
}

function putEncryptKeyCache(cache, key, data) {
    if (!cache || !key || !data) return;
    const version = String(data.version || data.encryptVer || '');
    const encryptKey = data.encryptKey || '';
    const cached = getCache(cache, key) || {};
    const encryptKeyCfg = { ...(cached.encryptKeyCfg || {}) };
    if (encryptKey && version) encryptKeyCfg[version] = encryptKey;
    putCache(cache, key, { encryptKey, encryptVer: version, encryptExpireTime: data.expireTime || '', encryptKeyCfg });
}

// ==================== HTTP 请求 ====================
function createAxios(token) {
    return axios.create({
        baseURL: BASE_URL,
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.70',
        },
        timeout: 30000
    });
}

async function apiRequest(method, url, data, token, encryptVer, openId, userId, appSecret, retries = 1, options = {}) {
    try {
        const headers = buildHeaders(data || {}, token, encryptVer, openId, userId, appSecret, options);
        const config = { method, url: BASE_URL + url, headers, timeout: 30000, proxy: false };
        if (method === 'POST') config.data = data;
        else config.params = { ...data, key: Date.now() };
        const resp = await axios(config);
        if (debug) log('[API] ' + url + ' code=' + resp.data?.code);
        return resp.data;
    } catch (e) {
        const status = e?.response?.status || 0;
        const body = e?.response?.data;
        const text = typeof body === 'string' ? body : JSON.stringify(body || '');
        if (status === 429 || /访问过于频繁|请稍后再试|系统繁忙|请求过于频繁|操作过于频繁/.test(text)) {
            if (retries > 0) {
                const waitMs = 5000 + randomInt(0, 2000);
                log(`  ⚠️ 频率限制(${status || 'body'})，${Math.round(waitMs / 1000)}秒后重试: ${url}`);
                await sleep(waitMs);
                return await apiRequest(method, url, data, token, encryptVer, openId, userId, appSecret, retries - 1, options);
            }
        }
        if (retries > 0 && method === 'GET') {
            await sleep(1500);
            log('  请求失败，重试... ' + (e.code || '网络错误'));
            return await apiRequest(method, url, data, token, encryptVer, openId, userId, appSecret, retries - 1, options);
        }
        log('  请求失败: ' + url + ' - ' + (e.code || ('HTTP ' + status)));
        return null;
    }
}

// ==================== 微信登录 ====================
// 使用脚本内置 YYB-Go-Enhanced 接口

// ==================== 业务逻辑 ====================

// 获取手机号授权code
async function getPhoneCodeInfo(wxid) {
    const cleanWxid = String(wxid).split('#')[0].trim();
    const isYyb = Boolean(findYybEntry(cleanWxid)) || /^\d+$/.test(cleanWxid) || /^o[a-zA-Z0-9_-]{20,}$/.test(cleanWxid);

    let respData;
    if (isYyb) {
        // 使用 YYB 协议获取手机号 code
        const entry = selectYybEntry(cleanWxid);
        const resolvedRef = entry.ref;
        const url = entry.server + '/wxapp/getPhoneNumber';

        if (debug) log(`[YYB] 请求手机号code: ref=${resolvedRef}, app_id=${APPID}`);
        const resp = await axios.post(url, { ref: resolvedRef, app_id: APPID }, {
            headers: _yybAuthHeaders(),
            timeout: 30000,
            validateStatus: () => true
        });
        respData = resp.data;
    } else {
        const resp = await axios.post(WECHAT_SERVER + '/api/v1/wx/app/get/all/mobile', {
            wxid: cleanWxid,
            appid: APPID,
            data: JSON.stringify({ api_name: 'webapi_getuserwxphone', with_credentials: true }),
            opt: 1
        });
        respData = resp.data;
    }

    if (respData && (respData.Code === 0 || respData.code === 0 || respData.Success === true || respData.Data || respData.result || respData.openid)) {
        // 从返回中提取 hex 格式 phoneCode，同时尽量提取明文手机号用于日志展示。
        let mobile = '';
        const walk = (node, depth = 0) => {
            if (depth > 8 || node == null) return null;
            if (typeof node === 'string') {
                if (/^[0-9a-f]{32,256}$/i.test(node)) return node;
                if (!mobile && /^1\d{10}$/.test(node)) mobile = node;
                try { return walk(JSON.parse(node), depth + 1); } catch { return null; }
            }
            if (Array.isArray(node)) { for (const x of node) { const r = walk(x, depth+1); if (r) return r; } return null; }
            if (typeof node === 'object') {
                for (const [k, v] of Object.entries(node)) {
                    const key = k.toLowerCase();
                    if (!mobile && (key.includes('mobile') || key.includes('phone')) && typeof v === 'string' && /^1\d{10}$/.test(v)) {
                        mobile = v;
                    }
                    if (key.includes('phonecode') || key === 'code') {
                        if (typeof v === 'string' && /^[0-9a-f]{32,256}$/i.test(v)) return v;
                    }
                    const r = walk(v, depth + 1);
                    if (r) return r;
                }
            }
            return null;
        };
        const phoneCode = walk(respData);
        if (phoneCode) return { phoneCode, mobile };
    }
    log('  ⚠️ 获取手机号code失败，code=' + (respData?.code ?? respData?.Code ?? '无响应'));
    return { phoneCode: '', mobile: '' };
}

async function getPhoneCode(wxid) {
    const info = await getPhoneCodeInfo(wxid);
    return info.phoneCode;
}

// 缓存 CK 有效但旧缓存没有手机号时，只补手机号，不触发业务重登。
async function fillCachedMobileIfMissing(wxid, cache, cacheKey) {
    const cached = getCache(cache, cacheKey);
    if (cached?.mobile) return cached.mobile;
    try {
        const phoneInfo = await getPhoneCodeInfo(wxid);
        if (phoneInfo.mobile) {
            putCache(cache, cacheKey, { mobile: phoneInfo.mobile });
            saveCache(cache);
            return phoneInfo.mobile;
        }
    } catch (e) {
        if (debug) log('  ⚠️ 补手机号失败: ' + e.message);
    }
    return '';
}

// 重新走一遍协议登录链路，避免签到/兑换时因为 7005 直接失败。
async function refreshProtocolSession(wxid, cache, cacheKey, reason = '') {
    if (reason) log('  🔄 准备重新协议登录: ' + reason);
    const code = await getWxCode(wxid, APPID);
    const ids = await getOpenIdAndUnionId(code);
    const phoneInfo = await getPhoneCodeInfo(wxid);
    const phoneCode = phoneInfo.phoneCode;
    if (!phoneCode) throw new Error('手机号授权code获取失败，保留原登录缓存');
    const loginData = await login(phoneCode, ids.openId, ids.unionId);
    if (!loginData) return null;
    putCache(cache, cacheKey, {
        token: loginData.token,
        openId: ids.openId,
        unionId: ids.unionId,
        userId: loginData.userId,
        mobile: phoneInfo.mobile || '',
        encryptUserId: loginData.encryptUserId || '',
        isRegister: loginData.isRegister || '',
    });
    saveCache(cache);
    return {
        token: loginData.token,
        openId: ids.openId,
        unionId: ids.unionId,
        userId: loginData.userId,
        mobile: phoneInfo.mobile || '',
        loginData,
    };
}

async function login(phoneCode, openId, unionId) {
    const resp = await apiRequest('POST', '/fundex-uc/uc/v1/login', {
        loginWay: 'miniprogram',
        platform: 'mini_fundex',
        code: phoneCode,
        openId,
        unionId,
        signAgreement: '阅读并同意用户协议、隐私政策，未注册的手机号认证后自动创建新账户',
        registerChannel: ''
    }, '');
    if ((resp?.code === '200' || resp?.code == 200 || resp?.code === '0' || resp?.code == 0 || resp?.data?.token) && resp?.data?.token) {
        return {
            token: resp.data.token,
            userId: resp.data.userId,
            encryptUserId: resp.data.encryptUserId,
            isRegister: resp.data.isRegister
        };
    }
    const respStr = typeof resp === 'string' ? resp : JSON.stringify(resp);
    log('  登录失败: ' + (resp?.message ? resp.message + ' - ' : '') + respStr);
    return null;
}

async function getOpenIdAndUnionId(code) {
    if (!code) throw new Error('小程序取码为空，保留原缓存并停止该账号');
    const headers = buildHeaders({ code }, '', '');
    const resp = await axios.post(BASE_URL + '/fundex-uc/uc/v1/getWxOpenIdAndUnionId', { code }, { headers });
    if (resp.data?.code === '200' && resp.data?.data?.openId) {
        return { openId: resp.data.data.openId, unionId: resp.data.data.unionId };
    }
    throw new Error('获取小程序身份失败，code=' + resp.data?.code);
}

// 校验缓存登录态：能正常访问轻量接口就认为 token/openId/userId 可用。
async function checkCachedLogin(cached) {
    if (!cached?.token || !cached?.openId || !cached?.userId) return false;
    const resp = await apiRequest('GET', '/fundex-activity/point/sign/getRecordList', {}, cached.token, '', cached.openId, cached.userId, '', 0);
    if (!resp) return null;
    if (String(resp.code) === '200') return true;
    if (/^(401|403|407)$/.test(String(resp.code))) return false;
    return null;
}

// 动态获取页面活动 ID 和渠道参数，失败才兜底使用默认页面 ID/当天渠道。
async function discoverActivityEntry(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-index/opportunity/v3/findPageContent', {
        orderBy: 'changePercent',
        classA: '02',
        order: 'desc',
        platform: '',
        openId,
    }, token, '', openId, userId, '', 1);
    if (!resp || String(resp.code) !== '200') throw new Error('首页活动查询失败，停止兑换，避免使用过期活动');
    const found = extractFanActivityFromHome(resp?.data || {});
    if (found.pageId) {
        log(`  🧭 动态活动入口: pageId=${found.pageId} channel=${found.registerChannel}`);
        return found;
    }
    // 再兜底：直接扫全量字符串，只要有 fanactivity 且带 id 就认。
    const flat = JSON.stringify(resp?.data || {});
    const hit = flat.match(/fanactivity[^"]*?[?&]id\s*=\s*([0-9]+)[^"]*?[&?]s\s*=\s*red[^"]*?[&?]m\s*=\s*daily[^"]*?[&?]c\s*=\s*([0-9]{4})/i);
    if (hit) {
        const pageId = hit[1];
        const channel = `&s=red&m=daily&c=${hit[2]}`;
        log(`  🧭 动态活动入口(宽松匹配): pageId=${pageId} channel=${channel}`);
        return { pageId, registerChannel: channel, skipAddr: '' };
    }
    if (process.env.HSJJ_ACTIVITY_PAGE_ID) return { pageId: ACTIVITY_PAGE_ID, registerChannel: buildDailyRegisterChannel(), skipAddr: '' };
    log('  ℹ️ 首页暂无口令活动入口');
    return { pageId: '', unavailable: true };
}

// 获取加密密钥配置
async function getEncryptConfig(token, openId) {
    const resp = await apiRequest('GET', '/fundex-material/knowledgeBase/findKnowledgeInfoListByKeyList', { knowledgeKeyList: 'secure_path' }, token, '', openId);
    if (resp?.code === '200' && Array.isArray(resp?.data)) {
        const content = resp.data[0]?.knowledgeContent || '';
        return content.split(',').filter(Boolean);
    }
    return [];
}

// 获取加密密钥：先尝试养鸡场“最新用户key”接口，失败再兜底调用小程序的 getUserCryptoManager。
async function getEncryptKey(wxid) {
    const cleanRef = String(wxid).split('#')[0].trim();
    let result;
    if (findYybEntry(cleanRef)) {
        result = await yybPost(cleanRef, APPID, '/wxapp/operateWxData', { api_name: 'webapi_getuserencryptkey' });
    } else {
        if (!WECHAT_SERVER) throw new Error('找不到该账号的小程序协议配置');
        const resp = await axios.post(WECHAT_SERVER + '/api/v1/wx/app/call/function', {
            wxid: cleanRef, appid: APPID,
            data: JSON.stringify({ api_name: 'webapi_getuserencryptkey', with_credentials: true }), opt: 1,
        }, { timeout: 30000, proxy: false });
        result = resp.data;
    }
    const walk = (node, depth = 0) => {
        if (depth > 8 || node == null) return null;
        if (typeof node === 'string') {
            try { return walk(JSON.parse(node), depth + 1); } catch {}
            try { return walk(JSON.parse(Buffer.from(node, 'base64').toString('utf8')), depth + 1); } catch {}
        } else if (typeof node === 'object') {
            const key = node.encrypt_key || node.encryptKey;
            if (key && node.version != null && Buffer.from(key, 'base64').length === 16) {
                return { encryptKey: key, version: String(node.version),
                    expireTime: Date.now() + Math.max(0, Number(node.expire_in || 0)) * 1000 };
            }
            for (const value of Object.values(node)) { const found = walk(value, depth + 1); if (found) return found; }
        }
        return null;
    };
    const key = walk(result);
    if (!key) throw new Error('小程序协议未返回有效的16字节加密密钥');
    return key;
}

// 签到
async function doSign(session, wxid, cache, cacheKey) {
    const token = session.token;
    const openId = session.openId;
    const userId = session.userId;
    log('  📝 执行签到...');
    const record = await apiRequest('GET', '/fundex-activity/point/sign/getRecordList', {}, token, '', openId, userId);
    if (record?.code === '7005' && !session._signCryptoRetry) {
        session._signCryptoRetry = true;
        log('  🔄 小程序返回7005，重新获取加密参数后重试一次');
        return await doSign(session, wxid, cache, cacheKey);
    }
    if (record?.code === '200') {
        const today = record.data?.today;
        const list = record.data?.signRecordList || [];
        const todayRecord = list.find(r => r.signDate === today);
        if (todayRecord?.signIn) {
            log('  ✅ 今日已签到，连续' + (record.data?.continuousDays || 0) + '天');
            return true;
        }
    }
    let encryptKeyData = { encryptKey: '', version: '' };
    try {
        encryptKeyData = await getEncryptKey(wxid);
        putEncryptKeyCache(cache, cacheKey, encryptKeyData);
        saveCache(cache);
        log('  🔑 签到encryptKey刷新成功, version=' + encryptKeyData.version);
    } catch (e) {
        log('  ⚠️ 签到encryptKey刷新失败，尝试缓存: ' + e.message);
        encryptKeyData = getEncryptKeyCache(cache, cacheKey);
    }
    // 2026-10-28：服务端已把 userSignIn 纳入 SM4 加密名单，明文 body 会返回 7005/7006(02)。
    let signPayload = { submitCode: '', requestId: '' };
    if (encryptKeyData.encryptKey) {
        try {
            const kb = hexToBytes(Buffer.from(encryptKeyData.encryptKey, 'base64').toString('hex'));
            if (kb.length === 16) {
                signPayload = { msg: sm4Encrypt(JSON.stringify(signPayload), kb) };
                log('  🔐 签到参数 SM4 加密完成');
            } else {
                log('  ⚠️ 签到 encryptKey 长度异常(' + kb.length + ')，明文提交');
            }
        } catch (e) {
            log('  ⚠️ 签到参数加密失败: ' + e.message + '，停止提交');
        }
    }
    if (!signPayload.msg) { log('  ⚠️ 无有效小程序密钥，停止签到写入'); return false; }
    const resp = await apiRequest('POST', '/fundex-activity/point/sign/userSignIn', signPayload,
        token, encryptKeyData.version || '', openId, userId, encryptKeyData.encryptKey || '');
    if ((resp?.code === '429' || /访问过于频繁|请稍后再试/.test(resp?.msg || resp?.message || '')) && (session._sign429RetryCount || 0) < 3) {
        session._sign429RetryCount = (session._sign429RetryCount || 0) + 1;
        const waitMs = 5000 + randomInt(0, 2000) + (session._sign429RetryCount - 1) * 3000;
        log(`  ⚠️ 签到频率限制(${session._sign429RetryCount}/3)，等待 ${Math.round(waitMs / 1000)} 秒后重试`);
        await sleep(waitMs);
        return await doSign(session, wxid, cache, cacheKey);
    }
    if (resp?.code === '7005' && !session._signCryptoRetry) {
        session._signCryptoRetry = true;
        log('  🔄 小程序返回7005，重新获取加密参数后重试一次');
        return await doSign(session, wxid, cache, cacheKey);
    }
    if (String(resp?.code) === '7005' && !session._signSessionRefresh) {
        session._signSessionRefresh = true;
        try {
            const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '新密钥仍被拒绝，同步小程序业务会话（限一次）');
            if (fresh) { Object.assign(session, fresh); return await doSign(session, wxid, cache, cacheKey); }
        } catch (e) { log('  ⚠️ 小程序会话同步失败：' + e.message); }
    }
    if (resp?.code === '200') {
        const point = resp?.data?.point || 0;
        const days = resp?.data?.continuousDays || 0;
        log('  ✅ 签到成功: +' + point + '积分，连续' + days + '天');
        return true;
    }
    log('  ⚠️ 签到失败: ' + (resp?.message || JSON.stringify(resp)));
    return false;
}

// 查询当前账号积分余额，用于最终汇总显示“当前积分”，不是本次积分奖励。
async function getTotalPoint(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/point/account/getTotalPoint', {}, token, '', openId, userId);
    if (resp?.code === '200' && resp?.data) {
        return Number(resp.data.totalPoint || 0);
    }
    log('  ⚠️ 查询当前积分失败: ' + (resp?.message || resp?.msg || JSON.stringify(resp)));
    return null;
}

// 查询ROE并提交口令
async function doRoeReward(session, wxid, cache, cacheKey, activityEntry = null) {
    const token = session.token;
    const openId = session.openId;
    const loginData = session.loginData;
    if (activityEntry?.unavailable) return { success: true, skipped: true };
    log('  🔍 查询ROE...');

    const pageActivityId = activityEntry?.pageId || ACTIVITY_PAGE_ID;
    const actResp = await apiRequest('GET', '/fundex-activity/financial/getActivityInfoV2', { id: pageActivityId }, token, '', openId, loginData.userId);
    if (actResp?.code === '7005' && !session._roeCryptoRetry) {
        session._roeCryptoRetry = true;
        log('  🔄 小程序返回7005，重新获取加密参数后重试一次');
        return await doRoeReward(session, wxid, cache, cacheKey, activityEntry);
    }
    // 说明：
    // - 这个接口在 HAR 里虽然 success=false，但只要 data 存在就是活动有效。
    // - 真正要看的是 activitystatusResponseVo.status，HAR 中为 "1" 才表示活动可用。
    const activity = actResp?.data || null;
    const activityStatus = String(activity?.activitystatusResponseVo?.status ?? activity?.status ?? '');
    if (actResp?.code !== '200' || !activity) {
        log(`  ⚠️ 活动接口无数据（code=${actResp?.code || '-'}）`);
        return { success: false };
    }
    if (activityStatus && activityStatus !== '1') {
        log(activityStatus === '2' ? '  ⏰ 活动尚未开始：' + (activity.activityTime || '') : `  ℹ️ 活动不可参与（status=${activityStatus}）：` + (activity.activityTime || ''));
        return { success: true, skipped: true, status: activityStatus };
    }
    log('  📋 活动: ' + activity.title + ` | status=${activityStatus || '-'}`);
    // 提交加密接口前必须尽量使用最新 encryptKey/version。
    // 0624 抓包中手动提交为 key_version=9，而旧缓存 version=7 会触发 7005。
    // 因此这里先刷新，刷新失败才兜底使用缓存。
    let encryptKeyData = { encryptKey: '', version: '' };
    try {
        encryptKeyData = await getEncryptKey(wxid);
        log('  🔑 encryptKey刷新成功, version=' + encryptKeyData.version);
        putEncryptKeyCache(cache, cacheKey, encryptKeyData);
        saveCache(cache);
    } catch (e) {
        log('  ⚠️ encryptKey刷新失败，尝试使用缓存: ' + e.message);
        encryptKeyData = getEncryptKeyCache(cache, cacheKey);
        if (encryptKeyData.encryptKey) log('  🔑 使用缓存encryptKey, version=' + encryptKeyData.version);
    }




    // 从活动内容中提取指数代码
    const skipLink = activity.skipLink || '';
    const codeMatch = skipLink.match(/[?&]code=([^&]+)/i);
    const securityCode = codeMatch ? codeMatch[1] : '930707.CSI';
    log('  📊 指数: ' + securityCode);

    // 查询ROE值
    const roeResp = await apiRequest('GET', '/fundex-quote/security/info/queryMustSee', { securityCode, isCapital: false }, token, '', openId, loginData.userId);
    if (roeResp?.code !== '200' || !roeResp?.data?.roe) {
        log('  ⚠️ 查询ROE失败');
        return { success: false };
    }
    const roeValue = Number(roeResp.data.roe.value);
    if (!Number.isFinite(roeValue)) return { success: false };
    const roeAnswer = roeValue.toFixed(2) + '%';
    log('  📈 ROE: ' + roeValue + ' -> 口令: ' + roeAnswer);

    // 注意：活动详情里有两个 ID：
    // - activity.id 是页面配置 ID，例如 7541
    // - activitystatusResponseVo.activityId 才是 doExchange 兑换接口使用的真实活动 ID，例如 131003
    // 如果误用页面配置 ID，接口会返回“本次活动已结束”等误导性错误。
    const exchangeActivityId = activity?.activitystatusResponseVo?.activityId || activity.id;
    // 2026-10-28：doExchange 必填 activityTemplateId / registerChannel，缺失即 400 参数异常。
    const registerChannel = String((activityEntry && activityEntry.registerChannel) || buildDailyRegisterChannel()).replace(/^&/, '');
    let payload = {
        watchword: roeAnswer,
        openId: openId,
        activityId: exchangeActivityId,
        activityTemplateId: Number(activity && activity.activityTemplateId ? activity.activityTemplateId : 0),
        registerChannel: registerChannel,
    };
    log('  🎯 兑换活动ID: ' + exchangeActivityId);

    // SM4加密
    if (encryptKeyData.encryptKey) {
        try {
            const keyBytes = hexToBytes(Buffer.from(encryptKeyData.encryptKey, 'base64').toString('hex'));
            if (keyBytes.length === 16) {
                const encrypted = sm4Encrypt(JSON.stringify(payload), keyBytes);
                payload = { msg: encrypted };
                log('  🔐 SM4加密完成');
            } else {
                log('  ⚠️ encryptKey长度异常(' + keyBytes.length + 'bytes)，明文提交');
            }
        } catch (e) {
            log('  ⚠️ SM4加密失败: ' + e.message + '，停止提交');
        }
    } else {
        log('  ⚠️ 无encryptKey，明文提交');
    }

    if (!payload.msg) { log('  ⚠️ 无有效小程序密钥，停止口令提交'); return { success: false }; }
    // 提交口令
    // 0624 抓包里 doExchange 的 register_channel 为空；
    // 渠道只用于发现页面入口，不强行带到兑换提交，避免 7005。
    log('  🧭 提交渠道参数: ' + registerChannel);
    const resp = await apiRequest(
        'POST',
        '/fundex-activity/watchWordCustom/doExchange',
        payload,
        token,
        encryptKeyData.version,
        openId,
        loginData.userId,
        encryptKeyData.encryptKey,
        3,
        { registerChannel }
    );
    if ((resp?.code === '429' || /访问过于频繁|请稍后再试/.test(resp?.msg || resp?.message || '')) && (session._roe429RetryCount || 0) < 3) {
        session._roe429RetryCount = (session._roe429RetryCount || 0) + 1;
        const waitMs = 5000 + randomInt(0, 2000) + (session._roe429RetryCount - 1) * 3000;
        log(`  ⚠️ 兑换频率限制(${session._roe429RetryCount}/3)，等待 ${Math.round(waitMs / 1000)} 秒后重试`);
        await sleep(waitMs);
        return await doRoeReward(session, wxid, cache, cacheKey, activityEntry);
    }
    if (resp?.code === '7005' && !session._roeCryptoRetry) {
        session._roeCryptoRetry = true;
        log('  🔄 小程序返回7005，重新获取加密参数后重试一次');
        return await doRoeReward(session, wxid, cache, cacheKey, activityEntry);
    }
    if (String(resp?.code) === '7005' && !session._roeSessionRefresh) {
        session._roeSessionRefresh = true;
        try {
            const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '新密钥仍被拒绝，同步小程序业务会话（限一次）');
            if (fresh) { Object.assign(session, fresh); return await doRoeReward(session, wxid, cache, cacheKey, activityEntry); }
        } catch (e) { log('  ⚠️ 小程序会话同步失败：' + e.message); }
    }
    if (resp?.code === '200') {
        const data = resp.data;
        if (data?.rewardAmount) {
            // rewardType=2 对应微信红包，rewardAmount 是元；不是积分。
            const isRedPacket = String(data.rewardType || '') === '2' || data.link || data.tickCode;
            if (isRedPacket) {
                log('  🎉 兑换成功! 标题: ' + (data.title || roeAnswer) + ' 红包: ' + data.rewardAmount + '元，请到小程序手动领取');


                return {
                    success: true, type: 'redPacket', amount: Number(data.rewardAmount) || 0, data,
                    activity,
                };
            }
            log('  🎉 兑换成功! 标题: ' + (data.title || roeAnswer) + ' 积分: ' + data.rewardAmount);
            return { success: true, type: 'point', amount: Number(data.rewardAmount) || 0, data, activity };
        }
        log('  ⚠️ ' + (data?.content || JSON.stringify(data)));
        return { success: false };
    }
    if (String(resp?.code) === '9001' && /超过单人限兑|已参与|已兑换/.test(resp?.msg || resp?.message || '')) {
        log('  ✅ 今日口令已兑换'); return { success: true, alreadyDone: true };
    }
    log('  ⚠️ 提交失败: ' + (resp?.message || resp?.msg || ('code=' + resp?.code)));
    return { success: false };
}

// 查询红包活动列表
async function getActivityList(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/redPacket/getActivityList', { openId }, token, '', openId, userId);
    if (resp?.code === '200' && resp?.data) {
        return resp.data;
    }
    throw new Error('红包活动列表查询失败');
}

// 查询未领取红包列表
// 抓包显示 getUnclaimedList 返回空，实际未领取记录通过 getRequestPage(receiveStatus=0) 查询
async function getUnclaimedList(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/redPacket/getRequestPage', {
        receiveStatus: 0,
        pageNo: 1,
        pageSize: 100
    }, token, '', openId, userId);
    if (resp?.code === '200' && resp?.data?.dataList) {
        return resp.data.dataList;
    }
    throw new Error('未领红包查询失败');
}

// 查询红包领取历史
async function getRequestPage(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/redPacket/getRequestPage', {
        receiveStatus: 1,
        pageNo: 1,
        pageSize: 100
    }, token, '', openId, userId);
    if (resp?.code === '200' && resp?.data?.dataList) {
        return resp.data.dataList;
    }
    throw new Error('红包历史查询失败');
}

// 只汇总本次现金奖励与后台待领记录，不读取自动领取缓存，也不发起领取请求。
function summarizeManualRedPackets(roeResult, unclaimedList, requestPage) {
    const pending = [];
    const ids = new Set(), tickets = new Set();
    const add = packet => {
        const id = String(packet.requestId || packet.redPacketRequestId || '');
        const ticket = String(packet.ticketCode || packet.tickCode || '');
        if ((id && ids.has(id)) || (ticket && tickets.has(ticket))) return;
        if (id) ids.add(id);
        if (ticket) tickets.add(ticket);
        const amount = Number(packet.amount ?? packet.rewardAmount ?? 0);
        pending.push({ amount: Number.isFinite(amount) ? amount : 0 });
    };
    for (const packet of unclaimedList) add(packet);
    if (roeResult?.success && roeResult.type === 'redPacket') {
        add({ ...roeResult.data, amount: roeResult.amount });
    }
    return {
        pendingRedPacketCount: pending.length,
        pendingRedPacketAmount: Math.round(pending.reduce((sum, item) => sum + item.amount, 0) * 100) / 100,
        historyRedPacketAmount: Math.round(requestPage.reduce((sum, item) => sum + (Number(item.amount) || 0), 0) * 100) / 100,
        historyCount: requestPage.length,
    };
}

// ==================== 单账号执行 ====================
async function runTask(accountInfo) {
    const wxid = accountInfo.wxid;
    const note = accountInfo.note || '';
    const display = note || wxid;
    log('\n' + '='.repeat(50));
    log('▶ 账号: ' + display);
    log('='.repeat(50));

    const cache = loadCache();
    const cacheKey = wxid;
    const cached = getCache(cache, cacheKey);

    let token = '';
    let openId = '';
    let unionId = '';

    try {
        let loginData = null;

        // 1. 先读缓存，缓存有效就不再调用 wx.login / 手机号授权 / 登录接口。
        const cachedStatus = cached ? await checkCachedLogin(cached) : false;
        if (cached && cachedStatus === null) throw new Error('缓存验证未完成（网络或服务异常），保留CK，稍后重试');
        if (cached && cachedStatus) {
            token = cached.token;
            openId = cached.openId;
            unionId = cached.unionId || '';
            loginData = {
                token,
                userId: cached.userId,
                encryptUserId: cached.encryptUserId || '',
                isRegister: cached.isRegister || '0',
            };
            // 有效缓存无需再次获取手机号授权。
            log('  ✅ 使用缓存CK成功');
        } else {
            if (cached) log('  ⚠️ 缓存CK失效，重新协议登录');

            // 2. 获取微信code
            const code = await getWxCode(wxid, APPID);
            log('  ✅ wx.login code获取成功');

            // 3. 获取openId和unionId
            const ids = await getOpenIdAndUnionId(code);
            openId = ids.openId;
            unionId = ids.unionId;
            log('  ✅ 小程序身份获取成功');

            // 4. 获取手机号授权code
            const phoneInfo = await getPhoneCodeInfo(wxid);
            const phoneCode = phoneInfo.phoneCode;
            if (!phoneCode) throw new Error('手机号授权code获取失败，保留原登录缓存');
            log('  ✅ 手机号授权code获取成功');

            // 5. 登录
            loginData = await login(phoneCode, openId, unionId);
            if (!loginData) {
                log('❌ ' + display + ' 登录失败');
                return false;
            }
            token = loginData.token;
            log('  ✅ 小程序登录成功');

            // 登录成功后写缓存，下次优先复用。
            putCache(cache, cacheKey, {
                token,
                openId,
                unionId,
                userId: loginData.userId,
                mobile: phoneInfo.mobile || '',
                encryptUserId: loginData.encryptUserId || '',
                isRegister: loginData.isRegister || '',
            });
            saveCache(cache);
        }

        // 统一保存当前会话；签到/兑换遇到 7005 自动重登时会原地更新它，后续查红包/积分继续用新 CK。
        const session = {
            token,
            openId,
            unionId,
            userId: loginData.userId,
            loginData,
        };

        await sleep(randomInt(1000, 2000));

        // 6. 签到
        const signOk = await doSign(session, wxid, cache, cacheKey);
        await sleep(randomInt(1000, 2000));

        // 7. 动态发现页面活动 ID，然后执行 ROE 口令红包。
        const activityEntry = await discoverActivityEntry(session.token, session.openId, session.userId);
        const roeResult = await doRoeReward(session, wxid, cache, cacheKey, activityEntry);

        // 8. 红包只查询和提示手动领取，所有账号采用相同逻辑。
        await sleep(randomInt(1000, 2000));
        let redPacketAmount = 0, roeReward = 0;
        const activities = await getActivityList(session.token, session.openId, session.userId);
        log('  📋 红包活动列表: ' + activities.length + '个');
        const unclaimedList = await getUnclaimedList(session.token, session.openId, session.userId);
        const requestPage = await getRequestPage(session.token, session.openId, session.userId);
        const manual = summarizeManualRedPackets(roeResult, unclaimedList, requestPage);
        const pendingRedPacketAmount = manual.pendingRedPacketAmount;
        const historyRedPacketAmount = manual.historyRedPacketAmount;
        log('  📊 历史已标记领取记录: ' + manual.historyCount + '笔，累计' + formatMoney(historyRedPacketAmount) + '元（非本次收益）');
        if (manual.pendingRedPacketCount > 0) {
            log('  🎁 需手动领取红包: ' + manual.pendingRedPacketCount + '笔，合计' + formatMoney(pendingRedPacketAmount) + '元');
        } else {
            log('  ℹ️ 后台未返回新的待领红包');
        }
        log('  📲 红包请打开红色火箭小程序，在活动中心/红包记录中手动领取。');


        // 汇总里展示账号当前积分余额，避免把"本次积分奖励"误当成总积分。
        const currentPoint = await getTotalPoint(session.token, session.openId, session.userId);
        log('  💎 当前积分: ' + currentPoint);

        // 记录本次兑换奖励：红包按元统计，积分按积分统计，不再把红包误写成积分。
        if (roeResult?.success) {
            if (roeResult.type === 'redPacket') {
                redPacketAmount += roeResult.amount || 0;
            } else if (roeResult.type === 'point') {
                roeReward += roeResult.amount || 0;
            }
        }


        return { success: Boolean(signOk && roeResult?.success && currentPoint !== null), currentPoint, roeReward, redPacketAmount, historyRedPacketAmount, pendingRedPacketAmount };

    } catch (e) {
        log('❌ 异常: ' + e.message);
        log('❌ ' + display + ' 异常: ' + e.message);
        return false;
    }
}

// ==================== 主逻辑 ====================
async function main() {
    log('🚀 红色火箭脚本启动');
    log('📲 手动领取版：现金红包需在小程序中自行领取');

    if (!taskVar.trim()) {
        log('环境变量未设置: ' + ckName);
        await push_notification();
        process.exit(0);
    }

    // 解析账号：WX_ID 格式 wxid#备注，多账号换行或 & 分隔
    const accounts = [];
    const lines = taskVar.split(/[&\n]/);
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split('#');
        const wxid = parts[0].trim();
        const note = parts[1] || '';
        if (wxid) accounts.push({ wxid, note });
    }

    log('📋 账号数: ' + accounts.length);

    let successCount = 0;
    for (let i = 0; i < accounts.length; i++) {
        try {
            const result = await runTask(accounts[i]);
            if (result) {
                if (result.success) successCount++;
                accounts[i].completed = true;
                accounts[i].ok = result.success;
                accounts[i].currentPoint = result.currentPoint;
                accounts[i].roeReward = result.roeReward || 0;
                accounts[i].redPacketAmount = result.redPacketAmount || 0;
                accounts[i].historyRedPacketAmount = result.historyRedPacketAmount || 0;
                accounts[i].pendingRedPacketAmount = result.pendingRedPacketAmount || 0;
            }
        } catch (e) {
            log('❌ 账号 ' + (i + 1) + ' 异常: ' + e.message);
        }
        if (i < accounts.length - 1) {
            log('⏳ 等待 ' + randomInt(3, 6) + ' 秒...');
            await sleep(randomInt(3000, 6000));
        }
    }

    // 汇总输出
    log('\n' + '='.repeat(50));
    log('📊 基础任务执行完毕, 成功 ' + successCount + '/' + accounts.length + '（红包需手动领取）');

    // 详细执行日志只输出到控制台；通知单独使用下列汇总。
    log('\n📋 账号汇总:');
    const summaryLines = accounts.map(formatAccountSummary);
    for (const line of summaryLines) log(line);
    await push_notification(summaryLines);
}

if (require.main === module) main().catch(e => { log('❌ 脚本异常: ' + e.message); process.exitCode = 1; });
module.exports = { main, apiRequest, checkCachedLogin, getWxCode, getOpenIdAndUnionId, getEncryptKey,
    loadCache, discoverActivityEntry, doRoeReward, extractFanActivityFromHome, todayMMdd, runTask,
    sm4Encrypt, buildHeaders, summarizeManualRedPackets, formatAccountSummary, push_notification };
