import { uvPrintingApi } from '@/api/uvPrinting'
import type { UvWorkspaceTransport } from '../contracts'

/**
 * 传输层门面：正式路由永远拿真实 transport，样例路由拿内存 transport。
 *
 * 关键约束：接口失败、403、断网都**不得**回落到样例 provider；
 * 正式路由收到 `data_mode: 'sample'` 应视为配置错误并停止操作。
 */

/** 仅 DEV 且显式开启 `VITE_UV_PREVIEW=true` 时样例预览可用。 */
export function isUvPreviewEnabled(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_UV_PREVIEW === 'true'
}

/** 正式发布开关：未定义等同关闭。 */
export function isUvModuleEnabled(): boolean {
  return import.meta.env.VITE_UV_ENABLED === 'true'
}

export const UV_PREVIEW_PATH = '/__preview/uv-printing'
export const UV_WORKSPACE_PATH = '/modules/production/uv-printing'

export function realUvTransport(): UvWorkspaceTransport {
  return uvPrintingApi
}

type PreviewModule = typeof import('../preview/memoryStore')

let previewModulePromise: Promise<PreviewModule> | null = null

/**
 * 样例 transport 通过动态 import 加载，生产构建不会静态引入样例数据。
 */
export async function loadSampleTransport() {
  if (!import.meta.env.DEV || import.meta.env.VITE_UV_PREVIEW !== 'true') {
    throw new Error('UV 样例预览未开启：需要 DEV 且 VITE_UV_PREVIEW=true。')
  }
  previewModulePromise ??= import('../preview/memoryStore')
  const module = await previewModulePromise
  return new module.UvMemoryStore()
}
