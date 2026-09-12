<script setup lang="ts">
import { computed, useId } from 'vue'
import type { Entity } from '../workspace'
const props=defineProps<{steps:Entity[];graph?:boolean}>(),arrow=useId()
const layout=computed(()=>{
  const ordered=[...props.steps].sort((a,b)=>Number(a.sequence)-Number(b.sequence));const steps:Entity[]=ordered.map((step,i)=>({...step,predecessors:props.graph?step.predecessors:(i?[ordered[i-1]!.id]:[])}));
  const levels=new Map<string,number>(),pending=[...steps],nodes:{id:string;name:string;x:number;y:number;wait:string;parents:string[]}[]=[]
  while(pending.length){const index=pending.findIndex(v=>(v.predecessors as string[]||[]).every(id=>levels.has(id)));if(index<0)break;const item=pending.splice(index,1)[0]!;const parents=(item.predecessors as string[]||[]);levels.set(item.id,parents.length?1+Math.max(...parents.map(id=>levels.get(id)!)):0)}
  const slots=new Map<number,number>()
  for(const item of steps){const level=levels.get(item.id)??0,slot=slots.get(level)??0;slots.set(level,slot+1);nodes.push({id:item.id,name:String(item.name),x:20+level*210,y:20+slot*100,wait:String(item.wait_hours??0),parents:item.predecessors as string[]||[]})}
  const byId=new Map(nodes.map(n=>[n.id,n]))
  return {nodes,width:Math.max(400,...nodes.map(n=>n.x+190)),height:Math.max(110,...nodes.map(n=>n.y+90)),edges:nodes.flatMap(to=>to.parents.flatMap(id=>{const from=byId.get(id);return from?[{id:id+to.id,from,to}]:[]}))}
})
</script>
<template><div class="process-graph" tabindex="0" aria-label="工艺依赖图，可横向滚动"><svg role="img" aria-label="工艺节点与前置依赖，汇合节点须完成全部前置工序" :width="layout.width" :height="layout.height"><defs><marker :id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs><path v-for="edge in layout.edges" :key="edge.id" :d="`M${edge.from.x+170},${edge.from.y+32} C${edge.from.x+190},${edge.from.y+32} ${edge.to.x-20},${edge.to.y+32} ${edge.to.x},${edge.to.y+32}`" fill="none" stroke="currentColor" stroke-width="1.5" :marker-end="`url(#${arrow})`" /><g v-for="node in layout.nodes" :key="node.id" :transform="`translate(${node.x},${node.y})`"><title>{{ node.name }}，放行等待 {{ node.wait }} 小时</title><rect width="170" height="64" rx="9" /><text x="12" y="25">{{ node.name.length>11?node.name.slice(0,10)+'…':node.name }}</text><text x="12" y="46" class="secondary">放行等待 {{ node.wait }} 小时</text></g></svg></div></template>
<style scoped>.process-graph{overflow:auto;margin:16px 0;background:var(--secondary);border-radius:10px;color:var(--primary)}rect{fill:var(--card);stroke:var(--border)}text{fill:var(--foreground);font-size:13px}.secondary{fill:var(--muted-foreground);font-size:11px}</style>
