import { assistantApi } from './api'
import type { Draft, RunRelation } from './types'

export const relationLabels: Record<RunRelation['kind'], string> = {revise:'修订提问',regenerate:'重新生成',excerpt:'摘录追问',retry:'显式重试'}
export function releaseDraftImages(draft: Draft) { draft.attachments.forEach(image => URL.revokeObjectURL(image.url)) }

// This endpoint reauthorizes the frozen input. Never borrow the currently open
// page or current selection when editing a historical question.
export async function relatedDraft(runId: string, kind: RunRelation['kind'], excerpt = '') {
  const original = await assistantApi.question(runId)
  const payload = original.payload
  const draft: Draft = {text:kind === 'excerpt' ? `【原回答摘录】\n${excerpt}\n\n我的问题：` : payload.text,
    attachments:[], documents:[], relation:{parent_run_id:runId,kind},
    intent:kind === 'excerpt' ? 'chat' : payload.intent, thinking:payload.thinking, search:kind === 'excerpt' ? 'off' : payload.web_search,
    scope:{page:payload.page_context, title:payload.page_context ? '沿用原提问页面' : '自由交流', selection:kind !== 'excerpt' && payload.context_selection ? structuredClone(payload.context_selection) : null},
    publicQuery:kind === 'excerpt' ? '' : String(payload.context_selection?.filters.public_query || '')}
  if (draft.scope?.selection) delete draft.scope.selection.filters.public_query
  try {
    // Collect settled results so a single failed image cannot leak blob URLs.
    const images = await Promise.allSettled((kind === 'excerpt' ? [] : payload.attachment_ids).map(async id => ({id,name:'原提问图片',url:URL.createObjectURL(await assistantApi.attachment(id))})))
    draft.attachments = images.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])
    const failed = images.find(result => result.status === 'rejected')
    if (failed?.status === 'rejected') throw failed.reason
    draft.documents = await Promise.all((kind === 'excerpt' ? [] : payload.document_ids || []).map(id => assistantApi.document(id)))
    return {sessionId:original.session_id, draft}
  } catch (error) { releaseDraftImages(draft); throw error }
}
