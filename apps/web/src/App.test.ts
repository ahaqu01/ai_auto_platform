import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('renders the management shell and primary navigation', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: true,
        },
      },
    })

    const navigation = wrapper.get('[aria-label="平台主导航"]')
    expect(wrapper.text()).toContain('AI 工程化平台')
    expect(navigation.text()).toContain('工作台')
    expect(navigation.text()).toContain('组织与项目')
    expect(navigation.text()).toContain('数据资产')
    expect(navigation.text()).toContain('智能标注')
    expect(navigation.text()).toContain('训练中心')
    expect(navigation.text()).toContain('模型仓库')
    expect(navigation.text()).toContain('设备与部署')
    expect(navigation.text()).toContain('系统管理')
    expect(wrapper.text()).toContain('内部演示环境')
  })
})
