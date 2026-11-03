<script setup>
import { transportStatusLabel, formatPercent } from '../services/formatters'
import { usePagination } from '../services/pagination'
import { computed, onMounted, ref } from 'vue'
import {
  ArrowUpRight, CalendarClock, CircleDollarSign, ClipboardCheck, PackageCheck,
  Plus, Wrench, UsersRound, Truck, AlertTriangle, Clock3, PackageOpen,
  ClipboardList, CalendarDays, CheckCircle2, RefreshCw
} from 'lucide-vue-next'
import { api, can, money, shortDate } from '../services/api'
import DashboardTransportMap from '../components/DashboardTransportMap.vue'
import StatusBadge from '../components/StatusBadge.vue'

const data = ref({ recent_quotes: [] })
const loading = ref(true)
const chartVersion = ref(0)
const error = ref('')
const quoteStatus = { DRAFT: 'Rascunho', SENT: 'Enviado', APPROVED: 'Aprovado / reservado', ACTIVE: 'Em locação', RETURNED: 'Devolvido', COMPLETED: 'Concluído', CANCELLED: 'Cancelado', EXPIRED: 'Expirado' }
const cards = computed(() => data.value ? [
  { label: 'Equipamentos cadastrados', value: data.value.equipment, note: `${data.value.available_equipment || 0} disponíveis`, icon: PackageCheck, tone: 'tone-fleet', to: '/equipamentos', permission: 'assets.view' },
  { label: 'Locações em andamento', value: data.value.rentals_in_progress || 0, note: `${data.value.overdue_rentals || 0} locação(ões) atrasada(s)`, icon: ClipboardList, tone: 'tone-rentals', to: { path: '/locacoes', query: { status: 'ACTIVE' } }, permission: 'rentals.view' },
  { label: 'Ordens de serviço abertas', value: data.value.open_orders, note: `${data.value.orders_in_progress || 0} em execução`, icon: Wrench, tone: 'tone-service', to: { path: '/manutencao', query: { queue: 'READY' } }, permission: 'maintenance.view' },
  { label: 'Inspeções pendentes', value: data.value.pending_inspections || 0, note: `${data.value.blocked_inspections || 0} impedida(s)`, icon: ClipboardCheck, tone: 'tone-inspection', to: can('rentals.view') ? { path: '/locacoes', query: { status: 'APPROVED' } } : { path: '/manutencao', query: { tab: 'rental' } }, permission: can('maintenance.view') ? 'maintenance.view' : 'rentals.view' },
  { label: 'Receita contratual', value: money(data.value.realized_revenue), note: 'Valor contratual de locações ativas e encerradas', icon: CircleDollarSign, tone: 'tone-revenue', to: '/comercial', permission: 'rentals.view' },
  { label: 'Entregas e coletas hoje', value: (data.value.deliveries_today || 0) + (data.value.collections_today || 0), note: `${data.value.deliveries_today || 0} entregas · ${data.value.collections_today || 0} coletas`, icon: Truck, tone: 'tone-transport', to: '/transporte', permission: 'logistics.view' },
].filter(card => can(card.permission)) : [])
const fleetBars = computed(() => [
  { status: 'AVAILABLE', label: 'Disponíveis', tone: 'available' },
  { status: 'RESERVED', label: 'Reservados', tone: 'reserved' },
  { status: 'RENTED', label: 'Locados', tone: 'rented' },
  { status: 'MAINTENANCE', label: 'Em manutenção', tone: 'maintenance' },
].map(item => {
  const count = Number(data.value?.equipment_by_status?.[item.status] || 0)
  return { ...item, count, percent: Math.min(100, count / Math.max(Number(data.value?.equipment || 0), 1) * 100) }
}))
const agenda = computed(() => data.value?.agenda_next_7_days || [])
async function load() {
  loading.value = true; error.value = ''
  try { data.value = (await api.get('/dashboard/')).data; chartVersion.value += 1 }
  catch (e) { error.value = e?.response?.data?.detail || 'Não foi possível carregar os indicadores.' }
  finally { loading.value = false }
}
function agendaDate(value) { return value ? new Date(value).toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'Horário a definir' }
onMounted(load)

const { page: recentPage, items: recentRows } = usePagination(computed(() => data.value.recent_quotes || []), [])
</script>

<template>
  <div class="page dashboard-page" :aria-busy="loading">
    <header class="page-heading"><div><span class="eyebrow">CENTRAL OPERACIONAL</span><h1>Painel de controle</h1><p>Visão rápida das locações, da manutenção e da logística da Mazzi.</p></div><div class="page-heading-actions"><button class="btn secondary" :disabled="loading" @click="load"><RefreshCw :size="18" :class="{ spinning: loading }" /> Atualizar dados</button><router-link v-if="can('rentals.manage')" to="/locacoes" class="btn primary"><Plus :size="18"/> Novo orçamento</router-link></div></header>
    <GeneralError v-if="error" :message="error" @close="error = ''" />
    <span v-if="loading" class="sr-only" role="status">Atualizando indicadores operacionais...</span>
    <template v-if="data">
      <div v-if="!cards.length" class="panel empty-state compact">Seu grupo não possui setores habilitados neste painel.</div><section class="metric-grid dashboard-metric-grid"><router-link v-for="card in cards" :key="card.label" :to="card.to" class="metric-card dashboard-metric-link" :class="card.tone"><div class="metric-icon"><component :is="card.icon" :size="22"/></div><span>{{ card.label }}</span><strong>{{ card.value ?? '—' }}</strong><small>{{ card.note }}</small><ArrowUpRight class="dashboard-card-arrow" :size="17"/></router-link></section>
      <section v-if="can('rentals.view')" class="quote-summary dashboard-sales-summary"><div><span class="eyebrow">EM NEGOCIAÇÃO</span><strong>{{ data.active_quotes || 0 }}</strong><p>propostas no funil comercial</p></div><div><span class="eyebrow">VALOR DO FUNIL</span><strong>{{ money(data.quotes_total) }}</strong><p>sem cancelados e expirados</p></div><div><span class="eyebrow">CONVERSÃO</span><strong>{{ formatPercent(data.conversion_percent || 0) }}</strong><p>orçamentos convertidos em reserva</p></div></section>
      <section class="dashboard-grid dashboard-main-grid">
        <article v-if="can('maintenance.view') || can('rentals.view') || can('logistics.view')" class="panel operations-panel"><header><div><span class="eyebrow">ATENÇÃO OPERACIONAL</span><h2>Pendências prioritárias</h2></div><AlertTriangle :size="21"/></header><div class="priority-list">
          <div v-if="can('maintenance.view')" class="priority-item critical"><span class="priority-date">CRÍTICO</span><div><strong>Manutenções vencidas</strong><p>{{ data.overdue_maintenance || 0 }} plano(s) exigem análise antes de novas reservas.</p></div><router-link :to="{ path: '/manutencao', query: { tab: 'workshop' } }"><ArrowUpRight :size="18"/></router-link></div>
          <div v-if="can('maintenance.view')" class="priority-item"><span class="priority-date">MANUT.</span><div><strong>Ordens aguardando avanço</strong><p>{{ data.orders_waiting || 0 }} aguardando execução ou peças; {{ data.waiting_technical_release || 0 }} concluída(s) aguardando liberação.</p></div><router-link :to="{ path: '/manutencao', query: { queue: 'READY' } }"><ArrowUpRight :size="18"/></router-link></div>
          <div v-if="can('rentals.view')" class="priority-item"><span class="priority-date">INSPEÇÃO</span><div><strong>Equipamentos aguardando conferência</strong><p>{{ data.pending_inspections || 0 }} inspeção(ões) pendente(s) e {{ data.blocked_inspections || 0 }} com impedimento.</p></div><router-link to="/locacoes"><ArrowUpRight :size="18"/></router-link></div>
          <div v-if="can('rentals.view') || can('logistics.view')" class="priority-item"><span class="priority-date">LOCAÇÃO</span><div><strong>{{ can('rentals.view') ? 'Locações / coletas atrasadas' : 'Coletas atrasadas' }}</strong><p><span v-if="can('rentals.view')">{{ data.overdue_rentals || 0 }} locação(ões) </span><span v-if="can('logistics.view')">{{ data.overdue_collections || 0 }} coleta(s) </span>fora do prazo.</p></div><router-link :to="can('logistics.view') ? { path: '/transporte', query: { leg: 'RETURN' } } : { path: '/locacoes', query: { status: 'ACTIVE' } }"><ArrowUpRight :size="18"/></router-link></div>
        </div></article>
        <article v-if="can('assets.view')" class="panel availability-panel"><header><div><span class="eyebrow">FROTA</span><h2>Disponibilidade</h2></div><PackageCheck :size="22"/></header><div :key="chartVersion" class="fleet-bars" aria-label="Distribuição da frota"><div v-for="(bar, index) in fleetBars" :key="bar.status" class="fleet-bar-row"><div class="fleet-bar-label"><span>{{ bar.label }}</span><strong>{{ bar.count }}</strong></div><div class="fleet-bar-track" role="progressbar" :aria-label="bar.label" :aria-valuenow="bar.count" :aria-valuemax="Math.max(Number(data.equipment || 0), 1)" aria-valuemin="0"><div class="fleet-bar-fill" :class="bar.tone" :style="{ width: `${bar.percent}%`, '--bar-delay': `${index * 80}ms` }" /></div></div><p v-if="!data.equipment" class="fleet-empty">Nenhum equipamento cadastrado.</p></div><div class="availability-foot"><span>Bloqueados / inspeção</span><strong>{{ data.blocked_equipment || 0 }}</strong></div></article>
      </section>
      <DashboardTransportMap v-if="can('logistics.view')" />
      <section v-if="can('logistics.view')" class="panel dashboard-agenda"><header><div><span class="eyebrow">PRÓXIMOS 7 DIAS</span><h2>Agenda de entregas e coletas</h2></div><router-link to="/transporte" class="text-link">Abrir logística <ArrowUpRight :size="15"/></router-link></header><div class="dashboard-agenda-list"><router-link v-for="task in agenda" :key="task.id" :to="{ path: '/transporte', query: { trip: String(task.id), quote: task.quote__number } }" class="dashboard-agenda-item"><div class="agenda-date"><strong>{{ task.scheduled_at ? new Date(task.scheduled_at).toLocaleDateString('pt-BR', { day: '2-digit' }) : '—' }}</strong><span>{{ task.scheduled_at ? new Date(task.scheduled_at).toLocaleDateString('pt-BR', { month: 'short' }) : 'Sem data' }}</span></div><div class="agenda-task-main"><strong>{{ task.quote__customer__name }}</strong><small>{{ task.leg === 'DELIVERY' ? 'Entrega' : 'Coleta' }} · {{ task.quote__number }} · {{ task.address }}</small></div><div class="agenda-task-time"><Clock3 :size="14"/>{{ agendaDate(task.scheduled_at) }}</div><StatusBadge :value="task.status" :label="transportStatusLabel(task.status)"/><ArrowUpRight :size="18" class="agenda-open-icon" /></router-link><div v-if="!agenda.length" class="commercial-empty">Nenhuma entrega ou coleta agendada para os próximos sete dias.</div></div></section>
      <section v-if="can('rentals.view')" class="panel quotes-panel"><header><div><span class="eyebrow">COMERCIAL</span><h2>Orçamentos recentes</h2></div><router-link to="/locacoes" class="text-link">Ver todos <ArrowUpRight :size="15"/></router-link></header><div class="table-wrap"><table><thead><tr><th>Número</th><th>Cliente</th><th>Data</th><th>Status</th><th class="right">Valor</th><th class="right">Abrir</th></tr></thead><tbody><tr v-for="quote in recentRows" :key="quote.id"><td><router-link :to="{ path: '/locacoes', query: { quote: quote.number } }" class="record-link">{{ quote.number }}</router-link></td><td>{{ quote.customer__name }}</td><td>{{ shortDate(quote.created_at?.slice(0, 10)) }}</td><td><StatusBadge :value="quote.status" :label="quoteStatus[quote.status] || quote.status"/></td><td class="right"><strong>{{ money(quote.total) }}</strong></td><td class="right"><router-link :to="{ path: '/locacoes', query: { quote: quote.number } }" class="icon-btn" :aria-label="`Abrir orçamento ${quote.number}`"><ArrowUpRight :size="18" /></router-link></td></tr><tr v-if="!data.recent_quotes?.length"><td colspan="6" class="empty-cell"><ClipboardCheck :size="22"/>Nenhum orçamento cadastrado.</td></tr></tbody></table><PaginationBar v-model="recentPage" :total="(data.recent_quotes || []).length" /></div></section>
    </template>
  </div>
</template>
