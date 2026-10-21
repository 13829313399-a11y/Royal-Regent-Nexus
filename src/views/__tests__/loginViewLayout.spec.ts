import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
const read = (path: string) => readFileSync(path, 'utf8')
describe('authentication layout boundary', () => {
  it('limits the persistent layout to the four authentication routes', () => {
    const shell = read('src/components/layout/AppShell.vue')
    expect(shell).toContain("['login', 'register', 'reset-password', 'change-password']")
    expect(shell).toContain('<AuthExperienceShell v-if="isAuthExperience"><RouterView /></AuthExperienceShell>')
    expect(shell).toContain('<RouterView v-else-if="isFullPage" />')
  })
  it('uses the original shared logo and only real public organization nodes', () => {
    const brand = read('src/components/auth/AuthBrandScene.vue')
    expect(brand).toContain('src="/brand/huadeng_group_dynamic_logo_topbar.svg"')
    expect(brand).not.toContain('public/brand/')
    expect(brand).toContain('authApi.organizationCatalog()')
    expect(brand).not.toContain('23/24')
    expect(read('index.html')).toContain('正在准备工作空间')
  })
})
