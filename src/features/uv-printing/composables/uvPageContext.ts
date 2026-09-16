import type { InjectionKey, Ref } from 'vue'
import type { UvWorkspaceTransport } from '../contracts'
import type { useUvWorkspace } from './useUvWorkspace'

/**
 * 页面上下文注入：所有页面共用同一套 contracts、transport 与筛选上下文。
 * 组件不得直接调用 PocketBase 或自己维护另一份工资/库存公式。
 */

export interface UvPageContext {
  /** 厂区、业务日期、班次、现场模式与权限。 */
  workspace: ReturnType<typeof useUvWorkspace>
  /** 当前 transport：正式接口或 DEV 样例内存实现。 */
  transport: Ref<UvWorkspaceTransport>
  /** 任何命令成功后自增，驱动所有页面重新派生。 */
  revision: Ref<number>
  /** 数据变化后通知壳层/其他页面刷新。 */
  markDirty: () => void
  /** 该页面是否使用样例数据。 */
  isPreview: Ref<boolean>
}

export const UV_TRANSPORT_KEY: InjectionKey<Ref<UvWorkspaceTransport>> = Symbol('uv-transport')
export const UV_CONTEXT_KEY: InjectionKey<UvPageContext> = Symbol('uv-context')
