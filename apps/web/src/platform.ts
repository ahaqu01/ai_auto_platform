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

export const platformApi = {
  listOrganizations: () => request<Organization[]>('/api/v1/organizations'),
  createOrganization: (name: string) => request<Organization>('/api/v1/organizations', json('POST', { name }, { 'Idempotency-Key': crypto.randomUUID() })),
  listMembers: (organizationId: string) => request<Member[]>(`/api/v1/organizations/${organizationId}/members`),
  inviteMember: (organizationId: string, email: string, role: 'ADMIN' | 'MEMBER') => request<{ token: string }>(`/api/v1/organizations/${organizationId}/invites`, json('POST', { email, role })),
  updateMemberRole: (organizationId: string, userId: string, role: Member['role']) => request<Member>(`/api/v1/organizations/${organizationId}/members/${userId}`, json('PATCH', { role })),
  removeMember: (organizationId: string, userId: string) => request<void>(`/api/v1/organizations/${organizationId}/members/${userId}`, { method: 'DELETE' }),
  listProjects: (organizationId: string) => request<Project[]>(`/api/v1/organizations/${organizationId}/projects?limit=100`),
  createProject: (organizationId: string, payload: { code: string; name: string; description?: string }) => request<Project>(`/api/v1/organizations/${organizationId}/projects`, json('POST', payload, { 'Idempotency-Key': crypto.randomUUID() })),
  updateProject: (organizationId: string, project: Project, name: string) => request<Project>(`/api/v1/organizations/${organizationId}/projects/${project.id}`, json('PATCH', { name }, { 'If-Match': `"${project.version}"` })),
  setProjectArchived: (organizationId: string, project: Project, archived: boolean) => request<Project>(`/api/v1/organizations/${organizationId}/projects/${project.id}:${archived ? 'archive' : 'restore'}`, { method: 'POST', headers: { 'If-Match': `"${project.version}"` } }),
}
