<script setup>
import { formatNumber } from '../services/formatters'
import { usePagination } from '../services/pagination'
import { matchesSearch, sortRecords, dateValue } from '../services/listFilters'
import { toDateTimeInput, toDateTimePayload } from '../services/formDates'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertTriangle, CalendarDays, ChevronDown, ClipboardPlus, Copy, Files, Plus, Search, Trash2, Wrench, Eye, EyeOff,
} from 'lucide-vue-next'
import AIConsultPanel from '../components/AIConsultPanel.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import MaintenanceOrdersTable from '../components/MaintenanceOrdersTable.vue'
import ModalDialog from '../components/ModalDialog.vue'
import RentalInspectionModal from '../components/RentalInspectionModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import SymptomsField from '../components/SymptomsField.vue'
import VoiceTextarea from '../components/VoiceTextarea.vue'
import { canUseAI } from '../services/ai'
import { api, apiError, auth, can, rows, shortDate, fetchAll } from '../services/api'

const tab = ref('rental')
const route = useRoute()
const queue = ref('ALL')
const plansExpanded = ref(false)
const search = ref('')
const equipmentFilter = ref(''), priorityFilter = ref(''), technicianFilter = ref(''), typeFilter = ref(''), ordering = ref('attention')
const moreFilters = ref(false)
const advancedFilterCount = computed(() => [equipmentFilter.value, priorityFilter.value, technicianFilter.value, typeFilter.value].filter(Boolean).length)
const sortOptions = [['attention', 'Prioridade'], ['scheduled', 'Agenda próxima'], ['-scheduled', 'Agenda distante'], ['number', 'Número da OS'], ['equipment', 'Equipamento A–Z'], ['-opened', 'Mais recentes']]
const priorityRank = order => ({ 'CRÍTICA': 0, ALTA: 1, NORMAL: 2 })[order.priority] ?? 3
const sortFields = { attention: order => (['COMPLETED', 'CANCELLED'].includes(order.status) ? 10 : 0) + priorityRank(order), scheduled: order => dateValue(order.scheduled_at), opened: order => dateValue(order.opened_at), number: order => order.number, equipment: order => order.equipment_name }
const technicianOptions = computed(() => [...new Map(categoryOrders.value.filter(order => order.technician).map(order => [String(order.technician), order.technician_name])).entries()])
const orders = ref([])
const plans = ref([])
const equipment = ref([])
const technicians = ref([])
const modal = ref(null)
const editing = ref(null)
const deleting = ref(null)
const mediaEquipment = ref(null)
const mediaOrder = ref(null)
const mediaReturnModal = ref(null)
const inspectionContext = ref(null)
const inspectionEditor = ref(null)
const expandedRentalGroup = ref(null)
const error = ref('')
const busy = ref(false)
const quickPlanning = ref(false)
const orderStep = ref(0), orderActivities = ref([]), checklistLoading = ref(false), checklistError = ref('')
const orderSteps = ['Chamado', 'Atendimento', 'Checklist e evidências', 'Revisão']
let orderSession = 0
function applyNavigationContext() {
  const requestedTab = String(route.query.tab || '')
  const requestedQueue = String(route.query.queue || '')
  const validTabs = ['rental', 'workshop']
  const validQueues = ['ALL', 'UNASSIGNED', 'READY', 'IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED', 'COMPLETED']
  if (validTabs.includes(requestedTab)) tab.value = requestedTab
  if (validQueues.includes(requestedQueue)) queue.value = requestedQueue
  if (route.query.quote) search.value = String(route.query.quote)
}

const aiHints = reactive({ urgency: '', candidates: [], location: '' })
const cloneTargets = ref([])
const cloneResult = ref(null)

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

const terminalStatuses = ['COMPLETED', 'CANCELLED']
const rentalOrders = computed(() => orders.value.filter(item => ['PRE_RENTAL', 'POST_RENTAL'].includes(item.maintenance_type)))
const rentalGroupKey = order => order.rental_quote_id ? `quote-${order.rental_quote_id}` : 'unlinked'
const maintenanceTabs = [
  { key: 'rental', label: 'Locação', icon: ClipboardPlus },
  { key: 'workshop', label: 'Oficina e revisões', icon: Wrench },
]
const categoryOrders = computed(() => orders.value.filter(order => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  workshop: ['PREVENTIVE', 'SCHEDULED', 'CORRECTIVE'],
})[tab.value]?.includes(order.maintenance_type)).sort((a, b) =>
  Number(terminalStatuses.includes(a.status)) - Number(terminalStatuses.includes(b.status))
  || Number(b.priority === 'CRÍTICA') - Number(a.priority === 'CRÍTICA')
  || (a.scheduled_at || '').localeCompare(b.scheduled_at || '')
))
const openOrderCount = computed(() => categoryOrders.value.filter(order => !terminalStatuses.includes(order.status)).length)
const categoryPlans = computed(() => plans.value.filter(plan => ({
  rental: ['PRE_RENTAL', 'POST_RENTAL'],
  workshop: ['PREVENTIVE', 'SCHEDULED'],
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
const equipmentOptions = computed(() => {
  const seen = new Map()
  for (const order of categoryOrders.value) if (!seen.has(order.equipment)) seen.set(order.equipment, order.equipment_name)
  return [...seen].map(([id, name]) => ({ id, name })).sort((a, b) => String(a.name).localeCompare(String(b.name), 'pt-BR'))
})
const hasFilters = computed(() => Boolean(search.value || equipmentFilter.value || priorityFilter.value || technicianFilter.value || typeFilter.value || queue.value !== 'ALL' || ordering.value !== 'attention'))
function clearFilters() { search.value = ''; equipmentFilter.value = ''; priorityFilter.value = ''; technicianFilter.value = ''; typeFilter.value = ''; queue.value = 'ALL'; ordering.value = 'attention' }
const filteredOrders = computed(() => sortRecords(categoryOrders.value.filter(order => matchesQueue(order, queue.value) && (!equipmentFilter.value || String(order.equipment) === String(equipmentFilter.value)) && (!priorityFilter.value || order.priority === priorityFilter.value) && (!typeFilter.value || order.maintenance_type === typeFilter.value) && (!technicianFilter.value || (technicianFilter.value === 'none' ? !order.technician : String(order.technician) === technicianFilter.value)) && matchesSearch(search.value, order.number, order.equipment_name, order.technician_name, order.symptoms, order.rental_quote_number, order.rental_customer_name)), ordering.value, sortFields))
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
    openCount: group.orders.filter(order => !terminalStatuses.includes(order.status)).length,
    equipmentSummary: [...new Set(group.orders.map(order => order.equipment_name))].join(' · '),
  }))
})
const rentalStatusLabel = status => ({
  APPROVED: 'Reservada', ACTIVE: 'Em locação', RETURNED: 'Em inspeção',
  COMPLETED: 'Concluída', CANCELLED: 'Cancelada',
})[status] || status || 'Sem vínculo'
const repairAfterCancellation = computed(() => editing.value?.rental_quote_status === 'CANCELLED' && editing.value?.inspection_result === 'BLOCKED')
const linkedOrderEditable = computed(() => can('maintenance.manage') && editing.value && !terminalStatuses.includes(editing.value.status) && ((['APPROVED', 'ACTIVE'].includes(editing.value.rental_quote_status) && (!editing.value.rental_item_stage || editing.value.rental_item_stage === 'PENDING')) || repairAfterCancellation.value))
const orderEditable = computed(() => can('maintenance.manage') && editing.value && !terminalStatuses.includes(editing.value.status) && (editing.value.maintenance_type !== 'PRE_RENTAL' || !editing.value.rental_inspection || linkedOrderEditable.value))
const inspectionControlsClosure = computed(() => Boolean(editing.value?.rental_inspection) && (editing.value.maintenance_type === 'PRE_RENTAL' && !repairAfterCancellation.value || editing.value.maintenance_type === 'POST_RENTAL' && editing.value.inspection_result === 'PENDING'))
const equipmentById = id => equipment.value.find(item => item.id === id)
function openMedia(equipmentId, orderScoped = false) {
  const item = equipmentById(equipmentId)
  if (!item) {
    error.value = 'Não foi possível localizar o equipamento desta OS.'
    return
  }
  mediaReturnModal.value = modal.value
  mediaOrder.value = orderScoped ? editing.value : null
  mediaEquipment.value = item
}
function closeMedia() {
  mediaEquipment.value = null
  if (mediaReturnModal.value) {
    modal.value = mediaReturnModal.value
    mediaReturnModal.value = null
  }
}
const toLocalInput = toDateTimeInput
const scheduledDay = value => toLocalInput(value).slice(0, 10)

async function load() {
  if (can('maintenance.manage')) {
    try {
      await api.post('/maintenance-plans/sync-due/')
    } catch (event) {
      error.value = `Não foi possível verificar os planos vencidos: ${apiError(event)}`
    }
  }
  const [o, p, e, u] = await Promise.all([
    fetchAll('/service-orders/'), fetchAll('/maintenance-plans/'), fetchAll('/equipment/'),
    can('accounts.users.view') ? fetchAll('/users/') : Promise.resolve({ data: [] }),
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
  modal.value = item ? 'order' : 'quick-order'
  orderStep.value = 0; inspectionContext.value = null; orderActivities.value = []
  checklistError.value = ''; checklistLoading.value = false
  const session = ++orderSession
  error.value = ''
  quickPlanning.value = Boolean(defaults.scheduled_at)
  Object.assign(aiHints, { urgency: '', candidates: [], location: '' })
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
  if (item) loadOrderChecklist(item, session)
}

async function loadOrderChecklist(item, session = orderSession) {
  checklistLoading.value = true; checklistError.value = ''
  try {
    if (item.rental_inspection) {
      const { data } = await api.get(`/rental-quotes/${item.rental_quote_id}/`)
      if (session !== orderSession || editing.value?.id !== item.id) return
      inspectionContext.value = { quote: data, type: item.maintenance_type === 'POST_RENTAL' ? 'RETURN' : 'PRE_RENTAL', initialId: item.rental_inspection }
    } else {
      let points = item.activities?.map(activity => ({ ...activity })) || []
      if (!points.length && !terminalStatuses.includes(item.status)) {
        let template = plans.value.find(plan => plan.id === item.plan)?.checklist || []
        if (!template.length) {
          const { data } = await api.get('/service-orders/checklist-template/', { params: { type: item.maintenance_type } })
          template = data.checklist || []
        }
        points = template.map(check => ({ description: typeof check === 'string' ? check : check.label, completed: false, hours: 0, part_used: '', quantity: null })).filter(check => check.description)
      }
      if (session === orderSession && editing.value?.id === item.id) orderActivities.value = points
    }
  } catch (event) { if (session === orderSession) checklistError.value = apiError(event) }
  finally { if (session === orderSession) checklistLoading.value = false }
}

function orderProblem() {
  if (!orderEditable.value) return ''
  if (['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status) && !orderForm.technician) { orderStep.value = 1; return 'Selecione o técnico responsável.' }
  if (orderForm.status === 'SCHEDULED' && !orderForm.scheduled_at) { orderStep.value = 1; return 'Informe o agendamento.' }
  if (orderForm.status === 'ABANDONED' && !orderForm.abandoned_reason.trim()) { orderStep.value = 1; return 'Registre o motivo do abandono.' }
  if (!editing.value.rental_inspection && orderForm.status === 'COMPLETED' && orderActivities.value.some(item => !item.completed)) { orderStep.value = 2; return 'Conclua o checklist antes de encerrar a OS.' }
  if (orderForm.released && (!orderForm.technician || !orderForm.final_tests.trim())) { orderStep.value = 1; return 'A liberação exige técnico responsável e testes finais.' }
  return ''
}
function orderPayload() {
  const common = { status: orderForm.status, priority: orderForm.priority, technician: orderForm.technician || null, scheduled_at: toDateTimePayload(orderForm.scheduled_at), diagnosis: orderForm.diagnosis, abandoned_reason: orderForm.status === 'ABANDONED' ? orderForm.abandoned_reason : '' }
  if (editing.value.maintenance_type === 'PRE_RENTAL' && editing.value.rental_inspection) return { ...common, ...(repairAfterCancellation.value ? { final_tests: orderForm.final_tests, released: orderForm.released } : {}) }
  return { ...common, final_tests: orderForm.final_tests, released: orderForm.status === 'COMPLETED' && orderForm.released, labor_hours: orderForm.labor_hours, parts_used: orderForm.parts_used, ...(!editing.value.rental_inspection ? { activities: orderActivities.value.map(({ id, description, completed, hours, part_used, quantity }) => ({ ...(id ? { id } : {}), description, completed, hours, part_used, quantity })) } : {}) }
}
async function saveOrderProgress() {
  if (!orderEditable.value) return true
  if (checklistLoading.value || checklistError.value) { orderStep.value = 2; error.value = 'Aguarde o checklist ou tente carregá-lo novamente.'; return false }
  error.value = orderProblem()
  if (error.value) return false
  const session = orderSession, id = editing.value.id
  busy.value = true
  try {
    const { data } = await api.patch(`/service-orders/${id}/`, orderPayload())
    if (session !== orderSession || editing.value?.id !== id) return false
    editing.value = { ...editing.value, ...data }
    const index = orders.value.findIndex(item => item.id === id)
    if (index >= 0) orders.value[index] = editing.value
    if (!editing.value.rental_inspection && data.activities) orderActivities.value = data.activities.map(item => ({ ...item }))
    return true
  } catch (event) { error.value = apiError(event); return false }
  finally { busy.value = false }
}
async function inspectionChanged() {
  const session = orderSession, id = editing.value?.id
  await load()
  if (session !== orderSession) return
  const fresh = orders.value.find(item => item.id === id)
  if (!fresh) return
  editing.value = fresh
  orderForm.diagnosis = fresh.diagnosis
  orderForm.status = fresh.status; orderForm.released = fresh.released; orderForm.final_tests = fresh.final_tests
}
async function finishOrder() {
  if (busy.value || inspectionEditor.value?.busy) return
  if (inspectionEditor.value?.editable && inspectionEditor.value.hasChanges && !await inspectionEditor.value.save()) { orderStep.value = 2; return }
  if (!await saveOrderProgress()) return
  modal.value = null
  await load()
}
async function nextOrderStep() {
  if (busy.value || inspectionEditor.value?.busy) return
  if (orderStep.value === 2 && inspectionEditor.value?.editable && inspectionEditor.value.hasChanges && !await inspectionEditor.value.save()) return
  error.value = orderStep.value === 1 ? orderProblem() : ''
  if (!error.value) orderStep.value = Math.min(orderStep.value + 1, 3)
}

function applyHints(data) {
  // O texto sugerido só entra no campo quando o usuário aceita (SymptomsField); aqui ficam apenas as dicas.
  const { extraction, equipment_candidates: candidates } = data
  const [best, second] = candidates
  aiHints.candidates = candidates
  aiHints.urgency = extraction.urgency_hint
  if (!orderForm.equipment && best && (!second || best.score >= second.score * 1.5)) orderForm.equipment = best.id
}

async function onAiApplied() {
  const before = editing.value
  const typed = { diagnosis: orderForm.diagnosis, final_tests: orderForm.final_tests, parts_used: orderForm.parts_used }
  await load()
  const fresh = orders.value.find(order => order.id === before?.id)
  if (!fresh) return
  editing.value = fresh
  // Preenche os campos aplicados pela IA sem perder o que o técnico já digitou e ainda não salvou.
  for (const field of ['diagnosis', 'final_tests', 'parts_used']) {
    const saved = (before[field] || '').trimEnd()
    const added = fresh[field].startsWith(saved) ? fresh[field].slice(saved.length).trim() : ''
    const dirty = typed[field] !== (before[field] || '')
    orderForm[field] = dirty && added ? `${typed[field].trimEnd()}\n${added}`.trim() : fresh[field]
  }
}

function openClone() {
  cloneTargets.value = []
  cloneResult.value = null
  error.value = ''
  modal.value = 'plan-clone'
}

async function submitClone() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await api.post(`/maintenance-plans/${editing.value.id}/clone/`, { equipment_ids: cloneTargets.value })
    cloneResult.value = { created: data.created.length, skipped: data.skipped.length }
    cloneTargets.value = []
    await load()
  } catch (e) {
    error.value = apiError(e)
  } finally {
    busy.value = false
  }
}

function selectTab(key) {
  tab.value = key
  clearFilters()
  moreFilters.value = false
  expandedRentalGroup.value = null
  plansExpanded.value = key === 'workshop'
}

function schedulePreventive() {
  const date = new Date(Date.now() + 3600000)
  date.setMinutes(0, 0, 0)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  openOrder(null, { maintenance_type: 'PREVENTIVE', status: 'SCHEDULED', scheduled_at: local })
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

const saveQuickOrder = () => persist('/service-orders/', {
  equipment: orderForm.equipment,
  maintenance_type: orderForm.maintenance_type,
  symptoms: orderForm.symptoms.trim(),
  priority: orderForm.priority,
  technician: orderForm.technician || null,
  scheduled_at: toDateTimePayload(orderForm.scheduled_at),
  status: orderForm.scheduled_at ? 'SCHEDULED' : 'OPEN',
})
const savePlan = () => persist('/maintenance-plans/', {
  ...planForm,
  interval_days: planForm.interval_days || null,
  usage_limit: planForm.usage_limit || null,
  next_due_date: planForm.next_due_date || null,
  last_service_date: planForm.last_service_date || null,
  last_service_usage_hours: planForm.last_service_usage_hours === '' ? null : planForm.last_service_usage_hours,
})
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
      queue.value = 'ALL'
      search.value = ''
      if (matched.rental_quote_number) expandedRentalGroup.value = rentalGroupKey(matched)
      openOrder(matched)
    }
    return
  }
  if (route.query.quote) {
    tab.value = 'rental'
    queue.value = 'ALL'
    search.value = String(route.query.quote)
    const matched = rentalOrders.value.find(order => order.rental_quote_number === String(route.query.quote))
    if (matched) expandedRentalGroup.value = rentalGroupKey(matched)
  }
}
watch(() => [route.query.order, route.query.quote], applyRouteContext)
onMounted(async () => {
  applyNavigationContext()
  try {
    await load()
    applyRouteContext()
  } catch (event) {
    error.value = apiError(event)
  }
})
const { page: planPage, items: planRows } = usePagination(categoryPlans, [tab])
const { page: rentalGroupPage, items: rentalGroupRows } = usePagination(rentalGroups, [search, queue, equipmentFilter, priorityFilter, technicianFilter, typeFilter, ordering, tab])
</script>

<template>
  <div class="page maintenance-page">
    <header class="page-heading compact">
      <div><span class="eyebrow">CONFIABILIDADE DA FROTA</span><h1>Manutenção</h1><p>Chamados e planos organizados por tipo de serviço.</p></div>
      <div v-if="can('maintenance.manage') && tab === 'workshop'" class="heading-actions"><button class="btn secondary" @click="schedulePreventive"><CalendarDays :size="16" />Agendar revisão avulsa</button><button class="btn primary" @click="openOrder(null, { maintenance_type: 'CORRECTIVE' })"><Plus :size="16" />Novo chamado</button></div>
    </header>

    <GeneralError v-if="error && !modal" :message="error" @close="error = ''" />

    <div class="tabs maintenance-area-tabs" role="tablist" aria-label="Áreas da manutenção">
      <button v-for="item in maintenanceTabs" :key="item.key" role="tab" :aria-selected="tab === item.key" :class="{ active: tab === item.key }" @click="selectTab(item.key)"><component :is="item.icon" :size="18" />{{ item.label }}</button>
    </div>


      <div class="maintenance-sections">
      <section class="panel list-panel">
        <header class="list-toolbar list-controls maintenance-list-toolbar"><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" :placeholder="tab === 'rental' ? 'Locação, cliente, equipamento ou OS' : 'OS, equipamento ou técnico'" aria-label="Pesquisar manutenção" /></span></label><label class="list-control"><span>Etapa</span><AppSelect v-model="queue"><option v-for="item in queueTabs" :key="item.key" :value="item.key">{{ item.label }} ({{ item.count }})</option></AppSelect></label><ListOrdering v-model="ordering" :options="sortOptions" /><div class="filter-meta"><span class="result-count">{{ tab === 'rental' ? `${rentalGroups.length} locação(ões)` : `${filteredOrders.length} OS` }}</span><div class="maintenance-filter-actions"><button type="button" class="btn secondary" :aria-expanded="moreFilters" @click="moreFilters = !moreFilters">{{ moreFilters ? 'Menos filtros' : 'Mais filtros' }}<span v-if="advancedFilterCount" class="filter-badge">{{ advancedFilterCount }}</span></button><button v-if="hasFilters" type="button" class="btn secondary" @click="clearFilters">Limpar filtros</button></div></div></header><div v-if="moreFilters" class="list-controls maintenance-more-filters"><label class="list-control"><span>Equipamento</span><AppSelect searchable v-model="equipmentFilter"><option value="">Todos</option><option v-for="item in equipmentOptions" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></label><label class="list-control"><span>Prioridade</span><AppSelect v-model="priorityFilter"><option value="">Todas</option><option value="CRÍTICA">Crítica</option><option value="ALTA">Alta</option><option value="NORMAL">Normal</option></AppSelect></label><label class="list-control"><span>Técnico</span><AppSelect searchable v-model="technicianFilter"><option value="">Todos</option><option value="none">Sem técnico</option><option v-for="[id, name] in technicianOptions" :key="id" :value="id">{{ name }}</option></AppSelect></label><label class="list-control"><span>Tipo de serviço</span><AppSelect v-model="typeFilter"><option value="">Todos</option><template v-if="tab === 'rental'"><option value="PRE_RENTAL">Pré-locação</option><option value="POST_RENTAL">Pós-locação</option></template><template v-else><option value="CORRECTIVE">Corretiva</option><option value="PREVENTIVE">Preventiva</option><option value="SCHEDULED">Revisão programada</option></template></AppSelect></label></div>
        <template v-if="tab === 'rental'"><div class="table-wrap maintenance-rental-table"><table><thead><tr><th>Locação</th><th>Cliente</th><th>Período</th><th>Equipamentos</th><th>Ordens</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody><template v-for="group in rentalGroupRows" :key="group.key"><tr><td><strong>{{ group.number }}</strong></td><td>{{ group.customer || 'Não informado' }}</td><td>{{ group.startDate ? shortDate(group.startDate) : '—' }}<small v-if="group.endDate">até {{ shortDate(group.endDate) }}</small></td><td>{{ group.equipmentSummary }}</td><td><strong>{{ group.orders.length }} OS</strong><small>{{ group.openCount }} em aberto</small></td><td><StatusBadge :value="group.status" :label="rentalStatusLabel(group.status)" /></td><td class="right"><button type="button" class="icon-btn" :aria-expanded="expandedRentalGroup === group.key" :aria-label="expandedRentalGroup === group.key ? 'Ocultar ordens da locação' : 'Mostrar ordens da locação'" @click="expandedRentalGroup = expandedRentalGroup === group.key ? null : group.key"><component :is="expandedRentalGroup === group.key ? EyeOff : Eye" :size="18" /></button></td></tr><tr v-if="expandedRentalGroup === group.key" class="maintenance-expanded-row"><td colspan="7"><MaintenanceOrdersTable :orders="group.orders" @open="openOrder" /></td></tr></template><tr v-if="!rentalGroups.length"><td colspan="7" class="empty-cell">Nenhuma locação encontrada com estes filtros.</td></tr></tbody></table></div><PaginationBar v-model="rentalGroupPage" :total="rentalGroups.length" /></template>
        <MaintenanceOrdersTable v-else :orders="filteredOrders" @open="openOrder" />
      </section>

      <details v-if="tab === 'workshop' || categoryPlans.length" :open="plansExpanded" class="panel list-panel maintenance-plan-details" @toggle="plansExpanded = $event.target.open"><summary><span><CalendarDays :size="18" /><strong>{{ tab === 'rental' ? 'Planos ligados à locação' : 'Planos de revisão periódica' }}</strong></span><b>{{ categoryPlans.length }} plano(s)</b></summary>
        <div v-if="tab === 'workshop' && can('maintenance.manage')" class="maintenance-plan-toolbar"><span>Cadastre o intervalo de um equipamento. Ao vencer, uma OS preventiva agendada será criada automaticamente.</span><button class="btn secondary" @click="openPlan()"><Plus :size="16" />Novo plano periódico</button></div>
        <div class="table-wrap maintenance-plans-table"><table><thead><tr><th>Plano</th><th>Equipamento</th><th>Periodicidade</th><th>Próxima data</th><th>Próximo uso</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody>
          <tr v-for="plan in planRows" :key="plan.id"><td><div><strong>{{ plan.name }}</strong><small>{{ plan.maintenance_type_label }}<template v-if="plan.criticality_label"> · {{ plan.criticality_label }}</template><template v-if="plan.active === false"> · Inativo</template></small></div></td><td>{{ plan.equipment_name }}</td><td>{{ plan.interval_days ? `A cada ${plan.interval_days} dias` : 'Por data/uso' }}</td><td>{{ plan.due_date ? shortDate(plan.due_date) : 'Sem data' }}</td><td>{{ plan.due_usage_hours != null ? `${formatNumber(plan.due_usage_hours)} h` : 'Não definido' }}</td><td><StatusBadge :value="plan.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></td><td class="right"><button type="button" class="icon-btn" :aria-label="`Abrir plano ${plan.name}`" :title="`Abrir plano ${plan.name}`" @click="openPlan(plan)"><Eye :size="18" /></button></td></tr>
          <tr v-if="!categoryPlans.length"><td colspan="7" class="empty-cell">Nenhum plano cadastrado.</td></tr>
        </tbody></table></div><PaginationBar v-model="planPage" :total="categoryPlans.length" />
      </details>
      </div>



    <ModalDialog v-if="modal === 'plan-detail'" :title="editing.name" @close="modal = null; error = ''"><div class="maintenance-readonly-detail"><StatusBadge :value="editing.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[editing.alert_status]" /><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }} · {{ editing.criticality_label }}</p><dl><div><dt>Próxima execução</dt><dd>{{ editing.due_date ? shortDate(editing.due_date) : 'Sem data' }}</dd></div><div v-if="editing.interval_days"><dt>Periodicidade</dt><dd>A cada {{ editing.interval_days }} dias</dd></div><div v-if="editing.due_usage_hours !== null"><dt>Gatilho por uso</dt><dd>{{ formatNumber(editing.due_usage_hours) }} h</dd></div></dl><div v-if="can('media.view')" class="maintenance-order-tools"><button class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div></div><div class="modal-actions"><span class="spacer" /><button class="btn secondary" @click="modal = null; error = ''">Fechar</button></div></ModalDialog>



    <ModalDialog v-if="modal === 'order' && editing" :title="`${orderEditable ? 'Atendimento' : 'Consulta'} · ${editing.number}`" wide @close="modal = null; orderSession += 1; error = ''">
      <form class="service-order-form order-wizard" novalidate @submit.prevent="orderStep < 3 ? nextOrderStep() : finishOrder()">
        <nav class="quote-wizard-nav order-wizard-nav" aria-label="Etapas do atendimento">
          <button v-for="(title, index) in orderSteps" :key="title" type="button" :disabled="busy || inspectionEditor?.busy" :class="{ active: orderStep === index, completed: orderStep > index }" :aria-current="orderStep === index ? 'step' : undefined" @click="orderStep = index; error = ''"><b>{{ index + 1 }}</b><span>{{ title }}</span></button>
        </nav>
        <section v-show="orderStep === 0" class="order-wizard-section">
          <header class="order-context"><div><span class="eyebrow">{{ editing.number }}</span><h3>{{ editing.equipment_name }}</h3><p>{{ editing.maintenance_type_label }}<template v-if="editing.rental_quote_number"> · {{ editing.rental_quote_number }}</template></p></div><StatusBadge :value="editing.status" :label="editing.status_label" /></header>
          <div class="form-field"><span class="order-readout-label">Solicitação</span><div class="order-readout order-readout-multiline">{{ editing.symptoms }}</div></div>
          <div v-if="editing.plan_due_date" class="order-readout">{{ editing.plan_name }} · vencimento em {{ shortDate(editing.plan_due_date) }}</div>
          <p v-if="inspectionControlsClosure" class="inspection-flow-hint">O checklist desta OS controla a liberação do equipamento. Conclua a inspeção na etapa 3.</p>
          <div v-if="can('media.view')" class="maintenance-order-tools"><button type="button" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div>
        </section>
        <section v-show="orderStep === 1" class="order-wizard-section">
          <h3>Responsável e execução</h3>
          <fieldset :disabled="!orderEditable || busy" class="order-fields"><div class="form-grid">
            <div class="form-field"><label>Status do chamado<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="orderForm.status" :disabled="!orderEditable || busy"><option value="OPEN">Aberto</option><option value="SCHEDULED">Agendado</option><option value="IN_PROGRESS">Em andamento</option><option value="WAITING_PARTS">Aguardando peças</option><option value="ABANDONED">Abandonado</option><option v-if="!inspectionControlsClosure || editing.status === 'COMPLETED'" value="COMPLETED">Concluído</option><option v-if="!inspectionControlsClosure && !repairAfterCancellation || editing.status === 'CANCELLED'" value="CANCELLED">Cancelado</option></AppSelect></div>
            <div class="form-field"><label>Prioridade<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="orderForm.priority" :disabled="!orderEditable || busy"><option value="NORMAL">Normal</option><option value="ALTA">Alta</option><option value="CRÍTICA">Crítica</option></AppSelect></div>
            <div class="form-field"><label>Técnico responsável<span class="required-mark" aria-hidden="true" v-if="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status) || orderForm.released"> *</span></label><AppSelect :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status) || orderForm.released" searchable v-model="orderForm.technician" :disabled="!orderEditable || busy"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></AppSelect></div>
            <div class="form-field"><label>Agendamento</label><AppDateTime v-model="orderForm.scheduled_at" type="datetime-local" /></div>
            <div v-if="orderForm.status === 'ABANDONED'" class="form-field span-2"><label>Motivo do abandono<span class="required-mark" aria-hidden="true" v-if="orderForm.status === 'ABANDONED'"> *</span></label><VoiceTextarea :required="orderForm.status === 'ABANDONED'" v-model="orderForm.abandoned_reason" :rows="3" :disabled="!orderEditable || busy" /></div>
            <div class="form-field span-2"><label>Diagnóstico e notas do atendimento</label><VoiceTextarea v-model="orderForm.diagnosis" :rows="3" :disabled="!orderEditable || busy" placeholder="Causa encontrada, verificações e serviço realizado." /></div>
            <template v-if="!inspectionControlsClosure || editing.maintenance_type === 'POST_RENTAL'">
              <div class="form-field"><label>Horas de mão de obra</label><AppInput mask="decimal" :precision="2" v-model="orderForm.labor_hours" min="0" step="0.25" placeholder="Ex.: 1,5" /></div>
              <div class="form-field"><label>Peças utilizadas</label><VoiceTextarea v-model="orderForm.parts_used" :rows="2" :disabled="!orderEditable || busy" /></div>
              <div class="form-field span-2"><label>Testes finais<span class="required-mark" aria-hidden="true" v-if="orderForm.released"> *</span></label><VoiceTextarea :required="orderForm.released" v-model="orderForm.final_tests" :rows="3" :disabled="!orderEditable || busy" /></div>
              <label v-if="can('maintenance.release') && orderForm.status === 'COMPLETED'" class="check-line span-2 order-release"><input v-model="orderForm.released" type="checkbox" />Liberar equipamento após validação técnica</label>
            </template>
          </div></fieldset>
          <AIConsultPanel v-if="orderEditable && canUseAI()" :equipment-id="editing.equipment" :order="editing" :initial-symptoms="editing.symptoms" @applied="onAiApplied" />
        </section>
        <section v-show="orderStep === 2" class="order-wizard-section">
          <h3>{{ editing.rental_inspection ? (editing.maintenance_type === 'POST_RENTAL' ? 'Checklist de devolução' : 'Checklist pré-locação') : 'Checklist do atendimento' }}</h3>
          <p v-if="checklistLoading" role="status">Carregando checklist...</p>
          <div v-else-if="checklistError" class="error-message" role="alert">{{ checklistError }}<button type="button" class="btn secondary" @click="loadOrderChecklist(editing)">Tentar novamente</button></div>
          <RentalInspectionModal v-if="inspectionContext" :key="editing.id" ref="inspectionEditor" embedded :quote="inspectionContext.quote" :type="inspectionContext.type" :initial-id="inspectionContext.initialId" :before-save="saveOrderProgress" :after-save="inspectionChanged" />
          <template v-else-if="!editing.rental_inspection && !checklistLoading && !checklistError">
            <p class="muted-text">{{ orderActivities.filter(item => item.completed).length }} de {{ orderActivities.length }} verificações concluídas. O progresso será salvo com o atendimento.</p>
            <div v-if="orderActivities.length" class="workshop-checklist"><label v-for="(item, index) in orderActivities" :key="item.id || index" class="check-line"><input v-model="item.completed" type="checkbox" :disabled="!orderEditable || busy" /><span>{{ item.description }}</span></label></div>
            <p v-else class="muted-text">Esta OS não possui pontos de checklist registrados.</p>
            <button v-if="can('media.view')" type="button" class="btn secondary" @click="openMedia(editing.equipment, true)"><Files :size="16" />Fotos e documentos desta OS</button>
          </template>
        </section>
        <section v-show="orderStep === 3" class="order-wizard-section quote-review">
          <h3>Revisão do atendimento</h3><dl><div><dt>Equipamento</dt><dd>{{ editing.equipment_name }}</dd></div><div><dt>Técnico</dt><dd>{{ technicians.find(item => String(item.id) === String(orderForm.technician))?.full_name || 'Sem técnico' }}</dd></div><div><dt>Situação</dt><dd><StatusBadge :value="orderForm.status" /></dd></div><div v-if="editing.rental_inspection"><dt>Inspeção</dt><dd>{{ ({ PENDING: 'Pendente', APPROVED: 'Aprovada', APPROVED_WITH_NOTES: 'Aprovada com ressalvas', BLOCKED: 'Impedida' })[editing.inspection_result] || 'Sem resultado' }}</dd></div><div v-else><dt>Checklist</dt><dd>{{ orderActivities.filter(item => item.completed).length }}/{{ orderActivities.length }} verificações</dd></div><div><dt>Diagnóstico</dt><dd class="preserve-lines">{{ orderForm.diagnosis || 'Não informado' }}</dd></div><div><dt>Testes finais</dt><dd class="preserve-lines">{{ orderForm.final_tests || 'Não informados' }}</dd></div></dl>
          <p v-if="inspectionControlsClosure" class="muted-text">A conclusão e a liberação são registradas pelo checklist da etapa 3.</p>
          <button v-if="orderEditable && !editing.rental_inspection && !editing.plan_due_date" type="button" class="btn secondary" @click="requestDelete('order', editing)"><Trash2 :size="15" />Excluir OS</button>
        </section>
        <div v-if="error" class="error-message" role="alert">{{ error }}</div>
        <div class="modal-actions"><button v-if="orderStep > 0" type="button" class="btn secondary" :disabled="busy || inspectionEditor?.busy" @click="orderStep -= 1; error = ''">Voltar</button><button v-if="orderEditable && orderStep < 3" type="button" class="btn secondary" :disabled="busy || checklistLoading || inspectionEditor?.busy" @click="saveOrderProgress">Salvar andamento</button><span class="spacer" /><button v-if="orderStep < 3" type="button" class="btn primary" :disabled="busy || inspectionEditor?.busy" @click="nextOrderStep">Continuar</button><button v-else-if="orderEditable" class="btn primary" :disabled="busy || checklistLoading || inspectionEditor?.busy">{{ busy ? 'Salvando...' : 'Salvar atendimento' }}</button><button v-else type="button" class="btn secondary" :disabled="inspectionEditor?.busy" @click="modal = null; error = ''">Concluir consulta</button></div>
      </form>
    </ModalDialog>

    <ModalDialog v-if="modal === 'quick-order'" title="Abrir chamado" @close="modal = null; error = ''">
      <form class="quick-order-form" @submit.prevent="saveQuickOrder">
        <p class="quick-order-lead">Registre a solicitação agora. Diagnóstico, peças e testes ficam para o atendimento.</p>
        <div class="form-field"><label for="quick-equipment">Equipamento<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable id="quick-equipment" v-model="orderForm.equipment" required><option value="" disabled>Selecione o equipamento</option><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></AppSelect><div v-if="aiHints.candidates.length && !orderForm.equipment" class="ai-candidates"><small>A IA sugere:</small><button v-for="item in aiHints.candidates" :key="item.id" type="button" class="ai-source-chip" @click="orderForm.equipment = item.id">{{ item.internal_code }} · {{ item.name }}</button></div></div>
        <div class="form-field"><label for="quick-symptoms">O que precisa ser feito?<span class="required-mark" aria-hidden="true"> *</span></label><SymptomsField required id="quick-symptoms" v-model="orderForm.symptoms" :equipment-id="orderForm.equipment" :maintenance-type="orderForm.maintenance_type" placeholder="Ex.: Betoneira não liga; verificar motor e cabo." @hints="applyHints" /></div>
        <div class="form-field"><label for="quick-type">Tipo de chamado<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required id="quick-type" v-model="orderForm.maintenance_type"><option value="CORRECTIVE">Corretiva · falha ou reparo</option><option value="PREVENTIVE">Preventiva · revisão programada</option></AppSelect></div>
        <details class="quick-order-options" :open="quickPlanning" @toggle="quickPlanning = $event.target.open"><summary>{{ orderForm.scheduled_at ? `Agendado para ${orderForm.scheduled_at.replace('T', ' · ')}` : 'Planejar agora (opcional)' }}</summary><div class="form-grid"><div class="form-field"><label for="quick-priority">Prioridade<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required id="quick-priority" v-model="orderForm.priority"><option value="NORMAL">Normal</option><option value="ALTA">Alta</option><option value="CRÍTICA">Crítica</option></AppSelect><small v-if="aiHints.urgency" class="ai-hint">Sugestão do relato: {{ aiHints.urgency }}. A prioridade é decisão sua.</small></div><div class="form-field"><label for="quick-technician">Técnico<span class="required-mark" aria-hidden="true" v-if="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status) || orderForm.released"> *</span></label><AppSelect :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status) || orderForm.released" searchable id="quick-technician" v-model="orderForm.technician"><option value="">Definir depois</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></AppSelect></div><div class="form-field span-2"><label for="quick-schedule">Data e hora<span class="required-mark" aria-hidden="true" v-if="quickPlanning && orderForm.status === 'SCHEDULED'"> *</span></label><AppDateTime id="quick-schedule" v-model="orderForm.scheduled_at" type="datetime-local" :required="quickPlanning && orderForm.status === 'SCHEDULED'" /><small>Sem data, o chamado entra na fila como aberto.</small></div></div></details>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy || !equipment.length">{{ busy ? 'Abrindo...' : 'Abrir chamado' }}</button></div>
      </form>
    </ModalDialog>



    <ModalDialog v-if="modal === 'plan'" :title="editing ? 'Editar plano de manutenção' : 'Cadastrar plano de manutenção'" wide @close="modal = null; error = ''"><form @submit.prevent="savePlan"><div class="form-grid three">
      <div class="form-field span-2"><label>Nome do plano<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="planForm.name" required placeholder="Ex.: Revisão a cada 90 dias" /></div><div class="form-field"><label>Criticidade<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="planForm.criticality"><option value="LOW">Baixa</option><option value="MEDIUM">Média</option><option value="HIGH">Alta</option><option value="CRITICAL">Crítica</option></AppSelect></div>
      <div class="form-field span-2"><label>Equipamento<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable v-model="planForm.equipment" required><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }} · {{ formatNumber(item.current_usage_hours) }} h</option></AppSelect></div><div class="form-field"><label>Modalidade<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="planForm.maintenance_type"><option value="PREVENTIVE">Preventiva periódica</option><option value="SCHEDULED">Revisão agendada</option><option v-if="editing?.maintenance_type === 'PRE_RENTAL'" value="PRE_RENTAL">Antes da locação</option><option v-if="editing?.maintenance_type === 'POST_RENTAL'" value="POST_RENTAL">Pós-locação</option></AppSelect></div>
      <div class="form-field"><label>Revisar a cada quantos dias?</label><input v-model="planForm.interval_days" type="number" min="1" placeholder="Ex.: 90" /><small>A primeira OS será criada após esse intervalo; informe uma próxima data para antecipá-la.</small></div><div class="form-field"><label>Última manutenção</label><AppDateTime v-model="planForm.last_service_date" type="date" /></div><div class="form-field"><label>Próxima execução (opcional)</label><AppDateTime v-model="planForm.next_due_date" type="date" /></div>
      <div class="form-field"><label>Periodicidade por uso (h)</label><AppInput mask="decimal" :precision="2" v-model="planForm.usage_limit" min="1" placeholder="Ex.: 250" /></div><div class="form-field"><label>Horas na última manutenção</label><AppInput mask="decimal" :precision="2" v-model="planForm.last_service_usage_hours" min="0" placeholder="Ex.: 120" /></div><div class="form-field"><label>Alertar antes (horas)</label><AppInput mask="decimal" :precision="2" v-model="planForm.advance_notice_usage_hours" min="0" placeholder="Ex.: 10" /></div>
      <div class="form-field"><label>Alertar antes (dias)</label><input v-model="planForm.advance_notice_days" type="number" min="0" placeholder="Ex.: 15" /></div><div class="plan-help span-2"><AlertTriangle :size="18" /><span>Planos críticos vencidos por data ou horas bloqueiam novas reservas e a entrega do equipamento.</span></div>
      <label class="check-line span-3"><input v-model="planForm.active" type="checkbox" />Plano ativo e participando dos alertas</label>
    </div><div v-if="editing && can('media.view')" class="maintenance-order-tools"><button type="button" class="btn secondary" @click="openMedia(editing.equipment)"><Files :size="16" />Mídias do equipamento</button></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><button v-if="editing && can('maintenance.manage')" type="button" class="btn secondary" @click="openClone"><Copy :size="15" />Duplicar para outros equipamentos</button><button v-if="editing" type="button" class="btn secondary" @click="requestDelete('plan', editing)"><Trash2 :size="15" />Excluir plano</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar plano' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="modal === 'plan-clone'" :title="`Duplicar plano · ${editing.name}`" @close="modal = null; error = ''">
      <p class="quick-order-lead">O plano copia periodicidade, criticidade e checklist. O histórico não é copiado: cada equipamento começa o próprio ciclo.</p>
      <div class="clone-targets"><label v-for="item in equipment.filter(e => e.id !== editing.equipment)" :key="item.id" class="check-line"><input v-model="cloneTargets" type="checkbox" :value="item.id" />{{ item.internal_code }} · {{ item.name }}</label></div>
      <div v-if="cloneResult" class="ai-notice ok">{{ cloneResult.created }} plano(s) criado(s)<template v-if="cloneResult.skipped">; {{ cloneResult.skipped }} ignorado(s) por já existir plano com o mesmo nome</template>.</div>
      <div v-if="error" class="error-message">{{ error }}</div>
      <div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button type="button" class="btn primary" :disabled="busy || !cloneTargets.length" @click="submitClone">{{ busy ? 'Duplicando...' : 'Duplicar plano' }}</button></div>
    </ModalDialog>

    <EquipmentMediaModal v-if="mediaEquipment" :equipment="mediaEquipment" :order="mediaOrder" @close="closeMedia" @changed="load" />

    <ConfirmDialog v-if="deleting" :title="deleting.kind === 'order' ? 'Excluir chamado' : 'Excluir plano'" :message="`Excluir “${deleting.item.number || deleting.item.name}”? Esta ação não pode ser desfeita.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
