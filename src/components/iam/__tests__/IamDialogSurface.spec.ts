import { defineComponent, ref } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import IamDialogSurface from '../workspace/IamDialogSurface.vue'
enableAutoUnmount(afterEach)
it('keeps unsaved input mounted when the administrator continues editing', async () => {
  const parent = defineComponent({
    components: { IamDialogSurface },
    setup() {
      return { open: ref(true), dirty: ref(true), value: ref('未保存资料') }
    },
    template:
      '<IamDialogSurface v-model:open="open" title="人员办理" :dirty="dirty" @discarded="dirty = false"><label>测试字段<input v-model="value" /></label></IamDialogSurface>',
  })
  const wrapper = mount(parent, {
    attachTo: document.body,
    global: { stubs: { teleport: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  await wrapper.get('input').setValue('保留这份修改')
  await wrapper.get('button[aria-label="关闭人员办理"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alertdialog"]').exists()).toBe(true)
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe('保留这份修改')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '继续编辑')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe('保留这份修改')
  await wrapper.get('button[aria-label="关闭人员办理"]').trigger('click')
  await flushPromises()
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '放弃未保存内容')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})
it('does not close or claim cancellation during an in-flight operation', async () => {
  const wrapper = mount(IamDialogSurface, {
    props: { open: true, title: '提交办理', busy: true },
    global: { stubs: { teleport: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('关闭页面不会取消服务器办理')
  expect(wrapper.emitted('update:open')).toBeUndefined()
})
