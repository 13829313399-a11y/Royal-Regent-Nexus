import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ReadTarget from '../FabricPurchaseReadTarget.vue'

const id = '0123456789abcdef0123456789abcdef'
let wrapper: VueWrapper | undefined
function open(value = id) { return wrapper = mount(ReadTarget, { props: { id: value }, attachTo: document.body }) }
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.useRealTimers(); vi.unstubAllGlobals() })

it('shows a short identifier and copies the complete original value only on request', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = open()
  expect(view.get('code').text()).toBe('01234567…cdef')
  expect(view.get('code').attributes('title')).toBe(id)
  expect(writeText).not.toHaveBeenCalled()
  view.get('button').element.focus()
  await view.get('button').trigger('click'); await flushPromises()
  expect(writeText).toHaveBeenCalledExactlyOnceWith(id)
  expect(view.get('[role="status"]').text()).toBe('完整编号已复制。')
  expect(document.activeElement).toBe(view.get('button').element)
  expect(view.find('input').exists()).toBe(false)
})

it('keeps short original identifiers intact', () => {
  expect(open('source-1').get('code').text()).toBe('source-1')
})

it.each(['missing', 'denied'])('provides selectable complete text when clipboard is %s', async kind => {
  vi.stubGlobal('navigator', kind === 'missing' ? {} : { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
  const view = open()
  await view.get('button').trigger('click'); await flushPromises()
  const field = view.get('input').element
  expect(field.value).toBe(id)
  expect(field.readOnly).toBe(true)
  expect(view.get('label').attributes('for')).toBe(field.id)
  expect(field.name).toBe('original_purchase_detail_id')
  field.focus()
  expect(field.selectionStart).toBe(0)
  expect(field.selectionEnd).toBe(id.length)
  expect(view.text()).toContain('无法自动复制')
  expect(view.text()).not.toContain('已复制')
})

it.each(['resolve', 'reject'] as const)('announces waiting, times out, and ignores a late %s', async result => {
  vi.useFakeTimers()
  let resolve!: () => void, reject!: (error: Error) => void
  const writeText = vi.fn(() => new Promise<void>((ok, no) => { resolve = ok; reject = no }))
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = open()
  await view.get('button').trigger('click')
  expect(view.get('[role="status"]').text()).toContain('正在复制完整编号')
  await view.get('button').trigger('click')
  expect(writeText).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10000)
  expect(view.get('[role="status"]').text()).toContain('复制等待超时')
  expect(view.get('input').element.value).toBe(id)
  expect(view.get('button').attributes('disabled')).toBeUndefined()
  if (result === 'resolve') resolve(); else reject(new Error('late denial'))
  await flushPromises()
  expect(view.get('[role="status"]').text()).toContain('复制等待超时')
  expect(vi.getTimerCount()).toBe(0)
})

it('clears pending feedback on target changes and cancels deadlines on unmount', async () => {
  vi.useFakeTimers()
  const completions: (() => void)[] = []
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn(() => new Promise<void>(ok => completions.push(ok))) } })
  const view = open()
  await view.get('button').trigger('click')
  await view.setProps({ id: 'next-source' })
  completions[0]!(); await flushPromises()
  expect(view.find('[role="status"]').exists()).toBe(false)
  expect(view.get('code').text()).toBe('next-source')
  await view.get('button').trigger('click')
  expect(vi.getTimerCount()).toBe(1)
  view.unmount(); wrapper = undefined
  completions[1]!(); await flushPromises()
  expect(vi.getTimerCount()).toBe(0)
})
