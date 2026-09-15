<script setup lang="ts">
import type { Capabilities } from '@/api/documentTools'
defineProps<{ availability?: Capabilities['translation']; compact?: boolean }>()
const options = defineModel<Record<string, unknown>>({ required: true })
</script>

<template>
  <div class="dt-translation-options">
    <div class="dt-translation-fields">
      <label>翻译方向<select v-model="options.translation_direction" aria-label="翻译方向">
        <option value="zh_to_en">中文 → 英文</option>
        <option value="en_to_zh">英文 → 中文</option>
      </select></label>
      <label>翻译方式<select v-model="options.translation_engine" aria-label="翻译方式" @change="options.glossary = ''">
        <option value="offline">离线翻译{{ !availability ? '（等待服务状态）' : availability.offline_available ? '' : '（未就绪）' }}</option>
        <option value="online">在线 AI 精译{{ !availability ? '（等待服务状态）' : availability.online_available ? '' : '（未配置）' }}</option>
      </select></label>
    </div>
    <p v-if="!availability">尚未获取翻译服务状态，请刷新服务；若后台版本较旧，请更新并重启 API 与文档处理服务。</p>
    <p v-else-if="options.translation_engine === 'online'">
      {{ availability?.online_available ? `已连接 · ${availability.online_model}` : '请管理员配置在线 AI 服务后使用。' }}
      文档文字将发送至已配置的 AI 服务；扫描 PDF 还会发送待识别图像。
    </p>
    <p v-else>{{ availability?.offline_available ? '使用服务器离线中英模型，文档内容不外发。' : '离线模型尚未就绪，请安装模型或选用已配置的在线 AI。' }}</p>
    <label v-if="!compact && options.translation_engine === 'online'">专业术语（可选）
      <textarea :value="String(options.glossary ?? '')" @input="options.glossary = ($event.target as HTMLTextAreaElement).value" aria-label="专业术语" rows="3" maxlength="4000" placeholder="例如：啤工 = injection molding labor；客料 = customer-supplied material" />
      <small>填写约定译法，帮助保持文档术语一致。</small>
    </label>
  </div>
</template>

<style scoped>
.dt-translation-options { display: grid; gap: 10px; font-size: 13px; }
.dt-translation-fields { display: flex; flex-wrap: wrap; gap: 12px; }
label { display: grid; gap: 6px; flex: 1; min-width: 140px; }
select, textarea { width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--card); color: var(--foreground); }
p, small { color: var(--muted-foreground); font-size: 12px; line-height: 1.6; }
select:focus-visible, textarea:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
</style>
