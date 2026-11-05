/**
 * 尽早把 Buffer polyfill 挂到全局：officecrypto-tool（投喂解密）的模块顶层有
 * Buffer.from(...) 常量（BLOCK_KEYS、zip 魔数），离线单文件版全量内联后这些顶层
 * 代码随 bundle 启动就执行，等不到上传时再注入。本模块作为 main.tsx 的第一个
 * import，保证在任何模块顶层代码之前就位。浏览器才需要；node/vitest 自带 Buffer。
 */
import { Buffer } from 'buffer'

if (!globalThis.Buffer) globalThis.Buffer = Buffer
