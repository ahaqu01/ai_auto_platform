import { beforeEach, describe, expect, it, vi } from 'vitest'

const { authenticatedFetch } = vi.hoisted(() => ({ authenticatedFetch: vi.fn() }))
vi.mock('./auth', () => ({ authenticatedFetch }))

import { ApiError, platformApi, requestId } from './platform'

beforeEach(() => {
  authenticatedFetch.mockReset()
  vi.stubGlobal('crypto', { randomUUID: () => 'request-id' })
})

describe('requestId', () => {
  it('creates a UUID when randomUUID is unavailable on a trusted-LAN HTTP origin', () => {
    vi.stubGlobal('crypto', {})
    expect(requestId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
})

describe('platformApi', () => {
  it('encodes asset cursors and preserves the caller completion key', async () => {
    authenticatedFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
    await platformApi.listArtifacts('o1', 'p1', 'cursor+/=')
    expect(authenticatedFetch.mock.calls[0][0]).toContain('limit=100&cursor=cursor%2B%2F%3D')
    await platformApi.completeUpload('o1', 'p1', 'u1', [{ part_number: 1, etag: 'etag' }], 'stable-completion-key')
    expect(authenticatedFetch.mock.calls[1][1].headers['Idempotency-Key']).toBe('stable-completion-key')
  })
  it('sends idempotency and optimistic-lock headers', async () => {
    authenticatedFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 'p1', version: 2 }) })
    await platformApi.createProject('o1', { code: 'demo', name: 'Demo' })
    expect(authenticatedFetch.mock.calls[0][1].headers['Idempotency-Key']).toBe('request-id')

    await platformApi.updateProject('o1', { id: 'p1', organization_id: 'o1', code: 'demo', name: 'Demo', description: null, status: 'ACTIVE', version: 2 }, 'Renamed')
    expect(authenticatedFetch.mock.calls[1][1].headers['If-Match']).toBe('"2"')
  })

  it('preserves the API problem code and detail', async () => {
    authenticatedFetch.mockResolvedValue({ ok: false, status: 412, json: async () => ({ code: 'VERSION_MISMATCH', detail: '请刷新' }) })
    await expect(platformApi.listOrganizations()).rejects.toEqual(new ApiError(412, 'VERSION_MISMATCH', '请刷新'))
  })
})
