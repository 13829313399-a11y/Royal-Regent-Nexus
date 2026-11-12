import { lazy, Suspense } from 'react'
import { createBrowserRouter, createRoutesFromElements, RouterProvider, Navigate, Route, useLocation } from 'react-router-dom'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './layouts/AppLayout'
import { nexusBase, nexusBusinessUrl, publicBase } from './deployment'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { canManageLegacyDatabase, canManageLegacyUsers, sessionFingerprint, PERMISSION_MODULES, type ModuleKey } from './auth/permissions'

const CustomersPage    = lazy(() => import('./pages/CustomersPage'))
const DictionariesPage = lazy(() => import('./pages/DictionariesPage'))
const SupplierSummaryPage = lazy(() => import('./pages/SupplierSummaryPage'))
const ProductsPage     = lazy(() => import('./pages/ProductsPage'))
const ToolMaterialsPage = lazy(() => import('./pages/ToolMaterialsPage'))
const QuotesPage       = lazy(() => import('./pages/QuotesPage'))
const PurchasePage     = lazy(() => import('./pages/PurchasePage'))
const OutboundPage     = lazy(() => import('./pages/OutboundPage'))
const MoldingPosPage   = lazy(() => import('./pages/MoldingPosPage'))
const SchedulesPage    = lazy(() => import('./pages/SchedulesPage'))
const ShipmentsPage    = lazy(() => import('./pages/ShipmentsPage'))
const DbAdminPage      = lazy(() => import('./pages/DbAdminPage'))
const LoginPage        = lazy(() => import('./pages/LoginPage'))
const UsersPage        = lazy(() => import('./pages/UsersPage'))
const MaterialAlertsPage = lazy(() => import('./pages/MaterialAlertsPage'))

const Fallback = <div style={{ padding: 48, textAlign: 'center' }}><Spin /></div>

function RequireLogin({ children }: { children: React.ReactNode }) {
  const auth = useAuth()
  const location = useLocation()
  if (auth.loading) return Fallback
  if (!auth.session && nexusBase()) return <div role="alert" style={{ padding: 32 }}>
    当前 Nexus 会话或印尼走货权限不可用，请返回业务部重新进入。
    <a href={nexusBusinessUrl()} target="_top">返回业务部</a>
  </div>
  return auth.session ? <div key={sessionFingerprint(auth.session)} style={{ display: 'contents' }}>{children}</div> : <Navigate to="/login" state={{ from: location.pathname }} replace />
}

function ModuleRoute({ module, children }: { module: ModuleKey; children: React.ReactNode }) {
  const auth = useAuth()
  if (!auth.canAccess(module)) return <Navigate to="/" replace />
  return children
}

function HomeRedirect() {
  const auth = useAuth()
  const first = PERMISSION_MODULES.find(m => auth.canAccess(m.key))
  if ((nexusBase() || auth.session?.nexus) && !first) return <div role="alert" style={{ padding: 32 }}>当前账号尚未获授具体业务页权限，请联系管理员分配印尼走货模块权限。</div>
  return <Navigate to={first?.path || (canManageLegacyUsers(auth.session) ? '/users' : '/login')} replace />
}

const router = createBrowserRouter(createRoutesFromElements(<>
            <Route path="/login" element={nexusBase() ? <RequireLogin><HomeRedirect /></RequireLogin> : <LoginPage />} />
            <Route path="/" element={<RequireLogin><AppLayout /></RequireLogin>}>
              <Route index element={<HomeRedirect />} />
              <Route path="customers"    element={<ModuleRoute module="customers"><CustomersPage /></ModuleRoute>} />
              <Route path="dictionaries" element={<ModuleRoute module="products"><DictionariesPage /></ModuleRoute>} />
              <Route path="supplier-summary" element={<ModuleRoute module="products"><SupplierSummaryPage /></ModuleRoute>} />
              <Route path="products"     element={<ModuleRoute module="products"><ProductsPage /></ModuleRoute>} />
              <Route path="tool-materials" element={<ModuleRoute module="products"><ToolMaterialsPage /></ModuleRoute>} />
              <Route path="quotes"       element={<ModuleRoute module="quotes"><QuotesPage /></ModuleRoute>} />
              <Route path="purchase"     element={<ModuleRoute module="purchase"><PurchasePage /></ModuleRoute>} />
              <Route path="material-alerts" element={<ModuleRoute module="purchase"><MaterialAlertsPage /></ModuleRoute>} />
              <Route path="molding-pos"  element={<ModuleRoute module="molding"><MoldingPosPage /></ModuleRoute>} />
              <Route path="schedules"    element={<ModuleRoute module="schedules"><SchedulesPage /></ModuleRoute>} />
              <Route path="shipments"    element={<ModuleRoute module="shipments"><ShipmentsPage /></ModuleRoute>} />
              <Route path="outbound"     element={<ModuleRoute module="outbound"><OutboundPage /></ModuleRoute>} />
              <Route path="users"        element={<AdminRoute kind="users"><UsersPage /></AdminRoute>} />
              <Route path="db-admin"     element={<AdminRoute kind="database"><DbAdminPage /></AdminRoute>} />
              <Route path="*" element={<HomeRedirect />} />
            </Route>
  </>), { basename: publicBase(import.meta.env.BASE_URL) })

export default function App() {
  return <ConfigProvider locale={zhCN}><AntApp><AuthProvider>
    <Suspense fallback={Fallback}><RouterProvider router={router} /></Suspense>
  </AuthProvider></AntApp></ConfigProvider>
}

function AdminRoute({ children, kind }: { children: React.ReactNode; kind: 'users' | 'database' }) {
  const auth = useAuth()
  const permitted = kind === 'users' ? canManageLegacyUsers(auth.session) : canManageLegacyDatabase(auth.session)
  return permitted ? children : <Navigate to="/" replace />
}
