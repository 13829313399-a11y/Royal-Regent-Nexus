import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

const webRoot = fileURLToPath(new URL('.', import.meta.url))
const repository = path.resolve(webRoot, '../../..')
export const aliases = [
  { find: /^@\/lib\/http$/, replacement: path.join(webRoot, 'src/http.ts') },
  { find: '@', replacement: path.join(repository, 'src') },
]
const reused = [
  'src/components/modules/sales/customer-order-center/HuakangBJPIntake.vue',
  'src/api/huakangBJP.ts',
  'src/components/common/PageHeader.vue',
  'src/components/common/SectionPanel.vue',
  'src/components/common/StatusPill.vue',
  'src/components/ui/button/Button.vue',
  'src/components/ui/button/index.ts',
  'src/lib/utils.ts',
  'src/style.css',
]

export default defineConfig({
  root: webRoot,
  envDir: false,
  publicDir: false,
  cacheDir: path.resolve(webRoot, '../build/vite-cache'),
  base: '/',
  plugins: [vue(), tailwindcss(), {
    name: 'jp-trial-source-boundary',
    generateBundle() {
      for (const id of this.getModuleIds()) {
        const source = id.split('?')[0]!
        if (source.startsWith(path.join(repository, 'src') + path.sep)) {
          const relative = path.relative(repository, source).split(path.sep).join('/')
          if (!reused.includes(relative)) this.error(`Unexpected ERP source in JP trial: ${relative}`)
        }
      }
      this.emitFile({ type: 'asset', fileName: 'source-manifest.json', source: JSON.stringify({
        application: 'huakang-b-jp-trial',
        sources: reused.map(file => ({ path: file, sha256: createHash('sha256').update(readFileSync(path.join(repository, file))).digest('hex') })),
      }, null, 2) })
    },
  }],
  resolve: { alias: aliases },
  build: { outDir: path.resolve(webRoot, '../build/web'), emptyOutDir: true, sourcemap: false },
})
