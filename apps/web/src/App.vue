<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useBrowserSession } from './auth'

const session = useBrowserSession()
onMounted(() => session.loadSession())

const navigation = [
  { label: '工作台', icon: '⌂', active: true },
  { label: '组织与项目', icon: '◇', status: '基础' },
  { label: '数据资产', icon: '▤', status: '规划中' },
  { label: '智能标注', icon: '⌖', status: '规划中' },
  { label: '训练中心', icon: '↗', status: '规划中' },
  { label: '模型仓库', icon: '⬡', status: '规划中' },
  { label: '设备与部署', icon: '◫', status: '规划中' },
  { label: '系统管理', icon: '⚙', status: '基础' },
]
</script>

<template>
  <div class="console-shell">
    <aside class="sidebar">
      <div class="logo-block">
        <div class="logo-mark">YJ</div>
        <div>
          <strong>AI 工程化平台</strong>
          <span>Engineering Console</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="平台主导航">
        <a
          v-for="item in navigation"
          :key="item.label"
          class="nav-item"
          :class="{ active: item.active }"
          href="#"
          :aria-current="item.active ? 'page' : undefined"
          @click.prevent
        >
          <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="item.status" class="nav-status">{{ item.status }}</span>
        </a>
      </nav>

      <div class="sidebar-footer">
        <span class="environment-dot" aria-hidden="true"></span>
        <div>
          <strong>内部演示环境</strong>
          <span>仅限可信局域网</span>
        </div>
      </div>
    </aside>

    <section class="console-main">
      <header class="topbar">
        <div>
          <p class="topbar-eyebrow">AI Engineering &amp; Delivery</p>
          <strong>多模型 · 多芯片 · 真实设备验证</strong>
        </div>
        <div class="topbar-actions">
          <span class="phase-badge">M0D · Phase 1</span>
          <div v-if="session.user.value" class="session-actions">
            <div class="user-avatar" aria-label="当前用户">{{ session.user.value.displayName.slice(0, 2) }}</div>
            <button type="button" class="button button-secondary" @click="session.logout()">退出</button>
          </div>
          <button v-else type="button" class="button button-primary" :disabled="session.loading.value" @click="session.login()">
            登录
          </button>
        </div>
      </header>
      <main class="app-content">
        <RouterView />
      </main>
    </section>
  </div>
</template>

