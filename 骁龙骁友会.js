/**
 * 骁龙骁友会 - 微信协议版（自动获取CK）
 * 变量: WX_ID (wxid#备注 多号@或换行)
 * 变量: WECHAT_SERVER (协议服务地址)
 * 可选: WX_APPID (默认 wx026c06df6adc5d06)
 * cron: 25 11,13 * * *
 */

const ckName = "WX_ID";
const WECHAT_SERVER = (process.env.WECHAT_SERVER || "").trim();
const WX_APPID = (process.env.WX_APPID || "wx026c06df6adc5d06").trim();

const axios = require("axios");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { getSingleCode } = require('./getCode.js');
const http = require("http");
const https = require("https");
const { EventEmitter } = require("events");
EventEmitter.defaultMaxListeners = 100;

const CACHE_NAME = "xlxyh";
const CACHE_FILE = path.join(__dirname, `${CACHE_NAME}.json`);
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a1b)XWEB/14185";

class Env {
  constructor(name) {
    this.name = name;
    this.logs = [];
    this.httpClient = axios.create({
      timeout: 30000,
      validateStatus: () => true,
      httpAgent: new http.Agent({ keepAlive: true, maxSockets: 30 }),
      httpsAgent: new https.Agent({ keepAlive: true, maxSockets: 30 }),
    });
  }
  log(...args) {
    const msg = args.join(" ");
    this.logs.push(msg);
    console.log(msg);
  }
  wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  async httpRequest(config) {
    const resp = await this.httpClient({
      method: config.method || "GET",
      url: config.url,
      headers: config.headers || {},
      data: config.data,
      timeout: config.timeout || 30000,
    });
    return { status: resp.status, data: resp.data, headers: resp.headers };
  }
}

const $ = new Env("骁龙骁友会");

function randomDelay(minSeconds, maxSeconds, message = "") {
  const ms = Math.floor(Math.random() * (maxSeconds - minSeconds + 1) + minSeconds) * 1000;
  if (message) $.log(`${message} ${Math.floor(ms / 1000)}秒`);
  return $.wait(ms);
}

function parseAccounts(raw) {
  const accounts = [];
  const lines = raw.split(/[&\n]/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split('#');
    const wxid = parts[0].trim();
    const remark = parts[1] || wxid;
    if (wxid) accounts.push({ wxid, remark });
  }
  return accounts;
}

function loadCache() {
  try {
    return JSON.parse(fs.readFileSync(CACHE_FILE, "utf8")) || {};
  } catch {
    return {};
  }
}

function saveCache(cache) {
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), "utf8");
}

function uuid32() {
  return "xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function signByHar(timestamp, requestId, bodyOrQuery = "") {
  return crypto.createHash("md5").update(`${bodyOrQuery || ""}${requestId}${timestamp}`).digest("hex");
}

function isAuthExpiredMsg(msg = "") {
  return /登录过期|请重新登录|invalid session|session失效|unauthorized|A00004/i.test(String(msg || ""));
}

function isAlreadySignedMsg(msg = "") {
  return /(\u5df2\u7b7e\u5230|\u4eca\u5929\u5df2\u7b7e\u5230|\u91cd\u590d\u7b7e\u5230|\u65e0\u9700\u91cd\u590d\u7b7e\u5230|already\s*signed|duplicate)/i.test(String(msg || ""));
}

function shortText(v, max = 220) {
  const s = String(v == null ? "" : v).replace(/\s+/g, " ").trim();
  if (!s) return "";
  return s.length > max ? `${s.slice(0, max)}...` : s;
}

function pickDailySignTask(taskList = []) {
  if (!Array.isArray(taskList)) return null;
  return (
    taskList.find((it) => String(it?.name || "").trim() === "\u6bcf\u65e5\u7b7e\u5230") ||
    taskList.find((it) => {
      const name = String(it?.name || "").trim();
      return /\u7b7e\u5230/.test(name) && !/\u6bcf\u6708\u8fde\u7eed\u7b7e\u523015\u5929/.test(name);
    }) ||
    null
  );
}

function isWafBlock(status, raw, msg = "") {
  const rawText = typeof raw === "string" ? raw : "";
  const compact = rawText.toLowerCase().replace(/\s+/g, "");
  const m = String(msg || "").toLowerCase();
  const hasHtml = compact.includes("<!doctypehtml") || compact.includes("<html");
  const hasWafWord = /(traceid|waf|aliyun|argus|forbidden|blocked|notallowed|security)/i.test(rawText);
  if (hasHtml && [403, 405, 412, 429, 503].includes(Number(status))) return true;
  if (hasHtml && hasWafWord) return true;
  if (/(waf|security|blocked|forbidden|intercept)/i.test(m)) return true;
  return false;
}


const getWxCode = (wxid) => getSingleCode(WX_APPID, String(wxid).split('#')[0].trim());

async function getSessionKeyByCode(code) {
  const timestamp = Date.now().toString();
  const requestId = uuid32();
  const body = `code=${code}`;

  const headers = {
    Host: "qualcomm.boysup.cn",
    Connection: "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    timestamp,
    sign: signByHar(timestamp, requestId, body),
    xweb_xhr: "1",
    openId: "",
    requestId,
    userId: "0",
    sessionKey: "",
    "User-Agent": UA,
    Referer: `https://servicewechat.com/${WX_APPID}/666/page-frame.html`,
    Accept: "*/*",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
  };

  const { status, data } = await $.httpRequest({
    method: "POST",
    url: "https://qualcomm.boysup.cn/qualcomm-app/api/user/getOpenId",
    headers,
    data: body,
    timeout: 15000,
  });

  if (status === 200 && data?.code === 200 && data?.data) {
    return {
      sessionKey: data.data.sessionKey,
      userId: String(data.data.userInfo?.id || ""),
      openId: data.data.openId || "",
      nick: data.data.userInfo?.nick || "",
      coreCoin: data.data.userInfo?.coreCoin || 0,
      level: data.data.userInfo?.level || 0,
      updateTime: new Date().toISOString(),
    };
  }
  throw new Error(`获取sessionKey失败: ${data?.message || JSON.stringify(data)}`);
}

async function validateCred(cred) {
  if (!cred?.sessionKey || !cred?.userId) return false;

  const timestamp = Date.now().toString();
  const requestId = uuid32();
  const query = `userId=${cred.userId}`;
  const headers = {
    Host: "qualcomm.boysup.cn",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    timestamp,
    sign: signByHar(timestamp, requestId, query),
    userId: cred.userId,
    sessionKey: cred.sessionKey,
    openId: cred.openId || "",
    requestId,
    xweb_xhr: "1",
    "User-Agent": UA,
    Referer: `https://servicewechat.com/${WX_APPID}/666/page-frame.html`,
  };

  try {
    const { status, data } = await $.httpRequest({
      method: "GET",
      url: `https://qualcomm.boysup.cn/qualcomm-app/api/user/info?${query}`,
      headers,
      timeout: 15000,
    });
    return status === 200 && data?.code === 200 && !isAuthExpiredMsg(data?.message);
  } catch {
    return false;
  }
}

async function canSignWithCred(account, cred) {
  try {
    const runner = new XLXYH(cred);
    if (!runner.valid) return { ok: false, msg: '\u0043\u004b\u65e0\u6548' };

    const userId = String(cred.userId || '');
    const checks = [
      { method: 'GET', path: `/qualcomm-app/api/user/signIn?userId=${userId}` },
      { method: 'GET', path: `/qualcomm-app/api/user/signIn?userId=${userId}`, skipSign: true },
      { method: 'POST', path: '/qualcomm-app/api/user/signIn', data: `userId=${userId}` },
      { method: 'POST', path: '/qualcomm-app/api/user/signIn', data: `userId=${userId}`, skipSign: true },
    ];

    const preheat = await runner.preheatDailySign();
    let lastMsg = preheat?.ok ? '' : (preheat?.msg || '\u7b7e\u5230\u524d\u7f6e\u5931\u8d25');
    for (const c of checks) {
      const ret = await runner.request(c.method, c.path, c.data || '', {}, { skipSign: !!c.skipSign });
      const msg = String(ret?.message || ret?.msg || ret?.code || '');
      if (ret?.code === 200 || isAlreadySignedMsg(msg)) {
        return { ok: true, msg: msg || `${c.method} ${c.path}` };
      }
      lastMsg = msg || shortText(JSON.stringify(ret || {}), 120);
    }

    const taskRet = await runner.request('GET', `/qualcomm-app/api/home/taskDaily?userId=${userId}`);
    if (taskRet.code === 200 && Array.isArray(taskRet.data)) {
      const signTask = pickDailySignTask(taskRet.data);
      if (Number(signTask?.status) === 1) {
        return { ok: true, msg: 'taskDaily\u72b6\u6001\u5df2\u7b7e' };
      }
    }

    return { ok: false, msg: lastMsg || 'signIn\u63a5\u53e3\u4e0d\u53ef\u7528' };
  } catch (e) {
    return { ok: false, msg: e?.message || String(e) };
  }
}

async function refreshCredOnce(account, opts = {}) {
  const maxTry = Math.max(1, Number(opts.maxTry || 3));
  const requireSignable = !!opts.requireSignable;

  let lastCred = null;
  let lastReason = '\u672a\u77e5\u9519\u8bef';

  for (let i = 1; i <= maxTry; i += 1) {
    $.log(`\u5237\u65b0CK: ${account.remark} (\u5c1d\u8bd5 ${i}/${maxTry})`);
    try {
      const code = await getWxCode(account.wxid);
      const cred = await getSessionKeyByCode(code);
      lastCred = cred;

      const alive = await validateCred(cred);
      if (!alive) {
        lastReason = 'user/info \u9a8c\u6d3b\u5931\u8d25';
        $.log(`\u5237\u65b0\u540e\u9a8c\u6d3b\u5931\u8d25: ${account.remark}`);
        if (i < maxTry) await $.wait(1200 + Math.floor(Math.random() * 1200));
        continue;
      }

      const signCheck = await canSignWithCred(account, cred);
      if (signCheck.ok) {
        $.log(`\u5237\u65b0\u6210\u529f: ${account.remark} (${cred.nick || cred.userId}) | \u7b7e\u5230\u9a8c\u6d3b\u901a\u8fc7`);
        return { cred, signable: true, reason: signCheck.msg || '' };
      }

      lastReason = `\u7b7e\u5230\u9a8c\u6d3b\u5931\u8d25: ${signCheck.msg || '\u672a\u77e5'}`;
      $.log(`\u5237\u65b0\u7ed3\u679c\u4e0d\u53ef\u7b7e\u5230: ${account.remark} ${shortText(lastReason, 120)}`);
    } catch (e) {
      lastReason = e?.message || String(e);
      $.log(`\u5237\u65b0\u5931\u8d25: ${account.remark} ${lastReason}`);
    }

    if (i < maxTry) await $.wait(1200 + Math.floor(Math.random() * 1200));
  }

  if (requireSignable) {
    throw new Error(`\u8fde\u7eed${maxTry}\u6b21\u5237\u65b0\u4ecd\u4e0d\u53ef\u7b7e\u5230: ${shortText(lastReason, 120)}`);
  }

  if (lastCred) {
    $.log(`\u26a0\ufe0f ${account.remark} \u5237\u65b0\u5b8c\u6210\u4f46\u4e0d\u53ef\u7b7e\u5230\uff0c\u5148\u7ee7\u7eed\u6267\u884c\uff08\u4e0d\u5199\u5165\u7f13\u5b58\uff09`);
    return { cred: lastCred, signable: false, reason: lastReason };
  }

  throw new Error(`\u5237\u65b0\u5931\u8d25: ${shortText(lastReason, 120)}`);
}

async function getValidCred(account, cache) {
  let cred = cache[account.wxid];

  if (cred?.sessionKey && cred?.userId) {
    $.log(`\u68c0\u67e5\u7f13\u5b58CK: ${account.remark}`);
    const ok = await validateCred(cred);
    if (ok) {
      $.log(`\u7f13\u5b58CK\u6709\u6548: ${account.remark}`);
      return { success: true, cred };
    }
    // ?????? 405/WAF ????????????????
    $.log(`\u7f13\u5b58CK\u6821\u9a8c\u672a\u901a\u8fc7\uff0c\u5148\u5e26\u7f13\u5b58\u5c1d\u8bd5\u6267\u884c: ${account.remark}`);
    return { success: true, cred };
  }

  try {
    const refreshed = await refreshCredOnce(account, { requireSignable: false, maxTry: 3 });
    cred = refreshed.cred;
    if (refreshed.signable) {
      cache[account.wxid] = cred;
      saveCache(cache);
    } else {
      $.log(`\u26a0\ufe0f ${account.remark} \u65b0CK\u4e0d\u53ef\u7b7e\u5230\uff0c\u5df2\u8df3\u8fc7\u7f13\u5b58\u5199\u5165`);
    }
    return { success: true, cred };
  } catch (e) {
    $.log(`\u5237\u65b0\u5931\u8d25: ${account.remark} ${e.message}`);
    return { success: false, cred: null };
  }
}

class XLXYH {
  constructor(cred) {
    this.sessionKey = cred.sessionKey;
    this.userId = cred.userId;
    this.openId = cred.openId || "";
    this.valid = !!(this.sessionKey && this.userId);
    this.taskStatus = {};
    this.taskList = [];
  }

  generateSign(timestamp, requestId, bodyOrQuery = "") {
    return signByHar(timestamp, requestId, bodyOrQuery);
  }

  async request(method, apiPath, data = "", extraHeaders = {}, options = {}) {
    if (!this.valid) return { code: 400, message: "CK invalid" };

    const retryDelays = [2000, 5000, 10000];
    let lastResult = { code: 500, message: "request failed" };

    for (let attempt = 0; attempt < retryDelays.length; attempt++) {
      const timestamp = Date.now().toString();
      const requestId = uuid32();
      const queryStr = apiPath.includes("?") ? apiPath.split("?")[1] : "";
      const bodyOrQuery = method === "GET" ? queryStr : (data || "");

      const headers = {
        Host: "qualcomm.boysup.cn",
        Connection: "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        timestamp,
        sign: this.generateSign(timestamp, requestId, bodyOrQuery),
        xweb_xhr: "1",
        openId: this.openId,
        requestId,
        userId: this.userId,
        sessionKey: this.sessionKey,
        "User-Agent": UA,
        Referer: `https://servicewechat.com/${WX_APPID}/666/page-frame.html`,
        Accept: "*/*",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        ...extraHeaders,
      };

      if (options?.skipSign) {
        delete headers.sign;
      }

      let status = 0;
      let rawResp = "";
      let parsed;

      try {
        const ret = await $.httpRequest({
          method,
          url: `https://qualcomm.boysup.cn${apiPath}`,
          headers,
          data: method === "GET" ? undefined : data,
        });
        status = ret.status;
        rawResp = ret.data;
      } catch (e) {
        status = e?.response?.status || 0;
        rawResp = e?.response?.data || e?.message || "";
      }

      if (typeof rawResp === "object" && rawResp !== null) {
        parsed = rawResp;
      } else if (typeof rawResp === "string") {
        try {
          parsed = JSON.parse(rawResp);
        } catch {
          parsed = { code: status || 500, message: shortText(rawResp || "response parse failed", 600) };
        }
      } else {
        parsed = { code: status || 500, message: String(rawResp || "network error") };
      }

      if (isWafBlock(status, rawResp, parsed?.message)) {
        lastResult = { code: 598, message: `WAF blocked (status=${status || 0})` };
        if (attempt < retryDelays.length - 1) {
          const waitMs = retryDelays[attempt];
          $.log(`WAF retry: ${method} ${apiPath}, wait ${Math.floor(waitMs / 1000)}s (${attempt + 1}/${retryDelays.length})`);
          await $.wait(waitMs);
          continue;
        }
        return lastResult;
      }

      return parsed;
    }

    return lastResult;
  }
  async getTaskStatus(showLog = true) {
    const res = await this.request("GET", `/qualcomm-app/api/home/taskDaily?userId=${this.userId}`);
    if (res.code === 200 && Array.isArray(res.data)) {
      this.taskStatus = {};
      this.taskList = res.data.map((t) => ({
        name: String(t?.name || ""),
        status: Number(t?.status || 0),
        remark: String(t?.remark || ""),
      }));

      for (const t of this.taskList) {
        this.taskStatus[t.name] = t.status;
      }

      if (showLog) {
        $.log('\u4efb\u52a1\u5217\u8868:');
        for (const t of this.taskList) {
          const done = t.status === 1;
          $.log(`  ${done ? '\u2705' : '\u2b55'} ${t.name}: ${done ? '\u5df2\u5b8c\u6210' : '\u672a\u5b8c\u6210'} (status:${t.status})`);
        }
      }
      return true;
    }

    $.log(`\u83b7\u53d6\u4efb\u52a1\u5217\u8868\u5931\u8d25: ${shortText(res.message || res.code, 120)}`);
    return false;
  }
  isTaskCompleted(name) {
    return this.taskStatus[name] === 1;
  }

  ensureAuthOrThrow(ret) {
    if (isAuthExpiredMsg(ret?.message)) {
      throw new Error(`AUTH_EXPIRED: ${ret.message || "登录过期"}`);
    }
  }

  async preheatDailySign() {
    const encOpenId = encodeURIComponent(this.openId || "");
    const body = `userId=${this.userId}&openId=${encOpenId}&activitySource=Xcx_MeiRiRenWu&urlPath=pages%2Ftask-center%2Findex&urlName=%E4%BB%BB%E5%8A%A1%E4%B8%AD%E5%BF%83&elementName=%E6%AF%8F%E6%97%A5%E7%AD%BE%E5%88%B0&elementType=%E9%A1%B5%E9%9D%A2&eventNameEn=MPClick`;
    const ret = await this.request("POST", "/qualcomm-app/api/buryPointApp/save", body);
    if (ret?.code !== 200) {
      return { ok: false, msg: ret?.message || ret?.code || "\u524d\u7f6e\u5931\u8d25" };
    }
    await $.wait(400 + Math.floor(Math.random() * 700));
    return { ok: true, msg: "ok" };
  }

  async run() {
    if (!this.valid) throw new Error("CK无效");

    const userInfo = await this.request("GET", `/qualcomm-app/api/user/info?userId=${this.userId}`);
    if (userInfo.code !== 200) {
      this.ensureAuthOrThrow(userInfo);
      throw new Error(`获取用户信息失败: ${userInfo.message || userInfo.code}`);
    }

    $.log(`用户: ${userInfo.data?.nick || this.userId} 等级:${userInfo.data?.level} 积分:${userInfo.data?.coreCoin}`);

    await this.getTaskStatus();

    if (!this.isTaskCompleted("\u6bcf\u65e5\u7b7e\u5230")) {
      const signPreheat = await this.preheatDailySign();
      if (!signPreheat.ok) {
        $.log(`\u7b7e\u5230\u524d\u7f6e\u57cb\u70b9\u5931\u8d25(\u7ee7\u7eed\u5c1d\u8bd5\u7b7e\u5230): ${shortText(signPreheat.msg, 100)}`);
      }

      let signRet = await this.request("GET", `/qualcomm-app/api/user/signIn?userId=${this.userId}`);

      if (!(signRet.code === 200 || isAlreadySignedMsg(signRet.message))) {
        const signGetNoSign = await this.request("GET", `/qualcomm-app/api/user/signIn?userId=${this.userId}`, "", {}, { skipSign: true });
        if (signGetNoSign.code === 200 || isAlreadySignedMsg(signGetNoSign.message)) {
          signRet = signGetNoSign;
        }
      }

      if (!(signRet.code === 200 || isAlreadySignedMsg(signRet.message))) {
        const signPost = await this.request("POST", "/qualcomm-app/api/user/signIn", `userId=${this.userId}`);
        if (signPost.code === 200 || isAlreadySignedMsg(signPost.message)) {
          signRet = signPost;
        }
      }

      if (!(signRet.code === 200 || isAlreadySignedMsg(signRet.message))) {
        const signPostNoSign = await this.request("POST", "/qualcomm-app/api/user/signIn", `userId=${this.userId}`, {}, { skipSign: true });
        if (signPostNoSign.code === 200 || isAlreadySignedMsg(signPostNoSign.message)) {
          signRet = signPostNoSign;
        }
      }

      if (!(signRet.code === 200 || isAlreadySignedMsg(signRet.message))) {
        const statusCheck = await this.request("GET", `/qualcomm-app/api/home/taskDaily?userId=${this.userId}`);
        if (statusCheck.code === 200 && Array.isArray(statusCheck.data)) {
          const signTask = pickDailySignTask(statusCheck.data);
          if (Number(signTask?.status) === 1) {
            signRet = { code: 200, data: { coreCoin: 0 }, message: "\u5df2\u7b7e\u5230(taskDaily\u5224\u5b9a)" };
            this.taskStatus["\u6bcf\u65e5\u7b7e\u5230"] = 1;
          }
        }
      }

      if (signRet.code === 200 || isAlreadySignedMsg(signRet.message)) {
        const coin = Number(signRet.data?.coreCoin || 0);
        if (coin > 0) $.log(`\u7b7e\u5230\u6210\u529f +${coin}`);
        else $.log(`\u7b7e\u5230\u5b8c\u6210: ${signRet.message || "\u5df2\u7b7e\u5230"}`);
      } else {
        if (isAuthExpiredMsg(signRet.message)) {
          $.log(`\u7b7e\u5230\u5931\u8d25(\u767b\u5f55\u6001\u95ee\u9898): ${shortText(signRet.message || "\u767b\u5f55\u8fc7\u671f", 120)}\uff0c\u7ee7\u7eed\u6267\u884c\u540e\u7eed\u4efb\u52a1`);
        } else {
          $.log(`\u7b7e\u5230\u5931\u8d25: ${shortText(signRet.message || signRet.code, 120)}`);
        }
      }
      await randomDelay(2, 5, "\u5ef6\u65f6");
    }

    if (!this.isTaskCompleted("每日参与抽奖")) {
      await this.handleDrawTask();
      await randomDelay(2, 5, "延时");
    }

    if (!this.isTaskCompleted("每日点赞文章")) {
      await this.handleLikeArticleTask();
      await randomDelay(2, 5, "延时");
    }

    if (!this.isTaskCompleted("每日阅读文章5分钟")) {
      await this.handleReadTask();
      await randomDelay(2, 5, "延时");
    }

    if (!this.isTaskCompleted("每日观看骁友Vlog视频1分钟")) {
      await this.handleVlogTask();
    }
  }

  async handleDrawTask() {
    $.log("开始抽奖任务");

    const listBefore = await this.request("GET", `/qualcomm-app/api/luckDraw/list?userId=${this.userId}&activityId=7`);
    let beforeCount = null;
    if (listBefore.code === 200 && listBefore.data) {
      beforeCount = Number(listBefore.data.luckDrawCount ?? 0);
      $.log(`抽奖次数: ${beforeCount}`);
      if (beforeCount <= 0) {
        $.log("今日抽奖次数已用完");
        return;
      }
    } else {
      this.ensureAuthOrThrow(listBefore);
      $.log(`抽奖前置查询失败: ${listBefore.message || listBefore.code}`);
    }

    const encOpenId = encodeURIComponent(this.openId || "");
    const subscribeBody = `moduleName=%E9%AA%81%E5%8F%8B%E4%BC%9A_%E6%88%90%E9%95%BF%E4%BB%BB%E5%8A%A1_%E6%AF%8F%E6%97%A5%E6%8A%BD%E5%A5%96%E6%8F%90%E9%86%92&subscribeId=21&urlName=%E8%8A%AF%E5%8A%A8%E7%A6%8F%E5%88%A9&urlPath=pages%2Fwheel%2Findex&state=accept&openId=${encOpenId}&userId=${this.userId}`;

    const buryClickDraw = `userId=${this.userId}&openId=${encOpenId}&activityId=7&activitySource=Xcx_ShouYeShortCut&isWifi=1&model=microsoft&manufacturer=microsoft&urlQuery=%7B%22channel%22%3A%22Xcx_ShouYeShortCut%22%7D&urlPath=pages%2Fwheel%2Findex&urlName=%E8%8A%AF%E5%8A%A8%E7%A6%8F%E5%88%A9&referrer=&scene=1145&pageStatus=&sfMsgTitle=&elementId=&elementName=%E7%82%B9%E5%87%BB%E6%8A%BD%E5%A5%96&elementType=%E9%A1%B5%E9%9D%A2&stallsName=&eventNameEn=MPClick`;
    const buryPopupShow = `userId=${this.userId}&openId=${encOpenId}&activityId=7&activitySource=Xcx_ShouYeShortCut&isWifi=1&model=microsoft&manufacturer=microsoft&urlQuery=%7B%22channel%22%3A%22Xcx_ShouYeShortCut%22%7D&urlPath=pages%2Fwheel%2Findex&urlName=%E8%8A%AF%E5%8A%A8%E7%A6%8F%E5%88%A9&referrer=&scene=1145&pageStatus=&sfMsgTitle=%E8%AE%A2%E9%98%85%E6%B6%88%E6%81%AF&eventNameEn=PlanPopupDisplay&sfMsgState=%E6%88%90%E5%8A%9F&sfMsgContent=%E6%B4%BB%E5%8A%A8%E5%8F%82%E4%B8%8E%E6%8F%90%E9%86%92`;
    const buryPopupAccept = `userId=${this.userId}&openId=${encOpenId}&activityId=7&activitySource=Xcx_ShouYeShortCut&isWifi=1&model=microsoft&manufacturer=microsoft&urlQuery=%7B%22channel%22%3A%22Xcx_ShouYeShortCut%22%7D&urlPath=pages%2Fwheel%2Findex&urlName=%E8%8A%AF%E5%8A%A8%E7%A6%8F%E5%88%A9&referrer=&scene=1145&pageStatus=&sfMsgTitle=%E8%AE%A2%E9%98%85%E6%B6%88%E6%81%AF&elementName=%E6%8E%A5%E5%8F%97&elementId=4Z1oTnNf9xc65ZawEN7UVhmf0o3egu8v1Xpn1zk-Qmc&sfMsgContent=%E6%B4%BB%E5%8A%A8%E5%8F%82%E4%B8%8E%E6%8F%90%E9%86%92&stallsName=&elementType=%E5%BC%B9%E7%AA%97&eventNameEn=MPClick`;

    // 更贴近抓包的顺序，降低非法请求概率
    await this.request("POST", "/qualcomm-app/api/buryPointApp/save", buryClickDraw);
    await $.wait(1000 + Math.floor(Math.random() * 1200));
    await this.request("POST", "/qualcomm-app/api/activity/rules", "activityId=7&type=0");
    await $.wait(1000 + Math.floor(Math.random() * 1200));
    await this.request("POST", "/qualcomm-app/api/buryPointApp/save", buryPopupShow);
    await $.wait(600 + Math.floor(Math.random() * 1000));
    await this.request("POST", "/qualcomm-app/api/buryPointApp/save", buryPopupAccept);
    await $.wait(800 + Math.floor(Math.random() * 1200));
    await this.request("POST", "/qualcomm-app/api/messageSubscribeApp/save", subscribeBody);
    await $.wait(2500 + Math.floor(Math.random() * 2500));

    const body = `userId=${this.userId}&activityId=7`;
    let drawRes = await this.request("POST", "/qualcomm-app/api/luckDraw/getLuck", body);

    // 非法请求：补一次全前置后再试
    if (drawRes.code !== 200 && /非法请求/.test(String(drawRes.message || ""))) {
      $.log("抽奖返回非法请求，补前置后重试一次");
      await $.wait(5000 + Math.floor(Math.random() * 3000));
      await this.request("POST", "/qualcomm-app/api/buryPointApp/save", buryClickDraw);
      await $.wait(800 + Math.floor(Math.random() * 1000));
      await this.request("POST", "/qualcomm-app/api/activity/rules", "activityId=7&type=0");
      await $.wait(800 + Math.floor(Math.random() * 1000));
      await this.request("POST", "/qualcomm-app/api/messageSubscribeApp/save", subscribeBody);
      await $.wait(2500 + Math.floor(Math.random() * 2500));
      drawRes = await this.request("POST", "/qualcomm-app/api/luckDraw/getLuck", body);
    }

    // 频控：等待后再试一次
    if (drawRes.code !== 200 && /请求太频繁|请稍后再试|操作太频繁/.test(String(drawRes.message || ""))) {
      $.log("抽奖触发频控，等待后重试一次");
      await $.wait(20000 + Math.floor(Math.random() * 12000));
      drawRes = await this.request("POST", "/qualcomm-app/api/luckDraw/getLuck", body);
    }

    if (drawRes.code === 200) {
      const prize = drawRes.data?.name || (drawRes.data?.coreCoin ? `${drawRes.data.coreCoin}积分` : "未知奖品");
      $.log(`抽奖成功: ${prize}`);
      return;
    }

    // 兜底：看次数是否已扣减（已受理）
    const listAfter = await this.request("GET", `/qualcomm-app/api/luckDraw/list?userId=${this.userId}&activityId=7`);
    if (listAfter.code === 200 && listAfter.data && beforeCount !== null) {
      const afterCount = Number(listAfter.data.luckDrawCount ?? beforeCount);
      if (afterCount < beforeCount) {
        $.log(`抽奖疑似已受理(次数 ${beforeCount}->${afterCount})`);
        return;
      }
    }

    this.ensureAuthOrThrow(drawRes);
    if (drawRes.code === 201) {
      $.log(drawRes.message || "今日抽奖次数已用完");
    } else {
      $.log(`抽奖失败: ${drawRes.message || drawRes.code}`);
    }
  }

  async handleLikeArticleTask() {
    const list = await this.request("GET", `/qualcomm-app/api/home/articles?page=1&size=10&userId=${this.userId}&type=0&searchDate=&articleShowPlace=%E9%AA%81%E5%8F%8B%E8%B5%84%E8%AE%AF%E5%88%97%E8%A1%A8%E9%A1%B5`);
    if (!(list.code === 200 && list.data?.articleList?.length)) {
      this.ensureAuthOrThrow(list);
      $.log("\u672a\u83b7\u53d6\u5230\u6587\u7ae0\uff0c\u8df3\u8fc7\u70b9\u8d5e");
      return;
    }

    const all = list.data.articleList.filter((it) => it?.id);
    const isLiked = (it) => Number(it?.isLike ?? it?.likeStatus ?? it?.likeState ?? it?.liked ?? 0) === 1;
    const candidates = [...all.filter((it) => !isLiked(it)), ...all.filter((it) => isLiked(it))].slice(0, 10);

    for (const a of candidates) {
      const like = await this.request("GET", `/qualcomm-app/api/article/like?articleId=${a.id}&userId=${this.userId}`);

      if (like.code !== 200) {
        this.ensureAuthOrThrow(like);
        const m = String(like.message || "");
        if (/\u8bf7\u6c42\u592a\u9891\u7e41|\u8bf7\u7a0d\u540e\u518d\u8bd5|\u64cd\u4f5c\u592a\u9891\u7e41/.test(m)) {
          $.log(`\u70b9\u8d5e\u9891\u63a7(\u6587\u7ae0${a.id})\uff0c\u7b49\u5f85\u540e\u91cd\u8bd5\u4e0b\u4e00\u7bc7`);
          await $.wait(2000 + Math.floor(Math.random() * 2500));
          continue;
        }
        $.log(`\u70b9\u8d5e\u5931\u8d25(\u6587\u7ae0${a.id}): ${shortText(like.message || like.code, 100)}`);
        continue;
      }

      await $.wait(600 + Math.floor(Math.random() * 900));
      await this.getTaskStatus(false);
      if (this.isTaskCompleted("\u6bcf\u65e5\u70b9\u8d5e\u6587\u7ae0")) {
        $.log(`\u70b9\u8d5e\u4efb\u52a1\u5b8c\u6210(${like.message || "\u6210\u529f"})`);
        return;
      }

      const msg = String(like.message || "");
      if (/\u5df2\u70b9\u8d5e/.test(msg)) {
        $.log(`\u6587\u7ae0${a.id}\u5df2\u70b9\u8d5e\uff0c\u5c1d\u8bd5\u4e0b\u4e00\u7bc7`);
      } else {
        $.log(`\u6587\u7ae0${a.id}\u70b9\u8d5e\u8fd4\u56de: ${msg || "\u6210\u529f"}\uff0c\u7ee7\u7eed\u6821\u9a8c\u4efb\u52a1\u72b6\u6001`);
      }

      await $.wait(500 + Math.floor(Math.random() * 900));
    }

    await this.getTaskStatus(false);
    if (this.isTaskCompleted("\u6bcf\u65e5\u70b9\u8d5e\u6587\u7ae0")) {
      $.log("\u70b9\u8d5e\u4efb\u52a1\u5b8c\u6210(\u72b6\u6001\u5237\u65b0\u5224\u5b9a)");
      return;
    }

    $.log("\u70b9\u8d5e\u63a5\u53e3\u5df2\u5c1d\u8bd5\u591a\u7bc7\uff0c\u4f46\u4efb\u52a1\u4ecd\u672a\u5b8c\u6210");
  }

  async handleReadTask() {
    const list = await this.request("GET", `/qualcomm-app/api/home/articles?page=1&size=10&userId=${this.userId}&type=0&searchDate=&articleShowPlace=骁友资讯列表页`);
    if (!(list.code === 200 && list.data?.articleList?.length)) {
      this.ensureAuthOrThrow(list);
      $.log("未获取到文章，跳过阅读");
      return;
    }

    const a = list.data.articleList[0];
    await this.request("POST", "/qualcomm-app/api/article/enterReadDaily", `articleId=${a.id}&userId=${this.userId}`);
    await this.request("GET", `/qualcomm-app/api/article/like?articleId=${a.id}&userId=${this.userId}`);
    await this.request("POST", "/qualcomm-app/api/article/shareDaily", `articleId=${a.id}&userId=${this.userId}`);

    $.log("模拟阅读310秒...");
    await $.wait(310000);

    const exit = await this.request("POST", "/qualcomm-app/api/article/exitReadDaily", `articleId=${a.id}&userId=${this.userId}`);
    if (exit.code === 200) $.log("阅读任务完成");
    else this.ensureAuthOrThrow(exit);
  }

  async handleVlogTask() {
    const v = await this.request("GET", `/qualcomm-app/api/article/vlogList?page=1&size=20&userId=${this.userId}&sortBy=1`);
    if (!(v.code === 200 && v.data?.records?.length)) {
      this.ensureAuthOrThrow(v);
      $.log(`获取VLOG失败: ${v.message || v.code}`);
      return;
    }

    const one = v.data.records[0];
    const enter = await this.request("POST", "/qualcomm-app/api/article/enterReadDaily", `articleId=${one.id}&userId=${this.userId}`);
    if (enter.code !== 200) {
      this.ensureAuthOrThrow(enter);
      $.log(`进入VLOG失败: ${enter.message || enter.code}`);
      return;
    }

    $.log("模拟观看70秒...");
    await $.wait(70000);

    const exit = await this.request("POST", "/qualcomm-app/api/article/exitReadDaily", `articleId=${one.id}&userId=${this.userId}`);
    if (exit.code === 200) {
      await this.request("GET", `/qualcomm-app/api/article/like?articleId=${one.id}&userId=${this.userId}`);
      await this.request("POST", "/qualcomm-app/api/article/shareDaily", `articleId=${one.id}&userId=${this.userId}`);
      $.log("VLOG任务完成");
    } else {
      this.ensureAuthOrThrow(exit);
      $.log(`退出VLOG失败: ${exit.message || exit.code}`);
    }
  }
}

async function main() {
  const raw = process.env[ckName] || "";
  if (!raw) {
    $.log(`未找到变量 ${ckName}`);
    return;
  }
  if (!WECHAT_SERVER) {
    $.log("未配置 WECHAT_SERVER");
    return;
  }

  const accounts = parseAccounts(raw);
  if (!accounts.length) {
    $.log("未解析到有效账号");
    return;
  }

  const cache = loadCache();
  $.log(`账号数量: ${accounts.length} 缓存: ${CACHE_NAME}.json`);

  for (let i = 0; i < accounts.length; i++) {
    const acc = accounts[i];
    if (i > 0) await randomDelay(5, 10, `等待 ${acc.remark} 开始`);
    await randomDelay(6, 12, `${acc.remark} 延时后开始`);

    $.log(`\n开始账号 ${i + 1}/${accounts.length}: ${acc.remark}`);

    try {
      const ret = await getValidCred(acc, cache);
      let cred = ret.cred;
      if (!ret.success || !cred) {
        $.log(`${acc.remark} 获取CK失败，跳过`);
        continue;
      }

      if (!cred.openId) {
        $.log(`${acc.remark} CK缺少openId，自动刷新`);
        const refreshed = await refreshCredOnce(acc, { requireSignable: false, maxTry: 2 });
        cred = refreshed.cred;
        if (refreshed.signable) {
          cache[acc.wxid] = cred;
          saveCache(cache);
        } else {
          $.log(`\u26a0\ufe0f ${acc.remark} \u5237\u65b0\u540e\u7684CK\u4e0d\u53ef\u7b7e\u5230\uff0c\u672a\u5199\u5165\u7f13\u5b58`);
        }
      }

      let runner = new XLXYH(cred);
      try {
        await runner.run();
      } catch (e) {
        if (/AUTH_EXPIRED/i.test(String(e?.message || ""))) {
          $.log(`${acc.remark} \u767b\u5f55\u6001\u8fc7\u671f\uff0c\u5237\u65b0\u540e\u91cd\u8bd5\u4e00\u6b21`);
          try {
            const refreshed = await refreshCredOnce(acc, { requireSignable: true, maxTry: 3 });
            cred = refreshed.cred;
            cache[acc.wxid] = cred;
            saveCache(cache);
            runner = new XLXYH(cred);
            await runner.run();
          } catch (re) {
            $.log(`${acc.remark} \u81ea\u52a8\u5237\u65b0\u5931\u8d25\uff0c\u4fdd\u7559\u7f13\u5b58\u5e76\u8df3\u8fc7: ${shortText(re?.message || re, 140)}`);
          }
        } else {
          throw e;
        }
      }

      $.log(`${acc.remark} 执行完成`);
    } catch (e) {
      $.log(`${acc.remark} 失败: ${e.message || e}`);
    }
  }

  $.log("全部账号处理完成");
}

main().catch((e) => {
  $.log(`脚本异常: ${e.message || e}`);
  console.error(e?.stack || e);
});
