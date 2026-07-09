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

app.mount('#app')
