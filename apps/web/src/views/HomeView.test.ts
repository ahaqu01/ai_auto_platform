import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomeView from './HomeView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HomeView', () => {
  it('renders the visual project dashboard and truthful roadmap', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    const wrapper = mount(HomeView, {
      global: {
        stubs: ['a-skeleton', 'a-alert'],
      },
    })

    expect(wrapper.text()).toContain('项目工作台')
    expect(wrapper.text()).toContain('数据资产')
    expect(wrapper.text()).toContain('训练任务')
    expect(wrapper.text()).toContain('设备节点')
    expect(wrapper.findAll('[data-testid="pipeline-stage"]')).toHaveLength(6)
    expect(wrapper.text()).toContain('规划中')
  })

  it('renders live API identity after a successful health request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'ok',
        service: 'ai-auto-platform',
        version: '0.1.0',
      }),
    }))

    const wrapper = mount(HomeView, {
      global: {
        stubs: ['a-skeleton', 'a-alert'],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('ai-auto-platform')
    expect(wrapper.text()).toContain('0.1.0')
    expect(wrapper.text()).toContain('运行正常')
  })
})

