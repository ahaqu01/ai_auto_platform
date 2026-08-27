import { readonly, ref } from 'vue'

export type BrowserUser = { subject: string; email: string; displayName: string }
type SessionResponse = { authenticated: boolean; csrfToken?: string; user?: BrowserUser }

const user = ref<BrowserUser | null>(null)
const csrfToken = ref('')
const loading = ref(false)

export async function loadSession(): Promise<void> {
  loading.value = true
  try {
    const response = await fetch('/auth/session', { credentials: 'same-origin' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const session = await response.json() as SessionResponse
    user.value = session.authenticated ? session.user ?? null : null
    csrfToken.value = session.csrfToken ?? ''
  } catch {
    user.value = null
    csrfToken.value = ''
  } finally {
    loading.value = false
  }
}

export function login(returnTo = window.location.pathname): void {
  window.location.assign(`/auth/login?return_to=${encodeURIComponent(returnTo)}`)
}

export async function logout(): Promise<void> {
  const response = await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { Origin: window.location.origin, 'X-CSRF-Token': csrfToken.value },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  user.value = null
  csrfToken.value = ''
}

export function useBrowserSession() {
  return { user: readonly(user), loading: readonly(loading), loadSession, login, logout }
}
