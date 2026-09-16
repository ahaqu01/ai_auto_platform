import { authenticatedFetch } from './auth'

export type Organization = { id: string; name: string }
export type Member = {
  organization_id: string
  user_id: string
  email: string
  display_name: string
  role: 'OWNER' | 'ADMIN' | 'MEMBER'
}
export type Project = {
  id: string
  organization_id: string
  code: string
  name: string
  description: string | null
  status: 'ACTIVE' | 'ARCHIVED'
  version: number
}

export type UploadSession = {
  id: string
  status: 'PENDING_UPLOAD' | 'UPLOADING' | 'COMPLETING' | 'COMPLETED' | 'ABORTED' | 'EXPIRED' | 'FAILED'
  display_name: string
  expected_size: number
  expected_sha256: string
  declared_content_type: string
  expires_at: string
  version: number
}
export type SignedPart = { part_number: number; url: string; expires_in_seconds: number }
export type RegisteredPart = { part_number: number; etag: string; size_bytes: number; created_at: string; updated_at: string }
export type Artifact = {
  id: string
  display_name: string
  size_bytes: number
  status: 'VERIFYING' | 'AVAILABLE' | 'QUARANTINED' | 'FAILED' | 'DELETING' | 'DELETED'
  integrity_status: 'VERIFIED' | 'MISMATCH'
  security_scan_status?: 'PENDING' | 'CLEAN' | 'INFECTED' | 'FAILED'
  declared_content_type?: string
  expected_sha256?: string
  verified_sha256?: string
  created_at?: string
  version: number
}
export type ArtifactPage = { items: Artifact[]; next_cursor: string | null }
export type DownloadUrl = { url: string; expires_in_seconds: number; content_disposition: string }
export type UploadCreate = { display_name: string; size_bytes: number; sha256: string; content_type: string }
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await authenticatedFetch(path, init)
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as { code?: string; detail?: string }
    throw new ApiError(response.status, problem.code ?? 'REQUEST_FAILED', problem.detail ?? `HTTP ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return await response.json() as T
}

function json(method: string, body: object, headers: HeadersInit = {}): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) }
}

export function requestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (token) => {
    const value = Math.floor(Math.random() * 16)
    return (token === 'x' ? value : (value & 0x3) | 0x8).toString(16)
  })
}

export const platformApi = {
  listOrganizations: () => request<Organization[]>('/api/v1/organizations'),
  createOrganization: (name: string) => request<Organization>('/api/v1/organizations', json('POST', { name }, { 'Idempotency-Key': requestId() })),
  listMembers: (organizationId: string) => request<Member[]>(`/api/v1/organizations/${organizationId}/members`),
  inviteMember: (organizationId: string, email: string, role: 'ADMIN' | 'MEMBER') => request<{ token: string }>(`/api/v1/organizations/${organizationId}/invites`, json('POST', { email, role })),
  updateMemberRole: (organizationId: string, userId: string, role: Member['role']) => request<Member>(`/api/v1/organizations/${organizationId}/members/${userId}`, json('PATCH', { role })),
  removeMember: (organizationId: string, userId: string) => request<void>(`/api/v1/organizations/${organizationId}/members/${userId}`, { method: 'DELETE' }),
  listProjects: (organizationId: string) => request<Project[]>(`/api/v1/organizations/${organizationId}/projects?limit=100`),
  createProject: (organizationId: string, payload: { code: string; name: string; description?: string }) => request<Project>(`/api/v1/organizations/${organizationId}/projects`, json('POST', payload, { 'Idempotency-Key': requestId() })),
  updateProject: (organizationId: string, project: Project, name: string) => request<Project>(`/api/v1/organizations/${organizationId}/projects/${project.id}`, json('PATCH', { name }, { 'If-Match': `"${project.version}"` })),
  createUploadSession: (organizationId: string, projectId: string, payload: UploadCreate) => request<UploadSession>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions`, json('POST', payload, { 'Idempotency-Key': requestId() })),
  getUploadSession: (organizationId: string, projectId: string, uploadId: string) => request<UploadSession>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}`),
  signUploadParts: (organizationId: string, projectId: string, uploadId: string, partNumbers: number[]) => request<SignedPart[]>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}/parts:sign`, json('POST', { part_numbers: partNumbers, expires_in_seconds: 900 })),
  registerUploadPart: (organizationId: string, projectId: string, uploadId: string, partNumber: number, payload: { etag: string; size_bytes: number }) => request<RegisteredPart>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}/parts/${partNumber}`, json('PUT', payload)),
  listUploadParts: (organizationId: string, projectId: string, uploadId: string) => request<RegisteredPart[]>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}/parts`),
  completeUpload: (organizationId: string, projectId: string, uploadId: string, parts: { part_number: number; etag: string }[]) => request<Artifact>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}:complete`, json('POST', { parts }, { 'Idempotency-Key': requestId() })),
  cancelUpload: (organizationId: string, projectId: string, uploadId: string) => request<UploadSession>(`/api/v1/organizations/${organizationId}/projects/${projectId}/upload-sessions/${uploadId}:cancel`, { method: 'POST', headers: { 'Idempotency-Key': requestId() } }),
  listArtifacts: (organizationId: string, projectId: string) => request<ArtifactPage>(`/api/v1/organizations/${organizationId}/projects/${projectId}/artifacts?limit=100`),
  getArtifact: (organizationId: string, projectId: string, artifactId: string) => request<Artifact>(`/api/v1/organizations/${organizationId}/projects/${projectId}/artifacts/${artifactId}`),
  createArtifactDownloadUrl: (organizationId: string, projectId: string, artifactId: string) => request<DownloadUrl>(`/api/v1/organizations/${organizationId}/projects/${projectId}/artifacts/${artifactId}:download-url`, json('POST', { expires_in_seconds: 600 })),
  setProjectArchived: (organizationId: string, project: Project, archived: boolean) => request<Project>(`/api/v1/organizations/${organizationId}/projects/${project.id}:${archived ? 'archive' : 'restore'}`, { method: 'POST', headers: { 'If-Match': `"${project.version}"` } }),
}

export function putPresignedPart(url: string, body: Blob, signal: AbortSignal, onProgress: (loaded: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', url)
    request.withCredentials = false
    request.upload.onprogress = (event) => onProgress(event.loaded)
    request.onerror = () => reject(new Error('对象存储上传失败'))
    request.onabort = () => reject(new DOMException('上传已暂停', 'AbortError'))
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`对象存储上传失败（HTTP ${request.status}）`))
        return
      }
      const etag = request.getResponseHeader('ETag')
      if (!etag) {
        reject(new Error('对象存储未暴露 ETag，请检查 Bucket CORS'))
        return
      }
      resolve(etag)
    }
    signal.addEventListener('abort', () => request.abort(), { once: true })
    request.send(body)
  })
}
