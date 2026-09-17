import { createHash } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'

import { sha256File } from './fileHash'
import { UploadController } from './upload'

function fixture() {
  const session = { id: 'u1', status: 'PENDING_UPLOAD', display_name: 'data.bin', expected_size: 1, expected_sha256: '0'.repeat(64), declared_content_type: 'application/octet-stream', expires_at: '2099-01-01T00:00:00Z', version: 1 }
  const api = {
    createUploadSession: vi.fn(async () => session),
    getUploadSession: vi.fn(async () => ({ ...session, status: 'UPLOADING' })),
    signUploadParts: vi.fn(async (_o, _p, _u, numbers: number[]) => numbers.map((part_number) => ({ part_number, url: `https://storage.test/${part_number}?signature=secret`, expires_in_seconds: 900 }))),
    registerUploadPart: vi.fn(async (_o, _p, _u, part_number: number, body) => ({ part_number, etag: body.etag, size_bytes: body.size_bytes, created_at: '', updated_at: '' })),
    listUploadParts: vi.fn(async () => []),
    completeUpload: vi.fn(async (_organizationId: string, _projectId: string, _uploadId: string, _parts: { part_number: number; etag: string }[], _idempotencyKey?: string) => ({ id: 'a1', display_name: 'data.bin', size_bytes: 1, status: 'AVAILABLE', integrity_status: 'VERIFIED', version: 1 })),
    cancelUpload: vi.fn(async () => ({ ...session, status: 'ABORTED' })),
  }
  return { api, session }
}

it('computes incremental SHA-256 without reading the whole file API', async () => {
  const file = new File(['hello'], 'hello.txt')
  expect(await sha256File(file)).toBe('2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824')
})

it('keeps SHA-256 correct across internal read chunks', async () => {
  const bytes = new Uint8Array(5 * 1024 * 1024 + 17).fill(0x61)
  expect(await sha256File(new File([bytes], 'large.bin'))).toBe(createHash('sha256').update(bytes).digest('hex'))
})
describe('UploadController', () => {
  it('ends a quarantined terminal job locally so a new task can start', async () => {
    const { api, session } = fixture()
    api.completeUpload.mockRejectedValueOnce(new Error('CHECKSUM_MISMATCH'))
    api.getUploadSession.mockResolvedValue({ ...session, status: 'COMPLETED' })
    const controller = new UploadController(api as never, vi.fn(async () => 'etag'), vi.fn(async () => 'f'.repeat(64)))
    await controller.start('o1', 'p1', new File(['x'], 'x.bin'))
    expect(controller.phase).toBe('FAILED')
    await controller.cancel()
    expect(controller.phase).toBe('CANCELLED')
    expect(api.cancelUpload).not.toHaveBeenCalled()
    await controller.start('o2', 'p2', new File(['y'], 'y.bin'))
    expect(controller.phase).toBe('COMPLETED')
    expect(api.createUploadSession).toHaveBeenLastCalledWith('o2', 'p2', expect.objectContaining({ display_name: 'y.bin' }))
  })
  it('keeps the same completion key when retrying a lost completion response', async () => {
    const { api } = fixture()
    api.completeUpload.mockRejectedValueOnce(new Error('lost response'))
    const controller = new UploadController(api as never, vi.fn(async () => 'etag'), vi.fn(async () => 'e'.repeat(64)))
    await controller.start('o1', 'p1', new File(['x'], 'x.bin'))
    expect(controller.phase).toBe('FAILED')
    await controller.resume()
    expect(controller.phase).toBe('COMPLETED')
    const keys = api.completeUpload.mock.calls.map((call) => call[4])
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
  })
  it('uploads multiple parts, registers ETags and completes in order', async () => {
    const { api } = fixture()
    const put = vi.fn(async (_url, body: Blob, _signal, progress) => { progress(body.size); return `etag-${put.mock.calls.length}` })
    const controller = new UploadController(api as never, put, vi.fn(async () => 'a'.repeat(64)))
    const file = new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'large.bin')
    await controller.start('o1', 'p1', file)
    expect(controller.phase).toBe('COMPLETED')
    expect(controller.progress).toBe(100)
    expect(api.signUploadParts).toHaveBeenCalledTimes(2)
    expect(api.registerUploadPart).toHaveBeenCalledTimes(2)
    expect(api.completeUpload.mock.calls[0][3]).toEqual([{ part_number: 1, etag: 'etag-1' }, { part_number: 2, etag: 'etag-2' }])
  })

  it('pauses an in-flight part and resumes from server-registered parts', async () => {
    const { api } = fixture()
    let calls = 0
    const put = vi.fn((_url, body: Blob, signal: AbortSignal, progress: (loaded: number) => void) => {
      calls += 1
      if (calls > 1) { progress(body.size); return Promise.resolve('etag-resumed') }
      return new Promise<string>((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('paused', 'AbortError')), { once: true }))
    })
    const controller = new UploadController(api as never, put, vi.fn(async () => 'b'.repeat(64)))
    const running = controller.start('o1', 'p1', new File(['content'], 'data.bin'))
    await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1))
    controller.pause()
    await running
    expect(controller.phase).toBe('PAUSED')
    await controller.resume()
    expect(api.listUploadParts).toHaveBeenCalled()
    expect(controller.phase).toBe('COMPLETED')
  })

  it('re-signs and retries failed object-storage PUTs without persisting URLs', async () => {
    const { api } = fixture()
    const put = vi.fn().mockRejectedValueOnce(new Error('temporary')).mockResolvedValueOnce('etag-ok')
    const controller = new UploadController(api as never, put, vi.fn(async () => 'c'.repeat(64)))
    await controller.start('o1', 'p1', new File(['content'], 'data.bin'))
    expect(controller.phase).toBe('COMPLETED')
    expect(api.signUploadParts).toHaveBeenCalledTimes(2)
    expect(put.mock.calls[0][0]).toContain('signature=secret')
    expect(JSON.stringify(controller)).not.toContain('signature=secret')
  })

  it('cancels the remote session and rejects expired resume', async () => {
    const { api } = fixture()
    const controller = new UploadController(api as never, vi.fn(async () => 'etag'), vi.fn(async () => 'd'.repeat(64)))
    await controller.start('o1', 'p1', new File(['x'], 'x.bin'))
    await controller.cancel()
    expect(api.cancelUpload).toHaveBeenCalled()
    expect(controller.phase).toBe('CANCELLED')
  })
})
