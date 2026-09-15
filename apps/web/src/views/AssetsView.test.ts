import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listOrganizations: vi.fn(), listProjects: vi.fn() }))
const start = vi.hoisted(() => vi.fn())
vi.mock('../platform', () => ({
  platformApi: api,
  ApiError: class extends Error {},
}))
vi.mock('../upload', () => ({
  UploadController: class {
    phase = 'IDLE'; uploadedBytes = 0; error = ''; artifact = null; session = null; progress = 0
    start = start; pause = vi.fn(); resume = vi.fn(); cancel = vi.fn()
  },
}))

import AssetsView from './AssetsView.vue'

beforeEach(() => {
  start.mockReset().mockResolvedValue(undefined)
  api.listOrganizations.mockReset().mockResolvedValue([{ id: 'o1', name: 'Alpha' }])
  api.listProjects.mockReset().mockResolvedValue([
    { id: 'p1', organization_id: 'o1', code: 'active', name: 'Active', status: 'ACTIVE', version: 1 },
    { id: 'p2', organization_id: 'o1', code: 'old', name: 'Archived', status: 'ARCHIVED', version: 1 },
  ])
})

it('shows only active projects and starts the selected file upload', async () => {
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  expect(wrapper.text()).toContain('Active')
  expect(wrapper.text()).not.toContain('Archived')
  const file = new File(['payload'], 'dataset.bin', { type: 'application/octet-stream' })
  Object.defineProperty(wrapper.get('[aria-label="选择上传文件"]').element, 'files', { value: [file] })
  await wrapper.get('[aria-label="选择上传文件"]').trigger('change')
  await wrapper.get('.action-primary').trigger('click')
  expect(start).toHaveBeenCalledWith('o1', 'p1', file)
})

it('rejects empty files before creating an upload session', async () => {
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  const file = new File([], 'empty.bin')
  Object.defineProperty(wrapper.get('[aria-label="选择上传文件"]').element, 'files', { value: [file] })
  await wrapper.get('[aria-label="选择上传文件"]').trigger('change')
  expect(wrapper.get('a-alert-stub').attributes('message')).toBe('不能上传空文件')
  expect(start).not.toHaveBeenCalled()
})