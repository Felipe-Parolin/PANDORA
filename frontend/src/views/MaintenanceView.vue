<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertTriangle, CalendarDays, ChevronDown, ClipboardPlus, Files, Plus, Search, Trash2, Wrench,
} from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import MaintenanceOrderCard from '../components/MaintenanceOrderCard.vue'
import ModalDialog from '../components/ModalDialog.vue'
import RentalInspectionModal from '../components/RentalInspectionModal.vue'
import WorkshopOrderModal from '../components/WorkshopOrderModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, auth, can, rows, shortDate } from '../services/api'
import { isOpenServiceOrder, serviceOrderState, serviceOrderStateLabel } from '../services/maintenance'

const tab = ref('rental')
const route = useRoute()
const queue = ref('OPEN')
const plansExpanded = ref(false)
const search = ref('')
const orders = ref([])
const plans = ref([])
const equipment = ref([])
const technicians = ref([])
const modal = ref(null)
const planAdvanced = ref(false)
const editing = ref(null)
const deleting = ref(null)
const mediaEquipment = ref(null)
const mediaReturnModal = ref(null)
const inspectionContext = ref(null)
const expandedRentalGroup = ref(null)
const error = ref('')
const busy = ref(false)
const quickPlanning = ref(false)

const orderForm = reactive({
  equipment: '', maintenance_type: 'CORRECTIVE', priority: 'NORMAL', symptoms: '',
  diagnosis: '', technician: '', status: 'OPEN', scheduled_at: '', final_tests: '',
  released: false, labor_hours: 0, labor_cost: 0, parts_cost: 0, parts_used: '', abandoned_reason: '',
})
const planForm = reactive({
  equipment: '', name: '', maintenance_type: 'PREVENTIVE', interval_days: 90, usage_limit: null,
  next_due_date: '', last_service_date: '', last_service_usage_hours: null, advance_notice_days: 15,
  advance_notice_usage_hours: 10, criticality: 'MEDIUM', active: true,
})

const alerts = computed(() => plans.value.filter(item => ['OVERDUE', 'CRITICAL', 'UPCOMING'].includes(item.alert_status)))
const alertTarget = computed(() => alerts.value.some(item => ['PREVENTIVE', 'SCHEDULED'].includes(item.maintenance_type)) ? 'workshop' : 'rental')
const terminalStatuses = ['COMPLETED', 'CANCELLED']
const visibleOrders = computed(() => orders.value.filter(item => item.status !== 'CANCELLED'))
const rentalOrders = computed(() => visibleOrders.value.filter(item => ['PRE_RENTAL', 'POST_RENTAL'].includes(item.maintenance_type)))
const rentalGroupKey = order => order.rental_quote_id ? `quote-${order.rental_quote_id}` : 'unlinked'
const maintenanceTabs = computed(() => [
  { key: 'rental', label: 'Locação', icon: ClipboardPlus, count: new Set(rentalOrders.value.map(rentalGroupKey)).size },
  { key: 'workshop', label: 'Oficina e revisões', icon: Wrench, count: visibleOrders.value.filter(item => ['PREVENTIVE', 'SCHEDULED', 'CORRECTIVE'].includes(item.maintenance_type)).length },
])
const categoryOrders = computed(() => visibleOrders.value.filter(order => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  workshop: ['PREVENTIVE', 'SCHEDULED', 'CORRECTIVE'],
})[tab.value]?.includes(order.maintenance_type)).sort((a, b) =>
  Number(terminalStatuses.includes(a.status)) - Number(terminalStatuses.includes(b.status))
  || Number(b.priority === 'CRÍTICA') - Number(a.priority === 'CRÍTICA')
  || (a.scheduled_at || '').localeCompare(b.scheduled_at || '')
))
const openOrderCount = computed(() => categoryOrders.value.filter(order => isOpenServiceOrder(order.status)).length)
const categoryPlans = computed(() => plans.value.filter(plan => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  workshop: ['PREVENTIVE', 'SCHEDULED'],
})[tab.value]?.includes(plan.maintenance_type)))
const matchesQueue = (order, key) => serviceOrderState(order.status) === key
const queueTabs = computed(() => [
  { key: 'OPEN', label: 'Em aberto' },
  { key: 'COMPLETED', label: 'Concluído' },
].map(item => ({ ...item, count: categoryOrders.value.filter(order => matchesQueue(order, item.key)).length })))
const filteredOrders = computed(() => {
  const term = search.value.trim().toLocaleLowerCase('pt-BR')
  return categoryOrders.value.filter(order => matchesQueue(order, queue.value)).filter(order => !term || [
    order.number, order.equipment_name, order.technician_name, order.symptoms, order.rental_quote_number, order.rental_customer_name,
  ].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const rentalGroups = computed(() => {
  const groups = new Map()
  for (const order of filteredOrders.value) {
    const key = rentalGroupKey(order)
    if (!groups.has(key)) groups.set(key, {
      key,
      number: order.rental_quote_number || 'Sem locação vinculada',
      customer: order.rental_customer_name || '',
      startDate: order.rental_start_date,
      endDate: order.rental_end_date,
      status: order.rental_quote_status,
      orders: [],
    })
    groups.get(key).orders.push(order)
  }
  return [...groups.values()].map(group => ({
    ...group,
    openCount: group.orders.filter(order => isOpenServiceOrder(order.status)).length,
    equipmentSummary: [...new Set(group.orders.map(order => order.equipment_name))].join(' · '),
  }))
})
const rentalStatusLabel = status => ({
  APPROVED: 'Reservada', ACTIVE: 'Em locação', RETURNED: 'Em inspeção',
  COMPLETED: 'Concluída', CANCELLED: 'Cancelada',
})[status] || status || 'Sem vínculo'
const repairAfterCancellation = computed(() => editing.value?.rental_quote_status === 'CANCELLED' && editing.value?.inspection_result === 'BLOCKED')
const linkedOrderEditable = computed(() => can('maintenance.manage') && editing.value && !terminalStatuses.includes(editing.value.status) && (editing.value.rental_quote_status === 'APPROVED' || repairAfterCancellation.value))
const equipmentById = id => equipment.value.find(item => item.id === id)
function openMedia(equipmentId) {
  const item = equipmentById(equipmentId)
  if (!item) {
    error.value = 'Não foi possível localizar o equipamento desta OS.'
    return
  }
  mediaReturnModal.value = modal.value
  modal.value = null
  mediaEquipment.value = item
}
function closeMedia() {
  mediaEquipment.value = null
  if (mediaReturnModal.value) {
    modal.value = mediaReturnModal.value
    mediaReturnModal.value = null
  }
}
const toLocalInput = value => {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const planPreviewDate = computed(() => {
  if (planForm.next_due_date) return planForm.next_due_date
  if (!Number(planForm.interval_days)) return ''
  const base = planForm.last_service_date
    ? new Date(`${planForm.last_service_date}T12:00:00`)
    : editing.value?.created_at ? new Date(editing.value.created_at) : new Date()
  base.setDate(base.getDate() + Number(planForm.interval_days))
  return toLocalInput(base).slice(0, 10)
})

async function load() {
  if (can('maintenance.manage')) {
    try {
      await api.post('/maintenance-plans/sync-due/')
    } catch (event) {
      error.value = `Não foi possível verificar os planos vencidos: ${apiError(event)}`
    }
  }
  const [o, p, e, u] = await Promise.all([
    api.get('/service-orders/'), api.get('/maintenance-plans/'), api.get('/equipment/'),
    can('accounts.users.view') ? api.get('/users/') : Promise.resolve({ data: [] }),
  ])
  orders.value = rows(o.data)
  plans.value = rows(p.data)
  equipment.value = rows(e.data)
  technicians.value = rows(u.data).filter(user => user.permissions.includes('*') || user.permissions.includes('maintenance.manage'))
  if (can('maintenance.manage') && auth.user && !technicians.value.some(user => user.id === auth.user.id)) {
    technicians.value.push({ id: auth.user.id, full_name: auth.user.full_name || auth.user.email })
  }
}

function openOrder(item = null, defaults = {}) {
  if (item?.technician && !technicians.value.some(user => user.id === item.technician)) {
    technicians.value.push({ id: item.technician, full_name: item.technician_name || 'Técnico atual' })
  }
  editing.value = item
  modal.value = !item ? 'quick-order'
    : !item.rental_inspection ? 'workshop-order'
    : !can('maintenance.manage') || terminalStatuses.includes(item.status) ? 'order-detail'
      : item.rental_inspection && item.maintenance_type === 'PRE_RENTAL' ? 'linked-order'
        : item.rental_inspection && item.maintenance_type === 'POST_RENTAL' && item.inspection_result === 'PENDING' ? 'return-order'
          : 'order'
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
    labor_cost: item.labor_cost,
    parts_cost: item.parts_cost,
    parts_used: item.parts_used,
    abandoned_reason: item.abandoned_reason || '',
  } : {
    equipment: '', maintenance_type: 'CORRECTIVE', priority: 'NORMAL',
    symptoms: '', diagnosis: '', technician: '', status: 'OPEN', scheduled_at: '', final_tests: '',
    released: false, labor_hours: 0, labor_cost: 0, parts_cost: 0, parts_used: '', abandoned_reason: '', ...defaults,
  })
}

function selectTab(key) {
  tab.value = key
  queue.value = 'OPEN'
  search.value = ''
  expandedRentalGroup.value = null
  plansExpanded.value = false
}

function showAlertPlans() {
  selectTab(alertTarget.value)
  plansExpanded.value = true
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
  planAdvanced.value = false
  Object.assign(planForm, item ? {
    equipment: item.equipment, name: item.name, maintenance_type: item.maintenance_type,
    interval_days: item.interval_days, usage_limit: item.usage_limit, next_due_date: item.next_due_date || '',
    last_service_date: item.last_service_date || '', last_service_usage_hours: item.last_service_usage_hours,
    advance_notice_days: item.advance_notice_days, advance_notice_usage_hours: item.advance_notice_usage_hours,
    criticality: item.criticality, active: item.active,
  } : {
    equipment: '', name: '', maintenance_type: 'PREVENTIVE', interval_days: 90,
    usage_limit: null, next_due_date: '', last_service_date: '', last_service_usage_hours: null,
    advance_notice_days: 15, advance_notice_usage_hours: 10, criticality: 'MEDIUM', active: true,
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

function validateRepairCompletion() {
  if (!can('maintenance.release') || !orderForm.technician || !orderForm.final_tests.trim()) {
    error.value = 'Para concluir e liberar, informe o técnico e os testes finais. É necessária permissão de liberação.'
    return false
  }
  return true
}
const saveOrder = (conclude = false) => {
  if (conclude && !validateRepairCompletion()) return
  const payload = {
    technician: orderForm.technician || null,
    diagnosis: orderForm.diagnosis,
    final_tests: orderForm.final_tests,
    ...(conclude ? { status: 'COMPLETED', released: true } : {}),
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
const saveLinkedOrder = (conclude = false) => {
  if (conclude && (!repairAfterCancellation.value || !validateRepairCompletion())) return
  return persist('/service-orders/', {
    technician: orderForm.technician || null,
    diagnosis: orderForm.diagnosis,
    ...(repairAfterCancellation.value ? { final_tests: orderForm.final_tests } : {}),
    ...(conclude ? { status: 'COMPLETED', released: true } : {}),
  })
}
const savePlan = () => persist('/maintenance-plans/', {
  ...planForm,
  name: planForm.name.trim() || `Revisão periódica · ${equipmentById(planForm.equipment)?.internal_code || 'equipamento'}`,
  interval_days: planForm.interval_days || null,
  usage_limit: planForm.usage_limit || null,
  next_due_date: planForm.next_due_date || null,
  last_service_date: planForm.last_service_date || null,
  last_service_usage_hours: planForm.last_service_usage_hours === '' ? null : planForm.last_service_usage_hours,
})
async function workshopChanged() {
  modal.value = null
  editing.value = null
  try { await load() } catch (event) { error.value = apiError(event) }
}
function requestDelete(kind, item) {
  modal.value = null
  deleting.value = { kind, item }
}
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
function applyRouteContext() {
  if (route.query.order) {
    const matched = orders.value.find(order => String(order.id) === String(route.query.order))
    if (matched) {
      tab.value = matched.rental_quote_number ? 'rental' : 'workshop'
      queue.value = serviceOrderState(matched.status) === 'COMPLETED' ? 'COMPLETED' : 'OPEN'
      search.value = ''
      if (matched.rental_quote_number) expandedRentalGroup.value = rentalGroupKey(matched)
      openOrder(matched)
    }
    return
  }
  if (route.query.quote) {
    tab.value = 'rental'
    search.value = String(route.query.quote)
    const linked = rentalOrders.value.filter(order => order.rental_quote_number === String(route.query.quote))
    const matched = linked.find(order => isOpenServiceOrder(order.status)) || linked[0]
    queue.value = matched ? serviceOrderState(matched.status) : 'OPEN'
    if (matched) expandedRentalGroup.value = rentalGroupKey(matched)
  }
}
watch(() => [route.query.order, route.query.quote], applyRouteContext)
onMounted(async () => {
  try {
    await load()
    applyRouteContext()
  } catch (event) {
    error.value = apiError(event)
  }
})
</script>

<template>
  <div class="page">
    <header class="page-heading compact">
      <div><span class="eyebrow">CONFIABILIDADE DA FROTA</span><h1>Manutenção</h1><p>Chamados e planos organizados por tipo de serviço.</p></div>
    </header>

    <section v-if="alerts.length" class="maintenance-alert-note"><AlertTriangle :size="17" /><span><strong>{{ alerts.length }} plano(s) pedem atenção.</strong> Confira os vencimentos antes de liberar equipamentos.</span><button @click="showAlertPlans">Ver planos</button></section>
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>

    <div class="maintenance-tabs" role="tablist" aria-label="Áreas da manutenção">
      <button v-for="item in maintenanceTabs" :key="item.key" role="tab" :aria-selected="tab === item.key" :class="{ active: tab === item.key }" @click="selectTab(item.key)"><component :is="item.icon" :size="18" /><span>{{ item.label }}</span><b>{{ item.count }}</b></button>
    </div>

    <div class="maintenance-category-head"><div><span class="eyebrow">{{ tab === 'rental' ? 'ANTES E DEPOIS DA LOCAÇÃO' : 'REPAROS E REVISÕES' }}</span><h2>{{ tab === 'rental' ? 'Manutenção da locação' : 'Oficina e revisões' }}</h2><p>{{ tab === 'rental' ? 'As OS surgem da reserva e da devolução. Abra uma locação para ver suas OS.' : 'Abra uma OS para acompanhar o atendimento e avaliar o equipamento.' }}</p><small class="maintenance-category-count">{{ openOrderCount }} OS em aberto · {{ categoryOrders.length }} OS no total</small></div><div v-if="can('maintenance.manage') && tab === 'workshop'" class="maintenance-category-actions"><button class="btn primary" @click="openOrder(null, { maintenance_type: 'CORRECTIVE' })"><Plus :size="16" />Nova OS</button></div></div>
      <div class="maintenance-sections">
      <section class="panel list-panel">
        <header class="list-toolbar maintenance-list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" :placeholder="tab === 'rental' ? 'Buscar locação, cliente, equipamento ou OS' : 'Buscar OS, equipamento ou técnico'" /></div><select v-model="queue" aria-label="Situação da OS"><option v-for="item in queueTabs" :key="item.key" :value="item.key">{{ item.label }} ({{ item.count }})</option></select><span class="result-count">{{ tab === 'rental' ? `${rentalGroups.length} locação(ões)` : `${filteredOrders.length} OS` }}</span></header>
        <div v-if="tab === 'rental'" class="maintenance-rental-groups">
          <article v-for="group in rentalGroups" :key="group.key" class="maintenance-rental-group">
            <button class="maintenance-rental-group-trigger" :aria-expanded="expandedRentalGroup === group.key" @click="expandedRentalGroup = expandedRentalGroup === group.key ? null : group.key">
              <span class="maintenance-rental-group-identity"><span class="eyebrow">LOCAÇÃO</span><strong>{{ group.number }}</strong><small>{{ group.customer || 'Cliente não informado' }}<template v-if="group.startDate && group.endDate"> · {{ shortDate(group.startDate) }} a {{ shortDate(group.endDate) }}</template></small></span>
              <span class="maintenance-rental-group-summary"><span class="maintenance-rental-state">{{ rentalStatusLabel(group.status) }}</span><b>{{ group.orders.length }} OS</b><small>{{ group.openCount }} em aberto</small></span>
              <ChevronDown :size="19" class="maintenance-rental-chevron" :class="{ expanded: expandedRentalGroup === group.key }" />
            </button>
            <p class="maintenance-rental-equipment">{{ group.equipmentSummary }}</p>
            <div v-if="expandedRentalGroup === group.key" class="maintenance-order-grid maintenance-rental-orders"><MaintenanceOrderCard v-for="order in group.orders" :key="order.id" :order="order" @open="openOrder(order)" /></div>
          </article>
          <div v-if="!rentalGroups.length" class="empty-state compact maintenance-order-empty"><ClipboardPlus :size="26" /><h2>Nenhuma locação neste filtro</h2><p v-if="categoryOrders.length">Selecione outra situação ou limpe a busca.</p><p v-else>As OS serão agrupadas pela locação quando uma reserva for aprovada.</p></div>
        </div>
        <div v-else class="maintenance-order-grid">
          <MaintenanceOrderCard v-for="order in filteredOrders" :key="order.id" :order="order" @open="openOrder(order)" />
          <div v-if="!filteredOrders.length" class="empty-state compact maintenance-order-empty"><Wrench :size="26" /><h2>Nenhuma OS neste filtro</h2><p v-if="categoryOrders.length">Selecione outra situação ou limpe a busca.</p><p v-else>Os chamados aparecerão aqui quando forem abertos.</p></div>
        </div>
      </section>

      <details v-if="tab === 'workshop' || categoryPlans.length" :open="plansExpanded" class="panel list-panel maintenance-plan-details" @toggle="plansExpanded = $event.target.open"><summary><span><CalendarDays :size="18" /><strong>{{ tab === 'rental' ? 'Planos ligados à locação' : 'Revisões automáticas' }}</strong></span><b>{{ categoryPlans.length }} cadastrada(s)</b></summary>
        <div v-if="tab === 'workshop'" class="maintenance-plan-toolbar"><span>Escolha o equipamento e o intervalo em dias. O sistema abre uma OS quando a revisão vence.</span><button v-if="can('maintenance.manage')" class="btn secondary" @click="openPlan()"><Plus :size="16" />Nova revisão automática</button></div>
        <div class="maintenance-plan-grid">
          <article v-for="plan in categoryPlans" :key="plan.id" class="maintenance-plan-card">
            <header><span class="eyebrow">REVISÃO AUTOMÁTICA</span><StatusBadge :value="plan.active ? plan.alert_status : 'CANCELLED'" :label="!plan.active ? 'Pausada' : ({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></header>
            <h3>{{ plan.equipment_name }}</h3><p>{{ plan.name }}</p>
            <dl class="simple-plan-summary"><div><dt>Repetir</dt><dd>{{ plan.interval_days ? `A cada ${plan.interval_days} dias` : 'Por data/uso' }}</dd></div><div><dt>Próxima revisão</dt><dd>{{ plan.due_date ? shortDate(plan.due_date) : 'Por horas de uso' }}</dd></div><div v-if="plan.due_usage_hours !== null"><dt>Também por uso</dt><dd>{{ plan.due_usage_hours }} h</dd></div></dl>
            <footer><button class="btn secondary" @click="openPlan(plan)">{{ can('maintenance.manage') ? 'Editar revisão' : 'Ver revisão' }}</button></footer>
          </article>
          <div v-if="!categoryPlans.length" class="empty-state compact maintenance-order-empty"><CalendarDays :size="26" /><h2>Nenhuma revisão automática</h2><p>Cadastre um equipamento e defina a revisão a cada X dias.</p></div>
        </div>
      </details>
      </div>

    <ModalDialog v-if="modal === 'order-detail'" :title="editing.number" @close="modal = null"><div class="maintenance-readonly-detail"><StatusBadge :value="serviceOrderState(editing.status)" :label="serviceOrderStateLabel(editing.status)" /><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }} · {{ editing.technician_name || 'Sem técnico' }}</p><dl><div><dt>Abertura</dt><dd>{{ shortDate(editing.opened_at?.slice(0, 10)) }}</dd></div><div><dt>Solicitação</dt><dd>{{ editing.symptoms }}</dd></div><div v-if="editing.diagnosis"><dt>Diagnóstico</dt><dd>{{ editing.diagnosis }}</dd></div><div v-if="editing.abandoned_reason"><dt>Observação histórica</dt><dd>{{ editing.abandoned_reason }}</dd></div></dl><div class="maintenance-order-tools"><button v-if="editing.rental_inspection" class="btn primary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />{{ editing.maintenance_type === 'POST_RENTAL' ? editing.inspection_result === 'PENDING' && (can('maintenance.manage') || can('rentals.inspect')) ? 'Abrir inspeção final' : 'Ver inspeção final' : 'Ver inspeção pré-locação' }}</button><button v-if="can('media.view')" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null">Fechar</button></div></ModalDialog>
    <ModalDialog v-if="modal === 'return-order'" :title="`Inspeção final · ${editing.number}`" @close="modal = null"><div class="maintenance-readonly-detail"><StatusBadge :value="serviceOrderState(editing.status)" :label="serviceOrderStateLabel(editing.status)" /><h3>{{ editing.equipment_name }}</h3><p>Locação {{ editing.rental_quote_number }} · devolução registrada</p><dl><div><dt>Solicitação</dt><dd>{{ editing.symptoms }}</dd></div><div><dt>Avaliação</dt><dd>Confirme se o equipamento está operante ou inoperante. Se houver avaria, esta mesma OS seguirá para reparo.</dd></div></dl><div class="maintenance-order-tools"><button class="btn primary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />Avaliar equipamento</button><button v-if="can('media.view')" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null">Fechar</button></div></ModalDialog>
    <ModalDialog v-if="modal === 'plan-detail'" :title="editing.name" @close="modal = null"><div class="maintenance-readonly-detail"><StatusBadge :value="editing.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[editing.alert_status]" /><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }} · {{ editing.criticality_label }}</p><dl><div><dt>Próxima execução</dt><dd>{{ editing.due_date ? shortDate(editing.due_date) : 'Sem data' }}</dd></div><div v-if="editing.interval_days"><dt>Periodicidade</dt><dd>A cada {{ editing.interval_days }} dias</dd></div><div v-if="editing.due_usage_hours !== null"><dt>Gatilho por uso</dt><dd>{{ editing.due_usage_hours }} h</dd></div></dl><div v-if="can('media.view')" class="maintenance-order-tools"><button class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null">Fechar</button></div></ModalDialog>

    <ModalDialog v-if="modal === 'linked-order'" :title="`Atendimento ${editing.number}`" wide @close="modal = null">
      <form class="service-order-form" @submit.prevent="saveLinkedOrder()">
        <div class="order-form-intro"><ClipboardPlus :size="22" /><div><strong>Avaliação pré-locação · {{ editing.rental_quote_number }}</strong><span>{{ repairAfterCancellation ? 'Reserva cancelada após falha: repare e libere o equipamento neste chamado.' : `${editing.equipment_name}. A entrega só é liberada quando o equipamento estiver operante.` }}</span></div></div>
        <section class="order-form-section"><header><span>01</span><div><h3>Atendimento</h3><p>Defina o responsável e registre a avaliação</p></div></header><div class="form-grid">
          <div class="form-field span-2"><label>Solicitação</label><div class="order-readout">{{ editing.symptoms }}</div></div>
          <div class="form-field span-2"><label>Técnico responsável</label><select v-model="orderForm.technician" :disabled="!linkedOrderEditable" :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status)"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
          <div class="form-field span-2"><label>Notas do atendimento</label><textarea v-model="orderForm.diagnosis" rows="3" :disabled="!linkedOrderEditable" placeholder="O que foi encontrado? Registre o andamento do atendimento." /></div>
          <div v-if="repairAfterCancellation" class="form-field span-2"><label>Testes finais do reparo</label><textarea v-model="orderForm.final_tests" rows="3" :disabled="!linkedOrderEditable" placeholder="Descreva os testes que comprovam que o equipamento voltou a operar." /></div>
        </div></section>
        <div class="order-assessment-cta"><div><strong>{{ repairAfterCancellation ? 'Avaliação original' : 'Condição do equipamento' }}</strong><span>{{ repairAfterCancellation ? 'Confira a falha que originou este reparo.' : 'Registre se está operante ou inoperante antes de liberar a locação.' }}</span></div><button type="button" class="btn primary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />{{ editing.status === 'COMPLETED' ? 'Ver avaliação' : 'Avaliar equipamento' }}</button></div>
        <div v-if="can('media.view')" class="maintenance-order-tools"><button type="button" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Fechar</button><span class="spacer" /><button v-if="linkedOrderEditable" class="btn secondary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar atendimento' }}</button><button v-if="linkedOrderEditable && repairAfterCancellation && can('maintenance.release')" type="button" class="btn primary" :disabled="busy" @click="saveLinkedOrder(true)">Concluir e liberar</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'quick-order'" title="Abrir chamado" @close="modal = null">
      <form class="quick-order-form" @submit.prevent="saveQuickOrder">
        <p class="quick-order-lead">Registre a solicitação agora. A avaliação do equipamento e os testes ficam para o atendimento.</p>
        <div class="form-field"><label for="quick-equipment">Equipamento</label><select id="quick-equipment" v-model="orderForm.equipment" required><option value="" disabled>Selecione o equipamento</option><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></select></div>
        <div class="form-field"><label for="quick-symptoms">O que precisa ser feito?</label><textarea id="quick-symptoms" v-model="orderForm.symptoms" rows="3" required placeholder="Ex.: Betoneira não liga; verificar motor e cabo." /></div>
        <div class="form-field"><label for="quick-type">Tipo de chamado</label><select id="quick-type" v-model="orderForm.maintenance_type"><option value="CORRECTIVE">Corretiva · falha ou reparo</option><option value="PREVENTIVE">Preventiva · revisão programada</option></select></div>
        <details class="quick-order-options" :open="quickPlanning" @toggle="quickPlanning = $event.target.open"><summary>{{ orderForm.scheduled_at ? `Agendado para ${orderForm.scheduled_at.replace('T', ' · ')}` : 'Planejar agora (opcional)' }}</summary><div class="form-grid"><div class="form-field"><label for="quick-priority">Prioridade</label><select id="quick-priority" v-model="orderForm.priority"><option value="NORMAL">Normal</option><option value="ALTA">Alta</option><option value="CRÍTICA">Crítica</option></select></div><div class="form-field"><label for="quick-technician">Técnico</label><select id="quick-technician" v-model="orderForm.technician"><option value="">Definir depois</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div><div class="form-field span-2"><label for="quick-schedule">Data e hora</label><input id="quick-schedule" v-model="orderForm.scheduled_at" type="datetime-local" :required="quickPlanning && orderForm.status === 'SCHEDULED'" /><small>Sem data, o chamado entra na fila como aberto.</small></div></div></details>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy || !equipment.length">{{ busy ? 'Abrindo...' : 'Abrir chamado' }}</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'order'" :title="`Editar ${editing.number}`" wide @close="modal = null">
      <form class="service-order-form" @submit.prevent="saveOrder()">
        <div class="order-form-intro"><Wrench :size="22" /><div><strong>{{ editing ? 'Registro técnico' : 'Novo atendimento' }}</strong><span>{{ editing?.maintenance_type === 'POST_RENTAL' ? 'Reparo pós-locação vinculado à inspeção de devolução.' : 'Organize o chamado e registre o que precisa ser verificado no equipamento.' }}</span></div></div>
        <section class="order-form-section"><header><span>01</span><div><h3>Identificação</h3><p>Dados da abertura da OS; não podem ser alterados durante o atendimento</p></div></header><div class="form-grid">
          <div class="form-field"><span class="order-readout-label">Equipamento</span><div class="order-readout">{{ equipmentById(editing.equipment)?.internal_code || 'Equipamento' }} · {{ editing.equipment_name }}</div></div>
          <div class="form-field"><span class="order-readout-label">Tipo de manutenção</span><div class="order-readout">{{ editing.maintenance_type_label }}</div></div>
          <div class="form-field span-2"><span class="order-readout-label">Sintomas / relato inicial</span><div class="order-readout order-readout-multiline">{{ editing.symptoms }}</div></div>
          <div v-if="editing.plan_due_date" class="form-field span-2"><span class="order-readout-label">Plano periódico</span><div class="order-readout">{{ editing.plan_name }} · vencimento em {{ shortDate(editing.plan_due_date) }}</div></div>
        </div></section>
        <div class="maintenance-order-tools"><button v-if="editing.rental_inspection" type="button" class="btn primary" @click="modal = null; openInspection(editing)"><ClipboardPlus :size="16" />{{ editing.maintenance_type === 'POST_RENTAL' ? 'Ver inspeção final' : 'Abrir inspeção pré-locação' }}</button><button v-if="can('media.view')" type="button" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div>
        <section class="order-form-section"><header><span>02</span><div><h3>Responsável</h3><p>Defina quem atende este chamado</p></div></header><div class="form-grid">
          <div class="form-field span-2"><label>Técnico responsável</label><select v-model="orderForm.technician" :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status)"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
        </div></section>
        <section v-if="editing" class="order-form-section"><header><span>03</span><div><h3>Avaliação e liberação</h3><p>Registre o atendimento e os testes finais</p></div></header><div class="form-grid">
          <div class="form-field span-2"><label>Diagnóstico</label><textarea v-model="orderForm.diagnosis" rows="3" placeholder="Causa encontrada e serviço realizado." /></div>
          <div class="form-field span-2"><label>Testes finais</label><textarea v-model="orderForm.final_tests" rows="3" placeholder="Descreva como o funcionamento foi validado." /></div>
        </div></section>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><button v-if="can('maintenance.manage') && !editing.rental_inspection && !editing.plan_due_date" type="button" class="btn secondary" @click="requestDelete('order', editing)"><Trash2 :size="15" />Excluir OS</button><span class="spacer" /><button class="btn secondary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar atendimento' }}</button><button v-if="can('maintenance.release')" type="button" class="btn primary" :disabled="busy" @click="saveOrder(true)">Concluir e liberar</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'plan'" :title="editing ? 'Editar revisão automática' : 'Nova revisão automática'" @close="modal = null">
      <form class="simple-plan-form" @submit.prevent="savePlan">
        <p class="quick-order-lead">Defina de quanto em quanto tempo o equipamento deve ser revisado. No vencimento, uma OS preventiva será aberta na oficina.</p>
        <div class="form-field"><label for="plan-equipment">Equipamento</label><select id="plan-equipment" v-model="planForm.equipment" required><option value="" disabled>Selecione o equipamento</option><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></select></div>
        <div class="form-grid"><div class="form-field"><label for="plan-interval">Revisar a cada (dias)</label><input id="plan-interval" v-model="planForm.interval_days" type="number" min="1" :required="!editing" placeholder="Ex.: 30" /></div><div class="form-field"><label for="plan-next">{{ editing ? 'Próxima revisão (opcional)' : 'Primeira revisão (opcional)' }}</label><input id="plan-next" v-model="planForm.next_due_date" type="date" /><small>Sem data, o sistema calcula pelo intervalo.</small></div></div>
        <p v-if="planPreviewDate" class="simple-plan-preview"><CalendarDays :size="18" /><span>Próxima revisão em <strong>{{ shortDate(planPreviewDate) }}</strong>. Ao concluir a OS, o próximo ciclo será calculado.</span></p>
        <label class="check-line"><input v-model="planForm.active" type="checkbox" />Revisão ativa</label>
        <details class="quick-order-options" :open="planAdvanced" @toggle="planAdvanced = $event.target.open"><summary>Ajustes opcionais</summary><div class="form-grid">
          <div class="form-field span-2"><label for="plan-name">Nome da revisão (opcional)</label><input id="plan-name" v-model="planForm.name" maxlength="150" placeholder="Preenchido automaticamente com o equipamento" /></div>
          <div class="form-field"><label for="plan-priority">Criticidade</label><select id="plan-priority" v-model="planForm.criticality"><option value="LOW">Baixa</option><option value="MEDIUM">Média</option><option value="HIGH">Alta</option><option value="CRITICAL">Crítica</option></select></div>
          <div class="form-field"><label for="plan-notice">Avisar antes (dias)</label><input id="plan-notice" v-model="planForm.advance_notice_days" type="number" min="0" /></div>
          <div class="form-field span-2"><label for="plan-last">Última revisão realizada (opcional)</label><input id="plan-last" v-model="planForm.last_service_date" type="date" /></div>
          <div class="form-field"><label for="plan-usage">Também revisar a cada (horas)</label><input id="plan-usage" v-model="planForm.usage_limit" type="number" min="1" /></div>
          <div class="form-field"><label for="plan-last-usage">Horímetro na última revisão</label><input id="plan-last-usage" v-model="planForm.last_service_usage_hours" type="number" min="0" /></div>
          <div class="form-field"><label for="plan-usage-notice">Avisar antes (horas)</label><input id="plan-usage-notice" v-model="planForm.advance_notice_usage_hours" type="number" min="0" /></div>
          <p class="simple-plan-advanced-note span-2">Uma revisão crítica vencida bloqueia novas reservas. As configurações anteriores são mantidas ao editar.</p>
        </div></details>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><button v-if="editing" type="button" class="btn secondary" @click="requestDelete('plan', editing)"><Trash2 :size="15" />Excluir</button><span class="spacer" /><button class="btn primary" :disabled="busy || !equipment.length">{{ busy ? 'Salvando...' : 'Salvar revisão' }}</button></div>
      </form>
    </ModalDialog>

    <WorkshopOrderModal v-if="modal === 'workshop-order'" :order="editing" :equipment="equipmentById(editing.equipment)" :technicians="technicians" @close="modal = null" @changed="workshopChanged" @delete="requestDelete('order', editing)" />

    <EquipmentMediaModal v-if="mediaEquipment" :equipment="mediaEquipment" @close="closeMedia" @changed="load" />
    <RentalInspectionModal v-if="inspectionContext" :quote="inspectionContext.quote" :type="inspectionContext.type" :initial-id="inspectionContext.initialId" @close="inspectionContext = null" @changed="load" />
    <ConfirmDialog v-if="deleting" :title="deleting.kind === 'order' ? 'Excluir chamado' : 'Excluir plano'" :message="`Excluir “${deleting.item.number || deleting.item.name}”? Esta ação não pode ser desfeita.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
