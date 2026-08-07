// name:拼多多果园
/** cron: 26 9,13 * * *
 * 拼多多果园（微信协议版）
 *
 * 环境变量：
 *   WX_ID           必填，格式：wxid#备注，多账号换行或 & 分隔
 *   WECHAT_SERVER   必填，微信协议服务地址
 *   PDD_NO_RELOGIN  设为 '0' 或 'false' 关闭自动重登（默认开启）
 */

const { getSingleCode } = require('./getCode.js');
const getWxCode = (wxid, appid) => getSingleCode(appid, String(wxid).split('#')[0].trim());
const https = require('https');
const http = require('http');
const zlib = require('zlib');
const fs = require('fs');
const pathMod = require('path');

// ==================== 全局常量 ====================
const MINI_APP_ID = 'wx32540bd863b27570';
const XCX_VERSION = 'v8.6.21';
const PDD_APP_ID = 33;
const API_BASE = 'https://api.pinduoduo.com';
const ORCHARD_API_BASE = 'https://mobile.yangkeduo.com';
const MANOR_BASE = ORCHARD_API_BASE + '/proxy/api/api';

// 缓存文件
const CACHE_DIR = pathMod.join(process.cwd(), '.cache');
const COOKIE_CACHE_FILE = pathMod.join(CACHE_DIR, 'pdd_cookie_cache.json');

// 配置区
let ckName = 'WX_ID';
const WXID_RAW = (process.env.WX_ID || '').trim();
const WECHAT_SERVER = (process.env.WECHAT_SERVER || '').replace(/\/$/, '');
const NO_RELOGIN = process.env.PDD_NO_RELOGIN !== '0' && process.env.PDD_NO_RELOGIN !== 'false';

const SCRIPT_NAME = '拼多多果园';
const MULTI_SPLIT = ['\n', '&', '@'];

// 随机UA池
const UA_LIST = [
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 MicroMessenger/8.0.50',
    'Mozilla/5.0 (Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.50',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF XWEB/19895 miniProgram/wx32540bd863b27570'
];

// ==================== 通知模块 ====================
let _logMessages = [];
function log(str) {
    console.log(str);
    _logMessages.push(str);
}
async function push_notification() {
    let notify;
    try { notify = require('./notify'); } catch (e) { notify = null; }
    const title = SCRIPT_NAME;
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

// ==================== 工具函数 ====================
function getRandomUA() { return UA_LIST[Math.floor(Math.random() * UA_LIST.length)]; }

function mask(s, h = 4, t = 4) {
    s = String(s);
    if (s.length <= h + t) return s.substring(0, h) + "***";
    return s.substring(0, h) + "***" + s.substring(s.length - t);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function randomSleep(minMs = 200, maxMs = 800) {
    const ms = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
    return sleep(ms);
}

function shortJson(obj, limit = 180) {
    let s = typeof obj === 'string' ? obj : JSON.stringify(obj || {});
    return s.length > limit ? s.substring(0, limit) + "..." : s;
}

function okCode(res) {
    if (!res) return false;
    if (res.success === true) return true;
    if (parseInt(res.error_code || -1, 10) === 0) return true;
    if (res.code === 0) return true;
    return false;
}

function ensureCacheDir() {
    if (!fs.existsSync(CACHE_DIR)) fs.mkdirSync(CACHE_DIR, { recursive: true });
}

// Cookie 转换
function cookieStrToDict(cookieStr) {
    const cookies = {};
    for (const item of cookieStr.split(';')) {
        const trimmed = item.trim();
        if (trimmed.includes('=')) {
            const idx = trimmed.indexOf('=');
            cookies[trimmed.substring(0, idx).trim()] = trimmed.substring(idx + 1).trim();
        }
    }
    return cookies;
}

function cookieDictToStr(cookies) {
    return Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; ');
}

function extractUid(cookieStr) {
    const m = cookieStr.match(/pdd_user_id=(\d+)/);
    return m ? m[1] : '';
}

// ==================== 缓存读写 ====================
function readCookieCache() {
    try {
        ensureCacheDir();
        if (!fs.existsSync(COOKIE_CACHE_FILE)) return {};
        return JSON.parse(fs.readFileSync(COOKIE_CACHE_FILE, 'utf-8')) || {};
    } catch (e) {
        return {};
    }
}
function writeCookieCache(data) {
    try {
        ensureCacheDir();
        fs.writeFileSync(COOKIE_CACHE_FILE, JSON.stringify(data, null, 2), 'utf-8');
    } catch (e) {}
}

function getCachedCookie(wxid) {
    const cache = readCookieCache();
    const entry = cache[wxid] || {};
    return entry.cookie_str || '';
}
function saveCachedCookie(wxid, cookieStr) {
    const cache = readCookieCache();
    cache[wxid] = { cookie_str: cookieStr, updatedAt: new Date().toISOString() };
    writeCookieCache(cache);
}

// ==================== 账号解析 ====================
function parseAccounts(raw) {
    let sep = null;
    for (const s of MULTI_SPLIT) { if (raw.includes(s)) { sep = s; break; } }
    const items = sep ? raw.split(sep) : [raw];
    return items.map(item => {
        item = (item || '').trim();
        if (!item) return null;
        const idx = item.lastIndexOf('#');
        if (idx > 0) return { wxid: item.substring(0, idx).trim(), note: item.substring(idx + 1).trim() };
        return { wxid: item, note: '' };
    }).filter(x => x && x.wxid);
}

// ==================== Node.js HTTP 引擎 ====================
function httpRequest(opts) {
    return new Promise((resolve) => {
        const urlStr = opts.url;
        if (!urlStr) { resolve({ status: 0, body: '', error: 'no url' }); return; }

        const parsed = new URL(urlStr);
        const isHttps = parsed.protocol === 'https:';
        const lib = isHttps ? https : http;

        const reqOpts = {
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname + parsed.search,
            method: opts.method || 'POST',
            headers: opts.headers || {}
        };

        const req = lib.request(reqOpts, (res) => {
            const chunks = [];
            let stream = res;
            const encoding = res.headers['content-encoding'];
            if (encoding === 'gzip') stream = res.pipe(zlib.createGunzip());
            else if (encoding === 'deflate') stream = res.pipe(zlib.createInflate());
            else if (encoding === 'br') stream = res.pipe(zlib.createBrotliDecompress());

            stream.on('data', (chunk) => chunks.push(chunk));
            stream.on('end', () => {
                const body = Buffer.concat(chunks).toString('utf-8');
                resolve({ status: res.statusCode, headers: res.headers, body });
            });
            stream.on('error', (e) => resolve({ status: res.statusCode, body: '', error: e.message }));
        });

        req.on('error', (e) => {
            log(`[HTTP] ${opts.url} 错误: ${e.message}`);
            resolve({ status: 0, body: '', error: e.message });
        });

        if (opts.body) req.write(opts.body);
        req.end();
    });
}

async function jsonPost(url, headers, bodyObj) {
    const resp = await httpRequest({
        url,
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json;charset=UTF-8' },
        body: JSON.stringify(bodyObj)
    });
    if (resp.error) return null;
    try { return JSON.parse(resp.body); }
    catch { return null; }
}

// ==================== 微信协议：获取 code ====================
// 使用 getCode.js 统一接口

// ==================== PDD 登录（单步登录）====================
async function pddSingleLogin(wxid) {
    log(`  🔐 Code登录 wxid=${mask(wxid)} ...`);
    const code = await getWxCode(wxid, MINI_APP_ID);
    log(`  [1/2] 获取code: ${mask(code, 6, 6)}`);
    await randomSleep(300, 600);

    const loginBody = {
        code: code,
        has_auth: false,
        app_id: PDD_APP_ID,
        support_enhance_type: 3,
        xcx_version: XCX_VERSION
    };

    const loginHeaders = {
        'Content-Type': 'application/json;charset=UTF-8',
        'User-Agent': getRandomUA(),
        'Referer': `https://servicewechat.com/${MINI_APP_ID}/1840/page-frame.html`,
        'x-xcx-queries': `mini_program_name=pdd;mp_theme_version=${XCX_VERSION}`,
        'xweb_xhr': '1',
        'hd-xcx-model': 'microsoft'
    };

    // 使用 Session 方式获取 Set-Cookie
    let setCookieStr = '';
    const resp = await httpRequest({
        url: API_BASE + '/login',
        method: 'POST',
        headers: loginHeaders,
        body: JSON.stringify(loginBody)
    });
    if (resp.headers && resp.headers['set-cookie']) {
        const sc = Array.isArray(resp.headers['set-cookie']) ? resp.headers['set-cookie'] : [resp.headers['set-cookie']];
        setCookieStr = sc.map(c => c.split(';')[0]).join('; ');
    }

    const result = JSON.parse(resp.body || '{}');
    log(`登录返回片段: ${shortJson(result, 300)}`);

    // 风控拦截
    if (result.error_code === 54002) throw new Error('登录触发54002人机验证，需手动小程序登录');
    if (result.error_code === 43042) throw new Error('43042验证失败，当前账号风控拦截');

    const root = result.data || result;
    const accessToken = root.access_token || root.token;
    const uid = String(root.uid || root.user_id || '');
    const uin = root.uin || '';
    const acid = root.acid || '';

    if (!uid || !accessToken) throw new Error('登录未返回uid/access_token: ' + shortJson(result));

    const cookieParts = [
        `PDDAccessToken=${accessToken}`,
        `pdd_user_id=${uid}`,
        `pdd_user_uin=${uin}`
    ];
    if (acid) cookieParts.push(`acid=${acid}`);
    if (setCookieStr) cookieParts.push(setCookieStr);

    const cookieStr = cookieParts.join('; ');
    log(`  [2/2] 登录成功! uid=${uid}, uin=${mask(uin)}`);
    await randomSleep(400, 700);
    return { cookieStr, uid, uin };
}

// ==================== 果园通用请求头 ====================
function makeManorHeaders(cookieStr) {
    return [
        {
            'User-Agent': getRandomUA(),
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json;charset=UTF-8',
            'Origin': ORCHARD_API_BASE,
            'Referer': `${ORCHARD_API_BASE}/garden_index_lz_0.html`
        },
        cookieStrToDict(cookieStr)
    ];
}

async function manorPost(url, pdduid, cookieStr, body) {
    const [headers, cookies] = makeManorHeaders(cookieStr);
    return jsonPost(`${url}?pdduid=${pdduid}`, headers, body);
}

// ==================== 业务API ====================
// 查询水滴
async function getWater(pdduid, cookieStr) {
    const result = await manorPost(MANOR_BASE + '/manor-gateway/manor/query/user/water?is_back=1', pdduid, cookieStr, {});
    return (result && result.water_amount) || 0;
}

// 浇水
async function waterTree(pdduid, cookieStr, tubetoken, maxTimes = 50) {
    let water = await getWater(pdduid, cookieStr);
    log(`  [浇水] 当前水滴: ${water}`);
    if (water < 10) { log(`  [浇水] 水滴不足10颗，跳过`); return 0; }

    const count = Math.min(maxTimes, Math.floor(water / 10));
    let watered = 0;
    let currWater = water;

    for (let i = 0; i < count; i++) {
        const body = {
            atw: true,
            location_auth: false,
            last_stay_time: Math.floor(Math.random() * 40) + 10,
            can_trigger_random_mission: false,
            product_scene: 0,
            minor: false,
            ext_params: { can_trigger201824: true },
            mission_type: 0,
            cost_water_amount: 10,
            merge_cost: false,
            fun_id: 'wechat_app_home',
            lower_end_device: false,
            cost_water_competition_in_scene_icon: false,
            is_small_screen: true,
            tubetoken: tubetoken,
            fun_pl: 2
        };
        const result = await manorPost(MANOR_BASE + '/manor/water/cost', pdduid, cookieStr, body);
        const left = result?.now_water_amount;
        if (left != null && left < currWater) {
            currWater = left;
            watered++;
            log(`  [浇水] ${watered}/${count}, 剩余: ${left}`);
            if (left < 10) break;
            await randomSleep(200, 400);
        } else {
            log(`  [浇水] 水滴未扣除，停止`);
            break;
        }
    }
    const final = await getWater(pdduid, cookieStr);
    log(`  [浇水] 完成! 浇水${watered}次, 剩余水滴: ${final}`);
    return watered;
}

// 首页
async function getHomePage(pdduid, cookieStr, tubetoken) {
    const body = {
        mission_type: 0,
        fun_id: 'wechat_app_home',
        message_source: null,
        page_type: 'HOME_PAGE',
        push_source_mission_type: 0,
        fruit_config_version: '',
        unlock_scene_version: '',
        app_home_click_icon_type: null,
        tubetoken: tubetoken,
        push_act_source: null,
        need_show_home_popup: true,
        fun_pl: 2
    };
    const result = await manorPost(MANOR_BASE + '/manor-query/proxy/home/page', pdduid, cookieStr, body);
    if (!result) return [null, null];
    if (result.error_code === 40001) { log(`  [首页] 验证失败, Cookie可能已过期`); return [null, null]; }
    return [result.tubetoken || tubetoken, result.water_amount || 0];
}

// 任务列表
async function getMissionList(pdduid, cookieStr, tubetoken) {
    log(`  [任务] 获取任务列表...`);
    const requestParams = { act201015EntryInfo: {}, act201036EntryInfo: {} };
    for (let i = 1; i <= 8; i++) {
        requestParams.act201015EntryInfo[String(i)] = { needRefresh: true };
        requestParams.act201036EntryInfo[String(i)] = { needRefresh: true };
    }
    const body = {
        activity_id_list: [201015, 201036],
        mission_types: [38160, 38242, 38090, 38451, 37859, 38428, 38500, 38501, 38502, 38503, 38504, 38505, 38600, 38601, 38700, 38701, 38800, 38900, 37900, 37950, 38000, 38050, 38100, 38150],
        request_params: requestParams,
        lower_end_device: false,
        tubetoken: tubetoken,
        fun_pl: 2
    };
    const result = await manorPost(MANOR_BASE + '/manor/mission/list', pdduid, cookieStr, body);
    if (!result) return [], [];

    const activityMap = result.activity_vo_map || {};
    const tasks = [];
    for (const [actIdStr, actData] of Object.entries(activityMap)) {
        const actMissions = actData.mission_list || {};
        if (!actMissions) continue;
        for (const [missionIdStr, m] of Object.entries(actMissions)) {
            const rewardInfo = m.reward_info || [];
            let rewardAmount = 0;
            let rewardType = '';
            for (const ri of rewardInfo) {
                if (ri.reward_type === 1) { rewardAmount = ri.min_reward_amount || 0; rewardType = '水滴'; break; }
            }
            if (!rewardAmount && rewardInfo.length > 0) { rewardAmount = rewardInfo[0].min_reward_amount || 0; rewardType = `T${rewardInfo[0].reward_type || '?'}`; }
            tasks.push({
                activity_id: parseInt(actIdStr),
                mission_id: parseInt(missionIdStr),
                type: m.type,
                unified_status: m.unified_status,
                is_draw: m.is_draw || false,
                is_open: m.is_open || false,
                finished_count: m.finished_count || 0,
                max_count: m.max_count || 0,
                reward_amount: rewardAmount,
                reward_type: rewardType
            });
        }
    }
    const canClaim = tasks.filter(t => !t.is_draw && t.is_open && t.finished_count >= 1);
    const needAccept = tasks.filter(t => !t.is_draw && !t.is_open && t.finished_count >= 1);
    log(`  [任务] 共${tasks.length}个, 可领取: ${canClaim.length}, 需接受: ${needAccept.length}`);
    return [canClaim, needAccept];
}

// 接受任务
async function acceptMission(pdduid, cookieStr, tubetoken, activityId, missionId) {
    const body = { mission_id: missionId, activity_id: activityId, tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor/mission/accept', pdduid, cookieStr, body);
    await randomSleep();
    if (okCode(result)) { log(`  [任务] 接受成功 act=${activityId} id=${missionId}`); return true; }
    log(`  [任务] 接受失败 act=${activityId} id=${missionId}: ${result.error_msg || ''}`);
    return false;
}

// 领取任务奖励
async function claimMission(pdduid, cookieStr, tubetoken, activityId, missionId) {
    const body = { mission_id: missionId, activity_id: activityId, tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor/mission/draw', pdduid, cookieStr, body);
    await randomSleep();
    if (okCode(result)) { const reward = result.water || result.reward_amount || 0; log(`  [任务] 领取成功 act=${activityId} id=${missionId}: +${reward}水滴`); return true; }
    log(`  [任务] 领取失败 act=${activityId} id=${missionId}: ${result.error_msg || ''}`);
    return false;
}

// 签到
async function dailyCheckin(pdduid, cookieStr, tubetoken) {
    log(`  [签到] 签到中...`);
    const body = { type: 201811, params: { ui_id: 3, type: 2 }, fun_id: 'wechat_app_home', tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor/common/apply/activity', pdduid, cookieStr, body);
    await randomSleep();
    if (okCode(result)) { log(`  [签到] 成功!`); return true; }
    log(`  [签到] 今日已签到`);
    return false;
}

// ==================== 偷水逻辑 ====================
// 获取好友列表
async function getFriendList(pdduid, cookieStr, tubetoken) {
    log(`  [偷水] 获取好友列表...`);
    const body = { page_num: 1, tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor-query/friend/list/page', pdduid, cookieStr, body);
    if (!result) return [];
    const friendList = result.friend_list || [];
    const canSteal = friendList.filter(f => {
        const ss = f.steal_water_status || {};
        return ss.status === 2;
    }).map(f => ({ uid: f.uid, nickname: f.nickname || '未知', amount: f.amount || 0 }));
    log(`  [偷水] 可偷好友: ${canSteal.length} 人`);
    return canSteal;
}

// 获取偷水次数
async function getStealChances(pdduid, cookieStr, tubetoken) {
    const body = { tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor/steal/chance/lack', pdduid, cookieStr, body);
    if (!result) return 0, [];
    const activityMap = result.activity_vo_map || {};
    const stealInfo = activityMap['201423'] || {};
    const freeChance = stealInfo.free_chance || 0;
    const dailyFreeChance = stealInfo.daily_free_chance || 0;
    const restChance = stealInfo.rest_chance || 0;
    const robots = stealInfo.robots || [];
    log(`  [偷水] 免费次数: ${freeChance}, 每日总次数: ${dailyFreeChance}, 剩余: ${restChance}`);
    const robotUids = robots.map(r => ({ uid: r.uid, nickname: r.nickname || '机器人', water: r.water || 0 }));
    return [restChance, robotUids];
}

// 从单个好友偷水
async function stealWaterFromFriend(pdduid, cookieStr, tubetoken, friendUid, dogStatus) {
    const body = { friend_uid: friendUid, steal_type: 10, dog_status: dogStatus, tubetoken: tubetoken, fun_pl: 2 };
    const result = await manorPost(MANOR_BASE + '/manor/steal/water', pdduid, cookieStr, body);
    const stealAmount = (result?.steal_amount || 0) || 0;
    const bitten = (result?.bitten_water || 0) || 0;
    let reason = result?.error_msg || result?.msg || result?.message || '';
    const code = result?.error_code || result?.code;
    if (code && reason) reason = `${code}: ${reason}`;
    else if (code) reason = String(code);
    return { stealAmount, bitten, reason };
}

// 批量偷水
async function stealFromFriends(pdduid, cookieStr, tubetoken) {
    try {
        const friends = await getFriendList(pdduid, cookieStr, tubetoken);
        const [restChance, robotUids] = await getStealChances(pdduid, cookieStr, tubetoken);
    } catch (e) {
        log(`  [偷水] 获取偷水信息失败，跳过: ${e.message}`);
        return;
    }

    // 重新获取（上面catch会丢失数据）
    const friends = await getFriendList(pdduid, cookieStr, tubetoken);
    const [restChance, robotUids] = await getStealChances(pdduid, cookieStr, tubetoken);

    const allTargets = friends.map(f => ({ uid: f.uid, nickname: f.nickname, amount: f.amount })).concat(robotUids);
    if (!allTargets.length) { log(`  [偷水] 没有可偷的目标`); return; }

    let totalStolen = 0;
    let stealCount = 0;
    const maxSteals = restChance > 0 ? Math.min(restChance, allTargets.length) : allTargets.length;
    log(`  [偷水] 开始偷水, 最多 ${maxSteals} 次...`);

    for (let i = 0; i < maxSteals; i++) {
        const target = allTargets[i];
        if ((target.amount || 0) <= 0) continue;

        let stolen = 0;
        let lastDog = 0;
        let lastReason = '';
        const dogList = [1, 2, 3].sort(() => Math.random() - 0.5);

        for (const dog of dogList) {
            lastDog = dog;
            const r = await stealWaterFromFriend(pdduid, cookieStr, tubetoken, target.uid, dog);
            lastReason = r.reason;
            await randomSleep(100, 200);
            if (r.stealAmount > 0) { stolen = r.stealAmount; break; }
        }

        if (stolen > 0) {
            totalStolen += stolen;
            stealCount++;
            log(`  [偷水] uid=${target.uid} ${target.nickname} dog=${lastDog}: +${stolen}滴`);
        } else {
            const suffix = lastReason ? `，原因: ${lastReason}` : '';
            log(`  [偷水] uid=${target.uid} ${target.nickname} dog=${lastDog}: 未偷到(已试3个狗位${suffix})`);
        }
        await randomSleep(300, 600);
    }
    log(`  [偷水] 完成! 共偷 ${stealCount} 次, 获得 ${totalStolen} 水滴`);
}

// ==================== 单账号处理 ====================
async function processAccount(accountInfo) {
    const wxid = accountInfo.wxid;
    const note = accountInfo.note || '';
    const display = note || wxid;

    log(`\n${'='.repeat(48)}`);
    log(`▶ 账号: ${display}`);
    log('='.repeat(48));

    let cookieStr = getCachedCookie(wxid);
    let pdduid = '';

    // 校验缓存
    if (cookieStr) {
        pdduid = extractUid(cookieStr);
        if (pdduid) {
            const cookies = cookieStrToDict(cookieStr);
            const tubetoken = cookies.tubetoken || '';
            const [newToken, testWater] = await getHomePage(pdduid, cookieStr, tubetoken);
            if (newToken !== null) {
                log(`缓存Cookie有效, uid=${pdduid}, 水滴=${testWater}`);
            } else {
                log(`缓存Cookie失效, 重新登录`);
                cookieStr = '';
            }
        } else {
            cookieStr = '';
        }
    }

    // 登录分支
    if (!cookieStr) {
        if (NO_RELOGIN === false) {
            log('[跳过] 开启禁止自动重登，缓存失效不执行');
            return;
        }
        try {
            const loginResult = await pddSingleLogin(wxid);
            cookieStr = loginResult.cookieStr;
            pdduid = loginResult.uid;
            saveCachedCookie(wxid, cookieStr);
        } catch (e) {
            log(`❌ 登录失败: ${e.message}`);
            return;
        }
    }

    if (!pdduid) pdduid = extractUid(cookieStr);
    if (!pdduid) { log(`❌ Cookie中无 pdd_user_id`); return; }

    log(`UID: ${pdduid}`);

    // 刷新tubetoken
    const cookies = cookieStrToDict(cookieStr);
    let tubetoken = cookies.tubetoken || '';
    const [newToken, water] = await getHomePage(pdduid, cookieStr, tubetoken);
    if (newToken === null) { log(`❌ 首页加载失败, Cookie 无效`); return; }
    if (newToken && newToken !== tubetoken) {
        tubetoken = newToken;
        cookies.tubetoken = tubetoken;
        cookieStr = cookieDictToStr(cookies);
        saveCachedCookie(wxid, cookieStr);
    }
    log(`当前水滴: ${water}`);

    // 任务流程
    await dailyCheckin(pdduid, cookieStr, tubetoken);
    await randomSleep(500, 1000);

    await waterTree(pdduid, cookieStr, tubetoken, 50);
    await randomSleep(500, 1000);

    const [canClaim, needAccept] = await getMissionList(pdduid, cookieStr, tubetoken);
    if (needAccept.length > 0) {
        log(`\n  [任务] 正在接受 ${needAccept.length} 个任务...`);
        for (const t of needAccept) {
            await acceptMission(pdduid, cookieStr, tubetoken, t.activity_id, t.mission_id);
            await randomSleep(400, 800);
        }
    }
    if (canClaim.length > 0) {
        log(`\n  [任务] 正在领取 ${canClaim.length} 个任务...`);
        for (const t of canClaim) {
            await claimMission(pdduid, cookieStr, tubetoken, t.activity_id, t.mission_id);
            await randomSleep(400, 800);
        }
    }

    // 偷水
    await stealFromFriends(pdduid, cookieStr, tubetoken);

    const final = await getWater(pdduid, cookieStr);
    log(`\n最终水滴: ${final}`);

    return final;
}

// ==================== 主流程 ====================
const startTime = Date.now();

async function main() {
    log(`🔔${SCRIPT_NAME}, 开始!`);

    if (!WXID_RAW) {
        log(`❌ 未找到 ${ckName} 环境变量`);
        await push_notification();
        return;
    }
    if (!WECHAT_SERVER) {
        log('❌ 未找到 WECHAT_SERVER 环境变量');
        await push_notification();
        return;
    }

    const accounts = parseAccounts(WXID_RAW);
    log(`共 ${accounts.length} 个账号\n`);

    for (let i = 0; i < accounts.length; i++) {
        try {
            await processAccount(accounts[i]);
        } catch (e) {
            log(`❌ 账号异常: ${e.message}`);
        }
        if (i < accounts.length - 1) {
            const delaySec = Math.floor(Math.random() * 45) + 45;
            log(`⏳ 等待 ${delaySec} 秒...`);
            await sleep(delaySec * 1000);
        }
    }

    log(`\n${'='.repeat(48)}`);
    log('📊 全部账号执行完毕');

    // 推送通知
    await push_notification();

    const endTime = ((Date.now()) - startTime) / 1000;
    log(`🔔${SCRIPT_NAME}, 结束! 🕛 ${endTime.toFixed(1)} 秒`);
}

main().catch((e) => { log(`❌ 运行出错: ${e.message}`); });
