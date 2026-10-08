<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertTriangle, CalendarDays, ClipboardPlus, Files, Pencil, Plus, Search, Trash2, Wrench,
} from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import MaintenanceCalendar from '../components/MaintenanceCalendar.vue'
import ModalDialog from '../components/ModalDialog.vue'
import RentalInspectionModal from '../components/RentalInspectionModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, rows, shortDate } from '../services/api'

const tab = ref('calendar')
const route = useRoute()
const queue = ref('ALL')
const plansExpanded = ref(false)
const search = ref('')
const orders = ref([])
const plans = ref([])
const equipment = ref([])
const technicians = ref([])
const modal = ref(null)
const editing = ref(null)
const deleting = ref(null)
const mediaEquipment = ref(null)
const inspectionContext = ref(null)
const error = ref('')
const busy = ref(false)
const quickPlanning = ref(false)

const orderForm = reactive({
  equipment: '', maintenance_type: 'CORRECTIVE', priority: 'NORMAL', symptoms: '',
  diagnosis: '', technician: '', status: 'OPEN', scheduled_at: '', final_tests: '',
  released: false, labor_hours: 0, parts_used: '', abandoned_reason: '',
})
const planForm = reactive({
  equipment: '', name: '', maintenance_type: 'PREVENTIVE', interval_days: 90, usage_limit: null,
  next_due_date: '', last_service_date: '', last_service_usage_hours: null, advance_notice_days: 15,
  advance_notice_usage_hours: 10, criticality: 'MEDIUM', checklist: [], active: true,
})

const alerts = computed(() => plans.value.filter(item => ['OVERDUE', 'CRITICAL', 'UPCOMING'].includes(item.alert_status)))
const alertTarget = computed(() => alerts.value.some(item => ['PREVENTIVE', 'SCHEDULED'].includes(item.maintenance_type)) ? 'preventive' : 'rental')
const terminalStatuses = ['COMPLETED', 'CANCELLED']
const maintenanceTabs = computed(() => [
  { key: 'calendar', label: 'Calendário', icon: CalendarDays, count: null },
  { key: 'rental', label: 'Manutenção da locação', icon: ClipboardPlus, count: orders.value.filter(item => ['PRE_RENTAL', 'POST_RENTAL'].includes(item.maintenance_type) && !terminalStatuses.includes(item.status)).length },
  { key: 'preventive', label: 'Preventiva', icon: CalendarDays, count: orders.value.filter(item => ['PREVENTIVE', 'SCHEDULED'].includes(item.maintenance_type) && !terminalStatuses.includes(item.status)).length },
  { key: 'corrective', label: 'Corretiva', icon: Wrench, count: orders.value.filter(item => item.maintenance_type === 'CORRECTIVE' && !terminalStatuses.includes(item.status)).length },
])
const categoryOrders = computed(() => orders.value.filter(order => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  preventive: ['PREVENTIVE', 'SCHEDULED'],
  corrective: ['CORRECTIVE'],
})[tab.value]?.includes(order.maintenance_type)))
const categoryPlans = computed(() => plans.value.filter(plan => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  preventive: ['PREVENTIVE', 'SCHEDULED'],
})[tab.value]?.includes(plan.maintenance_type)))
const matchesQueue = (order, key) => ({
  ALL: true,
  UNASSIGNED: !order.technician && order.status !== 'ABANDONED' && !terminalStatuses.includes(order.status),
  READY: ['OPEN', 'SCHEDULED'].includes(order.status),
  IN_PROGRESS: order.status === 'IN_PROGRESS',
  WAITING_PARTS: order.status === 'WAITING_PARTS',
  ABANDONED: order.status === 'ABANDONED',
  COMPLETED: order.status === 'COMPLETED',
}[key])
const queueTabs = computed(() => [
  { key: 'ALL', label: 'Todas as etapas' },
  { key: 'UNASSIGNED', label: 'Sem técnico' },
  { key: 'READY', label: 'Aguardando início' },
  { key: 'IN_PROGRESS', label: 'Em andamento' },
  { key: 'WAITING_PARTS', label: 'Aguardando peças' },
  { key: 'ABANDONED', label: 'Abandonados' },
  { key: 'COMPLETED', label: 'Concluídos' },
].map(item => ({ ...item, count: categoryOrders.value.filter(order => matchesQueue(order, item.key)).length })))
const filteredOrders = computed(() => {
  const term = search.value.trim().toLocaleLowerCase('pt-BR')
  return categoryOrders.value.filter(order => matchesQueue(order, queue.value)).filter(order => !term || [
    order.number, order.equipment_name, order.technician_name, order.symptoms, order.rental_quote_number,
  ].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const repairAfterCancellation = computed(() => editing.value?.rental_quote_status === 'CANCELLED' && editing.value?.inspection_result === 'BLOCKED')
const linkedOrderEditable = computed(() => can('maintenance.manage') && editing.value && !terminalStatuses.includes(editing.value.status) && (editing.value.rental_quote_status === 'APPROVED' || repairAfterCancellation.value))
const equipmentById = id => equipment.value.find(item => item.id === id)
const toLocalInput = value => {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const scheduledDay = value => toLocalInput(value).slice(0, 10)

async function load() {
  const [o, p, e, u] = await Promise.all([
    api.get('/service-orders/'), api.get('/maintenance-plans/'), api.get('/equipment/'), api.get('/users/'),
  ])
  orders.value = rows(o.data)
  plans.value = rows(p.data)
  equipment.value = rows(e.data)
  technicians.value = rows(u.data).filter(user => user.permissions.includes('*') || user.permissions.includes('maintenance.manage'))
}

function openOrder(item = null, defaults = {}) {
  editing.value = item
  modal.value = !item ? 'quick-order' : !can('maintenance.manage') ? 'order-detail' : item.rental_inspection && item.maintenance_type === 'PRE_RENTAL' ? 'linked-order' : 'order'
  error.value = ''
  quickPlanning.value = Boolean(defaults.scheduled_at)
  Object.assign(orderForm, item ? {
    equipment: item.equipment,
    maintenance_type: item.maintenance_type,
    priority: item.priority,
    symptoms: item.symptoms,
    diagnosis: item.diagnosis,
    technician: item.technician || '',
    status: item.status,
    scheduled_at: toLocalInput(item.scheduled_at),
    final_tests: item.final_tests,
    released: item.released,
    labor_hours: item.labor_hours,
    parts_used: item.parts_used,
    abandoned_reason: item.abandoned_reason || '',
  } : {
    equipment: '', maintenance_type: 'CORRECTIVE', priority: 'NORMAL',
    symptoms: '', diagnosis: '', technician: '', status: 'OPEN', scheduled_at: '', final_tests: '',
    released: false, labor_hours: 0, parts_used: '', abandoned_reason: '', ...defaults,
  })
}

function selectTab(key) {
  tab.value = key
  queue.value = 'ALL'
  search.value = ''
  plansExpanded.value = false
}

function showAlertPlans() {
  selectTab(alertTarget.value)
  plansExpanded.value = true
}

function schedulePreventive() {
  const date = new Date(Date.now() + 3600000)
  date.setMinutes(0, 0, 0)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  openOrder(null, { maintenance_type: 'PREVENTIVE', status: 'SCHEDULED', scheduled_at: local })
}

async function openInspection(order) {
  error.value = ''
  try {
    const { data } = await api.get(`/rental-quotes/${order.rental_quote_id}/`)
    inspectionContext.value = { quote: data, type: order.maintenance_type === 'POST_RENTAL' ? 'RETURN' : 'PRE_RENTAL', initialId: order.rental_inspection }
  } catch (event) {
    error.value = apiError(event)
  }
}

function openPlan(item = null) {
  editing.value = item
  modal.value = !can('maintenance.manage') && item ? 'plan-detail' : 'plan'
  error.value = ''
  Object.assign(planForm, item ? {
    equipment: item.equipment, name: item.name, maintenance_type: item.maintenance_type,
    interval_days: item.interval_days, usage_limit: item.usage_limit, next_due_date: item.next_due_date || '',
    last_service_date: item.last_service_date || '', last_service_usage_hours: item.last_service_usage_hours,
    advance_notice_days: item.advance_notice_days, advance_notice_usage_hours: item.advance_notice_usage_hours,
    criticality: item.criticality, checklist: item.checklist, active: item.active,
  } : {
    equipment: equipment.value[0]?.id || '', name: '', maintenance_type: 'PREVENTIVE', interval_days: 90,
    usage_limit: null, next_due_date: '', last_service_date: '', last_service_usage_hours: null,
    advance_notice_days: 15, advance_notice_usage_hours: 10, criticality: 'MEDIUM', checklist: [], active: true,
  })
}

async function persist(base, payload) {
  busy.value = true
  error.value = ''
  try {
    editing.value ? await api.patch(`${base}${editing.value.id}/`, payload) : await api.post(base, payload)
    modal.value = null
    editing.value = null
    await load()
  } catch (e) {
    error.value = apiError(e)
  } finally {
    busy.value = false
  }
}

const saveOrder = () => {
  const payload = {
    ...orderForm,
    technician: orderForm.technician || null,
    scheduled_at: orderForm.scheduled_at || null,
    abandoned_reason: orderForm.status === 'ABANDONED' ? orderForm.abandoned_reason : '',
  }
  if (editing.value) {
    delete payload.equipment
    delete payload.maintenance_type
    delete payload.symptoms
  }
  return persist('/service-orders/', payload)
}
const saveQuickOrder = () => persist('/service-orders/', {
  equipment: orderForm.equipment,
  maintenance_type: orderForm.maintenance_type,
  symptoms: orderForm.symptoms.trim(),
  priority: orderForm.priority,
  technician: orderForm.technician || null,
  scheduled_at: orderForm.scheduled_at || null,
  status: orderForm.scheduled_at ? 'SCHEDULED' : 'OPEN',
})
const saveLinkedOrder = () => persist('/service-orders/', {
  status: orderForm.status,
  priority: orderForm.priority,
  technician: orderForm.technician || null,
  scheduled_at: orderForm.scheduled_at || null,
  diagnosis: orderForm.diagnosis,
  abandoned_reason: orderForm.status === 'ABANDONED' ? orderForm.abandoned_reason : '',
  ...(repairAfterCancellation.value ? { final_tests: orderForm.final_tests, released: orderForm.released } : {}),
})
const savePlan = () => persist('/maintenance-plans/', {
  ...planForm,
  interval_days: planForm.interval_days || null,
  usage_limit: planForm.usage_limit || null,
  next_due_date: planForm.next_due_date || null,
  last_service_date: planForm.last_service_date || null,
  last_service_usage_hours: planForm.last_service_usage_hours === '' ? null : planForm.last_service_usage_hours,
})
function requestDelete(kind, item) { deleting.value = { kind, item } }
async function remove() {
  busy.value = true
  const base = deleting.value.kind === 'order' ? '/service-orders/' : '/maintenance-plans/'
  try {
    await api.delete(`${base}${deleting.value.item.id}/`)
    deleting.value = null
    await load()
  } catch (e) {
    error.value = apiError(e)
    deleting.value = null
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  try {
    await load()
    if (route.query.quote) {
      tab.value = 'rental'
      queue.value = 'ALL'
      search.value = String(route.query.quote)
    }
  } catch (event) {
    error.value = apiError(event)
  }
})
</script>

<template>
  <div class="page">
    <header class="page-heading compact">
      <div><span class="eyebrow">CONFIABILIDADE DA FROTA</span><h1>Manutenção</h1><p>Consulte a agenda do dia e acompanhe cada tipo de atendimento em seu lugar.</p></div>
    </header>

    <section v-if="alerts.length && ['calendar', 'preventive'].includes(tab)" class="maintenance-alert-note"><AlertTriangle :size="17" /><span><strong>{{ alerts.length }} plano(s) pedem atenção.</strong> Consulte os vencimentos na aba correspondente ou no calendário.</span><button @click="showAlertPlans">Ver planos</button></section>
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>

    <div class="maintenance-tabs" role="tablist" aria-label="Áreas da manutenção">
      <button v-for="item in maintenanceTabs" :key="item.key" role="tab" :aria-selected="tab === item.key" :class="{ active: tab === item.key }" @click="selectTab(item.key)"><component :is="item.icon" :size="18" /><span>{{ item.label }}</span><b v-if="item.count !== null">{{ item.count }}</b></button>
    </div>

    <template v-if="tab === 'calendar'"><div class="maintenance-intro-actions"><p>Os eventos com data aparecem no calendário; chamados sem agendamento ficam na lateral.</p><button v-if="can('maintenance.manage')" class="btn secondary" @click="openOrder()"><Plus :size="16" />Novo chamado</button></div><MaintenanceCalendar :orders="orders" :plans="plans" @open-order="openOrder" @open-plan="openPlan" /></template>

    <template v-else>
      <div class="maintenance-category-head"><div><span class="eyebrow">{{ tab === 'rental' ? 'ANTES E DEPOIS DA LOCAÇÃO' : tab === 'preventive' ? 'REVISÕES PROGRAMADAS' : 'REPAROS E FALHAS' }}</span><h2>{{ tab === 'rental' ? 'Manutenção da locação' : tab === 'preventive' ? 'Preventiva' : 'Corretiva' }}</h2><p>{{ tab === 'rental' ? 'Inspeções pré e pós-locação, vinculadas às reservas e devoluções.' : tab === 'preventive' ? 'Agende revisões, acompanhe chamados e gerencie planos recorrentes.' : 'Acompanhe falhas, diagnósticos, peças e liberação técnica.' }}</p></div><div v-if="can('maintenance.manage')" class="maintenance-category-actions"><button v-if="tab === 'preventive'" class="btn secondary" @click="openPlan()"><Plus :size="16" />Novo plano</button><button v-if="tab === 'preventive'" class="btn primary" @click="schedulePreventive"><CalendarDays :size="16" />Agendar preventiva</button><button v-if="tab === 'corrective'" class="btn primary" @click="openOrder(null, { maintenance_type: 'CORRECTIVE' })"><Plus :size="16" />Novo chamado</button></div></div>
      <section class="panel list-panel">
        <header class="list-toolbar maintenance-list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Buscar OS, reserva, equipamento ou técnico" /></div><select v-model="queue" aria-label="Filtrar por etapa"><option v-for="item in queueTabs" :key="item.key" :value="item.key">{{ item.label }} ({{ item.count }})</option></select><span class="result-count">{{ filteredOrders.length }} chamado(s)</span></header>
        <div class="table-wrap desktop-list"><table><thead><tr><th>OS</th><th>Equipamento</th><th>Tipo</th><th>Técnico</th><th>Agenda</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody>
          <tr v-for="order in filteredOrders" :key="order.id"><td><strong>{{ order.number }}</strong><small>{{ order.priority }}</small></td><td>{{ order.equipment_name }}</td><td>{{ order.maintenance_type_label }}<small v-if="order.rental_quote_number">Reserva {{ order.rental_quote_number }}</small></td><td><span :class="{ 'unassigned-label': !order.technician_name }">{{ order.technician_name || 'Sem técnico' }}</span></td><td>{{ order.scheduled_at ? shortDate(scheduledDay(order.scheduled_at)) : 'Sem data' }}<small v-if="order.scheduled_at">{{ new Date(order.scheduled_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) }}</small></td><td><StatusBadge :value="order.status" :label="order.status_label" /><small v-if="order.status === 'ABANDONED'" class="abandoned-note">{{ order.abandoned_reason }}</small></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Mídias do equipamento" @click="mediaEquipment = equipmentById(order.equipment)"><Files :size="17" /></button><button v-if="order.rental_inspection" class="btn secondary inspection-row-button" @click="openInspection(order)"><ClipboardPlus :size="15" />{{ order.status === 'COMPLETED' ? 'Ver inspeção' : 'Checklist' }}</button><button v-if="can('maintenance.manage')" class="icon-btn table-action" title="Registrar atendimento" @click="openOrder(order)"><Pencil :size="17" /></button><button v-if="can('maintenance.manage') && !order.rental_inspection" class="icon-btn danger-icon" title="Excluir chamado" @click="requestDelete('order', order)"><Trash2 :size="17" /></button></div></td></tr>
          <tr v-if="!filteredOrders.length"><td colspan="7" class="empty-cell"><ClipboardPlus :size="22" />Nenhum chamado nesta fila.</td></tr>
        </tbody></table></div>
        <div class="mobile-card-list">
          <article v-for="order in filteredOrders" :key="order.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ order.number }} · {{ order.priority }}</span><strong>{{ order.equipment_name }}</strong></div><StatusBadge :value="order.status" :label="order.status_label" /></header><dl><div><dt>Tipo</dt><dd>{{ order.maintenance_type_label }}</dd></div><div><dt>Técnico</dt><dd>{{ order.technician_name || 'Sem técnico' }}</dd></div><div><dt>Agenda</dt><dd>{{ order.scheduled_at ? shortDate(scheduledDay(order.scheduled_at)) : 'Sem data' }}</dd></div><div v-if="order.rental_quote_number"><dt>Reserva</dt><dd>{{ order.rental_quote_number }}</dd></div></dl><p v-if="order.status === 'ABANDONED'" class="abandoned-callout"><strong>Motivo do abandono</strong>{{ order.abandoned_reason }}</p><footer><button class="btn secondary" @click="mediaEquipment = equipmentById(order.equipment)"><Files :size="16" />Mídias</button><button v-if="order.rental_inspection" class="btn primary" @click="openInspection(order)"><ClipboardPlus :size="16" />Checklist</button><button v-if="can('maintenance.manage')" class="btn secondary" @click="openOrder(order)"><Pencil :size="16" />Atendimento</button></footer></article>
          <div v-if="!filteredOrders.length" class="empty-state compact"><ClipboardPlus :size="26" /><h2>Nenhum chamado nesta fila</h2></div>
        </div>
      </section>

    <details v-if="tab === 'preventive' || categoryPlans.length" :open="plansExpanded" class="panel list-panel maintenance-plan-details" @toggle="plansExpanded = $event.target.open"><summary><span><CalendarDays :size="18" /><strong>{{ tab === 'rental' ? 'Planos ligados à locação' : 'Planos recorrentes e por uso' }}</strong></span><b>{{ categoryPlans.length }} plano(s)</b></summary>
      <div class="table-wrap desktop-list"><table><thead><tr><th>Plano</th><th>Equipamento</th><th>Modalidade</th><th>Próxima execução</th><th>Gatilho por uso</th><th>Criticidade</th><th>Alerta</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="plan in categoryPlans" :key="plan.id"><td><strong>{{ plan.name }}</strong><small v-if="!plan.active">Plano inativo</small></td><td>{{ plan.equipment_name }}</td><td>{{ plan.maintenance_type_label }}</td><td><strong>{{ plan.due_date ? shortDate(plan.due_date) : 'Sem data' }}</strong><small v-if="plan.interval_days">a cada {{ plan.interval_days }} dias</small></td><td><strong>{{ plan.due_usage_hours !== null ? `${plan.due_usage_hours} h` : 'Não configurado' }}</strong><small v-if="plan.usage_remaining !== null">{{ plan.usage_remaining >= 0 ? `${plan.usage_remaining} h restantes` : `${Math.abs(plan.usage_remaining)} h excedidas` }}</small></td><td>{{ plan.criticality_label }}</td><td><StatusBadge :value="plan.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Mídias do equipamento" @click="mediaEquipment = equipmentById(plan.equipment)"><Files :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn table-action" title="Editar plano" @click="openPlan(plan)"><Pencil :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn danger-icon" title="Excluir plano" @click="requestDelete('plan', plan)"><Trash2 :size="17" /></button></div></td></tr><tr v-if="!categoryPlans.length"><td colspan="8" class="empty-cell">Nenhum plano de manutenção cadastrado.</td></tr></tbody></table></div>
      <div class="mobile-card-list"><article v-for="plan in categoryPlans" :key="plan.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ plan.maintenance_type_label }} · {{ plan.criticality_label }}</span><strong>{{ plan.name }}</strong><small>{{ plan.equipment_name }}</small></div><StatusBadge :value="plan.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></header><dl><div><dt>Próxima data</dt><dd>{{ plan.due_date ? shortDate(plan.due_date) : 'Não configurada' }}</dd></div><div><dt>Próximo uso</dt><dd>{{ plan.due_usage_hours !== null ? `${plan.due_usage_hours} h` : 'Não configurado' }}</dd></div><div><dt>Margem de uso</dt><dd>{{ plan.usage_remaining !== null ? `${plan.usage_remaining} h` : '—' }}</dd></div></dl><footer><button class="btn secondary" @click="mediaEquipment = equipmentById(plan.equipment)"><Files :size="15" />Mídias</button><button v-if="can('maintenance.manage')" class="btn secondary" @click="openPlan(plan)"><Pencil :size="15" />Editar plano</button></footer></article><div v-if="!categoryPlans.length" class="empty-state compact"><CalendarDays :size="26" /><h2>Nenhum plano cadastrado</h2></div></div>
    </details>
    </template>

    <ModalDialog v-if="modal === 'order-detail'" :title="editing.number" @close="modal = null"><div class="maintenance-readonly-detail"><StatusBadge :value="editing.status" :label="editing.status_label" /><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }} · {{ editing.technician_name || 'Sem técnico' }}</p><dl><div><dt>Agendamento</dt><dd>{{ editing.scheduled_at ? `${shortDate(scheduledDay(editing.scheduled_at))} às ${new Date(editing.scheduled_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : 'Sem data' }}</dd></div><div><dt>Solicitação</dt><dd>{{ editing.symptoms }}</dd></div><div v-if="editing.diagnosis"><dt>Diagnóstico</dt><dd>{{ editing.diagnosis }}</dd></div><div v-if="editing.abandoned_reason"><dt>Motivo do abandono</dt><dd>{{ editing.abandoned_reason }}</dd></div></dl><button v-if="editing.rental_inspection" class="btn secondary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />Ver inspeção</button></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null">Fechar</button></div></ModalDialog>
    <ModalDialog v-if="modal === 'plan-detail'" :title="editing.name" @close="modal = null"><div class="maintenance-readonly-detail"><StatusBadge :value="editing.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[editing.alert_status]" /><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }} · {{ editing.criticality_label }}</p><dl><div><dt>Próxima execução</dt><dd>{{ editing.due_date ? shortDate(editing.due_date) : 'Sem data' }}</dd></div><div v-if="editing.interval_days"><dt>Periodicidade</dt><dd>A cada {{ editing.interval_days }} dias</dd></div><div v-if="editing.due_usage_hours !== null"><dt>Gatilho por uso</dt><dd>{{ editing.due_usage_hours }} h</dd></div></dl></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null">Fechar</button></div></ModalDialog>

    <ModalDialog v-if="modal === 'linked-order'" :title="`Atendimento ${editing.number}`" wide @close="modal = null">
      <form class="service-order-form" @submit.prevent="saveLinkedOrder">
        <div class="order-form-intro"><ClipboardPlus :size="22" /><div><strong>Inspeção pré-locação · {{ editing.rental_quote_number }}</strong><span>{{ repairAfterCancellation ? 'Reserva cancelada após falha: repare e libere o equipamento neste chamado.' : `${editing.equipment_name}. A entrega só é liberada após o checklist ser aprovado.` }}</span></div></div>
        <section class="order-form-section"><header><span>01</span><div><h3>Chamado e triagem</h3><p>Organize o responsável e a etapa do atendimento</p></div></header><div class="form-grid">
          <div class="form-field span-2"><label>Solicitação</label><div class="order-readout">{{ editing.symptoms }}</div></div>
          <div class="form-field"><label>Etapa</label><select v-model="orderForm.status" :disabled="!linkedOrderEditable"><option value="OPEN">Aberto</option><option value="SCHEDULED">Agendado</option><option value="IN_PROGRESS">Em andamento</option><option value="WAITING_PARTS">Aguardando peças</option><option value="ABANDONED">Abandonado</option><option v-if="repairAfterCancellation || editing.status === 'COMPLETED'" value="COMPLETED">Concluído</option><option v-if="editing.status === 'CANCELLED'" value="CANCELLED">Cancelado</option></select></div>
          <div class="form-field"><label>Prioridade</label><select v-model="orderForm.priority" :disabled="!linkedOrderEditable"><option>NORMAL</option><option>ALTA</option><option>CRÍTICA</option></select></div>
          <div class="form-field"><label>Técnico responsável</label><select v-model="orderForm.technician" :disabled="!linkedOrderEditable" :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status)"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
          <div class="form-field"><label>Agendamento</label><input v-model="orderForm.scheduled_at" type="datetime-local" :disabled="!linkedOrderEditable" :required="orderForm.status === 'SCHEDULED'" /></div>
          <div v-if="orderForm.status === 'ABANDONED'" class="form-field span-2"><label>Motivo do abandono</label><textarea v-model="orderForm.abandoned_reason" rows="3" required :disabled="!linkedOrderEditable" /></div>
          <div class="form-field span-2"><label>Notas do atendimento</label><textarea v-model="orderForm.diagnosis" rows="3" :disabled="!linkedOrderEditable" placeholder="O que foi encontrado? Registre o andamento antes de finalizar o checklist." /></div>
          <template v-if="repairAfterCancellation"><div class="form-field span-2"><label>Testes finais do reparo</label><textarea v-model="orderForm.final_tests" rows="3" :disabled="!linkedOrderEditable" placeholder="Descreva os testes que comprovam que o equipamento voltou a operar." /></div><label v-if="orderForm.status === 'COMPLETED'" class="check-line span-2 order-release"><input v-model="orderForm.released" type="checkbox" :disabled="!linkedOrderEditable" />Liberar equipamento após reparo</label></template>
        </div></section>
        <div class="order-checklist-cta"><div><strong>{{ repairAfterCancellation ? 'Inspeção original' : 'Pronto para inspecionar?' }}</strong><span>{{ repairAfterCancellation ? 'Confira a falha e as evidências que originaram este reparo.' : 'Abra o checklist do equipamento para registrar conformidade, falhas e evidências.' }}</span></div><button type="button" class="btn secondary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />Abrir checklist</button></div>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Fechar</button><span class="spacer" /><button v-if="linkedOrderEditable" class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar atendimento' }}</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'quick-order'" title="Abrir chamado" @close="modal = null">
      <form class="quick-order-form" @submit.prevent="saveQuickOrder">
        <p class="quick-order-lead">Registre a solicitação agora. Diagnóstico, peças e testes ficam para o atendimento.</p>
        <div class="form-field"><label for="quick-equipment">Equipamento</label><select id="quick-equipment" v-model="orderForm.equipment" required><option value="" disabled>Selecione o equipamento</option><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></select></div>
        <div class="form-field"><label for="quick-symptoms">O que precisa ser feito?</label><textarea id="quick-symptoms" v-model="orderForm.symptoms" rows="3" required placeholder="Ex.: Betoneira não liga; verificar motor e cabo." /></div>
        <div class="form-field"><label for="quick-type">Tipo de chamado</label><select id="quick-type" v-model="orderForm.maintenance_type"><option value="CORRECTIVE">Corretiva · falha ou reparo</option><option value="PREVENTIVE">Preventiva · revisão programada</option></select></div>
        <details class="quick-order-options" :open="quickPlanning" @toggle="quickPlanning = $event.target.open"><summary>{{ orderForm.scheduled_at ? `Agendado para ${orderForm.scheduled_at.replace('T', ' · ')}` : 'Planejar agora (opcional)' }}</summary><div class="form-grid"><div class="form-field"><label for="quick-priority">Prioridade</label><select id="quick-priority" v-model="orderForm.priority"><option value="NORMAL">Normal</option><option value="ALTA">Alta</option><option value="CRÍTICA">Crítica</option></select></div><div class="form-field"><label for="quick-technician">Técnico</label><select id="quick-technician" v-model="orderForm.technician"><option value="">Definir depois</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div><div class="form-field span-2"><label for="quick-schedule">Data e hora</label><input id="quick-schedule" v-model="orderForm.scheduled_at" type="datetime-local" :required="quickPlanning && orderForm.status === 'SCHEDULED'" /><small>Sem data, o chamado entra na fila como aberto.</small></div></div></details>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy || !equipment.length">{{ busy ? 'Abrindo...' : 'Abrir chamado' }}</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'order'" :title="`Editar ${editing.number}`" wide @close="modal = null">
      <form class="service-order-form" @submit.prevent="saveOrder">
        <div class="order-form-intro"><Wrench :size="22" /><div><strong>{{ editing ? 'Registro técnico' : 'Novo atendimento' }}</strong><span>{{ editing?.maintenance_type === 'POST_RENTAL' ? 'Reparo pós-locação vinculado à inspeção de devolução.' : 'Organize o chamado e registre o que precisa ser verificado no equipamento.' }}</span></div></div>
        <section class="order-form-section"><header><span>01</span><div><h3>Identificação</h3><p>Dados da abertura da OS; não podem ser alterados durante o atendimento</p></div></header><div class="form-grid">
          <div class="form-field"><span class="order-readout-label">Equipamento</span><div class="order-readout">{{ equipmentById(editing.equipment)?.internal_code || 'Equipamento' }} · {{ editing.equipment_name }}</div></div>
          <div class="form-field"><span class="order-readout-label">Tipo de manutenção</span><div class="order-readout">{{ editing.maintenance_type_label }}</div></div>
          <div class="form-field span-2"><span class="order-readout-label">Sintomas / relato inicial</span><div class="order-readout order-readout-multiline">{{ editing.symptoms }}</div></div>
        </div></section>
        <section class="order-form-section"><header><span>02</span><div><h3>Planejamento e responsável</h3><p>Defina a fila, a prioridade e quem irá atender</p></div></header><div class="form-grid">
          <div class="form-field"><label>Status do chamado</label><select v-model="orderForm.status"><option value="OPEN">Aberto</option><option value="SCHEDULED">Agendado</option><option value="IN_PROGRESS">Em andamento</option><option value="WAITING_PARTS">Aguardando peças</option><option value="ABANDONED">Abandonado</option><option value="COMPLETED">Concluído</option><option value="CANCELLED">Cancelado</option></select></div>
          <div class="form-field"><label>Prioridade</label><select v-model="orderForm.priority"><option>NORMAL</option><option>ALTA</option><option>CRÍTICA</option></select></div>
          <div class="form-field"><label>Técnico responsável</label><select v-model="orderForm.technician" :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status)"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
          <div class="form-field"><label>Agendamento</label><input v-model="orderForm.scheduled_at" type="datetime-local" :required="orderForm.status === 'SCHEDULED'" /></div>
          <div v-if="orderForm.status === 'ABANDONED'" class="form-field span-2 abandonment-field"><label>Motivo do abandono</label><textarea v-model="orderForm.abandoned_reason" rows="3" required placeholder="Por que o atendimento foi interrompido? O que falta para retomar?" /><small>O equipamento permanece bloqueado.</small></div>
        </div></section>
        <section v-if="editing" class="order-form-section"><header><span>03</span><div><h3>Execução e liberação</h3><p>Registre diagnóstico, recursos usados e testes finais</p></div></header><div class="form-grid">
          <div class="form-field span-2"><label>Diagnóstico</label><textarea v-model="orderForm.diagnosis" rows="3" placeholder="Causa encontrada e serviço realizado." /></div>
          <div class="form-field"><label>Horas de mão de obra</label><input v-model="orderForm.labor_hours" type="number" min="0" step="0.25" /></div>
          <div class="form-field"><label>Peças utilizadas</label><textarea v-model="orderForm.parts_used" rows="2" /></div>
          <div class="form-field span-2"><label>Testes finais</label><textarea v-model="orderForm.final_tests" rows="3" placeholder="Descreva como o funcionamento foi validado." /></div>
          <label v-if="can('maintenance.release') && orderForm.status === 'COMPLETED'" class="check-line span-2 order-release"><input v-model="orderForm.released" type="checkbox" />Liberar equipamento após validação técnica</label>
        </div></section>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar chamado' }}</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'plan'" :title="editing ? 'Editar plano de manutenção' : 'Cadastrar plano de manutenção'" wide @close="modal = null"><form @submit.prevent="savePlan"><div class="form-grid three">
      <div class="form-field span-2"><label>Nome do plano</label><input v-model="planForm.name" required /></div><div class="form-field"><label>Criticidade</label><select v-model="planForm.criticality"><option value="LOW">Baixa</option><option value="MEDIUM">Média</option><option value="HIGH">Alta</option><option value="CRITICAL">Crítica</option></select></div>
      <div class="form-field span-2"><label>Equipamento</label><select v-model="planForm.equipment" required><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }} · {{ item.current_usage_hours }} h</option></select></div><div class="form-field"><label>Modalidade</label><select v-model="planForm.maintenance_type"><option value="PREVENTIVE">Preventiva</option><option value="SCHEDULED">Agendada</option><option value="PRE_RENTAL">Antes da locação</option><option value="POST_RENTAL">Pós-locação</option></select></div>
      <div class="form-field"><label>Periodicidade (dias)</label><input v-model="planForm.interval_days" type="number" min="1" placeholder="Ex.: 90" /></div><div class="form-field"><label>Última manutenção</label><input v-model="planForm.last_service_date" type="date" /></div><div class="form-field"><label>Próxima execução</label><input v-model="planForm.next_due_date" type="date" /></div>
      <div class="form-field"><label>Periodicidade por uso (h)</label><input v-model="planForm.usage_limit" type="number" min="1" placeholder="Ex.: 250" /></div><div class="form-field"><label>Horas na última manutenção</label><input v-model="planForm.last_service_usage_hours" type="number" min="0" /></div><div class="form-field"><label>Alertar antes (horas)</label><input v-model="planForm.advance_notice_usage_hours" type="number" min="0" /></div>
      <div class="form-field"><label>Alertar antes (dias)</label><input v-model="planForm.advance_notice_days" type="number" min="0" /></div><div class="plan-help span-2"><AlertTriangle :size="18" /><span>Planos críticos vencidos por data ou horas bloqueiam novas reservas e a entrega do equipamento.</span></div>
      <label class="check-line span-3"><input v-model="planForm.active" type="checkbox" />Plano ativo e participando dos alertas</label>
    </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar plano' }}</button></div></form></ModalDialog>

    <EquipmentMediaModal v-if="mediaEquipment" :equipment="mediaEquipment" @close="mediaEquipment = null" @changed="load" />
    <RentalInspectionModal v-if="inspectionContext" :quote="inspectionContext.quote" :type="inspectionContext.type" :initial-id="inspectionContext.initialId" @close="inspectionContext = null" @changed="load" />
    <ConfirmDialog v-if="deleting" :title="deleting.kind === 'order' ? 'Excluir chamado' : 'Excluir plano'" :message="`Excluir “${deleting.item.number || deleting.item.name}”? Esta ação não pode ser desfeita.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
