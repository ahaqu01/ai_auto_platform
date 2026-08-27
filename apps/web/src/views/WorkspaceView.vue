<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, platformApi, type Member, type Organization, type Project } from '../platform'

const organizations = ref<Organization[]>([])
const selectedId = ref('')
const members = ref<Member[]>([])
const projects = ref<Project[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const organizationName = ref('')
const inviteEmail = ref('')
const inviteRole = ref<'ADMIN' | 'MEMBER'>('MEMBER')
const projectCode = ref('')
const projectName = ref('')

const selected = computed(() => organizations.value.find((item) => item.id === selectedId.value) ?? null)

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return `${cause.code}：${cause.message}`
  return cause instanceof Error ? cause.message : '请求失败'
}

async function refreshScope(): Promise<void> {
  if (!selectedId.value) {
    members.value = []
    projects.value = []
    return
  }
  error.value = ''
  try {
    ;[members.value, projects.value] = await Promise.all([
      platformApi.listMembers(selectedId.value),
      platformApi.listProjects(selectedId.value),
    ])
    localStorage.setItem('platform.organization', selectedId.value)
  } catch (cause) {
    error.value = describe(cause)
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    organizations.value = await platformApi.listOrganizations()
    const saved = localStorage.getItem('platform.organization')
    selectedId.value = organizations.value.some((item) => item.id === saved)
      ? saved ?? ''
      : organizations.value[0]?.id ?? ''
    await refreshScope()
  } catch (cause) {
    error.value = describe(cause)
  } finally {
    loading.value = false
  }
}

async function run(action: () => Promise<void>, success: string): Promise<void> {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
    notice.value = success
  } catch (cause) {
    error.value = describe(cause)
  } finally {
    busy.value = false
  }
}

async function createOrganization(): Promise<void> {
  await run(async () => {
    const created = await platformApi.createOrganization(organizationName.value)
    organizations.value.push(created)
    selectedId.value = created.id
    organizationName.value = ''
    await refreshScope()
  }, '组织已创建')
}

async function invite(): Promise<void> {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await platformApi.inviteMember(selectedId.value, inviteEmail.value, inviteRole.value)
    inviteEmail.value = ''
    notice.value = `邀请已创建；一次性令牌：${created.token}`
  } catch (cause) {
    error.value = describe(cause)
  } finally {
    busy.value = false
  }
}

async function changeRole(member: Member, role: Member['role']): Promise<void> {
  await run(async () => {
    const updated = await platformApi.updateMemberRole(selectedId.value, member.user_id, role)
    members.value = members.value.map((item) => item.user_id === updated.user_id ? updated : item)
  }, '成员角色已更新')
}

async function remove(member: Member): Promise<void> {
  if (!window.confirm(`确认移除 ${member.display_name}？`)) return
  await run(async () => {
    await platformApi.removeMember(selectedId.value, member.user_id)
    members.value = members.value.filter((item) => item.user_id !== member.user_id)
  }, '成员已移除')
}

async function createProject(): Promise<void> {
  await run(async () => {
    const created = await platformApi.createProject(selectedId.value, { code: projectCode.value, name: projectName.value })
    projects.value.push(created)
    projectCode.value = ''
    projectName.value = ''
  }, '项目已创建')
}

async function rename(project: Project): Promise<void> {
  const name = window.prompt('项目名称', project.name)?.trim()
  if (!name || name === project.name) return
  await run(async () => {
    const updated = await platformApi.updateProject(selectedId.value, project, name)
    projects.value = projects.value.map((item) => item.id === updated.id ? updated : item)
  }, '项目已更新')
}

async function toggleArchived(project: Project): Promise<void> {
  await run(async () => {
    const updated = await platformApi.setProjectArchived(selectedId.value, project, project.status === 'ACTIVE')
    projects.value = projects.value.map((item) => item.id === updated.id ? updated : item)
  }, project.status === 'ACTIVE' ? '项目已归档' : '项目已恢复')
}

onMounted(load)
</script>

<template>
  <div class="workspace-page">
    <section class="workspace-hero">
      <div><span class="panel-label">M1 · TENANT WORKSPACE</span><h1>组织与项目</h1><p>在当前组织边界内管理成员、角色与项目生命周期。</p></div>
      <div class="organization-switcher">
        <label for="organization-select">当前组织</label>
        <select id="organization-select" v-model="selectedId" :disabled="loading || busy" @change="refreshScope">
          <option v-if="!organizations.length" value="">暂无组织</option>
          <option v-for="organization in organizations" :key="organization.id" :value="organization.id">{{ organization.name }}</option>
        </select>
      </div>
    </section>

    <a-alert v-if="error" class="workspace-alert" type="error" :message="error" show-icon />
    <a-alert v-if="notice" class="workspace-alert" type="success" :message="notice" show-icon closable @close="notice = ''" />
    <a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" />

    <template v-else>
      <section class="workspace-grid compact-grid">
        <article class="panel workspace-panel">
          <div class="panel-heading"><div><span class="panel-label">ORGANIZATION</span><h2>新建组织</h2></div></div>
          <form class="inline-form" @submit.prevent="createOrganization">
            <input v-model.trim="organizationName" required minlength="2" maxlength="120" placeholder="组织名称" aria-label="组织名称" />
            <button class="button action-primary" type="submit" :disabled="busy">创建</button>
          </form>
        </article>
        <article class="panel workspace-panel scope-summary">
          <span class="panel-label">CURRENT SCOPE</span><h2>{{ selected?.name ?? '尚未选择组织' }}</h2>
          <p>{{ members.length }} 位成员 · {{ projects.length }} 个项目</p>
        </article>
      </section>

      <section v-if="selected" class="workspace-grid">
        <article class="panel workspace-panel">
          <div class="panel-heading"><div><span class="panel-label">MEMBERS</span><h2>成员管理</h2></div><span class="count-badge">{{ members.length }}</span></div>
          <form class="inline-form member-invite" @submit.prevent="invite">
            <input v-model.trim="inviteEmail" required type="email" placeholder="成员邮箱" aria-label="成员邮箱" />
            <select v-model="inviteRole" aria-label="邀请角色"><option value="MEMBER">Member</option><option value="ADMIN">Admin</option></select>
            <button class="button action-primary" type="submit" :disabled="busy">邀请</button>
          </form>
          <div class="data-list">
            <div v-for="member in members" :key="member.user_id" class="data-row" data-testid="member-row">
              <div class="row-main"><strong>{{ member.display_name }}</strong><span>{{ member.email }}</span></div>
              <select :value="member.role" :disabled="busy || member.role === 'OWNER'" :aria-label="`${member.display_name}角色`" @change="changeRole(member, ($event.target as HTMLSelectElement).value as Member['role'])"><option value="OWNER">Owner</option><option value="ADMIN">Admin</option><option value="MEMBER">Member</option></select>
              <button class="text-action danger" type="button" :disabled="busy || member.role === 'OWNER'" @click="remove(member)">移除</button>
            </div>
            <p v-if="!members.length" class="empty-state">暂无成员</p>
          </div>
        </article>

        <article class="panel workspace-panel">
          <div class="panel-heading"><div><span class="panel-label">PROJECTS</span><h2>项目管理</h2></div><span class="count-badge">{{ projects.length }}</span></div>
          <form class="inline-form project-create" @submit.prevent="createProject">
            <input v-model.trim="projectCode" required minlength="2" pattern="[a-z0-9][a-z0-9-]*" placeholder="project-code" aria-label="项目编码" />
            <input v-model.trim="projectName" required minlength="2" placeholder="项目名称" aria-label="项目名称" />
            <button class="button action-primary" type="submit" :disabled="busy">新建</button>
          </form>
          <div class="data-list">
            <div v-for="project in projects" :key="project.id" class="data-row" data-testid="project-row">
              <div class="row-main"><strong>{{ project.name }}</strong><span>{{ project.code }} · v{{ project.version }}</span></div>
              <span class="status-chip" :class="{ archived: project.status === 'ARCHIVED' }">{{ project.status === 'ACTIVE' ? '进行中' : '已归档' }}</span>
              <button class="text-action" type="button" :disabled="busy" @click="rename(project)">编辑</button>
              <button class="text-action" type="button" :disabled="busy" @click="toggleArchived(project)">{{ project.status === 'ACTIVE' ? '归档' : '恢复' }}</button>
            </div>
            <p v-if="!projects.length" class="empty-state">暂无项目</p>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>
