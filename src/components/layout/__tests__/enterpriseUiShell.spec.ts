import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

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
const loadingBarSource = readSource('src/components/layout/RouteLoadingBar.vue')
const styleSource = readSource('src/style.css')
const buttonSource = readSource('src/components/ui/button/index.ts')
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

  it('uses restrained brand loading feedback with an explicit completion state', () => {
    expect(loadingBarSource).toContain('progressValue.value = 100')
    expect(loadingBarSource).toContain('from-teal-800 via-teal-500 to-cyan-400')
    expect(loadingBarSource).toContain("'h-[3px]")
    expect(loadingBarSource).not.toMatch(/from-emerald|to-lime|route-loading-sweep/)
  })

  it('keeps motion accessible and surfaces responsive', () => {
    expect(styleSource).toContain('@media (prefers-reduced-motion: reduce)')
    expect(styleSource).toContain('.enterprise-panel')
    expect(styleSource).toContain('.route-page-enter-active')
    expect(styleSource).toContain('overflow-x: clip')
    expect(appShellSource).toContain('class="app-shell-content flex min-w-0"')
    expect(sidebarSource).toContain('lg:w-[88px]')
    expect(sidebarSource).toContain('2xl:w-[260px]')
    expect(sidebarSource).toContain('lg:sr-only 2xl:not-sr-only')
    expect(topBarSource).toContain('<NotificationCenter />')
    // The switch keeps both the current responsive bell and the rollback implementation.
    expect(notificationCenterSource).toContain('VITE_WORK_CENTER_ENABLED')
    expect(notificationCenterSource).toContain('<WorkCenterBell v-if="enabled" />')
    expect(notificationCenterSource).toContain('<LegacyNotificationCenter v-else />')
    expect(workCenterBellSource).toContain('mobile ? DialogRoot : PopoverRoot')
    expect(workCenterBellSource).toContain('mobile ? DialogContent : PopoverContent')
    expect(workCenterBellSource).toContain('DialogDescription v-if="mobile"')
    expect(workCenterBellSource).toContain('aria-label="关闭通知面板"')
    expect(workCenterCss).toMatch(/\.nc-popover\s*\{[^}]*max-width:\s*calc\(100vw - 24px\)/)
    expect(workCenterCss).toMatch(/\.nc-bell-sheet\s*\{[^}]*position:\s*fixed;[^}]*max-height:\s*90dvh/)
    expect(workCenterCss).toContain('@media(prefers-reduced-motion:reduce)')
    expect(legacyNotificationSource).toContain("left: '12px'")
    expect(legacyNotificationSource).toContain("right: '12px'")
    expect(legacyNotificationSource).toContain("width: '430px'")
    expect(legacyNotificationSource).toContain('class="fixed z-[70]')
    expect(accountMenuSource).toContain('fixed left-3 right-3 top-[68px]')
    expect(accountMenuSource).toContain('sm:w-[calc(100vw-1.5rem)] sm:max-w-80')
  })

  it('adapts dashboard columns to the available content width', () => {
    expect(dashboardSource).toContain('container: dashboard-page / inline-size')
    expect(dashboardSource).toContain('@container dashboard-page (min-width: 36rem)')
    expect(dashboardSource).toContain('@container dashboard-page (min-width: 62rem)')
    expect(dashboardSource).toContain('@container dashboard-page (min-width: 68rem)')
    expect(dashboardSource).not.toContain('md:grid-cols-2 xl:grid-cols-4')
    expect(dashboardSource).not.toContain('xl:grid-cols-[1fr_350px]')
  })

  it('exposes the requested primary, secondary, soft, ghost, and destructive button hierarchy', () => {
    for (const variant of ['default:', 'secondary:', 'soft:', 'ghost:', 'destructive:']) {
      expect(buttonSource).toContain(variant)
    }
    expect(buttonSource).toContain('hover:bg-primary/90')
  })

  it('keeps the approval table overflow inside its own grid column', () => {
    expect(approvalWorkbenchSource).toContain('class="min-w-0 space-y-6"')
    expect(approvalTableSource).toContain('class="overflow-x-auto"')
    expect(approvalTableSource).toContain(':aria-pressed="row.id === selectedId"')
  })
})
