<script setup lang="ts">
import { onMounted, ref } from 'vue'

type Health = { status: string; service: string; version: string }

const health = ref<Health | null>(null)
const error = ref('')

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
  <main class="hero">
    <p class="eyebrow">多模型 · 多芯片 · 真实设备验证</p>
    <h1>AI 工程化与交付平台</h1>
    <p class="summary">
      将需求、数据、模型、芯片和真实设备组织为可追溯、可验证、可交付的工程闭环。
    </p>
    <a-card class="status-card" title="开发环境状态">
      <a-skeleton v-if="!health && !error" active :paragraph="{ rows: 1 }" />
      <a-alert v-else-if="error" type="warning" :message="`API 未连接：${error}`" show-icon />
      <a-descriptions v-else :column="1" size="small">
        <a-descriptions-item label="服务">{{ health?.service }}</a-descriptions-item>
        <a-descriptions-item label="版本">{{ health?.version }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-badge status="success" text="运行正常" />
        </a-descriptions-item>
      </a-descriptions>
    </a-card>
  </main>
</template>

