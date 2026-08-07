// name:海信爱家
/**
 * 海信爱家任务中心 - 青龙自动化脚本
 * cron: 40 11,16 * * *
 * 变量名：
 *   WX_ID (统一变量，兼容旧变量 hsaj)
 *
 * 变量格式（仅 refreshToken）：
 *   多账号支持：换行 / & / @ 分隔
 *   单账号：refreshToken[#customerId#phone#remark#deviceId]
 *   最简只填 refreshToken 即可，其余字段可留空
 *
 * refreshToken 抓包说明：
 *   1) 先清理并重新登录海信爱家小程序
 *   2) 开启抓包后执行登录
 *   3) 在响应里定位链接：
 *      https://public-wxtv.hismarttv.com/weixintv/oauth/login4MiniAPPByPhone
 *   4) 从该响应 JSON 提取 refreshToken
 *
 * 说明：
 *   1) 签名算法已完整内嵌 sign.js（X-Sign-For + appKey）
 *   2) 每次优先尝试 refreshToken 续期，最大化 token 可用时间
 *   3) 自动流程：任务列表 -> 尝试完成未完成任务 -> 签到 -> 抽奖 -> 查询积分前后变化
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { getSingleCode } = require('./getCode');
const sign = (() => {
  const module = { exports: {} };
  const exports = module.exports;
var r = function(v){return typeof v};

function t(r, n) {
  var i = e();
  return (t = function(r, t) {
    return i[r -= 280]
  })(r, n)
}

function e() {
  var r = ["charCodeAt", "substring", "join", "getSignStrWithJSON", "&keeptime=", "SerializableCipher", "exports", "splice", "Z6rn", "videoUrl is required", "WordArray", "_doFinalize", "salt", "JDh5", "key", "algo", "ceil", "Pkcs7", "pZxL", "addAntiLeech", "PasswordBasedCipher", "2671428oJsGUf", "filter", "map", "Chin", "appKey", "compute", "_minBufferSize", "auth_key=", "indexOf", "_createHelper", "mixIn", "sin", "AES", "blockSize", "Base", "appKey is required", "_hasher", "_hash", "MORZ", "_keyPriorReset", "_invKeySchedule", "keyF", "5301CmmsbP", "bfCL", "_data", "_ENC_XFORM_MODE", "appSecret not found", "ivSize", "_oKey", "Malformed UTF-8 data", "myVidaa", "hasOwnProperty", "_doCryptBlock", "apply", "_cipher", "CBC", "_parse", "createEncryptor", "erWs", "mode", "toString", "27910pdCbtw", "replace", "iterations", "length", "stringify", "Native crypto module could not be used to get secure random number.", "finalize", "$super", "HmacMD5", "random", "keySize", "slice", "_xformMode", "361892hnpvLp", "push", "sigBytes", "v65Q", "Cent", "clone", "2115702eTTkxZ", "CipherParams", "OpenSSL", "_doReset", "formatter", "aNet", "1287874xExyGS", "_mode", "min", "_reverseMap", "appKey not found", "Utf8", "HmacSHA1", "update", "postAndJSON", "4vR_", "anti-leech-vr", "hasher", "KCak", "Hex", "charAt", "_nDataBytes", "_keySchedule", "BufferedBlockAlgorithm", "extend", "unpad", "string", "undefined", "fromCharCode", "clamp", "SHA1", "execute", "wsSecret=", "Hasher", "call", "create", "Cipher", "getRandomValues", "Encryptor", "default", "_append", "encrypt", "max", "parse", "encryptByAppKey", "MD5", "readInt32LE", "lib", "function", "createDecryptor", "randomBytes", "_iv", "Rbku", "Base64", "_key", "now", "ikRF", "HMAC", "Latin1", "_process", "5BWn", "BlockCipher", "EvpKDF", "decrypt", "words", "_doProcessBlock", "_createHmacHelper", "iWxj", "enc", "ciphertext", "45fRFxTw", "5235328EIRPOP", "keys", "3864426sYgQAs", "cfg", "prototype", "secret", "sign", "reset", "init", "object", "1PsYGBb", "crypto", "_iKey", "BlockCipherMode", "concat", "decryptByAppKey", "flush", "Decryptor", "_DEC_XFORM_MODE", "msCrypto", "format", "floor", "_nRounds", "padding", "p+SM", "pad", "sort"];
  return (e = function() {
    return r
  })()
}(function(r, n) {
  for (var i = t, o = e();;) try {
    if (697297 == -parseInt(i(300)) / 1 * (-parseInt(i(338)) / 2) + parseInt(i(398)) / 3 + -parseInt(i(392)) / 4 * (parseInt(i(289)) / 5) + parseInt(i(292)) / 6 + -parseInt(i(404)) / 7 + parseInt(i(290)) / 8 + parseInt(i(360)) / 9 * (-parseInt(i(379)) / 10)) break;
    o.push(o.shift())
  } catch (r) {
    o.push(o.shift())
  }
})(),
function(e, n) {
  var i = t;
  ("undefined" == typeof exports ? "undefined" : r(exports)) === i(299) && "undefined" != typeof module ? module[i(323)] = n() : ("undefined" == typeof define ? "undefined" : r(define)) === i(446) && define.amd ? define(n) : (e = ("undefined" == typeof globalThis ? "undefined" : r(globalThis)) !== i(425) ? globalThis : e || self).jhkSign = n()
}(void 0, (function() {
  var e = t,
    n = ("undefined" == typeof globalThis ? "undefined" : r(globalThis)) !== e(425) ? globalThis : ("undefined" == typeof window ? "undefined" : r(window)) !== e(425) ? window : ("undefined" == typeof global ? "undefined" : r(global)) !== e(425) ? global : "undefined" != typeof self ? self : {};

  function i(r) {
    var t = e;
    return r && r.__esModule && Object[t(294)][t(369)][t(432)](r, "default") ? r[t(437)] : r
  }
  var o = {
    exports: {}
  };

  function a(r) {
    throw new Error('Could not dynamically require "' + r + '". Please configure the dynamicRequireTargets or/and ignoreDynamicRequires option of @rollup/plugin-commonjs appropriately for this require call to work.')
  }
  var s, c, u, f = {
    exports: {}
  };

  function h() {
    var i, o = e;
    return s || (s = 1, f[t(323)] = i = i || function(e, i) {
      var o, s = t;
      if (("undefined" == typeof window ? "undefined" : r(window)) !== s(425) && window[s(301)] && (o = window[s(301)]), "undefined" != typeof self && self.crypto && (o = self[s(301)]), ("undefined" == typeof globalThis ? "undefined" : r(globalThis)) !== s(425) && globalThis[s(301)] && (o = globalThis.crypto), !o && ("undefined" == typeof window ? "undefined" : r(window)) !== s(425) && window.msCrypto && (o = window[s(309)]), !o && r(n) !== s(425) && n.crypto && (o = n.crypto), !o && r(a) === s(446)) try {
        o = require(s(301))
      } catch (e) {}
      var c = function() {
          var r = s;
          if (o) {
            if ("function" == typeof o[r(435)]) try {
              return o[r(435)](new Uint32Array(1))[0]
            } catch (r) {}
            if ("function" == typeof o[r(448)]) try {
              return o[r(448)](4)[r(444)]()
            } catch (r) {}
          }
          throw new Error(r(384))
        },
        u = Object[s(433)] || function() {
          function r() {}
          return function(e) {
            var n, i = t;
            return r[i(294)] = e, n = new r, r[i(294)] = null, n
          }
        }(),
        f = {},
        h = f.lib = {},
        p = h[s(352)] = {
          extend: function(r) {
            var e = t,
              n = u(this);
            return r && n[e(348)](r), (!n[e(369)](e(298)) || this[e(298)] === n[e(298)]) && (n[e(298)] = function() {
              var r = e;
              n[r(386)][r(298)].apply(this, arguments)
            }), n[e(298)][e(294)] = n, n.$super = this, n
          },
          create: function() {
            var r = t,
              e = this[r(422)]();
            return e[r(298)][r(371)](e, arguments), e
          },
          init: function() {},
          mixIn: function(r) {
            var e = t;
            for (var n in r) r[e(369)](n) && (this[n] = r[n]);
            r[e(369)](e(378)) && (this[e(378)] = r.toString)
          },
          clone: function() {
            var r = t;
            return this[r(298)][r(294)][r(422)](this)
          }
        },
        v = h[s(327)] = p[s(422)]({
          init: function(r, t) {
            var e = s;
            r = this[e(283)] = r || [], null != t ? this[e(394)] = t : this.sigBytes = 4 * r[e(382)]
          },
          toString: function(r) {
            return (r || l)[s(383)](this)
          },
          concat: function(r) {
            var t = s,
              e = this[t(283)],
              n = r[t(283)],
              i = this[t(394)],
              o = r[t(394)];
            if (this.clamp(), i % 4)
              for (var a = 0; a < o; a++) {
                var c = n[a >>> 2] >>> 24 - a % 4 * 8 & 255;
                e[i + a >>> 2] |= c << 24 - (i + a) % 4 * 8
              } else
                for (var u = 0; u < o; u += 4) e[i + u >>> 2] = n[u >>> 2];
            return this[t(394)] += o, this
          },
          clamp: function() {
            var r = s,
              t = this[r(283)],
              n = this.sigBytes;
            t[n >>> 2] &= 4294967295 << 32 - n % 4 * 8, t.length = e[r(333)](n / 4)
          },
          clone: function() {
            var r = s,
              t = p[r(397)].call(this);
            return t[r(283)] = this.words[r(390)](0), t
          },
          random: function(r) {
            for (var t = s, e = [], n = 0; n < r; n += 4) e[t(393)](c());
            return new(v[t(298)])(e, r)
          }
        }),
        d = f[s(287)] = {},
        l = d[s(417)] = {
          stringify: function(r) {
            for (var t = s, e = r.words, n = r[t(394)], i = [], o = 0; o < n; o++) {
              var a = e[o >>> 2] >>> 24 - o % 4 * 8 & 255;
              i.push((a >>> 4)[t(378)](16)), i[t(393)]((15 & a)[t(378)](16))
            }
            return i[t(319)]("")
          },
          parse: function(r) {
            for (var t = s, e = r.length, n = [], i = 0; i < e; i += 2) n[i >>> 3] |= parseInt(r.substr(i, 2), 16) << 24 - i % 8 * 4;
            return new(v[t(298)])(n, e / 2)
          }
        },
        y = d[s(456)] = {
          stringify: function(r) {
            for (var t = s, e = r[t(283)], n = r[t(394)], i = [], o = 0; o < n; o++) {
              var a = e[o >>> 2] >>> 24 - o % 4 * 8 & 255;
              i[t(393)](String[t(426)](a))
            }
            return i[t(319)]("")
          },
          parse: function(r) {
            for (var t = s, e = r[t(382)], n = [], i = 0; i < e; i++) n[i >>> 2] |= (255 & r[t(317)](i)) << 24 - i % 4 * 8;
            return new(v[t(298)])(n, e)
          }
        },
        _ = d.Utf8 = {
          stringify: function(r) {
            var t = s;
            try {
              return decodeURIComponent(escape(y[t(383)](r)))
            } catch (r) {
              throw new Error(t(367))
            }
          },
          parse: function(r) {
            return y.parse(unescape(encodeURIComponent(r)))
          }
        },
        g = h[s(421)] = p[s(422)]({
          reset: function() {
            var r = s;
            this[r(362)] = new(v[r(298)]), this[r(419)] = 0
          },
          _append: function(t) {
            var e = s;
            r(t) == e(424) && (t = _.parse(t)), this._data[e(304)](t), this._nDataBytes += t[e(394)]
          },
          _process: function(r) {
            var t, n = s,
              i = this._data,
              o = i.words,
              a = i[n(394)],
              c = this[n(351)],
              u = a / (4 * c),
              f = (u = r ? e[n(333)](u) : e[n(440)]((0 | u) - this[n(344)], 0)) * c,
              h = e[n(406)](4 * f, a);
            if (f) {
              for (var p = 0; p < f; p += c) this[n(284)](o, p);
              t = o[n(324)](0, f), i[n(394)] -= h
            }
            return new(v[n(298)])(t, h)
          },
          clone: function() {
            var r = s,
              t = p[r(397)][r(432)](this);
            return t._data = this._data[r(397)](), t
          },
          _minBufferSize: 0
        });
      h[s(431)] = g[s(422)]({
        cfg: p[s(422)](),
        init: function(r) {
          var t = s;
          this[t(293)] = this.cfg[t(422)](r), this[t(297)]()
        },
        reset: function() {
          var r = s;
          g.reset[r(432)](this), this[r(401)]()
        },
        update: function(r) {
          return this[s(438)](r), this._process(), this
        },
        finalize: function(r) {
          var t = s;
          return r && this[t(438)](r), this[t(328)]()
        },
        blockSize: 16,
        _createHelper: function(r) {
          return function(e, n) {
            var i = t;
            return new r.init(n)[i(385)](e)
          }
        },
        _createHmacHelper: function(r) {
          return function(e, n) {
            var i = t;
            return new(w.HMAC[i(298)])(r, n)[i(385)](e)
          }
        }
      });
      var w = f[s(332)] = {};
      return f
    }(Math)), f[o(323)]
  }
  o[t(323)] = (c = h(), u = t, function(r) {
    var e = t,
      n = c,
      i = n[e(445)],
      o = i.WordArray,
      a = i[e(431)],
      s = n[e(332)],
      u = [];
    ! function() {
      for (var t = e, n = 0; n < 64; n++) u[n] = 4294967296 * r.abs(r[t(349)](n + 1)) | 0
    }();
    var f = s[e(443)] = a[e(422)]({
      _doReset: function() {
        var r = e;
        this[r(355)] = new(o[r(298)])([1732584193, 4023233417, 2562383102, 271733878])
      },
      _doProcessBlock: function(r, t) {
        for (var e = 0; e < 16; e++) {
          var n = t + e,
            i = r[n];
          r[n] = 16711935 & (i << 8 | i >>> 24) | 4278255360 & (i << 24 | i >>> 8)
        }
        var o = this._hash.words,
          a = r[t + 0],
          s = r[t + 1],
          c = r[t + 2],
          f = r[t + 3],
          l = r[t + 4],
          y = r[t + 5],
          _ = r[t + 6],
          g = r[t + 7],
          w = r[t + 8],
          m = r[t + 9],
          k = r[t + 10],
          S = r[t + 11],
          x = r[t + 12],
          B = r[t + 13],
          b = r[t + 14],
          C = r[t + 15],
          E = o[0],
          z = o[1],
          M = o[2],
          R = o[3];
        E = h(E, z, M, R, a, 7, u[0]), R = h(R, E, z, M, s, 12, u[1]), M = h(M, R, E, z, c, 17, u[2]), z = h(z, M, R, E, f, 22, u[3]), E = h(E, z, M, R, l, 7, u[4]), R = h(R, E, z, M, y, 12, u[5]), M = h(M, R, E, z, _, 17, u[6]), z = h(z, M, R, E, g, 22, u[7]), E = h(E, z, M, R, w, 7, u[8]), R = h(R, E, z, M, m, 12, u[9]), M = h(M, R, E, z, k, 17, u[10]), z = h(z, M, R, E, S, 22, u[11]), E = h(E, z, M, R, x, 7, u[12]), R = h(R, E, z, M, B, 12, u[13]), M = h(M, R, E, z, b, 17, u[14]), E = p(E, z = h(z, M, R, E, C, 22, u[15]), M, R, s, 5, u[16]), R = p(R, E, z, M, _, 9, u[17]), M = p(M, R, E, z, S, 14, u[18]), z = p(z, M, R, E, a, 20, u[19]), E = p(E, z, M, R, y, 5, u[20]), R = p(R, E, z, M, k, 9, u[21]), M = p(M, R, E, z, C, 14, u[22]), z = p(z, M, R, E, l, 20, u[23]), E = p(E, z, M, R, m, 5, u[24]), R = p(R, E, z, M, b, 9, u[25]), M = p(M, R, E, z, f, 14, u[26]), z = p(z, M, R, E, w, 20, u[27]), E = p(E, z, M, R, B, 5, u[28]), R = p(R, E, z, M, c, 9, u[29]), M = p(M, R, E, z, g, 14, u[30]), E = v(E, z = p(z, M, R, E, x, 20, u[31]), M, R, y, 4, u[32]), R = v(R, E, z, M, w, 11, u[33]), M = v(M, R, E, z, S, 16, u[34]), z = v(z, M, R, E, b, 23, u[35]), E = v(E, z, M, R, s, 4, u[36]), R = v(R, E, z, M, l, 11, u[37]), M = v(M, R, E, z, g, 16, u[38]), z = v(z, M, R, E, k, 23, u[39]), E = v(E, z, M, R, B, 4, u[40]), R = v(R, E, z, M, a, 11, u[41]), M = v(M, R, E, z, f, 16, u[42]), z = v(z, M, R, E, _, 23, u[43]), E = v(E, z, M, R, m, 4, u[44]), R = v(R, E, z, M, x, 11, u[45]), M = v(M, R, E, z, C, 16, u[46]), E = d(E, z = v(z, M, R, E, c, 23, u[47]), M, R, a, 6, u[48]), R = d(R, E, z, M, g, 10, u[49]), M = d(M, R, E, z, b, 15, u[50]), z = d(z, M, R, E, y, 21, u[51]), E = d(E, z, M, R, x, 6, u[52]), R = d(R, E, z, M, f, 10, u[53]), M = d(M, R, E, z, k, 15, u[54]), z = d(z, M, R, E, s, 21, u[55]), E = d(E, z, M, R, w, 6, u[56]), R = d(R, E, z, M, C, 10, u[57]), M = d(M, R, E, z, _, 15, u[58]), z = d(z, M, R, E, B, 21, u[59]), E = d(E, z, M, R, l, 6, u[60]), R = d(R, E, z, M, S, 10, u[61]), M = d(M, R, E, z, c, 15, u[62]), z = d(z, M, R, E, m, 21, u[63]), o[0] = o[0] + E | 0, o[1] = o[1] + z | 0, o[2] = o[2] + M | 0, o[3] = o[3] + R | 0
      },
      _doFinalize: function() {
        var t = e,
          n = this[t(362)],
          i = n[t(283)],
          o = 8 * this[t(419)],
          a = 8 * n.sigBytes;
        i[a >>> 5] |= 128 << 24 - a % 32;
        var s = r.floor(o / 4294967296),
          c = o;
        i[15 + (a + 64 >>> 9 << 4)] = 16711935 & (s << 8 | s >>> 24) | 4278255360 & (s << 24 | s >>> 8), i[14 + (a + 64 >>> 9 << 4)] = 16711935 & (c << 8 | c >>> 24) | 4278255360 & (c << 24 | c >>> 8), n[t(394)] = 4 * (i[t(382)] + 1), this._process();
        for (var u = this[t(355)], f = u[t(283)], h = 0; h < 4; h++) {
          var p = f[h];
          f[h] = 16711935 & (p << 8 | p >>> 24) | 4278255360 & (p << 24 | p >>> 8)
        }
        return u
      },
      clone: function() {
        var r = e,
          t = a[r(397)][r(432)](this);
        return t[r(355)] = this[r(355)].clone(), t
      }
    });

    function h(r, t, e, n, i, o, a) {
      var s = r + (t & e | ~t & n) + i + a;
      return (s << o | s >>> 32 - o) + t
    }

    function p(r, t, e, n, i, o, a) {
      var s = r + (t & n | e & ~n) + i + a;
      return (s << o | s >>> 32 - o) + t
    }

    function v(r, t, e, n, i, o, a) {
      var s = r + (t ^ e ^ n) + i + a;
      return (s << o | s >>> 32 - o) + t
    }

    function d(r, t, e, n, i, o, a) {
      var s = r + (e ^ (t | ~n)) + i + a;
      return (s << o | s >>> 32 - o) + t
    }
    n[e(443)] = a[e(347)](f), n[e(387)] = a[e(285)](f)
  }(Math), c[u(443)]);
  var p, v, d = i(o[e(323)]),
    l = {
      exports: {}
    };
  l[t(323)] = (p = h(), v = t, function() {
    var r = t,
      e = p,
      n = e[r(445)][r(327)];

    function i(t, e, i) {
      for (var o = r, a = [], s = 0, c = 0; c < e; c++)
        if (c % 4) {
          var u = i[t[o(317)](c - 1)] << c % 4 * 2 | i[t[o(317)](c)] >>> 6 - c % 4 * 2;
          a[s >>> 2] |= u << 24 - s % 4 * 8, s++
        } return n[o(433)](a, s)
    }
    e[r(287)][r(451)] = {
      stringify: function(t) {
        var e = r,
          n = t[e(283)],
          i = t.sigBytes,
          o = this._map;
        t[e(427)]();
        for (var a = [], s = 0; s < i; s += 3)
          for (var c = (n[s >>> 2] >>> 24 - s % 4 * 8 & 255) << 16 | (n[s + 1 >>> 2] >>> 24 - (s + 1) % 4 * 8 & 255) << 8 | n[s + 2 >>> 2] >>> 24 - (s + 2) % 4 * 8 & 255, u = 0; u < 4 && s + .75 * u < i; u++) a[e(393)](o.charAt(c >>> 6 * (3 - u) & 63));
        var f = o[e(418)](64);
        if (f)
          for (; a[e(382)] % 4;) a[e(393)](f);
        return a.join("")
      },
      parse: function(t) {
        var e = r,
          n = t[e(382)],
          o = this._map,
          a = this[e(407)];
        if (!a) {
          a = this._reverseMap = [];
          for (var s = 0; s < o[e(382)]; s++) a[o[e(317)](s)] = s
        }
        var c = o[e(418)](64);
        if (c) {
          var u = t[e(346)](c); - 1 !== u && (n = u)
        }
        return i(t, n, a)
      },
      _map: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    }
  }(), p[v(287)][v(451)]);
  var y = i(l.exports),
    _ = {
      exports: {}
    };
  _.exports = h()[t(287)].Hex;
  var g, w = i(_.exports),
    m = function() {
      var n = e;

      function i(r) {
        var e = t,
          n = this;
        this[e(296)] = function(r, t) {
          var i = e;
          if (!(null == t ? void 0 : t[i(342)])) throw new Error(i(353));
          var o = n[i(295)](t[i(342)]);
          if (!o) throw new Error(i(364));
          var a = (null == t ? void 0 : t[i(412)]) ? n[i(320)](r || "", o) : n.getSignStr(r || "", o);
          return d(a)[i(378)](y)
        }, this[e(336)] = function(r, t, i) {
          var o = e;
          if (void 0 === i && (i = 15), !r) throw new Error("appKey is required");
          var a = n.secret(r);
          if (!a) throw new Error(o(408));
          if (!t) throw new Error(o(326));
          var s = t,
            c = s[o(380)](/http(s?)\:\/\/[^/]+/, "");
          if ("anti-leech-wangsu" === r) {
            var u = Math.floor(Date[o(453)]() / 1e3).toString(16),
              f = 60 * i,
              h = "".concat(a)[o(304)](c).concat(u)[o(304)](f),
              p = d(h).toString(w),
              v = -1 === s[o(346)]("?") ? "?" : "&";
            return v += o(430)[o(304)](p, "&wsTime=")[o(304)](u, o(321))[o(304)](f), "" [o(304)](s).concat(v)
          }
          if ("anti-leech-ali" === r) {
            var l = Math[o(311)](Date[o(453)]() / 1e3) + (f = 60 * i),
              y = (h = "" [o(304)](c, "-")[o(304)](l, "-")[o(304)](0, "-")[o(304)](0, "-")[o(304)](a), "" [o(304)](l, "-").concat(0, "-").concat(0, "-")[o(304)](d(h)[o(378)](w)));
            return v = -1 === s[o(346)]("?") ? "?" : "&", v += o(345).concat(y), "" [o(304)](s)[o(304)](v)
          }
          return t
        }, this.secret = r
      }
      return i[n(294)].getSignStr = function(t, e) {
        var i = n,
          o = "";
        if ("string" == typeof t) o = t;
        else {
          var a = Object[i(291)](t)[i(340)]((function(e) {
            var n = i,
              o = t[e];
            return "" === o || null == o ? "" : (r(o) === n(299) && (o = JSON[n(383)](o)), "" [n(304)](e, "=")[n(304)](o))
          }))[i(339)]((function(r) {
            return "" !== r
          }));
          a[i(316)]((function(r, t) {
            return r > t ? 1 : -1
          })), o = a[i(319)]("&")
        }
        return o[i(304)](e)
      }, i[n(294)][n(320)] = function(t, e) {
        var i = n,
          o = r(t) === i(424) ? t : JSON[i(383)](t);
        return "" [i(304)](o).concat(e)
      }, i
    }(),
    k = {
      exports: {}
    },
    S = {
      exports: {}
    },
    x = {
      exports: {}
    };
  var B, b, C = {
    exports: {}
  };

  function E() {
    var n, i, o, a, s, c, u, f, p, v, d = e;
    return b || (b = 1, S.exports = (n = h(), function() {
      var r, n, i, o, a, s, c, u, f, p = e;
      g ? x.exports : (g = 1, x.exports = (o = (i = r = h())[(n = t)(445)], a = o[n(327)], s = o[n(431)], c = i[n(332)], u = [], f = c[n(428)] = s.extend({
        _doReset: function() {
          var r = n;
          this._hash = new(a[r(298)])([1732584193, 4023233417, 2562383102, 271733878, 3285377520])
        },
        _doProcessBlock: function(r, t) {
          for (var e = this[n(355)].words, i = e[0], o = e[1], a = e[2], s = e[3], c = e[4], f = 0; f < 80; f++) {
            if (f < 16) u[f] = 0 | r[t + f];
            else {
              var h = u[f - 3] ^ u[f - 8] ^ u[f - 14] ^ u[f - 16];
              u[f] = h << 1 | h >>> 31
            }
            var p = (i << 5 | i >>> 27) + c + u[f];
            p += f < 20 ? 1518500249 + (o & a | ~o & s) : f < 40 ? 1859775393 + (o ^ a ^ s) : f < 60 ? (o & a | o & s | a & s) - 1894007588 : (o ^ a ^ s) - 899497514, c = s, s = a, a = o << 30 | o >>> 2, o = i, i = p
          }
          e[0] = e[0] + i | 0, e[1] = e[1] + o | 0, e[2] = e[2] + a | 0, e[3] = e[3] + s | 0, e[4] = e[4] + c | 0
        },
        _doFinalize: function() {
          var r = n,
            t = this[r(362)],
            e = t[r(283)],
            i = 8 * this._nDataBytes,
            o = 8 * t[r(394)];
          return e[o >>> 5] |= 128 << 24 - o % 32, e[14 + (o + 64 >>> 9 << 4)] = Math[r(311)](i / 4294967296), e[15 + (o + 64 >>> 9 << 4)] = i, t[r(394)] = 4 * e.length, this._process(), this[r(355)]
        },
        clone: function() {
          var r = n,
            t = s[r(397)].call(this);
          return t._hash = this[r(355)][r(397)](), t
        }
      }), i.SHA1 = s._createHelper(f), i[n(410)] = s[n(285)](f), r.SHA1), x[p(323)])
    }(), function() {
      var n, i, o, a, s = e;
      B || (B = 1, C[t(323)] = (o = (i = h())[(n = t)(445)][n(352)], a = i[n(287)][n(409)], void(i[n(332)][n(455)] = o[n(422)]({
        init: function(t, e) {
          var i = n;
          t = this[i(354)] = new t.init, r(e) == i(424) && (e = a[i(441)](e));
          var o = t.blockSize,
            s = 4 * o;
          e.sigBytes > s && (e = t.finalize(e)), e[i(427)]();
          for (var c = this[i(366)] = e.clone(), u = this[i(302)] = e[i(397)](), f = c[i(283)], h = u[i(283)], p = 0; p < o; p++) f[p] ^= 1549556828, h[p] ^= 909522486;
          c[i(394)] = u[i(394)] = s, this.reset()
        },
        reset: function() {
          var r = n,
            t = this[r(354)];
          t[r(297)](), t[r(411)](this._iKey)
        },
        update: function(r) {
          var t = n;
          return this[t(354)][t(411)](r), this
        },
        finalize: function(r) {
          var t = n,
            e = this[t(354)],
            i = e[t(385)](r);
          return e.reset(), e[t(385)](this[t(366)][t(397)]()[t(304)](i))
        }
      })))), C[s(323)]
    }(), i = t, o = t, c = (s = (a = n).lib)[o(352)], u = s.WordArray, p = (f = a.algo)[o(443)], v = f[o(281)] = c.extend({
      cfg: c[o(422)]({
        keySize: 4,
        hasher: p,
        iterations: 1
      }),
      init: function(r) {
        var t = o;
        this[t(293)] = this.cfg[t(422)](r)
      },
      compute: function(r, t) {
        for (var e, n = o, i = this[n(293)], a = i[n(415)].create(), s = u.create(), c = s[n(283)], f = i[n(389)], h = i[n(381)]; c[n(382)] < f;) {
          e && a[n(411)](e), e = a[n(411)](r)[n(385)](t), a[n(297)]();
          for (var p = 1; p < h; p++) e = a.finalize(e), a[n(297)]();
          s[n(304)](e)
        }
        return s[n(394)] = 4 * f, s
      }
    }), a.EvpKDF = function(r, t, e) {
      var n = o;
      return v[n(433)](e)[n(343)](r, t)
    }, n[i(281)])), S[d(323)]
  }
  var z, M, R, O = {
    exports: {}
  };

  function A() {
    var n, i, o = e;
    return z ? O.exports : (z = 1, O[t(323)] = (n = h(), E(), i = t, void(n.lib[i(434)] || function(e) {
      var o = i,
        a = n,
        s = a[o(445)],
        c = s[o(352)],
        u = s[o(327)],
        f = s.BufferedBlockAlgorithm,
        h = a.enc;
      h.Utf8;
      var p = h[o(451)],
        v = a.algo[o(281)],
        d = s[o(434)] = f[o(422)]({
          cfg: c[o(422)](),
          createEncryptor: function(r, t) {
            var e = o;
            return this[e(433)](this[e(363)], r, t)
          },
          createDecryptor: function(r, t) {
            var e = o;
            return this[e(433)](this[e(308)], r, t)
          },
          init: function(r, t, e) {
            var n = o;
            this[n(293)] = this[n(293)][n(422)](e), this[n(391)] = r, this[n(452)] = t, this[n(297)]()
          },
          reset: function() {
            var r = o;
            f[r(297)].call(this), this[r(401)]()
          },
          process: function(r) {
            var t = o;
            return this[t(438)](r), this[t(457)]()
          },
          finalize: function(r) {
            var t = o;
            return r && this._append(r), this[t(328)]()
          },
          keySize: 4,
          ivSize: 4,
          _ENC_XFORM_MODE: 1,
          _DEC_XFORM_MODE: 2,
          _createHelper: function() {
            function e(e) {
              return r(e) == t(424) ? x : k
            }
            return function(r) {
              return {
                encrypt: function(n, i, o) {
                  var a = t;
                  return e(i)[a(439)](r, n, i, o)
                },
                decrypt: function(t, n, i) {
                  return e(n).decrypt(r, t, n, i)
                }
              }
            }
          }()
        });
      s.StreamCipher = d[o(422)]({
        _doFinalize: function() {
          var r = o;
          return this[r(457)](!!r(306))
        },
        blockSize: 1
      });
      var l = a[o(377)] = {},
        y = s[o(303)] = c[o(422)]({
          createEncryptor: function(r, t) {
            var e = o;
            return this.Encryptor[e(433)](r, t)
          },
          createDecryptor: function(r, t) {
            var e = o;
            return this[e(307)][e(433)](r, t)
          },
          init: function(r, t) {
            var e = o;
            this[e(372)] = r, this[e(449)] = t
          }
        }),
        _ = l[o(373)] = function() {
          var r = o,
            t = y[r(422)]();

          function e(t, e, n) {
            var i, o = r,
              a = this[o(449)];
            a ? (i = a, this[o(449)] = void 0) : i = this._prevBlock;
            for (var s = 0; s < n; s++) t[e + s] ^= i[s]
          }
          return t[r(436)] = t[r(422)]({
            processBlock: function(t, n) {
              var i = r,
                o = this[i(372)],
                a = o[i(351)];
              e.call(this, t, n, a), o.encryptBlock(t, n), this._prevBlock = t.slice(n, n + a)
            }
          }), t[r(307)] = t[r(422)]({
            processBlock: function(t, n) {
              var i = r,
                o = this[i(372)],
                a = o[i(351)],
                s = t[i(390)](n, n + a);
              o.decryptBlock(t, n), e.call(this, t, n, a), this._prevBlock = s
            }
          }), t
        }(),
        g = (a[o(315)] = {})[o(334)] = {
          pad: function(r, t) {
            for (var e = o, n = 4 * t, i = n - r[e(394)] % n, a = i << 24 | i << 16 | i << 8 | i, s = [], c = 0; c < i; c += 4) s.push(a);
            var f = u[e(433)](s, i);
            r[e(304)](f)
          },
          unpad: function(r) {
            var t = o,
              e = 255 & r[t(283)][r.sigBytes - 1 >>> 2];
            r[t(394)] -= e
          }
        };
      s.BlockCipher = d[o(422)]({
        cfg: d.cfg[o(422)]({
          mode: _,
          padding: g
        }),
        reset: function() {
          var r, t = o;
          d[t(297)][t(432)](this);
          var e = this[t(293)],
            n = e.iv,
            i = e.mode;
          this._xformMode == this._ENC_XFORM_MODE ? r = i[t(375)] : (r = i[t(447)], this[t(344)] = 1), this[t(405)] && this._mode.__creator == r ? this[t(405)][t(298)](this, n && n.words) : (this._mode = r.call(i, this, n && n[t(283)]), this[t(405)].__creator = r)
        },
        _doProcessBlock: function(r, t) {
          this[o(405)].processBlock(r, t)
        },
        _doFinalize: function() {
          var r, t = o,
            e = this[t(293)][t(313)];
          return this[t(391)] == this[t(363)] ? (e[t(315)](this[t(362)], this.blockSize), r = this[t(457)](!0)) : (r = this[t(457)](!!t(306)), e[t(423)](r)), r
        },
        blockSize: 4
      });
      var w = s[o(399)] = c[o(422)]({
          init: function(r) {
            this[o(348)](r)
          },
          toString: function(r) {
            var t = o;
            return (r || this[t(402)])[t(383)](this)
          }
        }),
        m = (a[o(310)] = {})[o(400)] = {
          stringify: function(r) {
            var t = o,
              e = r[t(288)],
              n = r[t(329)];
            return (n ? u[t(433)]([1398893684, 1701076831])[t(304)](n)[t(304)](e) : e)[t(378)](p)
          },
          parse: function(r) {
            var t, e = o,
              n = p[e(441)](r),
              i = n[e(283)];
            return 1398893684 == i[0] && 1701076831 == i[1] && (t = u[e(433)](i[e(390)](2, 4)), i.splice(0, 4), n.sigBytes -= 16), w.create({
              ciphertext: n,
              salt: t
            })
          }
        },
        k = s[o(322)] = c[o(422)]({
          cfg: c[o(422)]({
            format: m
          }),
          encrypt: function(r, t, e, n) {
            var i = o;
            n = this[i(293)][i(422)](n);
            var a = r.createEncryptor(e, n),
              s = a[i(385)](t),
              c = a[i(293)];
            return w[i(433)]({
              ciphertext: s,
              key: e,
              iv: c.iv,
              algorithm: r,
              mode: c[i(377)],
              padding: c.padding,
              blockSize: r[i(351)],
              formatter: n[i(310)]
            })
          },
          decrypt: function(r, t, e, n) {
            var i = o;
            return n = this.cfg[i(422)](n), t = this[i(374)](t, n[i(310)]), r[i(447)](e, n)[i(385)](t[i(288)])
          },
          _parse: function(t, e) {
            return r(t) == o(424) ? e.parse(t, this) : t
          }
        }),
        S = (a.kdf = {}).OpenSSL = {
          execute: function(r, t, e, n) {
            var i = o;
            !n && (n = u[i(388)](8));
            var a = v.create({
                keySize: t + e
              })[i(343)](r, n),
              s = u.create(a[i(283)][i(390)](t), 4 * e);
            return a[i(394)] = 4 * t, w.create({
              key: a,
              iv: s,
              salt: n
            })
          }
        },
        x = s[o(337)] = k.extend({
          cfg: k[o(293)][o(422)]({
            kdf: S
          }),
          encrypt: function(r, t, e, n) {
            var i = o,
              a = (n = this[i(293)][i(422)](n)).kdf[i(429)](e, r[i(389)], r[i(365)]);
            n.iv = a.iv;
            var s = k.encrypt[i(432)](this, r, t, a[i(331)], n);
            return s[i(348)](a), s
          },
          decrypt: function(r, t, e, n) {
            var i = o;
            n = this.cfg[i(422)](n), t = this._parse(t, n[i(310)]);
            var a = n.kdf.execute(e, r[i(389)], r.ivSize, t.salt);
            return n.iv = a.iv, k.decrypt[i(432)](this, r, t, a.key, n)
          }
        })
    }())), O[o(323)])
  }
  k[t(323)] = (M = h(), E(), A(), R = t, function() {
    var r = t,
      e = M,
      n = e.lib[r(280)],
      i = e[r(332)],
      o = [],
      a = [],
      s = [],
      c = [],
      u = [],
      f = [],
      h = [],
      p = [],
      v = [],
      d = [];
    ! function() {
      for (var r = [], t = 0; t < 256; t++) r[t] = t < 128 ? t << 1 : t << 1 ^ 283;
      var e = 0,
        n = 0;
      for (t = 0; t < 256; t++) {
        var i = n ^ n << 1 ^ n << 2 ^ n << 3 ^ n << 4;
        i = i >>> 8 ^ 255 & i ^ 99, o[e] = i, a[i] = e;
        var l = r[e],
          y = r[l],
          _ = r[y],
          g = 257 * r[i] ^ 16843008 * i;
        s[e] = g << 24 | g >>> 8, c[e] = g << 16 | g >>> 16, u[e] = g << 8 | g >>> 24, f[e] = g, g = 16843009 * _ ^ 65537 * y ^ 257 * l ^ 16843008 * e, h[i] = g << 24 | g >>> 8, p[i] = g << 16 | g >>> 16, v[i] = g << 8 | g >>> 24, d[i] = g, e ? (e = l ^ r[r[r[_ ^ l]]], n ^= r[r[n]]) : e = n = 1
      }
    }();
    var l = [0, 1, 2, 4, 8, 16, 32, 64, 128, 27, 54],
      y = i[r(350)] = n[r(422)]({
        _doReset: function() {
          var t = r;
          if (!this[t(312)] || this[t(357)] !== this[t(452)]) {
            for (var e = this[t(357)] = this[t(452)], n = e[t(283)], i = e[t(394)] / 4, a = 4 * ((this._nRounds = i + 6) + 1), s = this[t(420)] = [], c = 0; c < a; c++) c < i ? s[c] = n[c] : (y = s[c - 1], c % i ? i > 6 && c % i == 4 && (y = o[y >>> 24] << 24 | o[y >>> 16 & 255] << 16 | o[y >>> 8 & 255] << 8 | o[255 & y]) : (y = o[(y = y << 8 | y >>> 24) >>> 24] << 24 | o[y >>> 16 & 255] << 16 | o[y >>> 8 & 255] << 8 | o[255 & y], y ^= l[c / i | 0] << 24), s[c] = s[c - i] ^ y);
            for (var u = this[t(358)] = [], f = 0; f < a; f++) {
              if (c = a - f, f % 4) var y = s[c];
              else y = s[c - 4];
              u[f] = f < 4 || c <= 4 ? y : h[o[y >>> 24]] ^ p[o[y >>> 16 & 255]] ^ v[o[y >>> 8 & 255]] ^ d[o[255 & y]]
            }
          }
        },
        encryptBlock: function(t, e) {
          var n = r;
          this._doCryptBlock(t, e, this[n(420)], s, c, u, f, o)
        },
        decryptBlock: function(t, e) {
          var n = r,
            i = t[e + 1];
          t[e + 1] = t[e + 3], t[e + 3] = i, this[n(370)](t, e, this[n(358)], h, p, v, d, a), i = t[e + 1], t[e + 1] = t[e + 3], t[e + 3] = i
        },
        _doCryptBlock: function(t, e, n, i, o, a, s, c) {
          for (var u = this[r(312)], f = t[e] ^ n[0], h = t[e + 1] ^ n[1], p = t[e + 2] ^ n[2], v = t[e + 3] ^ n[3], d = 4, l = 1; l < u; l++) {
            var y = i[f >>> 24] ^ o[h >>> 16 & 255] ^ a[p >>> 8 & 255] ^ s[255 & v] ^ n[d++],
              _ = i[h >>> 24] ^ o[p >>> 16 & 255] ^ a[v >>> 8 & 255] ^ s[255 & f] ^ n[d++],
              g = i[p >>> 24] ^ o[v >>> 16 & 255] ^ a[f >>> 8 & 255] ^ s[255 & h] ^ n[d++],
              w = i[v >>> 24] ^ o[f >>> 16 & 255] ^ a[h >>> 8 & 255] ^ s[255 & p] ^ n[d++];
            f = y, h = _, p = g, v = w
          }
          y = (c[f >>> 24] << 24 | c[h >>> 16 & 255] << 16 | c[p >>> 8 & 255] << 8 | c[255 & v]) ^ n[d++], _ = (c[h >>> 24] << 24 | c[p >>> 16 & 255] << 16 | c[v >>> 8 & 255] << 8 | c[255 & f]) ^ n[d++], g = (c[p >>> 24] << 24 | c[v >>> 16 & 255] << 16 | c[f >>> 8 & 255] << 8 | c[255 & h]) ^ n[d++], w = (c[v >>> 24] << 24 | c[f >>> 16 & 255] << 16 | c[h >>> 8 & 255] << 8 | c[255 & p]) ^ n[d++], t[e] = y, t[e + 1] = _, t[e + 2] = g, t[e + 3] = w
        },
        keySize: 8
      });
    e.AES = n[r(347)](y)
  }(), M[R(350)]);
  var D, H = i(k[e(323)]),
    F = {
      exports: {}
    };
  F.exports = h()[(D = t)(287)][D(409)];
  var I, T, K = i(F[e(323)]),
    P = {
      exports: {}
    };
  P[t(323)] = (I = h(), A(), I[(T = t)(315)][T(334)]);
  var q = i(P[e(323)]);

  function j(r) {
    var t = e;
    switch (r) {
      case t(368):
        return [t(416), "auQg", t(458), t(330), t(395), t(361), "7bRF", t(454)][t(319)]("");
      case "commonweb":
        return [t(356), t(450), t(286), t(314), t(413), "GxY4", t(335), t(325)][t(319)]("");
      case t(414):
        return [t(341), t(403), t(396), t(376), t(359), "orJu", "HaoK", "an"][t(319)]("");
      default:
        return ""
    }
  }
  var N = new m(j);

  function U(r, t) {
    return N[e(296)](r, t)
  }
  return U[e(336)] = function(r, t, n) {
    return void 0 === n && (n = 15), N[e(336)](r, t, n)
  }, U[e(442)] = function(r, t) {
    return function(r, t) {
      var n = e;
      if (!t) throw new Error(n(353));
      if (!r) return "";
      var i = t[n(318)](0, 16),
        o = H[n(439)](r, K.parse(t), {
          iv: K[n(441)](i),
          padding: q
        });
      return o[n(288)] ? o[n(288)][n(378)](y) : ""
    }(r, j(t))
  }, U[e(305)] = function(r, t) {
    return function(r, t) {
      var n = e;
      if (!t) throw new Error("appKey is required");
      if (!r) return "";
      var i = t[n(318)](0, 16);
      return H[n(282)](r, K[n(441)](t), {
        iv: K[n(441)](i),
        padding: q
      }).toString(K)
    }(r, j(t))
  }, U
}));
  return module.exports;
})();

const SCRIPT_NAME = '海信爱家任务中心';

const HOSTS = {
  ACCOUNT: 'https://portal-account.hismarttv.com',
  SERVICE: 'https://service-aihome.hismarttv.com',
  POINT: 'https://mobile-aiot.hismarttv.com',
  MINI_MOBI: 'https://mini-mobi.hismarttv.com',
  WXTV: 'https://public-wxtv.hismarttv.com',
  AIOT: 'https://iot-aihome.hismarttv.com',
  HILIFE: 'https://hilife.hisense.com',
};

const API = {
  SERVICE_ACTION: '/2.0/iot/vip/actions',
  JFSC_ACTION: '/1.0/iot/vip/jfsc/actions',
  TASK_LIST: '/hilife/taskCenter/miniapp/task/list',
  TASK_COMPLETE: '/hilife/taskCenter/miniapp/task/toComplete',
  TASK_BEHAVIOR_COLLECT: '/hilife/aijia/miniapp/behaviorCollect/behaviorCollect',
  TASK_NOTICE: '/taskCenter/miniapp/task/notice',
  LOTTERY_LIST: '/aijia/miniapp/shopmall/listPrizeDraw',

  REFRESH_TOKEN: '/MobileMiniAppAPI/1.2/adapter/refreshToken',
  SCENE_PARAM: '/vodapptv/5.10/sceneParams/data/get',
  GET_LOGIN_KEY: '/mobile/st/getLoginKey',
  GET_USER_INFO_BY_LOGIN_KEY: '/mobile/se/getUserInfoByLoginKey',
  GET_CUSTOMER_PROFILE: '/MobileMiniAppAPI/s/6.3/account/getCustomerProfile',

  POINTS_TOTAL: '/AIoTPointsMall/gw/svc/HiScore/1.0/userPoints',
  POINTS_RECORDS: '/AIoTPointsMall/gw/svc/HiScore/1.0/userPointRecords',
  SIGN_STATUS: '/AIoTPointsMall/gw/svc/HiVip/1.0/getCheckInStatus',
  SIGN_IN: '/AIoTPointsMall/gw/svc/HiVip/1.0/checkIn',

  TASK_REPORT_EXEC: '/4.0/iot/user/task/reportExecution',
};

const CONSTS = {
  APP_KEY: 'commonweb',
  APP_PACKAGE_NAME: 'com.hisense.miniapp-aiot',
  APP_VERSION: 'm_p.16.800',
  APP_VERSION_NAME: '-1',
  APP_VERSION_CODE: '-1',
  LICENSE: '1015',
  APP_TYPE_MINIPROGRAM: '105',
  SOURCE_TYPE_MINIPROGRAM: 21,
  USER_TYPE_DEFAULT: '1',
  PLATFORM_MINIPROGRAM: '105',
  TASK_BEHAVIOR_PLATFORM: 1,
  TASK_BEHAVIOR_LOGIN_TYPE: 1,
  TASK_BEHAVIOR_ITEM_CLICK: 'rwqwc',
  TASK_PHONE_AES_KEY: '4wLgPX7h2cc9bnXmrfP1GRZXiaoHGX6O',
  TASK_PHONE_AES_IV: 'rUzKqj5QfiXSO5uP',
  LOTTERY_AES_KEY: '4wLgPX7h2cc9bnXmrfP1GRZXiaoHGX6O',
  LOTTERY_AES_IV: 'rUzKqj5QfiXSO5uP',
};

const CACHE_FILE = path.join(__dirname, 'hsaj_cache.json');

const RAW_ACCOUNTS = String(process.env.WX_ID || process.env.hsaj || '').trim();
const ONLY_TASK_CODES = toSet(process.env.hsaj_only_task_codes || '');
const SKIP_TASK_CODES = toSet(process.env.hsaj_skip_task_codes || '');
const DISABLE_TASK_USER_PHONE = /^(1|true|yes)$/i.test(
  String(process.env.hsaj_disable_phone || '').trim(),
);
const REFRESH_EXPIRE_AHEAD_SEC = Math.max(
  0,
  Number(process.env.hsaj_refresh_ahead_sec || 300) || 300,
);
const ENABLE_LOTTERY = !/^(0|false|no)$/i.test(
  String(process.env.hsaj_enable_lottery || '1').trim(),
);
const LOTTERY_TIMES = Math.max(
  0,
  Math.min(10, Number(process.env.hsaj_lottery_times || 1) || 1),
);
const ENABLE_NOTIFY = !/^(0|false|no)$/i.test(
  String(process.env.hsaj_enable_notify || '1').trim(),
);

const AUTO_REPORT_TASK_CODES = new Set(['view_strategy', 'bind_machine', 'control_machine']);
const TASK_REPORT_EXEC_DELAY_MS = {
  view_strategy: 15500,
};
const TASK_TYPE_NAME_MAP = {
  1: '新手任务',
  2: '日常任务',
  3: '进阶任务',
};
const TASK_GROUP_CODE_NAME_MAP = {
  newcomerTasks: '新手任务',
  dailyTasks: '日常任务',
  advancedTasks: '进阶任务',
};
const TASK_CODE_NAME_MAP = {
  view_strategy: '浏览攻略',
  bind_machine: '绑定设备',
  invite_friend: '邀请好友',
  control_machine: '控制设备',
  share_activity: '活动分享',
  join_review: '参与评测',
  create_service_card: '创建服务卡',
  buy_machine: '购买家电',
};
const TASK_EXEC_HINT_MAP = {
  view_strategy: { tag: '可自动上报', reason: '浏览类任务通常可直接上报，是否发分以后台校验为准' },
  share_activity: { tag: '可自动上报', reason: '分享类任务通常可直接上报，可能存在每日上限' },
  join_review: { tag: '可自动上报', reason: '互动类任务通常可直接上报，可能存在风控/频次限制' },
  bind_machine: { tag: '需真实行为', reason: '需要存在真实家电绑定关系，仅上报可能不发分' },
  control_machine: { tag: '需真实行为', reason: '需要真实设备控制行为，仅上报可能不发分' },
  invite_friend: { tag: '需真实行为', reason: '通常要求被邀请用户注册/激活成功' },
  create_service_card: { tag: '需真实行为', reason: '需真实创建保修/服务卡行为' },
  buy_machine: { tag: '需真实行为', reason: '需真实订单或交易记录校验' },
};

let globalSeq = 0;

function toSet(str) {
  const out = new Set();
  String(str || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .forEach((s) => out.add(s));
  return out;
}

function nextSeq() {
  globalSeq = globalSeq < 99999999 ? globalSeq + 1 : 10000000;
  return globalSeq;
}

function md5(s) {
  return crypto.createHash('md5').update(String(s || '')).digest('hex');
}

function toCnTaskNameByCode(taskCode) {
  const code = String(taskCode || '').trim();
  return TASK_CODE_NAME_MAP[code] || code;
}

function isZhText(s) {
  return /[\u4e00-\u9fa5]/.test(String(s || ''));
}

function getTaskTitle(task) {
  const code = String(task?.taskCode || '');
  const raw = String(task?.taskName || task?.displayName || '').trim();
  if (raw && isZhText(raw)) return raw;
  const mapped = toCnTaskNameByCode(code);
  if (mapped && mapped !== code) return mapped;
  return raw || code || '-';
}

function getTaskExecHint(task) {
  const code = String(task?.taskCode || '').trim();
  const title = getTaskTitle(task);
  if (TASK_EXEC_HINT_MAP[code]) return TASK_EXEC_HINT_MAP[code];

  const t = `${title} ${code}`;
  if (/(绑定|邀请|购买|商城|下单|创建|保修|控制|设备)/.test(t)) {
    return { tag: '需真实行为', reason: '该任务通常依赖真实业务行为，接口上报可能不足以发分' };
  }
  if (/(浏览|分享|讨论|参与|签到|查看)/.test(t)) {
    return { tag: '可自动上报', reason: '该任务通常可上报，最终是否发分由后台规则决定' };
  }
  return { tag: '未知类型', reason: '接口已尝试上报，建议结合复核结果判断是否需手工完成' };
}

function summarizeHintCounts(tasks) {
  const map = {};
  (tasks || []).forEach((t) => {
    const hint = getTaskExecHint(t);
    map[hint.tag] = (map[hint.tag] || 0) + 1;
  });
  return Object.keys(map)
    .map((k) => `${k}:${map[k]}`)
    .join(' | ');
}

function getGroupName(g) {
  const taskType = Number(g?.taskType ?? g?.type ?? 0);
  const code = String(g?.code || '').trim();
  if (code && TASK_GROUP_CODE_NAME_MAP[code]) return TASK_GROUP_CODE_NAME_MAP[code];
  if (g?.taskTypeName && isZhText(g.taskTypeName)) return g.taskTypeName;
  if (g?.title && isZhText(g.title)) return g.title;
  return TASK_TYPE_NAME_MAP[taskType] || (taskType ? `类型${taskType}` : '未分组');
}

function isCnPhone(s) {
  return /^1\d{10}$/.test(String(s || '').trim());
}

function parseJwtPayload(token) {
  try {
    const raw = String(token || '').replace(/^Bearer\s+/i, '').trim();
    const parts = raw.split('.');
    if (parts.length < 2) return null;
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
  } catch {
    return null;
  }
}

function pickValue(obj, keys) {
  if (!obj || typeof obj !== 'object') return '';
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim()) {
      return String(v).trim();
    }
  }
  return '';
}

function guessCustomerIdFromToken(token) {
  const payload = parseJwtPayload(token);
  if (!payload) return '';
  const keys = ['customerId', 'customer_id', 'userId', 'user_id', 'uid', 'sub', 'subscriberId', 'subscriber_id'];
  const direct = pickValue(payload, keys);
  if (direct) return direct;
  const nests = [payload.userInfo, payload.user, payload.data, payload.body];
  for (const item of nests) {
    const hit = pickValue(item, keys);
    if (hit) return hit;
  }
  return '';
}

function randomHex(len = 8) {
  return crypto.randomBytes(Math.ceil(len / 2)).toString('hex').slice(0, len);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fmtTime(tsMs) {
  if (!tsMs || Number.isNaN(Number(tsMs))) return '-';
  const d = new Date(Number(tsMs));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${day} ${hh}:${mm}:${ss}`;
}

function safeJsonPreview(value, maxLen = 220) {
  try {
    const s = JSON.stringify(value);
    if (!s) return '-';
    return s.length > maxLen ? `${s.slice(0, maxLen)}...` : s;
  } catch {
    return '-';
  }
}

async function sendNotifySafe(title, content) {
  if (!ENABLE_NOTIFY) return false;
  try {
    let sender = null;
    try {
      const mod = require('./sendNotify');
      sender = mod?.sendNotify || mod;
    } catch (_) {
      // 非青龙环境可能不存在 sendNotify，忽略。
    }
    if (typeof sender !== 'function') {
      console.log('通知: 未找到 sendNotify 模块，跳过推送');
      return false;
    }
    await sender(String(title || SCRIPT_NAME), String(content || ''));
    console.log('通知: 推送成功');
    return true;
  } catch (err) {
    console.log(`通知: 推送失败 -> ${err.message}`);
    return false;
  }
}

function maskPhone(phone) {
  const s = String(phone || '').trim();
  if (!s) return '-';
  if (s.length >= 11 && /^1\d{10}$/.test(s)) return `${s.slice(0, 3)}****${s.slice(-4)}`;
  if (s.length <= 4) return '*'.repeat(s.length);
  return `${s.slice(0, 2)}****${s.slice(-2)}`;
}

function tokenTail(token, len = 8) {
  const s = String(token || '').trim();
  if (!s) return '-';
  return s.length <= len ? s : s.slice(-len);
}

function isLikelyToken(v) {
  const s = String(v || '').trim();
  if (!s) return false;
  if (/^(0a|1a)[A-Za-z0-9._-]{16,}/.test(s)) return true;
  if (s.split('.').length === 3 && s.length > 40) return true;
  return false;
}

function isLikelyRefreshToken(v) {
  const s = String(v || '').trim();
  if (!s) return false;
  if (s.split('.').length === 3 && s.length > 40) return false;
  return /^9[A-Za-z0-9._-]{16,}$/.test(s);
}

function buildAccessTokenByRefreshToken(refreshToken) {
  const rt = String(refreshToken || '').trim();
  if (!rt) return '';
  return rt.replace(/^9/, '1');
}

function accountFingerprint(acc) {
  return `remark=${acc?.remark || '-'} customerId=${acc?.customerId || '-'} phone=${maskPhone(acc?.phone)} token尾=${tokenTail(
    acc?.token,
  )}`;
}

function summarizePointFields(raw) {
  if (!raw || typeof raw !== 'object') return '-';
  const keys = [
    'totalScore',
    'availableScore',
    'validScore',
    'usableScore',
    'frozenScore',
    'todayScore',
    'score',
  ];
  const parts = [];
  for (const k of keys) {
    if (raw[k] !== undefined && raw[k] !== null && String(raw[k]).trim() !== '') {
      parts.push(`${k}=${raw[k]}`);
    }
  }
  if (parts.length) return parts.join(', ');
  return safeJsonPreview(raw);
}

function summarizeSignStatus(status) {
  if (!status || typeof status !== 'object') return '-';
  const keys = ['signedToday', 'hasCheckIn', 'isCheckIn', 'continueDays', 'todayPoint', 'point', 'checkInDate'];
  const parts = [];
  for (const k of keys) {
    if (status[k] !== undefined && status[k] !== null && String(status[k]).trim() !== '') {
      parts.push(`${k}=${status[k]}`);
    }
  }
  if (parts.length) return parts.join(', ');
  return safeJsonPreview(status);
}

function isSignedToday(status) {
  if (!status || typeof status !== 'object') return false;
  if (status.signedToday === true || status.signedToday === 1 || status.signedToday === '1') return true;
  if (status.hasCheckIn === true || status.hasCheckIn === 1 || status.hasCheckIn === '1') return true;
  if (status.isCheckIn === true || status.isCheckIn === 1 || status.isCheckIn === '1') return true;
  return false;
}

function withT(data) {
  return Object.assign({ _t: Date.now() }, data || {});
}

function makeSignHeaders(data, postAndJSON = true) {
  return {
    'content-type': 'application/json',
    appKey: CONSTS.APP_KEY,
    'X-Sign-For': sign(data, { appKey: CONSTS.APP_KEY, postAndJSON }),
  };
}

function makeQuerySignHeaders(data) {
  return {
    'content-type': 'application/x-www-form-urlencoded',
    appKey: CONSTS.APP_KEY,
    'X-Sign-For': sign(data, { appKey: CONSTS.APP_KEY, postAndJSON: false }),
  };
}

async function request(method, url, { headers = {}, data, timeout = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const options = {
      method,
      headers,
      signal: controller.signal,
    };
    if (data !== undefined) {
      options.body = typeof data === 'string' ? data : JSON.stringify(data);
    }
    const res = await fetch(url, options);
    const text = await res.text();
    if (!text || !text.trim()) {
      throw new Error(`空响应: [${res.status}] ${method} ${url}`);
    }
    let json;
    try {
      json = JSON.parse(text);
    } catch {
      throw new Error(`非JSON响应: [${res.status}] ${method} ${url} -> ${text.slice(0, 200)}`);
    }
    return { status: res.status, data: json };
  } finally {
    clearTimeout(timer);
  }
}

function loadCache() {
  try {
    const raw = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
    if (!raw || typeof raw !== 'object') return { accounts: {} };
    if (!raw.accounts || typeof raw.accounts !== 'object') raw.accounts = {};
    return raw;
  } catch {
    return { accounts: {} };
  }
}

function saveCache(cache) {
  cache.updatedAt = new Date().toISOString();
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
}

function parseAccounts(raw) {
  return raw
    .split(/[\n@&\r]+/)
    .map((s) => {
      let x = s.trim();
      if (x.includes('=')) {
        x = x.split('=', 2)[1].trim();
      }
      return x;
    })
    .filter(Boolean)
    .map((line, idx) => {
      if (line.startsWith('{')) {
        try {
          const obj = JSON.parse(line);
          const refreshToken = String(obj.refreshToken || obj.rt || '').trim();
          if (!refreshToken) return null;
          return {
            token: buildAccessTokenByRefreshToken(refreshToken),
            refreshToken,
            customerId: obj.customerId || '',
            phone: obj.phone || obj.mobilePhone || '',
            phoneEncrypted: obj.phoneEncrypted || '',
            remark: obj.remark || obj.name || `账号${idx + 1}`,
            deviceId: obj.deviceId || '',
            tokenCreateTime: Number(obj.tokenCreateTime || 0),
            tokenExpiredTime: Number(obj.tokenExpiredTime || 0),
            refreshTokenExpiredTime: Number(obj.refreshTokenExpiredTime || 0),
          };
        } catch {
          return null;
        }
      }
      const p = line.split('#');
      const p1 = (p[1] || '').trim();
      const p2 = (p[2] || '').trim();
      const p3 = (p[3] || '').trim();
      const p4 = (p[4] || '').trim();
      const first = (p[0] || '').trim();

      if (isLikelyRefreshToken(first) || (!isLikelyToken(first) && first.length >= 16)) {
        const defaultRemark = `账号${idx + 1}`;
        const customerId = /^\d{6,}$/.test(p1) ? p1 : '';
        let phoneRaw = '';
        let remarkRaw = '';
        let deviceId = '';
        if (customerId) {
          phoneRaw = isCnPhone(p2) ? p2 : '';
          remarkRaw = p3;
          deviceId = p4 || '';
        } else {
          if (isCnPhone(p1)) {
            phoneRaw = p1;
            remarkRaw = p2;
            deviceId = p3 || '';
          } else {
            remarkRaw = p1;
            if (isCnPhone(p2)) {
              phoneRaw = p2;
              deviceId = p3 || '';
            } else {
              deviceId = p2 || '';
            }
          }
        }
        const phoneInfo = resolvePhoneFields(phoneRaw, '');
        return {
          token: buildAccessTokenByRefreshToken(first),
          refreshToken: first,
          customerId,
          phone: phoneInfo.phone,
          phoneEncrypted: phoneInfo.phoneEncrypted,
          remark: (remarkRaw || defaultRemark).trim() || defaultRemark,
          deviceId,
          tokenCreateTime: 0,
          tokenExpiredTime: 0,
          refreshTokenExpiredTime: 0,
        };
      }

      return null;
    })
    .filter((x) => x && x.refreshToken);
}

function findCachedAccount(cache, acc) {
  if (!cache || !cache.accounts) return null;
  if (acc.customerId && cache.accounts[acc.customerId]) return cache.accounts[acc.customerId];

  const tokenHash = acc.token ? md5(acc.token) : '';
  const keys = Object.keys(cache.accounts);
  for (const k of keys) {
    const c = cache.accounts[k] || {};
    if (tokenHash && c.token && md5(c.token) === tokenHash) return c;
    if (acc.refreshToken && c.refreshToken && String(c.refreshToken).trim() === String(acc.refreshToken).trim()) return c;
    if (acc.remark && c.remark && c.remark === acc.remark) return c;
  }
  return null;
}

function mergeWithCache(acc, cache) {
  const cached = findCachedAccount(cache, acc) || {};
  const merged = Object.assign({}, cached, acc);
  if (!merged.token && cached.token) merged.token = cached.token;
  if (!merged.refreshToken && cached.refreshToken) merged.refreshToken = cached.refreshToken;
  if (!merged.customerId && cached.customerId) merged.customerId = cached.customerId;
  if (!merged.phone && cached.phone) merged.phone = cached.phone;
  if (!merged.phoneEncrypted && cached.phoneEncrypted) merged.phoneEncrypted = cached.phoneEncrypted;
  if (!merged.deviceId && cached.deviceId) merged.deviceId = cached.deviceId;
  if (!merged.remark && cached.remark) merged.remark = cached.remark;
  if (!merged.tokenCreateTime && cached.tokenCreateTime) merged.tokenCreateTime = cached.tokenCreateTime;
  if (!merged.tokenExpiredTime && cached.tokenExpiredTime) merged.tokenExpiredTime = cached.tokenExpiredTime;
  if (!merged.refreshTokenExpiredTime && cached.refreshTokenExpiredTime) {
    merged.refreshTokenExpiredTime = cached.refreshTokenExpiredTime;
  }
  if (!merged.customerId) {
    merged.customerId = guessCustomerIdFromToken(merged.token);
  }
  const phoneInfo = resolvePhoneFields(merged.phone, merged.phoneEncrypted);
  merged.phone = phoneInfo.phone;
  merged.phoneEncrypted = phoneInfo.phoneEncrypted;
  if (!merged.deviceId) {
    merged.deviceId = md5(merged.customerId || merged.token || merged.refreshToken || merged.remark || '').slice(0, 16);
  }
  if (!merged.remark) merged.remark = merged.customerId || '未命名账号';
  return merged;
}

function getCacheKey(acc) {
  if (acc.customerId) return String(acc.customerId);
  if (acc.refreshToken) return `rt:${md5(String(acc.refreshToken).trim())}`;
  return String(md5(acc.token || acc.remark || 'unknown'));
}

function encryptPhone(phone) {
  const p = String(phone || '').trim();
  if (!p) return null;
  return sign.encryptByAppKey(p, CONSTS.APP_KEY);
}

function decryptPhoneMaybe(v) {
  try {
    const s = String(v || '').trim();
    if (!s) return '';
    return String(sign.decryptByAppKey(s, CONSTS.APP_KEY) || '').trim();
  } catch {
    return '';
  }
}

async function requestRaw(method, url, { headers = {}, data, timeout = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const options = {
      method,
      headers,
      signal: controller.signal,
    };
    if (data !== undefined) {
      options.body = typeof data === 'string' ? data : JSON.stringify(data);
    }
    const res = await fetch(url, options);
    const text = await res.text();
    return { status: res.status, text };
  } finally {
    clearTimeout(timer);
  }
}

function encryptTaskPhoneAiot(plainPhone) {
  const p = String(plainPhone || '').trim();
  if (!p) return '';
  const cipher = crypto.createCipheriv(
    'aes-256-cbc',
    Buffer.from(CONSTS.TASK_PHONE_AES_KEY, 'utf8'),
    Buffer.from(CONSTS.TASK_PHONE_AES_IV, 'utf8'),
  );
  return cipher.update(p, 'utf8', 'base64') + cipher.final('base64');
}

function resolvePhoneFields(phone, phoneEncrypted) {
  const rawPhone = String(phone || '').trim();
  const rawEnc = String(phoneEncrypted || '').trim();
  let plain = '';
  let encrypted = '';

  if (rawEnc) {
    encrypted = rawEnc;
    const dec = decryptPhoneMaybe(rawEnc);
    if (isCnPhone(dec)) plain = dec;
  }

  if (rawPhone) {
    if (isCnPhone(rawPhone)) {
      plain = rawPhone;
      if (!encrypted) encrypted = encryptPhone(rawPhone) || '';
    } else {
      const dec = decryptPhoneMaybe(rawPhone);
      if (isCnPhone(dec)) {
        if (!plain) plain = dec;
        if (!encrypted) encrypted = rawPhone;
      } else if (!encrypted && rawPhone.length >= 16) {
        encrypted = rawPhone;
      }
    }
  }

  return { phone: plain, phoneEncrypted: encrypted };
}

function getEncryptedTaskPhone(acc) {
  if (DISABLE_TASK_USER_PHONE) return '';
  const normalized = resolvePhoneFields(acc.phone, acc.phoneEncrypted);
  if (normalized.phone) return encryptTaskPhoneAiot(normalized.phone);
  return '';
}

function buildPointCommon(acc, mode) {
  const phoneInfo = resolvePhoneFields(acc.phone, acc.phoneEncrypted);
  const encryptedMobile = phoneInfo.phone
    ? encryptPhone(phoneInfo.phone) || phoneInfo.phoneEncrypted || ''
    : phoneInfo.phoneEncrypted || '';
  const out = {
    deviceId: acc.deviceId,
    appPackageName: CONSTS.APP_PACKAGE_NAME,
    appVersionName: CONSTS.APP_VERSION_NAME,
    appVersionCode: CONSTS.APP_VERSION_CODE,
    license: CONSTS.LICENSE,
    appVersion: acc.appVersion || CONSTS.APP_VERSION,
    deviceExt: acc.deviceExt || 'Windows',
    customerId: String(acc.customerId || ''),
    mobile: encryptedMobile,
    accessToken: acc.token,
    userId: String(acc.customerId || ''),
  };

  if (mode === 'userType') {
    out.userType = CONSTS.USER_TYPE_DEFAULT;
  } else {
    out.appType = CONSTS.APP_TYPE_MINIPROGRAM;
  }
  return out;
}

function isRefreshTokenExpired(acc) {
  const create = Number(acc.tokenCreateTime || 0);
  const refreshExp = Number(acc.refreshTokenExpiredTime || 0);
  if (!acc.refreshToken || !create || !refreshExp) return false;
  const nowSec = Math.floor(Date.now() / 1000);
  return create + refreshExp - REFRESH_EXPIRE_AHEAD_SEC <= nowSec;
}

function tokenExpireMs(acc) {
  const create = Number(acc.tokenCreateTime || 0);
  const ttl = Number(acc.tokenExpiredTime || 0);
  if (!create || !ttl) return 0;
  return (create + ttl) * 1000;
}

function refreshExpireMs(acc) {
  const create = Number(acc.tokenCreateTime || 0);
  const ttl = Number(acc.refreshTokenExpiredTime || 0);
  if (!create || !ttl) return 0;
  return (create + ttl) * 1000;
}

async function refreshTokenIfPossible(acc) {
  if (!acc.refreshToken) return { refreshed: false, account: acc };
  if (isRefreshTokenExpired(acc)) {
    console.log(`  - refreshToken 已临近过期，跳过刷新`);
    return { refreshed: false, account: acc };
  }
  const refreshAccessToken = String(acc.token || buildAccessTokenByRefreshToken(acc.refreshToken)).trim();
  if (!refreshAccessToken) {
    return { refreshed: false, account: acc, error: new Error('refresh缺少token参数') };
  }

  try {
    const { data } = await request('POST', `${HOSTS.MINI_MOBI}${API.REFRESH_TOKEN}`, {
      headers: { 'content-type': 'application/json' },
      data: {
        token: refreshAccessToken,
        refreshToken: acc.refreshToken,
      },
      timeout: 15000,
    });

    const topCode = Number(data?.resultCode ?? -1);
    const body = data?.data || {};
    const bodyCode = Number(body?.resultCode ?? -1);

    if (topCode !== 0 || bodyCode !== 0 || !body?.token) {
      throw new Error(`refresh失败: top=${topCode} body=${bodyCode} msg=${body?.msg || data?.msg || ''}`);
    }

    const merged = Object.assign({}, acc, {
      token: body.token,
      accessToken: body.token,
      refreshToken: body.refreshToken || acc.refreshToken,
      customerId: String(body.customerId || acc.customerId || ''),
      subscriberId: String(body.subscriberId || acc.subscriberId || ''),
      tokenCreateTime: Number(body.tokenCreateTime || acc.tokenCreateTime || 0),
      tokenExpiredTime: Number(body.tokenExpiredTime || acc.tokenExpiredTime || 0),
      refreshTokenExpiredTime: Number(body.refreshTokenExpiredTime || acc.refreshTokenExpiredTime || 0),
      updateTime: new Date().toISOString(),
    });

    return { refreshed: true, account: merged };
  } catch (err) {
    return { refreshed: false, account: acc, error: err };
  }
}

async function postSignedJson(url, body) {
  const payload = withT(body);
  const { data } = await request('POST', url, {
    headers: makeSignHeaders(payload, true),
    data: payload,
  });
  return data;
}

async function getSignedQuery(url, params = {}) {
  const query = withT(params);
  const qs = new URLSearchParams();
  Object.keys(query).forEach((k) => {
    const v = query[k];
    if (v === undefined || v === null || String(v) === '') return;
    qs.append(k, String(v));
  });
  const { data } = await request('GET', `${url}?${qs.toString()}`, {
    headers: makeQuerySignHeaders(query),
    timeout: 15000,
  });
  return data;
}

function getBizBody(data) {
  return data && typeof data.data === 'object' ? data.data : data || {};
}

async function getLoginKeyByAccessToken(accessToken) {
  const data = await getSignedQuery(`${HOSTS.ACCOUNT}${API.GET_LOGIN_KEY}`, {
    accessToken: String(accessToken || ''),
    keyType: 1,
  });
  const body = getBizBody(data);
  const code = Number(body?.resultCode ?? data?.resultCode ?? -1);
  const loginKey = String(body?.loginKey || data?.loginKey || '').trim();
  if (code !== 0 || !loginKey) {
    throw new Error(`getLoginKey失败: code=${code} msg=${body?.message || body?.msg || data?.message || data?.msg || ''}`);
  }
  return loginKey;
}

async function getUserInfoByLoginKey(loginKey) {
  const data = await getSignedQuery(`${HOSTS.ACCOUNT}${API.GET_USER_INFO_BY_LOGIN_KEY}`, {
    loginKey: String(loginKey || ''),
  });
  const body = getBizBody(data);
  const code = Number(body?.resultCode ?? data?.resultCode ?? -1);
  if (code !== 0) {
    throw new Error(`getUserInfoByLoginKey失败: code=${code} msg=${body?.message || body?.msg || data?.message || data?.msg || ''}`);
  }
  const phoneInfo = resolvePhoneFields(String(body?.mobilePhone || data?.mobilePhone || '').trim(), '');
  return {
    customerId: String(body?.customerId || data?.customerId || '').trim(),
    phone: phoneInfo.phone,
    phoneEncrypted: phoneInfo.phoneEncrypted,
    nickName: String(body?.nickName || data?.nickName || '').trim(),
  };
}

async function resolveCustomerIdByAccessToken(accessToken) {
  if (!accessToken) return { customerId: '', phone: '', phoneEncrypted: '', nickName: '' };
  const loginKey = await getLoginKeyByAccessToken(accessToken);
  return getUserInfoByLoginKey(loginKey);
}

async function getCustomerProfileByToken(acc) {
  const data = await getSignedQuery(`${HOSTS.POINT}${API.GET_CUSTOMER_PROFILE}`, {
    accessToken: String(acc.token || ''),
    customerId: String(acc.customerId || ''),
    timeStamp: Math.floor(Date.now() / 1000),
    randStr: randomHex(16),
  });
  const code = Number(data?.resultCode ?? -1);
  if (code !== 0) {
    throw new Error(`getCustomerProfile失败: code=${code} msg=${data?.msg || data?.message || ''}`);
  }
  const body = data?.data || {};
  const phoneInfo = resolvePhoneFields(String(body?.mobilePhone || '').trim(), '');
  return {
    phone: phoneInfo.phone,
    phoneEncrypted: phoneInfo.phoneEncrypted,
    nickName: String(body?.nickName || '').trim(),
  };
}

async function getTotalPoints(acc) {
  const detail = await getTotalPointsDetail(acc);
  return detail.totalScore;
}

async function getTotalPointsDetail(acc) {
  const body = buildPointCommon(acc, 'appType');
  const data = await postSignedJson(`${HOSTS.POINT}${API.POINTS_TOTAL}`, body);

  if (Number(data?.resultCode ?? -1) !== 0) {
    throw new Error(`积分查询失败: resultCode=${data?.resultCode} msg=${data?.msg || ''}`);
  }
  const raw = data?.data || {};
  const totalScore = Number(raw?.totalScore ?? 0);
  return {
    totalScore,
    raw,
  };
}

async function getUserPointRecords(acc, { pageNo = 1, pageSize = 20, startTime, endTime } = {}) {
  const body = Object.assign(buildPointCommon(acc, 'appType'), {
    pageNo: String(pageNo),
    pageSize: String(pageSize),
  });
  if (startTime) body.startTime = Number(startTime);
  if (endTime) body.endTime = Number(endTime);

  const data = await postSignedJson(`${HOSTS.POINT}${API.POINTS_RECORDS}`, body);
  const rc = Number(data?.resultCode ?? -1);
  const inner = data?.data || {};

  if (rc === 1 && String(inner?.resultCode || '') === 'B0306') {
    return { entities: [] };
  }
  if (rc !== 0) {
    throw new Error(`积分记录查询失败: resultCode=${rc} msg=${data?.msg || ''}`);
  }
  return inner;
}

function extractPointEntities(data) {
  if (!data || typeof data !== 'object') return [];
  if (Array.isArray(data.entities)) return data.entities;
  if (Array.isArray(data.records)) return data.records;
  return [];
}

async function getTodayPointEntities(acc, pageSize = 50) {
  const range = getDayRangeMs();
  const data = await getUserPointRecords(acc, { pageNo: 1, pageSize, ...range });
  return extractPointEntities(data);
}

function getDayRangeMs() {
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  return { startTime: start.getTime(), endTime: end.getTime() };
}

function recordTimeMs(rec) {
  return Number(
    rec?.createdTime ||
      rec?.createTime ||
      rec?.recordTime ||
      rec?.gmtCreate ||
      rec?.time ||
      rec?.timestamp ||
      0,
  );
}

function recordDesc(rec) {
  return (
    rec?.description ||
    rec?.desc ||
    rec?.scoreName ||
    rec?.typeDesc ||
    rec?.remark ||
    rec?.title ||
    '-'
  );
}

function recordScore(rec) {
  return Number(rec?.score ?? rec?.points ?? rec?.integral ?? 0);
}

function isSignRewardRecord(rec) {
  const desc = recordDesc(rec);
  const s = recordScore(rec);
  if (s <= 0) return false;
  return /(签到|check\s*in|checkin|每日签到|小程序签到)/i.test(String(desc || ''));
}

function sortRecordsByTimeDesc(records) {
  return records.slice().sort((a, b) => recordTimeMs(b) - recordTimeMs(a));
}

async function printSignRewardDetail(acc, { retry = 1, intervalMs = 1200 } = {}) {
  for (let i = 1; i <= Math.max(1, Number(retry || 1)); i++) {
    try {
      const entities = await getTodayPointEntities(acc, 60);
      const signRecords = sortRecordsByTimeDesc(entities).filter(isSignRewardRecord);
      if (signRecords.length) {
        const x = signRecords[0];
        const s = Math.abs(recordScore(x));
        console.log(`签到积分明细: ${fmtTime(recordTimeMs(x))} ${recordDesc(x)} +${s}`);
        return true;
      }
    } catch (err) {
      if (i === retry) {
        console.log(`签到积分明细: 查询失败 ${err.message}`);
        return false;
      }
    }
    if (i < retry) await sleep(intervalMs);
  }
  console.log('签到积分明细: 今日未查到签到奖励流水（可能是延迟或已过零点）');
  return false;
}

async function printTodayPointRecords(acc) {
  try {
    const entities = await getTodayPointEntities(acc, 20);
    if (!entities.length) {
      console.log('今日积分流水: 无记录');
      return;
    }
    const gain = entities
      .filter((x) => Number(x?.type ?? 0) === 1)
      .reduce((s, x) => s + Math.abs(recordScore(x)), 0);
    console.log(`今日积分流水: 共${entities.length}条，收入合计 +${gain}`);

    const top = sortRecordsByTimeDesc(entities).slice(0, 5);
    top.forEach((x) => {
      const s = recordScore(x);
      const sign = s > 0 ? '+' : '';
      const tm = fmtTime(recordTimeMs(x));
      console.log(`  [流水] ${tm} ${recordDesc(x)} ${sign}${s}`);
    });
  } catch (err) {
    console.log(`积分流水诊断失败: ${err.message}`);
  }
}

async function getSceneParamByCode(sceneCode, extraParams = {}) {
  const qs = new URLSearchParams({
    type: '2',
    sceneCode: String(sceneCode || ''),
    _t: String(Date.now()),
  });
  Object.keys(extraParams || {}).forEach((k) => {
    const v = extraParams[k];
    if (v === undefined || v === null || String(v).trim() === '') return;
    qs.set(k, String(v));
  });

  const { data } = await request('GET', `${HOSTS.WXTV}${API.SCENE_PARAM}?${qs.toString()}`, {
    timeout: 15000,
  });

  if (Number(data?.resultCode ?? -1) !== 0) {
    throw new Error(`scene参数获取失败: resultCode=${data?.resultCode}`);
  }

  const pageParams = Array.isArray(data?.pageParams) ? data.pageParams : [];
  const hit = pageParams.find((x) => x?.sceneCode === String(sceneCode || '')) || pageParams[0] || {};
  return hit || {};
}

async function getSceneSignTaskId() {
  const hit = await getSceneParamByCode('STATIC_AILIFE_SIGN_INFO');
  return hit?.mpSignInfo?.taskId || null;
}

async function getMissionCenterSceneUrls() {
  const hit = await getSceneParamByCode('STATIC_AILIFE_MISSION_CENTER');
  return hit?.urls || {};
}

async function visitMiniUsageGuide(acc) {
  const urls = await getMissionCenterSceneUrls();
  const base = String(urls?.miniUsageGuide || '').trim();
  if (!base) {
    throw new Error('缺少 miniUsageGuide 配置');
  }
  const u = new URL(base);
  u.searchParams.set('customerId', String(acc.customerId || ''));
  u.searchParams.set('token', String(acc.token || ''));
  const encryPhone = getEncryptedTaskPhone(acc);
  if (encryPhone) u.searchParams.set('encryPhone', encryPhone);
  const { status, text } = await requestRaw('GET', u.toString(), {
    headers: {
      accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'user-agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    },
    timeout: 20000,
  });
  if (status < 200 || status >= 400) {
    throw new Error(`请求失败: HTTP ${status}`);
  }
  return { status, bytes: (text || '').length };
}

async function getSignStatus(acc, taskId) {
  const body = Object.assign(buildPointCommon(acc, 'userType'), {
    taskId,
    sourceType: CONSTS.SOURCE_TYPE_MINIPROGRAM,
  });
  const data = await postSignedJson(`${HOSTS.POINT}${API.SIGN_STATUS}`, body);

  if (String(data?.code ?? '1') !== '0') {
    throw new Error(`签到状态查询失败: code=${data?.code} msg=${data?.msg || ''}`);
  }

  return data?.checkInStatus || {};
}

async function doSignIn(acc, taskId) {
  const now = Date.now();
  const body = Object.assign(buildPointCommon(acc, 'userType'), {
    returnCheckInStatus: false,
    requestId: `ailife_sign-${now}-${randomHex(8)}`,
    taskId,
    reportToGroup: 1,
    requestTime: String(now),
  });

  const url = `${HOSTS.POINT}${API.SIGN_IN}?customerId=${encodeURIComponent(String(acc.customerId || ''))}`;
  const data = await postSignedJson(url, body);

  if (String(data?.code ?? '1') !== '0') {
    throw new Error(`签到失败: code=${data?.code} msg=${data?.msg || ''}`);
  }

  return data?.checkInStatus || {};
}

async function callServiceAction(acc, actionUrl, param = {}) {
  const body = {
    accessToken: acc.token,
    messageId: `h5-mini-request${Date.now()}-${nextSeq()}`,
    header: {
      token: acc.token,
    },
    url: actionUrl,
    method: 'POST',
    param,
  };

  const data = await postSignedJson(`${HOSTS.SERVICE}${API.SERVICE_ACTION}`, body);

  if (Number(data?.resultCode ?? -1) !== 0) {
    throw new Error(`服务网关失败: resultCode=${data?.resultCode}`);
  }
  if (Number(data?.data?.code ?? -1) !== 0) {
    throw new Error(`业务失败: code=${data?.data?.code} msg=${data?.data?.msg || data?.data?.message || ''}`);
  }

  return data?.data?.data;
}

async function getTaskCenterTaskList(acc) {
  return callServiceAction(acc, API.TASK_LIST, {
    userId: String(acc.customerId || ''),
    platform: CONSTS.PLATFORM_MINIPROGRAM,
  });
}

async function completeTask(acc, taskCode) {
  const param = {
    userId: String(acc.customerId || ''),
    taskCode: String(taskCode),
  };
  const userPhone = getEncryptedTaskPhone(acc);
  if (userPhone) param.userPhone = userPhone;
  return callServiceAction(acc, API.TASK_COMPLETE, param);
}

function pickTaskDataId(task) {
  const id = task?.id ?? task?.taskId ?? task?.dataId;
  if (id === undefined || id === null) return '';
  const s = String(id).trim();
  return s || '';
}

async function reportBehaviorCollect(acc, task) {
  const dataId = pickTaskDataId(task);
  if (!dataId) {
    throw new Error('缺少任务id，无法上报behaviorCollect');
  }
  const param = {
    userId: String(acc.customerId || ''),
    loginType: CONSTS.TASK_BEHAVIOR_LOGIN_TYPE,
    dataId,
    item: CONSTS.TASK_BEHAVIOR_ITEM_CLICK,
    platform: CONSTS.TASK_BEHAVIOR_PLATFORM,
  };
  return callServiceAction(acc, API.TASK_BEHAVIOR_COLLECT, param);
}

async function reportTaskExecution(acc, taskCode) {
  const payload = {
    customerId: String(acc.customerId || ''),
    sourceType: CONSTS.SOURCE_TYPE_MINIPROGRAM,
    taskCode: String(taskCode),
    joinTime: fmtTime(Date.now()),
  };
  const userPhone = getEncryptedTaskPhone(acc);
  if (userPhone) payload.userPhone = userPhone;

  const body = {
    accessToken: acc.token,
    header: {
      messageId: `h5_mini_request-${Date.now()}-${nextSeq()}`,
    },
    payload,
  };

  const data = await postSignedJson(`${HOSTS.AIOT}${API.TASK_REPORT_EXEC}`, body);
  if ((data?.payload || {}).status !== 'SUCCESS') {
    throw new Error(`reportExecution失败: ${(data?.payload || {}).status || 'unknown'}`);
  }
  return data.payload;
}

async function reportTaskNotice(acc, taskCode) {
  const code = String(taskCode || '').trim();
  const body = {
    requestId: Date.now(),
    taskCode: code,
    userId: String(acc.customerId || ''),
    userPhone: getEncryptedTaskPhone(acc) || '',
    joinPlatform: '1',
  };
  const { data } = await request('POST', `${HOSTS.HILIFE}${API.TASK_NOTICE}`, {
    headers: {
      'content-type': 'application/json',
    },
    data: body,
    timeout: 15000,
  });
  if (Number(data?.code ?? -1) !== 0) {
    throw new Error(`taskNotice失败: code=${data?.code} msg=${data?.msg || ''}`);
  }
  if (Number(data?.data?.resultCode ?? 0) !== 1) {
    throw new Error(`taskNotice业务失败: resultCode=${data?.data?.resultCode ?? 0}`);
  }
  return data?.data || {};
}

function aesCbcEncryptBase64(text, key, iv) {
  const cipher = crypto.createCipheriv('aes-256-cbc', Buffer.from(key, 'utf8'), Buffer.from(iv, 'utf8'));
  return cipher.update(String(text || ''), 'utf8', 'base64') + cipher.final('base64');
}

function aesCbcDecryptBase64(base64Text, key, iv) {
  const decipher = crypto.createDecipheriv('aes-256-cbc', Buffer.from(key, 'utf8'), Buffer.from(iv, 'utf8'));
  return decipher.update(String(base64Text || ''), 'base64', 'utf8') + decipher.final('utf8');
}

async function getLotteryActivityList() {
  const { data } = await request('POST', `${HOSTS.HILIFE}${API.LOTTERY_LIST}`, {
    headers: {
      'content-type': 'application/json',
    },
    data: {
      pageNo: 1,
      pageSize: 10,
      endpoint: '',
      isEnable: null,
      siteld: null,
    },
    timeout: 15000,
  });
  return Array.isArray(data?.data) ? data.data : [];
}

async function jfscAction(acc, actionPath, paramObj) {
  const body = {
    accessToken: acc.token,
    messageId: `h5-mini-request${Date.now()}-${nextSeq()}`,
    sourceType: CONSTS.SOURCE_TYPE_MINIPROGRAM,
    method: 'POST',
    param: aesCbcEncryptBase64(JSON.stringify(paramObj || {}), CONSTS.LOTTERY_AES_KEY, CONSTS.LOTTERY_AES_IV),
    url: String(actionPath || ''),
  };

  const data = await postSignedJson(`${HOSTS.SERVICE}${API.JFSC_ACTION}`, body);
  if (Number(data?.resultCode ?? -1) !== 0) {
    throw new Error(`jfsc网关失败: resultCode=${data?.resultCode} msg=${data?.message || data?.msg || ''}`);
  }

  const encryptedPayload = String(data?.data || '').trim();
  if (!encryptedPayload) {
    throw new Error('jfsc返回缺少加密数据');
  }

  let plain = '';
  try {
    plain = aesCbcDecryptBase64(encryptedPayload, CONSTS.LOTTERY_AES_KEY, CONSTS.LOTTERY_AES_IV);
  } catch (err) {
    throw new Error(`jfsc解密失败: ${err.message}`);
  }

  try {
    return JSON.parse(plain);
  } catch {
    throw new Error(`jfsc解析失败: ${plain.slice(0, 180)}`);
  }
}

async function getLotteryDetail(acc, activityId) {
  return jfscAction(acc, '/jfsc/openapi/activity-manage/outer/lottery/detail', {
    activityId: String(activityId || ''),
  });
}

function extractLotteryRuleCodes(sceneHit) {
  const params = Array.isArray(sceneHit?.params) ? sceneHit.params : [];
  const mini = params.find((x) => x?.scene?.id === 'miniapp') || params[0] || {};
  return {
    produceRuleCode: String(mini?.lotteryNineCells?.produceRuleCode || '').trim(),
    exchangeRuleCode: String(mini?.lotteryNineCells?.exchangeRuleCode || '').trim(),
  };
}

async function drawLottery(acc, detail, sceneHit) {
  const code = String(detail?.data?.code || detail?.code || '').trim();
  const { produceRuleCode, exchangeRuleCode } = extractLotteryRuleCodes(sceneHit);
  if (!code) return { error: '缺少抽奖code' };
  if (!produceRuleCode || !exchangeRuleCode) return { error: '缺少抽奖规则码' };

  return jfscAction(acc, '/jfsc/openapi/activity-manage/outer/lottery/draw', {
    code,
    customId: String(acc.customerId || ''),
    customUserName: `USER_${String(acc.customerId || '').trim()}`,
    phone: String(acc.phone || '').trim(),
    produceRuleCode,
    exchangeRuleCode,
  });
}

function isLotteryChanceOver(resultMsg = '') {
  const txt = String(resultMsg || '');
  const keywords = ['no chance', 'chance over', 'used up', '次数不足', '抽奖次数已用完', '已参与'];
  return keywords.some((k) => txt.includes(k));
}

async function doLottery(acc, times = 1) {
  if (!ENABLE_LOTTERY || times <= 0) return;
  const activities = await getLotteryActivityList();
  if (!activities.length) {
    console.log('抽奖: 未获取到活动，跳过');
    return;
  }

  const act = activities[0];
  const activityId = act?.activityId || act?.id;
  if (!activityId) {
    console.log('抽奖: 活动缺少 activityId，跳过');
    return;
  }
  console.log(`抽奖: 活动 ${act?.activityName || activityId}`);

  const detail = await getLotteryDetail(acc, activityId);
  const sceneHit = await getSceneParamByCode('STATIC_AILIFE_POINTS_MALL', {
    accessToken: String(acc.token || ''),
  });

  for (let i = 0; i < times; i++) {
    const draw = await drawLottery(acc, detail, sceneHit);
    if (draw?.isSuccess) {
      const prizeName = draw?.data?.prizeName || draw?.prizeName || draw?.data?.displayName || '未知奖品';
      const prizeType = draw?.data?.prizeType || draw?.prizeType || '';
      console.log(`抽奖: 第${i + 1}次 -> ${prizeName}${prizeType ? ` (${prizeType})` : ''}`);
    } else {
      const msg = draw?.resultMsg || draw?.error || draw?.message || safeJsonPreview(draw);
      console.log(`抽奖: 第${i + 1}次 -> ${msg}`);
      if (isLotteryChanceOver(msg)) break;
    }
    if (i < times - 1) await sleep(1600 + Math.floor(Math.random() * 700));
  }
}

function flattenTasks(taskGroups) {
  if (!Array.isArray(taskGroups)) return [];
  const list = [];
  taskGroups.forEach((g) => {
    const t = Array.isArray(g?.taskList) ? g.taskList : [];
    t.forEach((x) => list.push(x));
  });
  return list;
}

function flattenTasksWithMeta(taskGroups) {
  if (!Array.isArray(taskGroups)) return [];
  const list = [];
  taskGroups.forEach((g) => {
    const taskType = Number(g?.taskType ?? g?.type ?? 0);
    const groupName = getGroupName(g);
    const t = Array.isArray(g?.taskList) ? g.taskList : [];
    t.forEach((x) =>
      list.push(
        Object.assign({}, x, {
          __groupType: taskType,
          __groupName: groupName,
        }),
      ),
    );
  });
  return list;
}

function summarizeTaskGroups(taskGroups) {
  if (!Array.isArray(taskGroups)) return '-';
  const parts = taskGroups.map((g) => {
    const name = getGroupName(g);
    const count = Array.isArray(g?.taskList) ? g.taskList.length : 0;
    return `${name}:${count}`;
  });
  return parts.join(' | ');
}

function filterTasks(tasks) {
  const pending = tasks.filter((t) => Number(t?.taskStatus ?? 0) !== 1 && t?.taskCode);
  return pending.filter((t) => {
    const code = String(t.taskCode);
    if (ONLY_TASK_CODES.size > 0 && !ONLY_TASK_CODES.has(code)) return false;
    if (SKIP_TASK_CODES.has(code)) return false;
    return true;
  });
}

async function ensureAccountReady(acc) {
  let current = Object.assign({}, acc);
  let refreshTried = false;
  if (!current.refreshToken) {
    throw new Error('缺少 refreshToken：请抓 login4MiniAPPByPhone 响应里的 refreshToken');
  }
  if (!current.token) {
    current.token = buildAccessTokenByRefreshToken(current.refreshToken);
  }

  if (!current.customerId && current.refreshToken) {
    const refreshed = await refreshTokenIfPossible(current);
    if (refreshed.refreshed) current = refreshed.account;
  }

  if (current.refreshToken) {
    const refreshed = await refreshTokenIfPossible(current);
    refreshTried = true;
    if (refreshed.refreshed) {
      current = refreshed.account;
      console.log(`  - refreshToken续期成功`);
    } else if (refreshed.error) {
      console.log(`  - refreshToken续期失败，先尝试旧token: ${refreshed.error.message}`);
    }
  }

  if (!current.customerId && current.token) {
    const guessed = guessCustomerIdFromToken(current.token);
    if (guessed) {
      current.customerId = guessed;
      console.log(`  - 已从token解析customerId`);
    }
  }

  if (!current.customerId && current.token) {
    try {
      const info = await resolveCustomerIdByAccessToken(current.token);
      if (info.customerId) {
        current.customerId = info.customerId;
        if (!current.phone && info.phone) current.phone = info.phone;
        if (!current.phoneEncrypted && info.phoneEncrypted) current.phoneEncrypted = info.phoneEncrypted;
        if (!current.remark && info.nickName) current.remark = info.nickName;
        console.log(`  - 已通过accessToken自动获取customerId`);
      }
    } catch (err) {
      console.log(`  - accessToken自动查询customerId失败: ${err.message}`);
    }
  }

  {
    const phoneInfo = resolvePhoneFields(current.phone, current.phoneEncrypted);
    current.phone = phoneInfo.phone;
    current.phoneEncrypted = phoneInfo.phoneEncrypted;
  }

  if (current.customerId && !current.phone) {
    try {
      const profile = await getCustomerProfileByToken(current);
      if (profile.phone) current.phone = profile.phone;
      if (!current.phoneEncrypted && profile.phoneEncrypted) current.phoneEncrypted = profile.phoneEncrypted;
      if (!current.remark && profile.nickName) current.remark = profile.nickName;
      if (current.phone) {
        console.log(`  - 已通过用户资料接口补全手机号`);
      }
    } catch (err) {
      console.log(`  - 用户资料补全手机号失败: ${err.message}`);
    }
  }

  if (!current.token) {
    throw new Error('缺少 accessToken：请检查 refreshToken 是否有效');
  }

  if (!current.customerId) {
    throw new Error('缺少 customerId：请检查 refreshToken 是否有效，或补充 customerId');
  }

  try {
    const points = await getTotalPointsDetail(current);
    return { account: current, pointsBefore: points.totalScore, pointsBeforeDetail: points };
  } catch (err) {
    if (!refreshTried && current.refreshToken) {
      const refreshed = await refreshTokenIfPossible(current);
      if (refreshed.refreshed) {
        current = refreshed.account;
        const points = await getTotalPointsDetail(current);
        return { account: current, pointsBefore: points.totalScore, pointsBeforeDetail: points };
      }
    }

    throw new Error(`token不可用: ${err.message}`);
  }
}

async function runOneAccount(acc, idx, total) {
  console.log(`\n========== [${idx}/${total}] ${acc.remark} ==========`);

  const ready = await ensureAccountReady(acc);
  const account = ready.account;
  const pointsBefore = ready.pointsBefore;
  const pointsBeforeDetail = ready.pointsBeforeDetail;

  console.log(`账号: ${account.remark}`);
  console.log(`账号指纹: ${accountFingerprint(account)}`);
  console.log(`customerId: ${account.customerId}`);
  console.log(`积分(执行前): ${pointsBefore}`);
  console.log(`积分字段(执行前): ${summarizePointFields(pointsBeforeDetail?.raw)}`);
  console.log(`任务手机号: ${getEncryptedTaskPhone(account) ? '已就绪' : '缺失'}`);

  const tExp = tokenExpireMs(account);
  const rtExp = refreshExpireMs(account);
  if (tExp) console.log(`token到期: ${fmtTime(tExp)}`);
  if (rtExp) console.log(`refreshToken到期: ${fmtTime(rtExp)}`);

  let doneCount = 0;
  let behaviorCount = 0;

  try {
    const groups = await getTaskCenterTaskList(account);
    console.log(`任务分组: ${summarizeTaskGroups(groups)}`);
    const allTasks = flattenTasks(groups);
    const pending = filterTasks(allTasks);

    console.log(`任务总数: ${allTasks.length}，待尝试: ${pending.length}`);
    if (pending.length) {
      console.log(`任务判定汇总: ${summarizeHintCounts(pending)}`);
    }

    for (const task of pending) {
      const code = String(task.taskCode || '');
      const title = getTaskTitle(task);
      const hint = getTaskExecHint(task);
      console.log(`  [判定] ${title} (${code}) -> ${hint.tag}：${hint.reason}`);

      const taskDataId = pickTaskDataId(task);
      if (taskDataId) {
        try {
          await reportBehaviorCollect(account, task);
          behaviorCount += 1;
          console.log(`  [行为] ${title} (${code}) -> behaviorCollect 成功`);
        } catch (err) {
          console.log(`  [行为] ${title} (${code}) -> behaviorCollect 失败: ${err.message}`);
        }
      } else {
        console.log(`  [行为] ${title} (${code}) -> 跳过: 任务缺少id`);
      }

      try {
        await completeTask(account, code);
        doneCount += 1;
        console.log(`  [任务] ${title} (${code}) -> 已上报`);
      } catch (err) {
        console.log(`  [任务] ${title} (${code}) -> 失败: ${err.message}`);
      }

      if (code === 'view_strategy') {
        try {
          const guide = await visitMiniUsageGuide(account);
          console.log(`  [动作] ${code} -> miniUsageGuide 已访问 (HTTP ${guide.status}, ${guide.bytes} bytes)`);
        } catch (err) {
          console.log(`  [动作] ${code} -> miniUsageGuide 访问失败: ${err.message}`);
        }
      }

      if (AUTO_REPORT_TASK_CODES.has(code)) {
        try {
          const delayMs = Number(TASK_REPORT_EXEC_DELAY_MS[code] || 0);
          if (delayMs > 0) {
            console.log(`  [上报] ${code} -> 等待 ${Math.floor(delayMs / 1000)}s 模拟停留后上报`);
            await sleep(delayMs);
          }
          await reportTaskExecution(account, code);
          console.log(`  [上报] ${code} -> reportExecution 成功`);
        } catch (err) {
          console.log(`  [上报] ${code} -> reportExecution 失败: ${err.message}`);
        }
      }

      if (code === 'share_activity') {
        try {
          await reportTaskNotice(account, code);
          console.log(`  [上报] ${code} -> taskNotice 成功`);
        } catch (err) {
          console.log(`  [上报] ${code} -> taskNotice 失败: ${err.message}`);
        }
      }

      await sleep(500 + Math.floor(Math.random() * 400));
    }
  } catch (err) {
    console.log(`任务中心处理异常: ${err.message}`);
  }

  try {
    const groupsAfter = await getTaskCenterTaskList(account);
    const allAfter = flattenTasksWithMeta(groupsAfter);
    const remaining = allAfter.filter((t) => Number(t?.taskStatus ?? 0) !== 1 && t?.taskCode);
    if (!remaining.length) {
      console.log('复核: 任务中心接口显示全部已完成');
    } else {
      console.log(`复核: 仍有 ${remaining.length} 个未完成任务`);
      console.log(`复核判定汇总: ${summarizeHintCounts(remaining)}`);
      remaining.forEach((t) => {
        const groupName = t.__groupName || '未分组';
        const title = getTaskTitle(t);
        const code = t.taskCode || '-';
        const status = t.taskStatus;
        const hint = getTaskExecHint(t);
        console.log(`  [未完成][${groupName}][${hint.tag}] ${title} (${code}) status=${status}`);
      });
    }
  } catch (err) {
    console.log(`复核失败: ${err.message}`);
  }

  try {
    const taskId = await getSceneSignTaskId();
    if (!taskId) {
      console.log('签到: 未获取到 taskId，跳过');
    } else {
      console.log(`签到: 调用签到状态接口 ${API.SIGN_STATUS} (taskId=${taskId})`);
      const status = await getSignStatus(account, taskId);
      console.log(`签到: 状态返回 -> ${summarizeSignStatus(status)}`);
      if (isSignedToday(status)) {
        console.log('签到: 今日已签到（本次不会再加签到分）');
        await printSignRewardDetail(account, { retry: 2, intervalMs: 1500 });
      } else {
        console.log(`签到: 调用签到接口 ${API.SIGN_IN} (taskId=${taskId})`);
        const signRet = await doSignIn(account, taskId);
        console.log(`签到: 签到返回 -> ${summarizeSignStatus(signRet)}`);
        console.log('签到: 成功');
        await printSignRewardDetail(account, { retry: 4, intervalMs: 1800 });
      }
    }
  } catch (err) {
    console.log(`签到异常: ${err.message}`);
  }

  if (ENABLE_LOTTERY && LOTTERY_TIMES > 0) {
    try {
      await doLottery(account, LOTTERY_TIMES);
    } catch (err) {
      console.log(`抽奖异常: ${err.message}`);
    }
  }

  await sleep(800);
  const pointsAfterDetail = await getTotalPointsDetail(account);
  const pointsAfter = pointsAfterDetail.totalScore;
  const delta = pointsAfter - pointsBefore;

  console.log(`积分(执行后): ${pointsAfter}  (变化: ${delta >= 0 ? '+' : ''}${delta})`);
  console.log(`积分字段(执行后): ${summarizePointFields(pointsAfterDetail?.raw)}`);
  await printTodayPointRecords(account);
  console.log(`行为上报次数: ${behaviorCount}`);
  console.log(`任务上报次数: ${doneCount}`);

  return {
    account,
    pointsBefore,
    pointsAfter,
    delta,
    doneCount,
  };
}

async function main() {
  if (!RAW_ACCOUNTS) {
    throw new Error('未设置变量 WX_ID 或 hsaj');
  }

  const accounts = parseAccounts(RAW_ACCOUNTS);
  if (!accounts.length) {
    throw new Error('账号解析失败，请检查变量格式');
  }

  const cache = loadCache();
  console.log(`${SCRIPT_NAME} 启动，账号数: ${accounts.length}`);
  console.log(`抽奖: ${ENABLE_LOTTERY ? `开启(${LOTTERY_TIMES}次)` : '关闭'}`);

  let ok = 0;
  let fail = 0;
  const notifyLines = [];

  for (let i = 0; i < accounts.length; i++) {
    const fromEnv = accounts[i];
    const merged = mergeWithCache(fromEnv, cache);

    try {
      const result = await runOneAccount(merged, i + 1, accounts.length);
      ok += 1;
      notifyLines.push(
        `✅ ${result?.account?.remark || merged.remark || `账号${i + 1}`}: ${result.pointsBefore} -> ${result.pointsAfter} (${
          result.delta >= 0 ? '+' : ''
        }${result.delta})`,
      );

      const toSave = Object.assign({}, merged, result.account, {
        updateTime: new Date().toISOString(),
      });
      cache.accounts[getCacheKey(toSave)] = toSave;
      saveCache(cache);
    } catch (err) {
      fail += 1;
      console.log(`❌ 账号失败: ${merged.remark} -> ${err.message}`);
      notifyLines.push(`❌ ${merged.remark || `账号${i + 1}`}: ${err.message}`);

      const toSave = Object.assign({}, merged, {
        lastError: err.message,
        updateTime: new Date().toISOString(),
      });
      cache.accounts[getCacheKey(toSave)] = toSave;
      saveCache(cache);
    }
  }

  console.log(`\n${SCRIPT_NAME} 结束: 成功 ${ok}，失败 ${fail}`);
  const title = `${SCRIPT_NAME} 执行结果`;
  const content = [
    `时间: ${fmtTime(Date.now())}`,
    `总账号: ${accounts.length}`,
    `成功: ${ok}`,
    `失败: ${fail}`,
    '',
    ...notifyLines,
  ].join('\n');
  await sendNotifySafe(title, content);
}

main().catch(async (err) => {
  console.error(err.message || err);
  await sendNotifySafe(`${SCRIPT_NAME} 执行异常`, `时间: ${fmtTime(Date.now())}\n错误: ${err.message || err}`);
  process.exit(1);
});
