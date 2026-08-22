/*
君品荟签到

变量：
  YYB_SERVER    YYB-Go-Enhanced 地址@账号标识，多账号一行一个，必须配置
                示例：yyb-go:8000@openid
  cron: 57 10,13 * * *

可选：
  JPH_NOTIFY     通知开关，默认 1；填 0 关闭 sendNotify
*/
const $ = new Env('君品荟签到');
const axios = require('axios');

const { setGlobalDispatcher, Agent } = require('undici');
setGlobalDispatcher(new Agent({
  allowH2: false, // 关键：关闭 HTTP/2
  connect: { rejectUnauthorized: false }
}));

const CryptoJS = require('crypto-js'); // 直接使用青龙本地依赖
let request = require("request");
request = request.defaults({
    jar: true
});
const { log } = console;
const Notify = !['0', 'false', 'off', 'no'].includes(String(($.isNode() ? process.env.JPH_NOTIFY : $.getdata("JPH_NOTIFY")) || '1').toLowerCase());
const debug = 0; //0为关闭调试，1为打开调试,默认为0
const WX_APPID = "wx8d41cdc44c8aeaab";
const OCR_SERVER = (($.isNode() ? process.env.OCR_SERVER : $.getdata("OCR_SERVER")) || "http://ocr.fj.us.ci").replace(/\/$/, "");
const YYB_SERVER = ($.isNode() ? process.env.YYB_SERVER : $.getdata("YYB_SERVER")) || "";
let xjhd = '';
let xjhdArr = [];
let data = '';
let msg = '';
let xj_code = '';
let xj_token = '';
let xj_cookie = '';
let pointValue = '';
let wx_unionid = '';
let wx_applet_openid = '';
let user_phone = '';

function parseYybGoEntry(rawValue) {
    const value = String(rawValue || '').trim();
    const atIndex = value.lastIndexOf('@');
    if (atIndex <= 0 || atIndex === value.length - 1) {
        return { server: '', ref: '' };
    }
    let server = value.slice(0, atIndex).trim().replace(/\/+$/, '');
    const ref = value.slice(atIndex + 1).trim();
    if (server && !/^https?:\/\//i.test(server)) server = `http://${server}`;
    return server && ref ? { server, ref } : { server: '', ref: '' };
}

!(async () => {
    if (typeof $request !== "undefined") {
        await GetRewrite();
    } else {
        if (!(await Envs()))
            return;


        log(`\n\n=============================================    \n脚本执行 - 北京时间(UTC+8)：${new Date(
            new Date().getTime() + new Date().getTimezoneOffset() * 60 * 1000 + 8 * 60 * 60 * 1000
        ).toLocaleString()} \n=============================================\n`);

        log(`\n============ 君品荟签到  ============`)
        log(`\n=================== 共找到 ${xjhdArr.length} 个账号 ===================`)
        if (debug) {
            log(`【debug】 这是你的全部账号数组:\n ${xjhdArr}`);
        }

        for (let index = 0; index < xjhdArr.length; index++) {
            let num = index + 1
            addNotifyStr(`\n==== 开始【第 ${num} 个账号】====\n`, true)
            xjhd = xjhdArr[index];
            xj_code = '';
            xj_token = '';
            xj_cookie = '';
            wx_unionid = '';
            wx_applet_openid = '';
            user_phone = '';

            if (!(await get_code(xjhd))) {
                addNotifyStr(`❌ 第 ${num} 个账号获取微信 code 失败，跳过`, true);
                continue;
            }
            if (!(await wxMiniSilentLogin(xj_code))) {
                addNotifyStr(`❌ 第 ${num} 个账号业务登录失败，跳过`, true);
                continue;
            }
            await get_setcookie(xj_token);

            // 滑块验证
            let captcha = await get_captcha(xj_token);
            let captchaPassed = false;
            let captchaSamplePayload = null;
            if (captcha && captcha.data && captcha.data.repData) {
                try {
                    const sliderImage = captcha.data.repData.jigsawImageBase64;
                    const backImage = captcha.data.repData.originalImageBase64;
                    let getXpos = await slidePost({
                        'slidingImage': sliderImage,
                        'backImage': backImage
                    })
                    const predictedX = getXpos?.result || 50
                    const predictedY = 5
                    let point = aesEncrypt({ "x": predictedX, "y": predictedY }, captcha.data.repData.secretKey)
                    let check = await commonPost(`/api/captcha/check`, {
                        "captchaType": "blockPuzzle",
                        "pointJson": point,
                        "token": captcha.data.repData.token
                    }, xj_token)
                    captchaPassed = !!check?.data?.success;
                    captchaSamplePayload = {
                        type: 'slide',
                        success: captchaPassed,
                        prediction: { x: predictedX, y: predictedY },
                        verify: check,
                        images: {
                            slidingImage: sliderImage,
                            backImage: backImage
                        }
                    }
                    addNotifyStr(`✅ 滑块验证结果：${captchaPassed ? "成功" : "失败"}`, true);
                    if (!captchaPassed) {
                        addNotifyStr(`⚠️ 滑块校验返回：${JSON.stringify(check || {}).slice(0, 300)}`, true);
                    }
                } catch (e) {
                    addNotifyStr(`⚠️ 滑块验证异常：${e.message || e}`, true);
                }
            } else {
                addNotifyStr(`⚠️ 未获取到验证码，跳过滑块`, true);
            }

            if (!captchaPassed) {
                addNotifyStr(`⚠️ 验证码未通过，继续尝试签到`, true);
            }

            await fillSignIn(xj_cookie, xj_token, xj_code);
            if (captchaSamplePayload) {
                reportCaptchaSample({
                    ...captchaSamplePayload,
                    extra: { signMessage: msg.split('\n').slice(-3).join('\n') }
                });
            }
            await getpoints(xj_token);
            await $await(10000)
        }
        await SendMsg(msg);
    }
})()
    .catch((e) => log(e))
    .finally(() => $.done())

// 获取code
async function get_code(hd) {
    xj_code = '';
    const { server, ref } = parseYybGoEntry(hd);
    if (!server || !ref) {
        log(`❌ YYB_SERVER 格式错误，应为 地址@账号标识`);
        return false;
    }
    try {
        const response = await axios.post(`${server}/wxapp/getCode`, {
            ref,
            app_id: WX_APPID
        }, {
            timeout: 20000,
            proxy: false,
            validateStatus: () => true
        });
        const result = response.data;
        xj_code = result && result.data && result.data.result && result.data.result.code;
        if (xj_code) {
            log(`✅ YYB-Go-Enhanced 获取 code 成功`);
            return true;
        } else {
            const detail = JSON.stringify(result || {}).slice(0, 300);
            log(`❌ YYB-Go-Enhanced 获取 code 失败（HTTP ${response.status}）：${detail}`);
        }
    } catch (err) {
        log(`❌ YYB-Go-Enhanced 请求异常：${err.message || err}`);
    }
    return false;
}

// 静默登录
async function wxMiniSilentLogin(codestr) {
    return new Promise((resolve) => {
        const options = {
            method: 'POST',
            url: 'https://fm.exijiu.com/api/v2/login/wxMiniSilentLogin',
            headers: {
                'AppID': 'wx8d41cdc44c8aeaab',
                'Authorization': 'Basic d2VjaGF0OndlY2hhdF9zZWNyZXQ=',
                'Content-Type': 'application/json'
            },
            data: { code: codestr }
        };
        axios.request(options).then(res => {
            try {
                const data = res.data;
                const loginData = data && data.data;
                if (!loginData || !loginData.token) {
                    const code = data && (data.code ?? data.status);
                    const reason = data && (data.message || data.msg || data.error || data.success);
                    log(`❌ 业务登录失败：code=${code ?? 'unknown'} message=${String(reason ?? '未返回 token').slice(0, 160)}`);
                    return resolve(false);
                }
                xj_token = loginData.token;
                wx_unionid = loginData.unionId || '';
                wx_applet_openid = loginData.openId || '';
                user_phone = loginData.phone || '';
                let hidePhone = user_phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
                //log(`✅ 用户手机号获取成功:  ${hidePhone}`);
                addNotifyStr(`✅ 用户手机号获取成功:  ${hidePhone}`);
                resolve(true);
            } catch (e) {
                log(`❌ 登录解析异常：${e.message || e}`)
                resolve(false);
            }
        }).catch(err => {
            log(`❌ 登录请求失败：${err.message || err}`)
            resolve(false);
        })
    })
}

// 获取Cookie
async function get_setcookie(token_) {
    return new Promise((resolve) => {
        const options = {
            method: 'POST',
            url: 'https://fm.exijiu.com/api/banneradvert/query-by-location',
            headers: { 'X-access-token': token_, 'Content-Type': 'application/json' },
            data: { locationIdList: [18, 17] }
        };
        axios.request(options).then(res => {
            try {
                let setCookieHeader = res.headers['set-cookie'];
                if (setCookieHeader) {
                    const target = Array.isArray(setCookieHeader) ? setCookieHeader[0] : setCookieHeader;
                    xj_cookie = target.split(';')[0];
                }
            } catch (e) {}
            resolve(xj_cookie);
        }).catch(() => { resolve('') })
    })
}

// 获取验证码
async function get_captcha(token_) {
    return new Promise((resolve) => {
        if (!token_) return resolve(null);
        const options = {
            method: 'POST',
            url: 'https://fm.exijiu.com/api/captcha/get',
            headers: { 'X-Access-Token': token_, 'Content-Type': 'application/json' },
            data: { captchaType: "blockPuzzle" },
            timeout: 5000
        };
        axios.request(options).then(res => {
            resolve(res.data);
        }).catch(() => { resolve(null) })
    })
}

// AES 加密（手机号）
function aes128EcbEncrypt(plainText) {
    if (!plainText) return "";
    try {
        const key = CryptoJS.enc.Utf8.parse('4SlNEr0k8Qyo8keM');
        const plainBytes = CryptoJS.enc.Utf8.parse(plainText);
        const encrypted = CryptoJS.AES.encrypt(plainBytes, key, {
            mode: CryptoJS.mode.ECB,
            padding: CryptoJS.pad.Pkcs7
        });
        return encrypted.toString();
    } catch (e) {
        return "";
    }
}

// 滑块加密（直接使用本地CryptoJS）
function aesEncrypt(e, n) {
    var t = CryptoJS.enc.Utf8.parse(n)
    var i = CryptoJS.enc.Utf8.parse(JSON.stringify(e))
    var r = CryptoJS.AES.encrypt(i, t, {
        mode: CryptoJS.mode.ECB,
        padding: CryptoJS.pad.Pkcs7
    });
    return CryptoJS.enc.Base64.stringify(r.ciphertext)
}



// 签到
async function fillSignIn(cookie_, token__, signCode) {
    return new Promise((resolve) => {
        const options = {
            method: 'POST',
            url: 'https://fm.exijiu.com/api/customer/daily/fillSignIn',
            headers: {
                'X-access-token': token__,
                Cookie: cookie_,
                'Content-Type': 'application/json'
            },
            data: { code: signCode, channelCode: "xj_mall_wx_applet" }
        };
        axios.request(options).then(res => {
            try {
                let d = res.data;
                if (d.success) {
                    pointValue = d.data?.pointValue || 0;
                    //log(`✅ 签到成功，积分：${pointValue}`);
                    addNotifyStr(`签到成功，获得积分：${pointValue}`);
                } else {
                    addNotifyStr(`签到失败：${d.message || '未知'}`);
                }
            } catch (e) {
                addNotifyStr(`签到异常`);
            }
            resolve();
        }).catch(() => {
            addNotifyStr(`签到请求失败`);
            resolve();
        })
    })
}

// 查积分
async function getpoints(token__) {
    return new Promise((resolve) => {
        const options = {
  method: 'POST',
  url: 'https://fm.exijiu.com/api/customer/accoutInter/token',
  headers: {
    'X-Access-Token': token__,
    AppID: 'wx8d41cdc44c8aeaab',
    Authorization: 'Basic d2VjaGF0OndlY2hhdF9zZWNyZXQ=',
    'Content-Type': 'application/json',
    Accept: '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'User-Agent': 'PostmanRuntime-ApipostRuntime/1.1.0',
    Connection: 'keep-alive'
  },
  data: '{"checkLevelExist":true}'
};
        axios.request(options).then(res => {
            try {
                let d = res.data;
                if (d.success) {
                    pointss = d.data.points;
                    //log(`✅ 总积分：${pointss}`);
                    addNotifyStr(`总积分：${pointss}`);
                } else {
                    addNotifyStr(`获取总积分失败：${d.message || '未知'}`);
                }
            } catch (e) {
                addNotifyStr(`获取总积分`);
            }
            resolve();
        }).catch(() => {
            addNotifyStr(`获取总积分失败`);
            resolve();
        })
    })
}


// 滑块请求
async function slidePost(body) {
    return new Promise(resolve => {
        axios.post(`${OCR_SERVER}/capcode`, body, {
            headers: { 'Content-Type': 'application/json' }
        }).then(res => {
            resolve(res.data);
        }).catch(() => { resolve(null) })
    })
}

// 样本采集上报
async function reportCaptchaSample(payload) {
    return new Promise(resolve => {
        const body = {
            ...payload,
            script: $.name,
            account: user_phone ? user_phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') : ''
        };
        axios.post(`${OCR_SERVER}/collect`, body, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 5000
        }).then(() => resolve(true)).catch(() => resolve(false))
    })
}

// 通用POST
async function commonPost(url, body = {}, token_) {
    return new Promise(resolve => {
        axios.post(`https://fm.exijiu.com${url}`, body, {
            headers: { 'X-access-token': token_, 'Content-Type': 'application/json' }
        }).then(res => {
            resolve(res.data);
        }).catch(() => { resolve(null) })
    })
}

// 延迟
function $await(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 环境处理
async function Envs() {
    if (!YYB_SERVER.trim()) {
        log(`未填写变量 YYB_SERVER，格式：地址@账号标识，多账号一行一个`);
        return false;
    }
    xjhdArr = YYB_SERVER.split(/\r?\n/).map(i => i.trim()).filter(i => {
        if (!i) return false;
        const parsed = parseYybGoEntry(i);
        if (!parsed.server || !parsed.ref) log(`跳过无效 YYB_SERVER 配置：${i}`);
        return parsed.server && parsed.ref;
    });
    if (!xjhdArr.length) {
        log(`YYB_SERVER 中没有有效账号`);
        return false;
    }
    return true;
}

// 消息拼接
function addNotifyStr(str, is_log = true) {
    if (is_log) log(str);
    msg += str + '\n';
}

// 发送通知
async function SendMsg(message) {
    if (!message || !Notify) return;
    if ($.isNode()) {
        try {
            const notify = require('./sendNotify');
            await notify.sendNotify($.name, message);
        } catch {}
    } else {
        $.msg(message);
    }
}






var MD5=function(string){function RotateLeft(lValue,iShiftBits){return(lValue<<iShiftBits)|(lValue>>>(32-iShiftBits));}function AddUnsigned(lX,lY){var lX4,lY4,lX8,lY8,lResult;lX8=(lX&0x80000000);lY8=(lY&0x80000000);lX4=(lX&0x40000000);lY4=(lY&0x40000000);lResult=(lX&0x3FFFFFFF)+(lY&0x3FFFFFFF);if(lX4&lY4){return(lResult^0x80000000^lX8^lY8);}if(lX4|lY4){if(lResult&0x40000000){return(lResult^0xC0000000^lX8^lY8);}else{return(lResult^0x40000000^lX8^lY8);}}else{return(lResult^lX8^lY8);}}function F(x,y,z){return(x&y)|((~x)&z);}function G(x,y,z){return(x&z)|(y&(~z));}function H(x,y,z){return(x^y^z);}function I(x,y,z){return(y^(x|(~z)));}function FF(a,b,c,d,x,s,ac){a=AddUnsigned(a,AddUnsigned(AddUnsigned(F(b,c,d),x),ac));return AddUnsigned(RotateLeft(a,s),b);}function GG(a,b,c,d,x,s,ac){a=AddUnsigned(a,AddUnsigned(AddUnsigned(G(b,c,d),x),ac));return AddUnsigned(RotateLeft(a,s),b);}function HH(a,b,c,d,x,s,ac){a=AddUnsigned(a,AddUnsigned(AddUnsigned(H(b,c,d),x),ac));return AddUnsigned(RotateLeft(a,s),b);}function II(a,b,c,d,x,s,ac){a=AddUnsigned(a,AddUnsigned(AddUnsigned(I(b,c,d),x),ac));return AddUnsigned(RotateLeft(a,s),b);}function ConvertToWordArray(string){var lWordCount;var lMessageLength=string.length;var lNumberOfWords_temp1=lMessageLength+8;var lNumberOfWords_temp2=(lNumberOfWords_temp1-(lNumberOfWords_temp1%64))/64;var lNumberOfWords=(lNumberOfWords_temp2+1)*16;var lWordArray=Array(lNumberOfWords-1);var lBytePosition=0;var lByteCount=0;while(lByteCount<lMessageLength){lWordCount=(lByteCount-(lByteCount%4))/4;lBytePosition=(lByteCount%4)*8;lWordArray[lWordCount]=(lWordArray[lWordCount]|(string.charCodeAt(lByteCount)<<lBytePosition));lByteCount++;}lWordCount=(lByteCount-(lByteCount%4))/4;lBytePosition=(lByteCount%4)*8;lWordArray[lWordCount]=lWordArray[lWordCount]|(0x80<<lBytePosition);lWordArray[lNumberOfWords-2]=lMessageLength<<3;lWordArray[lNumberOfWords-1]=lMessageLength>>>29;return lWordArray;}function WordToHex(lValue){var WordToHexValue="",WordToHexValue_temp="",lByte,lCount;for(lCount=0;lCount<=3;lCount++){lByte=(lValue>>>(lCount*8))&255;WordToHexValue_temp="0"+lByte.toString(16);WordToHexValue=WordToHexValue+WordToHexValue_temp.substr(WordToHexValue_temp.length-2,2);}return WordToHexValue;}function Utf8Encode(string){string=string.replace(/\r\n/g,"\n");var utftext="";for(var n=0;n<string.length;n++){var c=string.charCodeAt(n);if(c<128){utftext+=String.fromCharCode(c);}else if((c>127)&&(c<2048)){utftext+=String.fromCharCode((c>>6)|192);utftext+=String.fromCharCode((c&63)|128);}else{utftext+=String.fromCharCode((c>>12)|224);utftext+=String.fromCharCode(((c>>6)&63)|128);utftext+=String.fromCharCode((c&63)|128);}}return utftext;}var x=Array();var k,AA,BB,CC,DD,a,b,c,d;var S11=7,S12=12,S13=17,S14=22;var S21=5,S22=9,S23=14,S24=20;var S31=4,S32=11,S33=16,S34=23;var S41=6,S42=10,S43=15,S44=21;string=Utf8Encode(string);x=ConvertToWordArray(string);a=0x67452301;b=0xEFCDAB89;c=0x98BADCFE;d=0x10325476;for(k=0;k<x.length;k+=16){AA=a;BB=b;CC=c;DD=d;a=FF(a,b,c,d,x[k+0],S11,0xD76AA478);d=FF(d,a,b,c,x[k+1],S12,0xE8C7B756);c=FF(c,d,a,b,x[k+2],S13,0x242070DB);b=FF(b,c,d,a,x[k+3],S14,0xC1BDCEEE);a=FF(a,b,c,d,x[k+4],S11,0xF57C0FAF);d=FF(d,a,b,c,x[k+5],S12,0x4787C62A);c=FF(c,d,a,b,x[k+6],S13,0xA8304613);b=FF(b,c,d,a,x[k+7],S14,0xFD469501);a=FF(a,b,c,d,x[k+8],S11,0x698098D8);d=FF(d,a,b,c,x[k+9],S12,0x8B44F7AF);c=FF(c,d,a,b,x[k+10],S13,0xFFFF5BB1);b=FF(b,c,d,a,x[k+11],S14,0x895CD7BE);a=FF(a,b,c,d,x[k+12],S11,0x6B901122);d=FF(d,a,b,c,x[k+13],S12,0xFD987193);c=FF(c,d,a,b,x[k+14],S13,0xA679438E);b=FF(b,c,d,a,x[k+15],S14,0x49B40821);a=GG(a,b,c,d,x[k+1],S21,0xF61E2562);d=GG(d,a,b,c,x[k+6],S22,0xC040B340);c=GG(c,d,a,b,x[k+11],S23,0x265E5A51);b=GG(b,c,d,a,x[k+0],S24,0xE9B6C7AA);a=GG(a,b,c,d,x[k+5],S21,0xD62F105D);d=GG(d,a,b,c,x[k+10],S22,0x2441453);c=GG(c,d,a,b,x[k+15],S23,0xD8A1E681);b=GG(b,c,d,a,x[k+4],S24,0xE7D3FBC8);a=GG(a,b,c,d,x[k+9],S21,0x21E1CDE6);d=GG(d,a,b,c,x[k+14],S22,0xC33707D6);c=GG(c,d,a,b,x[k+3],S23,0xF4D50D87);b=GG(b,c,d,a,x[k+8],S24,0x455A14ED);a=GG(a,b,c,d,x[k+13],S21,0xA9E3E905);d=GG(d,a,b,c,x[k+2],S22,0xFCEFA3F8);c=GG(c,d,a,b,x[k+7],S23,0x676F02D9);b=GG(b,c,d,a,x[k+12],S24,0x8D2A4C8A);a=HH(a,b,c,d,x[k+5],S31,0xFFFA3942);d=HH(d,a,b,c,x[k+8],S32,0x8771F681);c=HH(c,d,a,b,x[k+11],S33,0x6D9D6122);b=HH(b,c,d,a,x[k+14],S34,0xFDE5380C);a=HH(a,b,c,d,x[k+1],S31,0xA4BEEA44);d=HH(d,a,b,c,x[k+4],S32,0x4BDECFA9);c=HH(c,d,a,b,x[k+7],S33,0xF6BB4B60);b=HH(b,c,d,a,x[k+10],S34,0xBEBFBC70);a=HH(a,b,c,d,x[k+13],S31,0x289B7EC6);d=HH(d,a,b,c,x[k+0],S32,0xEAA127FA);c=HH(c,d,a,b,x[k+3],S33,0xD4EF3085);b=HH(b,c,d,a,x[k+6],S34,0x4881D05);a=HH(a,b,c,d,x[k+9],S31,0xD9D4D039);d=HH(d,a,b,c,x[k+12],S32,0xE6DB99E5);c=HH(c,d,a,b,x[k+15],S33,0x1FA27CF8);b=HH(b,c,d,a,x[k+2],S34,0xC4AC5665);a=II(a,b,c,d,x[k+0],S41,0xF4292244);d=II(d,a,b,c,x[k+7],S42,0x432AFF97);c=II(c,d,a,b,x[k+14],S43,0xAB9423A7);b=II(b,c,d,a,x[k+5],S44,0xFC93A039);a=II(a,b,c,d,x[k+12],S41,0x655B59C3);d=II(d,a,b,c,x[k+3],S42,0x8F0CCC92);c=II(c,d,a,b,x[k+10],S43,0xFFEFF47D);b=II(b,c,d,a,x[k+1],S44,0x85845DD1);a=II(a,b,c,d,x[k+8],S41,0x6FA87E4F);d=II(d,a,b,c,x[k+15],S42,0xFE2CE6E0);c=II(c,d,a,b,x[k+6],S43,0xA3014314);b=II(b,c,d,a,x[k+13],S44,0x4E0811A1);a=II(a,b,c,d,x[k+4],S41,0xF7537E82);d=II(d,a,b,c,x[k+11],S42,0xBD3AF235);c=II(c,d,a,b,x[k+2],S43,0x2AD7D2BB);b=II(b,c,d,a,x[k+9],S44,0xEB86D391);a=AddUnsigned(a,AA);b=AddUnsigned(b,BB);c=AddUnsigned(c,CC);d=AddUnsigned(d,DD);}var temp=WordToHex(a)+WordToHex(b)+WordToHex(c)+WordToHex(d);return temp.toLowerCase();}
function randomString(m) {
    for (var e = m > 0 && void 0 !== m ? m : 21, t = ""; t.length < e;) t += Math.random().toString(36).slice(2);
    return t.slice(0, e)
}
function randomnum(e) {
    e = e || 32;
    var t = "1234567890",
        a = t.length,
        n = "";
    for (i = 0; i < e; i++)
        n += t.charAt(Math.floor(Math.random() * a));
    return n
}
function Env(t, e) {
    "undefined" != typeof process && JSON.stringify(process.env).indexOf("GITHUB") > -1 && process.exit(0);

    class s {
        constructor(t) {
            this.env = t
        }

        send(t, e = "GET") {
            t = "string" == typeof t ? {
                url: t
            } : t;
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
            } catch {}
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
                this.get({
                    url: t
                }, (t, s, i) => e(i))
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
                    body: {
                        script_text: t,
                        mock_type: "cron",
                        timeout: r
                    },
                    headers: {
                        "X-Key": o,
                        Accept: "*/*"
                    }
                };
                this.post(n, (t, e, i) => s(i))
            }).catch(t => this.logErr(t))
        }

        loaddata() {
            if (!this.isNode()) return {}; {
                this.fs = this.fs ? this.fs : require("fs"), this.path = this.path ? this.path : require("path");
                const t = this.path.resolve(this.dataFile),
                    e = this.path.resolve(process.cwd(), this.dataFile),
                    s = this.fs.existsSync(t),
                    i = !s && this.fs.existsSync(e);
                if (!s && !i) return {}; {
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
                const t = this.path.resolve(this.dataFile),
                    e = this.path.resolve(process.cwd(), this.dataFile),
                    s = this.fs.existsSync(t),
                    i = !s && this.fs.existsSync(e),
                    r = JSON.stringify(this.data);
                s ? this.fs.writeFileSync(t, r) : i ? this.fs.writeFileSync(e, r) : this.fs.writeFileSync(t, r)
            }
        }

        lodash_get(t, e, s) {
            const i = e.replace(/\[(\d+)\]/g, ".$1").split(".");
            let r = t;
            for (const t of i)
                if (r = Object(r)[t], void 0 === r) return s;
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

        get(t, e = (() => {})) {
            t.headers && (delete t.headers["Content-Type"], delete t.headers["Content-Length"]), this.isSurge() || this.isLoon() ? (this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {
                "X-Surge-Skip-Scripting": !1
            })), $httpClient.get(t, (t, s, i) => {
                !t && s && (s.body = i, s.statusCode = s.status), e(t, s, i)
            })) : this.isQuanX() ? (this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {
                hints: !1
            })), $task.fetch(t).then(t => {
                const {
                    statusCode: s,
                    statusCode: i,
                    headers: r,
                    body: o
                } = t;
                e(null, {
                    status: s,
                    statusCode: i,
                    headers: r,
                    body: o
                }, o)
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
                const {
                    statusCode: s,
                    statusCode: i,
                    headers: r,
                    body: o
                } = t;
                e(null, {
                    status: s,
                    statusCode: i,
                    headers: r,
                    body: o
                }, o)
            }, t => {
                const {
                    message: s,
                    response: i
                } = t;
                e(s, i, i && i.body)
            }))
        }

        post(t, e = (() => {})) {
            if (t.body && t.headers && !t.headers["Content-Type"] && (t.headers["Content-Type"] = "application/x-www-form-urlencoded"), t.headers && delete t.headers["Content-Length"], this.isSurge() || this.isLoon()) this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {
                "X-Surge-Skip-Scripting": !1
            })), $httpClient.post(t, (t, s, i) => {
                !t && s && (s.body = i, s.statusCode = s.status), e(t, s, i)
            });
            else if (this.isQuanX()) t.method = "POST", this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {
                hints: !1
            })), $task.fetch(t).then(t => {
                const {
                    statusCode: s,
                    statusCode: i,
                    headers: r,
                    body: o
                } = t;
                e(null, {
                    status: s,
                    statusCode: i,
                    headers: r,
                    body: o
                }, o)
            }, t => e(t));
            else if (this.isNode()) {
                this.initGotEnv(t);
                const {
                    url: s,
                    ...i
                } = t;
                this.got.post(s, i).then(t => {
                    const {
                        statusCode: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    } = t;
                    e(null, {
                        status: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    }, o)
                }, t => {
                    const {
                        message: s,
                        response: i
                    } = t;
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
                if ("string" == typeof t) return this.isLoon() ? t : this.isQuanX() ? {
                    "open-url": t
                } : this.isSurge() ? {
                    url: t
                } : void 0;
                if ("object" == typeof t) {
                    if (this.isLoon()) {
                        let e = t.openUrl || t.url || t["open-url"],
                            s = t.mediaUrl || t["media-url"];
                        return {
                            openUrl: e,
                            mediaUrl: s
                        }
                    }
                    if (this.isQuanX()) {
                        let e = t["open-url"] || t.url || t.openUrl,
                            s = t["media-url"] || t.mediaUrl;
                        return {
                            "open-url": e,
                            "media-url": s
                        }
                    }
                    if (this.isSurge()) {
                        let e = t.url || t.openUrl || t["open-url"];
                        return {
                            url: e
                        }
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
            const e = (new Date).getTime(),
                s = (e - this.startTime) / 1e3;
            this.log("", `🔔${this.name}, 结束! 🕛 ${s} 秒`), this.log(), (this.isSurge() || this.isQuanX() || this.isLoon()) && $done(t)
        }
    }(t, e)
}
