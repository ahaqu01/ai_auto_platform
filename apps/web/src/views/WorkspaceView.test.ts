import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listOrganizations: vi.fn(), listMembers: vi.fn(), listProjects: vi.fn(),
  createOrganization: vi.fn(), inviteMember: vi.fn(), updateMemberRole: vi.fn(),
  removeMember: vi.fn(), createProject: vi.fn(), updateProject: vi.fn(), setProjectArchived: vi.fn(),
}))
vi.mock('../platform', () => ({ platformApi: api, ApiError: class extends Error {} }))

import WorkspaceView from './WorkspaceView.vue'

beforeEach(() => {
  localStorage.clear()
  Object.values(api).forEach((mock) => mock.mockReset())
  api.listOrganizations.mockResolvedValue([{ id: 'o1', name: 'Alpha' }, { id: 'o2', name: 'Beta' }])
  api.listMembers.mockImplementation(async (id) => id === 'o1' ? [{ organization_id: id, user_id: 'u1', email: 'owner@example.com', display_name: 'Owner', role: 'OWNER' }] : [])
  api.listProjects.mockImplementation(async (id) => id === 'o1' ? [{ id: 'p1', organization_id: id, code: 'demo', name: 'Demo', description: null, status: 'ACTIVE', version: 1 }] : [])
})

describe('WorkspaceView', () => {
  it('loads organizations, members and projects then switches tenant scope', async () => {
    const wrapper = mount(WorkspaceView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Alpha')
    expect(wrapper.findAll('[data-testid="member-row"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="project-row"]')).toHaveLength(1)

    await wrapper.get('#organization-select').setValue('o2')
    await flushPromises()
    expect(api.listMembers).toHaveBeenLastCalledWith('o2')
    expect(api.listProjects).toHaveBeenLastCalledWith('o2')
    expect(localStorage.getItem('platform.organization')).toBe('o2')
  })

  it('creates a project in the selected organization', async () => {
    api.createProject.mockResolvedValue({ id: 'p2', organization_id: 'o1', code: 'new-project', name: 'New Project', description: null, status: 'ACTIVE', version: 1 })
    const wrapper = mount(WorkspaceView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
    await flushPromises()
    await wrapper.get('[aria-label="项目编码"]').setValue('new-project')
    await wrapper.get('[aria-label="项目名称"]').setValue('New Project')
    await wrapper.get('.project-create').trigger('submit')
    await flushPromises()
    expect(api.createProject).toHaveBeenCalledWith('o1', { code: 'new-project', name: 'New Project' })
    expect(wrapper.text()).toContain('New Project')
  })
})
