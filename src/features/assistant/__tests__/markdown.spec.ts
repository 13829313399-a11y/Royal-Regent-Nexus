import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'
describe('safe rich answers', () => {
  it('binds record links only to server actions and leaves unknown protocols inert', () => {
    const source='[原单](customer-orders:order:SYN-O-A001) [外厂](customer-orders:order:SYN-O-B001) [应用](custom:launch)'
    const value=renderMarkdown(source,undefined,undefined,[{type:'open_record',label:'原单',route_name:'customer-order-center',params:{},query:{factory:'huakang-a',order:'SYN-O-A001'},resource:{module_id:'customer-orders',resource_type:'order',resource_id:'SYN-O-A001'}}])
    expect(value).toContain('<button type="button" class="yl-record-link" data-yl-action="0">原单</button>')
    expect(value).toContain('<span>外厂</span>');expect(value).toContain('<span>应用</span>')
    expect(value).not.toContain('href=')
    expect(renderMarkdown(source)).not.toContain('data-yl-action')
  })
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
