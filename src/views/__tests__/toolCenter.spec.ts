import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '@/stores/app'
import { pdfRenameApi } from '@/api/pdfRename'
import ToolCenterView from '@/views/ToolCenterView.vue'
import { navigationGroups } from '@/data/enterpriseMock'
import {
  documentTools,
  operationLabels,
  type Job,
  type Source,
} from '@/api/documentTools'

vi.mock('@/features/document-tools/PdfCanvas.vue', () => ({
  default: { template: '<div data-pdf-preview />', props: ['url'] },
}))
const routeState = reactive<{ query: Record<string, string> }>({ query: { factory: 'group' } })
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ replace: async ({ query }: { query: Record<string, string> }) => { routeState.query = query } }),
}))
const job: Job = {
  id: 'inspect-1',
  source_id: 'source-1',
  source_name: 'source.pdf',
  operation: 'inspect',
  execution_status: 'succeeded',
  quality_status: 'passed',
  stage: 'inspect',
  completed_units: 1,
  total_units: 1,
  revision: 1,
  options: {},
  summary: {},
  created_at: '2026-09-08T08:00:00Z',
  cancel_requested: false,
  artifacts: [],
}
const source: Source = {
  id: 'source-1',
  original_name: 'source.pdf',
  detected_type: 'pdf',
  inspection_status: 'succeeded',
  inspection_job_id: 'inspect-1',
  manifest: {
    pages: [
      {
        page_index: 0,
        display_page_number: 1,
        width_pt: 600,
        height_pt: 1200,
        rotation: 0,
      },
    ],
    supported_operations: ['pdf_to_word', 'pdf_to_excel', 'pdf_split'],
  },
  artifacts: [
    {
      id: 'original',
      role: 'source',
      format: 'pdf',
      filename: 'source.pdf',
      size: 12,
      revision: 1,
    },
  ],
}
const wrappers: VueWrapper[] = []
const render = () => {
  const wrapper = mount(ToolCenterView)
  wrappers.push(wrapper)
  return wrapper
}
async function upload(wrapper: VueWrapper, files: File[]) {
  Object.defineProperty(wrapper.get('input[type=file]').element, 'files', {
    configurable: true,
    value: files,
  })
  await wrapper.get('input[type=file]').trigger('change')
  await flushPromises()
}
beforeEach(() => {
  setActivePinia(createPinia())
  routeState.query = { factory: 'group' }
  vi.spyOn(pdfRenameApi, 'getPdfRenameRules').mockResolvedValue({ rules: [], limits: { max_files: 50, max_file_bytes: 20 * 1024 * 1024, max_batch_bytes: 200 * 1024 * 1024 } })
  vi.spyOn(documentTools, 'capabilities').mockResolvedValue({
    operations: Object.entries(operationLabels).map(([id, label]) => ({
      id: id as keyof typeof operationLabels,
      label,
      available: true,
    })),
    worker: { online: true },
    translation: { offline_available: true, online_available: true, online_model: 'test-model' },
    limits: { max_file_bytes: 20 * 1024 * 1024, max_pages: 500 },
  })
  vi.spyOn(documentTools, 'jobs').mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  })
  vi.spyOn(documentTools, 'source').mockResolvedValue(source)
  vi.spyOn(documentTools, 'job').mockResolvedValue(job)
  vi.spyOn(documentTools, 'upload').mockResolvedValue({
    source_id: source.id,
    inspection_job_id: job.id,
  })
  vi.spyOn(documentTools, 'issues').mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
  })
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('public tool center', () => {
  it.each(['group', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d'] as const)('does not expose or mount renaming in %s, even with a deep link', async (factory) => {
    useAppStore().setActiveFactory(factory)
    routeState.query = { factory, tool: 'pdf-batch-rename' }
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).not.toContain('批量改名')
    expect(pdfRenameApi.getPdfRenameRules).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-label="华兴 PDF 批量改名"]').exists()).toBe(false)
    expect(wrapper.get('.dt-desk').isVisible()).toBe(true)
  })

  it('adds Huaxing renaming, keeps conversion selections, and closes the rename workspace on factory change', async () => {
    useAppStore().setActiveFactory('huaxing')
    routeState.query = { factory: 'huaxing' }
    const wrapper = render()
    await flushPromises()
    await upload(wrapper, [new File(['document'], 'source.pdf')])
    await wrapper.get('.dt-tools button:last-child').trigger('click')
    await flushPromises()
    expect(routeState.query.tool).toBe('pdf-batch-rename')
    expect(pdfRenameApi.getPdfRenameRules).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    expect((wrapper.get('.dt-desk').element as HTMLElement).style.display).toBe('none')
    expect(wrapper.get('[aria-label="华兴 PDF 批量改名"]').isVisible()).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === '返回文档转换')!.trigger('click')
    await flushPromises()
    expect(routeState.query.tool).toBeUndefined()
    // Check v-show directly: jsdom can cache computed display across toggles.
    expect((wrapper.get('.dt-desk').element as HTMLElement).style.display).toBe('')
    expect(wrapper.get('.dt-document-bar').text()).toContain('source.pdf')
    await wrapper.get('.dt-tools button:last-child').trigger('click')
    await flushPromises()
    useAppStore().setActiveFactory('group')
    routeState.query = { factory: 'group', tool: 'pdf-batch-rename' }
    await flushPromises()
    expect(wrapper.find('[aria-label="华兴 PDF 批量改名"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('批量改名')
  })

  it('opens the restored Huaxing deep link directly', async () => {
    useAppStore().setActiveFactory('huaxing')
    routeState.query = { factory: 'huaxing', tool: 'pdf-batch-rename' }
    const wrapper = render()
    await flushPromises()
    expect(wrapper.get('[aria-label="华兴 PDF 批量改名"]').isVisible()).toBe(true)
  })
  it('uses the measured middle workspace width for comparison and leaves comparison when it narrows', async () => {
    const observers: Array<{
      callback: ResizeObserverCallback
      observed: Element[]
    }> = []
    vi.stubGlobal(
      'ResizeObserver',
      class {
        callback: ResizeObserverCallback
        observed: Element[] = []
        constructor(callback: ResizeObserverCallback) {
          this.callback = callback
          observers.push(this)
        }
        observe(element: Element) {
          this.observed.push(element)
        }
        unobserve() {}
        disconnect() {}
      },
    )
    vi.mocked(documentTools.job).mockResolvedValue({
      ...job,
      operation: 'pdf_to_excel',
    })
    vi.spyOn(documentTools, 'result').mockResolvedValue({
      schema_version: 1,
      source_type: 'pdf',
      pages: [],
      tables: [],
      blocks: [],
      issues: [],
      total_cells: 0,
      offset: 0,
      limit: 200,
    })
    const wrapper = render()
    await flushPromises()
    const resize = async (middleWidth: number) => {
      const target = wrapper.get('.dt-main').element
      const observer = observers.find((entry) =>
        entry.observed.includes(target),
      )!
      observer.callback(
        [
          { target: wrapper.element, contentRect: { width: 1400 } },
          { target, contentRect: { width: middleWidth } },
        ] as unknown as ResizeObserverEntry[],
        observer as unknown as ResizeObserver,
      )
      await flushPromises()
    }
    await resize(730)
    await upload(wrapper, [new File(['pdf'], 'source.pdf')])
    const comparisonButton = () =>
      wrapper.findAll('[role=tab]').find((button) => button.text() === '对照')
    expect(comparisonButton()).toBeUndefined()
    expect(wrapper.get('.dt-document-content').classes()).not.toContain(
      'comparing',
    )
    expect(
      wrapper
        .findAll('[role=tab]')
        .find((button) => button.text() === '结果')!
        .attributes('aria-selected'),
    ).toBe('true')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '专注模式')!
      .trigger('click')
    await resize(1100)
    await comparisonButton()!.trigger('click')
    expect(wrapper.get('.dt-document-content').classes()).toContain('comparing')
    await resize(900)
    expect(comparisonButton()).toBeUndefined()
    expect(wrapper.get('.dt-document-content').classes()).not.toContain(
      'comparing',
    )
    expect(
      wrapper
        .findAll('[role=tab]')
        .find((button) => button.text() === '结果')!
        .attributes('aria-selected'),
    ).toBe('true')
  })
  it.each(['docx', 'pdf'] as const)(
    'offers regional recognition only for a PDF source, even when %s has a PDF preview',
    async (kind) => {
      const completed = {
        ...job,
        operation: kind === 'pdf' ? 'pdf_to_excel' : 'word_to_excel',
      }
      vi.mocked(documentTools.job).mockResolvedValue(completed)
      vi.mocked(documentTools.source).mockResolvedValue({
        ...source,
        detected_type: kind,
        original_name: `source.${kind}`,
        artifacts: [
          { ...source.artifacts[0]!, role: 'preview', format: 'pdf' },
        ],
      })
      vi.spyOn(documentTools, 'result').mockResolvedValue({
        schema_version: 1,
        source_type: kind,
        pages: [],
        tables: [],
        blocks: [],
        issues: [],
        total_cells: 0,
        offset: 0,
        limit: 200,
      })
      const wrapper = render()
      await flushPromises()
      await upload(wrapper, [new File(['document'], `source.${kind}`)])
      await wrapper
        .findAll('.dt-view-tabs button')
        .find((button) => button.text() === '原文')!
        .trigger('click')
      expect(wrapper.find('[data-pdf-preview]').exists()).toBe(true)
      const recognition = wrapper
        .findAll('.dt-view-tabs button')
        .find((button) => button.text() === '框选重新识别')
      expect(Boolean(recognition)).toBe(kind === 'pdf')
    },
  )

  it('retains a selected source and its queue after a minute of idle capability refreshes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    vi.mocked(documentTools.capabilities).mockResolvedValue({
      operations: [],
      worker: { online: false },
      limits: { max_file_bytes: 1024, max_pages: 10 },
    })
    const wrapper = render()
    await flushPromises()
    await upload(wrapper, [new File(['pdf'], 'source.pdf')])
    await wrapper.findAll('.dt-tools button')[1]!.trigger('click')
    await vi.advanceTimersByTimeAsync(65000)
    await flushPromises()
    expect(documentTools.capabilities.mock.calls.length).toBeGreaterThanOrEqual(
      4,
    )
    expect(wrapper.find('.dt-document-bar').text()).toContain('source.pdf')
    expect(wrapper.find('.dt-file').text()).toContain('source.pdf')
    expect(
      wrapper.findAll('.dt-tools button')[1]!.attributes('aria-pressed'),
    ).toBe('true')
    expect(wrapper.find('.dt-drop').exists()).toBe(false)
  })
  it('separates initial status loading from an actual conversion submission', async () => {
    let finish!: (
      value: Awaited<ReturnType<typeof documentTools.capabilities>>,
    ) => void
    vi.mocked(documentTools.capabilities).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const wrapper = render()
    await flushPromises()
    expect(wrapper.get('.dt-generate button').text()).toContain('读取服务状态')
    expect(wrapper.get('.dt-generate button').text()).not.toContain('正在提交')
    finish({
      operations: [],
      worker: { online: true },
      limits: { max_file_bytes: 1024, max_pages: 1 },
    })
    await flushPromises()
    expect(wrapper.get('.dt-generate button').text()).toContain('生成文档')
  })

  it('refreshes offline capabilities at low frequency without resetting the selected tool or file queue', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    const offline = {
      operations: Object.entries(operationLabels).map(([id, label]) => ({
        id: id as keyof typeof operationLabels,
        label,
        available: true,
      })),
      worker: { online: false },
      limits: { max_file_bytes: 1024, max_pages: 1 },
    }
    vi.mocked(documentTools.capabilities)
      .mockResolvedValueOnce(offline)
      .mockResolvedValue({ ...offline, worker: { online: true } })
    const wrapper = render()
    await flushPromises()
    await wrapper.findAll('.dt-tools button')[2]!.trigger('click')
    await upload(wrapper, [new File(['x'], 'invalid.txt')])
    expect(wrapper.text()).toContain('后台处理服务暂未在线')
    await vi.advanceTimersByTimeAsync(15001)
    await flushPromises()
    expect(documentTools.capabilities).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('后台处理服务暂未在线')
    expect(
      wrapper.findAll('.dt-tools button')[2]!.attributes('aria-pressed'),
    ).toBe('true')
    expect(wrapper.findAll('.dt-file')).toHaveLength(1)
    expect(wrapper.find('.dt-file').text()).toContain('invalid.txt')
  })
  it('places the shared toolbar between main and cross-factory navigation', () => {
    const labels = navigationGroups.map((group) => group.label)
    expect(labels.indexOf('TOOLS')).toBe(labels.indexOf('MAIN') + 1)
    expect(labels.indexOf('TOOLS')).toBeLessThan(
      labels.indexOf('CROSS FACTORY'),
    )
    expect(
      navigationGroups.find((group) => group.label === 'TOOLS')?.items,
    ).toContainEqual(
      expect.objectContaining({
        label: '公共工具栏',
        to: '/tools',
        preserveFactory: true,
      }),
    )
  })

  it('keeps the authenticated route and exposes ten real tools without invented history', async () => {
    const routerSource = readFileSync(
      join(process.cwd(), 'src/router/index.ts'),
      'utf8',
    )
    expect(routerSource).toMatch(/path: '\/tools',[\s\S]*?requiresAuth: true/)
    expect(routerSource).toContain(
      "component: () => import('@/views/ToolCenterView.vue')",
    )

    const wrapper = render()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('公共工具栏')
    expect(wrapper.text()).toContain('文档翻译、转换与精确分页')
    expect(
      wrapper.find('input[type="file"]').attributes('multiple'),
    ).toBeDefined()
    expect(wrapper.findAll('.dt-tools button')).toHaveLength(10)
    expect(wrapper.text()).toContain('还没有任务')
    expect(wrapper.findAll('.dt-task')).toHaveLength(0)
  })

  it('preserves Excel translation preferences across upload and sends only translation options', async () => {
    vi.mocked(documentTools.source).mockResolvedValue({ ...source, detected_type: 'xlsx', original_name: 'book.xlsx', manifest: { sheets: ['Sheet1'] } })
    const create = vi.spyOn(documentTools, 'create').mockResolvedValue({ job_id: 'translation-1' })
    const wrapper = render()
    await flushPromises()
    await wrapper.findAll('.dt-tools button').find(button => button.text() === operationLabels.excel_translate)!.trigger('click')
    await wrapper.get('.dt-translation-intro [aria-label="翻译方向"]').setValue('en_to_zh')
    await wrapper.get('.dt-translation-intro [aria-label="翻译方式"]').setValue('online')
    await upload(wrapper, [new File(['xlsx'], 'book.xlsx')])
    expect(wrapper.get('.dt-translation-intro [aria-label="翻译方向"]').element).toHaveProperty('value', 'en_to_zh')
    expect(wrapper.get('.dt-translation-intro [aria-label="翻译方式"]').element).toHaveProperty('value', 'online')
    await wrapper.get('.dt-generate button').trigger('click')
    await flushPromises()
    expect(create).toHaveBeenCalledWith(source.id, 'excel_translate', { translation_direction: 'en_to_zh', translation_engine: 'online', sheets: ['Sheet1'] }, expect.any(String))
  })

  it('offers the image translator with the actual factory context', async () => {
    useAppStore().setActiveFactory('group')
    const wrapper = render()
    await flushPromises()
    expect(wrapper.get('a.dt-image-translation-link').attributes('href'))
      .toBe('/image-translation/?factory=group')
    useAppStore().setActiveFactory('huaxing')
    await flushPromises()
    expect(wrapper.get('a.dt-image-translation-link').attributes('href'))
      .toBe('/image-translation/?factory=huaxing')
    routeState.query = { factory: 'huaxing' }
    await flushPromises()
    expect(wrapper.findAll('.dt-tools button')).toHaveLength(11)
  })

  it('keeps a failed file independent while uploading the next file', async () => {
    vi.mocked(documentTools.upload)
      .mockRejectedValueOnce(new Error('文件损坏'))
      .mockResolvedValueOnce({
        source_id: source.id,
        inspection_job_id: job.id,
      })
    const wrapper = render()
    await flushPromises()
    await upload(wrapper, [
      new File(['bad'], 'broken.pdf'),
      new File(['pdf'], 'source.pdf'),
    ])
    expect(documentTools.upload).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.dt-file')).toHaveLength(2)
    expect(wrapper.findAll('.dt-file')[0]!.text()).toContain('文件损坏')
    expect(wrapper.text()).toContain('source.pdf')
    expect(wrapper.find('[data-pdf-preview]').exists()).toBe(true)
  })

  it('does not silently switch a mismatched tool and blocks generation', async () => {
    const wrapper = render()
    await flushPromises()
    await wrapper.findAll('.dt-tools button')[0]!.trigger('click')
    await upload(wrapper, [new File(['pdf'], 'source.pdf')])
    expect(
      wrapper.findAll('.dt-tools button')[0]!.attributes('aria-pressed'),
    ).toBe('true')
    expect(wrapper.text()).toContain('此文件不适用 Word → PDF')
    expect(
      wrapper.get('.dt-generate button').attributes('disabled'),
    ).toBeDefined()
  })

  it('creates an asynchronous conversion with operation-specific options', async () => {
    vi.spyOn(documentTools, 'create').mockResolvedValue({ job_id: 'convert-1' })
    const wrapper = render()
    await flushPromises()
    await upload(wrapper, [new File(['pdf'], 'source.pdf')])
    await wrapper.get('.dt-generate button').trigger('click')
    await flushPromises()
    expect(documentTools.create).toHaveBeenCalledWith(
      'source-1',
      'pdf_to_excel',
      expect.objectContaining({
        preserve_merges: true,
        numeric_locale: 'preserve_ambiguous',
      }),
      expect.any(String),
    )
    expect(wrapper.text()).toContain('任务已在后台开始')
  })

  it('reports unavailable workers without fake completion progress', async () => {
    vi.mocked(documentTools.capabilities).mockResolvedValue({
      operations: [],
      worker: { online: false },
      limits: { max_file_bytes: 1024, max_pages: 10 },
    })
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('后台处理服务暂未在线')
    expect(wrapper.find('progress').exists()).toBe(false)
  })
})
