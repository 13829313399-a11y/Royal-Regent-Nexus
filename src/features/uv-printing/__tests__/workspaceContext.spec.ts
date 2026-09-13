import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { useUvWorkspace } from '../composables/useUvWorkspace'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

/**
 * 工作区上下文契约。
 *
 * 这里锁定三条容易静默失效的边界：
 * 1. 只有 `/__preview/uv-printing` 前缀才是样例预览（生产入口不得被判成预览）；
 * 2. 正式环境下权限必须落到宿主 authStore，而不是「一律放行」；
 * 3. 有效厂区不是华康A 时必须给出违规状态，让页面停止读取。
 */

const WORKSPACE_PATH = '/modules/production/uv-printing/overview'
const PREVIEW_PATH = '/__preview/uv-printing/overview'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: WORKSPACE_PATH, component: { template: '<div />' } },
      { path: PREVIEW_PATH, component: { template: '<div />' } },
    ],
  })
}

let captured: ReturnType<typeof useUvWorkspace> | null = null

async function mountContext(router: Router) {
  const probe = defineComponent({
    setup() {
      captured = useUvWorkspace()
      return () => h('div')
    },
  })
  const wrapper = mount(probe, { global: { plugins: [router] } })
  await router.isReady()
  await wrapper.vm.$nextTick()
  return wrapper
}

async function visit(router: Router, path: string, query: Record<string, string> = {}) {
  await router.push({ path, query })
  await router.isReady()
}

describe('useUvWorkspace', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    captured = null
  })

  it('只有 /__preview/uv-printing 前缀被判为样例预览', async () => {
    const router = makeRouter()
    const wrapper = await mountContext(router)

    await visit(router, PREVIEW_PATH)
    await wrapper.vm.$nextTick()
    expect(captured!.pageMode.value).toBe('preview')
    expect(captured!.isPreview.value).toBe(true)

    await visit(router, WORKSPACE_PATH, { factory: 'huakang-a' })
    await wrapper.vm.$nextTick()
    expect(captured!.pageMode.value).toBe('workspace')
    expect(captured!.isPreview.value).toBe(false)
    wrapper.unmount()
  })

  it('正式环境下权限落到宿主 authStore，且未被预览分支短路', async () => {
    const router = makeRouter()
    useAuthStore().isAuthenticated = true
    useAppStore().setActiveFactory('huakang-a')
    const wrapper = await mountContext(router)
    await visit(router, WORKSPACE_PATH, { factory: 'huakang-a' })
    await wrapper.vm.$nextTick()

    const can = vi.spyOn(useAuthStore(), 'can')
    // 没有任何生效权限时，正式路由必须返回 false（不是「预览一律放行」）。
    expect(captured!.can('uv_printing:read')).toBe(false)
    expect(can).toHaveBeenCalled()
    expect(captured!.permissionDenied.value).toBe(true)
    expect(captured!.isReadOnly.value).toBe(true)
    wrapper.unmount()
  })

  it('预览环境下不读真实授权，权限判定为可用（只影响样例内存）', async () => {
    const router = makeRouter()
    useAppStore().setActiveFactory('group')
    const wrapper = await mountContext(router)
    await visit(router, PREVIEW_PATH)
    await wrapper.vm.$nextTick()

    expect(captured!.violation.value).toBeNull()
    expect(captured!.contextReady.value).toBe(true)
    expect(captured!.permissionDenied.value).toBe(false)
    wrapper.unmount()
  })

  it('有效厂区不是华康A 时给出 factory-mismatch，并停止上下文就绪', async () => {
    const router = makeRouter()
    useAuthStore().isAuthenticated = true
    useAppStore().setActiveFactory('huaxing')
    const wrapper = await mountContext(router)
    await visit(router, WORKSPACE_PATH, { factory: 'huakang-a' })
    await wrapper.vm.$nextTick()

    expect(captured!.violation.value?.code).toBe('factory-mismatch')
    expect(captured!.contextReady.value).toBe(false)
    wrapper.unmount()
  })

  it('URL 指定别的厂区时也判定违规，不悄悄改用华康A', async () => {
    const router = makeRouter()
    useAuthStore().isAuthenticated = true
    useAppStore().setActiveFactory('huakang-a')
    const wrapper = await mountContext(router)
    await visit(router, WORKSPACE_PATH, { factory: 'huadeng' })
    await wrapper.vm.$nextTick()

    expect(captured!.violation.value?.code).toBe('factory-mismatch')
    expect(captured!.violation.value?.message).toContain('停止读取')
    wrapper.unmount()
  })

  it('作用域始终显式带 factory_id=huakang-a，全天时省略 shift', async () => {
    const router = makeRouter()
    useAppStore().setActiveFactory('huakang-a')
    const wrapper = await mountContext(router)
    await visit(router, WORKSPACE_PATH, { factory: 'huakang-a', date: '2026-09-13' })
    await wrapper.vm.$nextTick()

    expect(captured!.scope.value.factory_id).toBe('huakang-a')
    expect(captured!.scope.value.business_date).toBe('2026-09-13')
    expect(captured!.scope.value.shift).toBeUndefined()

    captured!.setShift('night')
    // setShift 走 router.replace，需要等导航完成后再断言 query 派生值。
    await router.isReady()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(captured!.shift.value).toBe('night')
    expect(captured!.scope.value.shift).toBe('night')
    expect(captured!.scopeFor().shift).toBe('night')
    expect(router.currentRoute.value.query.shift).toBe('night')
    wrapper.unmount()
  })

  it('未知班次 query 归一为全天，非法日期不覆盖业务日回退', async () => {
    const router = makeRouter()
    useAppStore().setActiveFactory('huakang-a')
    const wrapper = await mountContext(router)
    await visit(router, WORKSPACE_PATH, { factory: 'huakang-a', shift: 'midnight' })
    await wrapper.vm.$nextTick()

    expect(captured!.shift.value).toBe('all')
    expect(captured!.scope.value.shift).toBeUndefined()
    wrapper.unmount()
  })
})
