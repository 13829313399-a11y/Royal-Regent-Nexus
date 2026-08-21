import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import UserAvatar from '@/components/common/UserAvatar.vue'

describe('UserAvatar image loading contract', () => {
  it('exposes lazy/eager loading and asynchronous decoding without changing fallback behavior', async () => {
    const wrapper = mount(UserAvatar, {
      props: { src: '/avatar.png', name: '成员甲', loading: 'eager' },
    })
    const image = wrapper.get('img')
    expect(image.attributes('loading')).toBe('eager')
    expect(image.attributes('decoding')).toBe('async')
    expect(image.attributes('alt')).toBe('成员甲的头像')

    await image.trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('成')
  })
})
