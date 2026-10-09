import { createRouter, createWebHistory } from 'vue-router'
import { auth, canAny, logout, refreshCurrentUser } from '../services/api'
import LoginView from '../views/LoginView.vue'
import AppShell from '../components/AppShell.vue'
import DashboardView from '../views/DashboardView.vue'
import PeopleView from '../views/PeopleView.vue'
import EquipmentView from '../views/EquipmentView.vue'
import MaintenanceView from '../views/MaintenanceView.vue'
import RentalsView from '../views/RentalsView.vue'
import LogisticsView from '../views/LogisticsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    {
      path: '/', component: AppShell, children: [
        { path: '', name: 'dashboard', component: DashboardView, meta: { permission: 'dashboard.view' } },
        { path: 'pessoas', name: 'people', component: PeopleView, meta: { permission: ['customers.view', 'accounts.users.view', 'accounts.groups.manage'] } },
        { path: 'equipamentos', name: 'equipment', component: EquipmentView, meta: { permission: 'assets.view' } },
        { path: 'manutencao', name: 'maintenance', component: MaintenanceView, meta: { permission: 'maintenance.view' } },
        { path: 'locacoes', name: 'rentals', component: RentalsView, meta: { permission: 'rentals.view' } },
        { path: 'transporte', name: 'logistics', component: LogisticsView, meta: { permission: 'logistics.view' } },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.public && !auth.token) return '/login'
  if (to.path === '/login' && auth.token) return '/'
  if (!to.meta.public) {
    try { await refreshCurrentUser() }
    catch { return auth.token ? false : '/login' }
  }
  if (to.meta.permission && !canAny(to.meta.permission)) {
    const fallback = [
      ['dashboard.view', '/'], [['customers.view', 'accounts.users.view', 'accounts.groups.manage'], '/pessoas'], ['assets.view', '/equipamentos'],
      ['maintenance.view', '/manutencao'], ['rentals.view', '/locacoes'], ['logistics.view', '/transporte'],
    ].find(([permission]) => canAny(permission))
    if (!fallback) { logout(); return '/login' }
    return fallback[1]
  }
})

export default router
