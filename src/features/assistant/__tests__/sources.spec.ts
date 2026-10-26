import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AssistantSources from '../AssistantSources.vue'
import type { EvidencePart, WebSource } from '../v2'
import { sourceSummary } from '../sourceSummary'

it('distinguishes current excerpts, failed reads and historical sources without claiming full-text verification', () => {
  const base: WebSource = {kind:'web',source_id:'fresh',run_id:'run',title:'官方文档',step_id:'search-0',provider:'dashscope_multimodal',provider_ref:'1',provider_request_id:null,url:'https://example.org/doc',site_name:'example.org',retrieved_at:'2026-10-23T00:00:00Z',published_at:null,evidence_level:'page_content',excerpt:'依赖由调用方提供。',locator:{kind:'extracted_lines',start:1,end:1},excerpt_truncated:true}
  const evidence: EvidencePart = {type:'evidence',schema_version:2,run_id:'run',revision:3,search:{requested_mode:'on',execution:'confirmed',evidence_level:'pages_fetched',search_count:1,reason_code:null},sources:[base,{...base,source_id:'failed',evidence_level:'search_result',read_status:'failed',read_error:'page_address_forbidden',excerpt:'仅检索摘要'},{...base,source_id:'old',origin:{run_id:'old-run',source_id:'old'}}],citations:[],activities:[]}
  const w = mount(AssistantSources,{props:{evidence}})
  expect(w.text()).toContain('2 个本轮公开来源 · 1 个已取得正文摘录')
  expect(w.text()).toContain('本轮公开来源 2 项：已取得正文摘录 1 项，读取失败 1 项，未尝试读取 0 项。沿用历史公开来源 1 项。')
  expect(w.text()).toContain('引用表示资料关联，不代表内容已核实')
  expect(w.text()).toContain('地址不符合公开网页读取范围')
  expect(w.text()).toContain('检索条目，尚未取得正文')
  expect(w.text()).toContain('提取文本第 1–1 行 · 已截取')
  expect(w.text()).toContain('不能据此声称已读全文')
  expect(w.find('a').attributes()).toMatchObject({target:'_blank',rel:'noopener noreferrer'})
  w.unmount()
  evidence.sources = [evidence.sources[2]!]
  evidence.search = {...evidence.search, attempted:true, execution:'unconfirmed', evidence_level:'none', search_count:1}
  expect(sourceSummary(evidence)).toContain('本轮公开来源 0 项：已取得正文摘录 0 项')
  expect(sourceSummary(evidence)).toContain('沿用历史公开来源 1 项')
})
