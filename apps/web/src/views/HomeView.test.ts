import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomeView from './HomeView.vue'

afterEach(() => { vi.unstubAllGlobals() })

describe('HomeView', () => {
  it('renders the M0/M1/M2 capability dashboard truthfully', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    const wrapper = mount(HomeView, { global: { stubs: { 'a-skeleton': true, 'a-alert': true, RouterLink: { template: '<a><slot /></a>' } } } })
    expect(wrapper.text()).toContain('让 AI 方案走到真实设备')
    expect(wrapper.text()).toContain('组织与项目')
    expect(wrapper.text()).toContain('数据资产')
    expect(wrapper.text()).toContain('模型与训练')
    expect(wrapper.text()).toContain('实机验证与交付')
    expect(wrapper.findAll('[data-testid="pipeline-stage"]')).toHaveLength(6)
    expect(wrapper.findAll('[data-testid="capability-card"]')).toHaveLength(6)
    expect(wrapper.text()).toContain('M0')
    expect(wrapper.text()).toContain('待实存 E2E')
    expect(wrapper.text()).toContain('规划中')
  })

  it('renders live API identity after a successful health request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', service: 'ai-auto-platform', version: '0.1.0' }) }))
    const wrapper = mount(HomeView, { global: { stubs: { 'a-skeleton': true, 'a-alert': true, RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(wrapper.text()).toContain('ai-auto-platform')
    expect(wrapper.text()).toContain('0.1.0')
    expect(wrapper.text()).toContain('运行正常')
  })
})