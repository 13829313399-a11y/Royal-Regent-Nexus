import { reactive } from 'vue'
let viewer = ''
const modes = reactive(new Map<string, 'legacy' | 'v2'>())
export function setIdentityViewer(id: string) {
  if (viewer !== id) {
    modes.clear()
    viewer = id
  }
}
export function rememberIdentityMode(viewerId: string, targetId: string, mode: 'legacy' | 'v2') {
  setIdentityViewer(viewerId)
  modes.set(targetId, mode)
}
export function knownIdentityMode(viewerId: string, targetId: string) {
  setIdentityViewer(viewerId)
  return modes.get(targetId) ?? 'unknown'
}
