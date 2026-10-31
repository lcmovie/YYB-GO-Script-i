#!/usr/bin/env node
// name: 福利吧论坛签到
// cron: 0 8,21 * * *

/**
 * 万能的福利吧论坛签到脚本
 * cron: 0 8 * * *
 * new Env('福利吧论坛签到');
 */var _0x51681e=(266692^266693)+(920856^920861);const axios=require("\u0061\u0078\u0069\u006F\u0073");_0x51681e="bhbcpi".split("").reverse().join("");const fs=require("\u0066\u0073");let _0x4741ab;const path=require("\u0070\u0061\u0074\u0068");// 检查是否在青龙环境中
_0x4741ab='\u0068\u006D\u006E\u006E\u0064\u0063';const IS_QINGLONG=fs['\u0065\u0078\u0069\u0073\u0074\u0073\u0053\u0079\u006E\u0063']("\u002F\u0071\u006C");// 多账号支持，使用@分隔多个cookie
let cookies_arr=[];if(process['\u0065\u006E\u0076']['\u0046\u0055\u004C\u0049\u005F\u0043\u004F\u004F\u004B\u0049\u0045']){if(process['\u0065\u006E\u0076']['\u0046\u0055\u004C\u0049\u005F\u0043\u004F\u004F\u004B\u0049\u0045']['\u0069\u006E\u0063\u006C\u0075\u0064\u0065\u0073']("\u0040")){cookies_arr=process['\u0065\u006E\u0076']['\u0046\u0055\u004C\u0049\u005F\u0043\u004F\u004F\u004B\u0049\u0045']['\u0073\u0070\u006C\u0069\u0074']("\u0040");}else{cookies_arr=[process['\u0065\u006E\u0076']['\u0046\u0055\u004C\u0049\u005F\u0043\u004F\u004F\u004B\u0049\u0045']];}}// 请求配置
// 支持多个域名自动切换，从第一个开始尝试直到找到可用的
const BASE_URLS=["moc.3202blfnw.www//:sptth".split("").reverse().join(""),"\u0068\u0074\u0074\u0070\u0073\u003A\u002F\u002F\u0077\u0077\u0077\u002E\u0077\u006E\u0066\u006C\u0062\u0039\u0039\u002E\u0063\u006F\u006D",// 备用域名1
"\u0068\u0074\u0074\u0070\u0073\u003A\u002F\u002F\u0077\u0077\u0077\u002E\u0077\u006E\u0066\u006C\u0062\u002E\u0063\u006F\u006D",// 备用域名2
"evil.82yadlufrednow.f//:sptth".split("").reverse().join("")// 备用域名3
];var _0x59b=(813848^813840)+(703677^703673);const USER_AGENT="\u004D\u006F\u007A\u0069\u006C\u006C\u0061\u002F\u0035\u002E\u0030\u0020\u0028\u0057\u0069\u006E\u0064\u006F\u0077\u0073\u0020\u004E\u0054\u0020\u0031\u0030\u002E\u0030\u003B\u0020\u0057\u0069\u006E\u0036\u0034\u003B\u0020\u0078\u0036\u0034\u0029\u0020\u0041\u0070\u0070\u006C\u0065\u0057\u0065\u0062\u004B\u0069\u0074\u002F\u0035\u0033\u0037\u002E\u0033\u0036\u0020\u0028\u004B\u0048\u0054\u004D\u004C\u002C\u0020\u006C\u0069\u006B\u0065\u0020\u0047\u0065\u0063\u006B\u006F\u0029\u0020\u0043\u0068\u0072\u006F\u006D\u0065\u002F\u0031\u0030\u0033\u002E\u0030\u002E\u0030\u002E\u0030\u0020\u0053\u0061\u0066\u0061\u0072\u0069\u002F\u0035\u0033\u0037\u002E\u0033\u0036";// 日志信息
_0x59b=(664456^664463)+(110826^110826);const result_list=[];// 是否开启调试模式（打印更多信息）
let _0x0b31d;const DEBUG_MODE=false;_0x0b31d=236759^236754;class Env{constructor(name){this['\u006E\u0061\u006D\u0065']=name;this['\u0073\u0074\u0061\u0072\u0074\u0054\u0069\u006D\u0065']=Date['\u006E\u006F\u0077']();}log(...args){console['\u006C\u006F\u0067'](...args);}wait(seconds){return new Promise(resolve=>setTimeout(resolve,seconds*(850039^850847)));}done(){var _0x99g=(262347^262345)+(994183^994180);const costTime=(Date['\u006E\u006F\u0077']()-this['\u0073\u0074\u0061\u0072\u0074\u0054\u0069\u006D\u0065'])/(673679^672871);_0x99g=593339^593342;console['\u006C\u006F\u0067'](`⏱️ ${this['\u006E\u0061\u006D\u0065']}执行完毕，耗时 ${costTime['\u0074\u006F\u0046\u0069\u0078\u0065\u0064'](172929^172931)} 秒`);}static isNode(){return IS_QINGLONG;}}// 实例化环境
const env=new Env("\u5230\u7B7E\u575B\u8BBA\u5229\u798F".split("").reverse().join(""));function debugLog(message){if(DEBUG_MODE){console['\u006C\u006F\u0067'](`[DEBUG] ${message}`);}}function extractFormhash(html,_0x4ab4ed){// 尝试多种正则模式提取formhash
const _0x697e=[new RegExp('\u006E\u0061\u006D\u0065\u003D\u0022\u0066\u006F\u0072\u006D\u0068\u0061\u0073\u0068\u0022\u0020\u0076\u0061\u006C\u0075\u0065\u003D\u0022\u0028\u005B\u005E\u0022\u005D\u002B\u0029\u0022',""),new RegExp(")}8{]f-a9-0[(=hsahmrof".split("").reverse().join(""),""),new RegExp("\")+]\"^[(\"=eulav \"hsahmrof".split("").reverse().join(""),"")];_0x4ab4ed=(230724^230732)+(888078^888072);for(const _0xc5d5c of _0x697e){var _0x8fg=(487811^487808)+(879824^879824);const _0x_0x50a=_0xc5d5c['\u0065\u0078\u0065\u0063'](html);_0x8fg=(470652^470649)+(170739^170741);if(_0x_0x50a){debugLog(`使用模式 '${_0xc5d5c}' 成功提取到formhash: ${_0x_0x50a[222539^222538]}`);return _0x_0x50a[151106^151107];}}debugLog("hsahmrof\u5230\u53D6\u63D0\u80FD\u672A\u5747\u5F0F\u6A21\u5219\u6B63\u6709\u6240".split("").reverse().join(""));// 如果正则都未匹配到，尝试寻找特定文本附近的formhash
if(html['\u0069\u006E\u0063\u006C\u0075\u0064\u0065\u0073']("\u0066\u006F\u0072\u006D\u0068\u0061\u0073\u0068")){const _0xc01fd=html['\u0069\u006E\u0064\u0065\u0078\u004F\u0066']("hsahmrof".split("").reverse().join(""));if(_0xc01fd>(812131^812131)){debugLog(`找到formhash文本位置: ${_0xc01fd}`);var _0x61cf=(807392^807393)+(888714^888717);const _0xa7ad2a=html['\u0073\u0075\u0062\u0073\u0074\u0072\u0069\u006E\u0067'](Math['\u006D\u0061\u0078'](863432^863432,_0xc01fd-(917234^917228)),Math['\u006D\u0069\u006E'](html['\u006C\u0065\u006E\u0067\u0074\u0068'],_0xc01fd+(960070^960116)));_0x61cf=307901^307902;debugLog(`formhash上下文: ${_0xa7ad2a}`);}}return null;}function extractUserIdFromCookie(cookie){var _0xgce72f=(916846^916845)+(655543^655538);const _0x527f=[new RegExp('\u005F\u0073\u0069\u0064\u003D\u0028\u005B\u005E\u003B\u005D\u002B\u0029',""),new RegExp('\u005F\u006C\u0061\u0073\u0074\u0076\u0069\u0073\u0069\u0074\u003D\u0028\u005B\u005E\u003B\u005D\u002B\u0029',""),new RegExp(")+];^[(=htua_".split("").reverse().join(""),"")];_0xgce72f=(829350^829345)+(708390^708391);for(const _0xff6b of _0x527f){let _0x7ga9dc;const _0x2_0x455=_0xff6b['\u0065\u0078\u0065\u0063'](cookie);_0x7ga9dc='\u0071\u0062\u0070\u0063\u006E\u0067';if(_0x2_0x455){debugLog(`从Cookie中找到可能的会话ID: ${_0x2_0x455[213682^213683]}`);return _0x2_0x455[591594^591595];}}return null;}function extractUserInfo(html,_0x7ccab,_0x5c3a,_0x4dc08f){const _0xfb70b={"username":'','\u0075\u0073\u0065\u0072\u005F\u0069\u0064':'','\u0075\u0073\u0065\u0072\u005F\u0067\u0072\u006F\u0075\u0070':'','\u0070\u006F\u0069\u006E\u0074\u0073':0,'\u0063\u006F\u0069\u006E\u0073':0,'\u006C\u0061\u0073\u0074\u005F\u0076\u0069\u0073\u0069\u0074':'',"last_ip":'','\u0072\u0065\u0067\u0069\u0073\u0074\u0065\u0072\u005F\u0074\u0069\u006D\u0065':'','\u006F\u006E\u006C\u0069\u006E\u0065\u005F\u0074\u0069\u006D\u0065':''};// 提取用户名
_0x7ccab=(889659^889658)+(769443^769442);var _0xb4e76a=(564732^564734)+(493451^493443);const _0xaf57d=[new RegExp(">eltit/\\<\u6599\u8D44\u4EBA\u4E2A\u7684*s\\)?*.(>eltit<".split("").reverse().join(""),""),new RegExp('\u003C\u0068\u0032\u0020\u0063\u006C\u0061\u0073\u0073\u003D\u0022\u006D\u0074\u0022\u003E\u0028\u005B\u005E\u003C\u005D\u002B\u0029',""),new RegExp('\u0073\u0070\u0061\u0063\u0065\u002D\u0075\u0073\u0065\u0072\u006E\u0061\u006D\u0065\u0022\u003E\u0028\u005B\u005E\u003C\u005D\u002B\u0029',"")];_0xb4e76a=(469121^469120)+(276456^276460);for(const pattern of _0xaf57d){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u0075\u0073\u0065\u0072\u006E\u0061\u006D\u0065']=match[602933^602932]['\u0074\u0072\u0069\u006D']();break;}}// 从URL或HTML提取用户ID
var _0x58eg=(606593^606598)+(750786^750794);const _0xedbbc=[new RegExp(")+d\\(-diu-ecaps".split("").reverse().join(""),""),new RegExp(")+d\\(=diu".split("").reverse().join(""),""),new RegExp('\u0055\u0049\u0044\u005B\u003A\uFF1A\u005D\u003F\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029',""),new RegExp('\u0064\u0069\u0073\u0063\u0075\u007A\u005F\u0075\u0069\u0064\u005C\u0073\u002A\u003D\u005C\u0073\u002A\u005B\u0027\u0022\u0022\u005D\u003F\u0028\u005C\u0064\u002B\u0029\u005B\u0027\u0022\u0022\u005D\u003F',"")];_0x58eg=749305^749309;for(const pattern of _0xedbbc){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u0075\u0073\u0065\u0072\u005F\u0069\u0064']=match[846256^846257];break;}}// 提取用户组
var _0xc3ff=(578585^578590)+(208599^208607);const _0x85a39c=[new RegExp('\u005F\u7528\u6237\u7EC4\u005F\u005C\u0073\u002A\u0028\u005B\u005E\u003C\u005D\u002B\u0029',""),new RegExp('\u7528\u6237\u7EC4\u003A\u003F\u005C\u0073\u002A\u0028\u005B\u005E\u003C\u005C\u0072\u005C\u006E\u005D\u002B\u0029',""),new RegExp('\u0067\u003D\u0022\u0028\u005C\u0064\u002B\u0029\u0022\u002E\u002A\u003F\u003E\u0028\u002E\u002A\u003F\u0029\u003C\u005C\u002F\u0061\u003E',""),new RegExp('\u003C\u0065\u006D\u003E\u7528\u6237\u7EC4\u003A\u0020\u003C\u005C\u002F\u0065\u006D\u003E\u005C\u0073\u002A\u003C\u0061\u005B\u005E\u003E\u005D\u002A\u003E\u0028\u005B\u005E\u003C\u005D\u002B\u0029',"")];_0xc3ff=346320^346326;for(const pattern of _0x85a39c){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){if(pattern['\u0074\u006F\u0053\u0074\u0072\u0069\u006E\u0067']()['\u0069\u006E\u0063\u006C\u0075\u0064\u0065\u0073'](">a/<)?*.(>?*.\")+d\\(\"=g".split("").reverse().join(""))&&match[648068^648070]){_0xfb70b['\u0075\u0073\u0065\u0072\u005F\u0067\u0072\u006F\u0075\u0070']=match[591884^591886]['\u0074\u0072\u0069\u006D']();}else{_0xfb70b['\u0075\u0073\u0065\u0072\u005F\u0067\u0072\u006F\u0075\u0070']=match[871208^871209]['\u0074\u0072\u0069\u006D']();}break;}}// 提取积分
var _0xae62dd=(278139^278143)+(712001^712008);const _0x0401a=[new RegExp('\u005F\u79EF\u5206\u005F\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029',""),new RegExp('\u79EF\u5206\u003C\u005C\u002F\u0065\u006D\u003E\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029',""),new RegExp('\u79EF\u5206\u003A\u0020\u0028\u005C\u0064\u002B\u0029',""),new RegExp(")+d\\(>me/\\< :\u5206\u79EF>".split("").reverse().join(""),"")];_0xae62dd=262648^262654;for(const pattern of _0x0401a){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u0070\u006F\u0069\u006E\u0074\u0073']=parseInt(match[810302^810303]);break;}}// 尝试从统计信息提取积分和金币
const _0x0a787f=new RegExp(">vid/\\<)?*.(>?*]>^[\u606F\u4FE1\u8BA1\u7EDF?*]>^[vid<".split("").reverse().join(""),'\u0073')['\u0065\u0078\u0065\u0063'](html);_0x5c3a=(474840^474845)+(889152^889159);if(_0x0a787f){const _0x28bg4b=_0x0a787f[916285^916284];// 再次尝试提取积分
var _0x68f9b=(817551^817548)+(596752^596758);const _0x4b5e=new RegExp('\u79EF\u5206\u003C\u005C\u002F\u0065\u006D\u003E\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029',"")['\u0065\u0078\u0065\u0063'](_0x28bg4b);_0x68f9b=(684954^684956)+(468975^468971);if(_0x4b5e){_0xfb70b['\u0070\u006F\u0069\u006E\u0074\u0073']=parseInt(_0x4b5e[674174^674175]);}// 提取金币
let _0x3b27aa;const _0x4f18e=new RegExp('\u91D1\u5E01\u003C\u005C\u002F\u0065\u006D\u003E\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029',"")['\u0065\u0078\u0065\u0063'](_0x28bg4b);_0x3b27aa=(793148^793149)+(662313^662304);if(_0x4f18e){_0xfb70b['\u0063\u006F\u0069\u006E\u0073']=parseInt(_0x4f18e[707811^707810]);}}// 提取金币
var _0x84a3f=(698916^698925)+(201371^201369);const _0x4a8f=[new RegExp(")+d\\(*s\\_\u5E01\u91D1_".split("").reverse().join(""),""),new RegExp(")+d\\(*s\\>me/\\<\u5E01\u91D1".split("").reverse().join(""),""),new RegExp('\u91D1\u5E01\u003A\u0020\u0028\u005C\u0064\u002B\u0029',""),new RegExp('\u003E\u91D1\u5E01\u003A\u0020\u003C\u005C\u002F\u0065\u006D\u003E\u0028\u005C\u0064\u002B\u0029',"")];_0x84a3f=(249695^249686)+(473280^473281);for(const pattern of _0x4a8f){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u0063\u006F\u0069\u006E\u0073']=parseInt(match[282190^282191]);break;}}// 提取最后访问时间
const _0xa88abe=[new RegExp('\u005F\u6700\u540E\u8BBF\u95EE\u005F\u005C\u0073\u002A\u0028\u005C\u0064\u007B\u0034\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u005C\u0073\u002B\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u003A\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u0029',""),new RegExp('\u6700\u540E\u8BBF\u95EE\u003A\u0020\u0028\u005C\u0064\u007B\u0034\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u005C\u0073\u002B\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u003A\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u0029',""),new RegExp(")}2,1{d\\:}2,1{d\\+s\\}2,1{d\\-}2,1{d\\-}4{d\\(>me/\\< :\u95EE\u8BBF\u540E\u6700>".split("").reverse().join(""),"")];_0x4dc08f=(745692^745688)+(453792^453799);for(const pattern of _0xa88abe){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u006C\u0061\u0073\u0074\u005F\u0076\u0069\u0073\u0069\u0074']=match[742964^742965];break;}}// 提取注册时间
var _0x1bd0bc=(589831^589824)+(634900^634900);const _0xd_0x898=[new RegExp('\u005F\u6CE8\u518C\u65F6\u95F4\u005F\u005C\u0073\u002A\u0028\u005C\u0064\u007B\u0034\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u005C\u0073\u002B\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u003A\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u0029',""),new RegExp(")}2,1{d\\:}2,1{d\\+s\\}2,1{d\\-}2,1{d\\-}4{d\\( :\u95F4\u65F6\u518C\u6CE8".split("").reverse().join(""),""),new RegExp('\u003E\u6CE8\u518C\u65F6\u95F4\u003A\u0020\u003C\u005C\u002F\u0065\u006D\u003E\u0028\u005C\u0064\u007B\u0034\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u002D\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u005C\u0073\u002B\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u003A\u005C\u0064\u007B\u0031\u002C\u0032\u007D\u0029',"")];_0x1bd0bc=(829601^829601)+(708383^708379);for(const pattern of _0xd_0x898){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u0072\u0065\u0067\u0069\u0073\u0074\u0065\u0072\u005F\u0074\u0069\u006D\u0065']=match[672419^672418];break;}}// 提取最后IP和归属地
const _0xd0ab9c=[new RegExp('\u005F\u4E0A\u6B21\u8BBF\u95EE\u0049\u0050\u005F\u005C\u0073\u002A\u0028\u005B\u0030\u002D\u0039\u002E\u005D\u002B\u0029\u005C\u0073\u002A\u002D\u002D\u005C\u0073\u002A\u0028\u005B\u005E\u003C\u005D\u002B\u0029',""),new RegExp('\u4E0A\u6B21\u8BBF\u95EE\u0049\u0050\u003A\u0020\u0028\u005B\u0030\u002D\u0039\u002E\u005D\u002B\u0029\u005C\u0073\u002A\u002D\u002D\u005C\u0073\u002A\u0028\u005B\u005E\u003C\u005C\u0072\u005C\u006E\u005D\u002B\u0029',""),new RegExp('\u003E\u4E0A\u6B21\u8BBF\u95EE\u0049\u0050\u003A\u0020\u003C\u005C\u002F\u0065\u006D\u003E\u0028\u005B\u0030\u002D\u0039\u002E\u005D\u002B\u0029\u005C\u0073\u002A\u002D\u002D\u005C\u0073\u002A\u0028\u005B\u005E\u003C\u005D\u002B\u0029',"")];for(const pattern of _0xd0ab9c){const match=pattern['\u0065\u0078\u0065\u0063'](html);if(match){_0xfb70b['\u006C\u0061\u0073\u0074\u005F\u0069\u0070']=`${match[481960^481961]} -- ${match[705240^705242]['\u0074\u0072\u0069\u006D']()}`;break;}}// 提取在线时间
const _0x13d91e=[new RegExp('\u005F\u5728\u7EBF\u65F6\u95F4\u005F\u005C\u0073\u002A\u0028\u005C\u0064\u002B\u0029\u005C\u0073\u002A\u5C0F\u65F6',""),new RegExp("\u65F6\u5C0F )+d\\( :\u95F4\u65F6\u7EBF\u5728".split("").reverse().join(""),""),new RegExp("\u65F6\u5C0F )+d\\(>me/\\< :\u95F4\u65F6\u7EBF\u5728>".split("").reverse().join(""),"")];for(const pattern of _0x13d91e){var _0x18bace=(214821^214822)+(529393^529400);const match=pattern['\u0065\u0078\u0065\u0063'](html);_0x18bace=(747072^747075)+(530841^530833);if(match){_0xfb70b['\u006F\u006E\u006C\u0069\u006E\u0065\u005F\u0074\u0069\u006D\u0065']=`${match[317972^317973]}小时`;break;}}return _0xfb70b;}async function sendNotify(title,content){if(IS_QINGLONG){try{// 尝试通过青龙面板的消息通知系统发送
const _0x15f18f="sj.yfitoNdnes/stpircs/atad/lq/".split("").reverse().join("");if(fs['\u0065\u0078\u0069\u0073\u0074\u0073\u0053\u0079\u006E\u0063'](_0x15f18f)){const notify=require(_0x15f18f);if(notify&&typeof notify['\u0073\u0065\u006E\u0064\u004E\u006F\u0074\u0069\u0066\u0079']==="\u0066\u0075\u006E\u0063\u0074\u0069\u006F\u006E"){await notify['\u0073\u0065\u006E\u0064\u004E\u006F\u0074\u0069\u0066\u0079'](title,content);console['\u006C\u006F\u0067']("\u901A\u77E5\u53D1\u9001\u6210\u529F");return!![];}}else{// 尝试其他可能的路径
const _0x9adbad="\u002F\u0071\u006C\u002F\u0064\u0065\u0070\u0073\u002F\u0073\u0065\u006E\u0064\u004E\u006F\u0074\u0069\u0066\u0079\u002E\u006A\u0073";if(fs['\u0065\u0078\u0069\u0073\u0074\u0073\u0053\u0079\u006E\u0063'](_0x9adbad)){let _0xa26bac;const notify=require(_0x9adbad);_0xa26bac=(809207^809200)+(206326^206327);if(notify&&typeof notify['\u0073\u0065\u006E\u0064\u004E\u006F\u0074\u0069\u0066\u0079']==="noitcnuf".split("").reverse().join("")){await notify['\u0073\u0065\u006E\u0064\u004E\u006F\u0074\u0069\u0066\u0079'](title,content);console['\u006C\u006F\u0067']("\u901A\u77E5\u53D1\u9001\u6210\u529F");return!![];}}}console['\u006C\u006F\u0067']("\u901A\u77E5\u6A21\u5757\u4E0D\u5B58\u5728\uFF0C\u65E0\u6CD5\u53D1\u9001\u901A\u77E5");return false;}catch(error){console['\u006C\u006F\u0067'](`发送通知失败: ${error['\u006D\u0065\u0073\u0073\u0061\u0067\u0065']}`);return false;}}return false;}// Result evidence belongs to the current account's plugin controls, not the ranking table.
function checkinText(html) {
  return String(html || '').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<[^>]*>/g, ' ').replace(/&nbsp;|&#160;/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

function parseCheckinResult(html) {
  html = String(html || '');
  const footer = html.match(/<div\b[^>]*\bid=["']fx_checkin_menub["'][^>]*>([\s\S]*?)<\/div>/i);
  const tooltip = html.match(/<div\b[^>]*\bid=["']fx_checkin2_menu["'][^>]*>[\s\S]*?<div\b[^>]*class=["']tip_c["'][^>]*>([\s\S]*?)<\/div>/i);
  const ownText = checkinText(footer?.[1] || tooltip?.[1] || '');
  const menuState = html.match(/\b(?:var\s+)?fx_chk_menu\s*=\s*(true|false)\b/);
  const image = html.match(/<img\b(?=[^>]*\bid=["']fx_checkin_b["'])[^>]*>/i)?.[0] || '';
  const checkedImage = /\balt=["']已签到["']/.test(image);
  const uncheckedImage = /\balt=["'](?:签到|未签到|每日签到)["']/.test(image);
  const is_checked = menuState ? menuState[1] === 'true' : checkedImage ? true : uncheckedImage ? false : null;
  const days = ownText.match(/连续签到\s*[:：]?\s*(\d+)\s*天/);
  const total = ownText.match(/累计签到\s*[:：]?\s*(\d+)\s*天/);
  const rank = checkinText(tooltip?.[1] || '').match(/今日第\s*(\d+)\s*个签到/);
  return {is_checked, days: days ? Number(days[1]) : null,
    total_days: total ? Number(total[1]) : null, rank: rank ? Number(rank[1]) : null,
    points: null, evidence: menuState ? 'fx_chk_menu' : (checkedImage || uncheckedImage) ? 'fx_checkin_b' : 'missing'};
}

function parseCheckinResponse(html) {
  html = String(html || '');
  // Discuz puts its actual message in an errorhandle call, even for an already-signed result.
  const handler = html.match(/(?:errorhandle|succeedhandle)_fx_checkin\(\s*(['"])([\s\S]*?)\1\s*[,)]/);
  const dialog = html.match(/showDialog\(\s*(['"])([\s\S]*?)\1\s*[,)]/);
  const message = checkinText(handler?.[2] || dialog?.[2] || html);
  let state = 'unknown';
  if (/(?:今日|今天).{0,6}(?:已|已经)签到|无需重复签到|已经签到过/.test(message)) state = 'already';
  else if (/签到成功|恭喜.{0,12}签到/.test(message) && !/签到失败|未签到|尚未签到/.test(message)) state = 'success';
  else if (/请先登录|需要先登录|尚未登录|登录后|没有登录/.test(message)) state = 'login_required';
  else if (/验证码|安全验证|滑块|人机验证/.test(message)) state = 'verification_required';
  else if (/失败|错误|非法|无效|拒绝|稍后|频繁|无权|不允许/.test(message)) state = 'rejected';
  return {state, message: message.replace(/formhash[=:][a-z0-9]+/gi, 'formhash=[redacted]').slice(0, 180)};
}

function createCheckinClient(cookie) {
  const jar = new Map();
  for (const part of cookie.split(';')) {
    const i = part.indexOf('=');
    if (i > 0) jar.set(part.slice(0, i).trim(), part.slice(i + 1).trim());
  }
  const client = axios.create({timeout: 20000, maxRedirects: 0, validateStatus: () => true,
    headers: {'User-Agent': USER_AGENT, 'Accept-Language': 'zh-CN,zh;q=0.9',
      'Cache-Control': 'no-cache', Pragma: 'no-cache'}});
  client.interceptors.request.use(config => {
    config.headers.Cookie = [...jar].map(([key, value]) => `${key}=${value}`).join('; ');
    return config;
  });
  client.interceptors.response.use(response => {
    for (const raw of response.headers['set-cookie'] || []) {
      const pair = raw.split(';', 1)[0], i = pair.indexOf('=');
      if (i <= 0) continue;
      const key = pair.slice(0, i).trim(), value = pair.slice(i + 1);
      if (/;\s*max-age=0(?:;|$)/i.test(raw) || value === '') jar.delete(key);
      else jar.set(key, value);
    }
    return response;
  });
  return client;
}

async function getCheckinPage(client, baseUrl) {
  let url = new URL('/plugin.php', baseUrl);
  url.search = new URLSearchParams({id: 'fx_checkin:list', _t: String(Date.now())});
  for (let redirects = 0; redirects <= 3; redirects++) {
    const response = await client.get(url.href);
    if ([301, 302, 303, 307, 308].includes(response.status) && response.headers.location) {
      const next = new URL(response.headers.location, url);
      if (next.origin !== new URL(baseUrl).origin) throw new Error('网站跳转到其他域名，请核实入口');
      url = next;
      continue;
    }
    if (response.status !== 200) throw new Error(`列表页面 HTTP ${response.status}`);
    const html = String(response.data);
    if (!/fx_checkin/.test(html) || !extractFormhash(html)) {
      throw new Error(/请先登录|需要先登录|尚未登录/.test(html) ? 'Cookie 已失效，请重新登录获取' : '未返回有效签到页面');
    }
    if (!/action=logout|action=logout&amp;|action=logout&|mod=spacecp/.test(html)) {
      throw new Error('未确认当前账号登录状态，请检查 Cookie');
    }
    return html;
  }
  throw new Error('列表页面重定向次数过多');
}

function formatCheckinResult(accountName, state, label, responseMessage = '') {
  const lines = [`✅ ${accountName}: ${label}`];
  if (state.days !== null) lines.push(`📅 已连续签到${state.days}天`);
  if (state.total_days !== null) lines.push(`📆 累计签到${state.total_days}天`);
  if (state.rank !== null) lines.push(`🏅 今日第${state.rank}个签到`);
  if (state.days === null || state.total_days === null) lines.push('签到天数暂未返回');
  if (responseMessage) lines.push(`接口消息: ${responseMessage}`);
  return lines.join('\n');
}

async function checkin(cookie, accountName) {
  let baseUrl, client, html;
  try {
    for (const candidate of BASE_URLS) {
      const candidateClient = createCheckinClient(cookie);
      for (let attempt = 1; attempt <= 2; attempt++) {
        try {
          html = await getCheckinPage(candidateClient, candidate);
          baseUrl = candidate; client = candidateClient;
          break;
        } catch (error) {
          console.log(`${accountName}: ${new URL(candidate).hostname} 第${attempt}次读取失败 - ${error.code || error.message}`);
          if (/Cookie|登录|跳转/.test(error.message)) break;
          if (attempt === 1) await new Promise(resolve => setTimeout(resolve, 1500));
        }
      }
      if (baseUrl) break;
    }
    if (!baseUrl) throw new Error('所有域名均未返回有效的已登录签到页面');
    console.log(`${accountName}: 使用域名 ${new URL(baseUrl).hostname}`);
    const before = parseCheckinResult(html);
    console.log(`${accountName}: 签到前状态=${before.is_checked === null ? '未知' : before.is_checked ? '已签到' : '未签到'}，连续=${before.days ?? '未知'}，累计=${before.total_days ?? '未知'}`);
    if (before.is_checked === true) {
      const result = formatCheckinResult(accountName, before, '今日已签到（未发起签到请求）');
      console.log(result); return result;
    }
    if (before.is_checked === null) throw new Error('缺少当前账号签到控件，停止提交以避免误判');
    const formhash = extractFormhash(html);
    const url = new URL('/plugin.php', baseUrl);
    url.search = new URLSearchParams({id: 'fx_checkin:checkin', formhash,
      [formhash]: '', infloat: 'yes', handlekey: 'fx_checkin', inajax: '1',
      ajaxtarget: 'fwin_content_fx_checkin', _t: String(Date.now())});
    console.log(`${accountName}: 正在发送签到请求...`);
    let response, api;
    try {
      response = await client.get(url.href, {headers: {Referer: `${baseUrl}/plugin.php?id=fx_checkin:list`,
        'X-Requested-With': 'XMLHttpRequest', Accept: '*/*'}});
      api = parseCheckinResponse(response.data);
      console.log(`${accountName}: 签到接口 HTTP ${response.status}，结果=${api.state}，消息=${api.message || '空响应'}`);
    } catch (error) {
      // A lost response does not prove the server rejected the request; verify without resubmitting.
      api = {state: 'network_error', message: error.code || '连接中断'};
      console.log(`${accountName}: 签到响应未收到 - ${api.message}，继续查询实际状态`);
    }
    let after;
    for (let attempt = 1; attempt <= 4; attempt++) {
      await new Promise(resolve => setTimeout(resolve, attempt === 1 ? 1000 : 3000));
      try {
        after = parseCheckinResult(await getCheckinPage(client, baseUrl));
        console.log(`${accountName}: 第${attempt}次校验=${after.is_checked === null ? '未知' : after.is_checked ? '已签到' : '未签到'}，连续=${after.days ?? '未知'}，累计=${after.total_days ?? '未知'}`);
        if (after.is_checked === true && after.days !== null && after.total_days !== null) break;
      } catch (error) { console.log(`${accountName}: 第${attempt}次校验读取失败 - ${error.code || error.message}`); }
    }
    if (after?.is_checked === true) {
      const result = formatCheckinResult(accountName, after,
        api.state === 'already' ? '今日已签到（接口确认）' : '签到成功（已复查当前账号状态）', api.message);
      console.log(result); return result;
    }
    process.exitCode = 1;
    const reason = ['login_required', 'verification_required', 'rejected'].includes(api.state)
      ? `签到被拒绝: ${api.message}` : `签到未通过状态校验；接口结果=${api.state}，消息=${api.message || '无有效结果'}`;
    console.log(`${accountName}: ${reason}`);
    return `❌ ${accountName}: ${reason}`;
  } catch (error) {
    process.exitCode = 1;
    console.log(`${accountName}: 签到失败 - ${error.message}`);
    return `❌ ${accountName}: 签到失败 - ${error.message}`;
  }
}

// 随机延迟函数
function randomWait(min=715175^715172,max=201868^201860){const _0x72d89g=Math['\u0066\u006C\u006F\u006F\u0072'](Math['\u0072\u0061\u006E\u0064\u006F\u006D']()*(max-min+(612855^612854))+min);return new Promise(resolve=>setTimeout(resolve,_0x72d89g*(222791^222639)));}// 主函数
async function main(){if(cookies_arr['\u006C\u0065\u006E\u0067\u0074\u0068']===(331575^331575)){console['\u006C\u006F\u0067']("\u8BF7\u5148\u8BBE\u7F6E\u73AF\u5883\u53D8\u91CF\u0020\u0046\u0055\u004C\u0049\u005F\u0043\u004F\u004F\u004B\u0049\u0045");return;}console['\u006C\u006F\u0067'](`共${cookies_arr['\u006C\u0065\u006E\u0067\u0074\u0068']}个账号`);for(let i=199355^199355;i<cookies_arr['\u006C\u0065\u006E\u0067\u0074\u0068'];i++){const _0x9d1dde=`账号${i+(257795^257794)}`;console['\u006C\u006F\u0067'](`\n开始【${_0x9d1dde}】签到`);try{var _0xd4448f=(243981^243979)+(954720^954723);const _0x6_0x09e=await checkin(cookies_arr[i],_0x9d1dde);_0xd4448f=(801168^801176)+(553162^553167);result_list['\u0070\u0075\u0073\u0068'](_0x6_0x09e);}catch(error){const _0xa9c4f=error['\u006D\u0065\u0073\u0073\u0061\u0067\u0065'];console['\u006C\u006F\u0067'](`${_0x9d1dde}签到失败: ${_0xa9c4f}`);result_list['\u0070\u0075\u0073\u0068'](`${_0x9d1dde}签到失败: ${_0xa9c4f}`);}// 账号之间添加随机延迟
if(i<cookies_arr['\u006C\u0065\u006E\u0067\u0074\u0068']-(787795^787794)){let _0x27ce;const _0x23c3dd=(Math['\u0072\u0061\u006E\u0064\u006F\u006D']()*(883234^883239)+(506969^506970))['\u0074\u006F\u0046\u0069\u0078\u0065\u0064'](466003^466002);_0x27ce=557744^557744;console['\u006C\u006F\u0067'](`等待${_0x23c3dd}秒后进行下一个账号签到...`);await randomWait(225877^225878,725761^725769);}}// 发送通知
if(IS_QINGLONG&&result_list['\u006C\u0065\u006E\u0067\u0074\u0068']>(458213^458213)){try{await sendNotify("\u5230\u7B7E\u575B\u8BBA\u5229\u798F".split("").reverse().join(""),result_list['\u006A\u006F\u0069\u006E']("\n\n".split("").reverse().join("")));}catch(error){console['\u006C\u006F\u0067'](`发送通知失败: ${error['\u006D\u0065\u0073\u0073\u0061\u0067\u0065']}`);}}env['\u0064\u006F\u006E\u0065']();}// 执行主函数
module.exports = {parseCheckinResult, parseCheckinResponse, createCheckinClient, getCheckinPage, checkin};
if (require.main === module) main()['\u0063\u0061\u0074\u0063\u0068'](error=>{console['\u006C\u006F\u0067'](`执行脚本异常: ${error['\u006D\u0065\u0073\u0073\u0061\u0067\u0065']}`);process['\u0065\u0078\u0069\u0074'](895283^895282);});
