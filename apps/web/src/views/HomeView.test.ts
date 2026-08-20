import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import HomeView from './HomeView.vue'

describe('HomeView', () => {
  it('renders platform title', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    const wrapper = mount(HomeView, {
      global: {
        stubs: ['a-card', 'a-skeleton', 'a-alert', 'a-descriptions', 'a-descriptions-item', 'a-badge'],
      },
    })
    expect(wrapper.text()).toContain('AI 工程化与交付平台')
  })
})

