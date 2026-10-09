import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import { documentTools, type Job } from '@/api/documentTools'
import ToolCenterView from '@/views/ToolCenterView.vue'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { factory: 'group' } }),
  useRouter: () => ({ replace: vi.fn() }),
}))

vi.mock('@/features/document-tools/PdfCanvas.vue', () => ({
  default: { template: '<div />' },
}))
vi.mock('@/lib/http', () => ({
  http: { defaults: { baseURL: '/api' } },
  getApiErrorMessage: (error: Error) => error.message,
}))

const makeJob = (id: string, status = 'queued') =>
  ({
    id,
    source_id: `source-${id}`,
    source_name: `${id}.docx`,
    operation: 'word_to_excel',
    execution_status: status,
    quality_status: 'not_checked',
    stage: 'queued',
    completed_units: 0,
    total_units: null,
    revision: 1,
    options: {},
    summary: {},
    created_at: '2026-09-09T00:00:00Z',
    cancel_requested: false,
    artifacts: [],
  }) satisfies Job
let records: Job[], wrapper: VueWrapper
const button = (label: string, selector = '') =>
  wrapper
    .find(selector || '.dt-recent')
    .findAll('button')
    .find((item) => item.text() === label)!

beforeAll(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.setAttribute('open', '')
      },
    },
    close: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.removeAttribute('open')
      },
    },
  })
})
afterAll(() => {
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
beforeEach(() => {
  setActivePinia(createPinia())
  records = [makeJob('first'), makeJob('second', 'succeeded')]
  vi.spyOn(documentTools, 'capabilities').mockResolvedValue({
    operations: [],
    worker: { online: true },
    limits: { max_file_bytes: 1000000, max_pages: 100 },
  })
  vi.spyOn(documentTools, 'jobs').mockImplementation(async (page = 1) => ({
    items: records.map((job) => ({ ...job })),
    total: records.length,
    page,
    page_size: 20,
  }))
  vi.spyOn(documentTools, 'cancel').mockImplementation(async (id) => {
    const job = records.find((item) => item.id === id)!
    job.execution_status = 'cancelled'
    job.cancel_requested = true
    return { ...job }
  })
  vi.spyOn(documentTools, 'delete').mockImplementation(async (id) => {
    records = records.filter((job) => job.id !== id)
  })
})
afterEach(() => {
  wrapper?.unmount()
  vi.restoreAllMocks()
})
async function render() {
  wrapper = mount(ToolCenterView, {
    global: {
      stubs: { PageHeader: true, ToolOptions: true, ResultReview: true },
    },
  })
  await flushPromises()
}

describe('document task actions in the workbench', () => {
  it('withdraws from recent tasks and preserves the record for retry', async () => {
    await render()
    await button('撤回任务').trigger('click')
    await flushPromises()
    expect(documentTools.cancel).toHaveBeenCalledWith('first')
    expect(wrapper.find('.dt-recent').text()).toContain('已撤回')
    expect(wrapper.findAll('.dt-recent-task')).toHaveLength(2)
    expect(wrapper.find('.dt-recent').text()).not.toContain('撤回任务')
  })

  it('requires confirmation, supports keeping the task, and removes only the selected record', async () => {
    await render()
    await button('删除任务').trigger('click')
    expect(wrapper.find('.dt-delete-dialog').attributes()).toHaveProperty(
      'open',
    )
    expect(documentTools.delete).not.toHaveBeenCalled()
    await button('保留任务', '.dt-delete-dialog').trigger('click')
    expect(documentTools.delete).not.toHaveBeenCalled()
    await button('删除任务').trigger('click')
    expect(wrapper.find('.dt-delete-dialog').text()).toContain('同时撤回')
    await button('确认删除', '.dt-delete-dialog').trigger('click')
    await flushPromises()
    expect(documentTools.delete).toHaveBeenCalledWith('first')
    expect(wrapper.find('.dt-recent').text()).not.toContain('first.docx')
    expect(wrapper.find('.dt-recent').text()).toContain('second.docx')
    expect(wrapper.find('.dt-delete-dialog').attributes()).not.toHaveProperty(
      'open',
    )
  })

  it('keeps the task and shows a deletion failure inside the confirmation dialog', async () => {
    vi.mocked(documentTools.delete).mockRejectedValue(
      new Error('连接中断，请重试'),
    )
    await render()
    await button('删除任务').trigger('click')
    await button('确认删除', '.dt-delete-dialog').trigger('click')
    await flushPromises()
    expect(wrapper.find('.dt-delete-dialog [role="alert"]').text()).toContain(
      '连接中断',
    )
    expect(wrapper.find('.dt-recent').text()).toContain('first.docx')
    expect(
      button('确认删除', '.dt-delete-dialog').attributes('disabled'),
    ).toBeUndefined()
  })

  it('clears the current task and returns to upload after deleting it', async () => {
    vi.spyOn(documentTools, 'job').mockImplementation(
      async (id) => records.find((job) => job.id === id)!,
    )
    vi.spyOn(documentTools, 'source').mockResolvedValue({
      id: 'source-first',
      original_name: 'first.docx',
      detected_type: 'docx',
      inspection_status: 'succeeded',
      inspection_job_id: 'inspection',
      manifest: {},
      artifacts: [],
    })
    await render()
    await wrapper.find('.dt-recent-task > button').trigger('click')
    await flushPromises()
    await button('删除任务', '.dt-document-bar').trigger('click')
    await button('确认删除', '.dt-delete-dialog').trigger('click')
    await flushPromises()
    expect(wrapper.find('.dt-empty').exists()).toBe(true)
    expect(wrapper.find('.dt-document-bar').text()).not.toContain('first.docx')
  })
})
