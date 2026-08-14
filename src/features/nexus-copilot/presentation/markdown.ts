import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  typographer: false,
})

markdown.renderer.rules.table_open = () => '<div class="ai-rich-table-scroll"><table><caption>AI 回答数据表</caption>'
markdown.renderer.rules.table_close = () => '</table></div>'

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 's', 'h1', 'h2', 'h3', 'h4',
  'ul', 'ol', 'li', 'blockquote', 'hr', 'code', 'pre',
  'div', 'table', 'caption', 'thead', 'tbody', 'tr', 'th', 'td', 'a',
]

function hardenLinks(html: string) {
  const template = document.createElement('template')
  template.innerHTML = html
  for (const anchor of template.content.querySelectorAll<HTMLAnchorElement>('a')) {
    const href = anchor.getAttribute('href')?.trim() ?? ''
    let safe = false
    try {
      const parsed = new URL(href)
      safe = parsed.protocol === 'https:' || parsed.protocol === 'http:'
    } catch {
      safe = false
    }
    if (!safe) {
      anchor.removeAttribute('href')
      anchor.removeAttribute('target')
      anchor.removeAttribute('rel')
      continue
    }
    anchor.setAttribute('target', '_blank')
    anchor.setAttribute('rel', 'noopener noreferrer')
  }
  return template.innerHTML
}

export function renderSafeMarkdown(source: string) {
  const bounded = source.slice(0, 8_000)
  const rendered = markdown.render(bounded)
  const sanitized = DOMPurify.sanitize(rendered, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'class'],
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'img', 'svg', 'math'],
    FORBID_ATTR: ['style'],
    ALLOW_DATA_ATTR: false,
  })
  return hardenLinks(sanitized)
}
