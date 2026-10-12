import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { createPinia } from 'pinia'
import { installUnauthorizedSessionHandler } from '@/lib/sessionExpiryHandler'
import { router } from '@/router'
import { installIdentitySync } from '@/lib/identitySync'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
installUnauthorizedSessionHandler(router, pinia)
const stopIdentitySync = installIdentitySync(router, pinia)
if (import.meta.hot) import.meta.hot.dispose(stopIdentitySync)

// Resolve the initial session and factory before rendering the shared shell.
void router.isReady().then(() => app.mount('#app')).catch(() => {
  const message = document.getElementById('boot-message')
  const retry = document.getElementById('boot-retry')
  if (message) message.textContent = '暂时无法连接工作空间，请检查网络后重试'
  if (retry) retry.style.display = 'block'
})
