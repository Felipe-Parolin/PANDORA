<script setup>
import { formatPhone } from '../services/formatters'
import { useRoute } from 'vue-router'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { LayoutDashboard, UsersRound, Wrench, PackageOpen, ClipboardList, LogOut, Menu, X, Truck, ChartNoAxesCombined, Sparkles, UserRound, ShieldCheck, Mail, Phone } from 'lucide-vue-next'
import { auth, canAny, logout, refreshCurrentUser } from '../services/api'
import HeaderClock from './HeaderClock.vue'
import NotificationCenter from './NotificationCenter.vue'
import ModalDialog from './ModalDialog.vue'

const route = useRoute()
const mobileOpen = ref(false), profileOpen = ref(false), profileLoading = ref(false), profileError = ref('')
async function openProfile() {
  profileOpen.value = true; profileLoading.value = true; profileError.value = ''
  try { await refreshCurrentUser() }
  catch { profileError.value = 'Não foi possível atualizar o perfil. Os dados exibidos são os da sessão atual.' }
  finally { profileLoading.value = false }
}
const closeOnEscape = event => { if (event.key === 'Escape') mobileOpen.value = false }
watch(() => route.fullPath, () => { mobileOpen.value = false; profileOpen.value = false })
watch(() => auth.user?.id, () => { profileOpen.value = false })
onMounted(() => document.addEventListener('keydown', closeOnEscape))
onUnmounted(() => document.removeEventListener('keydown', closeOnEscape))
const navGroups = computed(() => [
  { label: 'VISÃO GERAL', items: [{ to: '/', label: 'Painel de controle', icon: LayoutDashboard, permission: 'dashboard.view' }] },
  { label: 'CADASTROS', items: [
    { to: '/pessoas', label: 'Clientes e usuários', icon: UsersRound, permission: ['customers.view', 'accounts.users.view', 'accounts.groups.manage'] },
    { to: '/equipamentos', label: 'Equipamentos', icon: PackageOpen, permission: 'assets.view' },
    { to: '/veiculos', label: 'Veículos', icon: Truck, permission: 'logistics.view' },
  ] },
  { label: 'OPERAÇÃO', items: [
    { to: '/locacoes', label: 'Locações e reservas', icon: ClipboardList, permission: 'rentals.view' },
    { to: '/manutencao', label: 'Manutenção', icon: Wrench, permission: 'maintenance.view' },
    { to: '/transporte', label: 'Logística e viagens', icon: Truck, permission: 'logistics.view' },
  ] },
  { label: 'GESTÃO', items: [
    { to: '/comercial', label: 'Comercial', icon: ChartNoAxesCombined, permission: ['rentals.view', 'assets.view', 'customers.view', 'commercial.receivables.view'] },
    { to: '/assistente', label: 'Assistente de IA', icon: Sparkles, permission: 'ai.assist' },
  ] },
].map(group => ({ ...group, items: group.items.filter(item => canAny(item.permission)) })).filter(group => group.items.length))
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
      <section v-for="group in navGroups" :key="group.label" class="nav-group">
        <div class="nav-caption">{{ group.label }}</div>
        <nav>
          <router-link v-for="item in group.items" :key="item.to" :to="item.to" :class="{ active: active(item.to) }" @click="mobileOpen = false">
            <component :is="item.icon" :size="19" /><span>{{ item.label }}</span>
          </router-link>
        </nav>
      </section>
      <div class="sidebar-footer"><strong class="sidebar-group-name">{{ auth.user?.access_group_name || auth.user?.role_label || 'PANDORA' }}</strong><button type="button" class="icon-btn sidebar-logout" aria-label="Sair do sistema" title="Sair do sistema" @click="logout"><LogOut :size="19" /></button></div>
    </aside>
    <section class="workspace">
      <header class="topbar">
        <button class="icon-btn menu-btn" @click="mobileOpen = true"><Menu :size="22" /></button>
        <HeaderClock />
        <div class="top-actions">
          <NotificationCenter />
          <button type="button" class="top-avatar profile-trigger" aria-label="Abrir meu perfil" :title="auth.user?.full_name" @click="openProfile">{{ auth.user?.full_name?.charAt(0) || 'P' }}</button>
        </div>
      </header>
      <main><router-view /></main>
    </section>
    <ModalDialog v-if="profileOpen" title="Meu perfil" @close="profileOpen = false">
      <div class="profile-summary"><div class="profile-avatar"><UserRound :size="30" /></div><div><span class="eyebrow">SESSÃO ATUAL</span><h3>{{ auth.user?.full_name }}</h3><p>{{ auth.user?.access_group_name || auth.user?.role_label }}</p></div></div>
      <p v-if="profileLoading" role="status">Atualizando perfil...</p><GeneralError v-if="profileError" :message="profileError" @close="profileError = ''" />
      <dl class="profile-details"><div><dt><Mail :size="16" />E-mail</dt><dd>{{ auth.user?.email }}</dd></div><div><dt><Phone :size="16" />Telefone</dt><dd>{{ auth.user?.phone ? formatPhone(auth.user.phone) : 'Não informado' }}</dd></div><div><dt><ShieldCheck :size="16" />Grupo de permissão</dt><dd>{{ auth.user?.access_group_name || auth.user?.role_label }}</dd></div><div><dt>Situação</dt><dd>{{ auth.user?.is_active ? 'Ativo' : 'Inativo' }}</dd></div></dl>
      <div class="modal-actions"><button class="btn secondary" @click="logout"><LogOut :size="16" />Sair da conta</button></div>
    </ModalDialog>
  </div>
</template>
