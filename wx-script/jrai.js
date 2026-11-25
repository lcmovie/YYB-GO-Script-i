// name: 即融AI
// cron: 39 7,21 * * *
/**
 * 即融AI（YYB Go Enhanced 适配）
 *
 * 小程序：即融AI（wx06e7f75695cf12b1）
 *
 * 功能覆盖福利中心赚融豆入口与自动兑换：
 *   1) 每日签到
 *   2) 浏览类任务
 *   3) 现金红包自动兑换
 *   4) 青龙通知
 *
 * 不自动处理：档案建立、简信宝、详信宝、流水宝、个配宝（需本人材料或实名资料）。
 *
 * 重要说明（实测）：
 *   - 兑换后轮询订单状态，成功也只是把红包发到 App 钱包，提现仍需本人前往 App 操作。
 *
 * 环境变量：
 *   YYB_SERVER            必填。地址@微信账号标识，多行换行，例：yyb-go:8000@1
 *   YYB_API_KEY           YYB 服务开启鉴权时填写，须与服务端令牌一致
 *   YYB_PROTOCOL_TOKEN    YYB_API_KEY 为空时读取，未启用鉴权可留空
 *   ZXB_TASKS             1=执行任务（默认 1）；0=只签到
 *   ZXB_REDEEM            1=自动兑换红包（默认 1）；0=只签到不兑换
 *   ZXB_REDEEM_MIN        兑换门槛，小于该面额不兑，默认 0
 *   ZXB_NOTIFY_ALWAYS     1=无兑换也推送余额变化，默认 0
 *   ZXB_QUIET             1=不打印用户明细
 *   ZXB_MAX_CODE_RETRY    取码失败重试次数，默认 2
 */
'use strict';

const https = require('https');
const http = require('http');
const zlib = require('zlib');
const { URL } = require('url');

const APP_ID = 'wx06e7f75695cf12b1';
const HOST = 'jirong.zhixuanbao.cn';
const BASE = 'https://' + HOST;
const TIMEOUT = 20000;

const APP_VERSION = process.env.ZXB_APP_VERSION || '1.3.1';
const DEVICE_ID = process.env.ZXB_DEVICE_ID || '66b22125614b4abc90513357651fd35fa';

const YYB_TOKEN = (process.env.YYB_API_KEY || '').trim() || (process.env.YYB_PROTOCOL_TOKEN || '').trim();

const RUN_TASKS = process.env.ZXB_TASKS !== '0';
const RUN_REDEEM = process.env.ZXB_REDEEM !== '0';
const REDEEM_MIN = Number(process.env.ZXB_REDEEM_MIN || 0);
const NOTIFY_ALWAYS = process.env.ZXB_NOTIFY_ALWAYS === '1';
const QUIET = process.env.ZXB_QUIET === '1';
const MAX_CODE_RETRY = Math.max(0, Number(process.env.ZXB_MAX_CODE_RETRY || 2));

const UA =
  'Mozilla/5.0 (Linux; Android 10; M2007J17C Build/QKQ1.200628.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0 Mobile Safari/537.36 MicroMessenger/8.0.50';

// ----------------------------- 工具 -----------------------------

function log(...args) {
  console.log('[即融AI]', ...args);
}
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
function maskMobile(v) {
  const s = String(v || '');
  return /^\d{11}$/.test(s) ? s.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') : s;
}
function short(v, n = 200) {
  return String(v == null ? '' : v).slice(0, n);
}

function request(url, { method = 'GET', headers = {}, body = null, raw = false } = {}) {
  return new Promise((resolve) => {
    let u;
    try {
      u = new URL(url);
    } catch (e) {
      return resolve({ status: 0, headers: {}, text: '', json: null, error: e.message });
    }
    const lib = u.protocol === 'https:' ? https : http;
    const data = body == null ? null : Buffer.isBuffer(body) ? body : Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
    const h = { ...headers };
    if (data) h['Content-Length'] = data.length;
    const req = lib.request(
      { hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80), path: u.pathname + u.search, method, headers: h },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          let buf = Buffer.concat(chunks);
          if (!raw) {
            try {
              const ce = res.headers['content-encoding'];
              if (ce === 'gzip') buf = zlib.gunzipSync(buf);
              else if (ce === 'deflate') buf = zlib.inflateSync(buf);
              else if (ce === 'br') buf = zlib.brotliDecompressSync(buf);
            } catch (_) {}
          }
          const text = raw ? '' : buf.toString('utf8');
          let json = null;
          if (!raw) {
            try {
              json = JSON.parse(text);
            } catch (_) {}
          }
          resolve({ status: res.statusCode, headers: res.headers, text, json, buf });
        });
      }
    );
    req.setTimeout(TIMEOUT, () => req.destroy(new Error('timeout')));
    req.on('error', (e) => resolve({ status: 0, headers: {}, text: '', json: null, error: e.message }));
    if (data) req.write(data);
    req.end();
  });
}

// ----------------------------- YYB -----------------------------

function parseEntry(raw) {
  const value = String(raw || '').trim();
  const at = value.indexOf('@');
  if (at === -1) return { server: '', ref: '' };
  const server = value.slice(0, at).trim().replace(/\/+$/, '');
  const ref = value.slice(at + 1).trim();
  return { server, ref };
}
function yybBase(entry) {
  const { server } = parseEntry(entry);
  if (!server) return '';
  return /^https?:\/\//i.test(server) ? server : 'http://' + server;
}
async function yybPost(entry, path, payload) {
  const base = yybBase(entry);
  if (!base) return null;
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (YYB_TOKEN) headers.Authorization = 'Bearer ' + YYB_TOKEN;
  return request(base + path, { method: 'POST', headers, body: payload });
}

const YYB_AUTH_ERROR = 'YYB 鉴权失败 (HTTP 401)，请检查 YYB_API_KEY 或 YYB_PROTOCOL_TOKEN 是否与服务端配置一致';

async function getLoginCode(entry) {
  const { ref } = parseEntry(entry);
  for (let i = 0; i <= MAX_CODE_RETRY; i++) {
    if (i > 0) await sleep(8000 * i);
    const r = await yybPost(entry, '/wxapp/getCode', { ref, app_id: APP_ID });
    if (!r) return { error: 'YYB_SERVER 格式错误' };
    if (r.status === 401) return { error: YYB_AUTH_ERROR };
    const j = r.json || {};
    const code = j.data && j.data.result && j.data.result.code;
    if (j.code === 0 && code) return { code, openid: j.openid };
    const msg = short(j.msg || r.text || r.error, 200);
    const limited = /-13000|-10\b|rejected|limit|Timeout|超时/i.test(msg);
    if (!limited || i === MAX_CODE_RETRY) return { error: '取码失败: ' + msg };
    log(`取码受限，${8 * (i + 1)} 秒后重试（${i + 1}/${MAX_CODE_RETRY}）`);
  }
  return { error: '取码失败' };
}
async function getPhoneCode(entry) {
  const { ref } = parseEntry(entry);
  const r = await yybPost(entry, '/wxapp/getPhoneNumber', { ref, app_id: APP_ID });
  if (!r) return { error: 'YYB_SERVER 格式错误' };
  if (r.status === 401) return { error: YYB_AUTH_ERROR };
  const j = r.json || {};
  const result = (j.data && j.data.result) || {};
  if (j.code === 0 && result.code) {
    let mobile = result.phoneNumber || result.purePhoneNumber || '';
    if (!mobile && result.data) {
      try {
        const inner = typeof result.data === 'string' ? JSON.parse(result.data) : result.data;
        mobile = inner.mobile || inner.phoneNumber || '';
      } catch (_) {}
    }
    return { code: result.code, mobile };
  }
  return { error: '取手机号授权码失败: ' + short(j.msg || r.text || r.error, 200) };
}

// ----------------------------- 业务 API -----------------------------

function bizHeaders(token, pagePath) {
  const h = {
    Host: HOST,
    Accept: 'application/json',
    'Accept-Encoding': 'gzip',
    'User-Agent': UA,
    Referer: 'https://servicewechat.com/' + APP_ID + '/23/page-frame.html',
    'X-App-Version': APP_VERSION,
    'X-Client-Type': 'WECHAT_MP',
    'X-Device-Id': DEVICE_ID,
    'content-type': 'application/json',
    env: 'prod',
    charset: 'utf-8',
    'X-Page-Path': pagePath || 'package-user/pages/welfare-center/welfare-center',
  };
  if (token) h.Authorization = 'Bearer ' + token;
  return h;
}
async function api(path, { method = 'GET', token, body = null, page } = {}) {
  return request(BASE + path, { method, headers: bizHeaders(token, page), body });
}

// ----------------------------- 任务引擎 -----------------------------

const BROWSE_CODES = new Set(['BROWSE_DETAIL_REPORT', 'BROWSE_BANK_FLOW', 'BROWSE_CREDIT_REPORT']);
/** 依赖其他账号注册才会结算的任务码（不参与处理） */
const REGISTER_TASK = 'INVITE_REGISTER';
const isBrowse = (t) => t.taskType === 'BROWSE' || BROWSE_CODES.has(t.taskCode);

async function listTasks(ctx) {
  const r = await api('/welfare/tasks', { token: ctx.token });
  const j = r.json || {};
  if (r.status !== 200 || j.code !== 200 || !Array.isArray(j.data)) return null;
  return j.data;
}
async function claimTask(ctx, task) {
  const r = await api('/welfare/tasks/' + encodeURIComponent(task.taskId) + '/claim', {
    method: 'POST',
    token: ctx.token,
    body: {},
  });
  const j = r.json || {};
  const d = j.data || {};
  if (r.status === 200 && j.code === 200) {
    if (d.duplicated) return { ok: true, duplicated: true };
    return { ok: true, points: d.points, balance: d.balanceAfter };
  }
  return { ok: false, error: short(j.message || r.text || r.error, 140) };
}
async function startAndComplete(ctx, task, work) {
  const start = await api('/welfare/tasks/start', { method: 'POST', token: ctx.token, body: { taskId: task.taskId } });
  if (!(start.json && start.json.code === 200)) {
    return { ok: false, error: 'start 失败: ' + short((start.json && start.json.message) || start.text, 120) };
  }
  const w = await work();
  if (w && w.ok === false) return w;
  const cmp = await api('/welfare/tasks/complete', { method: 'POST', token: ctx.token, body: { taskCode: task.taskCode } });
  const cj = cmp.json || {};
  const cd = cj.data || {};
  if (cmp.status !== 200 || cj.code !== 200) {
    return { ok: false, error: 'complete 失败: ' + short(cj.message || cmp.text, 140) };
  }
  if (cd.taskStatus !== 'COMPLETED') {
    return { ok: false, error: '服务端未判定完成（业务条件未满足）', status: cd.taskStatus };
  }
  return { ok: true };
}

async function runTasks(ctx) {
  const tasks = await listTasks(ctx);
  if (!tasks) return { error: '任务列表获取失败' };
  const summary = [];
  const done = { claimed: 0, points: 0, skipped: [], failed: [] };

  for (const t of tasks) {
    if (!t || !t.taskCode || t.taskCode === REGISTER_TASK) continue;
    if (t.status === 'CLAIMED') {
      summary.push(`${t.taskCode}=已领`);
      continue;
    }
    // 已可领取，直接领
    if (t.action === 'CLAIM') {
      const c = await claimTask(ctx, t);
      if (c.ok) {
        done.claimed += 1;
        done.points += Number(c.points) || 0;
        log(`[${ctx.who}] 领取「${t.taskName}」+${c.points || 0} 融豆`);
        summary.push(`${t.taskCode}=领取${c.points || 0}`);
      } else {
        done.failed.push(`${t.taskCode}: ${c.error}`);
        summary.push(`${t.taskCode}=领取失败`);
      }
      continue;
    }

    let r = null;
    try {
      if (isBrowse(t)) {
        r = await startAndComplete(ctx, t, async () => {
          const wait = Math.min(Math.max(Number(t.durationThresholdMs) || 15000, 5000), 60000);
          await sleep(wait + 2000);
          return { ok: true };
        });
      } else if (t.taskCode === 'FIRST_PROFILE') {
        // 档案信息涉及本人实名资料，脚本不自动填写
        done.skipped.push(`${t.taskCode}(需本人按实际情况填写)`);
        summary.push(`${t.taskCode}=跳过`);
        continue;
      } else {
        done.skipped.push(`${t.taskCode}(需本人操作)`);
        summary.push(`${t.taskCode}=跳过`);
        continue;
      }
    } catch (e) {
      r = { ok: false, error: e.message };
    }

    if (r && r.ok) {
      await sleep(1200);
      const latest = await listTasks(ctx);
      const after = (latest || []).find((x) => x.taskCode === t.taskCode);
      if (after && after.action === 'CLAIM') {
        const c = await claimTask(ctx, after);
        if (c.ok) {
          done.claimed += 1;
          done.points += Number(c.points) || 0;
          log(`[${ctx.who}] 任务「${t.taskName}」完成并领取 +${c.points || 0} 融豆`);
          summary.push(`${t.taskCode}=完成+${c.points || 0}`);
          continue;
        }
        done.failed.push(`${t.taskCode}: 领取失败 ${c.error}`);
        summary.push(`${t.taskCode}=待领取`);
        continue;
      }
      summary.push(`${t.taskCode}=完成待领取`);
    } else {
      done.failed.push(`${t.taskCode}: ${(r && r.error) || '未知错误'}`);
      summary.push(`${t.taskCode}=失败`);
      log(`[${ctx.who}] 任务「${t.taskName}」未完成：${(r && r.error) || ''}`);
    }
    await sleep(1000);
  }

  return { ok: true, summary, ...done };
}

// ----------------------------- 现金红包兑换 -----------------------------

/** 商品 action 为 EXCHANGE 表示豆够且有库存；GO_EARN=豆不足，SOLD_OUT=抢完 */
const REDEEMABLE_ACTION = 'EXCHANGE';

/**
 * 兑换当前可兑的最大面额红包，只执行一次。
 * 余额不足 / 名额抢完 / 无可兑商品 → 不兑换，返回 skipped。
 */
async function redeemMaxCash(ctx, balance) {
  const g = await api('/welfare/goods', { token: ctx.token });
  const list = (g.json && g.json.data) || [];
  if (!Array.isArray(list) || !list.length) return { ok: false, skipped: true, reason: '商品列表为空' };

  const candidates = list
    .filter((x) => x && String(x.goodsType || '').toUpperCase() === 'CASH')
    .filter((x) => String(x.action || '').toUpperCase() === REDEEMABLE_ACTION)
    .filter((x) => Number(x.exchangePoints) > 0 && Number(x.exchangePoints) <= Number(balance))
    .filter((x) => x.remainingStock == null || Number(x.remainingStock) > 0)
    .filter((x) => REDEEM_MIN <= 0 || Number(x.cashAmount || 0) >= REDEEM_MIN)
    .sort((a, b) => Number(b.cashAmount || 0) - Number(a.cashAmount || 0) || Number(b.exchangePoints) - Number(a.exchangePoints));

  if (!candidates.length) return { ok: false, skipped: true, reason: '融豆不足或无可用名额' };

  const target = candidates[0];
  const r = await api('/welfare/exchange', {
    method: 'POST',
    token: ctx.token,
    body: {
      goodsId: target.goodsId,
      requestId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      expectedExchangePoints: target.exchangePoints,
    },
  });
  const j = r.json || {};
  const d = j.data || {};
  if (r.status !== 200 || j.code !== 200) {
    return { ok: false, error: short(j.message || r.text || r.error, 140), goodsName: target.goodsName };
  }
  if (String(d.status || '').toUpperCase() === 'FAILED') {
    return { ok: false, error: d.failReason || '兑换失败', goodsName: target.goodsName };
  }

  // 订单可能异步入账，轮询 5 次（3s 一次）
  let order = null;
  const orderNo = d.orderNo || '';
  for (let i = 0; i < 5 && orderNo; i++) {
    await sleep(3000);
    const o = await api('/welfare/orders/' + encodeURIComponent(orderNo), { token: ctx.token });
    order = (o.json && o.json.data) || null;
    if (!order || String(order.status || '').toUpperCase() !== 'PROCESSING') break;
  }
  const status = String((order && order.status) || d.status || '').toUpperCase();
  const ok = status !== 'FAILED' && (Boolean(orderNo) || Boolean(status));
  return {
    ok,
    goodsName: (order && order.goodsName) || target.goodsName,
    cashAmount: Number((order && order.cashAmount) || target.cashAmount || 0),
    points: Number((order && order.exchangePoints) || target.exchangePoints || 0),
    orderNo,
    status: status || 'UNKNOWN',
    error: ok ? '' : (order && order.failReason) || d.failReason || '兑换响应缺少订单信息',
  };
}

// ----------------------------- 单账号 -----------------------------

async function runAccount(entry, index) {
  const { ref } = parseEntry(entry);
  const tag = `账号[${index}] ref=${ref}`;
  const ctx = { tag, token: '', who: tag, mobile: '' };
  const result = { ok: false, ref };

  const c = await getLoginCode(entry);
  if (!c.code) {
    log(`[${tag}] ${c.error}`);
    return { ...result, error: c.error };
  }
  const p = await getPhoneCode(entry);
  if (!p.code) {
    log(`[${tag}] ${p.error}`);
    return { ...result, error: p.error };
  }
  const login = await api('/auth/wxmini/login?code=' + encodeURIComponent(c.code) + '&phoneCode=' + encodeURIComponent(p.code), { method: 'POST' });
  const lj = login.json || {};
  if (login.status !== 200 || lj.code !== 200 || !lj.token) {
    const msg = short(lj.message || login.text || login.error, 200);
    log(`[${tag}] 登录失败: HTTP ${login.status} ${msg}`);
    return { ...result, error: '登录失败: ' + msg };
  }
  ctx.token = lj.token;
  const user = lj.user || {};
  if (user.needBindMobile) {
    log(`[${tag}] 该账号需先在小程序内绑定手机号，跳过`);
    return { ...result, error: '需在小程序内绑定手机号' };
  }
  ctx.mobile = p.mobile || user.username || '';
  if (!QUIET) ctx.who = `${user.nickName || '用户'}（${maskMobile(user.username || p.mobile) || user.id || ref}）`;
  log(`[${ctx.who}] 登录成功`);
  result.user = user.nickName || '';

  // 签到
  const home = await api('/welfare/home', { token: ctx.token });
  const hj = home.json || {};
  if (home.status === 200 && hj.code === 200) {
    const hd = hj.data || {};
    result.before = Number(hd.balance) || 0;
    if (hd.checkIn && hd.checkIn.checkedToday) {
      log(`[${ctx.who}] 今日已签到，余额 ${hd.balance} 融豆（≈${hd.approxValue} 元）`);
      result.signed = true;
      result.balance = hd.balance;
    } else {
      const ck = await api('/welfare/check-in', { method: 'POST', token: ctx.token, body: {} });
      const cd = (ck.json && ck.json.data) || {};
      if (ck.status === 200 && ck.json && ck.json.code === 200) {
        if (cd.duplicated) {
          log(`[${ctx.who}] 服务端判定今日已签到`);
        } else {
          log(`[${ctx.who}] 签到成功 +${cd.points} 融豆，余额 ${cd.balanceAfter}`);
          result.points = cd.points;
        }
        result.signed = true;
        result.balance = cd.balanceAfter;
      } else {
        log(`[${ctx.who}] 签到失败: ${short((ck.json && ck.json.message) || ck.text, 120)}`);
      }
    }
  }

  // 任务
  if (RUN_TASKS) {
    const t = await runTasks(ctx);
    result.tasks = t;
    if (t && t.summary) log(`[${ctx.who}] 任务状态: ${t.summary.join(', ')}`);
    if (t && t.skipped && t.skipped.length) log(`[${ctx.who}] 跳过: ${t.skipped.join('；')}`);
    if (t && t.failed && t.failed.length) log(`[${ctx.who}] 未完成: ${t.failed.join('；')}`);
    result.earned = (t && t.points) || 0;
    result.claimed = (t && t.claimed) || 0;
  }

  // 兑换：任务全部跑完后，按当前最大可兑面额兑换一次
  if (RUN_REDEEM) {
    const pre = await api('/welfare/home', { token: ctx.token });
    const curBalance =
      pre.json && pre.json.code === 200 && pre.json.data ? Number(pre.json.data.balance) || 0 : Number(result.balance) || 0;
    const rd = await redeemMaxCash(ctx, curBalance);
    result.redeem = rd;
    if (rd.ok) {
      log(`[${ctx.who}] 兑换成功：${rd.goodsName}（-${rd.points} 融豆），请在 App 钱包提现`);
    } else if (rd.skipped) {
      log(`[${ctx.who}] 本次不兑换：${rd.reason}`);
    } else {
      log(`[${ctx.who}] 兑换未成功：${rd.error}`);
    }
  }

  const finalHome = await api('/welfare/home', { token: ctx.token });
  if (finalHome.json && finalHome.json.code === 200) result.balance = finalHome.json.data.balance;
  result.ok = true;
  return result;
}

// ----------------------------- 通知 -----------------------------

let notified = false;
async function notify(title, content) {
  try {
    const mod = require('./sendNotify');
    const fn = typeof mod === 'function' ? mod : mod && mod.sendNotify;
    if (typeof fn !== 'function') {
      log('未找到通知模块，跳过推送');
      return;
    }
    await fn(title, content);
    notified = true;
    log(`通知已提交：${title}`);
  } catch (e) {
    log(`通知发送失败：${e && e.message ? e.message : e}`);
  }
}

// ----------------------------- 入口 -----------------------------

(async () => {
  const servers = String(process.env.YYB_SERVER || '')
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (!servers.length) {
    console.error('未配置环境变量 YYB_SERVER（格式：地址@微信账号标识，多行换行）');
    process.exit(1);
  }
  log(`共 ${servers.length} 个账号，任务模式 ${RUN_TASKS ? '开' : '关'}，自动兑换 ${RUN_REDEEM ? '开' : '关'}`);

  const results = [];
  for (let i = 0; i < servers.length; i++) {
    try {
      results.push(await runAccount(servers[i], i + 1));
    } catch (e) {
      log(`账号[${i + 1}] 执行异常: ${e.message}`);
      results.push({ ok: false, error: e.message });
    }
    if (i < servers.length - 1) await sleep(2500 + Math.floor(Math.random() * 2000));
  }

  const okCount = results.filter((x) => x.ok).length;
  const failCount = results.length - okCount;
  const lines = results.map((x) => {
    if (!x.ok) return `- ${x.ref || '-'}: 失败 ${x.error}`;
    const extra = x.claimed ? `，任务领取 ${x.claimed} 项 +${x.earned}` : '';
    return `- ${x.user || x.ref}: ${x.signed ? '已签到' : '签到异常'}${extra}，余额 ${x.balance}`;
  });
  log(`执行完成：成功 ${okCount}，失败 ${failCount}`);
  lines.forEach((l) => log(l));

  // ---------------- 通知：只在本次发生兑换时推送（可用 ZXB_NOTIFY_ALWAYS=1 强制） ----------------
  const redeemed = results.filter((x) => x.ok && x.redeem && x.redeem.ok);
  if (redeemed.length || NOTIFY_ALWAYS) {
    const body = [];
    for (const x of results) {
      if (!x.ok) continue;
      const from = x.before == null ? '-' : x.before;
      const to = x.balance == null ? '-' : x.balance;
      const delta = x.before == null || x.balance == null ? '' : (Number(x.balance) - Number(x.before) >= 0 ? '+' : '') + (Number(x.balance) - Number(x.before));
      let line = `${x.user || x.ref}：${from} → ${to} 融豆`;
      if (delta) line += `（${delta}）`;
      if (x.redeem && x.redeem.ok) line += `｜已兑换 ${x.redeem.goodsName || '现金红包'}`;
      body.push(line);
    }
    if (redeemed.length) {
      body.push('');
      body.push('红包已发放到即融AI钱包，请打开 App →「我的 → 钱包」手动提现。');
    }
    const title = redeemed.length ? '即融AI：红包兑换成功' : '即融AI：融豆变化';
    await notify(title, body.join('\n'));
  }

  if (failCount) {
    const fails = results.filter((x) => !x.ok).map((x) => `- ${x.ref || '-'}: ${x.error}`);
    await notify('即融AI执行异常', `${failCount} 个账号失败：\n${fails.join('\n')}`);
    process.exit(1);
  }
})();
