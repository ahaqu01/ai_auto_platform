<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <a-layout class="app-shell">
    <a-layout-header class="app-header">
      <div class="brand">AI Engineering &amp; Delivery</div>
      <div class="phase">Phase 1</div>
    </a-layout-header>
    <a-layout-content class="app-content">
      <RouterView />
    </a-layout-content>
  </a-layout>
</template>

