import { useEffect, useRef, useState } from 'react'
import { ProLayout } from '@ant-design/pro-components'
import { Alert, App, Badge, Button, Space, Tag, Typography } from 'antd'
import { Link, Outlet, useBlocker, useLocation, useNavigate } from 'react-router-dom'
import { BellOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { canManageLegacyDatabase, canManageLegacyUsers, isNexusSessionLocked, moduleForPath } from '../auth/permissions'
import { workspaceMenu } from './workspaceMenu'
import type { MenuDataItem } from '@ant-design/pro-components'
import { nexusBase, nexusFactory, nexusFactoryName } from '../deployment'
import { confirmNavigation, navigationState } from '../auth/navigationState'
import { validateExportSession } from '../auth/validateExportSession'
import './AppLayout.css'

interface AlertStats {
  pending_critical: number
  pending_warning: number
  pending_normal: number
  pending_total: number
}

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuCollapsed, setMenuCollapsed] = useState(() => window.matchMedia('(max-width: 767px)').matches)
  useEffect(() => {
    if (window.matchMedia('(max-width: 767px)').matches) setMenuCollapsed(true)
  }, [location.pathname])
  const auth = useAuth()
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    const state = navigationState()
    return !!auth.session?.nexus && currentLocation.pathname !== nextLocation.pathname && (state.dirty || state.pending)
  })
  useEffect(() => {
    if (blocker.state === 'blocked') {
      let active = true
      void confirmNavigation().then(leave => {
        if (!active) return
        if (leave) blocker.proceed()
        else blocker.reset()
      })
      return () => { active = false }
    }
  }, [blocker])
  const { message } = App.useApp()
  const currentModule = moduleForPath(location.pathname)
  const readOnly = !!currentModule && !auth.canEdit(currentModule.key)
  const approvedExport = useRef<HTMLElement | null>(null)
  const exportChecking = useRef(false)
  const routes: MenuDataItem[] = workspaceMenu(auth.canAccess)
  if (canManageLegacyUsers(auth.session)) routes.push({ path: '/users', name: '账户管理' })
  if (canManageLegacyDatabase(auth.session)) routes.push({ path: '/db-admin', name: '数据库管理' })

  // ── 物料提醒桌面通知状态 ──
  const [alertStats, setAlertStats] = useState<AlertStats | null>(null)
  const notifiedRef = useRef<string>('')  // 记录上次已通知的内容摘要，避免重复弹窗
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const canCheckAlerts = auth.canAccess('purchase')
  const embedded = !!nexusBase() && window.parent !== window
  // Only the current, same-origin host may operate this document's navigation.
  useEffect(() => {
    if (!embedded) return
    let id = ''
    const publish = () => {
      if (!id) return
      const enabled = canCheckAlerts && !isNexusSessionLocked()
      window.parent.postMessage({ type: 'nexus-shipping-toolbar-state', factory: nexusFactory(), id,
        alertsEnabled: enabled, count: enabled ? alertStats?.pending_total || 0 : 0 }, window.location.origin)
    }
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== window.parent ||
          event.data?.type !== 'nexus-shipping-toolbar' || event.data.factory !== nexusFactory()) return
      if (event.data.action === 'connect' && typeof event.data.id === 'string' && event.data.id) {
        id = event.data.id; publish(); return
      }
      if (!id || event.data.id !== id || isNexusSessionLocked()) return
      if (event.data.action === 'alerts' && canCheckAlerts) navigate('/material-alerts')
      if (event.data.action === 'menu') setMenuCollapsed(value => !value)
    }
    window.addEventListener('message', receive)
    window.parent.postMessage({ type: 'nexus-shipping-toolbar-ready', factory: nexusFactory() }, window.location.origin)
    return () => {
      window.removeEventListener('message', receive)
      if (id) window.parent.postMessage({ type: 'nexus-shipping-toolbar-state', factory: nexusFactory(), id,
        active: false, alertsEnabled: false, count: 0 }, window.location.origin)
    }
  }, [embedded, canCheckAlerts, alertStats, navigate])

  // 请求浏览器通知权限
  useEffect(() => {
    if (!canCheckAlerts) return
    if ('Notification' in window && Notification.permission === 'default') {
      // 延迟3秒再请求，避免刚打开页面就弹权限框影响体验
      const t = setTimeout(() => {
        Notification.requestPermission().then(perm => {
          console.log('[MaterialAlerts] Notification permission:', perm)
        })
      }, 3000)
      return () => clearTimeout(t)
    }
  }, [canCheckAlerts])

  // 定时轮询提醒统计
  useEffect(() => {
    if (!canCheckAlerts) return

    const checkAlerts = async () => {
      try {
        const resp = await api.get('/material-alerts/stats')
        const stats: AlertStats = resp.data
        setAlertStats(stats)

        // 决定是否弹出桌面通知
        const critical = stats.pending_critical || 0
        const warning = stats.pending_warning || 0
        const totalUrgent = critical + warning

        if (totalUrgent === 0) return
        if (!('Notification' in window) || Notification.permission !== 'granted') return

        // 生成本次内容摘要，与上次比较避免重复弹窗
        const digest = `${critical}|${warning}|${stats.pending_total}`
        if (digest === notifiedRef.current) return
        notifiedRef.current = digest

        // 构建通知内容
        const title = critical > 0
          ? `🔴 物料追踪：${critical} 项超急提醒`
          : `🟡 物料追踪：${warning} 项紧急提醒`

        const bodyLines: string[] = []
        if (critical > 0) bodyLines.push(`超急 ${critical} 项`)
        if (warning > 0) bodyLines.push(`紧急 ${warning} 项`)
        bodyLines.push('点击查看详情并处理')

        const n = new Notification(title, {
          body: bodyLines.join('，'),
          icon: '/favicon.svg',
          tag: 'material-alerts-' + Date.now(),
          requireInteraction: critical > 0, // 超急时通知不自动消失
        })

        n.onclick = () => {
          window.focus()
          navigate('/material-alerts')
          n.close()
        }
      } catch (err) {
        // 静默失败，不打扰用户
        console.warn('[MaterialAlerts] check failed:', err)
      }
    }

    // 首次立即检查
    checkAlerts()

    // 每 5 分钟检查一次
    timerRef.current = setInterval(checkAlerts, 5 * 60 * 1000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [canCheckAlerts, navigate])

  function blockReadOnlyAction(e: React.MouseEvent<HTMLDivElement>) {
    const el = (e.target as HTMLElement).closest('button,a,[role="button"]') as HTMLElement | null
    const text = (el?.innerText || el?.getAttribute('aria-label') || '').trim()
    if (readOnly && el && /新增|添加|编辑|删除|保存|上传|导入|生成|合并|清空|停用|启用|标记|取消|套用|回填|重编号/.test(text)) {
      e.preventDefault(); e.stopPropagation()
      message.warning('当前账户在此模块为只读权限')
      return
    }
    if (auth.session?.nexus && el && /导出|打印/.test(text)) {
      if (approvedExport.current === el) { approvedExport.current = null; return }
      e.preventDefault(); e.stopPropagation()
      if (exportChecking.current) return
      exportChecking.current = true
      void validateExportSession().then(ok => {
        if (ok && el.isConnected) { approvedExport.current = el; el.click(); approvedExport.current = null }
      }).finally(() => { exportChecking.current = false })
    }
  }
  return (
    <ProLayout
      className={`indonesia-workspace${embedded ? ' indonesia-workspace-embedded' : ''}`}
      title="印尼物料管理系统"
      logo={false}
      layout={embedded ? 'side' : 'mix'}
      headerRender={embedded ? false : undefined}
      menuHeaderRender={embedded ? false : undefined}
      collapsed={menuCollapsed}
      onCollapse={setMenuCollapsed}
      location={{ pathname: location.pathname }}
      route={{ path: '/', routes }}
      menu={{ defaultOpenAll: false }}
      menuProps={{ inlineIndent: 12 }}
      menuItemRender={(item, dom) => item.children?.length || !item.path ? dom : <Link to={item.path}>{dom}</Link>}
      headerContentRender={() => (
        <Space>
          {auth.session?.nexus && <Tag>{nexusFactoryName()}</Tag>}
          {readOnly && <Tag color="orange">当前模块只读</Tag>}
        </Space>
      )}
      actionsRender={() => embedded ? [] : [
        canCheckAlerts ? (
          <Badge key="alerts" count={alertStats?.pending_total || 0} size="small" overflowCount={99}>
            <Button type="text" icon={<BellOutlined />} onClick={() => navigate('/material-alerts')}>物料提醒</Button>
          </Badge>
        ) : null,
        <Typography.Text key="user" className="indonesia-account-name" title={auth.session?.displayName}>{auth.session?.displayName}</Typography.Text>,
        canManageLegacyUsers(auth.session) ? <Link key="users" to="/users">账户管理</Link> : null,
        <Button key="logout" size="small" onClick={auth.logout}>{auth.session?.nexus ? '返回业务部' : '退出登录'}</Button>,
      ]}
    >
      {readOnly && <Alert type="warning" showIcon message="只读权限：可以查看和搜索，但不能新增、修改或删除数据。" style={{ marginBottom: 12 }} />}
      <div onClickCapture={blockReadOnlyAction}><Outlet /></div>
    </ProLayout>
  )
}
