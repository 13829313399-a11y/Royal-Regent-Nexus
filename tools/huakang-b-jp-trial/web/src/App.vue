<script setup lang="ts">
import HuakangBJPIntake from '@/components/modules/sales/customer-order-center/HuakangBJPIntake.vue'
</script>

<template>
  <main class="trial-shell">
    <aside class="trial-notice" aria-label="本地试用说明">
      <strong>华康B · 本地试用版</strong>
      <p>数据仅保存在本机，不连接线上系统。每台电脑独立编号，试用结果请勿作为正式编号使用。</p>
      <p>首次使用可上传随包的“演示资料”；正式核对时请换成自己的排期参照、货价表和邮件。</p>
    </aside>
    <HuakangBJPIntake factory-id="huakang-b" />
  </main>
</template>

<style scoped>
.trial-shell {
  max-width: 1720px;
  min-width: 0;
  margin: 0 auto;
  padding: clamp(16px, 2.5vw, 36px);
}
.trial-notice {
  margin-bottom: 24px;
  padding: 16px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  color: var(--foreground);
  box-shadow: 0 1px 2px oklch(0.2 0.025 240 / 4%);
}
.trial-notice strong { color: var(--primary); font-size: 14px; }
.trial-notice p { margin: 6px 0 0; color: var(--muted-foreground); font-size: 13px; line-height: 1.7; }
@media (max-width: 640px) {
  .trial-notice { padding: 14px 16px; margin-bottom: 20px; }
}
</style>
