'use strict';

async function sendNotify(title, content) {
  console.log(`\n============== 通知 ==============\n${title}\n${content || ''}`);
}

module.exports = { sendNotify };
