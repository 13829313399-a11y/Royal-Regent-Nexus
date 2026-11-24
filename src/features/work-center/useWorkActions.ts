import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkCenterStore } from '@/stores/workCenter'
import { entryRoute } from './routes'
import type { WorkEntry } from './types'

export function useWorkActions() {
  const router = useRouter(),
    center = useWorkCenterStore(),
    auth = useAuthStore()
  function preview(entry: WorkEntry) {
    center.panelOpen = false
    return router.push({
      name: 'notification-center',
      query: { view: entry.kind === 'info' ? 'info' : 'todo', entry: entry.id },
    })
  }
  async function open(entry: WorkEntry) {
    const action = entry.actions.find((item) => item.enabled)
    const route = entryRoute(entry)
    if (!route && action?.mode !== 'refresh_identity') return preview(entry)
    center.panelOpen = false
    if (entry.personal.read_state !== 'read')
      void center.patch(entry, { observed_content_version: entry.content_version }, false)
    if (action?.mode === 'refresh_identity') {
      await auth.refreshSession()
      await center.refresh()
      if (auth.currentUser && !center.error) center.feedback = '账户信息已刷新'
    } else if (route) await router.push(route)
  }
  return { open, preview }
}
