import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SchedulingImportDialog from '@/components/injection-scheduling/SchedulingImportDialog.vue'

describe('SchedulingImportDialog', () => {
  it('emits a read-only preview first and only enables confirmation for a confirmable batch', async () => {
    const wrapper = mount(SchedulingImportDialog, {
      global: { stubs: { teleport: true } },
      props: {
        open: true,
        busy: false,
        error: '',
        preview: null,
        factoryName: '华康B',
      },
    })
    const file = new File(['xlsx'], 'plan.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      configurable: true,
      value: [file],
    })
    await fileInput.trigger('change')

    const previewButton = wrapper.findAll('button').find((button) => button.text().includes('只读预览'))!
    expect(previewButton.attributes('disabled')).toBeUndefined()
    await previewButton.trigger('click')
    expect(wrapper.emitted('preview')?.[0]?.[0]).toBe(file)
    expect(wrapper.emitted('preview')?.[0]?.[1]).toMatch(/^\d{4}-\d{2}-\d{2}$/)

    await wrapper.setProps({
      preview: {
        batch_id: 'batch-1',
        factory_id: 'huakang-b',
        source_file_name: 'plan.xlsx',
        source_sha256: 'abc',
        business_date: '2026-07-28',
        parser_version: 'v1',
        preview_revision: 1,
        status: 'preview',
        summary: {
          template: 'huakang-b',
          machineCount: 96,
          moldCount: 331,
          orderCount: 434,
          taskCount: 493,
          currentTaskCount: 88,
          blockerCount: 0,
          warningCount: 17,
          canConfirm: true,
        },
        issues: [],
        created_at: '2026-07-28T10:00:00+08:00',
      },
    })
    expect(wrapper.text()).toContain('预览无阻断项')
    const confirmButton = wrapper.findAll('button').find((button) => button.text().includes('确认写入正式草案'))!
    expect(confirmButton.attributes('disabled')).toBeUndefined()
    await confirmButton.trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toContain('确认导入')
  })
})
