import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('system user management routing', () => {
  it('adds public registration, protected system users, and forbidden routes', () => {
    expect(source).toMatch(/path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
    expect(source).toMatch(/path:\s*'\/system\/users'[\s\S]{0,360}permissions:\s*\[['"]system:user_manage['"]\]/)
    expect(source).toMatch(/name:\s*'forbidden'/)
    expect(source).toMatch(/authStore\.hasAnyPermission/)
  })
})
