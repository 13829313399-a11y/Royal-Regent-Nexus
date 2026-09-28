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
void router.isReady().then(() => app.mount('#app'))
