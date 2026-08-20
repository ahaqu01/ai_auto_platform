import 'ant-design-vue/dist/reset.css'

import {
  Alert,
  Badge,
  Card,
  Descriptions,
  Layout,
  Skeleton,
} from 'ant-design-vue'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)
app.use(createPinia()).use(router)
for (const component of [Alert, Badge, Card, Descriptions, Layout, Skeleton]) {
  app.use(component)
}
app.mount('#app')
