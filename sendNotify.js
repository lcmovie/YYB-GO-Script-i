'use strict';

const axios = require('axios');

async function post(url, data, headers = {}) {
  const response = await axios.post(url, data, {
    timeout: 20000,
    proxy: false,
    headers,
    validateStatus: () => true,
  });
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.data;
}

async function serverChan(title, content) {
  const key = String(process.env.PUSH_KEY || '').trim();
  if (!key) return false;
  const base = key.startsWith('sctp') ? 'https://sctapi.ftqq.com' : 'https://sc.ftqq.com';
  await post(`${base}/${encodeURIComponent(key)}.send`, new URLSearchParams({ title, desp: content }).toString(), {
    'Content-Type': 'application/x-www-form-urlencoded',
  });
  return true;
}

async function pushPlus(title, content) {
  const token = String(process.env.PUSH_PLUS_TOKEN || '').trim();
  if (!token) return false;
  const body = { token, title, content, template: 'txt' };
  const topic = String(process.env.PUSH_PLUS_USER || '').trim();
  if (topic) body.topic = topic;
  await post('https://www.pushplus.plus/send', body, { 'Content-Type': 'application/json' });
  return true;
}

async function qiYeWeiXin(title, content) {
  const key = String(process.env.QYWX_KEY || '').trim();
  if (!key) return false;
  await post(`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${encodeURIComponent(key)}`, {
    msgtype: 'text',
    text: { content: `${title}\n${content}` },
  }, { 'Content-Type': 'application/json' });
  return true;
}

async function sendNotify(title, content = '') {
  const text = String(content || '');
  console.log(`\n============== 通知 ==============\n${title}\n${text}`);
  const channels = [serverChan, pushPlus, qiYeWeiXin];
  let configured = 0;
  for (const channel of channels) {
    try {
      if (await channel(String(title), text)) configured += 1;
    } catch (error) {
      console.log(`[通知失败] ${channel.name}: ${error.message || error}`);
    }
  }
  if (!configured) console.log('未配置 PUSH_KEY、PUSH_PLUS_TOKEN 或 QYWX_KEY，仅输出日志');
}

module.exports = { sendNotify };
