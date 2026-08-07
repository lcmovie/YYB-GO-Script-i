#!/usr/bin/env node
// name:期云积签兑
// cron: 47 11,16 * * *
'use strict';

/**
 * 期云积签兑 / qyqd 青龙自动化脚本
 *
 * 变量：
 *   WX_ID=微信wxid[#备注]  (或 qyqd)
 *   多账号可用换行、& 分割
 *
 * 微信协议中转服务器：
 *   WECHAT_SERVER=http://127.0.0.1:8011
 *
 * 可选控制变量：
 *   QYQD_DRY_RUN=1       只登录不执行
 *   QYQD_FAST=1          不等待广告
 *   QYQD_SKIP_SIGN=1     跳过签到
 *   QYQD_SKIP_LOCAL=1    跳过本地广告
 *   QYQD_SKIP_THIRD=1    跳过第三方广告
 *   QYQD_SKIP_LOTTERY=1  跳过抽奖
 */

const { getSingleCode } = require('./getCode.js');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const BASE_URL = 'https://api.jiqiandui.cn/api/v1';
const USER_AGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.74(0x18004a2d) NetType/WIFI Language/zh_CN';
const REFERER = 'https://servicewechat.com/wx958515f1809b73c0/4/page-frame.html';

/** 统一读取运行配置，便于青龙面板直接通过环境变量调参。 */
const CONFIG = {
  dryRun: isTruthy(process.env.QYQD_DRY_RUN),
  waitAds: !isTruthy(process.env.QYQD_FAST) && process.env.QYQD_WAIT !== '0',
  delayScale: toNumber(process.env.QYQD_AD_DELAY_SCALE, 1),
  skipSign: isTruthy(process.env.QYQD_SKIP_SIGN),
  skipLocal: isTruthy(process.env.QYQD_SKIP_LOCAL),
  skipThird: isTruthy(process.env.QYQD_SKIP_THIRD),
  skipLottery: isTruthy(process.env.QYQD_SKIP_LOTTERY),
  maxThird: toNumber(process.env.QYQD_MAX_THIRD, 0),
  maxLottery: toNumber(process.env.QYQD_MAX_LOTTERY, 0),
  reservePoints: toNumber(process.env.QYQD_RESERVE_POINTS, 0),
  lotteryDelay: toNumber(process.env.QYQD_LOTTERY_DELAY, 1),
  globalInviteCode: (process.env.QYQD_INVITE_CODE || '').trim(),
  sharedDeviceId: (process.env.QYQD_DEVICE_ID || '').trim(),
  wechatServer: buildWechatCodeUrl(process.env.WECHAT_SERVER || ''),
  miniAppId: (process.env.QYQD_MINI_APPID || 'wx958515f1809b73c0').trim(),
  notify: process.env.QYQD_NOTIFY !== '0' && !isTruthy(process.env.QYQD_NO_NOTIFY),
};

const NOTIFY_TITLE = '期云积签兑';
const notifyLines = [];

/** 判断青龙常见布尔环境变量。 */
function isTruthy(value) {
  return /^(1|true|yes|on)$/i.test(String(value || '').trim());
}

/** 安全转换数字，避免 NaN 影响任务次数或等待时间。 */
function toNumber(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** 睡眠工具；广告观看等待和账号间隔都会走这里。 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
}

/** 日志脱敏，避免手机号完整出现在青龙日志。 */
function maskPhone(phone) {
  const s = String(phone || '');
  if (s.length < 7) return '***';
  return `${s.slice(0, 3)}****${s.slice(-4)}`;
}

/** 生成小程序源码同风格的 X-Device-ID，服务端只需要稳定设备标识。 */
function makeDeviceId(seed) {
  const raw = `${seed || ''}_${Date.now()}_${Math.random()}`;
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
  }
  return `d_${Math.abs(hash).toString(36)}_${Date.now().toString(36)}`;
}

/** 兼容基址或完整 code 接口的微信协议地址。（已废弃：现使用 getCode.js 统一接口） */
function buildWechatCodeUrl(rawUrl) {
  return '';
}

/** 简单脱敏 wxid，避免日志里完整暴露。 */
function maskWxid(wxid) {
  const s = String(wxid || '');
  if (s.length <= 8) return '***';
  return `${s.slice(0, 4)}***${s.slice(-4)}`;
}

function accountDisplayName(account) {
  if (account.mode === 'wxid') {
    return `${maskWxid(account.wxid)}${account.remark ? `(${account.remark})` : ''}`;
  }
  return maskPhone(account.phone);
}

function nowText() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 调用青龙 sendNotify 推送。 */
function pushNotify(title, content) {
  if (!CONFIG.notify || !content.trim()) return;
  try {
    const notify = require('./sendNotify');
    notify.sendNotify(title, content);
  } catch (e) {
    console.log('通知发送失败:', e.message || e);
  }
}


/** 解析 wxid 环境变量：wxid[#备注]，支持多账号。 */
function parseWxidAccounts(raw) {
  return String(raw || '')
    .split(/[\n&@]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item, index) => {
      const parts = item.split('#');
      const wxid = (parts[0] || '').trim();
      const remark = (parts.slice(1).join('#') || '').trim();
      if (!wxid) throw new Error(`第 ${index + 1} 个 wxid 账号格式错误，应为 wxid[#备注]`);
      return { mode: 'wxid', wxid, remark };
    });
}

/** 解析 qyqd 环境变量：手机号#密码[#邀请码]，支持多账号。 */
function parsePasswordAccounts(raw) {
  return String(raw || '')
    .split(/[\n&@]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item, index) => {
      const parts = item.split('#');
      const phone = (parts[0] || '').trim();
      const password = (parts[1] || '').trim();
      const inviteCode = (parts[2] || CONFIG.globalInviteCode || '').trim();
      if (!phone || !password) {
        throw new Error(`第 ${index + 1} 个账号格式错误，应为 手机号#密码`);
      }
      return { mode: 'password', phone, password, inviteCode };
    });
}

/** 优先使用 WX_ID，保留 qyqd 密码模式兼容。 */
function parseAccounts() {
  const wxidRaw = process.env.WX_ID || process.env.qyqd || '';
  if (String(wxidRaw || '').trim()) {
    // 判断是 wxid 格式还是 手机号#密码 格式
    const firstItem = wxidRaw.split(/[\n&@]+/)[0] || '';
    if (firstItem.includes('#') && /^\d+$/.test(firstItem.split('#')[0])) {
      return parsePasswordAccounts(wxidRaw);
    }
    return parseWxidAccounts(wxidRaw);
  }
  return [];
}

/**
 * 通过 getCode.js 统一接口获取微信小程序 login code
 * 支持 YYB(应用宝) / Wechat(牛子) 双协议自动检测
 */
function getWxCode(wxid) {
  return getSingleCode(CONFIG.miniAppId, String(wxid).split('#')[0].trim());
}

/** 通用 JSON HTTP 请求，支持 http/https，用于中转服务器。 */
function requestJson(method, targetUrl, data) {
  const url = new URL(targetUrl);
  const body = data === undefined ? null : JSON.stringify(data || {});
  const headers = {
    Accept: 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
  };
  if (body) headers['Content-Length'] = Buffer.byteLength(body);

  return new Promise((resolve, reject) => {
    const transport = url.protocol === 'http:' ? http : https;
    const req = transport.request({
      method: method.toUpperCase(),
      hostname: url.hostname,
      path: `${url.pathname}${url.search}`,
      port: url.port || (url.protocol === 'http:' ? 80 : 443),
      headers,
      timeout: 30000,
    }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        try {
          resolve(text ? JSON.parse(text) : {});
        } catch (e) {
          reject(new Error(text || `HTTP ${res.statusCode}`));
        }
      });
    });
    req.on('timeout', () => req.destroy(new Error('request timeout')));
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

/**
 * API 客户端：封装小程序统一请求头、JWT token 和 JSON 请求/响应。
 * 使用 Node 内置 https，避免青龙环境缺少 axios/got 依赖。
 */
class QyqdClient {
  constructor(account, index) {
    this.account = account;
    this.index = index;
    this.token = '';
    this.deviceId = CONFIG.sharedDeviceId || makeDeviceId(account.wxid || account.phone || `account_${index}`);
  }

  /** 发送 HTTP 请求；所有业务方法都走这里，保证 header 和错误处理一致。 */
  request(method, path, data, needAuth = true) {
    const url = new URL(path.startsWith('http') ? path : `${BASE_URL}${path}`);
    const upperMethod = method.toUpperCase();
    let body = null;

    // GET 参数拼到 query；POST/PUT/DELETE 参数走 JSON body。
    if (upperMethod === 'GET' && data && typeof data === 'object') {
      for (const [key, value] of Object.entries(data)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
      }
    } else if (data !== undefined) {
      body = JSON.stringify(data || {});
    }

    const headers = {
      Accept: 'application/json, text/plain, */*',
      'Content-Type': 'application/json',
      'X-Client-Type': 'miniprogram',
      'X-Platform-Type': 'wechat',
      'X-Device-ID': this.deviceId,
      'User-Agent': USER_AGENT,
      Referer: REFERER,
    };
    if (body) headers['Content-Length'] = Buffer.byteLength(body);
    if (needAuth && this.token) headers.Authorization = `Bearer ${this.token}`;

    return new Promise((resolve, reject) => {
      const req = https.request({
        method: upperMethod,
        hostname: url.hostname,
        path: `${url.pathname}${url.search}`,
        port: url.port || 443,
        headers,
        timeout: 20000,
      }, (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          let json;
          try {
            json = text ? JSON.parse(text) : {};
          } catch (e) {
            json = { code: -1, message: text || `HTTP ${res.statusCode}` };
          }
          json.__statusCode = res.statusCode;
          resolve(json);
        });
      });
      req.on('timeout', () => req.destroy(new Error('request timeout')));
      req.on('error', reject);
      if (body) req.write(body);
      req.end();
    });
  }

  /** 登录，wxid 模式走微信 code，旧模式走手机号密码。 */
  async login() {
    if (this.account.mode === 'wxid') {
      const code = await getWxCode(this.account.wxid);
      const res = await this.request('POST', '/auth/wechat-login', { code }, false);
      if (res.code !== 0 || !res.data || !res.data.token) {
        throw new Error(res.message || '微信登录失败');
      }
      this.token = res.data.token;
      return res.data.user_info || {};
    }

    const payload = {
      phone: this.account.phone,
      password: this.account.password,
    };
    if (this.account.inviteCode) payload.invite_code = this.account.inviteCode;

    const res = await this.request('POST', '/auth/password-login', payload, false);
    if (res.code !== 0 || !res.data || !res.data.token) {
      throw new Error(res.message || '登录失败');
    }
    this.token = res.data.token;
    return res.data.user_info || {};
  }

  getUserInfo() { return this.request('GET', '/user/info'); }
  getSigninStatus() { return this.request('GET', '/signin/status'); }
  doSignin() { return this.request('POST', '/signin/do', {}); }
  getAdTasks() { return this.request('GET', '/ads/tasks?platform=miniprogram'); }
  getAdTaskStats() { return this.request('GET', '/ads/task-stats?platform=miniprogram'); }
  getAdTaskContent(taskId) { return this.request('POST', '/ads/content', { task_id: taskId }); }
  getAdConfig() { return this.request('GET', '/ads/config'); }
  completeAdTask(taskId) { return this.request('POST', '/ads/tasks/complete', { task_id: taskId }); }
  getAppConfig() { return this.request('GET', '/app/config'); }
  getLotteryConfig() { return this.request('GET', '/lottery/config'); }
  getLotteryStats() { return this.request('GET', '/lottery/stats'); }
  doLottery() { return this.request('POST', '/lottery/do', {}); }
}

/** 统一判断 API 成功，兼容 HTTP 200 但业务 code 非 0 的情况。 */
function ok(res) {
  return res && res.code === 0;
}

/** 计算任务今日剩余次数；daily_limit=0 时保守只尝试 1 次，避免无限循环。 */
function taskRemaining(task) {
  const dailyLimit = Number(task.daily_limit || 0);
  const completed = Number(task.today_completed || 0);
  if (task.is_daily_limit_reached || task.is_total_limit_reached || task.is_active === false) return 0;
  if (dailyLimit > 0) return Math.max(0, dailyLimit - completed);
  return completed > 0 ? 0 : 1;
}

/** 根据小程序 ad-play.js 的观看阈值，计算本地广告领取前应等待的秒数。 */
function calcWatchSeconds(task, material) {
  if (!CONFIG.waitAds) return 0;
  if (task.task_type === 'third_party_ad') return Math.ceil(2 * CONFIG.delayScale);

  const duration = Number((material && material.duration) || 10);
  const ratio = Number(task.min_watch_ratio || 0);
  const seconds = ratio > 0 ? Math.ceil(duration * ratio / 100) + 1 : duration;
  return Math.max(1, Math.ceil(seconds * CONFIG.delayScale));
}

/** 执行签到；已签到则不重复提交，避免无意义失败。 */
async function runSignin(client) {
  if (CONFIG.skipSign) {
    console.log('  - 签到：已按 QYQD_SKIP_SIGN 跳过');
    return false;
  }

  const status = await client.getSigninStatus();
  if (!ok(status)) {
    console.log(`  - 签到状态获取失败：${status.message || status.__statusCode}`);
    return false;
  }
  if (status.data && status.data.today_signed) {
    console.log(`  - 签到：今日已签到，连续 ${status.data.continuous_days || 0} 天`);
    return true;
  }
  if (CONFIG.dryRun) {
    console.log('  - 签到：dry-run，将执行 POST /signin/do');
    return false;
  }

  const res = await client.doSignin();
  if (ok(res)) {
    const reward = res.data && res.data.points_reward;
    const days = res.data && res.data.continuous_days;
    console.log(`  - 签到成功：+${reward || 0} 积分，连续 ${days || 0} 天`);
    return true;
  }
  console.log(`  - 签到失败：${res.message || res.__statusCode}`);
  return false;
}

/** 签到后任务页还有一个“每日签到领积分”任务，需要单独调用任务完成接口领取。 */
async function claimSigninTaskReward(client, task) {
  if (!task || taskRemaining(task) <= 0) {
    console.log('  - 签到任务奖励：已领取或无可领取次数');
    return;
  }
  if (!task.is_signed_in) {
    console.log('  - 签到任务奖励：当前任务状态未标记已签到，跳过');
    return;
  }
  if (CONFIG.dryRun) {
    console.log(`  - 签到任务奖励：dry-run，将领取 task_id=${task.id}`);
    return;
  }

  const res = await client.completeAdTask(task.id);
  if (ok(res)) {
    console.log(`  - 签到任务奖励成功：+${(res.data && res.data.reward_points) || task.reward_points || 0} 积分`);
  } else {
    console.log(`  - 签到任务奖励失败：${res.message || res.__statusCode}`);
  }
}

/** 执行本地广告或第三方广告任务；两类任务最终都调用 /ads/tasks/complete。 */
async function runAdTask(client, task) {
  if (task.task_type === 'local_ad' && CONFIG.skipLocal) {
    console.log(`  - ${task.name}：已按 QYQD_SKIP_LOCAL 跳过`);
    return;
  }
  if (task.task_type === 'third_party_ad' && CONFIG.skipThird) {
    console.log(`  - ${task.name}：已按 QYQD_SKIP_THIRD 跳过`);
    return;
  }

  let remaining = taskRemaining(task);
  if (task.task_type === 'third_party_ad' && CONFIG.maxThird > 0) {
    remaining = Math.min(remaining, CONFIG.maxThird);
  }
  if (remaining <= 0) {
    console.log(`  - ${task.name}：今日已完成或达到上限`);
    return;
  }

  // 第三方广告源码会先读取广告配置；这里也读取一次以贴近小程序流程。
  if (task.task_type === 'third_party_ad') {
    const cfg = await client.getAdConfig();
    if (ok(cfg)) {
      const adId = cfg.data && cfg.data.third_party && cfg.data.third_party.rewarded_video_id;
      console.log(`  - 第三方广告配置：rewarded_video_id=${adId || '未返回'}`);
    } else {
      console.log(`  - 第三方广告配置获取失败：${cfg.message || cfg.__statusCode}，继续尝试领奖`);
    }
  }

  for (let i = 1; i <= remaining; i++) {
    console.log(`  - ${task.name}：准备第 ${i}/${remaining} 次，task_id=${task.id}`);
    if (CONFIG.dryRun) {
      console.log(`    dry-run：将调用 /ads/content -> 等待 -> /ads/tasks/complete`);
      continue;
    }

    const content = await client.getAdTaskContent(task.id);
    let material = null;
    if (ok(content)) {
      material = content.data && content.data.material;
      console.log(`    素材：${(material && material.name) || '无名称'}，duration=${(material && material.duration) || '默认'}`);
    } else {
      console.log(`    获取素材失败：${content.message || content.__statusCode}，仍尝试完成任务`);
    }

    const waitSeconds = calcWatchSeconds(task, material);
    if (waitSeconds > 0) {
      console.log(`    等待 ${waitSeconds}s 模拟观看阈值`);
      await sleep(waitSeconds * 1000);
    }

    const res = await client.completeAdTask(task.id);
    if (ok(res)) {
      const reward = (res.data && res.data.reward_points) || task.reward_points || 0;
      console.log(`    领取成功：+${reward} 积分，完成次数=${(res.data && res.data.complete_count) || i}`);
      task.today_completed = Number(task.today_completed || 0) + 1;
    } else {
      console.log(`    领取失败：${res.message || res.__statusCode}`);
      break;
    }

    // 如果服务端配置了同一任务间隔，重复领取前按比例等待，避免连续请求过快。
    if (i < remaining && task.interval_sec > 0 && CONFIG.waitAds) {
      const intervalMs = Math.ceil(Number(task.interval_sec) * CONFIG.delayScale) * 1000;
      console.log(`    任务间隔等待 ${Math.ceil(intervalMs / 1000)}s`);
      await sleep(intervalMs);
    }
  }
}

/** 根据当前积分自动抽奖；接口来源于 lottery.js，成本由 /lottery/config 返回。 */
async function runLottery(client) {
  if (CONFIG.skipLottery) {
    console.log('  - 抽奖：已按 QYQD_SKIP_LOTTERY 跳过');
    return;
  }

  const cfg = await client.getLotteryConfig();
  if (!ok(cfg) || !cfg.data) {
    console.log(`  - 抽奖配置获取失败：${(cfg && (cfg.message || cfg.__statusCode)) || 'unknown'}`);
    return;
  }

  // 抽奖成本以后端实时配置为准；HAR 样本里是每次 10 积分。
  const cost = Math.max(1, Number(cfg.data.cost_points || 10));
  let userPoints = Number(cfg.data.user_points || 0);

  // 任务刚完成后重新拉用户信息，确保按最新积分计算抽奖次数。
  const info = await client.getUserInfo();
  if (ok(info) && info.data && Number.isFinite(Number(info.data.points))) {
    userPoints = Number(info.data.points);
  }

  let maxDailyRemain = Infinity;
  const appCfg = await client.getAppConfig();
  const stats = await client.getLotteryStats();
  if (ok(appCfg) && appCfg.data && ok(stats) && stats.data) {
    const maxDaily = Number(appCfg.data.max_lottery_per_day || 0);
    const todayLottery = Number(stats.data.today_lottery || 0);
    if (maxDaily > 0) maxDailyRemain = Math.max(0, maxDaily - todayLottery);
  }

  let drawTimes = Math.floor(Math.max(0, userPoints - CONFIG.reservePoints) / cost);
  drawTimes = Math.min(drawTimes, maxDailyRemain);
  if (CONFIG.maxLottery > 0) drawTimes = Math.min(drawTimes, CONFIG.maxLottery);

  if (drawTimes <= 0) {
    console.log(`  - 抽奖：积分 ${userPoints}，单次 ${cost}，保留 ${CONFIG.reservePoints}，暂无可抽次数`);
    return;
  }
  if (CONFIG.dryRun) {
    console.log(`  - 抽奖：dry-run，积分 ${userPoints}，单次 ${cost}，预计可抽 ${drawTimes} 次`);
    return;
  }

  for (let i = 1; i <= drawTimes; i++) {
    const res = await client.doLottery();
    if (!ok(res) || !res.data) {
      console.log(`  - 抽奖第 ${i}/${drawTimes} 次失败：${(res && (res.message || res.__statusCode)) || 'unknown'}`);
      break;
    }

    // 后端字段 reward_points 实际表现为“抽到的云豆数量”，user_points/user_yundou 是抽后余额。
    const data = res.data;
    const reward = Number(data.reward_points || 0);
    const display = data.display_text || data.marquee_text || data.prize_name || `${reward}云豆`;
    userPoints = Number.isFinite(Number(data.user_points)) ? Number(data.user_points) : Math.max(0, userPoints - cost);
    console.log(`  - 抽奖第 ${i}/${drawTimes} 次成功：${data.level_name || ''} ${display}，剩余积分=${userPoints}，云豆=${data.user_yundou ?? '未知'}`);

    // 连抽之间保留轻微间隔，避免请求过于密集。
    if (i < drawTimes && CONFIG.lotteryDelay > 0) {
      await sleep(CONFIG.lotteryDelay * 1000);
    }
  }
}

/** 单账号完整流程：登录 -> 签到 -> 领取签到任务奖励 -> 广告任务 -> 积分抽奖 -> 汇总。 */
async function runAccount(account, index, total) {
  const client = new QyqdClient(account, index);
  const accountName = accountDisplayName(account);
  const summary = {
    name: accountName,
    success: false,
    userId: 'unknown',
    beforePoints: 0,
    afterPoints: 0,
    beforeYundou: 0,
    afterYundou: 0,
    error: '',
  };
  console.log(`\n========== 账号 ${index + 1}/${total}：${accountName} ==========`);

  const user = await client.login();
  summary.success = true;
  summary.userId = user.id || 'unknown';
  summary.beforePoints = Number(user.points || 0);
  summary.beforeYundou = Number(user.yundou || 0);
  console.log(`  - 登录成功：uid=${user.id || 'unknown'}，当前积分=${user.points || 0}，云豆=${user.yundou || 0}`);

  await runSignin(client);

  const tasksRes = await client.getAdTasks();
  if (!ok(tasksRes) || !tasksRes.data || !Array.isArray(tasksRes.data.list)) {
    const message = tasksRes.message || tasksRes.__statusCode || 'unknown';
    summary.error = `获取任务列表失败：${message}`;
    console.log(`  - ${summary.error}`);
    return summary;
  }

  const tasks = tasksRes.data.list;
  const signinTask = tasks.find((t) => t.task_type === 'signin');
  await claimSigninTaskReward(client, signinTask);

  const localTasks = tasks.filter((t) => t.task_type === 'local_ad');
  for (const task of localTasks) await runAdTask(client, task);

  const thirdTasks = tasks.filter((t) => t.task_type === 'third_party_ad');
  for (const task of thirdTasks) await runAdTask(client, task);

  const stats = await client.getAdTaskStats();
  if (ok(stats) && stats.data) {
    console.log(`  - 今日任务汇总：${stats.data.total_completed || 0}/${stats.data.total_max_daily || 0}，任务积分=${stats.data.total_points || 0}`);
  }

  await runLottery(client);

  const info = await client.getUserInfo();
  if (ok(info) && info.data) {
    summary.afterPoints = Number(info.data.points || 0);
    summary.afterYundou = Number(info.data.yundou || 0);
    console.log(`  - 账号余额：积分=${info.data.points || 0}，云豆=${info.data.yundou || 0}，金豆=${info.data.gold_dou || 0}`);
  }
  return summary;
}

/** 主入口：解析账号并串行执行，串行能降低服务端频控风险且日志更清晰。 */
async function main() {
  console.log('期云积签兑 qyqd 自动化开始');
  if (CONFIG.dryRun) console.log('当前为 dry-run：不会提交签到或领奖接口');
  const accounts = parseAccounts();
  if (accounts.length === 0) throw new Error('未找到环境变量 WX_ID 或 qyqd');

  for (let i = 0; i < accounts.length; i++) {
    try {
      const summary = await runAccount(accounts[i], i, accounts.length);
      if (summary) {
        notifyLines.push(`【账号${i + 1}】${summary.name}`);
        notifyLines.push(`结果：成功，uid=${summary.userId}`);
        notifyLines.push(`积分：${summary.beforePoints} -> ${summary.afterPoints}`);
        notifyLines.push(`云豆：${summary.beforeYundou} -> ${summary.afterYundou}`);
        notifyLines.push('');
      }
    } catch (err) {
      const accountName = accountDisplayName(accounts[i]);
      const message = err.message || String(err);
      console.log(`  - 账号 ${i + 1} 异常：${message}`);
      notifyLines.push(`【账号${i + 1}】${accountName}`);
      notifyLines.push(`结果：失败`);
      notifyLines.push(`说明：${message}`);
      notifyLines.push('');
    }
    if (i < accounts.length - 1) await sleep(1500);
  }

  const successCount = notifyLines.filter((line) => line.startsWith('结果：成功')).length;
  const failCount = notifyLines.filter((line) => line.startsWith('结果：失败')).length;
  const content = [`期云积签兑任务`, `成功：${successCount}  失败：${failCount}`, `时间：${nowText()}`, '', ...notifyLines].join('\n').trim();
  pushNotify(NOTIFY_TITLE, content);
  console.log('\n期云积签兑 qyqd 自动化结束');
}

main().catch((err) => {
  console.error(`脚本异常：${err.message || err}`);
  process.exitCode = 1;
});
