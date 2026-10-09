import MarkdownIt from 'markdown-it'
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true, typographer: false })
markdown.renderer.rules.image = (tokens, index) => `<span class="yl-image-note">[图片未自动加载：${markdown.utils.escapeHtml(tokens[index]?.content || '图片')}]</span>`
const renderLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
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
export function renderMarkdown(value: string) { return markdown.render(value) }
