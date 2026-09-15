<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ApiError, platformApi, type Organization, type Project } from '../platform'
import { UploadController } from '../upload'

const organizations = ref<Organization[]>([])
const projects = ref<Project[]>([])
const organizationId = ref('')
const projectId = ref('')
const selectedFile = ref<File | null>(null)
const loading = ref(true)
const pageError = ref('')
const upload = reactive(new UploadController())
const activeProjects = computed(() => projects.value.filter((project) => project.status === 'ACTIVE'))
const canStart = computed(() => Boolean(selectedFile.value && organizationId.value && projectId.value && !['HASHING', 'UPLOADING', 'COMPLETING'].includes(upload.phase)))
const phaseLabel = computed(() => ({ IDLE: '等待文件', HASHING: '计算摘要', UPLOADING: '正在上传', PAUSED: '已暂停', COMPLETING: '服务端校验', COMPLETED: '上传完成', FAILED: '上传失败', CANCELLED: '已取消' }[upload.phase]))

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return `${cause.code}：${cause.message}`
  return cause instanceof Error ? cause.message : '加载失败'
}

async function loadProjects(): Promise<void> {
  projectId.value = ''
  if (!organizationId.value) { projects.value = []; return }
  try {
    projects.value = await platformApi.listProjects(organizationId.value)
    projectId.value = activeProjects.value[0]?.id ?? ''
  } catch (cause) { pageError.value = describe(cause) }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    organizations.value = await platformApi.listOrganizations()
    organizationId.value = organizations.value[0]?.id ?? ''
    await loadProjects()
  } catch (cause) { pageError.value = describe(cause) }
  finally { loading.value = false }
}

function choose(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  pageError.value = ''
  if (file && file.size === 0) { selectedFile.value = null; pageError.value = '不能上传空文件'; return }
  if (file && file.size > 20 * 1024 * 1024 * 1024) { selectedFile.value = null; pageError.value = '文件超过 20 GiB 上限'; return }
  selectedFile.value = file
}

async function start(): Promise<void> {
  if (!selectedFile.value) return
  await upload.start(organizationId.value, projectId.value, selectedFile.value)
}

watch(organizationId, loadProjects)
onMounted(load)
</script>

<template>
  <div class="assets-page">
    <section class="workspace-hero asset-hero">
      <div><span class="panel-label">M2 · ASSET INGESTION</span><h1>数据资产上传</h1><p>分块摘要、Multipart、暂停恢复与服务端完整性校验。</p></div>
      <span class="upload-phase" :class="upload.phase.toLowerCase()">{{ phaseLabel }}</span>
    </section>

    <a-alert v-if="pageError || upload.error" class="workspace-alert" type="error" :message="pageError || upload.error" show-icon />
    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />

    <section v-else class="workspace-grid asset-grid">
      <article class="panel workspace-panel upload-panel">
        <div class="panel-heading"><div><span class="panel-label">UPLOAD</span><h2>创建上传任务</h2></div></div>
        <div class="upload-scope">
          <label>组织<select v-model="organizationId" :disabled="upload.phase === 'UPLOADING'"><option v-for="item in organizations" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>活动项目<select v-model="projectId" :disabled="upload.phase === 'UPLOADING'"><option v-for="item in activeProjects" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        </div>
        <label class="file-drop">
          <input type="file" aria-label="选择上传文件" @change="choose" />
          <strong>{{ selectedFile?.name ?? '选择本地文件' }}</strong>
          <span>{{ selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MiB` : '最大 20 GiB；文件内容不会经过 Web 服务转发' }}</span>
        </label>
        <div class="upload-actions">
          <button class="button action-primary" type="button" :disabled="!canStart" @click="start">开始上传</button>
          <button class="button action-secondary" type="button" :disabled="upload.phase !== 'UPLOADING'" @click="upload.pause()">暂停</button>
          <button class="button action-secondary" type="button" :disabled="!['PAUSED', 'FAILED'].includes(upload.phase)" @click="upload.resume()">恢复 / 重试</button>
          <button class="button danger-button" type="button" :disabled="['IDLE', 'COMPLETED', 'CANCELLED'].includes(upload.phase)" @click="upload.cancel()">取消</button>
        </div>
      </article>

      <article class="panel workspace-panel upload-status-panel">
        <span class="panel-label">PROGRESS</span><h2>{{ phaseLabel }}</h2>
        <div class="progress-track" role="progressbar" :aria-valuenow="upload.progress" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${upload.progress}%` }"></i></div>
        <strong class="progress-number">{{ upload.progress }}%</strong>
        <dl class="upload-facts">
          <div><dt>已上传</dt><dd>{{ (upload.uploadedBytes / 1024 / 1024).toFixed(2) }} MiB</dd></div>
          <div><dt>会话状态</dt><dd>{{ upload.session?.status ?? '—' }}</dd></div>
          <div><dt>资产状态</dt><dd>{{ upload.artifact?.status ?? '—' }}</dd></div>
        </dl>
        <p class="security-note">预签名 URL 仅保存在当前任务内存中，不写入 localStorage、日志或页面文本。</p>
      </article>
    </section>
  </div>
</template>