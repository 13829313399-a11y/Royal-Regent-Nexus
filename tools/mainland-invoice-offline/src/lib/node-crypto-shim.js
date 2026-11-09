/**
 * node:crypto 的浏览器垫片——只实现 officecrypto-tool 解密投喂文件用到的子集：
 * createHash / createHmac / createCipheriv / createDecipheriv / randomBytes / getHashes。
 * 哈希与 AES 全部由 crypto-js（纯 JS）承担；Buffer 与 WordArray 互转走 buffer 包。
 * 由 vite.config 里 resolve.alias 把 'crypto' 指到本文件（浏览器与 vitest 都生效）。
 * 注意：cipher 的 update() 只缓存不产出，final() 一次性返回全部结果——officecrypto-tool
 * 所有调用点都是 Buffer.concat([update(...), final()])，语义等价。
 */
import CryptoJS from 'crypto-js'
import { Buffer as PolyfillBuffer } from 'buffer'

// officecrypto-tool 用的是全局 Buffer：浏览器里由 FactoryHxg 在上传解密前注入 polyfill，
// node/vitest 里是原生实现。这里随调用现场取同一个实现，避免两套 Buffer 混用
// （node 原生 Buffer.concat 对 polyfill 实例的 instanceof 检查会直接抛错）。
const getBuffer = () => globalThis.Buffer || PolyfillBuffer

// 诊断标记：本模块被加载说明 officecrypto-tool 的 require('crypto') 确实走到了这个垫片
// （hx-smoke.test.jsx 据此断言 jsdom 测试覆盖的是浏览器同款代码路径）
globalThis.__HXG_CRYPTO_SHIM_USED__ = true

const HASHERS = {
  md5: CryptoJS.algo.MD5,
  sha1: CryptoJS.algo.SHA1,
  sha256: CryptoJS.algo.SHA256,
  sha384: CryptoJS.algo.SHA384,
  sha512: CryptoJS.algo.SHA512,
}

const hashAlgo = (name) => {
  const h = HASHERS[String(name).toLowerCase().replace(/-/g, '')]
  if (!h) throw new Error(`crypto shim: 不支持的哈希算法 ${name}`)
  return h
}

const toWa = (data) => {
  if (typeof data === 'string') return CryptoJS.enc.Utf8.parse(data)
  return CryptoJS.lib.WordArray.create(data instanceof Uint8Array ? data : new Uint8Array(data))
}

const waToBuf = (wa) => {
  const out = new Uint8Array(wa.sigBytes)
  for (let i = 0; i < wa.sigBytes; i++) out[i] = (wa.words[i >>> 2] >>> (24 - (i % 4) * 8)) & 0xff
  return getBuffer().from(out)
}

export function createHash(algorithm) {
  const h = hashAlgo(algorithm).create()
  return {
    update(data) { h.update(toWa(data)); return this },
    digest() { return waToBuf(h.finalize()) },
  }
}

export function createHmac(algorithm, key) {
  const h = CryptoJS.algo.HMAC.create(hashAlgo(algorithm), toWa(key))
  return {
    update(data) { h.update(toWa(data)); return this },
    digest() { return waToBuf(h.finalize()) },
  }
}

function makeCipher(isEncrypt, name, key, iv) {
  const m = /^aes-(\d+)-(ecb|cbc)$/i.exec(String(name))
  if (!m) throw new Error(`crypto shim: 不支持的加密算法 ${name}`)
  const mode = m[2].toLowerCase() === 'cbc' ? CryptoJS.mode.CBC : CryptoJS.mode.ECB
  const keyWa = toWa(key)
  const ivWa = iv && iv.length ? toWa(iv) : undefined
  let autoPadding = true
  const pending = []
  return {
    setAutoPadding(flag) { autoPadding = !!flag },
    update(data) { pending.push(toWa(data)); return getBuffer().alloc(0) },
    final() {
      const input = pending.reduce((acc, wa) => acc.concat(wa), CryptoJS.lib.WordArray.create())
      const cfg = { iv: ivWa, mode, padding: autoPadding ? CryptoJS.pad.Pkcs7 : CryptoJS.pad.NoPadding }
      const result = isEncrypt
        ? CryptoJS.AES.encrypt(input, keyWa, cfg).ciphertext
        : CryptoJS.AES.decrypt(CryptoJS.lib.CipherParams.create({ ciphertext: input }), keyWa, cfg)
      return waToBuf(result)
    },
  }
}

export const createCipheriv = (name, key, iv) => makeCipher(true, name, key, iv)
export const createDecipheriv = (name, key, iv) => makeCipher(false, name, key, iv)

export function randomBytes(n) {
  const out = new Uint8Array(n)
  const rnd = globalThis.crypto
  if (rnd && rnd.getRandomValues) rnd.getRandomValues(out)
  else for (let i = 0; i < n; i++) out[i] = Math.floor(Math.random() * 256)
  return getBuffer().from(out)
}

export const getHashes = () => Object.keys(HASHERS)

export default { createHash, createHmac, createCipheriv, createDecipheriv, randomBytes, getHashes }
