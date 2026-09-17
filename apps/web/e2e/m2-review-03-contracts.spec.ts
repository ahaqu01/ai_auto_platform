import { expect, test } from '@playwright/test'
import { createHash, randomUUID } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'

test('P2：101 个真实 OSS 资产分页、详情下载、TTL 和完成幂等合同', async ({ page }, testInfo) => {
  test.skip(process.env.E2E_ENVIRONMENT !== 'staging', 'explicit Staging environment required')
  test.skip(!process.env.E2E_USERNAME || !process.env.E2E_PASSWORD, 'ephemeral credentials required')
  test.setTimeout(600_000)
  const runId = process.env.E2E_RUN_ID!
  const organizationName = `M2-CLOSE-03-${runId}` // Existing runner cleans only this exact test organization.
  await page.goto('/auth/login?return_to=/workspace')
  await page.locator('#username').fill(process.env.E2E_USERNAME!)
  await page.locator('#password').fill(process.env.E2E_PASSWORD!)
  await page.locator('#kc-login').click()
  await page.waitForURL('**/workspace')
  await page.getByLabel('组织名称').fill(organizationName)
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page.getByText('组织已创建')).toBeVisible()
  await page.getByLabel('项目编码').fill(`p2-${runId}`.slice(0, 48))
  await page.getByLabel('项目名称').fill('P2 真实 OSS 分页验收')
  await page.getByRole('button', { name: '新建' }).click()
  await expect(page.getByText('项目已创建')).toBeVisible()

  const orgs = await (await page.request.get('/api/v1/organizations')).json()
  const org = orgs.find((item: { name: string }) => item.name === organizationName)
  const projects = await (await page.request.get(`/api/v1/organizations/${org.id}/projects`)).json()
  const project = projects[0]
  const base = `/api/v1/organizations/${org.id}/projects/${project.id}`
  const session = await (await page.request.get('/auth/session')).json()
  const headers = { Origin: new URL(page.url()).origin, 'X-CSRF-Token': session.csrfToken }
  let oldestId = ''
  let oldestBody = Buffer.alloc(0)
  let oldestName = ''
  let signingBoundary = 0
  let completionConflict = ''
  for (let index = 0; index < 101; index += 1) {
    const content = Buffer.from(`P2-OSS-${runId}-${index}`)
    const displayName = `p2-${runId}-${index}.bin`
    const created = await page.request.post(`${base}/upload-sessions`, { headers: { ...headers, 'Idempotency-Key': randomUUID() }, data: {
      display_name: displayName, size_bytes: content.length, sha256: createHash('sha256').update(content).digest('hex'), content_type: 'application/octet-stream',
    } })
    expect(created.status()).toBe(201)
    const upload = `${base}/upload-sessions/${(await created.json()).id}`
    if (index === 0) {
      const invalid = await page.request.post(`${upload}/parts:sign`, { headers, data: { part_numbers: [1], expires_in_seconds: 901 } })
      signingBoundary = invalid.status()
      expect(signingBoundary).toBe(422)
    }
    const signing = await page.request.post(`${upload}/parts:sign`, { headers, data: { part_numbers: [1], expires_in_seconds: 900 } })
    expect(signing.status()).toBe(200)
    const [signed] = await signing.json()
    expect(signed.expires_in_seconds).toBe(900)
    const put = await page.request.put(signed.url, { data: content })
    expect(put.status()).toBe(200)
    const etag = put.headers().etag.replaceAll('"', '')
    const registered = await page.request.put(`${upload}/parts/1`, { headers, data: { etag, size_bytes: content.length } })
    expect(registered.status()).toBe(200)
    const key = randomUUID()
    const manifest = { parts: [{ part_number: 1, etag }] }
    const completed = await page.request.post(`${upload}:complete`, { headers: { ...headers, 'Idempotency-Key': key }, data: manifest })
    expect(completed.status()).toBe(201)
    const artifact = await completed.json()
    expect(artifact.integrity_status).toBe('VERIFIED')
    if (index === 0) {
      oldestId = artifact.id; oldestBody = content; oldestName = displayName
      const replay = await page.request.post(`${upload}:complete`, { headers: { ...headers, 'Idempotency-Key': key }, data: manifest })
      expect(replay.status()).toBe(200)
      expect(replay.headers()['idempotent-replayed']).toBe('true')
      expect((await replay.json()).id).toBe(oldestId)
      const conflict = await page.request.post(`${upload}:complete`, { headers: { ...headers, 'Idempotency-Key': key }, data: { parts: [{ part_number: 1, etag: 'changed' }] } })
      expect(conflict.status()).toBe(409)
      completionConflict = (await conflict.json()).code
      expect(completionConflict).toBe('IDEMPOTENCY_CONFLICT')
    }
  }
  for (const ttl of [60, 900, 901, 3600]) {
    const response = await page.request.post(`${base}/artifacts/${oldestId}:download-url`, { headers, data: { expires_in_seconds: ttl } })
    expect(response.status()).toBe(ttl <= 900 ? 200 : 422)
    if (ttl <= 900) {
      const signed = await response.json()
      expect(signed.expires_in_seconds).toBe(ttl)
      const downloaded = await page.request.get(signed.url)
      expect(downloaded.status()).toBe(200)
      expect(await downloaded.body()).toEqual(oldestBody)
    }
  }
  await page.getByRole('link', { name: /数据资产/ }).click()
  await expect(page.getByTestId('artifact-row')).toHaveCount(100)
  await expect(page.getByTestId('artifact-row').filter({ hasText: oldestName })).toHaveCount(0)
  await page.getByTestId('load-more-assets').click()
  await expect(page.getByTestId('artifact-row')).toHaveCount(101)
  await expect(page.getByTestId('load-more-assets')).toHaveCount(0)
  const row = page.getByTestId('artifact-row').filter({ hasText: oldestName })
  await row.getByRole('button', { name: '详情' }).click()
  await expect(page.getByTestId('artifact-detail')).toContainText('VERIFIED')
  await expect(page.getByTestId('artifact-detail')).toContainText('未执行恶意文件扫描')
  const downloadPromise = page.waitForEvent('download')
  await row.getByRole('button', { name: '下载' }).click()
  const download = await downloadPromise
  const path = testInfo.outputPath('oldest-asset.bin')
  await download.saveAs(path)
  expect(await readFile(path)).toEqual(oldestBody)
  await writeFile(testInfo.outputPath('m2-review03-evidence.json'), JSON.stringify({
    runId, environment: 'staging', provider: 'aliyun_oss', realAssets: 101,
    firstPage: 100, afterLoadMore: 101, laterPageDetailsAndDownload: 'PASS',
    uploadTtl901Status: signingBoundary, downloadTtls: { 60: 200, 900: 200, 901: 422, 3600: 422 },
    sameKeyReplay: 'PASS', changedPayloadCode: completionConflict, downloadContent: 'PASS',
  }, null, 2))
})
