import { useEffect, useId } from 'react'
import { nexusBase } from '../deployment'
import { Modal } from 'antd'
import { isNexusSessionLocked, subscribeSession } from './permissions'

const drafts = new Map<string, { dirty: boolean; pending: boolean }>()
let writes = 0
export function navigationState() { return { dirty: [...drafts.values()].some(v => v.dirty), pending: writes > 0 || [...drafts.values()].some(v => v.pending) } }
function publish() {
  if (nexusBase() && window.parent !== window) window.parent.postMessage({ type: 'nexus-shipping-navigation', ...navigationState() }, window.location.origin)
}
export function useNavigationDraft(dirty: boolean, pending = false) {
  const id = useId()
  useEffect(() => {
    if (!nexusBase()) return
    drafts.set(id, { dirty, pending }); publish()
    return () => { drafts.delete(id); publish() }
  }, [id, dirty, pending])
}
export function beginNavigationWrite() {
  if (!nexusBase()) return () => {}
  writes++; publish()
  let finished = false
  return () => { if (!finished) { finished = true; writes--; publish() } }
}
let confirmation: Promise<boolean> | null = null
let cancelConfirmation: (() => void) | null = null
subscribeSession(() => { if (isNexusSessionLocked()) cancelConfirmation?.() })
export function confirmNavigation(): Promise<boolean> {
  const state = navigationState()
  if (!state.pending && !state.dirty) return Promise.resolve(true)
  if (confirmation) return confirmation
  confirmation = new Promise(resolve => {
    const finish = (value: boolean) => { confirmation = null; cancelConfirmation = null; resolve(value) }
    const dialog = Modal.confirm({
      title: state.pending ? '操作正在提交' : '离开当前工作区？',
      content: state.pending ? '请等待当前操作完成后再离开。' : '当前有修改或编辑窗口尚未关闭。离开会放弃尚未保存的内容。',
      okText: '不保存并离开', cancelText: '继续留在工作区',
      okButtonProps: { disabled: state.pending },
      onOk: () => finish(true), onCancel: () => finish(false),
    })
    cancelConfirmation = () => { dialog.destroy(); finish(false) }
  })
  return confirmation
}
if (typeof window !== 'undefined') window.addEventListener('beforeunload', event => {
  const state = navigationState()
  if (nexusBase() && (state.dirty || state.pending)) { event.preventDefault(); event.returnValue = '' }
})
