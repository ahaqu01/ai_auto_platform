import { expect, test, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { mkdir, readFile, rm, truncate, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const runId = process.env.E2E_RUN_ID ?? `local-${Date.now()}`
const organizationName = `M2-CLOSE-03-${runId}`
const projectCode = `m2-close-03-${runId}`.toLowerCase().replace(/[^a-z0-9-]/g, '-').slice(0, 48)
const sampleDir = join(tmpdir(), `m2-close-03-${runId}`)

test.afterEach(async () => { await rm(sampleDir, { recursive: true, force: true }) })

async function login(page: Page): Promise<void> {
  const username = process.env.E2E_USERNAME
  const password = process.env.E2E_PASSWORD
  test.skip(!username || !password, 'E2E_USERNAME and E2E_PASSWORD are required')
  await page.goto('/auth/login?return_to=/workspace')
  await expect(page.locator('#kc-page-title')).toContainText('登录')
  await page.locator('#username').fill(username!)
  await page.locator('#password').fill(password!)
  await page.locator('#kc-login').click()
  await page.waitForURL('**/workspace')
  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()
}

async function selectFile(page: Page, name: string, size: number): Promise<void> {
  const body = Buffer.alloc(size, name.charCodeAt(0) || 65)
  await page.getByLabel('选择上传文件').setInputFiles({ name, mimeType: 'application/octet-stream', buffer: body })
}

async function waitForUpload(page: Page): Promise<void> {
  await expect(page.locator('.upload-phase')).toHaveText('正在上传', { timeout: 30_000 })
}

async function selectSparseFile(page: Page, name: string, size: number): Promise<void> {
  await mkdir(sampleDir, { recursive: true })
  const filePath = join(sampleDir, name)
  await writeFile(filePath, '')
  await truncate(filePath, size)
  await page.getByLabel('选择上传文件').setInputFiles(filePath)
}

test('真实阿里云 OSS：暂停恢复、取消、断线重试、校验、详情和授权下载', async ({ page, context }, testInfo) => {
  test.setTimeout(900_000)
  await login(page)

  await page.getByLabel('组织名称').fill(organizationName)
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page.getByText('组织已创建')).toBeVisible()
  await page.getByLabel('项目编码').fill(projectCode)
  await page.getByLabel('项目名称').fill('真实 MinIO 浏览器验收')
  await page.getByRole('button', { name: '新建' }).click()
  await expect(page.getByText('项目已创建')).toBeVisible()

  await page.getByRole('link', { name: /数据资产/ }).click()
  await expect(page.getByRole('heading', { name: '数据资产上传' })).toBeVisible()
  await expect(page.getByLabel('组织')).toHaveValue(await page.getByLabel('组织').locator('option', { hasText: organizationName }).getAttribute('value') ?? '')

  const cdp = await context.newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 80,
    downloadThroughput: 512 * 1024,
    uploadThroughput: 256 * 1024,
    connectionType: 'cellular3g',
  })
  await selectSparseFile(page, `pause-100mb-${runId}.bin`, 100 * 1024 * 1024)
  await page.getByRole('button', { name: '开始上传' }).click()
  await waitForUpload(page)
  await page.getByRole('button', { name: '暂停', exact: true }).click()
  await expect(page.locator('.upload-phase')).toHaveText('已暂停')
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1,
  })
  await page.getByRole('button', { name: '恢复 / 重试' }).click()
  await expect(page.locator('.upload-phase')).toHaveText('上传完成', { timeout: 60_000 })

  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 80,
    downloadThroughput: 512 * 1024,
    uploadThroughput: 256 * 1024,
    connectionType: 'cellular3g',
  })
  await selectFile(page, `cancel-${runId}.bin`, 9 * 1024 * 1024)
  await page.getByRole('button', { name: '开始上传' }).click()
  await waitForUpload(page)
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.upload-phase')).toHaveText('已取消')
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1,
  })

  let putAttempts = 0
  await page.route('**/*', async (route) => {
    if (route.request().method() === 'PUT' && putAttempts++ === 0) {
      await route.abort('failed')
      return
    }
    await route.continue()
  })
  const finalName = `retry-${runId}.bin`
  await selectFile(page, finalName, 1024)
  await page.getByRole('button', { name: '开始上传' }).click()
  await expect(page.locator('.upload-phase')).toHaveText('上传完成', { timeout: 60_000 })
  expect(putAttempts).toBeGreaterThanOrEqual(2)
  await page.unroute('**/*')

  const largeName = `complete-1gb-${runId}.bin`
  await selectSparseFile(page, largeName, 1024 * 1024 * 1024)
  await page.getByRole('button', { name: '开始上传' }).click()
  await expect(page.locator('.upload-phase')).toHaveText('上传完成', { timeout: 600_000 })
  await expect(page.getByTestId('artifact-row').filter({ hasText: largeName })).toContainText('可用')

  const row = page.getByTestId('artifact-row').filter({ hasText: finalName })
  await expect(row).toContainText('可用')
  await row.getByRole('button', { name: '详情' }).click()
  await expect(page.getByTestId('artifact-detail')).toContainText('VERIFIED')
  const downloadPromise = page.waitForEvent('download')
  await row.getByRole('button', { name: '下载' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe(finalName)
  const downloadedPath = testInfo.outputPath(finalName)
  await download.saveAs(downloadedPath)
  const expected = Buffer.alloc(1024, finalName.charCodeAt(0) || 65)
  const actual = await readFile(downloadedPath)
  expect(createHash('sha256').update(actual).digest('hex')).toBe(
    createHash('sha256').update(expected).digest('hex'),
  )
  await page.screenshot({ path: testInfo.outputPath('m2-close-03-assets.png'), fullPage: true })
})
