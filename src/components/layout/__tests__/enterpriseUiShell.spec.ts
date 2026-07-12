import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const appShellSource = readSource('src/components/layout/AppShell.vue')
const topBarSource = readSource('src/components/layout/TopBar.vue')
const accountMenuSource = readSource('src/components/layout/AccountMenu.vue')
const sidebarSource = readSource('src/components/layout/SidebarNav.vue')
const loadingBarSource = readSource('src/components/layout/RouteLoadingBar.vue')
const styleSource = readSource('src/style.css')
const buttonSource = readSource('src/components/ui/button/index.ts')
const approvalWorkbenchSource = readSource('src/views/ApprovalWorkbenchView.vue')
const approvalTableSource = readSource('src/components/workbench/ApprovalTable.vue')

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
    expect(appShellSource).toContain("document.body.style.overflow = 'hidden'")
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
    expect(topBarSource).toContain('fixed left-3 right-3 top-[68px]')
    expect(topBarSource).toContain('sm:w-[calc(100vw-1.5rem)] sm:max-w-[380px]')
    expect(accountMenuSource).toContain('fixed left-3 right-3 top-[68px]')
    expect(accountMenuSource).toContain('sm:w-[calc(100vw-1.5rem)] sm:max-w-80')
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
