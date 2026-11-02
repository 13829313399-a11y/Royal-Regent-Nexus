<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { cuttingResourceRecovery } from '@/router'
const { failure, feedback, reloading, reload } = cuttingResourceRecovery
</script>

<template>
  <aside v-if="failure" class="cutting-resource-recovery" role="alert" aria-labelledby="cutting-resource-title">
    <h2 id="cutting-resource-title">裁床页面未完整加载</h2>
    <p>脚本或样式读取失败，当前页面未完成更新。请恢复网络后重新加载目标页面。</p>
    <p>目标：{{ failure.title }} · 华康 C</p>
    <p>如有未保存内容或待核实操作，请先处理；重新加载后会重新核验登录与访问权限。</p>
    <Button type="button" variant="outline" :disabled="reloading" @click="reload">重新加载目标页面</Button>
    <p v-if="feedback" role="status">{{ feedback }}</p>
  </aside>
</template>

<style scoped>
.cutting-resource-recovery { position:fixed; z-index:100; right:20px; bottom:20px; max-width:420px; width:calc(100vw - 24px); max-height:calc(100dvh - 24px); overflow:auto; padding:20px; border:1px solid var(--border); border-radius:12px; background:var(--card); color:var(--foreground); box-shadow:0 8px 28px #173c2926; font-size:14px; line-height:1.6; }
.cutting-resource-recovery h2 { margin:0 0 8px; font-size:17px; font-weight:600; }
.cutting-resource-recovery p { margin:8px 0; overflow-wrap:anywhere; }
.cutting-resource-recovery :focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
@media (max-width:639px) { .cutting-resource-recovery { right:12px; bottom:12px; padding:16px; } }
</style>
