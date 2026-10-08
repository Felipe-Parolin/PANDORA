<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  AlertCircle, CalendarRange, Check, CheckCircle2,
  ClipboardCheck, Clock3, PackageCheck, Pencil, Plus, RotateCcw, Search, Trash2,
  Truck, XCircle, Route,
} from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import RentalInspectionModal from '../components/RentalInspectionModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, money, rows, shortDate } from '../services/api'

const quotes = ref([])
const customers = ref([])
const modal = ref(false)
const editing = ref(null)
const deleting = ref(null)
const error = ref('')
const busy = ref(false)
const statusFilter = ref('ALL')
const quoteSearch = ref('')
const equipmentSearch = ref('')
const availableEquipment = ref([])
const blockedEquipment = ref([])
const availabilityLoading = ref(false)
const availabilityChecked = ref(false)
let availabilityRequest = 0
const inspectionContext = ref(null)
const operation = ref(null)
const operationQuote = ref(null)
const flowQuote = ref(null)
const notice = ref('')
const operationForm = reactive({ date: '', conditions: '', new_end_date: '', reason: '' })

const form = reactive({ customer: '', start_date: '', end_date: '', status: 'DRAFT', conditions: '', discount: 0, notes: '', items: [], delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', transport_fee: 0 })
const days = computed(() => form.start_date && form.end_date ? Math.max(Math.round((new Date(`${form.end_date}T12:00:00`) - new Date(`${form.start_date}T12:00:00`)) / 86400000) + 1, 1) : 1)
const datesValid = computed(() => form.start_date && form.end_date && form.end_date >= form.start_date)
const selectedConflicts = computed(() => form.items.filter(line => blockedEquipment.value.some(item => item.equipment.id === line.equipment_id)))
const subtotal = computed(() => form.items.reduce((sum, item) => sum + Number(item.daily_rate) * days.value, 0))
const total = computed(() => Math.max(subtotal.value + Number(form.transport_fee || 0) - Number(form.discount || 0), 0))
const readyToSave = computed(() => Boolean(form.customer && datesValid.value && availabilityChecked.value && !availabilityLoading.value && form.items.length && !selectedConflicts.value.length &&
  (!form.delivery_transport_required || form.delivery_address.trim()) && (!form.return_transport_required || form.return_address.trim()) &&
  form.items.every(item => item.daily_rate !== '' && Number(item.daily_rate) >= 0) &&
  Number(form.transport_fee || 0) >= 0 && Number(form.discount || 0) >= 0 && Number(form.discount || 0) <= subtotal.value + Number(form.transport_fee || 0)))
const activeQuotes = computed(() => quotes.value.filter(item => ['DRAFT', 'SENT', 'APPROVED', 'ACTIVE', 'RETURNED'].includes(item.status)))
const tabMatches = (quote, key) => ({
  ALL: true,
  PROPOSAL: ['DRAFT', 'SENT'].includes(quote.status),
  APPROVED: quote.status === 'APPROVED',
  ACTIVE: quote.status === 'ACTIVE',
  RETURNED: quote.status === 'RETURNED',
  COMPLETED: quote.status === 'COMPLETED',
  CLOSED: ['CANCELLED', 'EXPIRED'].includes(quote.status),
}[key])
const statusTabs = computed(() => [
  { key: 'ALL', label: 'Todos' },
  { key: 'PROPOSAL', label: 'Propostas' },
  { key: 'APPROVED', label: 'Reservadas' },
  { key: 'ACTIVE', label: 'Em locação' },
  { key: 'RETURNED', label: 'Em inspeção' },
  { key: 'COMPLETED', label: 'Concluídas' },
  { key: 'CLOSED', label: 'Canceladas' },
].map(item => ({ ...item, count: quotes.value.filter(quote => tabMatches(quote, item.key)).length })))
const filteredQuotes = computed(() => {
  const term = quoteSearch.value.trim().toLocaleLowerCase('pt-BR')
  return quotes.value.filter(quote => tabMatches(quote, statusFilter.value)).filter(quote => !term || [quote.number, quote.customer_name].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const visibleAvailable = computed(() => {
  const term = equipmentSearch.value.trim().toLocaleLowerCase('pt-BR')
  return availableEquipment.value.filter(item => !term || [item.name, item.internal_code, item.category_name].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const visibleBlocked = computed(() => {
  const term = equipmentSearch.value.trim().toLocaleLowerCase('pt-BR')
  return blockedEquipment.value.filter(item => !term || [item.equipment.name, item.equipment.internal_code, item.reason].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})

async function load() {
  const [quoteResponse, customerResponse] = await Promise.all([api.get('/rental-quotes/'), api.get('/customers/')])
  quotes.value = rows(quoteResponse.data)
  customers.value = rows(customerResponse.data)
}

const inspectionProgress = (quote, type) => {
  const items = quote.inspections?.filter(item => item.inspection_type === type) || []
  return { done: items.filter(item => item.result !== 'PENDING').length, total: quote.items.length }
}
const taskFor = (quote, leg) => quote.transport_tasks?.find(task => task.leg === leg)
const transportReady = (quote, leg) => !(leg === 'DELIVERY' ? quote.delivery_transport_required : quote.return_transport_required) || taskFor(quote, leg)?.status === 'COMPLETED'
const inspectionsReleased = quote => inspectionProgress(quote, 'PRE_RENTAL').done === inspectionProgress(quote, 'PRE_RENTAL').total && !quote.inspections.some(item => item.inspection_type === 'PRE_RENTAL' && item.result === 'BLOCKED')
function flowSteps(quote) {
  const stage = quote.status
  return [
    { label: 'Orçamento e reserva', detail: stage === 'DRAFT' || stage === 'SENT' ? 'Aguardando aprovação' : 'Reserva confirmada', done: !['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(stage), link: null },
    { label: 'Inspeção pré-locação', detail: `${inspectionProgress(quote, 'PRE_RENTAL').done}/${inspectionProgress(quote, 'PRE_RENTAL').total} equipamento(s)`, done: quote.items.length > 0 && inspectionsReleased(quote), link: can('maintenance.view') ? { name: 'maintenance', query: { quote: quote.number } } : null },
    ...(quote.delivery_transport_required ? [{ label: 'Transporte de entrega', detail: taskFor(quote, 'DELIVERY')?.status_label || 'Após a reserva', done: transportReady(quote, 'DELIVERY'), link: can('logistics.view') ? { name: 'logistics', query: { quote: quote.number } } : null }] : []),
    { label: 'Entrega e locação', detail: quote.delivered_at ? shortDate(quote.delivered_at.slice(0, 10)) : 'Aguardando entrega', done: ['ACTIVE', 'RETURNED', 'COMPLETED'].includes(stage), link: null },
    ...(quote.return_transport_required ? [{ label: 'Coleta de devolução', detail: taskFor(quote, 'RETURN')?.status_label || 'Após a entrega', done: transportReady(quote, 'RETURN'), link: can('logistics.view') ? { name: 'logistics', query: { quote: quote.number } } : null }] : []),
    { label: 'Inspeção final e conclusão', detail: `${inspectionProgress(quote, 'RETURN').done}/${inspectionProgress(quote, 'RETURN').total} equipamento(s)`, done: stage === 'COMPLETED', link: null },
  ]
}

function localDateTime() {
  const date = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  return date.toISOString().slice(0, 16)
}

function openOperation(kind, quote) {
  operation.value = kind
  operationQuote.value = quote
  error.value = ''
  Object.assign(operationForm, {
    date: localDateTime(),
    conditions: '',
    new_end_date: quote.end_date,
    reason: '',
  })
}

async function reserve(quote) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.post(`/rental-quotes/${quote.id}/reserve/`)
    notice.value = `${quote.number} reservada. Chamados de inspeção pré-locação abertos na Manutenção.${quote.delivery_transport_required ? ' A viagem de entrega foi criada em Transporte.' : ''}`
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function submitOperation() {
  const quote = operationQuote.value
  const kind = operation.value
  busy.value = true
  error.value = ''
  notice.value = ''
  const config = {
    deliver: { url: 'deliver', payload: { delivered_at: operationForm.date, conditions: operationForm.conditions }, message: 'Entrega registrada e equipamentos marcados como locados.' },
    extend: { url: 'extend', payload: { new_end_date: operationForm.new_end_date, conditions: operationForm.conditions }, message: 'Prorrogação registrada após nova validação de disponibilidade.' },
    return: { url: 'return', payload: { returned_at: operationForm.date, conditions: operationForm.conditions }, message: 'Devolução registrada. Equipamentos bloqueados até a inspeção final.' },
    cancel: { url: 'cancel', payload: { reason: operationForm.reason }, message: 'Locação cancelada e equipamentos liberados.' },
  }[kind]
  try {
    await api.post(`/rental-quotes/${quote.id}/${config.url}/`, config.payload)
    operation.value = null
    operationQuote.value = null
    notice.value = config.message
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function finalizeReturn(quote) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/rental-quotes/${quote.id}/finalize-return/`)
    const routed = data.routed_to_maintenance || []
    notice.value = routed.length ? `Devolução concluída. ${routed.join(', ')} encaminhado(s) para manutenção.` : 'Devolução concluída e equipamentos liberados.'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

function open(item = null) {
  editing.value = item
  error.value = ''
  availableEquipment.value = []
  blockedEquipment.value = []
  availabilityChecked.value = false
  equipmentSearch.value = ''
  if (item) {
    Object.assign(form, {
      customer: item.customer, start_date: item.start_date, end_date: item.end_date, status: item.status,
      conditions: item.conditions, discount: item.discount, notes: item.notes,
      delivery_transport_required: item.delivery_transport_required, return_transport_required: item.return_transport_required,
      delivery_address: item.delivery_address, return_address: item.return_address, transport_fee: item.transport_fee,
      items: item.items.map(line => ({ equipment_id: line.equipment, name: line.equipment_name, code: line.internal_code, daily_rate: line.daily_rate, quantity_days: line.quantity_days })),
    })
  } else {
    const today = new Date()
    const later = new Date(today)
    later.setDate(later.getDate() + 3)
    const localDay = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    Object.assign(form, {
      customer: '', start_date: localDay(today), end_date: localDay(later), status: 'DRAFT',
      conditions: 'Locação somente de equipamento. Entrega e devolução conforme acordado.', discount: 0, notes: '', items: [],
      delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', transport_fee: 0,
    })
  }
  modal.value = true
  loadAvailability()
}

async function loadAvailability() {
  const request = ++availabilityRequest
  availabilityChecked.value = false
  availableEquipment.value = []
  blockedEquipment.value = []
  if (!datesValid.value) {
    availabilityLoading.value = false
    return
  }
  availabilityLoading.value = true
  error.value = ''
  try {
    const params = { start: form.start_date, end: form.end_date }
    if (editing.value) params.ignore_quote = editing.value.id
    const { data } = await api.get('/rental-quotes/availability/', { params })
    if (request !== availabilityRequest || !modal.value) return
    availableEquipment.value = data.available.map(item => item.equipment)
    blockedEquipment.value = data.blocked
    availabilityChecked.value = true
  } catch (e) {
    if (request === availabilityRequest && modal.value) error.value = apiError(e)
  } finally {
    if (request === availabilityRequest) availabilityLoading.value = false
  }
}

function toggle(item) {
  const index = form.items.findIndex(line => line.equipment_id === item.id)
  if (index >= 0) form.items.splice(index, 1)
  else form.items.push({ equipment_id: item.id, name: item.name, code: item.internal_code, daily_rate: item.daily_rate, quantity_days: days.value })
}

watch(() => [form.start_date, form.end_date], () => {
  availabilityChecked.value = false
  form.items.forEach(item => { item.quantity_days = days.value })
  if (modal.value) loadAvailability()
}, { flush: 'sync' })
watch(() => [form.delivery_transport_required, form.return_transport_required], ([delivery, returning]) => {
  if (!delivery && !returning) form.transport_fee = 0
})

async function save() {
  if (!readyToSave.value) return
  busy.value = true
  error.value = ''
  const payload = { ...form, items: form.items.map(({ equipment_id, daily_rate, quantity_days }) => ({ equipment_id, daily_rate, quantity_days })) }
  try {
    editing.value ? await api.patch(`/rental-quotes/${editing.value.id}/`, payload) : await api.post('/rental-quotes/', payload)
    modal.value = false
    editing.value = null
    await load()
  } catch (e) {
    error.value = apiError(e)
  } finally {
    busy.value = false
  }
}

async function remove() {
  busy.value = true
  try {
    await api.delete(`/rental-quotes/${deleting.value.id}/`)
    deleting.value = null
    await load()
  } catch (e) {
    error.value = apiError(e)
    deleting.value = null
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">COMERCIAL</span><h1>Locações e orçamentos</h1><p>Disponibilidade antecipada, composição de preço e acompanhamento do funil.</p></div><button v-if="can('rentals.manage')" class="btn primary" @click="open()"><Plus :size="18" />Gerar orçamento</button></header>
    <div v-if="notice" class="success-strip">{{ notice }}</div>
    <div v-if="error && !modal && !operation && !inspectionContext" class="floating-error">{{ error }}</div>

    <section class="quote-summary">
      <div><span class="eyebrow">EM NEGOCIAÇÃO</span><strong>{{ activeQuotes.length }}</strong><p>propostas no funil comercial</p></div>
      <div><span class="eyebrow">VALOR DO FUNIL</span><strong>{{ money(activeQuotes.reduce((sum, quote) => sum + Number(quote.total), 0)) }}</strong><p>sem cancelados e expirados</p></div>
      <div><span class="eyebrow">CONVERSÃO</span><strong>{{ quotes.length ? Math.round(quotes.filter(quote => ['APPROVED', 'ACTIVE', 'RETURNED', 'COMPLETED'].includes(quote.status)).length / quotes.length * 100) : 0 }}%</strong><p>orçamentos convertidos em reserva</p></div>
    </section>

    <div class="workflow-tabs quote-tabs" role="tablist" aria-label="Filtrar orçamentos por status"><button v-for="item in statusTabs" :key="item.key" :class="{ active: statusFilter === item.key }" @click="statusFilter = item.key"><span>{{ item.label }}</span><b>{{ item.count }}</b></button></div>

    <section class="panel list-panel">
      <header class="list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="quoteSearch" placeholder="Buscar por número ou cliente" /></div><span class="result-count">{{ filteredQuotes.length }} orçamento(s)</span></header>
      <div class="table-wrap desktop-list"><table><thead><tr><th>Orçamento</th><th>Cliente</th><th>Período</th><th>Itens</th><th>Status</th><th class="right">Total</th><th class="right">Ações</th></tr></thead><tbody>
        <tr v-for="quote in filteredQuotes" :key="quote.id">
          <td><strong>{{ quote.number }}</strong><small>{{ shortDate(quote.created_at?.slice(0, 10)) }} · {{ quote.created_by_name }}</small></td>
          <td>{{ quote.customer_name }}</td><td>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</td><td>{{ quote.items.length }} equipamento(s)</td>
          <td><StatusBadge :value="quote.status" :label="quote.status_label" /><small v-if="quote.status === 'APPROVED'">Manutenção · pré-inspeção {{ inspectionProgress(quote, 'PRE_RENTAL').done }}/{{ inspectionProgress(quote, 'PRE_RENTAL').total }}</small><small v-if="quote.status === 'RETURNED'">Inspeção final {{ inspectionProgress(quote, 'RETURN').done }}/{{ inspectionProgress(quote, 'RETURN').total }}</small><small v-if="quote.delivery_transport_required || quote.return_transport_required">Transporte {{ quote.delivery_transport_required && quote.return_transport_required ? 'ida e volta' : quote.delivery_transport_required ? 'de entrega' : 'de coleta' }}</small></td>
          <td class="right"><strong>{{ money(quote.total) }}</strong></td>
          <td class="right"><div class="row-actions rental-row-actions">
            <button class="icon-btn table-action" title="Ver fluxo da locação" @click="flowQuote = quote"><Route :size="17" /></button>
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT'].includes(quote.status)" class="icon-btn table-action" title="Editar orçamento" @click="open(quote)"><Pencil :size="17" /></button>
            <button v-if="can('rentals.approve') && ['DRAFT', 'SENT'].includes(quote.status)" class="icon-btn success-action" title="Aprovar e reservar" :disabled="busy" @click="reserve(quote)"><PackageCheck :size="17" /></button>
            <router-link v-if="can('maintenance.view') && quote.status === 'APPROVED'" class="icon-btn table-action" title="Ver chamados de pré-locação na manutenção" :to="{ name: 'maintenance', query: { quote: quote.number } }"><ClipboardCheck :size="17" /></router-link>
            <router-link v-if="can('logistics.view') && quote.status === 'APPROVED' && quote.delivery_transport_required" class="icon-btn table-action" title="Planejar transporte de entrega" :to="{ name: 'logistics', query: { quote: quote.number } }"><Truck :size="17" /></router-link>
            <button v-if="can('rentals.dispatch') && quote.status === 'APPROVED'" class="icon-btn success-action" :title="!transportReady(quote, 'DELIVERY') ? 'Conclua a viagem de entrega' : 'Registrar entrega'" :disabled="!inspectionsReleased(quote) || !transportReady(quote, 'DELIVERY')" @click="openOperation('deliver', quote)"><PackageCheck :size="17" /></button>
            <button v-if="can('rentals.extend') && ['APPROVED', 'ACTIVE'].includes(quote.status)" class="icon-btn table-action" title="Prorrogar locação" @click="openOperation('extend', quote)"><CalendarRange :size="17" /></button>
            <router-link v-if="can('logistics.view') && quote.status === 'ACTIVE' && quote.return_transport_required" class="icon-btn table-action" title="Planejar coleta de devolução" :to="{ name: 'logistics', query: { quote: quote.number } }"><Truck :size="17" /></router-link>
            <button v-if="can('rentals.return') && quote.status === 'ACTIVE'" class="icon-btn table-action" :title="!transportReady(quote, 'RETURN') ? 'Conclua a coleta de devolução' : 'Registrar devolução'" :disabled="!transportReady(quote, 'RETURN')" @click="openOperation('return', quote)"><RotateCcw :size="17" /></button>
            <button v-if="['RETURNED', 'COMPLETED'].includes(quote.status)" class="icon-btn table-action" title="Inspeção final" @click="inspectionContext = { quote, type: 'RETURN' }"><ClipboardCheck :size="17" /></button>
            <button v-if="can('rentals.return') && quote.status === 'RETURNED'" class="icon-btn success-action" title="Concluir devolução" :disabled="inspectionProgress(quote, 'RETURN').done !== inspectionProgress(quote, 'RETURN').total" @click="finalizeReturn(quote)"><CheckCircle2 :size="17" /></button>
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT', 'APPROVED'].includes(quote.status)" class="icon-btn danger-icon" title="Cancelar" @click="openOperation('cancel', quote)"><XCircle :size="17" /></button>
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(quote.status)" class="icon-btn danger-icon" title="Excluir" @click="deleting = quote"><Trash2 :size="17" /></button>
          </div></td>
        </tr><tr v-if="!filteredQuotes.length"><td colspan="7" class="empty-cell">Nenhuma locação nesta etapa.</td></tr>
      </tbody></table></div>
      <div class="mobile-card-list"><article v-for="quote in filteredQuotes" :key="quote.id" class="mobile-record-card rental-mobile-card"><header><div><span class="eyebrow">{{ quote.number }}</span><strong>{{ quote.customer_name }}</strong></div><StatusBadge :value="quote.status" :label="quote.status_label" /></header><dl><div><dt>Período</dt><dd>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</dd></div><div><dt>Equipamentos</dt><dd>{{ quote.items.length }}</dd></div><div><dt>Total</dt><dd><strong>{{ money(quote.total) }}</strong></dd></div></dl><footer>
        <button class="btn secondary" @click="flowQuote = quote"><Route :size="15" />Ver fluxo</button>
        <button v-if="can('rentals.manage') && ['DRAFT', 'SENT'].includes(quote.status)" class="btn secondary" @click="open(quote)"><Pencil :size="15" />Editar</button>
        <button v-if="can('rentals.approve') && ['DRAFT', 'SENT'].includes(quote.status)" class="btn primary" @click="reserve(quote)"><PackageCheck :size="15" />Reservar</button>
        <router-link v-if="can('maintenance.view') && quote.status === 'APPROVED'" class="btn secondary" :to="{ name: 'maintenance', query: { quote: quote.number } }"><ClipboardCheck :size="15" />Ver chamados</router-link>
        <span v-else-if="quote.status === 'APPROVED'" class="rental-inspection-note">Pré-locação na Manutenção: {{ inspectionProgress(quote, 'PRE_RENTAL').done }}/{{ inspectionProgress(quote, 'PRE_RENTAL').total }}</span>
        <router-link v-if="can('logistics.view') && quote.status === 'APPROVED' && quote.delivery_transport_required" class="btn secondary" :to="{ name: 'logistics', query: { quote: quote.number } }"><Truck :size="15" />Entrega · transporte</router-link>
        <button v-if="can('rentals.dispatch') && quote.status === 'APPROVED'" class="btn primary" :disabled="!inspectionsReleased(quote) || !transportReady(quote, 'DELIVERY')" @click="openOperation('deliver', quote)"><PackageCheck :size="15" />Entregar</button>
        <button v-if="can('rentals.extend') && ['APPROVED', 'ACTIVE'].includes(quote.status)" class="btn secondary" @click="openOperation('extend', quote)"><CalendarRange :size="15" />Prorrogar</button>
        <router-link v-if="can('logistics.view') && quote.status === 'ACTIVE' && quote.return_transport_required" class="btn secondary" :to="{ name: 'logistics', query: { quote: quote.number } }"><Truck :size="15" />Coleta · transporte</router-link>
        <button v-if="can('rentals.return') && quote.status === 'ACTIVE'" class="btn primary" :disabled="!transportReady(quote, 'RETURN')" @click="openOperation('return', quote)"><RotateCcw :size="15" />Devolver</button>
        <button v-if="['RETURNED', 'COMPLETED'].includes(quote.status)" class="btn secondary" @click="inspectionContext = { quote, type: 'RETURN' }"><ClipboardCheck :size="15" />Inspeção final</button>
        <button v-if="can('rentals.return') && quote.status === 'RETURNED'" class="btn primary" :disabled="inspectionProgress(quote, 'RETURN').done !== inspectionProgress(quote, 'RETURN').total" @click="finalizeReturn(quote)"><CheckCircle2 :size="15" />Concluir</button>
      </footer></article></div>
    </section>

    <ModalDialog v-if="modal" :title="editing ? `Editar ${editing.number}` : 'Novo orçamento de locação'" wide @close="modal = false">
      <form class="quote-editor" @submit.prevent="save">
        <p class="quote-editor-lead">Escolha o cliente e o período. Os equipamentos disponíveis e o valor aparecem aqui mesmo.</p>
        <div class="form-grid quote-editor-basics"><div class="form-field span-2"><label for="quote-customer">Cliente</label><select id="quote-customer" v-model="form.customer" required><option value="" disabled>Selecione o cliente</option><option v-for="customer in customers" :key="customer.id" :value="customer.id">{{ customer.name }} · {{ customer.document }}</option></select><small v-if="!customers.length">Cadastre um cliente antes de criar o orçamento.</small></div><div class="form-field"><label for="quote-start">Retirada</label><input id="quote-start" v-model="form.start_date" type="date" required /></div><div class="form-field"><label for="quote-end">Devolução prevista</label><input id="quote-end" v-model="form.end_date" type="date" :min="form.start_date" required /></div></div>
        <div class="quote-period-hint"><CalendarRange :size="17" /><span v-if="datesValid">{{ days }} diária(s) · {{ shortDate(form.start_date) }} a {{ shortDate(form.end_date) }}</span><span v-else>Informe uma devolução igual ou posterior à retirada.</span></div>

        <section class="quote-editor-section"><header><div><h3>Equipamentos</h3><p>Selecione um ou mais itens disponíveis nesse período.</p></div><div class="search-box"><Search :size="16" /><input v-model="equipmentSearch" placeholder="Buscar equipamento" aria-label="Buscar equipamento" :disabled="!datesValid" /></div></header>
          <div v-if="!datesValid" class="quote-picker-placeholder">Informe as datas para consultar os equipamentos.</div>
          <div v-else-if="availabilityLoading" class="quote-picker-placeholder"><Clock3 :size="18" />Consultando disponibilidade...</div>
          <template v-else-if="availabilityChecked"><div class="quote-stock-count"><CheckCircle2 :size="16" />{{ availableEquipment.length }} disponível(is) no período</div><div v-if="visibleAvailable.length" class="equipment-picker quote-editor-picker"><button v-for="item in visibleAvailable" :key="item.id" type="button" :aria-pressed="form.items.some(line => line.equipment_id === item.id)" :class="{ selected: form.items.some(line => line.equipment_id === item.id) }" @click="toggle(item)"><span class="select-check"><Check :size="15" /></span><div><strong>{{ item.name }}</strong><small>{{ item.internal_code }} · {{ item.category_name }}</small></div><b>{{ money(item.daily_rate) }}<small>/dia</small></b></button></div><p v-else class="quote-picker-placeholder">Nenhum equipamento encontrado. Tente outra busca ou período.</p><details v-if="visibleBlocked.length" class="blocked-equipment"><summary><AlertCircle :size="17" />{{ visibleBlocked.length }} indisponível(is) neste período</summary><article v-for="item in visibleBlocked" :key="item.equipment.id"><div><strong>{{ item.equipment.internal_code }} · {{ item.equipment.name }}</strong><span>{{ item.reason }}</span></div></article></details></template>
        </section>

        <section class="quote-editor-section"><header><div><h3>Itens do orçamento</h3><p v-if="!form.items.length">Selecione um equipamento acima para começar.</p><p v-else>{{ form.items.length }} equipamento(s) · ajuste a diária se necessário.</p></div></header><div class="quote-lines"><div v-for="item in form.items" :key="item.equipment_id" class="quote-line"><div><strong>{{ item.name }}</strong><span>{{ item.code }} · {{ days }} diária(s)</span></div><label class="rate-editor"><span>Diária (R$)</span><input v-model="item.daily_rate" type="number" min="0" step="0.01" required /></label><strong>{{ money(Number(item.daily_rate) * days) }}</strong><button type="button" class="icon-btn" :aria-label="`Remover ${item.name}`" @click="toggle({ id: item.equipment_id })"><Trash2 :size="17" /></button></div></div><div v-if="selectedConflicts.length" class="quote-conflict"><AlertCircle :size="17" />{{ selectedConflicts.length }} item(ns) selecionado(s) ficaram indisponíveis após a troca de datas. Remova-os ou escolha outro período.</div></section>

        <details class="quote-extra"><summary>Transporte e condições (opcional)</summary><div class="form-grid"><div class="form-field span-2"><label>Transporte</label><div class="transport-choices"><label><input v-model="form.delivery_transport_required" type="checkbox" /> Entrega com veículo</label><label><input v-model="form.return_transport_required" type="checkbox" /> Coleta na devolução</label></div><small>Se não marcar, a retirada e a devolução são no balcão.</small></div><div v-if="form.delivery_transport_required" class="form-field span-2"><label for="quote-delivery-address">Endereço de entrega</label><input id="quote-delivery-address" v-model="form.delivery_address" required maxlength="255" placeholder="Rua, número, bairro e cidade" /></div><div v-if="form.return_transport_required" class="form-field span-2"><label for="quote-return-address">Endereço da coleta</label><input id="quote-return-address" v-model="form.return_address" required maxlength="255" placeholder="Rua, número, bairro e cidade" /></div><div class="form-field span-2"><label for="quote-conditions">Condições comerciais</label><textarea id="quote-conditions" v-model="form.conditions" rows="2" /></div><div class="form-field span-2"><label for="quote-notes">Observações internas</label><textarea id="quote-notes" v-model="form.notes" rows="2" placeholder="Não aparecem nas condições enviadas ao cliente." /></div></div></details>

        <div class="quote-editor-footer"><div class="quote-editor-values"><span>Equipamentos <strong>{{ money(subtotal) }}</strong></span><label v-if="form.delivery_transport_required || form.return_transport_required">Transporte (R$)<input v-model="form.transport_fee" type="number" min="0" step="0.01" /></label><label>Desconto (R$)<input v-model="form.discount" type="number" min="0" :max="subtotal + Number(form.transport_fee || 0)" step="0.01" /></label><div>Total estimado <strong>{{ money(total) }}</strong></div></div><div class="form-field quote-editor-status"><label for="quote-status">Etapa</label><select id="quote-status" v-model="form.status"><option value="DRAFT">Rascunho</option><option value="SENT">Enviado ao cliente</option></select><small>Salvar o orçamento não reserva estoque. A reserva ocorre somente na aprovação.</small></div></div>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = false">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy || !readyToSave">{{ busy ? 'Salvando...' : (editing ? 'Salvar alterações' : 'Salvar orçamento') }}</button></div>
      </form>
    </ModalDialog>
    <ModalDialog v-if="flowQuote" :title="`Fluxo da locação · ${flowQuote.number}`" @close="flowQuote = null">
      <div class="operation-context"><span class="eyebrow">{{ flowQuote.customer_name }}</span><strong>{{ shortDate(flowQuote.start_date) }} → {{ shortDate(flowQuote.end_date) }}</strong><small>{{ flowQuote.items.length }} equipamento(s) · {{ money(flowQuote.total) }}</small></div>
      <ol class="rental-flow-list"><li v-for="(item, index) in flowSteps(flowQuote)" :key="index" :class="{ done: item.done }"><span class="flow-step-icon"><Check v-if="item.done" :size="16" /><span v-else>{{ index + 1 }}</span></span><div><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></div><router-link v-if="item.link" class="btn secondary" :to="item.link" @click="flowQuote = null">Abrir</router-link></li></ol>
      <div v-if="flowQuote.status === 'CANCELLED'" class="period-callout">Reserva cancelada: {{ flowQuote.cancellation_reason }}</div>
      <div class="modal-actions"><span class="spacer" /><button type="button" class="btn secondary" @click="flowQuote = null">Fechar</button></div>
    </ModalDialog>
    <ModalDialog v-if="operation && operationQuote" :title="({ deliver: 'Registrar entrega', extend: 'Prorrogar locação', return: 'Registrar devolução', cancel: 'Cancelar locação' })[operation]" @close="operation = null">
      <form @submit.prevent="submitOperation"><div class="form-grid">
        <div class="operation-context span-2"><span class="eyebrow">{{ operationQuote.number }}</span><strong>{{ operationQuote.customer_name }}</strong><small>{{ shortDate(operationQuote.start_date) }} → {{ shortDate(operationQuote.end_date) }} · {{ operationQuote.items.length }} equipamento(s)</small></div>
        <div v-if="['deliver', 'return'].includes(operation)" class="form-field span-2"><label>{{ operation === 'deliver' ? 'Data e hora da entrega' : 'Data e hora da devolução' }}</label><input v-model="operationForm.date" type="datetime-local" required /></div>
        <div v-if="operation === 'extend'" class="form-field span-2"><label>Nova data de término</label><input v-model="operationForm.new_end_date" type="date" :min="operationQuote.end_date" required /></div>
        <div v-if="operation !== 'cancel'" class="form-field span-2"><label>Condições e observações</label><textarea v-model="operationForm.conditions" rows="4" :placeholder="operation === 'deliver' ? 'Responsável pela retirada, acessórios e condições da entrega.' : (operation === 'return' ? 'Estado informado no recebimento; a inspeção detalhada vem na próxima etapa.' : 'Condições comerciais da prorrogação.')" /></div>
        <div v-else class="form-field span-2"><label>Motivo do cancelamento</label><textarea v-model="operationForm.reason" rows="4" required placeholder="Registre por que a reserva foi cancelada." /></div>
      </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="operation = null">Voltar</button><span class="spacer" /><button class="btn" :class="operation === 'cancel' ? 'danger' : 'primary'" :disabled="busy">{{ busy ? 'Processando...' : 'Confirmar' }}</button></div></form>
    </ModalDialog>
    <RentalInspectionModal v-if="inspectionContext" :quote="inspectionContext.quote" :type="inspectionContext.type" @close="inspectionContext = null" @changed="load" />
    <ConfirmDialog v-if="deleting" title="Excluir orçamento" :message="`Excluir “${deleting.number}”? A operação pode ser impedida se houver vínculos posteriores.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
