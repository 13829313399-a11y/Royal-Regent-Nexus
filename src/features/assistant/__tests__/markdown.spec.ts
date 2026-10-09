import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'
describe('safe rich answers', () => {
  it('escapes HTML, blocks unsafe schemes and remote images', () => {
    const value = renderMarkdown('<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[x](javascript:alert(1))\n![private](https://evil.test/secret)')
    expect(value).not.toMatch(/<script|<img|href="javascript:/)
    expect(value).toContain('图片未自动加载')
  })
  it('renders tables and partial code fences with safe link attributes', () => {
    expect(renderMarkdown('[source](https://example.test)')).toContain('noopener noreferrer')
    expect(renderMarkdown('| A | B |\n|---|---|\n| 1 | 2 |')).toContain('yl-table')
    const value = renderMarkdown('```ts\nconst value = "<tag>"')
    expect(value).toContain('复制代码'); expect(value).toContain('&lt;tag&gt;')
  })
})
