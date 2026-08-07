// name:红色火箭
// cron: 6 10,17 * * * 
//  红色火箭（华泰基金指慧家）
 
//  环境变量：
//    WX_ID              必填，格式：wxid#备注，多账号换行或 & 分隔
//   WECHAT_SERVER      微信协议服务地址
//    HSJJ_AUTO_CLAIM_H5 设为 '0' 或 'false' 关闭自动提现（默认开启）
 

'use strict';

const { getSingleCode } = require('./getCode.js');
const getWxCode = (wxid, appid) => getSingleCode(appid, String(wxid).split('#')[0].trim());
const axios = require('axios');
const fs = require('fs');
const pathMod = require('path');

const BASE_URL = 'https://index.amcfortune.com';

// ==================== 配置区 ====================
let ckName = "WX_ID";
let taskVar = process.env.WX_ID || '';
const WECHAT_SERVER = (process.env.WECHAT_SERVER || '').replace(/\/$/, '');
const debug = process.env.debug || 0;
const APPID = 'wx1b44c3ad181bde16';
const ACTIVITY_PAGE_ID = process.env.HSJJ_ACTIVITY_PAGE_ID || '7541';
const H5_OAUTH_APPID = 'wx80226ec03be5ab6c';
const H5_URLTAG = 'cfyh';
const AUTO_CLAIM_H5_RED_PACKET = process.env.HSJJ_AUTO_CLAIM_H5 !== '0';

const CACHE_DIR = pathMod.join(process.cwd(), '.cache');
const ACCOUNT_CACHE_FILE = pathMod.join(CACHE_DIR, 'hsjj_accounts.json');

// ==================== 通知模块 ====================
let notify;
try { notify = require('./notify'); } catch (e) { notify = null; }

// 消息收集
let _logMessages = [];
function log(str) {
    console.log(str);
    _logMessages.push(str);
}
async function push_notification() {
    const title = "红色火箭（华泰基金）";
    const content = _logMessages.join('\n');
    if (notify && typeof notify.send === 'function') {
        try {
            await notify.send(title, content);
            log('✅ 通知发送成功');
        } catch (e) {
            log('⚠️ 通知发送失败: ' + e.message);
        }
    } else {
        log("--- 通知 ---\n" + title + "\n" + content + "\n-------------");
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
    const d = new Date();
    return String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
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
        'ticket': token || '',
    };
}

// ==================== 缓存层 ====================
function loadCache() {
    try { return JSON.parse(fs.readFileSync(ACCOUNT_CACHE_FILE, 'utf8')) || {}; }
    catch { return {}; }
}
function saveCache(data) {
    try { ensureCacheDir(); fs.writeFileSync(ACCOUNT_CACHE_FILE, JSON.stringify(data, null, 2), 'utf8'); }
    catch (e) { log('保存缓存失败: ' + e.message); }
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
        const config = { method, url: BASE_URL + url, headers };
        if (method === 'POST') config.data = data;
        else config.params = { ...data, key: Date.now() };
        const resp = await axios(config);
        if (debug) log('[API] ' + url + ' => ' + JSON.stringify(resp.data).substring(0, 200));
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
        if (retries > 0) {
            log('  请求失败，重试... ' + e.message);
            return await apiRequest(method, url, data, token, encryptVer, openId, userId, appSecret, retries - 1, options);
        }
        log('  请求失败: ' + url + ' - ' + e.message);
        return null;
    }
}

// ==================== 微信登录 ====================
// 使用 getCode.js 统一接口

// ==================== 业务逻辑 ====================

// 获取手机号授权code
async function getPhoneCodeInfo(wxid) {
    const cleanWxid = String(wxid).split('#')[0].trim();
    const isYyb = /^\d+$/.test(cleanWxid) || /^o[a-zA-Z0-9_-]{20,}$/.test(cleanWxid);
    
    let respData;
    if (isYyb) {
        // 使用 YYB 协议获取手机号 code
        const { WeChatCodeGetter, YYBAdapter } = require('./getCode.js');
        const getter = new WeChatCodeGetter();
        await getter.init();
        
        const yybAdapter = new YYBAdapter(getter.yybServer);
        const resolvedRef = await yybAdapter._resolveRef(cleanWxid);
        const url = getter.yybServer.replace(/\/+$/, '') + '/wxapp/getPhoneNumber';
        
        if (debug) log(`[YYB] 请求手机号code: ref=${resolvedRef}, app_id=${APPID}`);
        const resp = await axios.post(url, { ref: resolvedRef, app_id: APPID }, {
            headers: { 'Content-Type': 'application/json' },
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
    log('  ⚠️ 获取手机号code失败: ' + (respData ? JSON.stringify(respData).substring(0, 300) : 'null'));
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
    const headers = buildHeaders({ code }, '', '');
    const resp = await axios.post(BASE_URL + '/fundex-uc/uc/v1/getWxOpenIdAndUnionId', { code }, { headers });
    if (resp.data?.code === '200' && resp.data?.data?.openId) {
        return { openId: resp.data.data.openId, unionId: resp.data.data.unionId };
    }
    throw new Error('获取openId失败: ' + JSON.stringify(resp.data));
}

// 校验缓存登录态：能正常访问轻量接口就认为 token/openId/userId 可用。
async function checkCachedLogin(cached) {
    if (!cached?.token || !cached?.openId || !cached?.userId) return false;
    const resp = await apiRequest('GET', '/fundex-activity/point/sign/getRecordList', {}, cached.token, '', cached.openId, cached.userId, '', 0);
    return resp?.code === '200';
}

// 动态获取页面活动 ID 和渠道参数，失败才兜底使用默认页面 ID/当天渠道。
async function discoverActivityEntry(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/opportunity/v3/findPageContent', {
        orderBy: 'changePercent',
        classA: '02',
        order: 'desc',
        platform: '',
        openId,
    }, token, '', openId, userId, '', 1);
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
    log(`  ⚠️ 未从首页发现活动入口，兜底 pageId=${ACTIVITY_PAGE_ID}`);
    return { pageId: ACTIVITY_PAGE_ID, registerChannel: buildDailyRegisterChannel(), skipAddr: '' };
}

// 获取加密密钥配置
async function getEncryptConfig(token, openId) {
    const resp = await apiRequest('GET', '/fundex-activity/knowledgeBase/findKnowledgeInfoListByKeyList', { knowledgeKeyList: 'secure_path' }, token, '', openId);
    if (resp?.code === '200' && Array.isArray(resp?.data)) {
        const content = resp.data[0]?.knowledgeContent || '';
        return content.split(',').filter(Boolean);
    }
    return [];
}

// 获取加密密钥：先尝试养鸡场“最新用户key”接口，失败再兜底调用小程序的 getUserCryptoManager。
async function getEncryptKey(wxid) {
    const tryParseEncryptKey = (obj) => {
        try {
            if (!obj) return null;
            const walk = (node, depth = 0) => {
                if (depth > 8 || node == null) return null;
                if (typeof node === 'string') {
                    // 1) base64（24+ 可见字符）解码后可能是嵌套 JSON
                    if (/^[A-Za-z0-9+/=]{24,}$/i.test(node)) {
                        try {
                            const decoded = Buffer.from(node, 'base64').toString('utf8');
                            if (decoded) return walk(JSON.parse(decoded), depth + 1);
                        } catch {}
                    }
                    // 2) 直接是 JSON 字符串（YYB: {"encrypt_key":"...","version":...,"iv":...}）
                    if (node.trim().startsWith('{')) {
                        try {
                            return walk(JSON.parse(node), depth + 1);
                        } catch {}
                    }
                    return null;
                }
                if (Array.isArray(node)) {
                    for (const item of node) {
                        const found = walk(item, depth + 1);
                        if (found) return found;
                    }
                    return null;
                }
                if (typeof node === 'object') {
                    const key = node.encryptKey || node.encrypt_key || node.key || node.EncryptKey;
                    if (key) {
                        return {
                            encryptKey: String(key),
                            version: String(node.version || node.Version || node.encryptVer || '1'),
                            iv: node.iv || '',
                        };
                    }
                    for (const v of Object.values(node)) {
                        const found = walk(v, depth + 1);
                        if (found) return found;
                    }
                }
                return null;
            };
            return walk(obj);
        } catch {
            return null;
        }
    };

    // 1) 优先尝试养鸡场最新key接口
    try {
        const latestResp = await axios.post(WECHAT_SERVER + '/wechat/api/getLatestUserKey', {
            wxid,
            appid: APPID
        });
        const latestKey = tryParseEncryptKey(latestResp.data || latestResp);
        if (latestKey?.encryptKey) {
            if (debug) log('  getLatestUserKey: ' + JSON.stringify(latestResp.data).substring(0, 500));
            return latestKey;
        }
    } catch (e) {
        if (debug) log('  getLatestUserKey失败: ' + e.message);
    }

    // 2) 兜底走小程序协议接口
    let respData;
    const cleanWxid = String(wxid).split('#')[0].trim();
    const isYyb = /^\d+$/.test(cleanWxid) || /^o[a-zA-Z0-9_-]{20,}$/.test(cleanWxid);

    if (isYyb) {
        const { WeChatCodeGetter, YYBAdapter } = require('./getCode.js');
        const getter = new WeChatCodeGetter();
        await getter.init();
        
        const yybAdapter = new YYBAdapter(getter.yybServer);
        const resolvedRef = await yybAdapter._resolveRef(cleanWxid);
        const url = getter.yybServer.replace(/\/+$/, '') + '/wxapp/operateWxData';
        
        if (debug) log(`[YYB] 请求EncryptKey: ref=${resolvedRef}, app_id=${APPID}`);
        const resp = await axios.post(url, {
            ref: resolvedRef,
            app_id: APPID,
            payload: { api_name: 'webapi_getuserencryptkey' }
        }, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 30000,
            validateStatus: () => true
        });
        respData = resp.data;
        if (debug) log('  [YYB][debug] getuserencryptkey 原始响应: ' + JSON.stringify(respData).substring(0, 1200));
    } else {
        const resp = await axios.post(WECHAT_SERVER + '/api/v1/wx/app/call/function', {
            wxid: cleanWxid,
            appid: APPID,
            data: JSON.stringify({ api_name: 'webapi_getuserencryptkey', with_credentials: true }),
            opt: 1
        });
        respData = resp.data;
    }

    // 原始响应始终打印（便于排查 YYB/牛子 不同返回格式），不再依赖 debug 开关
    log('  [encryptKey][raw] ' + JSON.stringify(respData).substring(0, 1500));

    if (respData && (respData.Code === 0 || respData.code === 0 || respData.Success === true || respData.Data || respData.data || respData.result || respData.openid)) {
        try {
            // 兼容多种结构:
            //   牛子/养鸡场: Data.Data / Data.data（base64）
            //   应用宝 YYB:  data.result / data.data（base64 或 JSON 字符串）
            let outer = respData.Data?.Data || respData.Data?.data ||
                        respData.data?.result || respData.data?.data || respData.data?.Data ||
                        respData.result?.data || respData.result?.Data || respData.result || '';
            let decoded = '';
            if (outer) {
                try {
                    decoded = Buffer.from(outer, 'base64').toString('utf8');
                } catch {
                    decoded = '';
                }
                // base64 解码失败/为空时，尝试直接把 outer 当 JSON 字符串
                if (!decoded) decoded = (typeof outer === 'string') ? outer : '';
            }
            let inner;
            try {
                inner = decoded ? JSON.parse(decoded) : {};
            } catch {
                inner = (typeof decoded === 'object') ? decoded : {};
            }
            if (inner && (inner.encrypt_key !== undefined || inner.encryptKey !== undefined || inner.version !== undefined)) {
                return {
                    encryptKey: inner.encrypt_key || inner.encryptKey || '',
                    version: String(inner.version || ''),
                    iv: inner.iv || '',
                };
            }
        } catch (e) {
            log('  [encryptKey] 解析异常: ' + e.message);
        }
    }
    // 兜底：用通用递归提取器在 YYB/牛子 多样结构中找 encryptKey（处理 base64 / 嵌套 JSON / 直出字段）
    try {
        const fb = tryParseEncryptKey(respData);
        if (fb?.encryptKey) {
            if (debug) log('  [encryptKey] 兜底递归提取成功');
            return fb;
        }
    } catch {}
    throw new Error('获取加密密钥失败, 响应预览: ' + JSON.stringify(respData).substring(0, 600));
}

// 签到
async function doSign(session, wxid, cache, cacheKey) {
    const token = session.token;
    const openId = session.openId;
    const userId = session.userId;
    log('  📝 执行签到...');
    const record = await apiRequest('GET', '/fundex-activity/point/sign/getRecordList', {}, token, '', openId, userId);
    if (record?.code === '7005' && !session._signReloginDone) {
        const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '签到记录返回7005');
        if (fresh) {
            session.token = fresh.token;
            session.openId = fresh.openId;
            session.userId = fresh.userId;
            session.loginData = fresh.loginData;
            session._signReloginDone = true;
            return await doSign(session, wxid, cache, cacheKey);
        }
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
    // HAR 中 userSignIn body 为 {"submitCode":"","requestId":""}，且需要 key_version/signature。
    const resp = await apiRequest('POST', '/fundex-activity/point/sign/userSignIn', {
        submitCode: '',
        requestId: '',
    }, token, encryptKeyData.version || '', openId, userId, encryptKeyData.encryptKey || '');
    if ((resp?.code === '429' || /访问过于频繁|请稍后再试/.test(resp?.msg || resp?.message || '')) && (session._sign429RetryCount || 0) < 3) {
        session._sign429RetryCount = (session._sign429RetryCount || 0) + 1;
        const waitMs = 5000 + randomInt(0, 2000) + (session._sign429RetryCount - 1) * 3000;
        log(`  ⚠️ 签到频率限制(${session._sign429RetryCount}/3)，等待 ${Math.round(waitMs / 1000)} 秒后重试`);
        await sleep(waitMs);
        return await doSign(session, wxid, cache, cacheKey);
    }
    if (resp?.code === '7005' && !session._signReloginDone) {
        const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '签到提交返回7005');
        if (fresh) {
            session.token = fresh.token;
            session.openId = fresh.openId;
            session.userId = fresh.userId;
            session.loginData = fresh.loginData;
            session._signReloginDone = true;
            return await doSign(session, wxid, cache, cacheKey);
        }
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
    return 0;
}

// 查询ROE并提交口令
async function doRoeReward(session, wxid, cache, cacheKey, activityEntry = null) {
    const token = session.token;
    const openId = session.openId;
    const loginData = session.loginData;
    log('  🔍 查询ROE...');

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

    const pageActivityId = activityEntry?.pageId || ACTIVITY_PAGE_ID;
    const actResp = await apiRequest('GET', '/fundex-activity/financial/getActivityInfoV2', { id: pageActivityId }, token, '', openId, loginData.userId);
    if (actResp?.code === '7005' && !session._roeReloginDone) {
        const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '兑换活动信息返回7005');
        if (fresh) {
            session.token = fresh.token;
            session.openId = fresh.openId;
            session.userId = fresh.userId;
            session.loginData = fresh.loginData;
            session._roeReloginDone = true;
            return await doRoeReward(session, wxid, cache, cacheKey, activityEntry);
        }
    }
    // 说明：
    // - 这个接口在 HAR 里虽然 success=false，但只要 data 存在就是活动有效。
    // - 真正要看的是 activitystatusResponseVo.status，HAR 中为 "1" 才表示活动可用。
    const activity = actResp?.data || null;
    const activityStatus = String(activity?.activitystatusResponseVo?.status ?? activity?.status ?? '');
    if (actResp?.code !== '200' || !activity) {
        log(`  ⚠️ 活动接口无数据（code=${actResp?.code || '-'}）`);
        return false;
    }
    if (activityStatus && activityStatus !== '1') {
        log(`  ⚠️ 活动已结束（status=${activityStatus}）`);
        return false;
    }
    log('  📋 活动: ' + activity.title + ` | status=${activityStatus || '-'}`);

    // 兑换前先补领历史未领取红包（自动提现）
    let existingClaimResult = { claimed: 0, amount: 0 };
    if (AUTO_CLAIM_H5_RED_PACKET) {
        log('  💰 检查历史未领取红包...');
        existingClaimResult = await claimExistingWatchRewards(session, wxid, cache, cacheKey, activity);
        if (existingClaimResult.claimed > 0) {
            log(`  ✅ 历史红包补领完成: ${existingClaimResult.claimed}个, 共${formatMoney(existingClaimResult.amount)}元`);
        }
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
        return { success: false, existingClaim: existingClaimResult };
    }
    const roeValue = roeResp.data.roe.value;
    const roeAnswer = roeValue.toFixed(2) + '%';
    log('  📈 ROE: ' + roeValue + ' -> 口令: ' + roeAnswer);

    // 注意：活动详情里有两个 ID：
    // - activity.id 是页面配置 ID，例如 7541
    // - activitystatusResponseVo.activityId 才是 doExchange 兑换接口使用的真实活动 ID，例如 131003
    // 如果误用页面配置 ID，接口会返回“本次活动已结束”等误导性错误。
    const exchangeActivityId = activity?.activitystatusResponseVo?.activityId || activity.id;
    let payload = { watchword: roeAnswer, openId: openId, activityId: exchangeActivityId };
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
            log('  ⚠️ SM4加密失败: ' + e.message + '，明文提交');
        }
    } else {
        log('  ⚠️ 无encryptKey，明文提交');
    }

    // 提交口令
    // 0624 抓包里 doExchange 的 register_channel 为空；
    // 渠道只用于发现页面入口，不强行带到兑换提交，避免 7005。
    const registerChannel = '';
    log('  🧭 提交渠道参数: 空(按抓包)');
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
    if (resp?.code === '7005' && !session._roeReloginDone) {
        const fresh = await refreshProtocolSession(wxid, cache, cacheKey, '兑换提交返回7005');
        if (fresh) {
            session.token = fresh.token;
            session.openId = fresh.openId;
            session.userId = fresh.userId;
            session.loginData = fresh.loginData;
            session._roeReloginDone = true;
            return await doRoeReward(session, wxid, cache, cacheKey, activityEntry);
        }
    }
    if (resp?.code === '200') {
        const data = resp.data;
        if (data?.rewardAmount) {
            // rewardType=2 对应微信红包，rewardAmount 是元；不是积分。
            const isRedPacket = String(data.rewardType || '') === '2' || data.link || data.tickCode;
            if (isRedPacket) {
                log('  🎉 兑换成功! 标题: ' + (data.title || roeAnswer) + ' 红包: ' + data.rewardAmount + '元');

                // 自动提现：兑换成功后立即领取新红包
                let newClaimResult = null;
                if (AUTO_CLAIM_H5_RED_PACKET) {
                    const requestId = data.redPacketRequestId || data.requestId || '';
                    const ticketCode = data.tickCode || data.ticketCode || '';
                    if (requestId && ticketCode) {
                        log('  💰 开始自动领取新红包...');
                        await updateRedPacketGetStatus(token, openId, loginData.userId, {
                            requestId,
                            activityId: exchangeActivityId,
                            activityType: '4',
                        });
                        newClaimResult = await claimRedPacket(
                            token, openId, loginData.userId,
                            requestId, ticketCode, exchangeActivityId, '4',
                            '', wxid, cache, cacheKey
                        );
                        if (newClaimResult?.success) {
                            log('  ✅ 新红包自动领取成功: ' + formatMoney(newClaimResult.amount || data.rewardAmount) + '元' + (newClaimResult.message ? ' (' + newClaimResult.message + ')' : ''));
                        } else {
                            log('  ⚠️ 新红包自动领取失败: ' + (newClaimResult?.message || '未知'));
                        }
                    }
                }

                return {
                    success: true, type: 'redPacket', amount: Number(data.rewardAmount) || 0, data,
                    claimResult: newClaimResult, existingClaim: existingClaimResult, activity,
                };
            }
            log('  🎉 兑换成功! 标题: ' + (data.title || roeAnswer) + ' 积分: ' + data.rewardAmount);
            return { success: true, type: 'point', amount: Number(data.rewardAmount) || 0, data, existingClaim: existingClaimResult, activity };
        }
        log('  ⚠️ ' + (data?.content || JSON.stringify(data)));
        return { success: false, existingClaim: existingClaimResult };
    }
    log('  ⚠️ 提交失败: ' + (resp?.message || JSON.stringify(resp)));
    return { success: false, existingClaim: existingClaimResult };
}

// 查询红包活动列表
async function getActivityList(token, openId, userId) {
    const resp = await apiRequest('GET', '/fundex-activity/redPacket/getActivityList', { openId }, token, '', openId, userId);
    if (resp?.code === '200' && resp?.data) {
        return resp.data;
    }
    return [];
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
    return [];
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
    return [];
}

// 标记红包进入领取流程。抓包显示打开外部 mktzb 页面前会先调用这个接口。
async function updateRedPacketGetStatus(token, openId, userId, packet) {
    const payload = {
        requestId: packet.requestId,
        activityId: packet.activityId,
        activityType: packet.activityType || '4',
    };
    const resp = await apiRequest('POST', '/fundex-activity/redPacket/updateGetStatus', payload, token, '', openId, userId);
    if (debug) log('  [updateGetStatus] ' + JSON.stringify(resp).substring(0, 200));
    return resp?.code === '200';
}

/**
 * 通过桥接服务获取 H5 公众号 openid（cfyh cookie）。
 * 流程参考 Python resolve_h5_openid：
 * 1) 用 H5_OAUTH_APPID 从桥接服务拿 code
 * 2) 访问 baseWxAuth 授权页，从 Set-Cookie / HTML 提取 cfyh openid
 * 3) 缓存到账号缓存，下次直接复用
 */
async function resolveH5Openid(wxid, ticketCode, cache, cacheKey) {
    if (cache && cacheKey) {
        const cached = getCache(cache, cacheKey);
        if (cached?.h5Openid) {
            if (debug) log('  📦 使用缓存H5 openid');
            return cached.h5Openid;
        }
    }
    if (!wxid || !WECHAT_SERVER || !ticketCode) return '';

    try {
        // 1. 通过 getCode.js 统一接口获取 H5 公众号 code
        const code = await getSingleCode(H5_OAUTH_APPID, String(wxid).split('#')[0].trim());
        if (!code) {
            if (debug) log('  ⚠️ 桥接服务未返回H5 code');
            return '';
        }

        // 2. 访问 baseWxAuth 授权页，跟随重定向并提取 cfyh cookie
        const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254186b) XWEB/19841 miniProgram/' + APPID;
        const authUrl = `https://www.mktzb.com/mktadmin/wcode/baseWxAuth/${H5_URLTAG}?code=${encodeURIComponent(code)}&state=${encodeURIComponent(ticketCode)}`;

        let h5Openid = '';
        try {
            const resp = await axios.get(authUrl, {
                headers: {
                    'User-Agent': ua,
                    'Referer': `https://www.mktzb.com/mktadmin/wcode/baseWxAuth/${H5_URLTAG}?prjCode=${encodeURIComponent(ticketCode)}`,
                },
                timeout: 30000,
                maxRedirects: 5,
            });

            // 从 Set-Cookie 提取 cfyh
            const setCookies = resp.headers['set-cookie'];
            if (setCookies) {
                const cookies = Array.isArray(setCookies) ? setCookies : [setCookies];
                for (const c of cookies) {
                    const m = c.match(new RegExp(`${H5_URLTAG}=([^;]+)`));
                    if (m) { h5Openid = m[1]; break; }
                }
            }

            // 从 HTML 提取 openid
            if (!h5Openid) {
                const html = typeof resp.data === 'string' ? resp.data : '';
                const m = html.match(/id=["']openid["'][^>]*value=["']([^"']*)/i);
                if (m) h5Openid = m[1];
            }
        } catch (e) {
            if (debug) log('  ⚠️ H5授权请求失败: ' + e.message);
        }

        if (h5Openid) {
            if (debug) log('  🔑 H5 openid获取成功: ' + h5Openid.substring(0, 8) + '***');
            if (cache && cacheKey) {
                putCache(cache, cacheKey, { h5Openid });
                saveCache(cache);
            }
        }
        return h5Openid;
    } catch (e) {
        if (debug) log('  ⚠️ resolveH5Openid失败: ' + e.message);
        return '';
    }
}

// 领取红包：真正领取流程在外部 mktzb 红包页，不是 fundex 的 exchangeRedPacket。
// 抓包流程：baseWxAuth 页面 -> getCodeBaseInfo 查看 -> checkCodeBatchRepeat 领取。
// wxid/cache/cacheKey 用于在 HTML 提取不到 openid 时通过 resolveH5Openid 兜底。
async function claimRedPacket(token, openId, userId, requestId, ticketCode, activityId, activityType, mktzbOpenId = '', wxid = '', cache = null, cacheKey = '') {
    const prjCode = ticketCode || requestId;
    if (!prjCode) return { success: false, message: '缺少ticketCode/prjCode' };

    const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254186b) XWEB/19841 miniProgram/' + APPID;
    const pageUrl = `https://www.mktzb.com/mktadmin/wcode/baseWxAuth/cfyh?prjCode=${encodeURIComponent(prjCode)}`;
    const formHeaders = {
        'User-Agent': ua,
        'Referer': pageUrl,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
    };

    const pageResp = await axios.get(pageUrl, { headers: { 'User-Agent': ua }, timeout: 30000 });
    const html = String(pageResp.data || '');
    let pageOpenId = (html.match(/id=["']openid["'][^>]*value=["']([^"']*)/i) || [])[1] || mktzbOpenId || process.env.HSJJ_MKTZB_OPENID || '';
    const prjUrltag = (html.match(/id=["']prj_urltag["'][^>]*value=["']([^"']*)/i) || [])[1] || H5_URLTAG;
    const pagePrjCode = (html.match(/id=["']prjCode["'][^>]*value=["']([^"']*)/i) || [])[1] || prjCode;

    // HTML 提取不到 openid 时，通过桥接服务走 H5 OAuth 兜底
    if (!pageOpenId && wxid && AUTO_CLAIM_H5_RED_PACKET) {
        log('  🔄 HTML未获取到openid，通过桥接服务解析H5 openid...');
        pageOpenId = await resolveH5Openid(wxid, prjCode, cache, cacheKey);
    }

    if (!pageOpenId) {
        return {
            success: false,
            message: '红包页未获取到mktzb公众号openid，可手动打开授权一次或设置 HSJJ_MKTZB_OPENID；url=' + pageUrl
        };
    }

    const form = new URLSearchParams({ prj_code: pagePrjCode, prj_urltag: prjUrltag, openid: pageOpenId }).toString();
    const infoResp = await axios.post('https://www.mktzb.com/mktadmin/wcode/getCodeBaseInfo', form, { headers: formHeaders, timeout: 30000 });
    if (debug) log('  [getCodeBaseInfo] ' + JSON.stringify(infoResp.data).substring(0, 300));
    const codeInfo = infoResp.data?.value?.activityPrjCode || {};
    const amount = codeInfo.user_bonus ? codeInfo.user_bonus / 100 : 0;
    // mktzb 页面逻辑：
    // if_used=2 表示红包发放中，if_used=3 表示领取成功；二者都不应当按失败处理。
    if (String(codeInfo.if_used) === '2') return { success: true, data: infoResp.data, amount, message: '红包发放中' };
    if (String(codeInfo.if_used) === '3') return { success: true, data: infoResp.data, amount, message: '红包已领取' };

    const claimResp = await axios.post('https://www.mktzb.com/mktadmin/wcode/checkCodeBatchRepeat', form, { headers: formHeaders, timeout: 30000 });
    if (debug) log('  [checkCodeBatchRepeat] ' + JSON.stringify(claimResp.data).substring(0, 300));
    if (claimResp.data?.success) return { success: true, data: claimResp.data, amount };
    // c0004 = 红包发放中，说明领取请求已经进入发放队列。
    if (claimResp.data?.message === 'c0004') return { success: true, data: claimResp.data, amount, message: '红包发放中' };
    return { success: false, message: JSON.stringify(claimResp.data) };
}

/**
 * 从活动信息的 exchangeRequestVoList 中补领历史未领取红包。
 * 参考 Python claim_existing_watch_rewards：遍历历史兑换记录，
 * 对每条有 ticketCode 的记录调用 updateRedPacketGetStatus + claimRedPacket。
 */
async function claimExistingWatchRewards(session, wxid, cache, cacheKey, activityInfo) {
    const rewards = activityInfo?.exchangeRequestVoList || [];
    if (!rewards.length) return { claimed: 0, amount: 0 };

    let claimedCount = 0;
    let claimedAmount = 0;

    for (const item of rewards) {
        const requestId = item.requestId || item.redPacketRequestId || '';
        if (!requestId) continue;

        const ticketCode = item.ticketCode || item.tickCode || '';
        const amount = Number(item.rewardAmount || 0);
        const status = String(item.receiveStatus || '');

        log(`  📦 发现历史红包: ${formatMoney(amount)}元, 券码: ${ticketCode || '无'}, receiveStatus=${status || '-'}`);

        if (!AUTO_CLAIM_H5_RED_PACKET) continue;

        // 更新红包领取状态
        await updateRedPacketGetStatus(session.token, session.openId, session.userId, {
            requestId,
            activityId: item.activityId || '',
            activityType: item.activityType || '4',
        });

        // 通过 H5 领取
        if (ticketCode) {
            const claimResult = await claimRedPacket(
                session.token, session.openId, session.userId,
                requestId, ticketCode, item.activityId, item.activityType,
                '', wxid, cache, cacheKey
            );
            if (claimResult?.success) {
                claimedCount++;
                claimedAmount += claimResult.amount || amount;
                log(`  ✅ 历史红包领取成功: ${formatMoney(claimResult.amount || amount)}元${claimResult.message ? ' (' + claimResult.message + ')' : ''}`);
            } else {
                log(`  ⚠️ 历史红包领取失败: ${claimResult?.message || '未知'}`);
            }
        }

        await sleep(randomInt(500, 1500));
    }

    return { claimed: claimedCount, amount: claimedAmount };
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
        if (cached && await checkCachedLogin(cached)) {
            token = cached.token;
            openId = cached.openId;
            unionId = cached.unionId || '';
            loginData = {
                token,
                userId: cached.userId,
                encryptUserId: cached.encryptUserId || '',
                isRegister: cached.isRegister || '0',
            };
            const mobile = await fillCachedMobileIfMissing(wxid, cache, cacheKey);
            log('  ✅ 使用缓存CK成功, userId: ' + loginData.userId + (mobile ? ' 手机号：' + mobile : ''));
        } else {
            if (cached) log('  ⚠️ 缓存CK失效，重新协议登录');

            // 2. 获取微信code
            const code = await getWxCode(wxid, APPID);
            log('  ✅ wx.login code获取成功');

            // 3. 获取openId和unionId
            const ids = await getOpenIdAndUnionId(code);
            openId = ids.openId;
            unionId = ids.unionId;
            log('  ✅ openId: ' + openId.substring(0, 10) + '...');

            // 4. 获取手机号授权code
            const phoneInfo = await getPhoneCodeInfo(wxid);
            const phoneCode = phoneInfo.phoneCode;
            log('  ✅ 手机号授权code获取成功' + (phoneInfo.mobile ? '，手机号：' + phoneInfo.mobile : ''));

            // 5. 登录
            loginData = await login(phoneCode, openId, unionId);
            if (!loginData) {
                log('❌ ' + display + ' 登录失败');
                return false;
            }
            token = loginData.token;
            log('  ✅ 登录成功, userId: ' + loginData.userId);

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
        await doSign(session, wxid, cache, cacheKey);
        await sleep(randomInt(1000, 2000));

        // 7. 动态发现页面活动 ID，然后执行 ROE 口令红包。
        const activityEntry = await discoverActivityEntry(session.token, session.openId, session.userId);
        const roeResult = await doRoeReward(session, wxid, cache, cacheKey, activityEntry);

        // 8. 查询红包列表，领取红包
        await sleep(randomInt(1000, 2000));
        let redPacketAmount = 0;
        let pendingRedPacketAmount = 0;
        let roeReward = 0;
        let claimedAmount = 0;
        // 记录已领取的 requestId，避免 claimExistingWatchRewards 和 unclaimedList 重复领取
        const claimedRequestIds = new Set();

        // 从 ROE 兑换结果中提取已领取金额
        if (roeResult?.existingClaim) {
            claimedAmount += roeResult.existingClaim.amount || 0;
            for (const item of (roeResult.activity?.exchangeRequestVoList || [])) {
                const rid = item.requestId || item.redPacketRequestId || '';
                if (rid) claimedRequestIds.add(rid);
            }
        }
        if (roeResult?.claimResult?.success) {
            claimedAmount += roeResult.claimResult.amount || 0;
            const newRid = roeResult.data?.redPacketRequestId || roeResult.data?.requestId || '';
            if (newRid) claimedRequestIds.add(newRid);
        }

        // 获取红包活动列表
        const activities = await getActivityList(session.token, session.openId, session.userId);
        if (activities && activities.length > 0) {
            log('  📋 红包活动列表: ' + activities.length + '个');
            for (const activity of activities) {
                if (activity.id && activity.title) {
                    log('  📌 ' + activity.title + ' (ID: ' + activity.id + ')');
                }
            }
        }

        // 获取未领取红包列表（通过 getRequestPage receiveStatus=0）
        const unclaimedList = await getUnclaimedList(session.token, session.openId, session.userId);
        if (unclaimedList && unclaimedList.length > 0) {
            log('  🎁 未领取红包: ' + unclaimedList.length + '个');
            for (const packet of unclaimedList) {
                if (packet.ticketCode || packet.requestId) {
                    const amount = Number(packet.amount || 0);
                    pendingRedPacketAmount += amount;
                    log('  🎯 未领红包: ' + (packet.describe || '') + ' 金额: ' + amount + '元 (ticketCode: ' + (packet.ticketCode || packet.requestId) + ')');

                    // 自动提现：领取未领取红包（跳过已处理的）
                    const pktRequestId = packet.requestId || '';
                    if (AUTO_CLAIM_H5_RED_PACKET && packet.ticketCode && pktRequestId && !claimedRequestIds.has(pktRequestId)) {
                        claimedRequestIds.add(pktRequestId);
                        log('  💰 自动领取未领红包...');
                        await updateRedPacketGetStatus(session.token, session.openId, session.userId, {
                            requestId: pktRequestId,
                            activityId: packet.activityId,
                            activityType: packet.activityType || '4',
                        });
                        const pktClaim = await claimRedPacket(
                            session.token, session.openId, session.userId,
                            pktRequestId, packet.ticketCode, packet.activityId, packet.activityType,
                            '', wxid, cache, cacheKey
                        );
                        if (pktClaim?.success) {
                            claimedAmount += pktClaim.amount || amount;
                            log('  ✅ 未领红包领取成功: ' + formatMoney(pktClaim.amount || amount) + '元' + (pktClaim.message ? ' (' + pktClaim.message + ')' : ''));
                        } else {
                            log('  ⚠️ 未领红包领取失败: ' + (pktClaim?.message || '未知'));
                        }
                        await sleep(randomInt(500, 1500));
                    }
                }
            }
        } else {
            log('  ℹ️ 没有未领取的红包');
        }

        // 获取红包领取历史：这里是账号累计已领取红包，用于最终汇总的"当前总获得红包"。
        let historyRedPacketAmount = 0;
        const requestPage = await getRequestPage(session.token, session.openId, session.userId);
        if (requestPage && requestPage.length > 0) {
            log('  📊 历史已领取红包: ' + requestPage.length + '条（非本次收益）');
            for (const item of requestPage) {
                if (item.amount) {
                    historyRedPacketAmount += Number(item.amount) || 0;
                }
            }
            log('  💰 历史已领取红包累计: ' + formatMoney(historyRedPacketAmount) + '元（非本次收益）');
        }

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
        if (claimedAmount > 0) {
            log('  💰 本次自动提现领取: ' + formatMoney(claimedAmount) + '元');
        }
        return { success: true, currentPoint, roeReward, redPacketAmount, historyRedPacketAmount, pendingRedPacketAmount, claimedAmount };

    } catch (e) {
        log('❌ 异常: ' + e.message);
        log('❌ ' + display + ' 异常: ' + e.message);
        return false;
    }
}

// ==================== 主逻辑 ====================
async function main() {
    log('🚀 红色火箭脚本启动');

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
            if (result && result.success) {
                successCount++;
                accounts[i].currentPoint = result.currentPoint || 0;
                accounts[i].roeReward = result.roeReward || 0;
                accounts[i].redPacketAmount = result.redPacketAmount || 0;
                accounts[i].historyRedPacketAmount = result.historyRedPacketAmount || 0;
                accounts[i].pendingRedPacketAmount = result.pendingRedPacketAmount || 0;
                accounts[i].claimedAmount = result.claimedAmount || 0;
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
    log('📊 执行完毕, 成功 ' + successCount + '/' + accounts.length);

    // 输出每个账号的汇总信息
    log('\n📋 账号汇总:');
    let totalClaimed = 0;
    for (const account of accounts) {
        const display = account.note || account.wxid;
        const currentPoint = account.currentPoint || 0;
        const redPacketAmount = Math.max(account.historyRedPacketAmount || 0, account.redPacketAmount || 0);
        const pendingRedPacketAmount = account.pendingRedPacketAmount || 0;
        const claimedAmount = account.claimedAmount || 0;
        totalClaimed += claimedAmount;
        log('当前账号: ' + display + ' 当前积分: ' + currentPoint + ' 当前总获得红包:' + formatMoney(redPacketAmount) + '元 当前未领红包: ' + formatMoney(pendingRedPacketAmount) + '元 本次自动提现: ' + formatMoney(claimedAmount) + '元');
    }
    if (totalClaimed > 0) {
        log('\n💰 全部账号本次自动提现合计: ' + formatMoney(totalClaimed) + '元');
    }

    // 推送通知
    await push_notification();
}

main().catch(e => { log('❌ 脚本异常: ' + e.message); log(e.stack); });
