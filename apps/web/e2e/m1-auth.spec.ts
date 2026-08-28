import { expect, test } from '@playwright/test'

test('Keycloak authorization code, BFF cookie, protected API and logout', async ({
  page,
  context,
}, testInfo) => {
  const username = process.env.E2E_USERNAME
  const password = process.env.E2E_PASSWORD
  test.skip(!username || !password, 'E2E_USERNAME and E2E_PASSWORD are required')

  await page.goto('/auth/login?return_to=/')
  await expect(page.locator('#kc-page-title')).toContainText('Sign in')
  await page.locator('#username').fill(username!)
  await page.locator('#password').fill(password!)
  await page.locator('#kc-login').click()
  await page.waitForURL('**/')

  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()
  const session = await page.evaluate(async () => {
    const response = await fetch('/auth/session', { credentials: 'same-origin' })
    return { status: response.status, body: await response.json() }
  })
  expect(session.status).toBe(200)
  expect(session.body.authenticated).toBe(true)
  expect(session.body.user.email).toBe('m1-e2e@example.test')

  const cookies = await context.cookies()
  const bffCookie = cookies.find((cookie) => cookie.name === 'platform_session')
  expect(bffCookie).toBeDefined()
  expect(bffCookie?.httpOnly).toBe(true)
  expect(bffCookie?.sameSite).toBe('Lax')

  const protectedApi = await page.evaluate(async () => {
    const response = await fetch('/api/v1/organizations', {
      credentials: 'same-origin',
    })
    return { status: response.status, body: await response.json() }
  })
  expect(protectedApi.status).toBe(200)
  expect(Array.isArray(protectedApi.body)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('authenticated-console.png') })

  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  const afterLogout = await page.evaluate(async () => {
    const response = await fetch('/auth/session', { credentials: 'same-origin' })
    return response.json()
  })
  expect(afterLogout.authenticated).toBe(false)
  expect((await context.cookies()).some((cookie) => cookie.name === 'platform_session')).toBe(false)
})
