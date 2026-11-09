/**
 * 内置资源加载：优先读离线包内嵌数据（window.__OFFLINE_ASSETS__，打包脚本注入），
 * 没有再走 fetch（局域网服务器版）。带缓存，重复调用不重复解码。
 */
const cache = new Map();

function base64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}

export function loadAsset(path) {
  if (cache.has(path)) return cache.get(path);
  const p = (async () => {
    const assets = typeof window !== 'undefined' ? window.__OFFLINE_ASSETS__ : null;
    const inline = assets && (assets[path] || assets[decodeURI(path)]);
    if (inline) return base64ToArrayBuffer(inline);
    const resp = await fetch(encodeURI(path));
    if (!resp.ok) throw new Error(`内置资源加载失败: ${path} (${resp.status})`);
    return resp.arrayBuffer();
  })();
  cache.set(path, p);
  return p;
}
