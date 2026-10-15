<script setup lang="ts">
import { AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogOverlay, AlertDialogPortal, AlertDialogRoot, AlertDialogTitle } from 'reka-ui'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ cancel: []; discard: [] }>()
</script>

<template>
  <AlertDialogRoot :open="open" @update:open="!$event && emit('cancel')">
    <AlertDialogPortal>
      <AlertDialogOverlay class="quote-leave-overlay" />
      <AlertDialogContent class="quote-leave-dialog">
        <AlertDialogTitle class="quote-leave-title">报价设置有未保存修改</AlertDialogTitle>
        <AlertDialogDescription class="quote-leave-description">分段码数、倍率、杂项或汇率已调整。可以继续编辑并保存，也可以不保存本次报价设置后离开；已经保存的报价资料会保留。</AlertDialogDescription>
        <footer>
          <button type="button" class="discard" @click="emit('discard')">不保存并离开</button>
          <AlertDialogCancel class="cancel" @click="emit('cancel')">继续编辑</AlertDialogCancel>
        </footer>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>

<style scoped>
.quote-leave-overlay{position:fixed;inset:0;z-index:1100;background:rgb(15 23 42/.46)}
.quote-leave-dialog{position:fixed;z-index:1101;left:50%;top:50%;transform:translate(-50%,-50%);box-sizing:border-box;width:min(480px,calc(100vw - 32px));border:1px solid #cbd5e1;border-radius:16px;background:#fff;padding:24px;box-shadow:0 28px 70px rgb(15 23 42/.3)}
.quote-leave-title{margin:0;color:#0f172a;font-size:18px;font-weight:800}
.quote-leave-description{margin:12px 0 24px;color:#475569;font-size:14px;line-height:1.7}
.quote-leave-dialog footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px}
.quote-leave-dialog button{min-height:38px;border:1px solid #cbd5e1;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:700;cursor:pointer}
.quote-leave-dialog .discard{background:#fff;color:#b91c1c;border-color:#fecaca}
.quote-leave-dialog .cancel{background:#0f766e;color:#fff;border-color:#0f766e}
.quote-leave-dialog button:focus-visible{outline:3px solid #5eead4;outline-offset:3px}
</style>
