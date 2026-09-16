<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

 type Health = { status: string; service: string; version: string }
const health = ref<Health | null>(null)
const healthError = ref('')
const now = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date())

const milestones = [
  { code: 'M0', title: '工程与运行底座', detail: '契约、数据库、迁移、CI、安全门禁与演示环境', percent: 100, state: '已验收' },
  { code: 'M1', title: '身份与租户工作台', detail: 'OIDC、组织、成员、项目、RBAC、审计与 Outbox', percent: 100, state: '已验收' },
  { code: 'M2', title: '数据资产与对象存储', detail: '上传、Multipart、完整性校验、授权、清理与 Web 闭环', percent: 100, state: '已验收' },
]

const capabilities = [
  { icon: '◇', title: '组织与项目', text: '成员、角色、项目生命周期与租户隔离', state: '可操作', tone: 'ready', to: '/workspace' },
  { icon: '▤', title: '数据资产', text: '分片上传、摘要校验、暂停恢复与资产状态', state: '可操作', tone: 'ready', to: '/data-assets' },
  { icon: '⌖', title: '数据与标注', text: '质量、版本、标注和困难样本工作流', state: '规划中', tone: 'planned', to: '' },
  { icon: '↗', title: '模型与训练', text: '实验、训练、评估与模型版本晋级', state: '规划中', tone: 'planned', to: '' },
  { icon: '⬡', title: '芯片适配', text: '转换、量化、编译与兼容矩阵', state: '规划中', tone: 'planned', to: '' },
  { icon: '◫', title: '实机验证与交付', text: '设备池、自动测试、验收报告与 OTA', state: '规划中', tone: 'planned', to: '' },
]

const flow = [
  { number: '01', title: '项目空间', text: '建立组织、成员、角色和项目边界', state: 'ready' },
  { number: '02', title: '资产接入', text: '上传数据/模型工件并完成强校验', state: 'active' },
  { number: '03', title: '训练评估', text: '执行训练、记录实验和质量指标', state: 'future' },
  { number: '04', title: '芯片适配', text: '生成特定硬件候选部署包', state: 'future' },
  { number: '05', title: '真实设备验证', text: '采集精度、延迟、功耗和稳定性', state: 'future' },
  { number: '06', title: '验收交付', text: '固化证据、报告、BOM 和运行边界', state: 'future' },
]

const runtimeLabel = computed(() => health.value ? '运行正常' : healthError.value ? '连接异常' : '检查中')

onMounted(async () => {
  try {
    const response = await fetch('/health/live', { credentials: 'same-origin' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json() as Health
  } catch (cause) {
    healthError.value = cause instanceof Error ? cause.message : '未知错误'
  }
})
</script>

<template>
  <div class="dashboard showcase-dashboard">
    <section class="welcome-panel console-welcome">
      <div class="welcome-copy">
        <div class="section-kicker"><span></span>AI DELIVERY CONTROL PLANE</div>
        <h1>让 AI 方案走到真实设备，<br><em>并形成可验收的交付结果</em></h1>
        <p>统一组织需求、数据资产、模型、异构芯片和真实设备验证；每一步保留版本、权限、状态和证据。</p>
        <div class="welcome-actions dashboard-actions">
          <RouterLink class="button button-primary" to="/data-assets">上传数据资产 <span>→</span></RouterLink>
          <RouterLink class="button button-secondary live-button" to="/workspace">管理组织与项目</RouterLink>
          <a class="button ghost-button" href="/docs" target="_blank" rel="noreferrer">API 文档 ↗</a>
        </div>
      </div>
      <div class="mission-card" aria-label="当前建设状态">
        <div class="mission-top"><span>当前阶段</span><b>M2</b></div>
        <strong>资产闭环 · 已验收</strong>
        <p>真实 MinIO / OSS 浏览器 E2E 与故障运维门禁已通过</p>
        <div class="mission-progress"><i></i></div>
        <small>工程底座与租户闭环已验收</small>
      </div>
    </section>

    <section class="milestone-strip" aria-label="阶段完成情况">
      <article v-for="item in milestones" :key="item.code" class="milestone-card">
        <div class="milestone-code">{{ item.code }}</div>
        <div class="milestone-copy"><div><strong>{{ item.title }}</strong><span :class="{ pending: item.percent < 100 }">{{ item.state }}</span></div><p>{{ item.detail }}</p><div class="mini-progress"><i :style="{ width: `${item.percent}%` }"></i></div></div>
        <b>{{ item.percent }}%</b>
      </article>
    </section>

    <section class="section-head">
      <div><span class="panel-label">AVAILABLE NOW</span><h2>当前可展示与操作</h2><p>深色状态为当前已经接入真实 API 的能力。</p></div>
      <span class="updated-at">更新于 {{ now }}</span>
    </section>
    <section class="capability-grid">
      <component :is="item.to ? RouterLink : 'article'" v-for="item in capabilities" :key="item.title" :to="item.to || undefined" class="capability-card" :class="item.tone" data-testid="capability-card">
        <div class="capability-icon">{{ item.icon }}</div><span class="capability-state">{{ item.state }}</span><h3>{{ item.title }}</h3><p>{{ item.text }}</p><span v-if="item.to" class="card-link">进入模块 →</span><span v-else class="card-link muted">后续里程碑</span>
      </component>
    </section>

    <section class="dashboard-lower">
      <article class="panel delivery-map">
        <div class="panel-heading"><div><span class="panel-label">DELIVERY WORKFLOW</span><h2>从项目到交付的工程链路</h2></div><span class="truthful-note">按验收进度点亮</span></div>
        <div class="flow-line">
          <div v-for="item in flow" :key="item.number" class="flow-step" :class="item.state" data-testid="pipeline-stage">
            <span class="flow-number">{{ item.number }}</span><div><strong>{{ item.title }}</strong><p>{{ item.text }}</p></div><i></i>
          </div>
        </div>
      </article>

      <aside class="panel operations-panel">
        <div class="panel-heading"><div><span class="panel-label">RUNTIME & GATES</span><h2>环境与质量门禁</h2></div><span class="runtime-pill" :class="{ error: healthError }"><i></i>{{ runtimeLabel }}</span></div>
        <div class="runtime-identity"><span>API</span><div><strong>{{ health?.service ?? 'ai-auto-platform' }}</strong><small>{{ health ? `v${health.version}` : healthError ? `未连接 · ${healthError}` : '正在读取健康状态' }}</small></div></div>
        <ul class="gate-list">
          <li><i class="pass">✓</i><span><b>身份与租户隔离</b><small>Keycloak · RBAC · PostgreSQL RLS</small></span></li>
          <li><i class="pass">✓</i><span><b>可追溯业务写入</b><small>幂等 · 审计 · Outbox · 乐观锁</small></span></li>
          <li><i class="pass">✓</i><span><b>资产完整性</b><small>SHA-256 · Multipart · 生命周期</small></span></li>
          <li><i class="pass">✓</i><span><b>真实存储终验</b><small>MinIO / OSS 浏览器 E2E · 故障与运维闭环</small></span></li>
        </ul>
      </aside>
    </section>
  </div>
</template>
