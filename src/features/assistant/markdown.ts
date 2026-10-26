import MarkdownIt from 'markdown-it'
import type { EvidencePart, UIAction } from './v2'
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true, typographer: false })
markdown.renderer.rules.image = (tokens, index) => `<span class="yl-image-note">[图片未自动加载：${markdown.utils.escapeHtml(tokens[index]?.content || '图片')}]</span>`
const renderLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index]!, href = String(token.attrGet('href') || '')
  const actions = (env?.actions || []) as UIAction[]
  const actionIndex = actions.findIndex(action => action.type === 'open_record' &&
    href === `${action.resource.module_id}:${action.resource.resource_type}:${action.resource.resource_id}`)
  if (actionIndex >= 0 || !/^(https?:\/\/|mailto:)/i.test(href)) {
    // A model reference can only reuse a server action. Never invoke a custom URI handler.
    token.tag = actionIndex >= 0 ? 'button' : 'span'
    token.attrs = actionIndex >= 0 ? [['type', 'button'], ['class', 'yl-record-link'], ['data-yl-action', String(actionIndex)]] : []
    const close = tokens.slice(index + 1).find(item => item.type === 'link_close' && item.level === token.level)
    if (close) close.tag = token.tag
    return self.renderToken(tokens, index, options)
  }
  tokens[index]?.attrSet('target', '_blank')
  tokens[index]?.attrSet('rel', 'noopener noreferrer nofollow')
  return renderLink ? renderLink(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
}
const fence = markdown.renderer.rules.fence
markdown.renderer.rules.fence = (tokens, index, options, env, self) => {
  const language = markdown.utils.escapeHtml(tokens[index]?.info.split(/\s+/)[0] || '文本')
  const code = fence ? fence(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
  return `<div class="yl-code"><div class="yl-code-head"><span>${language}</span><button type="button" data-yl-copy-code>复制代码</button></div>${code}</div>`
}
markdown.renderer.rules.table_open = () => '<div class="yl-table"><table>'
markdown.renderer.rules.table_close = () => '</table></div>'
const renderText = markdown.renderer.rules.text
markdown.renderer.rules.text = (tokens, index, options, env, self) => {
  const value = tokens[index]?.content || ''
  const evidence = env?.evidence as EvidencePart | undefined
  if (!evidence) return renderText ? renderText(tokens, index, options, env, self) : markdown.utils.escapeHtml(value)
  // Only Markdown text tokens are decorated; inline/fenced code is untouched.
  return value.split(/(\[ref_\d+\])/g).map(piece => {
    const binding = evidence.citations.find(c => c.part_id === env?.partId && c.marker === piece)
    if (!binding) return markdown.utils.escapeHtml(piece)
    const title = binding.source_ids.map(id => evidence.sources.find(s => s.source_id === id)?.title || '').join('、')
    return binding.resolution === 'resolved' && title
      ? `<button type="button" class="yl-source-marker" data-yl-source="${markdown.utils.escapeHtml(binding.binding_id)}" aria-label="查看来源：${markdown.utils.escapeHtml(title)}">${piece.replace(/\D/g, '')}</button>`
      : `<span class="yl-pending-source" title="${binding.resolution === 'pending' ? '来源尚在返回' : '来源不可核验'}">${markdown.utils.escapeHtml(piece)}</span>`
  }).join('')
}
export function renderMarkdown(value: string, evidence?: EvidencePart, partId?: string, actions?: UIAction[]) { return markdown.render(value, {evidence, partId, actions}) }
