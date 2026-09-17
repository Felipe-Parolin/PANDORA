<script setup>
import { useRoute } from 'vue-router'
import { computed, ref } from 'vue'
import { LayoutDashboard, UsersRound, Wrench, PackageOpen, ClipboardList, Bell, Search, LogOut, Menu, X } from 'lucide-vue-next'
import { auth, can, logout } from '../services/api'

const route = useRoute()
const mobileOpen = ref(false)
const nav = computed(() => [
  { to: '/', label: 'Visão geral', icon: LayoutDashboard, permission: 'dashboard.view' },
  { to: '/pessoas', label: 'Pessoas e acessos', icon: UsersRound, permission: 'accounts.users.view' },
  { to: '/equipamentos', label: 'Equipamentos', icon: PackageOpen, permission: 'assets.view' },
  { to: '/manutencao', label: 'Manutenção', icon: Wrench, permission: 'maintenance.view' },
  { to: '/locacoes', label: 'Locações', icon: ClipboardList, permission: 'rentals.view' },
].filter(item => can(item.permission)))
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
        <div class="user-meta"><strong>{{ auth.user?.full_name || 'Usuário' }}</strong><span>{{ auth.user?.role_label || 'PANDORA' }}</span></div>
        <button class="icon-btn" title="Sair" @click="logout"><LogOut :size="18" /></button>
      </div>
    </aside>
    <section class="workspace">
      <header class="topbar">
        <button class="icon-btn menu-btn" @click="mobileOpen = true"><Menu :size="22" /></button>
        <div class="global-search"><Search :size="18" /><input aria-label="Busca global" placeholder="Buscar equipamento, cliente ou OS..." /></div>
        <div class="top-actions"><button class="icon-btn"><Bell :size="20" /><i /></button><div class="top-avatar">{{ auth.user?.full_name?.charAt(0) || 'P' }}</div></div>
      </header>
      <main><router-view /></main>
    </section>
  </div>
</template>
