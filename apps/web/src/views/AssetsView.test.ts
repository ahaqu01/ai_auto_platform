import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listOrganizations: vi.fn(), listProjects: vi.fn(), listArtifacts: vi.fn(), getArtifact: vi.fn(), createArtifactDownloadUrl: vi.fn() }))
const start = vi.hoisted(() => vi.fn())
const uploadState = vi.hoisted(() => ({ phase: 'IDLE' }))
vi.mock('../platform', () => ({
  platformApi: api,
  ApiError: class extends Error {},
}))
vi.mock('../upload', () => ({
  UploadController: class {
    phase = uploadState.phase; uploadedBytes = 0; error = ''; artifact = null; session = null; progress = 0
    start = start; pause = vi.fn(); resume = vi.fn(); cancel = vi.fn()
  },
}))

import AssetsView from './AssetsView.vue'

beforeEach(() => {
  localStorage.clear()
  uploadState.phase = 'IDLE'
  start.mockReset().mockResolvedValue(undefined)
  api.listOrganizations.mockReset().mockResolvedValue([{ id: 'o1', name: 'Alpha' }])
  api.listArtifacts.mockReset().mockResolvedValue({ items: [], next_cursor: null })
  api.getArtifact.mockReset()
  api.createArtifactDownloadUrl.mockReset()
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

it('renders asset status, loads details, and gates download by availability', async () => {
  const available = {
    id: 'a1', display_name: 'verified.bin', size_bytes: 1024,
    status: 'AVAILABLE', integrity_status: 'VERIFIED', security_scan_status: 'NOT_REQUIRED',
    verified_sha256: 'a'.repeat(64), expected_sha256: 'a'.repeat(64),
  }
  const quarantined = {
    ...available, id: 'a2', display_name: 'blocked.bin', status: 'QUARANTINED',
    integrity_status: 'MISMATCH',
  }
  api.listArtifacts.mockResolvedValue({ items: [available, quarantined], next_cursor: null })
  api.getArtifact.mockResolvedValue(available)
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  const rows = wrapper.findAll('[data-testid="artifact-row"]')
  expect(rows).toHaveLength(2)
  expect(rows[0].text()).toContain('verified.bin')
  expect(rows[0].text()).toContain('VERIFIED')
  expect(rows[0].findAll('button')[1].attributes('disabled')).toBeUndefined()
  expect(rows[1].findAll('button')[1].attributes('disabled')).toBeDefined()
  await rows[0].findAll('button')[0].trigger('click')
  await flushPromises()
  expect(api.getArtifact).toHaveBeenCalledWith('o1', 'p1', 'a1')
  expect(wrapper.get('[data-testid="artifact-detail"]').text()).toContain('a'.repeat(64))
  expect(wrapper.get('[data-testid="artifact-detail"]').text()).toContain('未执行恶意文件扫描')
})

it('loads assets beyond 100 with details and retries a failed next page', async () => {
  const items = Array.from({ length: 100 }, (_, i) => ({ id: `a${i}`, display_name: `asset-${i}`, size_bytes: 1, status: 'AVAILABLE', integrity_status: 'VERIFIED' }))
  const later = { ...items[0], id: 'a100', display_name: 'asset-100', security_scan_status: 'NOT_REQUIRED' }
  api.listArtifacts.mockResolvedValueOnce({ items, next_cursor: 'page-two' })
    .mockRejectedValueOnce(new Error('temporary page error'))
    .mockResolvedValueOnce({ items: [items[99], later], next_cursor: null })
  api.getArtifact.mockResolvedValue(later)
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  expect(wrapper.findAll('[data-testid="artifact-row"]')).toHaveLength(100)
  await wrapper.get('[data-testid="load-more-assets"]').trigger('click')
  await flushPromises()
  expect(wrapper.findAll('[data-testid="artifact-row"]')).toHaveLength(100)
  await wrapper.get('[data-testid="load-more-assets"]').trigger('click')
  await flushPromises()
  expect(api.listArtifacts).toHaveBeenLastCalledWith('o1', 'p1', 'page-two')
  expect(wrapper.findAll('[data-testid="artifact-row"]')).toHaveLength(101)
  expect(wrapper.find('[data-testid="load-more-assets"]').exists()).toBe(false)
  const row = wrapper.findAll('[data-testid="artifact-row"]')[100]
  expect(row.findAll('button')[1].attributes('disabled')).toBeUndefined()
  await row.findAll('button')[0].trigger('click')
  await flushPromises()
  expect(api.getArtifact).toHaveBeenLastCalledWith('o1', 'p1', 'a100')
})

it.each(['HASHING', 'UPLOADING', 'PAUSED', 'COMPLETING'])('locks scope and file during %s', async (phase) => {
  uploadState.phase = phase
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  expect(wrapper.findAll('select').every((select) => select.attributes('disabled') !== undefined)).toBe(true)
  expect(wrapper.get('[aria-label="选择上传文件"]').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('完整性校验不等于恶意文件扫描')
})

it('discards stale pages after changing project', async () => {
  api.listProjects.mockResolvedValue([
    { id: 'p1', name: 'First', status: 'ACTIVE' }, { id: 'p2', name: 'Second', status: 'ACTIVE' },
  ])
  let resolveOld!: (value: unknown) => void
  api.listArtifacts.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
    .mockResolvedValueOnce({ items: [{ id: 'new', display_name: 'new-project', size_bytes: 1, status: 'AVAILABLE' }], next_cursor: null })
  const wrapper = mount(AssetsView, { global: { stubs: ['a-alert', 'a-skeleton'] } })
  await flushPromises()
  await wrapper.findAll('select')[1].setValue('p2')
  await flushPromises()
  resolveOld({ items: [{ id: 'old', display_name: 'old-project', size_bytes: 1, status: 'AVAILABLE' }], next_cursor: 'old-cursor' })
  await flushPromises()
  expect(wrapper.text()).toContain('new-project')
  expect(wrapper.text()).not.toContain('old-project')
  expect(wrapper.find('[data-testid="load-more-assets"]').exists()).toBe(false)
})
