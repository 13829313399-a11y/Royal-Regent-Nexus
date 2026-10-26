import type { HelpArticle, PageContext } from './types'

export function guidanceProblem(article: HelpArticle, page: PageContext | null) {
  if (article.status !== 'verified') return '说明对应的源码已变化或尚未核对，已停止定位。请等待说明更新。'
  if (!article.verification?.fingerprint || !article.verification.sources.length || article.verification.sources.some(source => !source.matches)) return '说明缺少有效的来源核对记录，已停止定位。请刷新说明。'
  if (!page || article.module_id !== page.module_id || !article.route_names.includes(page.route_name) ||
      (article.factory_ids?.length && !article.factory_ids.includes(page.factory_id || ''))) return '这份说明不适用于当前页面或厂区，请打开对应页面后重新选择。'
  return ''
}

export function verifyHelpTarget(previous: HelpArticle, current: HelpArticle, page: PageContext | null, id: string) {
  const problem = guidanceProblem(current, page)
  if (problem) throw new Error(problem)
  if (previous.id !== current.id || previous.verification?.fingerprint !== current.verification?.fingerprint) throw new Error('说明版本已更新，已停止旧引导。请阅读更新后的说明，再次开始。')
  if (current.anchor_id !== id && !current.steps.some(step => step.anchor_id === id)) throw new Error('这个目标已不在当前说明中，已停止引导。')
}
