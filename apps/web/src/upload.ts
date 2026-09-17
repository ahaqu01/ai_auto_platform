import { ApiError, platformApi, putPresignedPart, requestId, type Artifact, type RegisteredPart, type UploadSession } from './platform'
import { sha256File } from './fileHash'

export type UploadPhase = 'IDLE' | 'HASHING' | 'UPLOADING' | 'PAUSED' | 'COMPLETING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

type UploadApi = Pick<typeof platformApi, 'createUploadSession' | 'getUploadSession' | 'signUploadParts' | 'registerUploadPart' | 'listUploadParts' | 'completeUpload' | 'cancelUpload'>
type PartTransport = (url: string, body: Blob, signal: AbortSignal, onProgress: (loaded: number) => void) => Promise<string>
type HashFile = typeof sha256File

const PART_SIZE = 8 * 1024 * 1024

export class UploadController {
  phase: UploadPhase = 'IDLE'
  uploadedBytes = 0
  error = ''
  artifact: Artifact | null = null
  session: UploadSession | null = null
  private file: File | null = null
  private organizationId = ''
  private projectId = ''
  private registered = new Map<number, RegisteredPart>()
  private aborter: AbortController | null = null
  private completionKey = ''

  constructor(
    private readonly api: UploadApi = platformApi,
    private readonly putPart: PartTransport = putPresignedPart,
    private readonly hashFile: HashFile = sha256File,
  ) {}

  get progress(): number {
    if (!this.file?.size) return 0
    return Math.min(100, Math.round((this.uploadedBytes / this.file.size) * 100))
  }

  async start(organizationId: string, projectId: string, file: File): Promise<void> {
    if (this.phase !== 'IDLE' && this.phase !== 'FAILED' && this.phase !== 'CANCELLED' && this.phase !== 'COMPLETED') throw new Error('已有上传任务正在执行')
    this.reset(organizationId, projectId, file)
    this.aborter = new AbortController()
    this.phase = 'HASHING'
    try {
      const sha256 = await this.hashFile(file, this.aborter.signal)
      this.session = await this.api.createUploadSession(organizationId, projectId, {
        display_name: file.name,
        size_bytes: file.size,
        sha256,
        content_type: file.type || 'application/octet-stream',
      })
      await this.uploadMissingParts()
    } catch (cause) {
      this.failUnlessPaused(cause)
    }
  }

  pause(): void {
    if (this.phase !== 'UPLOADING') return
    this.phase = 'PAUSED'
    this.aborter?.abort()
  }

  async resume(): Promise<void> {
    if (this.phase !== 'PAUSED' && this.phase !== 'FAILED') return
    if (!this.file) throw new Error('当前页面没有可恢复的文件上下文')
    if (!this.session) {
      await this.start(this.organizationId, this.projectId, this.file)
      return
    }
    this.error = ''
    this.aborter = new AbortController()
    try {
      this.session = await this.api.getUploadSession(this.organizationId, this.projectId, this.session.id)
      if (['EXPIRED', 'ABORTED', 'FAILED'].includes(this.session.status)) throw new ApiError(409, 'UPLOAD_NOT_RESUMABLE', '上传会话已终止，请重新选择文件')
      const parts = await this.api.listUploadParts(this.organizationId, this.projectId, this.session.id)
      this.registered = new Map(parts.map((part) => [part.part_number, part]))
      this.uploadedBytes = parts.reduce((total, part) => total + part.size_bytes, 0)
      await this.uploadMissingParts()
    } catch (cause) {
      this.failUnlessPaused(cause)
    }
  }

  async cancel(): Promise<void> {
    this.aborter?.abort()
    if (this.session) {
      try {
        const current = await this.api.getUploadSession(this.organizationId, this.projectId, this.session.id)
        this.session = current
        if (!['COMPLETED', 'ABORTED', 'EXPIRED', 'FAILED'].includes(current.status)) {
          await this.api.cancelUpload(this.organizationId, this.projectId, this.session.id)
        }
      } catch (cause) {
        this.phase = 'FAILED'
        this.error = describe(cause)
        return
      }
    }
    this.phase = 'CANCELLED'
    this.error = ''
  }

  private async uploadMissingParts(): Promise<void> {
    if (!this.file || !this.session || !this.aborter) return
    this.phase = 'UPLOADING'
    const partCount = Math.ceil(this.file.size / PART_SIZE)
    for (let partNumber = 1; partNumber <= partCount; partNumber += 1) {
      if (this.phase !== 'UPLOADING') return
      if (this.registered.has(partNumber)) continue
      const start = (partNumber - 1) * PART_SIZE
      const end = Math.min(this.file.size, start + PART_SIZE)
      const body = this.file.slice(start, end)
      const completedBefore = this.uploadedBytes
      const etag = await this.uploadPartWithRetry(partNumber, body, completedBefore)
      const registered = await this.api.registerUploadPart(this.organizationId, this.projectId, this.session.id, partNumber, { etag, size_bytes: body.size })
      this.registered.set(partNumber, registered)
      this.uploadedBytes = Array.from(this.registered.values()).reduce((total, part) => total + part.size_bytes, 0)
    }
    if (this.phase !== 'UPLOADING') return
    this.phase = 'COMPLETING'
    const parts = Array.from(this.registered.values()).sort((left, right) => left.part_number - right.part_number).map(({ part_number, etag }) => ({ part_number, etag }))
    this.artifact = await this.api.completeUpload(this.organizationId, this.projectId, this.session.id, parts, this.completionKey)
    this.phase = 'COMPLETED'
  }

  private async uploadPartWithRetry(partNumber: number, body: Blob, completedBefore: number): Promise<string> {
    let lastError: unknown
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      if (!this.aborter) throw new Error('上传控制器不可用')
      try {
        const [signed] = await this.api.signUploadParts(this.organizationId, this.projectId, this.session!.id, [partNumber])
        return await this.putPart(signed.url, body, this.aborter.signal, (loaded) => { this.uploadedBytes = completedBefore + loaded })
      } catch (cause) {
        lastError = cause
        if (this.phase === 'PAUSED' || this.aborter.signal.aborted) throw cause
      }
    }
    throw lastError
  }

  private reset(organizationId: string, projectId: string, file: File): void {
    this.organizationId = organizationId
    this.projectId = projectId
    this.file = file
    this.registered.clear()
    this.uploadedBytes = 0
    this.error = ''
    this.artifact = null
    this.session = null
    this.completionKey = requestId()
  }

  private failUnlessPaused(cause: unknown): void {
    if (this.phase === 'PAUSED' || this.phase === 'CANCELLED') return
    this.phase = 'FAILED'
    this.error = describe(cause)
  }
}

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return `${cause.code}：${cause.message}`
  return cause instanceof Error ? cause.message : '上传失败'
}
