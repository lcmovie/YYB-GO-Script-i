/**
 * 网易云音乐自动签到脚本
 * 
 * @description 支持青龙面板的全自动签到脚本
 * @author Your Name
 * @version 1.0.0
 * @license MIT
 * 
 * 功能：
 * 1. 普通签到（PC端 + 安卓端）
 * 2. 云贝签到 + 连签奖励领取
 * 3. 云贝日常任务自动完成
 * 4. 黑胶乐签打卡（+3成长值）
 * 5. VIP成长日常任务领取
 * 6. VIP成长值一键领取
 * 
 * 环境变量：
 * NETEASE_MUSIC_U - MUSIC_U cookie值
 * 
 * cron: 0 9 * * *
 * 
 * 
 * ⚠️ 免责声明：
 * 1. 本脚本仅供学习交流使用，请勿用于商业用途
 * 2. 使用本脚本造成的任何后果由使用者自行承担
 * 3. 本脚本不存储、不上传任何用户数据
 * 4. 使用前请确认遵守网易云音乐用户服务条款
 */

const https = require('https');
const crypto = require('crypto');

// 从环境变量获取MUSIC_U
const MUSIC_U = process.env.NETEASE_MUSIC_U || '';

if (!MUSIC_U) {
    console.log('❌ 请设置环境变量 NETEASE_MUSIC_U');
    console.log('   在青龙面板添加环境变量：');
    console.log('   名称：NETEASE_MUSIC_U');
    console.log('   值：你的MUSIC_U cookie值');
    process.exit(1);
}

// 通知函数（青龙面板内置）
let notify;
try {
    notify = require('./sendNotify');
} catch (e) {
    notify = {
        sendNotify: async (title, content) => {
            console.log(`📢 ${title}\n${content}`);
        }
    };
}

// weapi加密参数
const presetKey = '0CoJUm6Qyw8W8jud';
const iv = '0102030405060708';
const publicKey = '010001';
const modulus = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7';

function aesEncrypt(text, key) {
    const cipher = crypto.createCipheriv('aes-128-cbc', key, iv);
    return cipher.update(text, 'utf8', 'base64') + cipher.final('base64');
}

function rsaEncrypt(text, pubKey, mod) {
    const reversedText = text.split('').reverse().join('');
    const hexText = Buffer.from(reversedText).toString('hex');
    const encrypted = BigInt('0x' + hexText) ** BigInt('0x' + pubKey) % BigInt('0x' + mod);
    return encrypted.toString(16).padStart(256, '0');
}

function generateSecretKey(size) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let key = '';
    for (let i = 0; i < size; i++) {
        key += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return key;
}

function encryptRequest(data) {
    const text = JSON.stringify(data);
    const secretKey = generateSecretKey(16);
    const params = aesEncrypt(aesEncrypt(text, presetKey), secretKey);
    const encSecKey = rsaEncrypt(secretKey, publicKey, modulus);
    return { params, encSecKey };
}

// 发送请求
function request(hostname, path, data = {}) {
    return new Promise((resolve, reject) => {
        const encrypted = encryptRequest(data);
        const postData = `params=${encodeURIComponent(encrypted.params)}&encSecKey=${encodeURIComponent(encrypted.encSecKey)}`;

        const options = {
            hostname: hostname,
            port: 443,
            path: path,
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Content-Length': Buffer.byteLength(postData),
                'Cookie': `MUSIC_U=${MUSIC_U}; os=pc; appver=2.10.6;`,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://music.163.com/',
                'Origin': 'https://music.163.com'
            }
        };

        const req = https.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                try {
                    resolve(JSON.parse(body));
                } catch (e) {
                    resolve({ code: -1, body });
                }
            });
        });

        req.on('error', reject);
        req.write(postData);
        req.end();
    });
}

// 获取用户信息
async function getUserInfo() {
    return await request('music.163.com', '/weapi/nuser/account/get', {});
}

// 普通签到
async function dailySign(type = 0) {
    return await request('music.163.com', '/weapi/point/dailyTask', { type });
}

// 云贝签到
async function yunbeiSign() {
    return await request('music.163.com', '/weapi/pointmall/user/sign', {});
}

// 云贝签到进度（连续签到奖励）
async function yunbeiSignProgress() {
    return await request('music.163.com', '/weapi/pointmall/user/sign/progress', {});
}

// 领取云贝签到奖励
async function yunbeiSignLottery(userLotteryId) {
    return await request('music.163.com', '/weapi/pointmall/user/lottery/get', { userLotteryId: String(userLotteryId) });
}

// 获取云贝待完成任务列表
async function yunbeiTaskTodo() {
    return await request('music.163.com', '/weapi/usertool/task/todo/query', {});
}

// 完成云贝任务领取奖励
async function yunbeiTaskFinish(period, userTaskId, depositCode) {
    return await request('music.163.com', '/weapi/usertool/task/point/receive', {
        period: String(period),
        userTaskId: String(userTaskId),
        depositCode: String(depositCode)
    });
}

// 获取云贝余额
async function yunbeiInfo() {
    return await request('music.163.com', '/weapi/v1/user/info', {});
}

// 黑胶乐签打卡 ✨
async function vipSign() {
    return await request('interface3.music.163.com', '/weapi/vip-center-bff/task/sign', {});
}

// 获取VIP成长值信息
async function getVipGrowth() {
    return await request('music.163.com', '/weapi/vipnewcenter/app/level/growhpoint/basic', {});
}

// 领取所有VIP成长值任务奖励
async function receiveAllVipReward() {
    return await request('music.163.com', '/weapi/vipnewcenter/app/level/task/reward/getall', {});
}

// VIP成长任务列表（日常任务）
async function getVipMissionProgress() {
    return await request('interface3.music.163.com', '/weapi/middle/vip/mission/user/progress/list', {});
}

// 领取VIP任务奖励
async function receiveVipMissionReward(userRewardId, userProgressId) {
    return await request('interface3.music.163.com', '/weapi/middle/vip/mission/user/reward/receive', {
        userRewardId: String(userRewardId),
        userProgressId: String(userProgressId)
    });
}
async function main() {
    console.log('🎵 网易云音乐完整签到');
    console.log('时间：' + new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }));
    console.log('='.repeat(50));

    let message = '';

    try {
        // 1. 获取用户信息
        console.log('\n🔐 检查登录状态...');
        const userInfo = await getUserInfo();
        const account = userInfo.account || userInfo.data?.account;
        const profile = userInfo.profile || userInfo.data?.profile;
        if (userInfo.code === 200 && (account || profile)) {
            const nickname = profile?.nickname || account?.userName || '用户';
            console.log(`   ✅ 用户：${nickname}`);
            message += `👤 用户：${nickname}\n`;
        } else {
            console.log('   ❌ 登录失败，请检查MUSIC_U');
            console.log('   响应：', JSON.stringify(userInfo).substring(0, 200));
            await notify.sendNotify('网易云签到失败', '登录失败，请检查MUSIC_U');
            return;
        }

        // 2. 普通签到
        console.log('\n📝 普通签到...');

        // 安卓端
        const androidSign = await dailySign(0);
        if (androidSign.code === 200) {
            console.log(`   ✅ 安卓端签到成功！获得 ${androidSign.point || 0} 积分`);
            message += `✅ 安卓端签到成功 (+${androidSign.point || 0})\n`;
        } else if (androidSign.code === -2) {
            console.log('   ⚠️ 安卓端今日已签到');
            message += '⚠️ 安卓端已签到\n';
        } else {
            console.log(`   ❌ 安卓端签到失败`);
        }

        // PC端
        const pcSign = await dailySign(1);
        if (pcSign.code === 200) {
            console.log(`   ✅ PC端签到成功！获得 ${pcSign.point || 0} 积分`);
            message += `✅ PC端签到成功 (+${pcSign.point || 0})\n`;
        } else if (pcSign.code === -2) {
            console.log('   ⚠️ PC端今日已签到');
            message += '⚠️ PC端已签到\n';
        } else {
            console.log(`   ❌ PC端签到失败 (${pcSign.code}: ${pcSign.message || pcSign.msg || '未知错误'})`);
        }

        // 3. 云贝签到
        console.log('\n☁️ 云贝签到...');
        const yunbei = await yunbeiSign();
        if (yunbei.code === 200) {
            console.log('   ✅ 云贝签到成功！+5云贝');
            message += '✅ 云贝签到成功 (+5云贝)\n';
        } else {
            console.log('   ⚠️ 云贝今日已签到');
            message += '⚠️ 云贝已签到\n';
        }

        // 3.1 云贝签到进度奖励
        console.log('\n📅 云贝签到进度奖励...');
        try {
            const progress = await yunbeiSignProgress();
            if (progress.code === 200 && progress.data?.lotteryConfig) {
                let rewardCount = 0;
                for (const config of progress.data.lotteryConfig) {
                    if (config.baseLotteryId > 0 && config.baseLotteryStatus === 1) {
                        const lottery = await yunbeiSignLottery(config.baseLotteryId);
                        if (lottery.code === 200 && lottery.data) {
                            console.log(`   ✅ 连续签到${config.signDay}天奖励领取成功`);
                            rewardCount++;
                        }
                    }
                }
                if (rewardCount > 0) {
                    message += `✅ 云贝连签奖励×${rewardCount}\n`;
                } else {
                    console.log('   ℹ️ 暂无连签奖励可领');
                }
            }
        } catch (e) {
            console.log('   ⚠️ 签到进度检查失败');
        }

        // 3.2 云贝日常任务
        console.log('\n📋 云贝日常任务...');
        try {
            const tasks = await yunbeiTaskTodo();
            if (tasks.code === 200 && tasks.data) {
                let taskCount = 0;
                for (const task of tasks.data) {
                    if (task.completed) {
                        const finish = await yunbeiTaskFinish(task.period, task.userTaskId, task.depositCode);
                        if (finish.code === 200) {
                            console.log(`   ✅ [${task.taskName}] 完成，+${task.taskPoint}云贝`);
                            taskCount++;
                        }
                    }
                }
                if (taskCount > 0) {
                    message += `✅ 云贝任务×${taskCount}\n`;
                } else {
                    console.log('   ℹ️ 暂无已完成的任务可领取');
                }
            }
        } catch (e) {
            console.log('   ⚠️ 云贝任务检查失败');
        }

        // 获取云贝余额
        let yunbeiBalance = 0;
        try {
            const info = await yunbeiInfo();
            if (info.code === 200) {
                yunbeiBalance = info.userPoint?.balance || info.data?.userPoint?.balance || 0;
                console.log(`   💰 云贝余额：${yunbeiBalance}`);
                message += `☁️ 云贝余额：${yunbeiBalance}\n`;
            }
        } catch (e) { }

        // 4. 黑胶乐签打卡 ✨
        console.log('\n💎 黑胶乐签打卡...');
        const vipSignResult = await vipSign();
        if (vipSignResult.code === 200 && vipSignResult.data === true) {
            console.log('   ✅ 黑胶乐签打卡成功！+3成长值');
            message += '✅ 黑胶乐签成功 (+3成长值)\n';
        } else if (vipSignResult.code === 200 && vipSignResult.data === false) {
            console.log('   ⚠️ 黑胶乐签今日已打卡');
            message += '⚠️ 黑胶乐签已打卡\n';
        } else {
            console.log(`   ⚠️ 黑胶乐签：${vipSignResult.message || '可能不是VIP'}`);
        }

        // 4.5 VIP日常任务（成长任务）
        console.log('\n📋 VIP成长日常任务...');
        try {
            const missions = await getVipMissionProgress();
            if (missions.code === 200 && missions.data) {
                let missionCount = 0;
                let totalGrowth = 0;
                for (const mission of missions.data) {
                    // 检查任务阶段是否可领取 (stageStatus === 100 表示已完成可领取)
                    if (mission.stageProgressDTOS) {
                        for (const stage of mission.stageProgressDTOS) {
                            if (stage.stageStatus === 100 && stage.userRewardId && stage.userProgressId) {
                                const claim = await receiveVipMissionReward(stage.userRewardId, stage.userProgressId);
                                if (claim.code === 200) {
                                    const taskName = mission.basicMissionDTO?.name || '任务';
                                    console.log(`   ✅ [${taskName}] +${stage.worth || stage.rewardCount}成长值`);
                                    missionCount++;
                                    totalGrowth += (stage.worth || stage.rewardCount || 0);
                                }
                            }
                        }
                    }
                }
                if (missionCount > 0) {
                    console.log(`   📈 共领取 ${missionCount} 个任务，+${totalGrowth}成长值`);
                    message += `✅ VIP任务×${missionCount} (+${totalGrowth})\n`;
                } else {
                    console.log('   ℹ️ 暂无可领取的日常任务奖励');
                }
            }
        } catch (e) {
            console.log('   ⚠️ VIP任务检查失败:', e.message);
        }

        // 5. VIP成长值
        console.log('\n📊 VIP成长值...');
        const vipGrowth = await getVipGrowth();
        if (vipGrowth.code === 200 && vipGrowth.data) {
            const data = vipGrowth.data.userLevel || vipGrowth.data;
            console.log(`   等级：${data.levelName || 'Lv.' + data.level}`);
            console.log(`   成长值：${data.growthPoint}`);
            console.log(`   昨日获得：+${data.yesterdayPoint || 0}`);
            message += `\n💎 VIP等级：${data.levelName || 'Lv.' + data.level}\n`;
            message += `📊 成长值：${data.growthPoint}\n`;
            message += `📈 昨日获得：+${data.yesterdayPoint || 0}\n`;
        }

        // 6. 领取VIP任务奖励
        console.log('\n🎁 领取VIP任务奖励...');
        const reward = await receiveAllVipReward();
        if (reward.code === 200 && reward.data?.result) {
            console.log('   ✅ VIP任务奖励领取成功！');
            message += '✅ VIP奖励已领取\n';
        } else {
            console.log('   ℹ️ 暂无可领取奖励');
        }

        console.log('\n' + '='.repeat(50));
        console.log('🎉 所有签到任务完成！');
        message += '\n🎉 签到完成！';

    } catch (error) {
        console.log(`\n❌ 错误：${error.message}`);
        message = `❌ 签到出错：${error.message}`;
    }

    // 发送通知
    await notify.sendNotify('🎵 网易云音乐签到', message);
}

main();
