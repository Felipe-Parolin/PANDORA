import { createRouter, createWebHistory } from 'vue-router'
import { auth, can, logout } from '../services/api'
import LoginView from '../views/LoginView.vue'
import AppShell from '../components/AppShell.vue'
import DashboardView from '../views/DashboardView.vue'
import PeopleView from '../views/PeopleView.vue'
import EquipmentView from '../views/EquipmentView.vue'
import MaintenanceView from '../views/MaintenanceView.vue'
import RentalsView from '../views/RentalsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    {
      path: '/', component: AppShell, children: [
        { path: '', name: 'dashboard', component: DashboardView, meta: { permission: 'dashboard.view' } },
        { path: 'pessoas', name: 'people', component: PeopleView, meta: { permission: 'accounts.users.view' } },
        { path: 'equipamentos', name: 'equipment', component: EquipmentView, meta: { permission: 'assets.view' } },
        { path: 'manutencao', name: 'maintenance', component: MaintenanceView, meta: { permission: 'maintenance.view' } },
        { path: 'locacoes', name: 'rentals', component: RentalsView, meta: { permission: 'rentals.view' } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (!to.meta.public && !auth.token) return '/login'
  if (to.path === '/login' && auth.token) return '/'
  if (to.meta.permission && !can(to.meta.permission)) {
    const fallback = [
      ['dashboard.view', '/'], ['accounts.users.view', '/pessoas'], ['assets.view', '/equipamentos'],
      ['maintenance.view', '/manutencao'], ['rentals.view', '/locacoes'],
    ].find(([permission]) => can(permission))
    if (!fallback) { logout(); return '/login' }
    return fallback[1]
  }
})

export default router
