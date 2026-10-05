import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { copyFileSync, mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { browserRuntimeBoundaryPlugin } from '../../scripts/vite-browser-runtime-boundary';
import { MODEL_PACKAGE } from '@shinobu/model-manifest';

const modelManifest = MODEL_PACKAGE;
const rrIntegration = process.env.VITE_RR_INTEGRATION === 'true';

const isolationHeaders = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
  'Cross-Origin-Resource-Policy': 'same-origin',
};

export default defineConfig({
  base: rrIntegration ? '/image-translation/' : '/',
  plugins: [
    browserRuntimeBoundaryPlugin(),
    react(),
    {
      name: 'shinobu-pages-config',
      transformIndexHtml: { order: 'pre', handler(html) {
        if (!rrIntegration) return html;
        return html.replace(/\s*<link rel="manifest"[^>]*>/u, '')
          .replace('/src/main.tsx', '/src/server/main.tsx')
          .replace('Shinobu Translator Web，在浏览器本地处理漫画图片。', '图片与 PDF 原位翻译，由网站服务器统一处理。')
          .replace('<title>Shinobu Translator Web</title>', '<title>图片与 PDF 翻译 · Royal Regent Nexus</title>');
      } },
      closeBundle() {
        for (const asset of modelManifest.assets) {
          rmSync(
            resolve(import.meta.dirname, 'dist', 'models', asset.path),
            { force: true },
          );
        }
        copyFileSync(
          resolve(import.meta.dirname, '_headers'),
          resolve(import.meta.dirname, 'dist', '_headers'),
        );
        for (const documentName of (rrIntegration ? ['LICENSE', 'THIRD_PARTY_DEPENDENCIES.json', 'THIRD_PARTY_NOTICES.md'] : [
          'LICENSE',
          'PRIVACY_POLICY.md',
          'THIRD_PARTY_DEPENDENCIES.json',
          'THIRD_PARTY_NOTICES.md',
          'WEB_PUBLIC_BETA_RELEASE_NOTES.md',
          'WEB_TROUBLESHOOTING.md',
        ])) {
          copyFileSync(
            resolve(import.meta.dirname, '../..', documentName),
            resolve(import.meta.dirname, 'dist', documentName),
          );
        }
        if (rrIntegration) {
          mkdirSync(resolve(import.meta.dirname, 'dist/icons'), { recursive: true });
          for (const name of ['icon32.png', 'icon128.png']) {
            copyFileSync(
              resolve(import.meta.dirname, '../../public/icons', name),
              resolve(import.meta.dirname, 'dist/icons', name),
            );
          }
        }
      },
    },
  ],
  publicDir: rrIntegration ? false : '../../public',
  worker: {
    format: 'es',
    plugins: () => [
      browserRuntimeBoundaryPlugin(),
    ],
  },
  server: {
    port: 5174,
    headers: isolationHeaders,
  },
  preview: {
    port: 4174,
    headers: isolationHeaders,
  },
});
