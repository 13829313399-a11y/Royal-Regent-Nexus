import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResultReview from './ResultReview.vue'
import { documentTools, type Job, type Result } from '@/api/documentTools'
const job = { id: 'job-1', revision: 2 } as Job
const result: Result = {
  schema_version: 1,
  source_type: 'pdf',
  pages: [],
  blocks: [],
  issues: [],
  total_cells: 1,
  offset: 0,
  limit: 200,
  tables: [
    {
      id: 'table-1',
      title: '报价',
      row_count: 1,
      column_count: 1,
      source: {},
      cells: [
        {
          id: 'cell-1',
          row: 0,
          column: 0,
          rowspan: 1,
          colspan: 1,
          raw_text: '001234',
          display_text: '001234',
          resolution: 'ambiguous',
          source: {
            page_index: 0,
            bbox_pt: [1, 2, 30, 40],
            anchor_precision: 'region',
          },
        },
      ],
    },
  ],
}
afterEach(() => vi.restoreAllMocks())
describe('document result review', () => {
  it('marks a manually confirmed revision as confirmed rather than ambiguous', async () => {
    const table = result.tables[0]!
    vi.spyOn(documentTools, 'result').mockResolvedValue({ ...result, tables: [{ ...table, cells: [{ ...table.cells[0]!, display_text: '001235', resolution: 'manually_confirmed' }] }] })
    const wrapper = mount(ResultReview, { props: { job } })
    await flushPromises()
    expect(wrapper.find('tbody tr').classes()).not.toContain('ambiguous')
    expect(wrapper.text()).toContain('已人工确认')
    expect(wrapper.text()).not.toContain('需要核对原文')
    expect((wrapper.get('td input').element as HTMLInputElement).value).toBe('001235')
    wrapper.unmount()
  })
  it('requests the server window for a selected target outside the loaded cells', async () => {
    const fetchResult = vi.spyOn(documentTools, 'result').mockResolvedValue(result)
    const wrapper = mount(ResultReview, { props: { job } }); await flushPromises()
    const nextCell = { ...result.tables[0]!.cells[0]!, id: 'far-cell', row: 800 }
    fetchResult.mockResolvedValue({ ...result, offset: 800, total_cells: 1000, tables: [{ ...result.tables[0]!, cells: [nextCell] }] })
    await wrapper.setProps({ selectedTarget: 'far-cell' }); await flushPromises()
    expect(fetchResult).toHaveBeenLastCalledWith('job-1', undefined, 0, 'far-cell')
    expect(wrapper.find('tr.selected').text()).toContain('801')
    wrapper.unmount()
  })
  it('preserves identifiers and records manual corrections against an immutable base revision', async () => {
    vi.spyOn(documentTools, 'result').mockResolvedValue(result)
    vi.spyOn(documentTools, 'revise').mockResolvedValue({ job_id: 'revised-1' })
    const wrapper = mount(ResultReview, { props: { job } })
    await flushPromises()
    expect((wrapper.get('td input').element as HTMLInputElement).value).toBe(
      '001234',
    )
    await wrapper.get('td button').trigger('click')
    expect(wrapper.emitted('locate')![0]).toEqual([
      result.tables[0]!.cells[0]!.source,
      'cell-1',
    ])
    await wrapper.get('td input').setValue('001235')
    await wrapper.get('.dt-review-save button').trigger('click')
    await flushPromises()
    expect(documentTools.revise).toHaveBeenCalledWith('job-1', {
      base_revision: 2,
      corrections: [
        {
          target_id: 'cell-1',
          new_value: '001235',
          reason: '人工对照原文修正',
        },
      ],
    })
    expect(wrapper.emitted('revised')![0]).toEqual(['revised-1'])
    wrapper.unmount()
  })
})
