<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertCircle, CalendarRange, Check, CheckCircle2, Clock3, Plus, Search, Trash2,
} from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import WorkflowFilterSelect from '../components/WorkflowFilterSelect.vue'
import { api, apiError, can, money, rows, shortDate } from '../services/api'
import { transportCosts } from '../services/rentalTransport'

const quotes = ref([])
const route = useRoute()
const customers = ref([])
const modal = ref(false)
const editing = ref(null)
const deleting = ref(null)
const error = ref('')
const busy = ref(false)
const statusFilter = ref('ALL')
const equipmentSearch = ref('')
const availableEquipment = ref([])
const blockedEquipment = ref([])
const availabilityLoading = ref(false)
const availabilityChecked = ref(false)
let availabilityRequest = 0
const discountPercent = ref(0)
const addressLookup = reactive({
  delivery: { cep: '', loading: false, error: '', result: null, request: 0 },
  return: { cep: '', loading: false, error: '', result: null, request: 0 },
})
let addressRequest = 0
const sameAddress = ref(true)
const freightAutomatic = ref(true)
const freightChanged = ref(false)
const operation = ref(null)
const operationQuote = ref(null)
const flowQuote = ref(null)
const flowAction = ref('')
const documents = ref([])
const documentBusy = ref('')
const documentError = ref('')
const recordedDemand = ref([])
const demandBusy = ref(null)
const demandFeedback = ref('')
const notice = ref('')
const operationForm = reactive({ date: '', conditions: '', new_end_date: '', reason: '' })

const form = reactive({ customer: '', start_date: '', end_date: '', status: 'DRAFT', discount: 0, items: [], delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', delivery_complement: '', return_complement: '', delivery_cep: '', return_cep: '', transport_fee: 0 })
const days = computed(() => form.start_date && form.end_date ? Math.max(Math.round((new Date(`${form.end_date}T12:00:00`) - new Date(`${form.start_date}T12:00:00`)) / 86400000) + 1, 1) : 1)
const datesValid = computed(() => form.start_date && form.end_date && form.end_date >= form.start_date)
const selectedConflicts = computed(() => form.items.filter(line => blockedEquipment.value.some(item => item.equipment.id === line.equipment_id)))
const subtotal = computed(() => form.items.reduce((sum, item) => sum + Number(item.daily_rate) * days.value, 0))
const discountBase = computed(() => subtotal.value + Number(form.transport_fee || 0))
const discountAmount = computed(() => Math.round(Math.round(discountBase.value * 100) * Number(discountPercent.value || 0) / 100) / 100)
const total = computed(() => Math.max(discountBase.value - discountAmount.value, 0))
const transportRequired = computed(() => form.delivery_transport_required || form.return_transport_required)
const sharedAddress = computed(() => form.delivery_transport_required && form.return_transport_required && sameAddress.value)
const estimateFor = leg => {
  const source = leg === 'return' && sharedAddress.value ? 'delivery' : leg
  const state = addressLookup[source]
  return state.result?.cep === form[`${source}_cep`] ? state.result.estimate : null
}
const freightCosts = computed(() => transportCosts(form.delivery_transport_required, form.return_transport_required, estimateFor('delivery'), estimateFor('return')))
const freightEstimatesReady = computed(() => transportRequired.value && freightCosts.value.total !== null)
const freightOrigin = computed(() => (form.delivery_transport_required ? estimateFor('delivery') : estimateFor('return')) || estimateFor('return'))
const transportEstimating = computed(() => form.delivery_transport_required && addressLookup.delivery.loading || form.return_transport_required && !sharedAddress.value && addressLookup.return.loading)
const readyToSave = computed(() => Boolean(form.customer && datesValid.value && availabilityChecked.value && !availabilityLoading.value && form.items.length && !selectedConflicts.value.length &&
  (!form.delivery_transport_required || form.delivery_address.trim()) && (!form.return_transport_required || form.return_address.trim()) &&
  !transportEstimating.value && (!transportRequired.value || !freightAutomatic.value || freightEstimatesReady.value) &&
  form.items.every(item => item.daily_rate !== '' && Number(item.daily_rate) >= 0) &&
  (!form.delivery_cep || /^\d{8}$/.test(form.delivery_cep)) && (!form.return_cep || /^\d{8}$/.test(form.return_cep)) &&
  Number(form.transport_fee || 0) >= 0 && discountPercent.value !== '' && Number(discountPercent.value) >= 0 && Number(discountPercent.value) <= 100))
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
const filteredQuotes = computed(() => quotes.value.filter(quote => tabMatches(quote, statusFilter.value)))
const visibleAvailable = computed(() => {
  const term = equipmentSearch.value.trim().toLocaleLowerCase('pt-BR')
  return availableEquipment.value.filter(item => !term || [item.name, item.internal_code, item.category_name].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const visibleBlocked = computed(() => {
  const term = equipmentSearch.value.trim().toLocaleLowerCase('pt-BR')
  return blockedEquipment.value.filter(item => !term || [item.equipment.name, item.equipment.internal_code, item.reason].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})

async function load() {
  const [quoteResponse, customerResponse] = await Promise.all([
    api.get('/rental-quotes/'),
    can('customers.view') ? api.get('/customers/') : Promise.resolve({ data: [] }),
  ])
  quotes.value = rows(quoteResponse.data)
  customers.value = rows(customerResponse.data)
}

const inspectionProgress = (quote, type) => {
  const equipmentIds = new Set(quote.items.map(item => item.equipment))
  const items = quote.inspections?.filter(item => item.inspection_type === type && equipmentIds.has(item.equipment)) || []
  return { done: items.filter(item => item.result !== 'PENDING').length, total: quote.items.length }
}
const taskFor = (quote, leg) => quote.transport_tasks?.find(task => task.leg === leg)
const transportReady = (quote, leg) => !(leg === 'DELIVERY' ? quote.delivery_transport_required : quote.return_transport_required) || taskFor(quote, leg)?.status === 'COMPLETED'
const inspectionsReleased = quote => quote.items.length > 0 && inspectionProgress(quote, 'PRE_RENTAL').done === inspectionProgress(quote, 'PRE_RENTAL').total && !quote.inspections.some(item => item.inspection_type === 'PRE_RENTAL' && quote.items.some(line => line.equipment === item.equipment) && item.result === 'BLOCKED')
function guidanceFor(quote) {
  if (['DRAFT', 'SENT'].includes(quote.status) && !quote.items.length) return { title: 'Orçamento incompleto', detail: 'Adicione ao menos um equipamento para aprovar a reserva.', action: 'edit', blocked: true }
  if (['DRAFT', 'SENT'].includes(quote.status)) return can('rentals.approve')
    ? { title: 'Aprovar e reservar', detail: 'Confirme o orçamento para gerar a reserva e as OS de pré-locação.', action: 'reserve', blocked: false }
    : { title: 'Aguardando aprovação', detail: 'Um usuário de vendas com permissão deve aprovar este orçamento.', action: '', blocked: true }
  if (quote.status === 'APPROVED') {
    const pre = quote.inspections.filter(item => item.inspection_type === 'PRE_RENTAL' && quote.items.some(line => line.equipment === item.equipment))
    const broken = pre.filter(item => item.result === 'BLOCKED')
    const pending = quote.items.length - pre.filter(item => item.result !== 'PENDING').length
    if (broken.length) return { title: 'Entrega bloqueada', detail: `${broken.map(item => item.internal_code).join(', ')} inoperante(s). A Manutenção deve reparar e reavaliar antes da entrega.`, action: 'deliver', blocked: true }
    if (pending > 0) return { title: 'Aguardando Manutenção', detail: `${pending} equipamento(s) ainda precisam da avaliação pré-locação.`, action: 'deliver', blocked: true }
    if (quote.delivery_transport_required && !transportReady(quote, 'DELIVERY')) return { title: 'Aguardando transporte', detail: 'A viagem de entrega deve ser concluída antes de registrar a entrega.', action: 'deliver', blocked: true }
    return can('rentals.dispatch')
      ? { title: 'Registrar entrega', detail: 'Equipamentos liberados; registre a saída para iniciar a locação.', action: 'deliver', blocked: false }
      : { title: 'Aguardando entrega', detail: 'Um usuário autorizado deve registrar a entrega.', action: '', blocked: true }
  }
  if (quote.status === 'ACTIVE') {
    if (quote.return_transport_required && !transportReady(quote, 'RETURN')) return { title: 'Aguardando coleta', detail: 'Conclua a viagem de coleta no Transporte antes da devolução.', action: 'return', blocked: true }
    return can('rentals.return')
      ? { title: 'Registrar devolução', detail: 'Receba o equipamento e abra a avaliação final na Manutenção.', action: 'return', blocked: false }
      : { title: 'Aguardando devolução', detail: 'Um usuário autorizado deve registrar o retorno.', action: '', blocked: true }
  }
  if (quote.status === 'RETURNED') {
    const remaining = quote.items.length - inspectionProgress(quote, 'RETURN').done
    if (remaining > 0) return { title: 'Aguardando Manutenção', detail: `${remaining} equipamento(s) ainda precisam da avaliação final.`, action: 'finalize', blocked: true }
    return can('rentals.return')
      ? { title: 'Concluir devolução', detail: 'Todas as avaliações finais foram registradas.', action: 'finalize', blocked: false }
      : { title: 'Aguardando conclusão', detail: 'Um usuário autorizado deve concluir a devolução.', action: '', blocked: true }
  }
  return { title: quote.status === 'COMPLETED' ? 'Locação concluída' : 'Fluxo encerrado', detail: 'Nenhuma ação operacional pendente.', action: '', blocked: false }
}
function flowSteps(quote) {
  const stage = quote.status
  return [
    { label: 'Orçamento e reserva', detail: stage === 'DRAFT' || stage === 'SENT' ? 'Aguardando aprovação' : 'Reserva confirmada', done: !['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(stage) },
    { label: 'Avaliação pré-locação', detail: `${inspectionProgress(quote, 'PRE_RENTAL').done}/${inspectionProgress(quote, 'PRE_RENTAL').total} equipamento(s) · Manutenção`, done: quote.items.length > 0 && inspectionsReleased(quote) },
    ...(quote.delivery_transport_required ? [{ label: 'Transporte de entrega', detail: taskFor(quote, 'DELIVERY')?.status_label || 'Após a reserva', done: transportReady(quote, 'DELIVERY') }] : []),
    { label: 'Entrega e locação', detail: quote.delivered_at ? shortDate(quote.delivered_at.slice(0, 10)) : 'Aguardando entrega', done: ['ACTIVE', 'RETURNED', 'COMPLETED'].includes(stage) },
    ...(quote.return_transport_required ? [{ label: 'Coleta de devolução', detail: taskFor(quote, 'RETURN')?.status_label || 'Após a entrega', done: transportReady(quote, 'RETURN') }] : []),
    { label: 'Avaliação final', detail: `${inspectionProgress(quote, 'RETURN').done}/${inspectionProgress(quote, 'RETURN').total} equipamento(s) · Manutenção`, done: inspectionProgress(quote, 'RETURN').total > 0 && inspectionProgress(quote, 'RETURN').done === inspectionProgress(quote, 'RETURN').total },
    { label: 'Conclusão da devolução', detail: stage === 'COMPLETED' ? 'Locação concluída' : 'Após a avaliação final', done: stage === 'COMPLETED' },
  ]
}

function actionsFor(quote) {
  const actions = []
  if (can('rentals.manage') && ['DRAFT', 'SENT'].includes(quote.status)) actions.push({ key: 'edit', label: 'Editar orçamento' })
  if (can('rentals.approve') && ['DRAFT', 'SENT'].includes(quote.status)) actions.push({ key: 'reserve', label: 'Aprovar e reservar' })
  if (can('rentals.dispatch') && quote.status === 'APPROVED') actions.push({ key: 'deliver', label: 'Registrar entrega', disabled: !inspectionsReleased(quote) || !transportReady(quote, 'DELIVERY'), reason: 'Aguarde a avaliação pré-locação e, se necessário, o transporte de entrega.' })
  if (can('rentals.extend') && ['APPROVED', 'ACTIVE'].includes(quote.status)) actions.push({ key: 'extend', label: 'Prorrogar locação' })
  if (can('rentals.return') && quote.status === 'ACTIVE') actions.push({ key: 'return', label: 'Registrar devolução', disabled: !transportReady(quote, 'RETURN'), reason: 'Aguarde a coleta pelo Transporte.' })
  if (can('rentals.return') && quote.status === 'RETURNED') actions.push({ key: 'finalize', label: 'Concluir devolução', disabled: inspectionProgress(quote, 'RETURN').done !== inspectionProgress(quote, 'RETURN').total, reason: 'Aguarde a avaliação final na Manutenção.' })
  if (can('rentals.manage') && ['DRAFT', 'SENT', 'APPROVED'].includes(quote.status)) actions.push({ key: 'cancel', label: 'Cancelar locação' })
  if (can('rentals.manage') && ['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(quote.status)) actions.push({ key: 'delete', label: 'Excluir orçamento' })
  return actions
}
const selectedFlowAction = computed(() => actionsFor(flowQuote.value || { status: '', inspections: [], items: [] }).find(item => item.key === flowAction.value))
watch(flowQuote, async quote => {
  flowAction.value = quote && !guidanceFor(quote).blocked ? guidanceFor(quote).action : ''
  documents.value = []
  documentError.value = ''
  if (quote) {
    try {
      const { data } = await api.get(`/rental-quotes/${quote.id}/documents/`)
      if (flowQuote.value?.id === quote.id) documents.value = data
    } catch (event) { if (flowQuote.value?.id === quote.id) documentError.value = apiError(event) }
  }
})
function demandKey(item) { return `${form.customer}-${form.start_date}-${form.end_date}-${item.equipment.id}` }
async function registerDemand(item) {
  if (!form.customer || !datesValid.value) { demandFeedback.value = 'Selecione cliente e período antes de registrar a procura.'; return }
  demandBusy.value = item.equipment.id
  demandFeedback.value = ''
  try {
    const { data } = await api.post('/rental-quotes/unmet-demand/', {
      equipment: item.equipment.id, customer: form.customer,
      start_date: form.start_date, end_date: form.end_date,
    })
    recordedDemand.value.push(demandKey(item))
    demandFeedback.value = data.created ? 'Procura não atendida registrada para análise de compras.' : 'Esta procura já estava registrada.'
  } catch (event) { demandFeedback.value = apiError(event) }
  finally { demandBusy.value = null }
}
async function downloadDocument(quote, item) {
  documentBusy.value = `${item.kind}-${item.version}`
  documentError.value = ''
  try {
    const { data } = await api.get(`/rental-quotes/${quote.id}/documents/${item.id}/pdf/`, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `pandora-${quote.number.toLowerCase()}-${item.kind.toLowerCase()}-v${item.version}.pdf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (event) { documentError.value = apiError(event) }
  finally { documentBusy.value = '' }
}
async function createDocument(quote, kind) {
  documentBusy.value = kind
  documentError.value = ''
  try {
    const { data } = await api.post(`/rental-quotes/${quote.id}/documents/`, { kind })
    const history = await api.get(`/rental-quotes/${quote.id}/documents/`)
    documents.value = history.data
    const item = documents.value.find(entry => entry.id === data.id)
    if (item) await downloadDocument(quote, item)
  } catch (event) { documentError.value = apiError(event) }
  finally { documentBusy.value = '' }
}
function executeFlowAction() {
  const quote = flowQuote.value
  const action = selectedFlowAction.value
  if (!quote || !action || action.disabled) return
  flowQuote.value = null
  if (action.key === 'edit') open(quote)
  else if (action.key === 'reserve') reserve(quote)
  else if (action.key === 'finalize') finalizeReturn(quote)
  else if (action.key === 'delete') deleting.value = quote
  else openOperation(action.key, quote)
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
    return: { url: 'return', payload: { returned_at: operationForm.date, conditions: operationForm.conditions }, message: 'Devolução registrada. OS de inspeção final abertas na Manutenção; equipamentos bloqueados até a conferência.' },
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
  modal.value = false
  editing.value = item
  error.value = ''
  availableEquipment.value = []
  blockedEquipment.value = []
  availabilityChecked.value = false
  equipmentSearch.value = ''
  sameAddress.value = false
  freightAutomatic.value = !item || Boolean(item.transport_estimate?.total)
  freightChanged.value = false
  for (const leg of ['delivery', 'return']) {
    const estimate = item?.transport_estimate?.[leg]
    Object.assign(addressLookup[leg], { cep: item?.[`${leg}_cep`] || '', loading: false, error: '', result: estimate ? { cep: estimate.cep, estimate } : null, request: ++addressRequest })
  }
  if (item) {
    Object.assign(form, {
      customer: item.customer, start_date: item.start_date, end_date: item.end_date, status: item.status,
      discount: item.discount,
      delivery_transport_required: item.delivery_transport_required, return_transport_required: item.return_transport_required,
      delivery_address: item.delivery_address, return_address: item.return_address,
      delivery_complement: item.delivery_complement || '', return_complement: item.return_complement || '',
      delivery_cep: item.delivery_cep || '', return_cep: item.return_cep || '', transport_fee: item.transport_fee,
      items: item.items.map(line => ({ equipment_id: line.equipment, name: line.equipment_name, code: line.internal_code, daily_rate: line.daily_rate, quantity_days: line.quantity_days })),
    })
    const base = Number(item.subtotal) + Number(item.transport_fee)
    discountPercent.value = item.discount_percent != null ? Number(item.discount_percent) : base ? Math.round(Number(item.discount) / base * 10000) / 100 : 0
  } else {
    const today = new Date()
    const later = new Date(today)
    later.setDate(later.getDate() + 3)
    const localDay = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    Object.assign(form, {
      customer: '', start_date: localDay(today), end_date: localDay(later), status: 'DRAFT',
      discount: 0, items: [],
      delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', delivery_complement: '', return_complement: '', delivery_cep: '', return_cep: '', transport_fee: 0,
    })
    discountPercent.value = 0
  }
  sameAddress.value = !item || !item.delivery_transport_required || !item.return_transport_required ||
    ['address', 'cep', 'complement'].every(key => (item[`delivery_${key}`] || '') === (item[`return_${key}`] || ''))
  modal.value = true
  loadAvailability()
}

function onCepInput(leg) {
  const state = addressLookup[leg]
  state.cep = state.cep.replace(/\D/g, '').slice(0, 8)
  state.result = null
  state.error = ''
  state.request = ++addressRequest
  state.loading = false
  form[`${leg}_cep`] = state.cep
  freightAutomatic.value = true
  freightChanged.value = true
}

async function searchAddress(leg, fillAddress = true) {
  const state = addressLookup[leg]
  if (state.loading) return
  state.error = ''
  if (!/^\d{8}$/.test(state.cep)) {
    state.error = 'Informe um CEP com 8 dígitos.'
    return
  }
  freightAutomatic.value = true
  freightChanged.value = true
  state.loading = true
  const request = state.request = ++addressRequest
  const cep = state.cep
  try {
    const { data } = await api.get('/rental-quotes/lookup-address/', { params: { cep } })
    if (!modal.value || request !== state.request || cep !== state.cep) return
    state.result = data
    form[`${leg}_cep`] = data.cep
    if (fillAddress) form[`${leg}_address`] = [data.street, data.neighborhood, `${data.city}/${data.state}`, `CEP ${data.cep.slice(0, 5)}-${data.cep.slice(5)}`].filter(Boolean).join(', ')
  } catch (event) {
    if (request === state.request) state.error = apiError(event)
  } finally {
    if (request === state.request) state.loading = false
  }
}

async function activateFreight(recalculate = false) {
  freightAutomatic.value = true
  freightChanged.value = true
  const legs = ['delivery', 'return'].filter(leg => form[`${leg}_transport_required`] && !(leg === 'return' && sharedAddress.value))
  await Promise.all(legs.map(leg => {
    if (recalculate) addressLookup[leg].result = null
    if (/^\d{8}$/.test(addressLookup[leg].cep) && (recalculate || !estimateFor(leg))) return searchAddress(leg, false)
  }))
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
watch(() => [sharedAddress.value, form.delivery_address, form.delivery_cep, form.delivery_complement, addressLookup.delivery.result], () => {
  if (!sharedAddress.value) return
  for (const suffix of ['address', 'cep', 'complement']) form[`return_${suffix}`] = form[`delivery_${suffix}`]
  Object.assign(addressLookup.return, { cep: addressLookup.delivery.cep, result: addressLookup.delivery.result, error: '', loading: false, request: ++addressRequest })
}, { flush: 'sync' })
watch(() => [freightCosts.value.total, freightAutomatic.value, transportRequired.value], () => {
  if (!modal.value) return
  if (!transportRequired.value) form.transport_fee = 0
  else if (freightAutomatic.value) form.transport_fee = freightCosts.value.total ?? 0
}, { flush: 'sync' })

async function save() {
  if (!readyToSave.value) return
  busy.value = true
  error.value = ''
  const payload = { ...form, discount_percent: Number(discountPercent.value), discount: discountAmount.value,
    return_same_as_delivery: sharedAddress.value,
    calculate_transport: freightAutomatic.value && (!editing.value || freightChanged.value),
    items: form.items.map(({ equipment_id, daily_rate, quantity_days }) => ({ equipment_id, daily_rate, quantity_days })) }
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
function showLinkedQuote() {
  if (!route.query.quote) return
  const matched = quotes.value.find(quote => quote.number === String(route.query.quote))
  if (matched) {
    statusFilter.value = 'ALL'
    flowQuote.value = matched
  }
}
watch(() => route.query.quote, showLinkedQuote)
onMounted(async () => {
  await load()
  showLinkedQuote()
})
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">COMERCIAL</span><h1>Locações e orçamentos</h1><p>Disponibilidade antecipada, composição de preço e acompanhamento do funil.</p></div><button v-if="can('rentals.manage')" class="btn primary" @click="open()"><Plus :size="18" />Gerar orçamento</button></header>
    <div v-if="notice" class="success-strip rental-success-strip"><span>{{ notice }}</span></div>
    <div v-if="error && !modal && !operation" class="floating-error">{{ error }}</div>

    <section class="quote-summary">
      <div><span class="eyebrow">EM NEGOCIAÇÃO</span><strong>{{ activeQuotes.length }}</strong><p>propostas no funil comercial</p></div>
      <div><span class="eyebrow">VALOR DO FUNIL</span><strong>{{ money(activeQuotes.reduce((sum, quote) => sum + Number(quote.total), 0)) }}</strong><p>sem cancelados e expirados</p></div>
      <div><span class="eyebrow">CONVERSÃO</span><strong>{{ quotes.length ? Math.round(quotes.filter(quote => ['APPROVED', 'ACTIVE', 'RETURNED', 'COMPLETED'].includes(quote.status)).length / quotes.length * 100) : 0 }}%</strong><p>orçamentos convertidos em reserva</p></div>
    </section>

    <section class="panel list-panel">
      <header class="list-toolbar workflow-list-toolbar"><WorkflowFilterSelect v-model="statusFilter" :options="statusTabs" label="Etapa da locação" /><span class="result-count">{{ filteredQuotes.length }} orçamento(s)</span></header>
      <div class="table-wrap desktop-list"><table><thead><tr><th>Orçamento</th><th>Cliente</th><th>Período</th><th>Itens</th><th>Status</th><th>Próxima ação</th><th class="right">Total</th><th class="right">Ações</th></tr></thead><tbody>
        <tr v-for="quote in filteredQuotes" :key="quote.id">
          <td><strong>{{ quote.number }}</strong><small>{{ shortDate(quote.created_at?.slice(0, 10)) }} · {{ quote.created_by_name }}</small></td>
          <td>{{ quote.customer_name }}</td><td>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</td><td>{{ quote.items.length }} equipamento(s)</td>
          <td><StatusBadge :value="quote.status" :label="quote.status_label" /><small v-if="quote.status === 'APPROVED'">Manutenção · pré-inspeção {{ inspectionProgress(quote, 'PRE_RENTAL').done }}/{{ inspectionProgress(quote, 'PRE_RENTAL').total }}</small><small v-if="quote.status === 'RETURNED'">Manutenção · inspeção final {{ inspectionProgress(quote, 'RETURN').done }}/{{ inspectionProgress(quote, 'RETURN').total }}</small><small v-if="quote.delivery_transport_required || quote.return_transport_required">Transporte {{ quote.delivery_transport_required && quote.return_transport_required ? 'ida e volta' : quote.delivery_transport_required ? 'de entrega' : 'de coleta' }}</small></td>
          <td><div class="rental-next-step" :class="{ blocked: guidanceFor(quote).blocked }"><strong>{{ guidanceFor(quote).title }}</strong><small>{{ guidanceFor(quote).detail }}</small></div></td>
          <td class="right"><strong>{{ money(quote.total) }}</strong></td>
          <td class="right"><button class="btn secondary rental-open-button" @click="flowQuote = quote">Abrir locação</button></td>
        </tr><tr v-if="!filteredQuotes.length"><td colspan="8" class="empty-cell">Nenhuma locação nesta etapa.</td></tr>
      </tbody></table></div>
      <div class="mobile-card-list"><article v-for="quote in filteredQuotes" :key="quote.id" class="mobile-record-card rental-mobile-card"><header><div><span class="eyebrow">{{ quote.number }}</span><strong>{{ quote.customer_name }}</strong></div><StatusBadge :value="quote.status" :label="quote.status_label" /></header><dl><div><dt>Período</dt><dd>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</dd></div><div><dt>Equipamentos</dt><dd>{{ quote.items.length }}</dd></div><div><dt>Total</dt><dd><strong>{{ money(quote.total) }}</strong></dd></div></dl><div class="rental-next-step" :class="{ blocked: guidanceFor(quote).blocked }"><strong>{{ guidanceFor(quote).title }}</strong><small>{{ guidanceFor(quote).detail }}</small></div><footer><button class="btn secondary" @click="flowQuote = quote">Abrir locação</button></footer></article></div>
    </section>

    <ModalDialog v-if="modal" :title="editing ? `Editar ${editing.number}` : 'Novo orçamento de locação'" wide @close="modal = false">
      <form class="quote-editor" @submit.prevent="save">
        <p class="quote-editor-lead">Escolha o cliente e o período. Os equipamentos disponíveis e o valor aparecem aqui mesmo.</p>
        <div class="form-grid quote-editor-basics"><div class="form-field span-2"><label for="quote-customer">Cliente</label><select id="quote-customer" v-model="form.customer" required><option value="" disabled>Selecione o cliente</option><option v-for="customer in customers" :key="customer.id" :value="customer.id">{{ customer.name }} · {{ customer.document }}</option></select><small v-if="!customers.length">Cadastre um cliente antes de criar o orçamento.</small></div><div class="form-field"><label for="quote-start">Retirada</label><input id="quote-start" v-model="form.start_date" type="date" required /></div><div class="form-field"><label for="quote-end">Devolução prevista</label><input id="quote-end" v-model="form.end_date" type="date" :min="form.start_date" required /></div></div>
        <div class="quote-period-hint"><CalendarRange :size="17" /><span v-if="datesValid">{{ days }} diária(s) · {{ shortDate(form.start_date) }} a {{ shortDate(form.end_date) }}</span><span v-else>Informe uma devolução igual ou posterior à retirada.</span></div>

        <section class="quote-editor-section"><header><div><h3>Equipamentos</h3><p>Selecione um ou mais itens disponíveis nesse período.</p></div><div class="search-box"><Search :size="16" /><input v-model="equipmentSearch" placeholder="Buscar equipamento" aria-label="Buscar equipamento" :disabled="!datesValid" /></div></header>
          <div v-if="!datesValid" class="quote-picker-placeholder">Informe as datas para consultar os equipamentos.</div>
          <div v-else-if="availabilityLoading" class="quote-picker-placeholder"><Clock3 :size="18" />Consultando disponibilidade...</div>
          <template v-else-if="availabilityChecked"><div class="quote-stock-count"><CheckCircle2 :size="16" />{{ availableEquipment.length }} disponível(is) no período</div><div v-if="visibleAvailable.length" class="equipment-picker quote-editor-picker"><button v-for="item in visibleAvailable" :key="item.id" type="button" :aria-pressed="form.items.some(line => line.equipment_id === item.id)" :class="{ selected: form.items.some(line => line.equipment_id === item.id) }" @click="toggle(item)"><span class="select-check"><Check :size="15" /></span><div><strong>{{ item.name }}</strong><small>{{ item.internal_code }} · {{ item.category_name }}</small></div><b>{{ money(item.daily_rate) }}<small>/dia</small></b></button></div><p v-else class="quote-picker-placeholder">Nenhum equipamento encontrado. Tente outra busca ou período.</p><details v-if="visibleBlocked.length" class="blocked-equipment"><summary><AlertCircle :size="17" />{{ visibleBlocked.length }} indisponível(is) neste período</summary><article v-for="item in visibleBlocked" :key="item.equipment.id"><div><strong>{{ item.equipment.internal_code }} · {{ item.equipment.name }}</strong><span>{{ item.reason }}</span></div><button v-if="can('rentals.manage')" type="button" class="btn secondary" :disabled="!form.customer || demandBusy === item.equipment.id || recordedDemand.includes(demandKey(item))" @click="registerDemand(item)">{{ recordedDemand.includes(demandKey(item)) ? 'Procura registrada' : 'Registrar procura não atendida' }}</button></article><small v-if="!form.customer">Selecione um cliente para registrar uma procura não atendida.</small><p v-if="demandFeedback" class="demand-feedback">{{ demandFeedback }}</p></details></template>
        </section>

        <section class="quote-editor-section"><header><div><h3>Itens do orçamento</h3><p v-if="!form.items.length">Selecione um equipamento acima para começar.</p><p v-else>{{ form.items.length }} equipamento(s) · ajuste a diária se necessário.</p></div></header><div class="quote-lines"><div v-for="item in form.items" :key="item.equipment_id" class="quote-line"><div><strong>{{ item.name }}</strong><span>{{ item.code }} · {{ days }} diária(s)</span></div><label class="rate-editor"><span>Diária (R$)</span><input v-model="item.daily_rate" type="number" min="0" step="0.01" required /></label><strong>{{ money(Number(item.daily_rate) * days) }}</strong><button type="button" class="icon-btn" :aria-label="`Remover ${item.name}`" @click="toggle({ id: item.equipment_id })"><Trash2 :size="17" /></button></div></div><div v-if="selectedConflicts.length" class="quote-conflict"><AlertCircle :size="17" />{{ selectedConflicts.length }} item(ns) selecionado(s) ficaram indisponíveis após a troca de datas. Remova-os ou escolha outro período.</div></section>

        <details class="quote-extra"><summary>Transporte (opcional)</summary><div class="form-grid">
          <div class="form-field span-2"><label>Serviços de transporte</label><div class="transport-choices"><label><input v-model="form.delivery_transport_required" type="checkbox" @change="activateFreight()" /> Entrega com veículo</label><label><input v-model="form.return_transport_required" type="checkbox" @change="activateFreight()" /> Coleta na devolução</label></div><small>Sem transporte selecionado, a retirada e a devolução são no balcão.</small></div>
          <label v-if="form.delivery_transport_required && form.return_transport_required" class="same-address-toggle span-2"><input v-model="sameAddress" type="checkbox" @change="activateFreight()" /><span>Coletar no mesmo endereço da entrega<small>CEP, endereço e complemento são compartilhados. Desmarque para informar outro local.</small></span></label>
          <div v-if="form.delivery_transport_required" class="address-search-group span-2">
            <div class="form-field"><label for="quote-delivery-cep">{{ sharedAddress ? 'CEP da entrega e coleta' : 'CEP da entrega' }}</label><div class="address-lookup-row"><input id="quote-delivery-cep" v-model="addressLookup.delivery.cep" inputmode="numeric" maxlength="8" :required="freightAutomatic" placeholder="00000000" @input="onCepInput('delivery')" @blur="addressLookup.delivery.cep.length === 8 && !estimateFor('delivery') && searchAddress('delivery')" /><button type="button" class="btn secondary" :disabled="addressLookup.delivery.loading" @click="searchAddress('delivery')">{{ addressLookup.delivery.loading ? 'Calculando...' : 'Buscar CEP' }}</button></div><small v-if="addressLookup.delivery.error" class="address-lookup-error">{{ addressLookup.delivery.error }}</small><small v-else>Informe o CEP para preencher o endereço e calcular o transporte. Acrescente o número abaixo.</small></div>
            <div class="form-field"><label for="quote-delivery-address">{{ sharedAddress ? 'Endereço da entrega e coleta' : 'Endereço completo da entrega' }}</label><input id="quote-delivery-address" v-model="form.delivery_address" required maxlength="255" placeholder="Rua, número, bairro, cidade/UF" /></div>
            <div class="form-field"><label for="quote-delivery-complement">Complemento (opcional)</label><input id="quote-delivery-complement" v-model="form.delivery_complement" maxlength="120" placeholder="Bloco, apartamento, portão ou ponto de referência" /></div>
            <p v-if="estimateFor('delivery')?.fee == null && addressLookup.delivery.result" class="address-lookup-error">{{ estimateFor('delivery')?.reason }}</p>
          </div>
          <div v-if="form.return_transport_required && !sharedAddress" class="address-search-group span-2">
            <div class="form-field"><label for="quote-return-cep">CEP da coleta</label><div class="address-lookup-row"><input id="quote-return-cep" v-model="addressLookup.return.cep" inputmode="numeric" maxlength="8" :required="freightAutomatic" placeholder="00000000" @input="onCepInput('return')" @blur="addressLookup.return.cep.length === 8 && !estimateFor('return') && searchAddress('return')" /><button type="button" class="btn secondary" :disabled="addressLookup.return.loading" @click="searchAddress('return')">{{ addressLookup.return.loading ? 'Calculando...' : 'Buscar CEP' }}</button></div><small v-if="addressLookup.return.error" class="address-lookup-error">{{ addressLookup.return.error }}</small><small v-else>O custo da coleta será somado ao da entrega, quando selecionada.</small></div>
            <div class="form-field"><label for="quote-return-address">Endereço completo da coleta</label><input id="quote-return-address" v-model="form.return_address" required maxlength="255" placeholder="Rua, número, bairro, cidade/UF" /></div>
            <div class="form-field"><label for="quote-return-complement">Complemento da coleta (opcional)</label><input id="quote-return-complement" v-model="form.return_complement" maxlength="120" placeholder="Bloco, apartamento, portão ou ponto de referência" /></div>
            <p v-if="estimateFor('return')?.fee == null && addressLookup.return.result" class="address-lookup-error">{{ estimateFor('return')?.reason }}</p>
          </div>
          <div v-if="transportRequired" class="freight-summary span-2" aria-live="polite">
            <template v-if="freightAutomatic"><div v-if="form.delivery_transport_required"><span>Entrega</span><strong>{{ freightCosts.delivery === null ? 'A calcular' : money(freightCosts.delivery) }}</strong></div><div v-if="form.return_transport_required"><span>Coleta na devolução</span><strong>{{ freightCosts.collection === null ? 'A calcular' : money(freightCosts.collection) }}</strong></div></template>
            <div class="freight-total"><span>Total do transporte</span><strong>{{ freightAutomatic && !freightEstimatesReady ? 'A calcular' : money(form.transport_fee) }}</strong></div>
            <small v-if="freightAutomatic && !freightEstimatesReady">{{ transportEstimating ? 'Calculando o transporte...' : 'Consulte o CEP de cada endereço para calcular antes de salvar.' }}</small>
            <small v-else-if="!freightAutomatic">Valor do orçamento anterior preservado. <button type="button" class="text-action" @click="activateFreight(true)">Recalcular pelos CEPs</button></small>
          </div>
          <p v-if="freightEstimatesReady && freightAutomatic" class="freight-estimate-note span-2">Custo aplicado automaticamente a partir de {{ freightOrigin?.origin_label }}. {{ freightOrigin?.provisional_origin ? 'Origem provisória: configure o CEP do depósito e as tarifas para uso real.' : '' }} Distância aproximada; não é rota viária nem tarifa oficial.</p>
        </div></details>

        <div class="quote-editor-footer"><div class="quote-editor-values"><span>Equipamentos <strong>{{ money(subtotal) }}</strong></span><span v-if="transportRequired">Transporte <strong>{{ freightAutomatic && !freightEstimatesReady ? 'A calcular' : money(form.transport_fee) }}</strong></span><label>Desconto (%)<input v-model="discountPercent" type="number" min="0" max="100" step="0.01" /></label><span class="discount-breakdown">{{ money(discountAmount) }} de desconto sobre equipamentos + transporte</span><div>{{ transportRequired && freightAutomatic && !freightEstimatesReady ? 'Total parcial (falta transporte)' : 'Total estimado' }} <strong>{{ money(total) }}</strong></div></div><div class="form-field quote-editor-status"><label for="quote-status">Etapa</label><select id="quote-status" v-model="form.status"><option value="DRAFT">Rascunho</option><option value="SENT">Enviado ao cliente</option></select><small>Salvar o orçamento não reserva estoque. A reserva ocorre somente na aprovação.</small></div></div>
        <div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = false">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy || !readyToSave">{{ busy ? 'Salvando...' : (editing ? 'Salvar alterações' : 'Salvar orçamento') }}</button></div>
      </form>
    </ModalDialog>
    <ModalDialog v-if="flowQuote" :title="`Fluxo da locação · ${flowQuote.number}`" @close="flowQuote = null">
      <div class="operation-context"><span class="eyebrow">{{ flowQuote.customer_name }}</span><strong>{{ shortDate(flowQuote.start_date) }} → {{ shortDate(flowQuote.end_date) }}</strong><small>{{ flowQuote.items.length }} equipamento(s) · {{ money(flowQuote.total) }}</small></div>
      <div class="rental-guidance" :class="{ blocked: guidanceFor(flowQuote).blocked }"><span class="eyebrow">PRÓXIMA AÇÃO</span><strong>{{ guidanceFor(flowQuote).title }}</strong><p>{{ guidanceFor(flowQuote).detail }}</p></div>
      <ol class="rental-flow-list"><li v-for="(item, index) in flowSteps(flowQuote)" :key="index" :class="{ done: item.done }"><span class="flow-step-icon"><Check v-if="item.done" :size="16" /><span v-else>{{ index + 1 }}</span></span><div><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></div></li></ol>
      <div v-if="flowQuote.status === 'CANCELLED'" class="period-callout">Reserva cancelada: {{ flowQuote.cancellation_reason }}</div>
      <div v-if="actionsFor(flowQuote).length" class="rental-flow-actions"><label for="rental-flow-action">O que deseja fazer?</label><div><select id="rental-flow-action" v-model="flowAction"><option value="" disabled>Selecione uma ação</option><option v-for="action in actionsFor(flowQuote)" :key="action.key" :value="action.key" :disabled="action.disabled">{{ action.label }}</option></select><button class="btn primary" :disabled="!selectedFlowAction || selectedFlowAction.disabled || busy" @click="executeFlowAction">Continuar</button></div><small v-for="action in actionsFor(flowQuote).filter(item => item.disabled)" :key="action.key">{{ action.label }}: {{ action.reason }}</small></div>
      <details class="rental-documents"><summary>Documentos comerciais e comprovantes</summary><p>PDFs versionados do registro no momento da geração. Não são documentos fiscais nem comprovantes assinados.</p><div v-if="can('rentals.manage')" class="rental-document-actions"><button class="btn secondary" :disabled="!!documentBusy" @click="createDocument(flowQuote, 'QUOTE')">Gerar orçamento em PDF</button><button v-if="flowQuote.delivered_at" class="btn secondary" :disabled="!!documentBusy" @click="createDocument(flowQuote, 'DELIVERY')">Gerar comprovante de entrega</button><button v-if="flowQuote.returned_at" class="btn secondary" :disabled="!!documentBusy" @click="createDocument(flowQuote, 'RETURN')">Gerar comprovante de devolução</button></div><div v-if="documentError" class="error-message">{{ documentError }}</div><div v-if="documents.length" class="rental-document-list"><button v-for="item in documents" :key="item.id" class="rental-document-item" :disabled="!!documentBusy" @click="downloadDocument(flowQuote, item)"><span><strong>{{ item.kind_label }} · versão {{ item.version }}</strong><small>{{ shortDate(item.created_at?.slice(0, 10)) }} · {{ item.created_by_name }}</small></span><span>Baixar PDF</span></button></div><small v-else>Nenhum documento gerado para esta locação.</small></details>
      <router-link v-if="can('fiscal.view')" class="fiscal-rental-link" :to="{ path: '/fiscal', query: { rental: flowQuote.id } }">Conferir preparação fiscal desta locação</router-link>
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
    <ConfirmDialog v-if="deleting" title="Excluir orçamento" :message="`Excluir “${deleting.number}”? A operação pode ser impedida se houver vínculos posteriores.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
