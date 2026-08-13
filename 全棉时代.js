/**
 日期：2026-4-15
 软件：全棉时代
 定时：一天3次
 cron:51 11,15 * * *
 */

const $ = new Env('全棉时代');
const axios = require('axios');
const { getSingleCode } = require('./getCode.js');
const sendNotify = require('./sendNotify');
const {log} = console;
const debug = 0; //0为关闭调试，1为打开调试,默认为0

const { setGlobalDispatcher, Agent } = require('undici');
setGlobalDispatcher(new Agent({
  allowH2: false, // 关键：关闭 HTTP/2
  connect: { rejectUnauthorized: false }
}));

//////////////////////
let scriptVersion = "1.0.7";  // 合并 1.0.7: 自动获取签到ID + 新版活动任务 finish 接口
let scriptVersionLatest = '1.0.7';
let S_qmsdCk = ($.isNode() ? process.env.WX_ID : $.getdata("WX_ID")) || ""
let S_qmsdCkArr = [];
let msg = '';
let wxid = '';
let userAgent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x18002230) NetType/WIFI Language/zh_CN';
let accountTips = '';
let taskBeforeScore = 0;
let scriptAppId = "wxdfcaa44b1aa891a7";
let scriptToken = "";
let scriptUnionID = "";
let scriptOpenId = "";
let scriptPhone = "";
let scriptSessionKey = "";
let scriptSign = "";
let scriptCode = "b8fe166f-8641-460c-9f79-edd6489a8d62";
let scriptSignId = ($.isNode() ? process.env.QMSD_SIGN_ID : $.getdata("QMSD_SIGN_ID")) || "QD26060001";
let factoryInfo = [];

// 空的GetRewrite函数，避免未定义错误
async function GetRewrite() {
    // 此函数用于处理重写请求，当前脚本不需要实现
    return;
}

!(async () => {
    if (typeof $request !== "undefined") {
        await GetRewrite();
    } else {
        if (!(await Envs()))
            return;
        else {
            log(`\n\n=============================================    \n脚本执行 - 北京时间(UTC+8)：${new Date(
                new Date().getTime() + new Date().getTimezoneOffset() * 60 * 1000 +
                8 * 60 * 60 * 1000).toLocaleString()} \n=============================================\n`);


            log(`\n============ 当前版本：${scriptVersion}，最新版本：${scriptVersionLatest} ============`)
            log(`\n=================== 共找到 ${S_qmsdCkArr.length} 个账号 ===================`)
            if (debug) {
                log(`【debug】 这是你的全部账号数组:\n ${S_qmsdCkArr}`);
            }

            for (let index = 0; index < S_qmsdCkArr.length; index++) {
                let num = index + 1
                log(`\n========= 开始【第 ${num} 个账号】=========\n`)
                accountTips = `账号【${num}】`;
                wxid = S_qmsdCkArr[index];
                if (wxid.indexOf("#") !== -1) {
                    wxid = wxid.split("#")[0].trim();
                }
                taskBeforeScore = 0;
                let code = await getCode();
                if (code == "") {
                    log(`\n==== 账号【${num}】获取code失败 ====\n`);
                    continue;
                }
                log(`\n==== 全棉时代登录 ====\n`)
                let loginFlag = await doLogin(code);
                await $.wait(2000);
                if (!loginFlag) {
                    log(`\n==== 账号【${num}】登入失败 ====\n`);
                    continue;
                }

                scriptSignId = await fetchSignId();
                await $.wait(1000);
                log(`${accountTips}当前签到ID：${scriptSignId}`);

                log(`\n==== 全棉时代每日签到 ====\n`)
                let signFlag = await signDetail();
                await $.wait(2000);
                if (signFlag) {
                    log(`\n==== 账号【${num}】已经签到了 ====\n`);
                } else {
                    await doSignIn();
                    await $.wait(2000);
                }
                log(`\n==== 全棉时代每日任务(新) ====\n`)
                await runActivityTasks();
                await $.wait(2000);
                log(`\n==== 全棉时代工厂任务 ====\n`)
                await factoryGame();
                await $.wait(5000);
                log(`\n==== 全棉时代农场任务 ====\n`)
                await farmGame();
                await $.wait(5000);
            }
            await SendMsg(msg);
        }
    }
})()
    .catch((e) => log(e))
    .finally(() => $.done())

/**
 * 获取code
 * @param timeout
 * @returns {Promise<unknown>}
 */
async function getCode() {
    try {
        const code = await getSingleCode(scriptAppId, wxid);
        log(`获取code:${code}`)
        return code;
    } catch (e) {
        log(`获取code异常，原因：${e}`)
        return "";
    }
}


async function doLogin(code, timeout = 2 * 1000) {
    let loginFlag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://nmp.pureh2b.com/api/wx/main/login',
            params: {code: code},
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/678/page-frame.html'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('token') && result.hasOwnProperty('member')) {
                    scriptToken = result.token;
                    scriptOpenId = result.openid;
                    scriptUnionID = result.unionID;
                    let availablePoint = result.member.availablePoint;
                    scriptPhone = result.member.phone;
                    loginFlag = true;
                    taskBeforeScore = availablePoint;
                    log(`${accountTips}全棉时代登入✅积分：${availablePoint}`);
                } else {
                    log(`${accountTips}全棉时代登入❌：【${result.message}】`)
                }

            } catch (e) {
                log(`${accountTips}全棉时代登入异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(loginFlag);
        });

    })
}

// ==================== 修复签到接口 ====================
async function signDetail() {
    let signFlag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: `https://nmp.pureh2b.com/api/new/member/sign/index?signId=${scriptSignId}`,
            headers: {
                'host': 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                'tag': 'v3.0',
                'token': scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                'code': scriptCode,
                'accept': '*/*',
                'user-agent': userAgent,
                'referer': 'https://servicewechat.com/wxdfcaa44b1aa891a7/1372/page-frame.html'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.signMember) {
                    let signDays = result.signMember.signDays || 0;
                    let signDateList = result.signMember.signDateList || [];
                    // 判断今天是否已签到
                    let today = new Date(new Date().getTime() + 8 * 60 * 60 * 1000)
                        .toISOString().slice(0, 10); // UTC+8 的今天日期
                    signFlag = signDateList.includes(today);
                    log(`${accountTips}签到天数【${signDays}】✅`, true);
                } else {
                    log(`${accountTips}签到详情❌：【${JSON.stringify(result)}】`, true);
                }
            } catch (e) {
                log(`${accountTips}签到详情异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`);
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(signFlag);
        });
    });
}

async function doSignIn() {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/new/member/sign/signIn',
            headers: {
                'host': 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                'tag': 'v3.0',
                'token': scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                'code': scriptCode,
                'accept': '*/*',
                'user-agent': userAgent,
                'referer': 'https://servicewechat.com/wxdfcaa44b1aa891a7/1372/page-frame.html'
            },
            data: { signType: 1, signInId: scriptSignId }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                // 新版接口返回数组，成功时数组长度>0
                if (Array.isArray(result) && result.length > 0) {
                    let point = result[0].rewardPoint || 0;
                    taskBeforeScore += point;  // 更新积分显示
                    addNotifyStr(`${accountTips}签到【积分 +${point}】✅`, true);
                } else if (Array.isArray(result) && result.length === 0) {
                    addNotifyStr(`${accountTips}签到【今日已签到】✅`, true);
                } else {
                    addNotifyStr(`${accountTips}签到❌：【${JSON.stringify(result)}】`, true);
                }
            } catch (e) {
                log(`${accountTips}签到异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`);
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve();
        });
    });
}
// ==================== 签到接口修复结束 ====================

function v3Headers(refererVer = '1376') {
    return {
        'host': 'nmp.pureh2b.com',
        'connection': 'keep-alive',
        'tag': 'v3.0',
        'token': scriptToken,
        'content-type': 'application/json;charset=UTF-8',
        'code': scriptCode,
        'accept': '*/*',
        'user-agent': userAgent,
        'referer': `https://servicewechat.com/${scriptAppId}/${refererVer}/page-frame.html`
    };
}

function parseSignIdFromInfo(info) {
    if (!info || typeof info !== 'string') return '';
    const m = info.match(/[?&]id=([^&]+)/i) || info.match(/(QD\d+)/i);
    return m ? decodeURIComponent(m[1]) : '';
}

function findSignIdInObject(obj) {
    if (!obj) return '';
    if (typeof obj === 'string') return parseSignIdFromInfo(obj);
    if (Array.isArray(obj)) {
        for (const item of obj) {
            const id = findSignIdInObject(item);
            if (id) return id;
        }
        return '';
    }
    if (typeof obj === 'object') {
        if (obj.redirectInfo && obj.redirectInfo.info) {
            const id = parseSignIdFromInfo(obj.redirectInfo.info);
            if (id) return id;
        }
        for (const k of Object.keys(obj)) {
            const id = findSignIdInObject(obj[k]);
            if (id) return id;
        }
    }
    return '';
}

async function fetchSignId(timeout = 5000) {
    const fallback = scriptSignId || 'QD26060001';
    const headers = v3Headers('1376');
    try {
        const catResp = await axios.request({
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/new/navigation/category/query',
            data: { pageNum: 1, pageSize: 10, venueType: 'MAIN', categoryId: '010002' },
            headers,
            timeout
        });
        const catData = catResp && catResp.data ? catResp.data : {};
        if (catData.code == 200 && catData.data) {
            let signId = findSignIdInObject(catData.data.componentList);
            if (signId) {
                log(`${accountTips}自动获取签到ID✅ ${signId}（首页组件）`);
                return signId;
            }
            let navId = '';
            try {
                const pageConfig = JSON.parse(catData.data.pageConfig || '{}');
                navId = pageConfig.topNavigationId || '';
            } catch (e) {}
            if (navId) {
                const navResp = await axios.request({
                    method: 'GET',
                    url: 'https://nmp.pureh2b.com/api/new/navigation/nav/query',
                    params: { navigationId: navId },
                    headers,
                    timeout
                });
                const navData = navResp && navResp.data ? navResp.data : {};
                if (navData.code == 200) {
                    signId = findSignIdInObject(navData.data);
                    if (signId) {
                        log(`${accountTips}自动获取签到ID✅ ${signId}（顶部导航）`);
                        return signId;
                    }
                }
            }
        } else {
            log(`${accountTips}自动获取签到ID❌ category/query：${JSON.stringify(catData)}`);
        }
    } catch (e) {
        log(`${accountTips}自动获取签到ID异常：${e.message || e}`);
    }
    log(`${accountTips}自动获取签到ID失败，使用默认：${fallback}`);
    return fallback;
}

// ==================== 新版活动任务(finish 即完成+发奖) ====================

function parseActivityTaskList(respData) {
    if (Array.isArray(respData)) return respData;
    if (respData && Array.isArray(respData.data)) return respData.data;
    if (respData && respData.code == 200 && Array.isArray(respData.data)) return respData.data;
    return [];
}

async function fetchActivityTaskList(type = 1) {
    try {
        const resp = await axios.request({
            method: 'GET',
            url: 'https://nmp.pureh2b.com/api/new/member/sign/activityTask/list',
            params: { activityId: scriptSignId, type },
            headers: v3Headers('1376'),
            timeout: 5000
        });
        return parseActivityTaskList(resp.data);
    } catch (e) {
        log(`${accountTips}获取活动任务type=${type}异常：${e.message || e}`);
        return [];
    }
}

async function taskListNew() {
    const type1 = await fetchActivityTaskList(1);
    const type2 = await fetchActivityTaskList(2);
    const all = type1.concat(type2);
    log(`${accountTips}签到活动任务✅ 日常${type1.length}个 其他${type2.length}个 activityId=${scriptSignId}`, true);
    return all;
}

function isActivityTaskDone(task) {
    const count = parseInt(task.count || 0);
    const limit = parseInt(task.giveRewardNum || task.limitTotalCount || 1);
    return count >= limit && limit > 0;
}

function parseActivityTaskResult(result) {
    if (result == null) return { ok: false, msg: 'empty response' };
    if (Array.isArray(result)) return { ok: true, data: result, raw: result };
    if (result.code == 200 || result.success === true) {
        return { ok: true, data: result.data, msg: result.message || result.msg, raw: result };
    }
    if (result.taskId || result.taskName || result.id) {
        const finish = parseInt(result.finish);
        const status = parseInt(result.status);
        const ok = finish === 1 || status >= 1;
        const reward = result.reward ? `+${result.reward}积分` : '';
        return {
            ok,
            data: result,
            msg: `${result.taskName || result.taskId || ''} finish=${result.finish} status=${result.status}${reward ? ' ' + reward : ''}`,
            raw: result
        };
    }
    if (result.message && /已|成功/.test(result.message)) return { ok: true, msg: result.message, raw: result };
    return { ok: false, msg: result.message || result.msg || JSON.stringify(result), raw: result };
}

async function activityTaskFinish(taskId) {
    try {
        const resp = await axios.request({
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/new/member/sign/activityTask/finish',
            headers: v3Headers('1376'),
            data: { activityId: scriptSignId, taskId },
            timeout: 5000
        });
        const res = parseActivityTaskResult(resp.data);
        if (res.ok) {
            log(`${accountTips}完成任务[${taskId}]✅ ${res.msg || ''}`);
            if (res.data && res.data.reward) addNotifyStr(`${accountTips}活动任务[${taskId}]完成✅ +${res.data.reward}积分`, true);
        } else log(`${accountTips}完成任务[${taskId}]❌ ${res.msg}`);
        return res;
    } catch (e) {
        log(`${accountTips}完成任务[${taskId}]❌ ${e.message || e}`);
        return { ok: false, msg: e.message || String(e) };
    }
}

async function runActivityTasks() {
    const taskData = await taskListNew();
    if (!taskData.length) return;
    for (const task of taskData) {
        const taskId = task.taskId;
        const taskType = String(task.taskType || '');
        const name = task.name || taskId;
        const reward = task.reward || '';
        if (!taskId) continue;
        if (isActivityTaskDone(task)) {
            log(`${accountTips}任务【${name}】已完成(${task.count}/${task.giveRewardNum})`);
            continue;
        }
        if (taskType === '4' || taskType === '7') {
            log(`${accountTips}任务【${name}】类型${taskType}已排除，跳过`);
            continue;
        }
        log(`${accountTips}准备做任务【${name}】类型${taskType} +${reward}积分 taskId=${taskId}`);
        const waitSec = parseInt(task.standingTime || (taskType === '3' ? 30 : 3));
        if (waitSec > 0) await $.wait(waitSec * 1000);
        const fin = await activityTaskFinish(taskId);
        if (!fin.ok) continue;
        await $.wait(1500);
    }
}

async function taskList() {
    let taskData = [];
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://nmp.pureh2b.com/api/member/sign/task/get/list',
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/678/page-frame.html'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.data && result.data.taskList) {
                        taskData = result.data.taskList;
                        let todayNoneScoreNum = result.data.todayNoneScoreNum;
                        let todayScoreNum = result.data.todayScoreNum;
                        log(`${accountTips}全棉时代任务【${result.message}】今日可得积分【${todayNoneScoreNum}】已获取【${todayScoreNum}】✅`, true)
                    } else {
                        taskData = [];
                        log(`${accountTips}全棉时代任务提示：返回 data 为空，跳过任务列表`, true)
                    }
                } else {
                    log(`${accountTips}全棉时代任务❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}全棉时代任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(taskData);
        });

    })

}

async function doStart(taskId) {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/member/sign/task/start',
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/675/page-frame.html'
            },
            data: {taskId: taskId}
        };

        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    log(`${accountTips}[${result.data.result}]✅`, true)
                } else {
                    log(`${accountTips}开始任务❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}开始任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function doFinish(taskId) {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/member/sign/task/finish',
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/675/page-frame.html'
            },
            data: {taskId: taskId}
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    log(`${accountTips}[${result.data.result}]✅`, true)
                } else {
                    log(`${accountTips}完成任务❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}完成任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function doReward(taskId) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/member/sign/task/give/reward',
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/675/page-frame.html'
            },
            data: {taskId: taskId}
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}[${result.data.result}]✅`, true)
                } else {
                    log(`${accountTips}领取奖励❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}领取奖励异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function doView(id) {
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://nmp.pureh2b.com/api/navigation/page/getColumnContent',
            params: {id: id, pageNum: '0'},
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/json;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/675/page-frame.html'
            }
        };

        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}访问页面[${result.pageName}]✅`, true)
                } else {
                    log(`${accountTips}访问页面❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}访问页面异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

//========================================棉花农场===========================================//
async function farmIndex() {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://sg01.purcotton.com/api/index',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.hasOwnProperty('data') && result.data.hasOwnProperty('tree') && result.data.tree.hasOwnProperty('is_finish')) {
                        flag = true;
                        let level = result.data.level;
                        let place = result.data.place;
                        let user = result.data.user;
                        let tree = result.data.tree;
                        factoryInfo['tree_id'] = tree.id;
                        factoryInfo['water'] = user.water;
                        factoryInfo['balance'] = user.balance;
                        factoryInfo['get_water_date'] = result.data.user_info.get_water_date;
                        log(`当前农场金币【${user.balance}】水滴【${user.water}】`);
                        if (tree.is_finish == 1) {
                            addNotifyStr(`全棉时代农场已经完成！`, true);
                            await farmReplantTask();
                        }
                    } else {
                        log(`全棉时代农场游戏未初始化，请先手动完成`);
                    }
                } else {
                    log(`${accountTips}全棉时代农场首页❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}全棉时代农场首页异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function farmPrizeHomeList() {
    let list = [];
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://sg01.purcotton.com/api/prize/home',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    list = (result.data && result.data.list) ? result.data.list : [];
                    log(`${accountTips}获取重新种植奖品列表✅ 数量=${list.length}`, true)
                } else {
                    log(`${accountTips}获取重新种植奖品列表❌：【${result && (result.msg || result.message) ? (result.msg || result.message) : ''}】`, true)
                }
            } catch (e) {
                log(`${accountTips}获取重新种植奖品列表异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(list);
        });
    })
}

async function farmGainTree(prizeId) {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/gain-tree',
            headers: {
                'host': 'sg01.purcotton.com',
                'content-type': 'application/json;charset=utf-8',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: { prize_id: prizeId }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    log(`${accountTips}重新种植✅ prize_id=${prizeId}`, true)
                } else {
                    log(`${accountTips}重新种植❌：【${result && (result.msg || result.message) ? (result.msg || result.message) : ''}】`, true)
                }
            } catch (e) {
                log(`${accountTips}重新种植异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(flag);
        });
    })
}

async function farmReplantTask() {
    try {
        let list = await farmPrizeHomeList();
        if (!list || list.length == 0) {
            addNotifyStr(`农场重新种植失败：奖品列表为空`, true);
            return false;
        }
        let idx = randomInt(0, list.length - 1);
        let item = list[idx] || {};
        let prizeId = parseInt(item.id);
        let title = item.title || '';
        if (!prizeId) {
            addNotifyStr(`农场重新种植失败：未取到 prize_id`, true);
            return false;
        }
        log(`${accountTips}随机选择重新种植：${title} prize_id=${prizeId}`);
        let ok = await farmGainTree(prizeId);
        if (ok) {
            addNotifyStr(`农场已重新种植✅：${title}（${prizeId}）`, true);
        } else {
            addNotifyStr(`农场重新种植失败❌：${title}（${prizeId}）`, true);
        }
        return ok;
    } catch (e) {
        addNotifyStr(`农场重新种植异常：${e && e.message ? e.message : e}`, true);
        return false;
    }
}

async function farmLogin() {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/login',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: {invite_source: 'normal', channel: 'authority_banner'}
        };

        axios.request(options).then(function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.hasOwnProperty('data') && result.data.hasOwnProperty('current_people')) {
                        flag = true;
                        log(`全棉时代农场登录成功！游戏人数：${result.data.current_people}`);
                    } else {
                        log(`全棉时代农场登录异常${JSON.stringify(response.data)}`);
                    }
                } else {
                    log(`${accountTips}全棉时代农场登录❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}全棉时代农场登录异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });
    })
}

async function farmTaskList() {
    let taskData = [];
    return new Promise((resolve) => {
        var options = {
            method: 'GET',
            url: 'https://sg01.purcotton.com/api/task/list',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    let task_user_info = result.data.task_user_info;
                    taskData = result.data.tasks;
                    for (let i in taskData) {
                        let taskId = parseInt(taskData[i]["id"]);
                        for (let j in task_user_info) {
                            if (taskId == parseInt(task_user_info[j]["task_id"])) {
                                taskData[i]['receive_num'] = task_user_info[j]['receive_num'];
                                taskData[i]['complete_num'] = task_user_info[j]['complete_num'];
                                taskData[i]['complete_date'] = task_user_info[j]['complete_date'];
                                taskData[i]['receive_date'] = task_user_info[j]['receive_date'];
                                if (task_user_info[j]['task_user_id']) {
                                    taskData[i]['task_user_id'] = task_user_info[j]['task_user_id'];
                                }
                            }
                        }
                    }
                    log(`${accountTips}获取农场任务✅`, true)
                } else {
                    log(`${accountTips}获取农场任务❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}获取农场任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(taskData);
        });

    })

}

// 生成签名
function generateSign(params) {
    // 简单的签名生成算法，实际可能需要根据服务器要求调整
    const timestamp = params.timestamp;
    const tid = params.tid;
    // 这里使用简单的字符串拼接，实际可能需要更复杂的算法
    const signStr = `tid=${tid}&timestamp=${timestamp}`;
    // 使用MD5生成签名，需要确保环境中有crypto模块
    try {
        const crypto = require('crypto');
        return crypto.createHash('md5').update(signStr).digest('hex').toUpperCase();
    } catch (e) {
        // 如果没有crypto模块，返回一个基于时间戳的简单签名
        return (timestamp + tid).split('').reverse().join('');
    }
}

function generateSignV2(params) {
    // 签名算法来自 H5 JS 源码：
    // qs.stringify(排序后参数，过滤空值) + 盐值 → MD5大写
    const SALT = 'z0hQTvC21f8SXlLbL9Hv';
    const src = (params && typeof params === 'object') ? params : {};
    const keys = Object.keys(src)
        .filter(k => k !== 'sign' && src[k] !== undefined && src[k] !== null && src[k] !== '')
        .sort();
    const signStr = keys.map(k => `${k}=${src[k]}`).join('&') + SALT;
    try {
        const crypto = require('crypto');
        return crypto.createHash('md5').update(signStr).digest('hex').toUpperCase();
    } catch (e) {
        return signStr;
    }
}

async function farmSign(taskId, taskType, taskUserId) {
    return new Promise((resolve) => {
        let timestamp = Date.now();
        let sign = generateSignV2({ tid: taskId, timestamp: timestamp });

        var options = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/task/complete-task',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'content-type': 'application/json;charset=utf-8',
                'origin': 'https://sg01.purcotton.com',
                'referer': `https://sg01.purcotton.com/h5/?token=${encodeURIComponent(scriptToken)}&code=${scriptCode}&app_id=${scriptAppId}`
            },
            data: {
                tid: taskId,
                timestamp: timestamp,
                sign: sign
            } // 使用正确的参数格式
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取❌：【${result.msg}】`, true)
                }
            } catch (e) {
                log(`${accountTips}任务完成异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function receiveFarmTaskWater(taskId, taskType, taskUserId) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/task/receive-task-water',
            headers: {
                'host': 'sg01.purcotton.com',
                'content-type': 'application/json;charset=utf-8',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: { tid: taskId } // 使用正确的参数格式
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取奖励成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取奖励❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}任务领取奖励异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function getQuestionList() {
    let question = [];
    return new Promise((resolve) => {
        var options = {
            method: "get",
            url: 'https://sg01.purcotton.com/api/answer',
            headers: {
                "Host": "sg01.purcotton.com",
                "accept": "application/json, text/plain, */*",
                "code": scriptCode,
                "app-id": scriptAppId,
                "token": scriptToken,
                "x-requested-with": "com.tencent.mm",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://sg01.purcotton.com/h5/answer",
                "accept-encoding": "gzip, deflate",
            }
        };

        axios.request(options).then(async function (response) {
            try {
                if (debug) {
                    log(`\n\n【debug】=============== 这是 返回data ============== `);
                    log(JSON.stringify(response.data));
                }
                if (response.data.code == '200') {
                    const data = response.data.data;
                    const raw = data.exams || data.list || data.questions || [];
                    const options_map = ['A', 'B', 'C', 'D'];
                    question = Array.isArray(raw) ? raw.map(item => {
                        const id = item.id || item.exam_id || item.examId;
                        // answer 字段为空时，根据 latin（选项数）随机选一个
                        const latin = parseInt(item.latin) || 2;
                        const validOptions = options_map.slice(0, latin);
                        const answer = item.answer || item.right_answer || item.rightAnswer
                            || validOptions[Math.floor(Math.random() * validOptions.length)];
                        return { id, answer };
                    }) : [];
                } else {
                    log(response.data.msg)
                }
            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve(question)
        })
    })
}

async function answerQuestion(item, taskId) {
    const examId = item.id || item.exam_id || item.examId;
    const answer = item.answer || item.right_answer || item.rightAnswer || 'A';

    if (!examId) {
        log(`答题参数异常，跳过：${JSON.stringify(item)}`);
        return;
    }

    return new Promise((resolve) => {
        let timestamp = Date.now();
        let sign = generateSignV2({ answer: answer, exam_id: examId, tid: taskId, timestamp: timestamp });
        var options = {
            method: "post",
            url: 'https://sg01.purcotton.com/api/answer/complete',
            headers: {
                "code": scriptCode,
                "app-id": scriptAppId,
                "token": scriptToken,
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://sg01.purcotton.com",
                "x-requested-with": "com.tencent.mm",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://sg01.purcotton.com/h5/answer",
                "accept-encoding": "gzip, deflate",
            },
            data: { answer: answer, exam_id: examId, tid: taskId, timestamp: timestamp, sign: sign }
        };
        if (debug) {
            log(`\n【debug】=============== 这是  请求 url =============== `);
            log(JSON.stringify(options));
        }
        axios.request(options).then(async function (response) {
            try {
                if (debug) {
                    log(`\n\n【debug】=============== 这是 返回data ============== `);
                    log(JSON.stringify(response.data));
                }
                if (response.data.code == '200') {
                    const d = response.data.data;
                    log(`答题成功，获得${d.get_water}水滴`);
                    // 有宝箱时开箱
                    if (d.box_id && d.box_id > 0) {
                        await openAnswerBox(d.box_id);
                    }
                } else {
                    log(response.data.msg)
                }
            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve()
        })
    })
}

async function openAnswerBox(boxId) {
    return new Promise((resolve) => {
        var options = {
            method: "post",
            url: 'https://sg01.purcotton.com/api/answer/open-box',
            headers: {
                "code": scriptCode,
                "app-id": scriptAppId,
                "token": scriptToken,
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://sg01.purcotton.com",
                "x-requested-with": "com.tencent.mm",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://sg01.purcotton.com/h5/answer",
                "accept-encoding": "gzip, deflate",
            },
            data: { box_id: boxId }
        };
        axios.request(options).then(async function (response) {
            try {
                if (response.data.code == '200') {
                    const d = response.data.data;
                    log(`${accountTips}开箱成功，获得${d.get_water}水滴，当前剩余：${d.sy_water}✅`);
                } else {
                    log(`${accountTips}开箱失败：【${response.data.msg}】`);
                }
            } catch (e) {
                log(`开箱异常：${e}`);
            }
        }).catch(function (error) {
            console.error(error);
        }).then(() => resolve());
    })
}

// 获取阳光
async function getSunshine() {
    return new Promise((resolve) => {
        var options = {
            method: "post",
            url: 'https://sg01.purcotton.com/api/get-sunshine',
            headers: {
                "code": scriptCode,
                "app-id": scriptAppId,
                "token": scriptToken,
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://sg01.purcotton.com",
                "x-requested-with": "com.tencent.mm",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
            },
            data: {time: Date.now()}

        };
        if (debug) {
            log(`\n【debug】=============== 这是  请求 url =============== `);
            log(JSON.stringify(options));
        }
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}获取阳光成功，获得 ${result.data.get_sunshine} 阳光，当前剩余 ${result.data.sy_sunshine} ✅`, true)
                } else {
                    log(`${accountTips}获取阳光失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve()
        })
    })

}

// 使用阳光
async function useSunshine() {
    // 阳光加速只在 7:00-19:00 之间可用
    const now = new Date(new Date().getTime() + 8 * 60 * 60 * 1000); // UTC+8
    const hour = now.getUTCHours();
    if (hour < 7 || hour >= 19) {
        log(`${accountTips}当前时间不在阳光使用时段(7:00-19:00)，跳过`, true);
        return;
    }

    return new Promise((resolve) => {
        var getSunshineOptions = {
            method: "get",
            url: 'https://sg01.purcotton.com/api/index',
            headers: {
                "CODE": scriptCode,
                "APP-ID": scriptAppId,
                "TOKEN": scriptToken,
                "accept": "application/json, text/plain, */*",
            }
        };

        axios.request(getSunshineOptions).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    let currentSunshine = result.data.user.sunshine || 0;
                    let speedCount = (((result.data || {}).user_info || {}).sy_sunshine_speed_cnt || 0);
                    log(`${accountTips}当前阳光数量：${currentSunshine}`, true);

                    if (currentSunshine >= 100 && speedCount > 0) {
                        // 新接口：/api/sunshine-task/complete-task，请求体 {"tid":1}
                        var useSunshineOptions = {
                            method: "post",
                            url: 'https://sg01.purcotton.com/api/sunshine-task/complete-task',
                            headers: {
                                "CODE": scriptCode,
                                "APP-ID": scriptAppId,
                                "TOKEN": scriptToken,
                                "content-type": "application/json;charset=UTF-8",
                                "origin": "https://sg01.purcotton.com",
                                "accept": "application/json, text/plain, */*",
                            },
                            data: { tid: 1 }
                        };

                        axios.request(useSunshineOptions).then(async function (response) {
                            try {
                                let result = response.data;
                                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                                    log(`${accountTips}使用阳光成功，剩余 ${result.data.sy_sunshine} 阳光，加速次数剩余 ${result.data.sy_sunshine_speed_cnt} ✅`, true);
                                } else {
                                    log(`${accountTips}使用阳光失败❌：【${result.msg}】`, true);
                                }
                            } catch (e) {
                                log(`异常：${e}，原因：${e.msg} `);
                            }
                        }).catch(function (error) {
                            console.error(error);
                        }).then(res => {
                            resolve();
                        });
                    } else if (currentSunshine >= 100 && speedCount <= 0) {
                        log(`${accountTips}今日阳光加速次数已用完，跳过使用阳光`, true);
                        resolve();
                    } else {
                        log(`${accountTips}阳光不足100，跳过使用阳光`, true);
                        resolve();
                    }
                } else {
                    log(`${accountTips}获取阳光数量失败❌：【${result.msg}】`, true);
                    resolve();
                }
            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `);
                resolve();
            }
        }).catch(function (error) {
            console.error(error);
            resolve();
        });
    });
}

async function plant() {
    return new Promise((resolve) => {
        var options = {
            method: "post",
            url: 'https://sg01.purcotton.com/api/watering',
            headers: {
                "code": scriptCode,
                "app-id": scriptAppId,
                "token": scriptToken,
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://sg01.purcotton.com",
                "x-requested-with": "com.tencent.mm",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
            },
            data: {tree_user_id: factoryInfo.tree_id, water_cnt: 1}

        };
        if (debug) {
            log(`\n【debug】=============== 这是  请求 url =============== `);
            log(JSON.stringify(options));
        }
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}农场浇水成功,还需要浇${result.data.tree_user.drop_cnt}次升级✅`, true)
                } else {
                    log(`${accountTips}农场浇水失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve()
        })
    })

}

async function getTodayWater() {
    return new Promise((resolve) => {
        var options = {
            method: "POST",
            url: 'https://sg01.purcotton.com/api/get-today-water',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: {tree_user_id: factoryInfo.tree_id, water_cnt: 1}

        };
        if (debug) {
            log(`\n【debug】=============== 这是  请求 url =============== `);
            log(JSON.stringify(options));
        }
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取奖励成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取奖励❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve()
        })
    })

}

async function farmCompleteFactory(taskId, taskType, taskUserId) {
    let flag = false;
    return new Promise((resolve) => {
        const payload = { tid: taskId, relate_id: 0, timestamp: Date.now() };
        payload.sign = generateSignV2(payload);
        const optionsFixed = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/task/complete-manual-task',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive',
                'content-type': 'application/json;charset=utf-8'
            },
            data: payload
        };
        axios.request(optionsFixed).then(async function (response) {
            try {
                let result = response.data;
                if (result && parseInt(result.code) === 200) {
                    flag = true;
                }
            } catch (e) {
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(flag);
        });
        return;

        let timestamp = Date.now();
        let sign = generateSignV2({ tid: taskId, relate_id: 0, timestamp: timestamp });
        var options = {
            method: 'POST',
            url: 'https://sg01.purcotton.com/api/task/complete-manual-task',
            headers: {
                'host': 'sg01.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive',
                'content-type': 'application/json;charset=utf-8'
            },
            data: { tid: taskId, timestamp: timestamp, sign: sign } // 使用正确的参数格式
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true
                    log(`${accountTips}访问农场任务完成✅`, true)
                } else {
                    log(`${accountTips}访问农场任务❌：【${result.msg}】`, true)
                }
            } catch (e) {
                log(`${accountTips}访问农场任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function farmGame() {
    let currDate = time('yyyy-MM-dd');
    let loginFlag = await farmLogin();
    await $.wait(2000);
    if (!loginFlag) {
        log(`${accountTips}[农场登录失败]✅`);
        return false;
    }
    let farmFlag = await farmIndex();
    await $.wait(2000);
    if (!farmFlag) {
        return false;
    }
    if (factoryInfo['get_water_date'] != currDate) {
        log(`准备去领取今日水滴`)
        await getTodayWater();
        await $.wait(2000);
    } else {
        log(`今日水滴已经领取`)
    }
    let taskData = await farmTaskList();
    await $.wait(2000);
    if (taskData.length > 0) {
        for (let i in taskData) {
            let id = parseInt(taskData[i]["id"]);
            let day_reward_num = parseInt(taskData[i]["day_reward_num"]);
            let title = taskData[i]["title"];
            let complete_num = 0;
            let receive_num = 0;
            let complete_date = '';
            let receive_date = '';
            if (taskData[i].hasOwnProperty('complete_num')) {
                complete_num = taskData[i]['complete_num'];
            }
            if (taskData[i].hasOwnProperty('receive_num')) {
                receive_num = taskData[i]['receive_num'];
            }
            if (taskData[i].hasOwnProperty('complete_date')) {
                complete_date = taskData[i]['complete_date'];
            }
            if (taskData[i].hasOwnProperty('receive_date')) {
                receive_date = taskData[i]['receive_date'];
            }

            let calCompleteNum = (complete_date == currDate) ? (day_reward_num - complete_num) : day_reward_num;
            let calReceiveNum = (receive_date == currDate) ? (complete_num - receive_num) : complete_num;
            switch (id) {
                case 1:
                    if (complete_date == currDate) {
                        log(`${title}已经完成了`)
                    } else {
                        log(`准备去完成[${title}]`)
                        await farmSign(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                        await $.wait(2000);
                    }
                    break;
                case 4:
                    log(`准备去完成[${title}]`)
                    await farmSign(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                    await $.wait(2000);
                    break;
                case 14:
                    if (complete_date == currDate) {
                        log(`${title}已经完成了`)
                    } else {
                        let questions = await getQuestionList();
                        for (let j = 0; j < questions.length; j++) {
                            log(`正在执行第${(j + 1)}次每日答题`)
                            await answerQuestion(questions[j], id) // 传递taskId参数
                            await $.wait(1000)
                        }
                    }
                    break;
                case 16:
                case 6:
                case 13:
                case 10:
                    let action = '';
                    if (id == 16) {
                        action = 'browse_community'
                    } else if (id == 6) {
                        action = 'browse_venue'
                    } else if (id == 13) {
                        action = 'browse_new_user_zone'
                    } else if (id == 10) {
                        action = 'subscibe'
                    }
                    if (complete_date == currDate) {
                        for (let k = 1; k <= calReceiveNum; k++) {
                            log(`开始第${k}次去领取任务奖励[${title}]`);
                            await receiveFarmTaskWater(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                            await $.wait(1500);
                        }
                    }
                    for (let j = 1; j <= calCompleteNum; j++) {
                        log(`开始第${j}次任务[${title}]`)
                        let taskFlag = await completeTask(action, 'guoyuan');
                        await $.wait(1500);
                        if (taskFlag) {
                            await receiveFarmTaskWater(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                            await $.wait(1500);
                        }
                    }
                    break;
                case 15:
                    if (calCompleteNum > 0) {
                        let taskFlag = await farmCompleteFactory(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                        await $.wait(1500);
                        if (taskFlag) {
                            await receiveFarmTaskWater(id, taskData[i]["type"], taskData[i]["task_user_id"]);
                            await $.wait(1500);
                        }
                    }
                    break;
            }
        }
    }
    await farmIndex();
    await $.wait(2000);

    // 获取阳光
    await getSunshine();
    await $.wait(2000);

    // 使用阳光购买加速
    await useSunshine();
    await $.wait(2000);

    if (factoryInfo['water'] >= 10) {
        for (let i = 10; i <= factoryInfo['water']; i += 10) {
            await plant();
            await $.wait(2000);
        }
    }
}


//=========================================工厂游戏=============================================//

async function factoryGame() {
    // let articleList = await getArticleList(129);
    // if(articleList.length > 0){
    //     let articleId = articleList[randomInt(0,articleList.length-1)]['id'];
    //     log(articleId);
    // }
    // log(articleId);return
    let currDate = time('yyyy-MM-dd');
    let loginFlag = await factoryLogin();
    await $.wait(2000);
    if (!loginFlag) {
        log(`${accountTips}[工厂登录失败]✅`);
        return false;
    }
    factoryInfo['finished_reopen_failed'] = false;
    let factoryFlag = await factoryIndex();
    await $.wait(2000);
    if (!factoryFlag) {
        return false;
    }
    if (factoryInfo['finished_reopen_failed']) {
        addNotifyStr(`工厂复开失败，本账号跳过工厂后续任务，避免对已完成轮次重复浇水`, true);
        return false;
    }
    if (factoryInfo['get_water_date'] != currDate) {
        log(`准备去领取今日水滴`)
        await getTodayFactoryWater();
        await $.wait(2000);
    } else {
        log(`今日水滴已经领取`)
    }
    let taskData = await factoryTaskList();
    await $.wait(2000);
    if (taskData.length > 0) {
        for (let i in taskData) {
            let id = parseInt(taskData[i]["id"]);
            let day_reward_num = parseInt(taskData[i]["day_reward_num"]);
            let title = taskData[i]["title"];
            let complete_num = 0;
            let receive_num = 0;
            let complete_date = '';
            let receive_date = '';
            if (taskData[i].hasOwnProperty('complete_num')) {
                complete_num = taskData[i]['complete_num'];
            }
            if (taskData[i].hasOwnProperty('receive_num')) {
                receive_num = taskData[i]['receive_num'];
            }
            if (taskData[i].hasOwnProperty('complete_date')) {
                complete_date = taskData[i]['complete_date'];
            }
            if (taskData[i].hasOwnProperty('receive_date')) {
                receive_date = taskData[i]['receive_date'];
            }

            let calCompleteNum = (complete_date == currDate) ? (day_reward_num - complete_num) : day_reward_num;
            let calReceiveNum = (receive_date == currDate) ? (complete_num - receive_num) : complete_num;
            switch (id) {
                case 12:
                    if (complete_date == currDate) {
                        log(`${title}已经完成了`)
                    } else {
                        await completeSanTask(id);
                        await $.wait(2000);
                    }
                    break;
                case 3:
                    await completeSanTask(id);
                    break;
                case 13:
                case 14:
                    if (complete_date == currDate) {
                        for (let k = 1; k <= calReceiveNum; k++) {
                            log(`开始第${k}次去领取任务奖励[${title}]`);
                            await receiveTaskWater(id);
                            await $.wait(1500);
                        }
                    } else {
                        let gameId = await factoryGameStart(id);
                        if (gameId != '') {
                            await $.wait(15000);
                            let body = {"is_complete": "1", "gid": gameId};
                            await factoryGameEnd(body);
                            await $.wait(1500);
                            await receiveTaskWater(id);
                            await $.wait(1500);
                        }
                    }
                    break;
                case 9:
                case 5:
                case 8:
                    let action = '';
                    if (id == 9) {
                        action = 'browse_new_user_zone'
                    } else if (id == 5) {
                        action = 'browse_venue'
                    } else if (id == 8) {
                        action = 'subscibe'
                    }
                    if (complete_date == currDate) {
                        for (let k = 1; k <= calReceiveNum; k++) {
                            log(`开始第${k}次去领取任务奖励[${title}]`);
                            await receiveTaskWater(id);
                            await $.wait(1500);
                        }
                    }
                    for (let j = 1; j <= calCompleteNum; j++) {
                        log(`开始第${j}次任务[${title}]`)
                        let taskFlag = await completeTask(action, 'factory');
                        await $.wait(1500);
                        if (taskFlag) {
                            await receiveTaskWater(id);
                            await $.wait(1500);
                        }
                    }
                    break;
                case 15:
                    if (complete_date == currDate) {
                        for (let k = 1; k <= calReceiveNum; k++) {
                            log(`开始第${k}次去领取任务奖励[${title}]`);
                            await receiveTaskWater(id);
                            await $.wait(1500);
                        }
                    } else {
                        let gameId = await factoryGameStart(id);
                        await $.wait(1500);
                        if (gameId != '') {
                            let winIds = await answerInfo();
                            if (winIds.length > 0) {
                                await $.wait(15000);
                                let body = {
                                    "is_complete": 1,
                                    "gid": gameId,
                                    "win_exam_ids": winIds,
                                    "lose_exam_ids": []
                                };
                                await factoryGameEnd(body);
                                await $.wait(1500);
                                await receiveTaskWater(id);
                                await $.wait(1500);
                            }
                        }
                    }
                    break;

            }
        }
    }
    await factoryIndex();
    await $.wait(2000);
    if (factoryInfo['water'] >= 10) {
        for (let i = 10; i <= factoryInfo['water']; i += 10) {
            let gameFlag = await watering();
            await $.wait(2000);
            if (gameFlag) {
                let factoryGameId = await factoryGameBegin();
                await $.wait(15000);
                if (factoryGameId != '') {
                    let body = {
                        "is_complete": 1,
                        "gid": factoryGameId,
                        "tree_user_id": factoryInfo.tree_id,
                    };
                    await factoryGameOver(body);
                    await $.wait(2000);
                }
            }
        }
    }

}

async function getTodayFactoryWater() {
    return new Promise((resolve) => {
        var options = {
            method: "POST",
            url: 'https://cottonfactory.purcotton.com/api/get-today-water',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },

        };
        if (debug) {
            log(`\n【debug】=============== 这是  请求 url =============== `);
            log(JSON.stringify(options));
        }
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取奖励成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取奖励❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`异常：${e}，原因：${e.msg} `)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            resolve()
        })
    })

}

async function factoryLogin() {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/login',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };

        axios.request(options).then(function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.hasOwnProperty('data') && result.data.hasOwnProperty('current_people')) {
                        flag = true;
                        log(`全棉时代工厂登录成功！游戏人数：${result.data.current_people}`);
                    } else {
                        log(`全棉时代工厂登录异常${JSON.stringify(response.data)}`);
                    }
                } else {
                    log(`${accountTips}全棉时代工厂登录❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}全棉时代工厂登录异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });
    })
}

async function factoryIndex() {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/index',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'Content-Length': '0',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.hasOwnProperty('data') && result.data.hasOwnProperty('tree') && result.data.tree.hasOwnProperty('is_finish')) {
                        flag = true;
                        let level = result.data.level;
                        let place = result.data.place;
                        let user = result.data.user;
                        let tree = result.data.tree;
                        factoryInfo['tree_id'] = tree.id;
                        factoryInfo['water'] = user.water;
                        factoryInfo['balance'] = user.balance;
                        factoryInfo['receive_finished_reward'] = tree.receive_finished_reward;
                        factoryInfo['show_qr_code'] = tree.show_qr_code;
                        log(`当前工厂等级：${level}，金币【${user.balance}】`);
                        if (tree.is_finish == 1) {
                            addNotifyStr(`全棉时代工厂已经完成！`, true);
                            if (parseInt(tree.receive_finished_reward || 0) === 0) {
                                await factoryReceiveFinishedReward(tree.id);
                                await $.wait(1500);
                            } else {
                                log(`${accountTips}工厂完成奖励已领取，准备重新开启`, true);
                            }
                            let reopenOk = await factoryReopenTask();
                            await factoryIndexResetInfo();
                            if (!reopenOk) {
                                factoryInfo['finished_reopen_failed'] = true;
                            }
                        }
                    } else {
                        log(`全棉时代工厂游戏未初始化，请先手动完成`);
                    }
                } else {
                    log(`${accountTips}全棉时代工厂首页❌：【${result.message}】`, true)
                }

            } catch (e) {
                log(`${accountTips}全棉时代工厂首页异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function factoryIndexResetInfo() {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/index',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'Content-Length': '0',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    if (result.hasOwnProperty('data') && result.data.hasOwnProperty('tree') && result.data.hasOwnProperty('user')) {
                        let user = result.data.user;
                        let tree = result.data.tree;
                        factoryInfo['tree_id'] = tree.id;
                        factoryInfo['water'] = user.water;
                        factoryInfo['balance'] = user.balance;
                        log(`${accountTips}工厂信息已刷新✅ tree_id=${tree.id} water=${user.water} balance=${user.balance}`, true)
                        resolve(true);
                        return;
                    }
                }
                log(`${accountTips}工厂信息刷新失败❌`, true)
            } catch (e) {
                log(`${accountTips}工厂信息刷新异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
            resolve(false);
        }).catch(function (error) {
            console.error(error.message);
            resolve(false);
        });
    })
}

async function factoryReceiveFinishedReward(treeUserId) {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/receive_finished_reward',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                Origin: 'https://cottonfactory.purcotton.com',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive',
                'content-type': 'application/json;charset=UTF-8'
            },
            data: {tree_user_id: treeUserId || factoryInfo.tree_id}
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    let d = result.data || {};
                    let reward = d.reward_value || d.reward || d.get_balance || '';
                    let syBalance = d.sy_balance || d.balance || '';
                    log(`${accountTips}工厂完成奖励领取✅${reward !== '' ? `，奖励${reward}棉棉币` : ''}${syBalance !== '' ? `，当前金币${syBalance}` : ''}`, true)
                } else {
                    log(`${accountTips}工厂完成奖励领取❌：【${result && (result.msg || result.message) ? (result.msg || result.message) : ''}】`, true)
                }
            } catch (e) {
                log(`${accountTips}工厂完成奖励领取异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(flag);
        });
    })
}

async function factoryGainTree() {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/gain-tree',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                Origin: 'https://cottonfactory.purcotton.com',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'Content-Length': '0',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result && result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    log(`${accountTips}工厂重新开启✅`, true)
                } else {
                    log(`${accountTips}工厂重新开启❌：【${result && (result.msg || result.message) ? (result.msg || result.message) : ''}】`, true)
                }
            } catch (e) {
                log(`${accountTips}工厂重新开启异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            resolve(flag);
        });
    })
}

async function factoryReopenTask() {
    try {
        let ok = await factoryGainTree();
        if (ok) {
            addNotifyStr(`工厂已重新开启✅`, true);
        } else {
            addNotifyStr(`工厂重新开启失败❌`, true);
        }
        return ok;
    } catch (e) {
        addNotifyStr(`工厂重新开启异常：${e && e.message ? e.message : e}`, true);
        return false;
    }
}

async function watering() {
    let gameFlag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/watering',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'content-type': 'application/json;charset=utf-8',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: {tree_user_id: factoryInfo.tree_id, water_cnt: 1}
        };


        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}工厂浇水成功,还需要浇${result.data.tree_user.drop_cnt}次升级✅`, true)
                } else {
                    if (result.msg == '需完成才能游戏才能继续加棉力') {
                        gameFlag = true;
                    }
                    log(`${accountTips}工厂浇水失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}工厂浇水异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(gameFlag);
        });

    })

}

async function factoryGameBegin() {
    let gameId = '';
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/game/begin',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                Accept: '*/*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'accept-encoding': 'gzip, deflate, br',
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'connection': 'keep-alive',
                'Content-Type': 'application/json'
            },
            data: {tree_user_id: factoryInfo.tree_id}
        };

        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    gameId = result.data.gid;
                    log(`${accountTips}开始游戏成功${gameId}✅`, true)
                } else {
                    log(`${accountTips}开始游戏失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}开始游戏异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(gameId);
        });

    })

}

async function factoryGameOver(body) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/game/end',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                Accept: '*/*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'accept-encoding': 'gzip, deflate, br',
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'connection': 'keep-alive',
                'Content-Type': 'application/json'
            },
            data: body
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    let get_water = result.data.get_water;
                    // let sy_water = result.data.sy_water;
                    log(`${accountTips}游戏完成获取【${get_water}】绵力✅`, true)
                } else {
                    log(`${accountTips}游戏完成失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}游戏完成异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function factoryGameStart(taskId) {
    let gameId = '';
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/game/task/begin',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                Accept: '*/*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'accept-encoding': 'gzip, deflate, br',
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'connection': 'keep-alive',
                'Content-Type': 'application/json'
            },
            data: {task_id: taskId}
        };

        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    gameId = result.data.gid;
                    log(`${accountTips}开始游戏[${taskId}]成功${gameId}✅`, true)
                } else {
                    log(`${accountTips}开始游戏[${taskId}]失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}开始游戏[${taskId}]异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(gameId);
        });

    })

}

async function factoryGameEnd(body) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/game/task/end',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                Accept: '*/*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'accept-encoding': 'gzip, deflate, br',
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'connection': 'keep-alive',
                'Content-Type': 'application/json'
            },
            data: body
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    let get_water = result.data.water;
                    // let sy_water = result.data.sy_water;
                    log(`${accountTips}游戏完成获取【${get_water}】绵力✅`, true)
                } else {
                    log(`${accountTips}游戏完成失败❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}游戏完成异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function factoryTaskList() {
    let taskData = [];
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/task/list',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    let task_user_info = result.data.task_user_info;
                    taskData = result.data.tasks;
                    for (let i in taskData) {
                        let taskId = parseInt(taskData[i]["id"]);
                        for (let j in task_user_info) {
                            if (taskId == parseInt(task_user_info[j]["task_id"])) {
                                taskData[i]['receive_num'] = task_user_info[j]['receive_num'];
                                taskData[i]['complete_num'] = task_user_info[j]['complete_num'];
                                taskData[i]['complete_date'] = task_user_info[j]['complete_date'];
                                taskData[i]['receive_date'] = task_user_info[j]['receive_date'];
                                if (task_user_info[j]['task_user_id']) {
                                    taskData[i]['task_user_id'] = task_user_info[j]['task_user_id'];
                                }
                            }
                        }
                    }
                    log(`${accountTips}获取工厂任务✅`, true)
                } else {
                    log(`${accountTips}获取工厂任务❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}获取工厂任务异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(taskData);
        });

    })

}

async function completeSanTask(taskId) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/task/complete-task',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'content-type': 'application/json;charset=utf-8',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                Referer: 'https://cottonfactory.purcotton.com/h5/?token=W7gENz4JvYHF3jS78jymuQ%3D%3D&code=a3b58363-93ca-47e1-908f-69e8fbd3159e&app_id=wxdfcaa44b1aa891a7',
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: {tid: taskId, task_id: taskId, taskId: taskId}
        };

        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取❌：【${result.msg}】`, true)
                }
            } catch (e) {
                log(`${accountTips}任务完成异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function completeTask(action, from) {
    let flag = false;
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://nmp.pureh2b.com/api/purcotton/completetask',
            headers: {
                Host: 'nmp.pureh2b.com',
                'connection': 'keep-alive',
                token: scriptToken,
                'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
                code: scriptCode,
                'Accept-Encoding': 'gzip,compress,br,deflate',
                'user-agent': userAgent,
                Referer: 'https://servicewechat.com/wxdfcaa44b1aa891a7/678/page-frame.html'
            },
            data: `action=${action}&phone=${scriptPhone}&from=${from}`
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    flag = true;
                    log(`${accountTips}任务完成[${action}]成功✅`, true)
                } else {
                    log(`${accountTips}任务完成[${action}]❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}任务完成[${action}]异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(flag);
        });

    })

}

async function receiveTaskWater(taskId) {
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/task/receive-task-water',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'content-type': 'application/json;charset=utf-8',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            },
            data: {tid: taskId, task_id: taskId, taskId: taskId}
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    log(`${accountTips}任务领取奖励成功获得水滴${result.data.get_water}，当前剩余：${result.data.sy_water}✅`, true)
                } else {
                    log(`${accountTips}任务领取奖励❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}任务领取奖励异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve();
        });

    })

}

async function answerInfo() {
    let answerData = [];
    return new Promise((resolve) => {
        var options = {
            method: 'POST',
            url: 'https://cottonfactory.purcotton.com/api/game/answer-info',
            headers: {
                Host: 'cottonfactory.purcotton.com',
                'accept': 'application/json, text/plain, */*',
                'app-id': scriptAppId,
                'accept-language': 'zh-CN,zh-Hans;q=0.9',
                'code': scriptCode,
                'token': scriptToken,
                Origin: 'https://cottonfactory.purcotton.com',
                'user-agent': userAgent,
                'accept-encoding': 'gzip, deflate, br',
                'connection': 'keep-alive'
            }
        };
        axios.request(options).then(async function (response) {
            try {
                let result = response.data;
                if (result.hasOwnProperty('code') && parseInt(result.code) == 200) {
                    for (let i in result.data.exams) {
                        let id = parseInt(result.data.exams[i]["id"]);
                        answerData.push(id);
                    }
                    log(`${accountTips}获取质检问题✅`, true)
                } else {
                    log(`${accountTips}获取质检问题❌：【${result.msg}】`, true)
                }

            } catch (e) {
                log(`${accountTips}获取质检问题异常：${JSON.stringify(response.data)}，请求：${JSON.stringify(options)}`)
            }
        }).catch(function (error) {
            console.error(error.message);
        }).then(res => {
            //这里处理正确返回
            resolve(answerData);
        });

    })

}

//=========================================工厂游戏=============================================//


// ============================================重写============================================ \\
async function GetRewrite() {
    if ($request.url.indexOf("/api/task/index/user") > -1) {
        const ck = $request.headers.body;
        if (S_qmsdCk) {
            if (S_qmsdCk.indexOf(ck) == -1) {
                S_qmsdCk = S_qmsdCk + "@" + ck;
                $.setdata(S_qmsdCk, "S_qmsdCk");
                let List = S_qmsdCk.split("@");
                $.msg(`【${$.name}】` + ` 获取第${List.length}个 ck 成功: ${ck} ,不用请自行关闭重写!`);
            }
        } else {
            $.setdata(ck, "S_qmsdCk");
            $.msg(`【${$.name}】` + ` 获取第1个 ck 成功: ${ck} ,不用请自行关闭重写!`);
        }
    }
}

/**
 *
 * 示例:$.time('yyyy-MM-dd qq HH:mm:ss.S')
 *    :$.time('yyyyMMddHHmmssS')
 *    y:年 M:月 d:日 q:季 H:时 m:分 s:秒 S:毫秒
 *    其中y可选0-4位占位符、S可选0-1位占位符，其余可选0-2位占位符
 * @param {string} fmt 格式化参数
 * @param {number} 可选: 根据指定时间戳返回格式化日期
 *
 */
function time(fmt, ts = null) {
    const date = ts ? new Date(ts) : new Date();
    let o = {
        'M+': date.getMonth() + 1,
        'd+': date.getDate(),
        'H+': date.getHours(),
        'm+': date.getMinutes(),
        's+': date.getSeconds(),
        'q+': Math.floor((date.getMonth() + 3) / 3),
        S: date.getMilliseconds(),
    };
    if (/(y+)/.test(fmt))
        fmt = fmt.replace(
            RegExp.$1,
            (date.getFullYear() + '').substr(4 - RegExp.$1.length)
        );
    for (let k in o)
        if (new RegExp('(' + k + ')').test(fmt))
            fmt = fmt.replace(
                RegExp.$1,
                RegExp.$1.length == 1
                    ? o[k]
                    : ('00' + o[k]).substr(('' + o[k]).length)
            );
    return fmt;
}


// ============================================变量检查============================================ \\
async function Envs() {
    if (S_qmsdCk) {
        if (S_qmsdCk.indexOf("@") != -1) {
            S_qmsdCk.split("@").forEach((item) => {
                S_qmsdCkArr.push(item);
            });
        } else if (S_qmsdCk.indexOf("\n") != -1) {
            S_qmsdCk.split("\n").forEach((item) => {
                S_qmsdCkArr.push(item);
            });
        } else {
            S_qmsdCkArr.push(S_qmsdCk);
        }
    } else {
        log(`\n 【${$.name}】：未填写变量 WX_ID`)
        return;
    }
    return true;
}

// ============================================发送消息============================================ \\
/**
 * 添加消息
 * @param str
 * @param is_log
 */
function addNotifyStr(str, is_log = true) {
    if (is_log) {
        log(`${accountTips}${str}\n`)
    }
    msg += `${accountTips}${str}\n`
}

async function SendMsg(message) {
    if (!message)
        return;
    try {
        await sendNotify.sendNotify($.name, message);
    } catch (e) {
        log(`通知发送失败: ${e}`);
    }
}


/**
 * 随机数生成
 */
function randomString(e) {
    e = e || 32;
    var t = "QWERTYUIOPASDFGHJKLZXCVBNM1234567890",
        a = t.length,
        n = "";
    for (i = 0; i < e; i++)
        n += t.charAt(Math.floor(Math.random() * a));
    return n
}

/**
 * 随机整数生成
 */
function randomInt(min, max) {
    return Math.round(Math.random() * (max - min) + min)
}

/**
 * 获取毫秒时间戳
 */
function timestampMs() {
    return new Date().getTime();
}

/**
 * 获取秒时间戳
 */
function timestampS() {
    return Date.parse(new Date()) / 1000;
}

/**
 * 获取随机诗词
 */
function poem(timeout = 3 * 1000) {
    return new Promise((resolve) => {
        let url = {
            url: `https://v1.jinrishici.com/all.json`
        }
        $.get(url, async (err, resp, data) => {
            try {
                data = JSON.parse(data)
                log(`${data.content}  \n————《${data.origin}》${data.author}`);
            } catch (e) {
                log(e, resp);
            } finally {
                resolve()
            }
        }, timeout)
    })
}

/**
 * 修改配置文件
 */
function modify() {

    fs.readFile('/ql/data/config/config.sh', 'utf8', function (err, dataStr) {
        if (err) {
            return log('读取文件失败！' + err)
        } else {
            var result = dataStr.replace(/regular/g, string);
            fs.writeFile('/ql/data/config/config.sh', result, 'utf8', function (err) {
                if (err) {
                    return log(err);
                }
            });
        }
    })
}


function Env(t, e) {
    "undefined" != typeof process && JSON.stringify(process.env).indexOf("GITHUB") > -1 && process.exit(0);

    class s {
        constructor(t) {
            this.env = t
        }

        send(t, e = "GET") {
            t = "string" == typeof t ? {url: t} : t;
            let s = this.get;
            return "POST" === e && (s = this.post), new Promise((e, i) => {
                s.call(this, t, (t, s, r) => {
                    t ? i(t) : e(s)
                })
            })
        }

        get(t) {
            return this.send.call(this.env, t)
        }

        post(t) {
            return this.send.call(this.env, t, "POST")
        }
    }

    return new class {
        constructor(t, e) {
            this.name = t, this.http = new s(this), this.data = null, this.dataFile = "box.dat", this.logs = [], this.isMute = !1, this.isNeedRewrite = !1, this.logSeparator = "\n", this.startTime = (new Date).getTime(), Object.assign(this, e), this.log("", `🔔${this.name}, 开始!`)
        }

        isNode() {
            return "undefined" != typeof module && !!module.exports
        }

        isQuanX() {
            return "undefined" != typeof $task
        }

        isSurge() {
            return "undefined" != typeof $httpClient && "undefined" == typeof $loon
        }

        isLoon() {
            return "undefined" != typeof $loon
        }

        toObj(t, e = null) {
            try {
                return JSON.parse(t)
            } catch {
                return e
            }
        }

        toStr(t, e = null) {
            try {
                return JSON.stringify(t)
            } catch {
                return e
            }
        }

        getjson(t, e) {
            let s = e;
            const i = this.getdata(t);
            if (i) try {
                s = JSON.parse(this.getdata(t))
            } catch {
            }
            return s
        }

        setjson(t, e) {
            try {
                return this.setdata(JSON.stringify(t), e)
            } catch {
                return !1
            }
        }

        getScript(t) {
            return new Promise(e => {
                this.get({url: t}, (t, s, i) => e(i))
            })
        }

        runScript(t, e) {
            return new Promise(s => {
                let i = this.getdata("@chavy_boxjs_userCfgs.httpapi");
                i = i ? i.replace(/\n/g, "").trim() : i;
                let r = this.getdata("@chavy_boxjs_userCfgs.httpapi_timeout");
                r = r ? 1 * r : 20, r = e && e.timeout ? e.timeout : r;
                const [o, h] = i.split("@"), n = {
                    url: `http://${h}/v1/scripting/evaluate`,
                    body: {script_text: t, mock_type: "cron", timeout: r},
                    headers: {"X-Key": o, Accept: "*/*"}
                };
                this.post(n, (t, e, i) => s(i))
            }).catch(t => this.logErr(t))
        }

        loaddata() {
            if (!this.isNode()) return {};
            {
                this.fs = this.fs ? this.fs : require("fs"), this.path = this.path ? this.path : require("path");
                const t = this.path.resolve(this.dataFile), e = this.path.resolve(process.cwd(), this.dataFile),
                    s = this.fs.existsSync(t), i = !s && this.fs.existsSync(e);
                if (!s && !i) return {};
                {
                    const i = s ? t : e;
                    try {
                        return JSON.parse(this.fs.readFileSync(i))
                    } catch (t) {
                        return {}
                    }
                }
            }
        }

        writedata() {
            if (this.isNode()) {
                this.fs = this.fs ? this.fs : require("fs"), this.path = this.path ? this.path : require("path");
                const t = this.path.resolve(this.dataFile), e = this.path.resolve(process.cwd(), this.dataFile),
                    s = this.fs.existsSync(t), i = !s && this.fs.existsSync(e), r = JSON.stringify(this.data);
                s ? this.fs.writeFileSync(t, r) : i ? this.fs.writeFileSync(e, r) : this.fs.writeFileSync(t, r)
            }
        }

        lodash_get(t, e, s) {
            const i = e.replace(/\[(\d+)\]/g, ".$1").split(".");
            let r = t;
            for (const t of i) if (r = Object(r)[t], void 0 === r) return s;
            return r
        }

        lodash_set(t, e, s) {
            return Object(t) !== t ? t : (Array.isArray(e) || (e = e.toString().match(/[^.[\]]+/g) || []), e.slice(0, -1).reduce((t, s, i) => Object(t[s]) === t[s] ? t[s] : t[s] = Math.abs(e[i + 1]) >> 0 == +e[i + 1] ? [] : {}, t)[e[e.length - 1]] = s, t)
        }

        getdata(t) {
            let e = this.getval(t);
            if (/^@/.test(t)) {
                const [, s, i] = /^@(.*?)\.(.*?)$/.exec(t), r = s ? this.getval(s) : "";
                if (r) try {
                    const t = JSON.parse(r);
                    e = t ? this.lodash_get(t, i, "") : e
                } catch (t) {
                    e = ""
                }
            }
            return e
        }

        setdata(t, e) {
            let s = !1;
            if (/^@/.test(e)) {
                const [, i, r] = /^@(.*?)\.(.*?)$/.exec(e), o = this.getval(i),
                    h = i ? "null" === o ? null : o || "{}" : "{}";
                try {
                    const e = JSON.parse(h);
                    this.lodash_set(e, r, t), s = this.setval(JSON.stringify(e), i)
                } catch (e) {
                    const o = {};
                    this.lodash_set(o, r, t), s = this.setval(JSON.stringify(o), i)
                }
            } else s = this.setval(t, e);
            return s
        }

        getval(t) {
            return this.isSurge() || this.isLoon() ? $persistentStore.read(t) : this.isQuanX() ? $prefs.valueForKey(t) : this.isNode() ? (this.data = this.loaddata(), this.data[t]) : this.data && this.data[t] || null
        }

        setval(t, e) {
            return this.isSurge() || this.isLoon() ? $persistentStore.write(t, e) : this.isQuanX() ? $prefs.setValueForKey(t, e) : this.isNode() ? (this.data = this.loaddata(), this.data[e] = t, this.writedata(), !0) : this.data && this.data[e] || null
        }

        initGotEnv(t) {
            this.got = this.got ? this.got : require("got"), this.cktough = this.cktough ? this.cktough : require("tough-cookie"), this.ckjar = this.ckjar ? this.ckjar : new this.cktough.CookieJar, t && (t.headers = t.headers ? t.headers : {}, void 0 === t.headers.Cookie && void 0 === t.cookieJar && (t.cookieJar = this.ckjar))
        }

        get(t, e = (() => {
        })) {
            t.headers && (delete t.headers["Content-Type"], delete t.headers["Content-Length"]), this.isSurge() || this.isLoon() ? (this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {"X-Surge-Skip-Scripting": !1})), $httpClient.get(t, (t, s, i) => {
                !t && s && (s.body = i, s.statusCode = s.status), e(t, s, i)
            })) : this.isQuanX() ? (this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {hints: !1})), $task.fetch(t).then(t => {
                const {statusCode: s, statusCode: i, headers: r, body: o} = t;
                e(null, {status: s, statusCode: i, headers: r, body: o}, o)
            }, t => e(t))) : this.isNode() && (this.initGotEnv(t), this.got(t).on("redirect", (t, e) => {
                try {
                    if (t.headers["set-cookie"]) {
                        const s = t.headers["set-cookie"].map(this.cktough.Cookie.parse).toString();
                        s && this.ckjar.setCookieSync(s, null), e.cookieJar = this.ckjar
                    }
                } catch (t) {
                    this.logErr(t)
                }
            }).then(t => {
                const {statusCode: s, statusCode: i, headers: r, body: o} = t;
                e(null, {status: s, statusCode: i, headers: r, body: o}, o)
            }, t => {
                const {message: s, response: i} = t;
                e(s, i, i && i.body)
            }))
        }

        post(t, e = (() => {
        })) {
            if (t.body && t.headers && !t.headers["Content-Type"] && (t.headers["Content-Type"] = "application/x-www-form-urlencoded"), t.headers && delete t.headers["Content-Length"], this.isSurge() || this.isLoon()) this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {"X-Surge-Skip-Scripting": !1})), $httpClient.post(t, (t, s, i) => {
                !t && s && (s.body = i, s.statusCode = s.status), e(t, s, i)
            }); else if (this.isQuanX()) t.method = "POST", this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {hints: !1})), $task.fetch(t).then(t => {
                const {statusCode: s, statusCode: i, headers: r, body: o} = t;
                e(null, {status: s, statusCode: i, headers: r, body: o}, o)
            }, t => e(t)); else if (this.isNode()) {
                this.initGotEnv(t);
                const {url: s, ...i} = t;
                this.got.post(s, i).then(t => {
                    const {statusCode: s, statusCode: i, headers: r, body: o} = t;
                    e(null, {status: s, statusCode: i, headers: r, body: o}, o)
                }, t => {
                    const {message: s, response: i} = t;
                    e(s, i, i && i.body)
                })
            }
        }

        time(t, e = null) {
            const s = e ? new Date(e) : new Date;
            let i = {
                "M+": s.getMonth() + 1,
                "d+": s.getDate(),
                "H+": s.getHours(),
                "m+": s.getMinutes(),
                "s+": s.getSeconds(),
                "q+": Math.floor((s.getMonth() + 3) / 3),
                S: s.getMilliseconds()
            };
            /(y+)/.test(t) && (t = t.replace(RegExp.$1, (s.getFullYear() + "").substr(4 - RegExp.$1.length)));
            for (let e in i) new RegExp("(" + e + ")").test(t) && (t = t.replace(RegExp.$1, 1 == RegExp.$1.length ? i[e] : ("00" + i[e]).substr(("" + i[e]).length)));
            return t
        }

        msg(e = t, s = "", i = "", r) {
            const o = t => {
                if (!t) return t;
                if ("string" == typeof t) return this.isLoon() ? t : this.isQuanX() ? {"open-url": t} : this.isSurge() ? {url: t} : void 0;
                if ("object" == typeof t) {
                    if (this.isLoon()) {
                        let e = t.openUrl || t.url || t["open-url"], s = t.mediaUrl || t["media-url"];
                        return {openUrl: e, mediaUrl: s}
                    }
                    if (this.isQuanX()) {
                        let e = t["open-url"] || t.url || t.openUrl, s = t["media-url"] || t.mediaUrl;
                        return {"open-url": e, "media-url": s}
                    }
                    if (this.isSurge()) {
                        let e = t.url || t.openUrl || t["open-url"];
                        return {url: e}
                    }
                }
            };
            if (this.isMute || (this.isSurge() || this.isLoon() ? $notification.post(e, s, i, o(r)) : this.isQuanX() && $notify(e, s, i, o(r))), !this.isMuteLog) {
                let t = ["", "==============📣系统通知📣=============="];
                t.push(e), s && t.push(s), i && t.push(i), console.log(t.join("\n")), this.logs = this.logs.concat(t)
            }
        }

        log(...t) {
            t.length > 0 && (this.logs = [...this.logs, ...t]), console.log(t.join(this.logSeparator))
        }

        logErr(t, e) {
            const s = !this.isSurge() && !this.isQuanX() && !this.isLoon();
            s ? this.log("", `❗️${this.name}, 错误!`, t.stack) : this.log("", `❗️${this.name}, 错误!`, t)
        }

        wait(t) {
            return new Promise(e => setTimeout(e, t))
        }

        done(t = {}) {
            const e = (new Date).getTime(), s = (e - this.startTime) / 1e3;
            this.log("", `🔔${this.name}, 结束! 🕛 ${s} 秒`), this.log(), (this.isSurge() || this.isQuanX() || this.isLoon()) && $done(t)
        }
    }(t, e)
}
