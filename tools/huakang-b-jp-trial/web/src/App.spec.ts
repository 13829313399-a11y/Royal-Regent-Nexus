import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import App from './App.vue'

it('mounts the existing JP workspace only for Huakang B and labels local numbering', () => {
  const wrapper = mount(App, { global: { stubs: { HuakangBJPIntake: { props: ['factoryId'], template: '<div data-test="jp">{{ factoryId }}</div>' } } } })
  expect(wrapper.get('[data-test="jp"]').text()).toBe('huakang-b')
  expect(wrapper.text()).toContain('本地试用版')
  expect(wrapper.text()).toContain('不连接线上系统')
  expect(wrapper.text()).toContain('每台电脑独立编号')
  wrapper.unmount()
})
