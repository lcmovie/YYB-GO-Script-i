'use strict';

const axios = require('axios');

function entries() {
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

const configuredEntries = entries();
if (!process.env.WX_ID && configuredEntries.length) {
  process.env.WX_ID = configuredEntries.map(item => item.ref).join('\n');
}

function selectEntry(identifier) {
  if (!configuredEntries.length) {
    throw new Error('未配置 YYB_SERVER，格式：地址@账号ref，多账号换行');
  }
  const raw = String(identifier || '').split('#')[0].trim();
  const found = configuredEntries.find(item => item.ref === raw || `${item.server}@${item.ref}` === raw);
  if (found) return found;
  if (configuredEntries.length === 1) return configuredEntries[0];
  throw new Error(`YYB_SERVER 中找不到账号ref：${raw}`);
}

async function post(identifier, appId, route, payload) {
  const item = selectEntry(identifier);
  const body = { ref: item.ref, app_id: appId };
  if (payload !== undefined) body.payload = payload;
  const response = await axios.post(`${item.server}${route}`, body, {
    timeout: 30000,
    proxy: false,
    validateStatus: () => true,
    headers: { 'Content-Type': 'application/json' },
  });
  const data = response.data || {};
  if (response.status !== 200 || Number(data.code) !== 0) {
    throw new Error(data.msg || `YYB请求失败（HTTP ${response.status}）`);
  }
  const result = data.data && data.data.result;
  if (!result || typeof result !== 'object') throw new Error('YYB响应缺少data.result');
  return result;
}

class YYBAdapter {
  constructor(serverUrl) {
    this.serverUrl = serverUrl || (configuredEntries[0] && configuredEntries[0].server) || '';
  }
  async _resolveRef(identifier) {
    return selectEntry(identifier).ref;
  }
  async getCode(identifier, appId) {
    const result = await post(identifier, appId, '/wxapp/getCode');
    if (!result.code) throw new Error('YYB未返回有效code');
    return result.code;
  }
}

class WeChatCodeGetter {
  constructor() {
    this.yybServer = (configuredEntries[0] && configuredEntries[0].server) || '';
    this.protocolType = 'YYB';
  }
  async init() {
    if (!configuredEntries.length) throw new Error('未配置 YYB_SERVER');
    return this;
  }
  async getAppletCode(appId, identifier) {
    return new YYBAdapter().getCode(identifier, appId);
  }
}

async function getSingleCode(appId, identifier) {
  try {
    return await new YYBAdapter().getCode(identifier, appId);
  } catch (error) {
    console.log(`[getCode] 获取code失败：${error.message}`);
    return null;
  }
}

async function getSinglePhoneNumber(appId, identifier) {
  try {
    const result = await post(identifier, appId, '/wxapp/getPhoneNumber');
    return result.code || null;
  } catch (error) {
    console.log(`[getCode] 获取手机号code失败：${error.message}`);
    return null;
  }
}

async function getSingleOperateWxData(appId, identifier, payload) {
  try {
    if (payload) return await post(identifier, appId, '/wxapp/operateWxData', payload);
    const code = await getSingleCode(appId, identifier);
    return code ? { code, encryptedData: null, iv: null } : null;
  } catch (error) {
    console.log(`[getCode] 获取operateWxData失败：${error.message}`);
    return null;
  }
}

module.exports = {
  YYBAdapter,
  WeChatCodeGetter,
  getSingleCode,
  getSinglePhoneNumber,
  getSinglePhoneEncrypted: getSinglePhoneNumber,
  getSingleOperateWxData,
};

