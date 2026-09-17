<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowUpRight, CalendarClock, CircleDollarSign, ClipboardCheck, PackageCheck, Plus, Wrench, UsersRound } from 'lucide-vue-next'
import { api, money, shortDate } from '../services/api'
import StatusBadge from '../components/StatusBadge.vue'

const data = ref(null)
const loading = ref(true)
const quoteStatus = { DRAFT: 'Rascunho', SENT: 'Enviado', APPROVED: 'Aprovado / reservado', CANCELLED: 'Cancelado', EXPIRED: 'Expirado' }
const cards = computed(() => data.value ? [
  { label: 'Equipamentos', value: data.value.equipment, note: `${data.value.equipment_by_status?.AVAILABLE || 0} disponíveis agora`, icon: PackageCheck, tone: 'amber' },
  { label: 'Clientes ativos', value: data.value.customers, note: 'Base interna atualizada', icon: UsersRound, tone: 'dark' },
  { label: 'OS em andamento', value: data.value.open_orders, note: `${data.value.overdue_maintenance} manutenções vencidas`, icon: Wrench, tone: 'orange' },
  { label: 'Carteira em orçamento', value: money(data.value.quotes_total), note: `${data.value.active_quotes} propostas ativas`, icon: CircleDollarSign, tone: 'light' },
] : [])
onMounted(async () => { try { data.value = (await api.get('/dashboard/')).data } finally { loading.value = false } })
</script>

<template>
  <div class="page dashboard-page">
    <header class="page-heading"><div><span class="eyebrow">CENTRAL OPERACIONAL</span><h1>Bom dia. Aqui está o pulso da operação.</h1><p>Acompanhe disponibilidade, manutenção e propostas sem perder o contexto.</p></div><router-link to="/locacoes" class="btn primary"><Plus :size="18" />Novo orçamento</router-link></header>
    <section v-if="!loading" class="metric-grid"><article v-for="card in cards" :key="card.label" class="metric-card" :class="card.tone"><div class="metric-icon"><component :is="card.icon" :size="22" /></div><span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.note }}</small></article></section>
    <section class="dashboard-grid">
      <article class="panel operations-panel"><header><div><span class="eyebrow">HOJE</span><h2>Prioridades operacionais</h2></div><CalendarClock :size="22" /></header><div class="priority-list"><div class="priority-item critical"><span class="priority-date">AGORA</span><div><strong>Revisar manutenções vencidas</strong><p>{{ data?.overdue_maintenance || 0 }} planos exigem análise antes de novas reservas.</p></div><router-link to="/manutencao"><ArrowUpRight :size="18" /></router-link></div><div class="priority-item"><span class="priority-date">FLUXO</span><div><strong>Validar ordens em aberto</strong><p>{{ data?.open_orders || 0 }} intervenções aguardam avanço ou liberação técnica.</p></div><router-link to="/manutencao"><ArrowUpRight :size="18" /></router-link></div><div class="priority-item"><span class="priority-date">VENDAS</span><div><strong>Acompanhar propostas</strong><p>{{ data?.active_quotes || 0 }} orçamentos seguem ativos no funil.</p></div><router-link to="/locacoes"><ArrowUpRight :size="18" /></router-link></div></div></article>
      <article class="panel availability-panel"><header><div><span class="eyebrow">FROTA</span><h2>Disponibilidade</h2></div><PackageCheck :size="22" /></header><div class="donut-wrap"><div class="donut" :style="{ '--available': `${((data?.equipment_by_status?.AVAILABLE || 0) / Math.max(data?.equipment || 1, 1)) * 100}%` }"><div><strong>{{ data?.equipment_by_status?.AVAILABLE || 0 }}</strong><span>disponíveis</span></div></div><div class="legend"><span><i class="green" />Disponível <strong>{{ data?.equipment_by_status?.AVAILABLE || 0 }}</strong></span><span><i class="amber-dot" />Reservado <strong>{{ data?.equipment_by_status?.RESERVED || 0 }}</strong></span><span><i class="red" />Manutenção <strong>{{ data?.equipment_by_status?.MAINTENANCE || 0 }}</strong></span></div></div></article>
      <article class="panel quotes-panel"><header><div><span class="eyebrow">COMERCIAL</span><h2>Orçamentos recentes</h2></div><router-link to="/locacoes" class="text-link">Ver todos <ArrowUpRight :size="15" /></router-link></header><div class="table-wrap"><table><thead><tr><th>Número</th><th>Cliente</th><th>Data</th><th>Status</th><th class="right">Valor</th></tr></thead><tbody><tr v-for="quote in data?.recent_quotes" :key="quote.id"><td><strong>{{ quote.number }}</strong></td><td>{{ quote.customer__name }}</td><td>{{ shortDate(quote.created_at?.slice(0, 10)) }}</td><td><StatusBadge :value="quote.status" :label="quoteStatus[quote.status] || quote.status" /></td><td class="right"><strong>{{ money(quote.total) }}</strong></td></tr><tr v-if="!data?.recent_quotes?.length"><td colspan="5" class="empty-cell"><ClipboardCheck :size="22" />Nenhum orçamento cadastrado.</td></tr></tbody></table></div></article>
    </section>
  </div>
</template>
