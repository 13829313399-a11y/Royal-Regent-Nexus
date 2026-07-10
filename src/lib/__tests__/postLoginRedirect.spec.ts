import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { resolvePostLoginRedirect } from '../postLoginRedirect'

const EmptyView = defineComponent({ template: '<div />' })

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        component: EmptyView,
        meta: { requiresAuth: true },
      },
      {
        path: '/login',
        component: EmptyView,
        meta: { requiresAuth: false },
      },
      {
        path: '/register',
        component: EmptyView,
        meta: { requiresAuth: false },
      },
      {
        path: '/modules/molding-sample',
        component: EmptyView,
        meta: { requiresAuth: true },
      },
    ],
  })
}

describe('resolvePostLoginRedirect', () => {
  it('falls back to the dashboard when redirect points to a public auth page', () => {
    const router = createTestRouter()

    expect(resolvePostLoginRedirect(router, '/register')).toBe('/')
    expect(resolvePostLoginRedirect(router, '/login?redirect=/register')).toBe('/')
  })

  it('keeps a valid protected-page redirect and rejects protocol-relative URLs', () => {
    const router = createTestRouter()

    expect(resolvePostLoginRedirect(router, '/modules/molding-sample?factory=huaxing')).toBe(
      '/modules/molding-sample?factory=huaxing',
    )
    expect(resolvePostLoginRedirect(router, '//example.com')).toBe('/')
  })
})
