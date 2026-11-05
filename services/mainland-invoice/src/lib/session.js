import JSZip from 'jszip'

const SUPPORTED = new Set(['huakang-a', 'huakang-b', 'huakang-d'])
const INVALIDATED = 'mainland-invoice-access-lost'
let active = null
let epoch = 0

export function invalidateSession() {
  active = null
  epoch += 1
  window.dispatchEvent(new Event(INVALIDATED))
}

async function request(url) {
  const response = await fetch(url, {
    credentials: 'same-origin', cache: 'no-store',
    headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(20000),
  })
  if (!response.ok) {
    let detail = '大陆发票服务暂不可用，请重新登录或联系管理员'
    try { detail = (await response.json()).detail || detail } catch { /* no JSON body */ }
    throw new Error(typeof detail === 'string' ? detail : '厂区或模板配置无效')
  }
  return response
}

export async function startSession(factoryId) {
  if (!SUPPORTED.has(factoryId)) throw new Error('第一版仅支持华康 A、B、D，不能选择其他厂区')
  const token = ++epoch
  active = null
  const context = await (await request('/api/mainland-invoices/context?factory_id=' + encodeURIComponent(factoryId))).json()
  if (token !== epoch) throw new Error('厂区已变化，请重新打开')
  if (context.factory_id !== factoryId) throw new Error('服务器返回了错误的厂区')
  if (!context.user_id || !Number.isInteger(context.employment_epoch)) throw new Error('服务器返回了无效的会话身份')
  active = { factoryId, userId: context.user_id, employmentEpoch: context.employment_epoch, templates: context.templates, token }
  return context
}

export async function assertOperationAllowed(expected = null) {
  const snapshot = active
  if (!snapshot) throw new Error('当前会话已失效，请重新打开大陆发票')
  if (expected && expected !== snapshot) throw new Error('厂区或账号已变化，请重新打开')
  try {
    const context = await (await request('/api/mainland-invoices/context?factory_id=' + encodeURIComponent(snapshot.factoryId))).json()
    if (active !== snapshot || context.factory_id !== snapshot.factoryId) throw new Error('厂区已变化，请重新打开')
    if (context.user_id !== snapshot.userId || context.employment_epoch !== snapshot.employmentEpoch) {
      throw new Error('账号或任职身份已变化，请重新打开大陆发票')
    }
    return snapshot
  } catch (error) {
    if (active === snapshot) invalidateSession()
    throw error
  }
}

export async function loadPrivateTemplate(path) {
  const snapshot = active
  const key = snapshot?.templates?.[path]
  if (!snapshot || !key) throw new Error('此模板不属于当前授权厂区')
  try {
    await assertOperationAllowed()
    const response = await request('/api/mainland-invoices/templates/' + encodeURIComponent(key) + '?factory_id=' + encodeURIComponent(snapshot.factoryId))
    const buffer = await response.arrayBuffer()
    await assertOperationAllowed()
    if (snapshot !== active) throw new Error('厂区已变化，请重新打开')
    return buffer
  } catch (error) {
    invalidateSession()
    throw error
  }
}

function saveBlob(blob, name) {
  const anchor = document.createElement('a')
  const url = URL.createObjectURL(blob)
  anchor.href = url
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Individual buttons do not await the handler; failures are caught here.
export async function downloadBuffer(buffer, name) {
  try {
    await assertOperationAllowed()
    saveBlob(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), name)
  } catch (error) { window.alert(error.message) }
}

export async function downloadZip(files, name) {
  const snapshot = await assertOperationAllowed()
  const zip = new JSZip()
  for (const file of files) zip.file(file.fileName, file.buffer)
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
  await assertOperationAllowed()
  if (snapshot !== active) throw new Error('厂区已变化，请重新打开')
  saveBlob(blob, name)
}
