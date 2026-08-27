import { beforeEach, describe, expect, it, vi } from 'vitest'

import { loadSession, logout, useBrowserSession } from './auth'

describe('browser session', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads the HttpOnly-backed session without handling tokens', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ authenticated: true, csrfToken: 'csrf', user: { subject: 's', email: 'u@example.com', displayName: 'User' } }) }))
    await loadSession()
    expect(useBrowserSession().user.value?.displayName).toBe('User')
    expect(JSON.stringify(useBrowserSession())).not.toContain('access_token')
  })

  it('sends same-origin CSRF on logout', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    await logout()
    expect(fetchMock).toHaveBeenCalledWith('/auth/logout', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }))
  })
})
