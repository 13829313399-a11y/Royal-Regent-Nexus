import type { RouteRecordRaw } from 'vue-router'
import { SPRAY_BASE, isSprayFactory, sprayEnabled } from './contracts'
const meta={fullPage:true,requiresAuth:true,permissions:['spray_ops:read'],enforcePermissions:true,strictPermissions:true,permissionDepartment:'production'}
export const sprayProductionRoutes:RouteRecordRaw[]=[{
 path:SPRAY_BASE,component:()=>import('./SprayWorkspaceShell.vue'),meta:{...meta,title:'喷油生产管理'},
 beforeEnter:to=>sprayEnabled()&&isSprayFactory(to.query.factory)?true:{path:'/modules/production',query:to.query,replace:true},
 children:[
  {path:'',redirect:to=>({path:SPRAY_BASE+'/overview',query:to.query})},
  {path:'overview',component:()=>import('./pages/OverviewPage.vue'),meta:{...meta,title:'喷油 · 工作总览'}},
  {path:'planning',component:()=>import('./pages/SchedulePage.vue'),meta:{...meta,title:'喷油 · 计划调度'}},
  {path:'planning/demands',component:()=>import('./pages/DemandPage.vue'),meta:{...meta,title:'喷油 · 需求池'}},
  {path:'execution',component:()=>import('./pages/ProductionPage.vue'),meta:{...meta,title:'喷油 · 现场执行'}},
  {path:'handover',component:()=>import('./pages/HandoverPage.vue'),meta:{...meta,title:'喷油 · 胶件与交收'}},
  {path:'materials',component:()=>import('./pages/MaterialsPage.vue'),meta:{...meta,title:'喷油 · 油漆与采购'}},
  {path:'finance',component:()=>import('./pages/EconomicsPage.vue'),meta:{...meta,title:'喷油 · 经营与月结'}},
  {path:'finance/settlements/:id?',component:()=>import('./pages/SettlementPage.vue'),meta:{...meta,title:'喷油 · 委托方月结'}},
  {path:'master',component:()=>import('./pages/ConfigurationPage.vue'),meta:{...meta,title:'喷油 · 基础资料'}},
  {path:'imports',component:()=>import('./pages/ImportsPage.vue'),meta:{...meta,title:'喷油 · 导入中心'}},
  {path:'activity',component:()=>import('./pages/ActivityPage.vue'),meta:{...meta,title:'喷油 · 操作记录'}},
 ],
}]
