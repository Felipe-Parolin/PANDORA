<script setup>
import { useRoute, useRouter } from 'vue-router'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { LayoutDashboard, UsersRound, Wrench, PackageOpen, ClipboardList, Bell, Search, LogOut, Menu, X, Truck } from 'lucide-vue-next'
import { api, auth, canAny, logout } from '../services/api'

const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)
const notificationsOpen = ref(false)
const notifications = ref([])
const unreadCount = ref(0)
const notificationError = ref('')
let notificationTimer

async function loadNotifications() {
  if (!auth.token) return
  try {
    const { data } = await api.get('/notifications/')
    notifications.value = data.results
    unreadCount.value = data.unread_count
    notificationError.value = ''
  } catch {
    notificationError.value = 'Não foi possível carregar as notificações.'
  }
}

async function openNotification(item) {
  try {
    if (!item.read_at) await api.post(`/notifications/${item.id}/read/`)
  } catch {
    notificationError.value = 'Não foi possível marcar a notificação como lida.'
  }
  await loadNotifications()
  notificationsOpen.value = false
  if (item.target_url?.startsWith('/') && !item.target_url.startsWith('//')) router.push(item.target_url)
}

async function markAllRead() {
  try {
    await api.post('/notifications/read-all/')
    await loadNotifications()
  } catch {
    notificationError.value = 'Não foi possível marcar as notificações como lidas.'
  }
}

onMounted(() => {
  loadNotifications()
  notificationTimer = window.setInterval(loadNotifications, 30000)
})
onUnmounted(() => window.clearInterval(notificationTimer))
const nav = computed(() => [
  { to: '/', label: 'Visão geral', icon: LayoutDashboard, permission: 'dashboard.view' },
  { to: '/pessoas', label: 'Pessoas e acessos', icon: UsersRound, permission: ['customers.view', 'accounts.users.view', 'accounts.groups.manage'] },
  { to: '/equipamentos', label: 'Equipamentos', icon: PackageOpen, permission: 'assets.view' },
  { to: '/manutencao', label: 'Manutenção', icon: Wrench, permission: 'maintenance.view' },
  { to: '/locacoes', label: 'Locações', icon: ClipboardList, permission: 'rentals.view' },
  { to: '/transporte', label: 'Transporte', icon: Truck, permission: 'logistics.view' },
].filter(item => canAny(item.permission)))
const active = (path) => path === '/' ? route.path === '/' : route.path.startsWith(path)
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ open: mobileOpen }">
      <div class="brand">
        <div class="brand-mark">P</div>
        <div><strong>PANDORA</strong><span>Locação & manutenção</span></div>
        <button class="icon-btn sidebar-close" @click="mobileOpen = false"><X :size="20" /></button>
      </div>
      <div class="nav-caption">OPERAÇÃO</div>
      <nav>
        <router-link v-for="item in nav" :key="item.to" :to="item.to" :class="{ active: active(item.to) }" @click="mobileOpen = false">
          <component :is="item.icon" :size="19" /><span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <div class="avatar">{{ auth.user?.full_name?.charAt(0) || 'P' }}</div>
        <div class="user-meta"><strong>{{ auth.user?.full_name || 'Usuário' }}</strong><span>{{ auth.user?.access_group_name || auth.user?.role_label || 'PANDORA' }}</span></div>
        <button class="icon-btn" title="Sair" @click="logout"><LogOut :size="18" /></button>
      </div>
    </aside>
    <section class="workspace">
      <header class="topbar">
        <button class="icon-btn menu-btn" @click="mobileOpen = true"><Menu :size="22" /></button>
        <div class="global-search"><Search :size="18" /><input aria-label="Busca global" placeholder="Buscar equipamento, cliente ou OS..." /></div>
        <div class="top-actions">
          <div class="notification-wrap">
            <button class="icon-btn notification-trigger" type="button" :aria-expanded="notificationsOpen" aria-label="Notificações" @click="notificationsOpen = !notificationsOpen; if (notificationsOpen) loadNotifications()">
              <Bell :size="20" /><span v-if="unreadCount" class="notification-count">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
            </button>
            <div v-if="notificationsOpen" class="notification-panel" role="dialog" aria-label="Notificações">
              <header><strong>Notificações</strong><button v-if="unreadCount" type="button" @click="markAllRead">Marcar todas como lidas</button></header>
              <p v-if="notificationError" class="notification-error">{{ notificationError }}</p>
              <p v-if="!notifications.length" class="notification-empty">Nenhuma notificação por enquanto.</p>
              <div v-else class="notification-list">
                <button v-for="item in notifications" :key="item.id" type="button" :class="{ unread: !item.read_at }" @click="openNotification(item)">
                  <span class="notification-kind">{{ item.kind === 'RENTAL' ? 'Locação' : item.kind === 'TRANSPORT' ? 'Transporte' : 'Manutenção' }}</span>
                  <strong>{{ item.title }}</strong><span>{{ item.message }}</span>
                  <small>{{ new Date(item.created_at).toLocaleString('pt-BR') }}</small>
                </button>
              </div>
            </div>
          </div>
          <div class="top-avatar">{{ auth.user?.full_name?.charAt(0) || 'P' }}</div>
        </div>
      </header>
      <main><router-view /></main>
    </section>
  </div>
</template>
