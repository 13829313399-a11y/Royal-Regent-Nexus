import type { RouteRecordRaw } from 'vue-router'
import { UV_BASE, UV_FACTORY } from './contracts'
const meta={fullPage:true,requiresAuth:true,permissions:['uv_ops:read'],enforcePermissions:true,strictPermissions:true,permissionFactoryId:UV_FACTORY,permissionDepartment:'production'}
export const uvOperationsRoutes: RouteRecordRaw[] = [{
  path:UV_BASE, component:()=>import('./UvWorkspaceShell.vue'), meta:{...meta,title:'UV 打印管理'},
  beforeEnter:to=>to.query.factory===UV_FACTORY ? true : {path:'/modules/production',query:{factory:String(to.query.factory??'group')},replace:true},
  children:[
    {path:'',redirect:to=>({path:UV_BASE+'/live',query:to.query})},
    {path:'live',component:()=>import('./pages/LivePage.vue'),meta:{...meta,title:'UV · 机台现场'}},
    {path:'planning',component:()=>import('./pages/PlanningPage.vue'),meta:{...meta,title:'UV · 任务与排程'}},
    {path:'shifts',component:()=>import('./pages/ShiftsPage.vue'),meta:{...meta,title:'UV · 班次与品质'}},
    {path:'materials',component:()=>import('./pages/MaterialsPage.vue'),meta:{...meta,title:'UV · 材料与设备'}},
    {path:'analytics',component:()=>import('./pages/AnalyticsPage.vue'),meta:{...meta,title:'UV · 效益与核算'}},
    {path:'settings',component:()=>import('./pages/SettingsPage.vue'),meta:{...meta,title:'UV · 基础设置'}},
    {path:'imports',component:()=>import('./pages/ImportsPage.vue'),meta:{...meta,title:'UV · 导入与导出'}},
  ],
}]
