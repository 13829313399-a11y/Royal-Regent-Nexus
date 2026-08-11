import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SchedulingFeedbackToast from '../components/SchedulingFeedbackToast.vue'
import { createAsyncFeedback, shouldShowFeedbackToast } from '../presentation/asyncFeedback'

describe('injection scheduling typed async feedback', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('uses an alert for explicit errors and keeps the error visible until dismissed', async () => {
    vi.useFakeTimers()
    const feedback = createAsyncFeedback('save', 'failed', 'error', '保存失败：模拟网络错误')
    const wrapper = mount(SchedulingFeedbackToast, {
      attachTo: document.body,
      props: { feedback },
      global: { stubs: { Teleport: true } },
    })

    const toast = document.body.querySelector('.scheduling-feedback-toast')
    expect(toast?.getAttribute('role')).toBe('alert')
    expect(toast?.getAttribute('aria-live')).not.toBe('polite')
    expect(toast?.textContent).toContain('保存失败：模拟网络错误')

    await vi.advanceTimersByTimeAsync(5_000)
    expect(document.body.querySelector('.scheduling-feedback-toast')).not.toBeNull()
    await wrapper.get('button[aria-label="关闭提示"]').trigger('click')
    expect(document.body.querySelector('.scheduling-feedback-toast')).toBeNull()
    wrapper.unmount()
  })

  it('uses a polite live region for explicit success and dismisses it automatically', async () => {
    vi.useFakeTimers()
    const feedback = createAsyncFeedback('refresh', 'succeeded', 'success', '排产数据已刷新')
    const wrapper = mount(SchedulingFeedbackToast, {
      attachTo: document.body,
      props: { feedback },
      global: { stubs: { Teleport: true } },
    })

    const toast = document.body.querySelector('.scheduling-feedback-toast')
    expect(toast?.getAttribute('role')).toBe('status')
    expect(toast?.getAttribute('aria-live')).toBe('polite')
    expect(toast?.textContent).toContain('排产数据已刷新')

    await vi.advanceTimersByTimeAsync(3_601)
    expect(document.body.querySelector('.scheduling-feedback-toast')).toBeNull()
    wrapper.unmount()
  })

  it('keeps dialog and persistent-sync feedback out of the transient toast layer', () => {
    expect(shouldShowFeedbackToast(createAsyncFeedback('save', 'failed', 'error', '保存失败'), false)).toBe(true)
    expect(shouldShowFeedbackToast(createAsyncFeedback('save', 'failed', 'error', '版本冲突'), true)).toBe(false)
    expect(shouldShowFeedbackToast(createAsyncFeedback('publish', 'failed', 'error', '发布失败'), false)).toBe(false)
    expect(shouldShowFeedbackToast(createAsyncFeedback('auto-generate', 'failed', 'error', '生成失败'), false)).toBe(false)
    expect(shouldShowFeedbackToast(createAsyncFeedback('refresh', 'failed', 'warning', '数据已过期'), false)).toBe(false)
    expect(shouldShowFeedbackToast(createAsyncFeedback('poll', 'succeeded', 'info', '没有新事件'), false)).toBe(false)
    expect(shouldShowFeedbackToast(createAsyncFeedback('publish', 'succeeded', 'success', '计划已发布'), false)).toBe(true)
  })
})
