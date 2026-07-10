import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const loginViewSource = readFileSync(join(process.cwd(), 'src/views/LoginView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('post-login navigation integration', () => {
  it('uses the shared protected-route resolver instead of trusting an auth-page redirect', () => {
    expect(loginViewSource).toMatch(/resolvePostLoginRedirect\(router,\s*route\.query\.redirect\)/)
    expect(loginViewSource).not.toMatch(/router\.replace\(redirect\.value\)/)
  })

  it('applies the same redirect policy when an existing session opens the login route', () => {
    expect(routerSource).toMatch(/resolvePostLoginRedirect\(router,\s*to\.query\.redirect\)/)
    expect(routerSource).not.toMatch(/const redirect = typeof to\.query\.redirect/)
  })
})
