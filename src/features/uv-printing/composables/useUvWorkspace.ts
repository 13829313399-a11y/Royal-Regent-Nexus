import { computed, ref, type ComputedRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { BusinessDate, ShiftScope, UvFactoryId, UvScope } from '../contracts'
import { UV_PREVIEW_PATH, UV_WORKSPACE_PATH, isUvPreviewEnabled } from '../transport/provider'
import { SAMPLE_AS_OF, SAMPLE_BUSINESS_DATE } from '../preview/constants'

/**
 * 工作区上下文：厂区、业务日期、班次、现场模式与权限。
 *
 * - 厂区是固定业务上下文，模块内不再造一套厂区选择器；
 * - 正式路由的 query 里出现其他厂区时立即停止请求并给出合法上下文引导，
 *   不悄悄切到华康A；
 * - 样例预览读取 query factory 只用于展示，不改变真实 authStore。
 */

export type UvPageMode = 'workspace' | 'preview'

export const UV_FACTORY: UvFactoryId = 'huakang-a'

export interface UvContextViolation {
  code: 'factory-mismatch' | 'factory-invalid' | 'preview-disabled'
  message: string
  hint: string
}

function firstQueryValue(value: unknown): string | undefined {
  if (Array.isArray(value)) return value.length ? String(value[0]) : undefined
  if (value === undefined || value === null) return undefined
  return String(value)
}

export function useUvWorkspace() {
  const route = useRoute()
  const router = useRouter()
  const appStore = useAppStore()
  const authStore = useAuthStore()

  const pageMode: ComputedRef<UvPageMode> = computed(() =>
    // 用路径前缀判断，父级与所有子路由都算样例预览；
    // 只判断路由名会漏掉子路由（子路由为了不与正式路由重名而没有名字）。
    route.path.startsWith(UV_PREVIEW_PATH) ? 'preview' : 'workspace',
  )
  const isPreview = computed(() => pageMode.value === 'preview')

  const queryFactory = computed(() => firstQueryValue(route.query.factory))
  const activeFactoryId = computed(() => appStore.activeFactoryId)
  const sampleDate = ref<BusinessDate>(SAMPLE_BUSINESS_DATE)
  const sampleAsOf = ref<string>(SAMPLE_AS_OF)

  const businessDate = computed<BusinessDate>(() =>
    isPreview.value
      ? (firstQueryValue(route.query.date) ?? sampleDate.value)
      : (firstQueryValue(route.query.date) ?? new Date().toISOString().slice(0, 10)),
  )

  const shift = computed<ShiftScope>(() => {
    const value = firstQueryValue(route.query.shift)
    return value === 'day' || value === 'night' ? value : 'all'
  })

  const violation = computed<UvContextViolation | null>(() => {
    if (isPreview.value) {
      if (!isUvPreviewEnabled()) {
        return {
          code: 'preview-disabled',
          message: '样例预览未开启。',
          hint: '需要 DEV 构建且显式设置 VITE_UV_PREVIEW=true；生产包不可达。',
        }
      }
      return null
    }
    if (queryFactory.value && queryFactory.value !== UV_FACTORY) {
      return {
        code: 'factory-mismatch',
        message: 'URL 指定的厂区与华康A不一致，已停止读取 UV 数据。',
        hint: `UV打印管理只在华康A生产部提供；请返回 ${UV_FACTORY} 上下文。`,
      }
    }
    if (activeFactoryId.value !== UV_FACTORY) {
      return {
        code: 'factory-mismatch',
        message: `当前有效厂区是「${appStore.activeFactory.name}」，不是华康A。`,
        hint: 'UV数据不会跨厂区显示；请先切回华康A，URL 的权限作用域不能代替有效厂区检查。',
      }
    }
    return null
  })

  const contextReady = computed(() => violation.value === null)

  const scope = computed<UvScope>(() => ({
    factory_id: UV_FACTORY,
    business_date: businessDate.value,
    shift: shift.value === 'all' ? undefined : shift.value,
  }))

  function scopeFor(overrides: Partial<UvScope> = {}): UvScope {
    return {
      ...scope.value,
      ...overrides,
      shift: overrides.shift ?? scope.value.shift,
    }
  }

  function setQuery(patch: Record<string, string | undefined>) {
    const next: Record<string, string> = {}
    for (const [key, value] of Object.entries({ ...route.query, ...patch })) {
      if (value === undefined || value === null || value === '') continue
      next[key] = String(value)
    }
    void router.replace({ query: next })
  }

  function setBusinessDate(value: BusinessDate) {
    if (isPreview.value) sampleDate.value = value
    setQuery({ date: value })
  }

  function setShift(value: ShiftScope) {
    setQuery({ shift: value === 'all' ? undefined : value })
  }

  const permissions = computed(() => [
    'uv_printing:read',
    'uv_printing:report',
    'uv_printing:quality',
    'uv_printing:master_write',
    'uv_printing:shift_write',
    'uv_printing:ink_write',
    'uv_printing:cost_read',
    'uv_printing:cost_write',
    'uv_printing:payroll_read',
    'uv_printing:payroll_write',
    'uv_printing:export',
  ].filter((permission) => can(permission)))
  const isReadOnly = computed(() => !can('uv_printing:report'))

  function can(permission: string): boolean {
    if (isPreview.value) return true
    return authStore.can(permission, UV_FACTORY, 'production')
  }

  const permissionDenied = computed(() => {
    if (isPreview.value) return false
    return !can('uv_printing:read')
  })

  function setSampleClock(asOf: string, date: BusinessDate) {
    sampleAsOf.value = asOf
    sampleDate.value = date
  }

  return {
    // 上下文
    pageMode,
    isPreview,
    business_date: businessDate,
    shift,
    queryFactory,
    activeFactoryId,
    violation,
    contextReady,
    // 作用域
    scope,
    scopeFor,
    setBusinessDate,
    setShift,
    // 权限
    can,
    permissions,
    isReadOnly,
    permissionDenied,
    // 样例时钟
    sampleAsOf,
    setSampleClock,
    // 路径常量
    workspacePath: UV_WORKSPACE_PATH,
  }
}

export type UvWorkspaceContext = ReturnType<typeof useUvWorkspace>
