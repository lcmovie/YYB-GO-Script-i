#!/usr/bin/env node
// name:问问农
/**
 * 问问农
 * cron: 47 10,15 * * *
 *
 * 功能：
 * 1) wx.login code -> /users/wechat-pre-login -> loginInfoAtom(token)
 * 2) 查询 /v2/profile/{yaraUserId}/signin
 * 3) 执行会员签到（/modules/campaigncenter/signin）
 * 4) 分享赚积分（/modules/campaigncenter/signin/share）
 * 5) 自动任务（member task-center）
 *
 * 环境变量：
 * - WX_ID               多账号，换行或&分隔（兼容旧变量 wwnhd）
 *                       推荐：wxid_xxx#备注
 *                       兼容：
 *                        1) bffToken#yaraUserId
 *                        2) bffToken#yaraUserId#consumerToken#accountId
 *                        3) consumerToken
 * - WECHAT_SERVER       微信协议服务地址（可选，在 getCode.js 中配置）
 * - WWN_MAIN_APPID      默认 wx61a9d721d3396d1b
 * - WWN_MEMBER_APPID    默认 wxc5d513880ace81a4
 * - WWN_ACCOUNT_ID      默认 634f5f28a0e71c29500b0313
 * - WWN_ENABLE_SIGNIN   1开启会员签到(默认)，0关闭
 * - WWN_ENABLE_SHARE    1开启分享赚积分(默认)，0关闭
 * - WWN_SHARE_TIMES     分享调用次数，默认10
 * - WWN_SHARE_DELAY_MS  分享间隔毫秒，默认300
 * - WWN_SHARE_RETRY     分享频控重试次数，默认3
 * - WWN_ENABLE_TASKS    1开启自动任务(默认)，0仅登录+签到+分享
 * - WWN_SIGNIN_TEMPLATE_IDS  逗号分隔模板ID（默认内置1个）
 * - WWN_MAX_PER_TASK    单任务最多上报次数，默认5
 * - WWN_EVENT_WHITELIST 逗号分隔，任务事件白名单
 */

'use strict';

const { getSingleCode } = require('./getCode');
const { sendNotify } = require('./sendNotify');

const ENV_NAME = 'wwnhd';

const BFF = 'https://fcc-prd-bff.yaradigitalfarming.cn';
const CONSUMER = 'https://consumer-api.quncrm.com';
const OAUTH_BASE = process.env.WWN_OAUTH_BASE || 'https://oauth.quncrm.com';

const MAIN_APPID = process.env.WWN_MAIN_APPID || 'wx61a9d721d3396d1b';
const MEMBER_APPID = process.env.WWN_MEMBER_APPID || 'wxc5d513880ace81a4';
const ACCOUNT_ID_DEFAULT = process.env.WWN_ACCOUNT_ID || '634f5f28a0e71c29500b0313';

const MAIJS_VERSION = process.env.WWN_MAIJS_VERSION || '1.50.0';
const APP_VERSION = process.env.WWN_APP_VERSION || '1.96.3.535f053';
const APP_NAME = process.env.WWN_APP_NAME || '群脉电商';
const ENV_VERSION = process.env.WWN_ENV_VERSION || 'release';

const ENABLE_TASKS = (process.env.WWN_ENABLE_TASKS || '1') !== '0';
const ENABLE_SIGNIN = (process.env.WWN_ENABLE_SIGNIN || '1') !== '0';
const ENABLE_SHARE = (process.env.WWN_ENABLE_SHARE || '1') !== '0';
const SHARE_TIMES_RAW = Number(process.env.WWN_SHARE_TIMES || 10);
const SHARE_TIMES = Number.isFinite(SHARE_TIMES_RAW) && SHARE_TIMES_RAW > 0 ? Math.floor(SHARE_TIMES_RAW) : 10;
const SHARE_DELAY_MS_RAW = Number(process.env.WWN_SHARE_DELAY_MS || 300);
const SHARE_DELAY_MS = Number.isFinite(SHARE_DELAY_MS_RAW) && SHARE_DELAY_MS_RAW >= 0 ? Math.floor(SHARE_DELAY_MS_RAW) : 300;
const SHARE_RETRY_RAW = Number(process.env.WWN_SHARE_RETRY || 3);
const SHARE_RETRY = Number.isFinite(SHARE_RETRY_RAW) && SHARE_RETRY_RAW > 0 ? Math.floor(SHARE_RETRY_RAW) : 3;
const MAX_PER_TASK = Number(process.env.WWN_MAX_PER_TASK || 5);
const SIGNIN_TEMPLATE_IDS = (process.env.WWN_SIGNIN_TEMPLATE_IDS || 'r0RQspXnqWh9WaFblGjLwWXrcNjPceXbvYmfULrjvXE')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);

const UA_BFF = 'Mozilla/5.0 MicroMessenger MiniProgram';
const UA_CONSUMER = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.70';

const DEFAULT_EVENT_WHITELIST = [
  'maievent-campaigncenter-signin',
  'c_click_nutrition_plan_card',
  'c_click_fertilizer_item',
  'c_click_exper_demo_card',
  'c_click_nutrient_story_cards',
  'c_view_post_page_detail',
  'c_click_share_button',
  'c_click_share_pdd_button',
];

const EVENT_WHITELIST = (process.env.WWN_EVENT_WHITELIST || DEFAULT_EVENT_WHITELIST.join(','))
  .split(',').map(s => s.trim()).filter(Boolean);

const TASK_CENTER_URL = 'member/pages/task-center/index?_pageUrl=pages%252Ftask-center%252Findex%253Fstatus%253Dpublished%2526pageId%253D65decd67c201da00527e4ac1&pageId=65decd67c201da00527e4ac1&status=published';

const fetchFn = globalThis.fetch || ((...args) => import('node-fetch').then(({ default: f }) => f(...args)));

function splitAccounts(raw) {
  return String(raw || '').split(/[\n@&\r]+/).map(s => {
    let x = s.trim();
    if (x.includes('=')) {
      x = x.split('=', 2)[1].trim();
    }
    return x;
  }).filter(Boolean);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowISO() {
  const d = new Date();
  const tz = -d.getTimezoneOffset();
  const sign = tz >= 0 ? '+' : '-';
  const pad = n => String(Math.floor(Math.abs(n))).padStart(2, '0');
  const hh = pad(tz / 60), mm = pad(tz % 60);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3,'0')}${sign}${hh}:${mm}`;
}

function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

function decodeJwtPayload(token) {
  try {
    const parts = String(token || '').split('.');
    if (parts.length < 2) return null;
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
  } catch {
    return null;
  }
}

function stripBearer(s) {
  return String(s || '').replace(/^Bearer\s+/i, '').trim();
}

function isUuidLike(s) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(s || '').trim());
}

function looksLikeToken(s) {
  const x = stripBearer(s);
  if (!x) return false;
  // JWT
  if (x.split('.').length === 3 && decodeJwtPayload(x)) return true;
  // 兜底：较长且无空白（兼容部分非JWT token）
  return x.length >= 60 && !/\s/.test(x);
}

function isLikelyWxIdentifier(s) {
  const x = String(s || '').trim();
  if (!x) return false;
  if (x.startsWith('wx:')) return true;      // 显式前缀
  if (x.startsWith('wxid_')) return true;    // 常见微信id
  if (x.length > 64) return false;           // 太长更像token
  if (/[.\s]/.test(x)) return false;         // 含点通常是JWT
  // 兼容非 wxid_ 开头的微信标识
  return /^[a-zA-Z0-9_-]{4,}$/.test(x);
}

function fmtTs(ts) {
  try {
    const d = new Date(Number(ts) * 1000);
    // 固定按+08输出
    const p = n => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p((d.getUTCHours()+8)%24)}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} +08:00`;
  } catch {
    return String(ts);
  }
}

function printTokenInfo(label, token) {
  const p = decodeJwtPayload(token);
  const iat = Number(p?.iat || 0);
  const exp = Number(p?.exp || 0);
  if (!iat || !exp) {
    console.log(`${label} 非JWT或无法解码`);
    return;
  }
  const leftSec = exp - Math.floor(Date.now() / 1000);
  console.log(`${label} iat=${fmtTs(iat)} exp=${fmtTs(exp)} 有效期=${Math.floor((exp - iat) / 3600)}h 剩余≈${Math.max(0, Math.floor(leftSec / 60))}min`);
}

async function httpJson(url, { method = 'GET', headers = {}, body, timeout = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error('timeout')), timeout);
  try {
    const resp = await fetchFn(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await resp.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
    if (!resp.ok) {
      throw new Error(`${method} ${url} -> ${resp.status} ${text.slice(0, 400)}`);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function getWxCode(wxid, appid) {
  try {
    return await getSingleCode(appid, wxid);
  } catch (e) {
    throw new Error(`wx.login失败: ${e.message || e}`);
  }
}

async function preLoginByCode(code) {
  const payload = {
    code,
    socialPlatform: 'wechat',
    launchOptions: { scene: 1001, query: {} },
  };
  const ret = await httpJson(`${BFF}/users/wechat-pre-login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': UA_BFF,
    },
    body: payload,
  });
  return ret?.data || ret;
}

async function bffSigninStatus(token, yaraUserId) {
  return httpJson(`${BFF}/v2/profile/${encodeURIComponent(yaraUserId)}/signin`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': UA_BFF,
    },
  });
}

async function oauthWeapp(accountId, appid, code) {
  const url = `${OAUTH_BASE}/${accountId}/v2/weapp/oauth`;
  const payload = {
    scope: 'base',
    code,
    watermark: { appid },
    is_group: 'false',
  };
  const ret = await httpJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: payload,
  });

  const data = ret?.data && typeof ret.data === 'object' ? ret.data : ret;
  if (!data?.accessToken) {
    throw new Error(`获取consumer token失败: ${JSON.stringify(ret)}`);
  }
  return data;
}

function buildConsumerParams(clientId, extra = []) {
  const pairs = [
    ['maijsVersion', MAIJS_VERSION],
    ['clientId', clientId],
    ['appVersion', APP_VERSION],
    ['appName', APP_NAME],
    ['envVersion', ENV_VERSION],
    ...extra,
    ['clientTime', nowISO()],
  ];
  const usp = new URLSearchParams();
  for (const [k, v] of pairs) {
    if (Array.isArray(v)) v.forEach(x => usp.append(k, String(x)));
    else if (v !== undefined && v !== null) usp.append(k, String(v));
  }
  return usp.toString();
}

async function consumerReq({ method = 'GET', path, token, accountId, clientId, query = [], body }) {
  const url = `${CONSUMER}${path}?${buildConsumerParams(clientId, query)}`;
  const headers = {
    'X-Requested-With': 'XMLHttpRequest',
    'X-Access-Token': token,
    'X-Account-Id': accountId,
    'content-type': 'application/json; charset=utf-8',
    accept: 'application/json, text/plain, */*',
    'user-agent': UA_CONSUMER,
  };
  const resp = await fetchFn(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let data = null;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!resp.ok) throw new Error(`${method} ${path} -> ${resp.status} ${text.slice(0, 400)}`);
  return data;
}

function currentYearMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}`;
}

async function consumerSigninStats(consumerToken, accountId, clientId) {
  return consumerReq({
    method: 'GET',
    path: '/modules/campaigncenter/signin/stats',
    token: consumerToken,
    accountId,
    clientId,
    query: [['month', currentYearMonth()]],
  });
}

async function consumerDoSignin(consumerToken, accountId, clientId) {
  return consumerReq({
    method: 'POST',
    path: '/modules/campaigncenter/signin',
    token: consumerToken,
    accountId,
    clientId,
    body: {
      templateIds: SIGNIN_TEMPLATE_IDS,
    },
  });
}

function summarizeSigninStats(stats) {
  const hasSigned = !!stats?.hasSignedInToday;
  const days = Number(stats?.consecutiveDays || 0);
  const arr = Array.isArray(stats?.hasSignedInDates) ? stats.hasSignedInDates : [];
  const lastDate = arr.length ? arr[arr.length - 1] : '-';
  return `today=${hasSigned ? 'Y' : 'N'} consecutiveDays=${days} lastDate=${lastDate}`;
}

async function ensureConsumerSignin(consumerToken, accountId, clientId) {
  const before = await consumerSigninStats(consumerToken, accountId, clientId);
  console.log(`会员签到状态(前): ${summarizeSigninStats(before)}`);

  if (before?.hasSignedInToday) {
    console.log('会员签到: 今日已签到');
    return { signed: false, already: true, before, after: before };
  }

  const ret = await consumerDoSignin(consumerToken, accountId, clientId);
  if (ret?.rewardGroup?.[0]) {
    const r = ret.rewardGroup[0];
    console.log(`会员签到返回: reward=${r?.name || '-'} score=${r?.score ?? '-'}`);
  } else {
    console.log(`会员签到返回: ${JSON.stringify(ret).slice(0, 200)}`);
  }

  const after = await consumerSigninStats(consumerToken, accountId, clientId);
  console.log(`会员签到状态(后): ${summarizeSigninStats(after)}`);
  if (!after?.hasSignedInToday) {
    throw new Error('签到后状态未更新，疑似未成功');
  }
  return { signed: true, already: false, before, after, raw: ret };
}

async function consumerSigninShare(consumerToken, accountId, clientId) {
  const path = '/modules/campaigncenter/signin/share';
  const url = `${CONSUMER}${path}?${buildConsumerParams(clientId, [])}`;
  const headers = {
    'X-Requested-With': 'XMLHttpRequest',
    'X-Access-Token': consumerToken,
    'X-Account-Id': accountId,
    'content-type': 'application/x-www-form-urlencoded',
    accept: 'application/json, text/plain, */*',
    'user-agent': UA_CONSUMER,
    origin: 'https://servicewechat.com',
    referer: `https://servicewechat.com/${MEMBER_APPID}/22/page-frame.html`,
  };

  const resp = await fetchFn(url, {
    method: 'POST',
    headers,
  });

  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }

  if (resp.ok) return { ok: true, already: false, data, status: resp.status };

  const msg = String(data?.message || data?.msg || data?.error || '');
  if (resp.status === 400 && Number(data?.code) === 0 && /操作过于频繁|过于频繁|too\s*frequent/i.test(msg)) {
    return { ok: false, already: false, tooFrequent: true, data, status: resp.status };
  }
  if ((resp.status === 400 || resp.status === 409) && /已分享|重复|请勿重复|上限|already|limit/i.test(msg)) {
    return { ok: true, already: true, data, status: resp.status };
  }

  throw new Error(`POST ${path} -> ${resp.status} ${text.slice(0, 400)}`);
}

function summarizeRewardGroup(group) {
  const arr = Array.isArray(group) ? group : [];
  let score = 0;
  let growth = 0;
  for (const x of arr) {
    if (x?.type === 'score') score += Number(x?.scoreValue ?? x?.score ?? 0) || 0;
    if (x?.type === 'growth') growth += Number(x?.growthValue ?? x?.growth ?? 0) || 0;
  }
  const out = [];
  if (score) out.push(`score+${score}`);
  if (growth) out.push(`growth+${growth}`);
  return { score, growth, text: out.join(' ') };
}

async function runCampaignShare(consumerToken, accountId) {
  const clientId = uuidv4();
  let okCount = 0;
  let scoreGain = 0;
  let growthGain = 0;
  let alreadyCount = 0;
  let throttleCount = 0;
  let failCount = 0;
  let lastDaily = NaN;
  let lastTotal = NaN;
  console.log(`分享任务开始: 计划${SHARE_TIMES}次，间隔${SHARE_DELAY_MS}ms，频控重试${SHARE_RETRY}次`);

  for (let i = 0; i < SHARE_TIMES; i++) {
    try {
      let ret = null;
      for (let r = 0; r < SHARE_RETRY; r++) {
        ret = await consumerSigninShare(consumerToken, accountId, clientId);
        if (!ret?.tooFrequent) break;
        throttleCount += 1;
        if (r < SHARE_RETRY - 1) await sleep(Math.max(100, SHARE_DELAY_MS));
      }

      if (!ret) {
        failCount += 1;
        console.log(`分享第${i + 1}/${SHARE_TIMES}次: 失败(空响应)`);
      } else {
        const data = ret.data || {};
        const msg = String(data?.message || data?.msg || '');
        const already = ret.already || /已分享|重复|请勿重复|上限|already|limit/i.test(msg);

        const daily = Number(data?.dailySharedRewardCount);
        const total = Number(data?.totalSharedRewardCount);
        if (Number.isFinite(daily)) lastDaily = daily;
        if (Number.isFinite(total)) lastTotal = total;

        if (ret.tooFrequent) {
          console.log(`分享第${i + 1}/${SHARE_TIMES}次: 频控`);
        } else if (already) {
          alreadyCount += 1;
          console.log(`分享第${i + 1}/${SHARE_TIMES}次: 已达上限/重复`);
        } else {
          okCount += 1;
          const rg = summarizeRewardGroup(data?.rewardGroup || []);
          scoreGain += rg.score;
          growthGain += rg.growth;
          console.log(`分享第${i + 1}/${SHARE_TIMES}次: 成功${rg.text ? ` (${rg.text})` : ''}`);
        }
      }
    } catch (e) {
      failCount += 1;
      console.log(`分享第${i + 1}/${SHARE_TIMES}次: 异常 ${e.message || e}`);
    }

    if (i < SHARE_TIMES - 1) await sleep(Math.max(80, SHARE_DELAY_MS));
  }

  const rewardText = [scoreGain ? `score+${scoreGain}` : '', growthGain ? `growth+${growthGain}` : '']
    .filter(Boolean)
    .join(' ');
  const countText = [Number.isFinite(lastDaily) ? `daily=${lastDaily}` : '', Number.isFinite(lastTotal) ? `total=${lastTotal}` : '']
    .filter(Boolean)
    .join(', ');

  return `分享: 尝试${SHARE_TIMES}次，成功${okCount}次，重复/上限${alreadyCount}次，异常${failCount}次，频控重试${throttleCount}次${
    rewardText ? `，${rewardText}` : ''
  }${countText ? ` (${countText})` : ''}`;
}

function pickChannels(member) {
  const socials = Array.isArray(member?.socials) ? member.socials : [];
  const byName = (name) => socials.find(x => (x?.channelName || '').includes(name))?.channel || '';
  const memberCh = byName('会员');
  const wwnCh = byName('问问农');
  const originCh = member?.originFrom?.channel || '';
  return {
    mainChannelId: originCh || wwnCh || memberCh,
    memberChannelId: memberCh || wwnCh || originCh,
  };
}

function eventPayload(eventId, task, memberId) {
  const base1089 = { scene: 1089, utmSource: 'mp_1089' };

  if (eventId === 'maievent-campaigncenter-signin') {
    return {
      name: 'maievent-page-operate',
      properties: {
        url: TASK_CENTER_URL,
        scene: 1037,
        pageContent: '任务中心-页面',
        utmSource: 'mp_1037',
        action: '点击',
        content: '每日签到',
        extra: { taskId: task.id, memberId },
      },
      useMemberChannel: true,
    };
  }

  switch (eventId) {
    case 'c_click_nutrition_plan_card':
      return { name: eventId, properties: { ...base1089, url: 'pages/nutrition/nutrition' }, useMemberChannel: false };
    case 'c_click_fertilizer_item':
      return { name: eventId, properties: { ...base1089, url: 'pages/presentation/list/list', id: 22205 }, useMemberChannel: false };
    case 'c_click_exper_demo_card':
      return { name: eventId, properties: { ...base1089, url: 'pages/farm/farm_story/farm_story' }, useMemberChannel: false };
    case 'c_click_nutrient_story_cards':
      return { name: eventId, properties: { ...base1089, url: 'pages/nutri_story/nutri_story' }, useMemberChannel: false };
    case 'c_view_post_page_detail':
      return { name: eventId, properties: { ...base1089, url: 'pages/common_post_detail/common_post_detail?topicId=694bb28963579047bcdb7d18&source=mai' }, useMemberChannel: false };
    case 'c_click_share_button':
      return { name: eventId, properties: { ...base1089, url: 'pages/nutrition/nutrition' }, useMemberChannel: false };
    case 'c_click_share_pdd_button':
      return { name: eventId, properties: { ...base1089, url: 'pages/pdd/report/report' }, useMemberChannel: false };
    default:
      return null;
  }
}

function leftTimes(task) {
  const mr = task?.memberReward || {};
  if (mr.noLimit) return 1;
  const raw = Number(mr.rewardCount);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return Math.min(raw, MAX_PER_TASK);
}

async function autoTasks(consumerToken, accountId, clientId) {
  const member = await consumerReq({
    method: 'GET',
    path: '/v2/member',
    token: consumerToken,
    accountId,
    clientId,
  });

  const memberId = member?.id;
  if (!memberId) throw new Error(`获取member失败: ${JSON.stringify(member).slice(0, 300)}`);

  const beforeScore = Number(member?.annualAccumulatedScore || 0);
  const beforeGrowth = Number(member?.growth || 0);

  const channels = pickChannels(member);
  const mainChannelId = channels.mainChannelId;
  const memberChannelId = channels.memberChannelId;

  if (!mainChannelId && !memberChannelId) {
    throw new Error('无法识别 channelId');
  }

  const tasks = await consumerReq({
    method: 'GET',
    path: '/v2/memberTasks',
    token: consumerToken,
    accountId,
    clientId,
    query: [
      ['listCondition.page', 1],
      ['listCondition.perPage', 1000],
      ['listCondition.orderBy[]', 'createdAt'],
      ['types[]', ['task', 'scoreCampaignInformation', 'invitation']],
    ],
  });

  const items = Array.isArray(tasks?.items) ? tasks.items : [];
  const candidates = items.filter(t => {
    if (!t?.isEnabled) return false;
    const ev = t?.eventTrigger?.[0]?.eventId;
    return ev && EVENT_WHITELIST.includes(ev);
  });

  if (!candidates.length) {
    console.log('没有命中可自动事件任务');
    return;
  }

  console.log(`命中任务 ${candidates.length} 个`);

  let sent = 0;
  for (const t of candidates) {
    const ev = t?.eventTrigger?.[0]?.eventId;
    const times = leftTimes(t);
    if (times <= 0) {
      console.log(`- ${t.name} (${ev}) 今日疑似已完成`);
      continue;
    }

    const mapped = eventPayload(ev, t, memberId);
    if (!mapped) {
      console.log(`- ${t.name} (${ev}) 暂无模板`);
      continue;
    }

    const channelId = mapped.useMemberChannel
      ? (memberChannelId || mainChannelId)
      : (mainChannelId || memberChannelId);

    for (let i = 0; i < times; i++) {
      const body = {
        clientId,
        logs: [{
          name: mapped.name,
          properties: JSON.stringify(mapped.properties),
          id: uuidv4(),
          occurredAt: nowISO(),
        }],
        channelId,
      };

      const ret = await consumerReq({
        method: 'POST',
        path: '/v2/memberEventLogs',
        token: consumerToken,
        accountId,
        clientId,
        body,
      });

      const failed = Array.isArray(ret?.failedLogs) ? ret.failedLogs.length : 0;
      console.log(`  -> ${t.name} [${ev}] 第${i + 1}/${times}次 ${failed ? '失败' : '已上报'}`);
      sent++;
      await new Promise(r => setTimeout(r, 700));
    }
  }

  const after = await consumerReq({
    method: 'GET',
    path: '/v2/member',
    token: consumerToken,
    accountId,
    clientId,
  });

  const afterScore = Number(after?.annualAccumulatedScore || 0);
  const afterGrowth = Number(after?.growth || 0);

  console.log(`事件上报总数: ${sent}`);
  console.log(`积分: ${beforeScore} -> ${afterScore} (Δ${afterScore - beforeScore})`);
  console.log(`成长值: ${beforeGrowth} -> ${afterGrowth} (Δ${afterGrowth - beforeGrowth})`);
}

function parseManualTokenParts(parts) {
  // 兼容：
  // token
  // token#yaraUserId
  // bffToken#yaraUserId#consumerToken#accountId
  const token1 = stripBearer(parts[0] || '');
  const token2 = stripBearer(parts[2] || '');

  const p1 = decodeJwtPayload(token1) || {};

  let bffToken = '';
  let yaraUserId = '';
  let consumerToken = '';
  let accountId = parts[3] || ACCOUNT_ID_DEFAULT;
  let note = '';

  if (parts.length >= 3) {
    bffToken = token1;
    if (isUuidLike(parts[1])) yaraUserId = parts[1];
    else note = parts[1] || '';

    if (looksLikeToken(parts[2])) {
      consumerToken = token2;
      const p2 = decodeJwtPayload(consumerToken) || {};
      accountId = accountId || p2.aid || ACCOUNT_ID_DEFAULT;
    } else {
      note = note ? `${note}|${parts[2]}` : (parts[2] || '');
    }
    return { bffToken, yaraUserId, consumerToken, accountId, note };
  }

  if (parts.length === 2) {
    const p2 = decodeJwtPayload(stripBearer(parts[1])) || {};
    // token#yaraUserId（标准）
    if (isUuidLike(parts[1])) {
      bffToken = token1;
      yaraUserId = parts[1];
      return { bffToken, yaraUserId, consumerToken, accountId, note };
    }
    // token#consumerToken（可选兼容）
    if (looksLikeToken(parts[1]) && p2?.aid) {
      bffToken = token1;
      consumerToken = stripBearer(parts[1]);
      accountId = p2.aid || accountId;
      return { bffToken, yaraUserId, consumerToken, accountId, note };
    }
    // token#备注
    bffToken = token1;
    note = parts[1] || '';
    return { bffToken, yaraUserId, consumerToken, accountId, note };
  }

  // 单token自动识别
  if (p1?.aid && String(p1?.sub || '').startsWith('member:')) {
    consumerToken = token1;
    accountId = p1.aid || accountId;
  } else {
    bffToken = token1;
  }

  return { bffToken, yaraUserId, consumerToken, accountId, note };
}

async function runOne(line, idx) {
  const parts = line.split('#').map(s => s.trim()).filter(s => s !== '');
  const head = parts[0] || '';

  console.log(`\n===== 账号${idx} =====`);

  let bffToken = '';
  let yaraUserId = '';
  let discourseUsername = '';
  let consumerToken = '';
  let accountId = ACCOUNT_ID_DEFAULT;
  let note = '';
  const needConsumerToken = ENABLE_TASKS || ENABLE_SIGNIN || ENABLE_SHARE;

  // 自动识别 wxid 模式（兼容非 wxid_ 开头）
  const hasWechatServer = !!String(process.env.WECHAT_SERVER || process.env.YYB_SERVER || '').trim();
  const explicitWx = head.startsWith('wxid_') || head.startsWith('wx:');
  const useWxMode = explicitWx || (hasWechatServer && isLikelyWxIdentifier(head) && !looksLikeToken(head));

  if (useWxMode) {
    const wxid = head.startsWith('wx:') ? head.slice(3) : head;
    if (parts.length > 1) {
      console.log(`备注: ${parts.slice(1).join('#')}`);
    }

    const codeMain = await getWxCode(wxid, MAIN_APPID);
    console.log(`wxid=${wxid} 主程序code获取成功`);

    const loginInfo = await preLoginByCode(codeMain);
    bffToken = loginInfo?.token || '';
    yaraUserId = loginInfo?.yaraUserId || '';
    discourseUsername = loginInfo?.discourseUsername || '';

    console.log('loginInfoAtom=', JSON.stringify({
      token: bffToken,
      yaraUserId,
      discourseUsername,
    }));

    if (bffToken) printTokenInfo('BFF token', bffToken);

    if (bffToken && yaraUserId) {
      const sign = await bffSigninStatus(bffToken, yaraUserId);
      console.log('/v2/profile/{id}/signin =>', sign);
    }

    if (needConsumerToken) {
      const codeMember = await getWxCode(wxid, MEMBER_APPID);
      const oauthData = await oauthWeapp(accountId, MEMBER_APPID, codeMember);
      consumerToken = oauthData.accessToken;
      const p = decodeJwtPayload(consumerToken) || {};
      accountId = p.aid || accountId;
      printTokenInfo('Consumer token', consumerToken);
    }
  } else {
    const parsed = parseManualTokenParts(parts);
    bffToken = parsed.bffToken;
    yaraUserId = parsed.yaraUserId;
    consumerToken = parsed.consumerToken;
    accountId = parsed.accountId;
    note = parsed.note || '';

    if (bffToken) printTokenInfo('BFF token', bffToken);
    if (bffToken && yaraUserId) {
      const sign = await bffSigninStatus(bffToken, yaraUserId);
      console.log('/v2/profile/{id}/signin =>', sign);
    } else if (bffToken && !yaraUserId) {
      console.log('未提供有效 yaraUserId（看起来是备注），跳过BFF签到状态查询');
    }
    if (consumerToken) printTokenInfo('Consumer token', consumerToken);
    if (note) console.log(`备注: ${note}`);
  }

  if (ENABLE_SIGNIN) {
    if (!consumerToken) {
      console.log('未拿到 consumer token，跳过会员签到');
    } else {
      const signClientId = uuidv4();
      try {
        await ensureConsumerSignin(consumerToken, accountId, signClientId);
      } catch (e) {
        console.log(`会员签到失败: ${e.message || e}`);
      }
    }
  }

  if (ENABLE_SHARE) {
    if (!consumerToken) {
      console.log('未拿到 consumer token，跳过分享任务');
    } else {
      try {
        const shareMsg = await runCampaignShare(consumerToken, accountId);
        console.log(shareMsg);
      } catch (e) {
        console.log(`分享任务失败: ${e.message || e}`);
      }
    }
  }

  if (!ENABLE_TASKS) return;

  if (!consumerToken) {
    console.log('未拿到 consumer token，跳过任务');
    return;
  }

  const clientId = uuidv4();
  await autoTasks(consumerToken, accountId, clientId);
}

(async () => {
  try {
    const raw = process.env.WX_ID || process.env[ENV_NAME] || '';
    if (!raw.trim()) {
      console.log(`未设置环境变量 WX_ID 或 ${ENV_NAME}`);
      process.exit(0);
    }

    const accounts = splitAccounts(raw);
    console.log(`共 ${accounts.length} 个账号`);

    for (let i = 0; i < accounts.length; i++) {
      try {
        await runOne(accounts[i], i + 1);
      } catch (e) {
        console.log(`账号${i + 1}失败: ${e.message || e}`);
      }
    }
    await sendNotify('问问农', `全部账号任务执行完成，共 ${accounts.length} 个账号`);
  } catch (e) {
    console.log('脚本异常:', e.message || e);
    await sendNotify('问问农异常', e.stack || e.message || String(e));
  }
})();
