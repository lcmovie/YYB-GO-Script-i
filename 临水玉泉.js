// name:临水玉泉
/**
微信协议-临水玉泉（getCode.js 统一版）
变量：WX_ID  wxid#备注 多号换行
cron: 10 10,13 * * *
  WX_ID 由共享 getCode.js 读取并智能路由 牛子/应用宝
  WECHAT_SERVER / YYB_SERVER / SERVER_TYPE 在 getCode.js 中配置
 */

const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { getSingleCode } = require('./getCode.js'); // 共享微信小程序 code 获取模块（自动路由牛子/应用宝，读取 WX_ID）

const APPID = 'wx21293beab739d5c3';
const KDT_ID = '44353481';
const CHECKIN_ID = '15129';
const WEAPP_VERSION = '2.233.4';
const CACHE_NAME = 'lsyq';
const CACHE_FILE = path.join(__dirname, `${CACHE_NAME}.json`);
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254181d) XWEB/19201';

const WXLSYQ = (process.env.WX_ID || '').trim(); // wxid#备注（由 getCode.js 读取并智能路由牛子/应用宝）

let notifyMsg = '';

function log(msg) {
  console.log(msg);
}

function randStr(n = 24) {
  const seed = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  for (let i = 0; i < n; i++) out += seed[Math.floor(Math.random() * seed.length)];
  return out;
}

function loadCache() {
  try {
    return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8')) || {};
  } catch {
    return {};
  }
}

function saveCache(cache) {
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf8');
}

function parseAccounts(raw) {
  return raw
    .split(/[@\n]/)
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => {
      const i = s.indexOf('#');
      if (i === -1) return { wxid: s, remark: s };
      return { wxid: s.slice(0, i).trim(), remark: s.slice(i + 1).trim() || s.slice(0, i).trim() };
    })
    .filter(x => x.wxid);
}

function extraData(cred = {}) {
  return JSON.stringify({
    sid: cred.sid || '',
    version: WEAPP_VERSION,
    clientType: 'weapp-miniprogram',
    client: 'weapp',
    bizEnv: '',
    uuid: cred.uuid || randStr(24),
    ftime: cred.ftime || Date.now()
  });
}

function commonHeaders(cred = {}) {
  return {
    'User-Agent': UA,
    'Content-Type': 'application/json',
    'Extra-Data': extraData(cred),
    'Referer': `https://servicewechat.com/${APPID}/108/page-frame.html`,
    'Accept-Encoding': 'gzip,compress,br,deflate'
  };
}

async function getWxCode(wxid) {
  try {
    return await getSingleCode(APPID, wxid);
  } catch (e) {
    throw new Error(`微信协议获取code失败: ${e.message}`);
  }
}

async function authByCode(wxCode, oldCred = {}) {
  const url = `https://uic.youzan.com/passport/general/auth.json?kdt_id=${KDT_ID}&app_id=${APPID}`;
  const body = {
    appId: APPID,
    code: wxCode,
    platformName: 'weapp',
    signature: 'windows',
    clientBiz: 'weapp_wsc',
    inWsc: true,
    kdtId: KDT_ID,
    extraBizData: {
      enterOptions: {
        extKdtId: Number(KDT_ID),
        path: 'pages/home/dashboard/index',
        query: {},
        scene: 1007,
        referrerInfo: {},
        apiCategory: 'default'
      },
      guideBizDataMap: { from_params: '' },
      sceneData: {}
    }
  };

  const { data } = await axios.post(url, body, {
    headers: commonHeaders(oldCred),
    timeout: 20000
  });

  if (data?.code !== 0 || !data?.data?.accessToken || !data?.data?.sessionId) {
    throw new Error(`youzan鉴权失败: ${JSON.stringify(data)}`);
  }

  return {
    accessToken: data.data.accessToken,
    sid: data.data.sessionId,
    uuid: oldCred.uuid || randStr(24),
    ftime: Date.now(),
    updateTime: new Date().toISOString()
  };
}

async function fetchUserInfo(cred) {
  const url = `https://h5.youzan.com/wscaccount/api/authorize/data.json?app_id=${APPID}&kdt_id=${KDT_ID}&access_token=${cred.accessToken}&appId=${APPID}&kdtId=${KDT_ID}`;
  const { data } = await axios.get(url, { headers: commonHeaders(cred), timeout: 15000 });
  return data;
}

async function fetchPoints(cred) {
  const url = `https://h5.youzan.com/wscuser/membercenter/init-data.json?kdt_id=${KDT_ID}&app_id=${APPID}&access_token=${cred.accessToken}&kdtId=${KDT_ID}&version=${WEAPP_VERSION}&onlineKdtId=${KDT_ID}&currentKdtId=${KDT_ID}&needConsumptionAboveCoupon=1`;
  const { data } = await axios.get(url, { headers: commonHeaders(cred), timeout: 15000 });
  return data;
}

async function doSign(cred) {
  const url = `https://h5.youzan.com/wscump/checkin/checkinV2.json?checkinId=${CHECKIN_ID}&app_id=${APPID}&kdt_id=${KDT_ID}&access_token=${cred.accessToken}`;
  const { data } = await axios.get(url, { headers: commonHeaders(cred), timeout: 15000 });
  return data;
}

async function refreshCred(acc, oldCred = {}) {
  log(`🧩 ${acc.remark} 调用微信协议获取新ck...`);
  const code = await getWxCode(acc.wxid);
  return await authByCode(code, oldCred);
}

async function getValidCred(acc, cache) {
  let cred = cache[acc.wxid];
  if (cred?.accessToken && cred?.sid) {
    try {
      const userRes = await fetchUserInfo(cred);
      if (userRes?.code === 0) {
        log(`✅ ${acc.remark} 使用缓存ck`);
        return { cred, userRes, fromCache: true };
      }
      log(`⚠️ ${acc.remark} 缓存ck失效，准备刷新`);
    } catch (e) {
      log(`⚠️ ${acc.remark} 校验缓存ck异常: ${e.message}`);
    }
  } else {
    log(`ℹ️ ${acc.remark} 无缓存ck，准备微信协议登录`);
  }

  cred = await refreshCred(acc, cred || {});
  cache[acc.wxid] = cred;
  saveCache(cache);

  const userRes = await fetchUserInfo(cred);
  if (userRes?.code !== 0) {
    throw new Error(`新ck校验失败: ${JSON.stringify(userRes)}`);
  }
  return { cred, userRes, fromCache: false };
}

async function sendNotify(title, content) {
  try {
    const notify = require('./sendNotify');
    await notify.sendNotify(title, content);
  } catch {
    // ignore
  }
}

async function main() {
  if (!WXLSYQ) {
    throw new Error('未配置变量 WX_ID（格式：wxid#备注，多账号换行或@分隔）');
  }

  const accounts = parseAccounts(WXLSYQ);
  if (!accounts.length) throw new Error('WX_ID 解析后无账号');

  const cache = loadCache();
  log(`共 ${accounts.length} 个账号，缓存名: ${CACHE_NAME}`);

  for (let i = 0; i < accounts.length; i++) {
    const acc = accounts[i];
    log(`\n================ 账号${i + 1}: ${acc.remark} ================`);

    try {
      const { cred, userRes } = await getValidCred(acc, cache);
      const u = userRes?.data?.userInfo || {};
      const mobile = (u.mobile || '').replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
      const nickname = u.nickname || '未知';

      const signRes = await doSign(cred);
      let signMsg = signRes?.msg || JSON.stringify(signRes);
      if (signRes?.code === 0) signMsg = '签到成功';

      const pointRes = await fetchPoints(cred);
      const points = pointRes?.code === 0 ? (pointRes?.data?.member?.stats?.points ?? '-') : '-';

      const line = `【${acc.remark}】${nickname} ${mobile} 签到:${signMsg} 签到后积分:${points}`;
      log(line);
      notifyMsg += `${line}\n`;
    } catch (e) {
      const line = `【${acc.remark}】失败: ${e.message}`;
      log(line);
      notifyMsg += `${line}\n`;
    }
  }

  await sendNotify('临水玉泉线上商城', notifyMsg.trim());
}

main().catch(e => {
  console.error(e.message || e);
  process.exit(1);
});
