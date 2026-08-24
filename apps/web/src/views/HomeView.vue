<script setup lang="ts">
import { onMounted, ref } from 'vue'

type Health = { status: string; service: string; version: string }

const health = ref<Health | null>(null)
const error = ref('')

const overview = [
  { label: '组织与项目', value: 'API', detail: '租户隔离基础能力已完成', tone: 'blue', icon: '◇', status: '基础可用' },
  { label: '数据资产', value: '--', detail: '数据集与对象存储待接入', tone: 'cyan', icon: '▤', status: '规划中' },
  { label: '训练任务', value: '--', detail: '任务编排与算力调度待接入', tone: 'violet', icon: '↗', status: '规划中' },
  { label: '设备节点', value: '--', detail: 'Agent 与真实设备管理待接入', tone: 'orange', icon: '◫', status: '规划中' },
]

const pipeline = [
  { name: '数据准备', description: '采集、清洗与版本管理', icon: '01' },
  { name: '智能标注', description: '标注任务与质量验收', icon: '02' },
  { name: '模型训练', description: '实验、训练与评估追踪', icon: '03' },
  { name: '芯片适配', description: '转换、量化与性能优化', icon: '04' },
  { name: '设备验证', description: '真实硬件自动化测试', icon: '05' },
  { name: '交付部署', description: '制品、发布与运行监控', icon: '06' },
]

const progress = [
  { title: '工程底座与安全基线', detail: '数据库、API 契约、租户边界与测试体系', status: '已完成' },
  { title: '本地演示部署', detail: '容器编排、迁移、健康检查与局域网入口', status: '已完成' },
  { title: '可视化管理台', detail: '统一导航、工作台和模块进度呈现', status: '进行中' },
  { title: '身份与业务闭环', detail: '登录、数据、标注、训练、模型和设备', status: '下一阶段' },
]

onMounted(async () => {
  try {
    const response = await fetch('/health/live', { credentials: 'same-origin' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json() as Health
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '未知错误'
  }
})
</script>

<template>
  <div class="dashboard">
    <section class="welcome-panel">
      <div>
        <div class="section-kicker"><span></span>阶段成果总览</div>
        <h1>项目工作台</h1>
        <p>将需求、数据、模型、芯片和真实设备组织为可追溯、可验证、可交付的 AI 工程闭环。</p>
      </div>
      <div class="welcome-actions">
        <a class="button button-primary" href="/docs" target="_blank" rel="noreferrer">查看 API 文档 <span>↗</span></a>
        <button class="button button-secondary" type="button" disabled title="身份认证接入后开放">新建项目</button>
      </div>
    </section>

    <section class="overview-grid" aria-label="平台能力概览">
      <article v-for="item in overview" :key="item.label" class="metric-card">
        <div class="metric-top">
          <span class="metric-icon" :class="`tone-${item.tone}`">{{ item.icon }}</span>
          <span class="roadmap-tag" :class="{ ready: item.status === '基础可用' }">{{ item.status }}</span>
        </div>
        <div class="metric-value">{{ item.value }}</div>
        <h2>{{ item.label }}</h2>
        <p>{{ item.detail }}</p>
      </article>
    </section>

    <section class="content-grid">
      <article class="panel pipeline-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-label">PLATFORM FLOW</span>
            <h2>AI 工程交付闭环</h2>
          </div>
          <span class="truthful-note">模块入口 · 规划中</span>
        </div>
        <div class="pipeline-grid">
          <div v-for="stage in pipeline" :key="stage.name" class="pipeline-stage" data-testid="pipeline-stage">
            <div class="stage-number">{{ stage.icon }}</div>
            <div>
              <h3>{{ stage.name }}</h3>
              <p>{{ stage.description }}</p>
              <span class="stage-status">规划中</span>
            </div>
          </div>
        </div>
      </article>

      <article class="panel health-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-label">RUNTIME</span>
            <h2>系统运行状态</h2>
          </div>
          <span class="live-indicator"><i></i>实时</span>
        </div>

        <div v-if="!health && !error" class="health-loading">
          <a-skeleton active :paragraph="{ rows: 3 }" />
        </div>
        <a-alert v-else-if="error" type="warning" :message="`API 未连接：${error}`" show-icon />
        <div v-else class="health-content">
          <div class="health-score">
            <div class="health-ring"><span>100</span><small>服务状态</small></div>
            <div>
              <strong>运行正常</strong>
              <p>核心 API 已通过实时健康检查</p>
            </div>
          </div>
          <dl class="health-details">
            <div><dt>服务标识</dt><dd>{{ health?.service }}</dd></div>
            <div><dt>当前版本</dt><dd>v{{ health?.version }}</dd></div>
            <div><dt>部署环境</dt><dd>Local Demo</dd></div>
          </dl>
        </div>
      </article>
    </section>

    <section class="panel milestone-panel">
      <div class="panel-heading">
        <div>
          <span class="panel-label">MILESTONE</span>
          <h2>当前建设进度</h2>
        </div>
        <span class="phase-badge light">M0D-02</span>
      </div>
      <div class="progress-list">
        <div v-for="(item, index) in progress" :key="item.title" class="progress-item">
          <span class="progress-marker" :class="{ done: item.status === '已完成', active: item.status === '进行中' }">{{ index + 1 }}</span>
          <div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.detail }}</p>
          </div>
          <span class="progress-status" :class="{ done: item.status === '已完成', active: item.status === '进行中' }">{{ item.status }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

