import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import B1aFreshnessHarness from './B1aFreshnessHarness.vue'
import '../../injection-scheduling-v2.css'
import '../../styles/tokens.css'
import '../../styles/polish.css'
import '../../styles/motion.css'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', name: 'dashboard', component: { template: '<div />' } }],
})

createApp(B1aFreshnessHarness).use(createPinia()).use(router).mount('#app')
