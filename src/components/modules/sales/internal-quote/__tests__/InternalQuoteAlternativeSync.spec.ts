import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { internalQuoteApi, type ApiInternalQuoteAlternativeFamily } from '@/api/internalQuote'
import type { InternalQuote } from '@/types/internalQuoteDesk'
import InternalQuoteAlternativeSync from '../InternalQuoteAlternativeSync.vue'

afterEach(() => vi.restoreAllMocks())
function setup(dirty = () => false) {
  const quote = { id: 'source', headerRevision: 4, versionLabel: 'B-V1' } as InternalQuote
  const family = { revision: 2, items: [{ quote_id: 'source', status: 'exported' }, { quote_id: 'target', status: 'exported', version_label: 'A-V1', scenario_name: '普通盒', archived: false }] } as ApiInternalQuoteAlternativeFamily
  vi.spyOn(internalQuoteApi, 'syncOptions').mockResolvedValue([{ key: 'engineering.hardware', label: '五金', department: '工程部' }])
  vi.spyOn(internalQuoteApi, 'get').mockResolvedValue({ id: 'target', header_revision: 7, final_release_status: 'issued' } as never)
  const preview = vi.spyOn(internalQuoteApi, 'previewAlternativeSync').mockResolvedValue({ preview_token: 'verified', targets: [{ quote_id: 'target', version_label: 'A-V1', create_version: true, changed: true, before: {}, after: {}, sections: [] }] } as never)
  const apply = vi.spyOn(internalQuoteApi, 'applyAlternativeSync').mockResolvedValue({ targets: [{ quote_id: 'new', version_label: 'A-V2', changed: true }] })
  const wrapper = mount(InternalQuoteAlternativeSync, { props: { quote, family, hasUnsavedChanges: dirty }, global: { stubs: { InternalQuoteComparison: true } } })
  return { wrapper, preview, apply }
}
async function select(wrapper: ReturnType<typeof setup>['wrapper']) {
  await wrapper.get('button').trigger('click'); await flushPromises()
  await wrapper.get('input[value="engineering.hardware"]').setValue(true)
  await wrapper.get('input[value="target"]').setValue(true)
  await wrapper.get('input[placeholder="例如：产品统一改用加长螺丝"]').setValue('统一螺丝')
  await wrapper.findAll('button').find(button => button.text() === '预览同步差异')!.trigger('click'); await flushPromises()
}
describe('bulk alternative synchronization', () => {
  it('previews first and sends the exact token, making an issued target a new version', async () => {
    const { wrapper, preview, apply } = setup()
    await select(wrapper)
    expect(apply).not.toHaveBeenCalled()
    expect(preview).toHaveBeenCalledWith('source', { revision: 4, family_revision: 2, blocks: ['engineering.hardware'], reason: '统一螺丝', targets: [{ quote_id: 'target', revision: 7, create_version: true }] })
    await wrapper.findAll('button').find(button => button.text() === '确认同步并保存')!.trigger('click'); await flushPromises()
    expect(apply.mock.calls[0]![1].preview_token).toBe('verified')
    expect(wrapper.text()).toContain('A-V2'); expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('invalidates preview if the selection changes and blocks unsaved source changes', async () => {
    let dirty = false
    const { wrapper, apply } = setup(() => dirty)
    await select(wrapper)
    dirty = true
    await wrapper.findAll('button').find(button => button.text() === '确认同步并保存')!.trigger('click'); await flushPromises()
    expect(apply).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('请先保存')
    dirty = false
    await select(wrapper)
    await wrapper.get('input[placeholder="例如：产品统一改用加长螺丝"]').setValue('重新选择原因')
    expect(wrapper.findAll('button').some(button => button.text() === '确认同步并保存')).toBe(false)
    wrapper.unmount()
  })
})
