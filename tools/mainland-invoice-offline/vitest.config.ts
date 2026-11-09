import { defineConfig, mergeConfig } from 'vitest/config'
import appConfig from './vite.config'
export default mergeConfig(appConfig, defineConfig({
  cacheDir: '.cache/vite',
  test: { environment: 'jsdom', include: ['scripts/**/*.test.{js,jsx}'], fileParallelism: false },
}))
