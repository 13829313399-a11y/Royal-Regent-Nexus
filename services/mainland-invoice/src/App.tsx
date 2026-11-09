import { useEffect, useState } from 'react'
import FactoryHka from './pages/FactoryHka'
import FactoryHkb from './pages/FactoryHkb'
import FactoryHkd from './pages/FactoryHkd'
import { assertOperationAllowed, invalidateSession, startSession } from './lib/session.js'

const pages = { 'huakang-a': FactoryHka, 'huakang-b': FactoryHkb, 'huakang-d': FactoryHkd }
type Factory = keyof typeof pages

export default function App() {
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const factory = new URLSearchParams(window.location.search).get('factory_id') as Factory
  useEffect(() => {
    let disposed = false
    let authorized = false
    const lock = () => { if (!disposed) { setReady(false); setError('会话或权限已失效，请从业务部重新打开。') } }
    window.addEventListener('mainland-invoice-access-lost', lock)
    startSession(factory).then(() => { if (!disposed) { authorized = true; setReady(true) } }).catch((e: Error) => { if (!disposed) setError(e.message) })
    const validate = () => { if (authorized) void assertOperationAllowed().catch(lock) }
    const focus = () => { if (document.visibilityState === 'visible') validate() }
    const interval = window.setInterval(validate, 60000)
    document.addEventListener('visibilitychange', focus)
    window.addEventListener('focus', validate)
    return () => {
      disposed = true
      window.clearInterval(interval)
      window.removeEventListener('mainland-invoice-access-lost', lock)
      window.removeEventListener('focus', validate)
      document.removeEventListener('visibilitychange', focus)
      invalidateSession()
    }
  }, [factory])
  const Page = pages[factory]
  if (!ready || !Page) return <main className="p-8" role="status">{error || '正在检查厂区权限与私有模板…'}</main>
  return <><aside className="border-b border-teal-200 bg-teal-50 px-6 py-3 text-sm">
    在线生成与下载，不保存记录或发票历史。切换厂区会清空本页，下载后请核对金额与票号。
  </aside><Page /></>
}
