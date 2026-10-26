import type { EvidencePart } from './v2'

// Display execution facts independently of the model's prose. An old page
// excerpt never counts as a successful read in the current run.
export function sourceSummary(evidence?: EvidencePart | null): string {
  if (!evidence) return ''
  const web = evidence.sources.filter(source => source.kind === 'web')
  if (!web.length && !evidence.search.attempted) return ''
  const current = web.filter(source => !source.origin)
  const read = current.filter(source => source.evidence_level === 'page_content').length
  const failed = current.filter(source => source.evidence_level !== 'page_content' && source.read_status === 'failed').length
  const untouched = current.length - read - failed
  return `本轮公开来源 ${current.length} 项：已取得正文摘录 ${read} 项，读取失败 ${failed} 项，未尝试读取 ${untouched} 项。沿用历史公开来源 ${web.length - current.length} 项。引用表示资料关联，不代表内容已核实。`
}
