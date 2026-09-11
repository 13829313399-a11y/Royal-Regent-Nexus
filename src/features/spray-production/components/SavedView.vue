<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
const props=defineProps<{page:string;value:Record<string,unknown>}>()
const emit=defineEmits<{restore:[value:Record<string,unknown>]}>()
const s=useSprayWorkspace(),name=ref('常用视图')
onMounted(()=>s.loadPreferences())
</script>
<template><div class="spray-actions my-3"><input v-model="name" aria-label="保存视图名称" placeholder="视图名称" /><Button variant="outline" :disabled="s.busy||!name" @click="s.savePreference('view',page+':'+name,value)">保存当前视图</Button><select aria-label="恢复保存视图" @change="emit('restore',s.preferences.find(v=>v.id===($event.target as HTMLSelectElement).value)?.payload as Record<string,unknown>)"><option value="">恢复已保存视图</option><option v-for="view in s.preferences.filter(v=>v.kind==='view'&&String(v.name).startsWith(page+':'))" :key="view.id" :value="view.id">{{ String(view.name).slice(page.length+1) }}</option></select></div></template>
