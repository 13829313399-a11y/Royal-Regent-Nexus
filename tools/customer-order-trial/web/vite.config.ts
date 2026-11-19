import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

const root = fileURLToPath(new URL('.', import.meta.url))
const repository = path.resolve(root, '../../..')
export const aliases = [{ find: /^@\/lib\/http$/, replacement: path.join(root, 'src/api.ts') }, { find: '@', replacement: path.join(repository, 'src') }]
const reused = ['src/components/common/PageHeader.vue', 'src/components/common/SectionPanel.vue',
  'src/components/common/StatusPill.vue', 'src/components/ui/button/Button.vue',
  'src/components/ui/button/index.ts', 'src/lib/utils.ts', 'src/lib/customerOrderReconciliation.ts', 'src/style.css',
  'src/components/modules/sales/customer-order-center/CustomerOrderLedger.vue',
  'src/components/modules/sales/customer-order-center/CustomerOrderHistoryImport.vue',
  'src/components/modules/sales/customer-order-center/CustomerOrderSchedule.vue',
  'src/components/modules/sales/customer-order-center/CasdonWorkbookTools.vue',
  'src/api/customerOrderSchedule.ts', 'src/api/casdonWorkbook.ts',
  'src/api/customerOrderLedger.ts', 'src/api/customerOrderHistory.ts', 'src/composables/useDialogFocus.ts']
const greenToysReused = ['src/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue',
  'src/api/customerOrder.ts', 'src/features/cutting-operations/poTestBridge.ts', 'src/styles/customer-order-center-shell.css']
const contracts = ['backend/app/services/customer_order_ledger.py', 'backend/app/services/huaxing_order_legacy/edu_schedule.py', 'src/types/customerOrder.ts', 'src/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue']
export default defineConfig(({ mode }) => {
 const greenToys = mode === 'green-toys'
 const sources = greenToys ? [...reused, ...greenToysReused] : reused
 return {
  root, envDir: false, envPrefix: '__TRIAL_INTERNAL_UNUSED_', publicDir: false, base: '/', cacheDir: path.resolve(root, '../build/vite-cache'),
  plugins: [vue(), tailwindcss(), {
    name: 'order-trial-source-boundary',
    transformIndexHtml: {
      order: 'pre',
      handler(html) { return greenToys ? html.replace('/src/main.ts', '/src/greenToysMain.ts') : html },
    },
    generateBundle() {
      for (const id of this.getModuleIds()) {
        const source = id.split('?')[0]!
        if (source.startsWith(path.join(repository, 'src') + path.sep)) {
          const relative = path.relative(repository, source).split(path.sep).join('/')
          if (!sources.includes(relative)) this.error(`Unexpected ERP source in order trial: ${relative}`)
        }
      }
      this.emitFile({ type: 'asset', fileName: 'source-manifest.json', source: JSON.stringify({
        application: 'customer-order-trial',
        sources: sources.map(file => ({ path: file, sha256: createHash('sha256').update(readFileSync(path.join(repository, file))).digest('hex') })),
        contracts: contracts.map(file => ({ path: file, sha256: createHash('sha256').update(readFileSync(path.join(repository, file))).digest('hex') })),
      }, null, 2) })
    },
  }],
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api') },
  resolve: { alias: [...(greenToys ? [{ find: /^@\/api\/customerOrder$/, replacement: path.join(root, 'src/greenToysOrderApi.ts') }] : []), ...aliases] },
  build: { outDir: path.resolve(root, greenToys ? '../build/web-green-toys' : '../build/web'), emptyOutDir: true, sourcemap: false },
 }
})
