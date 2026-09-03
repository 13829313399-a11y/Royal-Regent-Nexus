import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { createPinia } from 'pinia'
import { installUnauthorizedSessionHandler } from '@/lib/sessionExpiryHandler'
import { router } from '@/router'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
installUnauthorizedSessionHandler(router, pinia)

// Resolve the initial session and factory before rendering the shared shell.
void router.isReady().then(() => app.mount('#app'))
