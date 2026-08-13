import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getStatus: vi.fn(),
  translateDocument: vi.fn(),
  uploadArtifact: vi.fn(),
  getTaskCapabilities: vi.fn(),
  createTask: vi.fn(),
}))

vi.mock('@/api/tools', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/tools')>(),
  sharedToolsApi: {
    getDocumentTranslationStatus: mocks.getStatus,
    translateDocument: mocks.translateDocument,
  },
}))

vi.mock('@/api/aiArtifacts', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiArtifacts')>(),
  uploadAIArtifact: mocks.uploadArtifact,
}))

vi.mock('@/api/aiTasks', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiTasks')>(),
  getAITaskCapabilities: mocks.getTaskCapabilities,
  createArtifactTranslationTask: mocks.createTask,
}))

import DocumentTranslationTool from '@/components/tools/DocumentTranslationTool.vue'

describe('document translation Artifact orchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getStatus.mockResolvedValue({
      available: true,
      engine: 'offline',
      engineLabel: '服务器离线中英模型',
      directions: { zh_to_en: true, en_to_zh: true },
      artifactWorkflowsEnabled: true,
    })
    mocks.getTaskCapabilities.mockResolvedValue({
      contract_version: '1',
      available: true,
      worker_enabled: true,
    })
    mocks.uploadArtifact.mockResolvedValue({
      id: `aiart-${'a'.repeat(32)}`,
      sha256: 'b'.repeat(64),
    })
    mocks.createTask.mockResolvedValue({ id: `aitask-${'c'.repeat(32)}` })
  })

  it('queues a large macro-free local document and does not hold the request open', async () => {
    const wrapper = mount(DocumentTranslationTool, {
      props: { factoryId: 'huaxing' },
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    await flushPromises()
    const file = new File(
      [new Uint8Array(2 * 1024 * 1024)],
      '大文件.docx',
      { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
    )
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const submit = wrapper.findAll('button').find((button) => button.text().includes('翻译并下载'))
    if (!submit) throw new Error('translation submit button missing')
    await submit.trigger('click')
    await flushPromises()

    expect(mocks.uploadArtifact).toHaveBeenCalledWith(
      file,
      'huaxing',
      'CONFIDENTIAL_BUSINESS',
    )
    expect(mocks.createTask).toHaveBeenCalledWith({
      artifactId: `aiart-${'a'.repeat(32)}`,
      artifactSha256: 'b'.repeat(64),
      factoryId: 'huaxing',
      direction: 'zh_to_en',
      selectedSheetNames: undefined,
    })
    expect(mocks.translateDocument).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('刷新页面不会丢失进度')
    expect(wrapper.text()).toContain('查看任务进度与结果')
    wrapper.unmount()
  })
})
