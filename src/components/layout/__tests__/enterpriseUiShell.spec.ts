import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick, ref } from 'vue'
import RouteLoadingBar from '@/components/layout/RouteLoadingBar.vue'
import { Button, Progress } from '@/components/ui'
import { useAppStore } from '@/stores/app'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const appShellSource = readSource('src/components/layout/AppShell.vue')
const topBarSource = readSource('src/components/layout/TopBar.vue')
const notificationCenterSource = readSource('src/components/notifications/NotificationCenter.vue')
const legacyNotificationSource = readSource('src/components/notifications/LegacyNotificationCenter.vue')
const workCenterBellSource = readSource('src/features/work-center/WorkCenterBell.vue')
const workCenterCss = readSource('src/features/work-center/work-center.css')
const accountMenuSource = readSource('src/components/layout/AccountMenu.vue')
const sidebarSource = readSource('src/components/layout/SidebarNav.vue')
const styleSource = readSource('src/style.css')
const approvalWorkbenchSource = readSource('src/views/ApprovalWorkbenchView.vue')
const approvalTableSource = readSource('src/components/workbench/ApprovalTable.vue')
const dashboardSource = readSource('src/views/DashboardView.vue')

describe('enterprise UI shell contract', () => {
  it('provides a responsive mobile navigation without changing route-driven content', () => {
    expect(topBarSource).toContain('aria-label="打开全局导航"')
    expect(topBarSource).toContain('aria-controls="global-navigation"')
    expect(topBarSource).toContain(':aria-expanded="props.navigationOpen"')
    expect(topBarSource).toContain('navigationTriggerRef.value?.focus()')
    expect(sidebarSource).toContain('aria-label="全局导航"')
    expect(sidebarSource).toContain('id="global-navigation"')
    expect(sidebarSource).toContain('aria-label="关闭全局导航"')
    expect(sidebarSource).toContain('@keydown="trapMobileFocus"')
    expect(sidebarSource).toContain('mobileCloseButtonRef.value?.focus()')
    expect(appShellSource).toContain(':mobile-open="isMobileNavigationOpen"')
    expect(appShellSource).toContain('@close="isMobileNavigationOpen = false"')
    expect(appShellSource).toContain('acquireBodyScrollLock()')
    expect(appShellSource).toContain("document.addEventListener('keydown', closeNavigationOnEscape)")
    expect(appShellSource).toContain("window.matchMedia('(min-width: 1024px)')")
    expect(appShellSource).toContain("desktopMediaQuery.addEventListener('change', closeNavigationAtDesktop)")
    expect(appShellSource).not.toContain(':key="route.path"')
    expect(appShellSource).not.toContain(':key="route.fullPath"')
  })

  it('reports loading progress without premature completion, resets and cancels stale timers', async () => {
    vi.useFakeTimers()
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    const wrapper = mount(RouteLoadingBar, { global: { plugins: [pinia] } })
    const progress = () => Number(wrapper.getComponent(Progress).props('modelValue'))
    try {
      expect(progress()).toBe(0)
      expect(wrapper.get('[role="progressbar"]').attributes('aria-hidden')).toBe('true')
      store.startRouteLoading()
      await nextTick()
      const initial = progress()
      expect(initial).toBeGreaterThan(0)
      expect(initial).toBeLessThan(100)
      vi.runAllTimers()
      await nextTick()
      expect(progress()).toBeGreaterThan(initial)
      expect(progress()).toBeLessThan(100)
      store.finishRouteLoading()
      await nextTick()
      expect(progress()).toBe(100)

      // A newer navigation must cancel the previous completion/reset timer.
      store.startRouteLoading()
      await nextTick()
      expect(progress()).toBeGreaterThan(0)
      expect(progress()).toBeLessThan(100)
      vi.runAllTimers()
      await nextTick()
      expect(progress()).toBeGreaterThan(0)
      expect(progress()).toBeLessThan(100)
      store.finishRouteLoading()
      await nextTick()
      expect(progress()).toBe(100)
      vi.runAllTimers()
      await nextTick()
      expect(progress()).toBe(0)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('keeps motion accessible and surfaces responsive', () => {
    expect(styleSource).toContain('@media (prefers-reduced-motion: reduce)')
    expect(styleSource).toContain('.enterprise-panel')
    expect(appShellSource).not.toContain('mode="out-in"')
    expect(styleSource).toContain('overflow-x: clip')
    expect(appShellSource).toContain('class="app-shell-content flex min-w-0"')
    // Compact/expanded widths are visual defaults; names and active state must survive either mode.
    expect(sidebarSource).toContain(':aria-label="item.label"')
    expect(sidebarSource).toContain(':aria-current="isActive(item, group.label) ? \'page\' : undefined"')
    expect(sidebarSource).toContain('@keydown.esc="emit(\'close\')"')
    expect(topBarSource).toContain('<NotificationCenter />')
    // The switch keeps both the current responsive bell and the rollback implementation.
    expect(notificationCenterSource).toContain('VITE_WORK_CENTER_ENABLED')
    expect(notificationCenterSource).toContain('<WorkCenterBell v-if="enabled" />')
    expect(notificationCenterSource).toContain('<LegacyNotificationCenter v-else />')
    expect(workCenterBellSource).toContain('mobile ? Drawer : Popover')
    expect(workCenterBellSource).toContain('mobile ? DrawerContent : PopoverContent')
    expect(workCenterBellSource).toMatch(/<DrawerDescription\s+v-if="mobile"/)
    expect(workCenterBellSource).toContain('label="关闭通知面板"')
    expect(workCenterCss).toMatch(/\.nc-popover\s*\{[^}]*max-width:\s*calc\(100vw - 24px\)/)
    expect(workCenterBellSource).toMatch(/side:\s*'bottom'/)
    expect(workCenterCss).toMatch(/\.nc-bell-sheet\s*\{[^}]*max-height:\s*88dvh/)
    expect(workCenterCss).toContain('@media (prefers-reduced-motion: reduce)')
    expect(workCenterCss).toContain('@media (prefers-reduced-transparency: reduce)')
    expect(legacyNotificationSource).toContain("left: '12px'")
    expect(legacyNotificationSource).toContain("right: '12px'")
    expect(legacyNotificationSource).toContain("width: '430px'")
    expect(legacyNotificationSource).toContain('class="fixed z-[70]')
    expect(accountMenuSource).toContain(':style="menuStyle"')
    expect(accountMenuSource).toContain('window.visualViewport')
  })

  it('adapts dashboard columns to the available content width', () => {
    expect(dashboardSource).toContain('container: dashboard-page / inline-size')
    // Keep content-width adaptation without locking the exact breakpoint values or column counts.
    const queries = [...dashboardSource.matchAll(/@container dashboard-page\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/g)]
    expect(queries.length).toBeGreaterThan(0)
    expect(queries.some((query) => query[1]?.includes('.dashboard-metrics'))).toBe(true)
    expect(queries.some((query) => query[1]?.includes('.dashboard-primary-grid'))).toBe(true)
  })

  it.each(['default', 'outline', 'secondary', 'soft', 'ghost', 'destructive', 'link'] as const)(
    'preserves the %s button API and native activation without fixing its visual treatment',
    async (variant) => {
      const onClick = vi.fn()
      const disabled = ref(false)
      const wrapper = mount(defineComponent({
        components: { Button },
        setup: () => ({ variant, disabled, onClick }),
        template: '<Button :variant="variant" type="button" :disabled="disabled" @click="onClick">操作</Button>',
      }))
      try {
        const button = wrapper.get('button')
        expect(button.attributes('data-variant')).toBe(variant)
        expect(button.text()).toBe('操作')
        await button.trigger('click')
        expect(onClick).toHaveBeenCalledTimes(1)
        disabled.value = true
        await nextTick()
        const nativeButton = button.element as HTMLButtonElement
        expect(nativeButton.disabled).toBe(true)
        nativeButton.click()
        expect(onClick).toHaveBeenCalledTimes(1)
      } finally {
        wrapper.unmount()
      }
    },
  )

  it('keeps the approval table overflow inside its own grid column', () => {
    expect(approvalWorkbenchSource).toContain('class="min-w-0 space-y-6"')
    expect(approvalTableSource).toContain('class="overflow-x-auto"')
    expect(approvalTableSource).toContain(':aria-pressed="row.id === selectedId"')
  })
})
