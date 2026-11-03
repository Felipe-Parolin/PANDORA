<script setup>
import { formatTaxId } from '../services/formatters'
import { matchesSearch, sortRecords, dateValue } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { toDateTimeInput, toDateTimePayload } from '../services/formDates'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertCircle, CalendarRange, Check, CheckCircle2, Eye, EyeOff,
  ClipboardCheck, Clock3, PackageCheck, Pencil, Plus, RotateCcw, Search, Trash2,
  Truck, XCircle, Route, MessageCircle,
} from 'lucide-vue-next'
import RentalEquipmentSummary from '../components/RentalEquipmentSummary.vue'
import RentalActions from '../components/RentalActions.vue'
import ItemDestinationEditor from '../components/ItemDestinationEditor.vue'
import { splitAddress, fullAddress, effectiveLocation, destinationGroups } from '../services/rentalDestinations'
import { periodDays, periodEnvelope, periodGroups } from '../services/rentalPeriods'
import { operationCandidates, operationProblem, itemStage, inspectionProgress, taskFor, transportReady, inspectionsReleased } from '../services/rentalActions'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import RentalDocumentsPanel from '../components/RentalDocumentsPanel.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, money, rows, shortDate, fetchAll } from '../services/api'

const quotes = ref([])
const route = useRoute(), router = useRouter()
const customers = ref([]), customersLoading = ref(false)
const packages = ref([])
const selectedPackageId = ref('')
const modal = ref(false)
const quoteStep = ref(0), furthestStep = ref(0), scheduleDelivery = ref(false), scheduleReturn = ref(false), expandedActions = ref(null)
const quoteSteps = ['Cliente e período', 'Equipamentos', 'Entrega e devolução', 'Valores e condições', 'Revisão e conclusão']
const editing = ref(null)
const deleting = ref(null)
const error = ref('')
const busy = ref(false)
const statusFilter = ref('ALL')
const quoteSearch = ref('')
const equipmentSearch = ref('')
const quoteCustomer = ref(''), quoteTransport = ref(''), quoteFrom = ref(''), quoteTo = ref(''), quoteOrdering = ref('-created')
const pickerOrdering = ref('code'), pickerBrand = ref(''), pickerMinRate = ref(''), pickerMaxRate = ref('')
const quoteSortOptions = [['-created', 'Mais recentes'], ['created', 'Mais antigos'], ['number', 'Nº da locação'], ['customer', 'Cliente A–Z'], ['start', 'Próxima retirada'], ['end', 'Próxima devolução'], ['-total', 'Maior valor'], ['total', 'Menor valor']]
const pickerSortOptions = [['code', 'Código'], ['name', 'Nome A–Z'], ['-name', 'Nome Z–A'], ['daily_rate', 'Menor diária'], ['-daily_rate', 'Maior diária'], ['brand', 'Marca A–Z']]
const quoteCustomerOptions = computed(() => [...new Map(quotes.value.map(item => [String(item.customer), item.customer_name])).entries()].sort((a,b) => a[1].localeCompare(b[1], 'pt-BR')))
function clearQuoteFilters() { quoteSearch.value = ''; quoteCustomer.value = ''; quoteTransport.value = ''; quoteFrom.value = ''; quoteTo.value = ''; quoteOrdering.value = '-created'; statusFilter.value = 'ALL' }
function clearPickerFilters() { clearCategory() }
const availableEquipment = ref([])
const blockedEquipment = ref([])
const availabilityNext = ref(null)
const availabilityCount = ref(0)
const availabilityLoading = ref(false)
const availabilityChecked = ref(false)
const selectionChecked = ref(false), selectionLoading = ref(false), selectionConflicts = ref([])
let selectionRequest = 0
const categorySummary = ref([])
const allCategories = ref([])
const categoryLoading = ref(false)
const selectedCategory = ref(null)
const lostModal = ref(false)
const lostBusy = ref(false)
const lostError = ref('')
const lostForm = reactive({ category: '', new_category_name: '', requested_item: '', quantity: 1, requested_days: 1, expected_daily_rate: '', reason: 'UNAVAILABLE', notes: '' })
const lostRateAuto = ref(true)
let editorSession = 0
let initializingEditor = false
let categoryRequest = 0
let availabilityRequest = 0
const discountPercent = ref(0)
const addressLookup = reactive({
  delivery: { cep: '', loading: false, cepLoading: false, cepRequest: 0, error: '', result: null, request: 0 },
  return: { cep: '', loading: false, cepLoading: false, cepRequest: 0, error: '', result: null, request: 0 },
})
const freightManuallyEdited = ref(false)
const freightNeedsCalculation = ref(false)
const separateDestinations = ref(false)
const destinationLookups = reactive(new Set())
function setDestinationLookup(id,leg,loading) { const key=`${id}:${leg}`; loading ? destinationLookups.add(key) : destinationLookups.delete(key) }
const autoFreightTimers = {}
const operation = ref(null)
const operationQuote = ref(null)
const flowQuote = ref(null)
const equipmentQuote = ref(null)
const { page: equipmentPage, items: equipmentRows } = usePagination(computed(() => equipmentQuote.value?.items || []), [equipmentQuote])
const notice = ref('')
const transportShortcut = ref('')
const maintenanceShortcut = ref('')
const pickerPeriod = reactive({ start_date: '', end_date: '' })
const operationForm = reactive({ equipment_ids: [], date: '', conditions: '', new_end_date: '', reason: '' })

const form = reactive({ customer: '', start_date: '', end_date: '', requested_delivery_at: '', requested_return_at: '', requested_delivery_notes: '', status: 'DRAFT', conditions: '', discount: 0, notes: '', items: [], delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', delivery_number: '', return_number: '', delivery_complement: '', return_complement: '', delivery_cep: '', return_cep: '', transport_fee: 0, estimated_transport_fee: 0, transport_fee_adjustment_reason: '' })
const destinationDefaults = computed(() => ({...form,requested_delivery_at:scheduleDelivery.value ? form.requested_delivery_at : null,requested_return_at:scheduleReturn.value ? form.requested_return_at : null}))
const destinationsFor = leg => destinationGroups(form.items, destinationDefaults.value, leg, separateDestinations.value)
const usesCommon = leg => !separateDestinations.value || form.items.some(item => !Object.keys(item[`${leg}_location`] || {}).length)
const customDestinationsAllowed = computed(() => form.items.length > 2 || separateDestinations.value)
function changeItemDestination(item,leg,enabled) { item[`${leg}_location`] = enabled ? { ...effectiveLocation(item,destinationDefaults.value,leg,false) } : {} }
const selectedCustomer = computed(() => customers.value.find(item => String(item.id) === String(form.customer)))
const addressSource = reactive({ delivery: 'customer', return: 'customer' })
function useCustomerAddress(leg) {
  const customer = selectedCustomer.value
  if (!customer?.address) return
  const location = splitAddress(customer.address, customer.address_number)
  form[`${leg}_address`] = location.address
  form[`${leg}_number`] = location.number
  form[`${leg}_cep`] = customer.address_cep || customer.address.match(/\b(\d{5})-?(\d{3})\b/)?.slice(1).join('') || ''
  addressLookup[leg].cep = form[`${leg}_cep`]
  form[`${leg}_complement`] = ''
  addressSource[leg] = 'customer'
  invalidateFreight(leg)
}
watch(() => form.customer, () => {
  if (!modal.value || initializingEditor) return
  for (const leg of ['delivery', 'return']) {
    if (addressSource[leg] !== 'customer') continue
    if (selectedCustomer.value?.address) useCustomerAddress(leg)
    else { form[`${leg}_number`] = ''; form[`${leg}_address`] = ''; form[`${leg}_cep`] = ''; addressLookup[leg].cep = ''; invalidateFreight(leg) }
  }
}, { flush: 'sync' })
const days = computed(() => form.start_date && form.end_date ? Math.max(Math.round((new Date(`${form.end_date}T12:00:00`) - new Date(`${form.start_date}T12:00:00`)) / 86400000) + 1, 1) : 1)
const lineDays = item => periodDays(item.start_date || form.start_date, item.end_date || form.end_date)
const envelope = computed(() => periodEnvelope(form.items, form))
const deliveryClock = computed({ get: () => form.requested_delivery_at?.slice(11,16) || '', set: value => { form.requested_delivery_at = value ? `${envelope.value.start_date}T${value}` : '' } })
const returnClock = computed({ get: () => form.requested_return_at?.slice(11,16) || '', set: value => { form.requested_return_at = value ? `${envelope.value.end_date}T${value}` : '' } })
watch(envelope, value => {
  if (initializingEditor || !modal.value) return
  if (form.requested_delivery_at) form.requested_delivery_at = `${value.start_date}T${form.requested_delivery_at.slice(11,16)}`
  if (form.requested_return_at) form.requested_return_at = `${value.end_date}T${form.requested_return_at.slice(11,16)}`
}, { flush: 'sync' })
const pickerDatesValid = computed(() => Boolean(periodDays(pickerPeriod.start_date, pickerPeriod.end_date)))
function useDefaultPeriod(item) { if (item.uses_default_period) { item.start_date = form.start_date; item.end_date = form.end_date } }
const operationItems = computed(() => operationQuote.value ? operationCandidates(operationQuote.value, operation.value).map(item => ({ ...item, problem: operationProblem(operationQuote.value, operation.value, item), destination: effectiveLocation(item,operationQuote.value,operation.value === 'return' ? 'return' : 'delivery') })) : [])
const datesValid = computed(() => form.start_date && form.end_date && form.end_date >= form.start_date)
const showList = computed(() => Boolean(selectedCategory.value || equipmentSearch.value.trim() || pickerBrand.value.trim() || pickerMinRate.value !== '' || pickerMaxRate.value !== '' || pickerOrdering.value !== 'code'))
const selectedConflicts = computed(() => form.items.filter(line => selectionConflicts.value.some(item => item.equipment.id === line.equipment_id)))
const subtotal = computed(() => form.items.reduce((sum, item) => sum + Number(item.daily_rate) * lineDays(item), 0))
const discountBase = computed(() => subtotal.value + Number(form.transport_fee || 0))
const discountAmount = computed(() => Math.round(Math.round(discountBase.value * 100) * Number(discountPercent.value || 0) / 100) / 100)
const total = computed(() => Math.max(discountBase.value - discountAmount.value, 0))
const freightEstimatesReady = computed(() => (!form.delivery_transport_required || addressLookup.delivery.result?.estimate?.fee !== null && addressLookup.delivery.result?.estimate?.fee !== undefined) &&
  (!form.return_transport_required || addressLookup.return.result?.estimate?.fee !== null && addressLookup.return.result?.estimate?.fee !== undefined) &&
  (form.delivery_transport_required || form.return_transport_required))
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
const filteredQuotes = computed(() => sortRecords(quotes.value.filter(quote => tabMatches(quote, statusFilter.value) && (!quoteCustomer.value || String(quote.customer) === quoteCustomer.value) && (!quoteFrom.value || quote.end_date >= quoteFrom.value) && (!quoteTo.value || quote.start_date <= quoteTo.value) && (!quoteTransport.value || ({ any: quote.delivery_transport_required || quote.return_transport_required, delivery: quote.delivery_transport_required, return: quote.return_transport_required, none: !quote.delivery_transport_required && !quote.return_transport_required })[quoteTransport.value]) && matchesSearch(quoteSearch.value, quote.number, quote.customer_name, ...quote.items.map(item => `${item.equipment_name} ${item.internal_code}`))), quoteOrdering.value, { created: item => dateValue(item.created_at), number: item => item.number, customer: item => item.customer_name, start: item => dateValue(item.start_date), end: item => dateValue(item.end_date), total: item => Number(item.total || 0) }))
const visibleAvailable = computed(() => availableEquipment.value.filter(item => matchesSearch(equipmentSearch.value, item.name, item.internal_code, item.category_name, item.brand, item.model)))
const visibleBlocked = computed(() => blockedEquipment.value.filter(item => matchesSearch(equipmentSearch.value, item.equipment.name, item.equipment.internal_code, item.equipment.brand, item.equipment.model, item.reason)))

async function load() {
  customersLoading.value = true
  try {
    const [quoteResponse, customerResponse, packageResponse] = await Promise.all([
      fetchAll('/rental-quotes/'),
      can('customers.view') ? fetchAll('/customers/') : Promise.resolve({ data: [] }),
      fetchAll('/packages/?active=true'),
    ])
    quotes.value = rows(quoteResponse.data)
    customers.value = rows(customerResponse.data)
    packages.value = rows(packageResponse.data)
  } finally { customersLoading.value = false }
}

function flowSteps(quote) {
  const stage = quote.status
  const delivered = quote.items.filter(item => itemStage(quote,item) !== 'PENDING').length
  const finished = quote.items.filter(item => itemStage(quote,item) === 'COMPLETED').length
  const returned = quote.items.some(item => ['RETURNED', 'COMPLETED'].includes(itemStage(quote,item)))
  const trips = leg => { const tasks = (quote.transport_tasks || []).filter(task => task.leg === leg && task.status !== 'CANCELLED'); return `${tasks.filter(task => task.status === 'COMPLETED').length}/${tasks.length} viagem(ns) concluída(s)` }
  return [
    { label: 'Orçamento e reserva', detail: stage === 'DRAFT' || stage === 'SENT' ? 'Aguardando aprovação' : 'Reserva confirmada', done: !['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(stage), link: null },
    { label: 'Inspeção pré-locação', detail: `${inspectionProgress(quote, 'PRE_RENTAL').done}/${inspectionProgress(quote, 'PRE_RENTAL').total} equipamento(s)`, done: quote.items.length > 0 && inspectionsReleased(quote), link: can('maintenance.view') ? { name: 'maintenance', query: { quote: quote.number } } : null },
    ...(quote.delivery_transport_required ? [{ label: 'Transporte de entrega', detail: trips('DELIVERY'), done: transportReady(quote, 'DELIVERY'), link: can('logistics.view') ? { name: 'logistics', query: { quote: quote.number } } : null }] : []),
    { label: 'Entrega e locação', detail: `${delivered}/${quote.items.length} equipamento(s) entregue(s)`, done: delivered === quote.items.length && delivered > 0, link: null },
    ...(quote.return_transport_required ? [{ label: 'Coleta de devolução', detail: trips('RETURN'), done: transportReady(quote, 'RETURN'), link: can('logistics.view') ? { name: 'logistics', query: { quote: quote.number } } : null }] : []),
    { label: 'Inspeção final na manutenção', detail: `${inspectionProgress(quote, 'RETURN').done}/${inspectionProgress(quote, 'RETURN').total} equipamento(s)`, done: inspectionProgress(quote, 'RETURN').total > 0 && inspectionProgress(quote, 'RETURN').done === inspectionProgress(quote, 'RETURN').total, link: can('maintenance.view') && returned ? { name: 'maintenance', query: { quote: quote.number } } : null },
    { label: 'Conclusão da devolução', detail: `${finished}/${quote.items.length} equipamento(s) concluído(s)`, done: stage === 'COMPLETED', link: null },
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
    equipment_ids: operationCandidates(quote, kind).filter(item => !operationProblem(quote, kind, item)).map(item => item.equipment),
  })
}

async function reserve(quote) {
  busy.value = true
  error.value = ''
  notice.value = ''
  transportShortcut.value = ''
  maintenanceShortcut.value = ''
  try {
    await api.post(`/rental-quotes/${quote.id}/reserve/`)
    notice.value = `${quote.number} reservada. Chamados de inspeção pré-locação abertos na Manutenção.${quote.delivery_transport_required ? ' A viagem de entrega foi criada em Transporte.' : ''}`
    transportShortcut.value = quote.delivery_transport_required ? quote.number : ''
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function submitOperation() {
  const quote = operationQuote.value
  const kind = operation.value
  if (kind !== 'cancel' && !operationForm.equipment_ids.length) { error.value = 'Selecione pelo menos um equipamento.'; return }
  busy.value = true
  error.value = ''
  notice.value = ''
  transportShortcut.value = ''
  maintenanceShortcut.value = ''
  const config = {
    deliver: { url: 'deliver', payload: { delivered_at: operationForm.date, conditions: operationForm.conditions }, message: 'Entrega registrada e equipamentos marcados como locados.' },
    extend: { url: 'extend', payload: { new_end_date: operationForm.new_end_date, conditions: operationForm.conditions }, message: 'Prorrogação registrada após nova validação de disponibilidade.' },
    return: { url: 'return', payload: { returned_at: operationForm.date, conditions: operationForm.conditions }, message: 'Devolução registrada. OS de inspeção final abertas na Manutenção; equipamentos bloqueados até a conferência.' },
    finalize: { url: 'finalize-return', payload: {}, message: 'Devolução dos itens selecionados concluída. Itens com avaria permanecem na manutenção.' },
    cancel: { url: 'cancel', payload: { reason: operationForm.reason }, message: 'Locação cancelada e equipamentos liberados.' },
  }[kind]
  if (kind !== 'cancel') config.payload.equipment_ids = [...operationForm.equipment_ids]
  try {
    await api.post(`/rental-quotes/${quote.id}/${config.url}/`, config.payload)
    operation.value = null
    operationQuote.value = null
    notice.value = config.message
    if (kind === 'return') maintenanceShortcut.value = quote.number
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

function finalizeReturn(quote) { openOperation('finalize', quote) }

function open(item = null) {
  modal.value = false
  editorSession += 1
  initializingEditor = true
  destinationLookups.clear()
  separateDestinations.value = false
  for (const leg of ['delivery','return']) clearTimeout(autoFreightTimers[leg])
  freightNeedsCalculation.value = !item
  quoteStep.value = 0; furthestStep.value = item ? 4 : 0
  scheduleDelivery.value = Boolean(item?.requested_delivery_at); scheduleReturn.value = Boolean(item?.requested_return_at)
  editing.value = item
  selectedPackageId.value = ''
  error.value = ''
  availableEquipment.value = []
  blockedEquipment.value = []
  availabilityChecked.value = false
  equipmentSearch.value = ''
  selectedCategory.value = null
  pickerOrdering.value = 'code'; pickerBrand.value = ''; pickerMinRate.value = ''; pickerMaxRate.value = ''
  categorySummary.value = []
  freightManuallyEdited.value = Boolean(item && Number(item.transport_fee) !== Number(item.estimated_transport_fee || 0))
  for (const leg of ['delivery', 'return']) {
    addressSource[leg] = item ? 'custom' : 'customer'
    Object.assign(addressLookup[leg], { cep: item?.[`${leg}_cep`] || '', loading: false, cepLoading: false, cepRequest: addressLookup[leg].cepRequest + 1, error: '', result: null, request: addressLookup[leg].request + 1 })
  }
  if (item) {
    Object.assign(form, {
      customer: item.customer, start_date: item.start_date, end_date: item.end_date, requested_delivery_at: toDateTimeInput(item.requested_delivery_at), requested_return_at: toDateTimeInput(item.requested_return_at), requested_delivery_notes: item.requested_delivery_notes || '', status: item.status,
      conditions: item.conditions, discount: item.discount, notes: item.notes,
      delivery_transport_required: item.delivery_transport_required, return_transport_required: item.return_transport_required,
      delivery_address: item.delivery_address, return_address: item.return_address, delivery_number: item.delivery_number || '', return_number: item.return_number || '',
      delivery_complement: item.delivery_complement || '', return_complement: item.return_complement || '',
      delivery_cep: item.delivery_cep || '', return_cep: item.return_cep || '', transport_fee: item.transport_fee, estimated_transport_fee: item.estimated_transport_fee || 0, transport_fee_adjustment_reason: item.transport_fee_adjustment_reason || '',
      items: item.items.map(line => ({ equipment_id: line.equipment, name: line.equipment_name, code: line.internal_code, daily_rate: line.daily_rate, quantity_days: line.quantity_days, delivery_location: { ...(line.delivery_location || {}) }, return_location: { ...(line.return_location || {}) }, start_date: line.start_date || item.start_date, end_date: line.end_date || item.end_date, uses_default_period: (line.start_date || item.start_date) === item.start_date && (line.end_date || item.end_date) === item.end_date })),
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
      requested_delivery_at: '', requested_return_at: '', requested_delivery_notes: '', conditions: 'Locação somente de equipamento. Entrega e devolução conforme acordado.', discount: 0, notes: '', items: [],
      delivery_transport_required: false, return_transport_required: false, delivery_address: '', return_address: '', delivery_number: '', return_number: '', delivery_complement: '', return_complement: '', delivery_cep: '', return_cep: '', transport_fee: 0, estimated_transport_fee: 0, transport_fee_adjustment_reason: '',
    })
    discountPercent.value = 0
  }
  for (const leg of ['delivery','return']) {
    const location = splitAddress(form[`${leg}_address`], form[`${leg}_number`])
    form[`${leg}_address`] = location.address; form[`${leg}_number`] = location.number
  }
  separateDestinations.value = form.items.some(item => Object.keys(item.delivery_location || {}).length || Object.keys(item.return_location || {}).length)
  Object.assign(pickerPeriod, { start_date: form.start_date, end_date: form.end_date })
  initializingEditor = false
  modal.value = true
  loadCategories()
  loadAvailability()
  checkSelectedAvailability()
}

function invalidateFreight(leg) {
  const state = addressLookup[leg]
  state.request += 1
  state.result = null; state.error = ''; state.loading = false
  freightNeedsCalculation.value = true
  applyFreightEstimate()
}

function onCepInput(leg) {
  const state = addressLookup[leg]
  state.cepRequest += 1; state.cepLoading = false
  state.cep = state.cep.replace(/\D/g, '').slice(0, 8)
  form[`${leg}_cep`] = state.cep
  invalidateFreight(leg)
}

function applyFreightEstimate() {
  if (!freightEstimatesReady.value) {
    if (freightNeedsCalculation.value) {
      form.estimated_transport_fee = 0
      if (!freightManuallyEdited.value) form.transport_fee = 0
    }
    return
  }
  const estimate = (form.delivery_transport_required ? Number(addressLookup.delivery.result.estimate.fee) : 0) +
    (form.return_transport_required ? Number(addressLookup.return.result.estimate.fee) : 0)
  form.estimated_transport_fee = Math.round(estimate * 100) / 100
  freightNeedsCalculation.value = false
  if (!freightManuallyEdited.value) {
    form.transport_fee = form.estimated_transport_fee
    const approximate = ['delivery', 'return'].filter(leg => form[`${leg}_transport_required`] && addressLookup[leg].result?.estimate?.approximate_destination)
    form.transport_fee_adjustment_reason = approximate.length ? `Estimativa automática pela mesma rua do CEP: ${approximate.map(leg => leg === 'delivery' ? 'entrega' : 'coleta').join(' e ')}.` : ''
  }
}

function useCalculatedFreight() {
  freightManuallyEdited.value = false
  applyFreightEstimate()
}

function refreshFreightForLoad() {
  for (const leg of ['delivery', 'return']) {
    if (form[`${leg}_transport_required`]) invalidateFreight(leg)
  }
}

function freightInputKey(leg) {
  return JSON.stringify([form[`${leg}_transport_required`], destinationsFor(leg).map(group => [group.address,group.number,group.cep,group.complement,group.items.map(item => [item.equipment_id,item.start_date,item.end_date,item.time])])])
}
function queueFreight(leg) {
  clearTimeout(autoFreightTimers[leg])
  const groups = destinationsFor(leg)
  if (!form[`${leg}_transport_required`] || !groups.length || groups.some(group => !group.address.trim() || !group.number.trim() || !/^\d{8}$/.test(group.cep))) return
  autoFreightTimers[leg] = setTimeout(() => { if (modal.value) calculateFreight(leg) }, 800)
}
watch(() => [freightInputKey('delivery'),freightInputKey('return')], (values,previous) => {
  if (!modal.value || initializingEditor) return
  for (const [index,leg] of ['delivery','return'].entries()) if (values[index] !== previous?.[index] && form[`${leg}_transport_required`]) { invalidateFreight(leg); queueFreight(leg) }
}, {flush:'sync'})

async function searchAddress(leg) {
  const session = editorSession, state = addressLookup[leg]
  invalidateFreight(leg)
  if (!/^\d{8}$/.test(state.cep)) { state.error = 'Informe um CEP com 8 dígitos.'; return }
  const request = ++state.cepRequest, cep = state.cep, previousAddress = form[`${leg}_address`]
  state.cepLoading = true
  try {
    const { data } = await api.get('/rental-quotes/lookup-address/', { params: { cep: state.cep } })
    if (!modal.value || session !== editorSession || request !== state.cepRequest || cep !== state.cep || form[`${leg}_address`] !== previousAddress) return
    form[`${leg}_cep`] = data.cep
    addressSource[leg] = 'custom'
    form[`${leg}_address`] = [data.street, data.neighborhood, `${data.city}/${data.state}`, `CEP ${data.cep.slice(0, 5)}-${data.cep.slice(5)}`].filter(Boolean).join(', ')
  } catch (event) {
    if (session === editorSession && request === state.cepRequest) state.error = apiError(event)
  } finally {
    if (session === editorSession && request === state.cepRequest) state.cepLoading = false
  }
}

async function calculateFreight(leg) {
  clearTimeout(autoFreightTimers[leg])
  const session = editorSession, state = addressLookup[leg]
  invalidateFreight(leg)
  const groups = destinationsFor(leg)
  if (!groups.length) { state.error='Selecione os equipamentos antes de calcular o frete.'; return }
  if (groups.some(group => !/^\d{8}$/.test(group.cep))) { state.error='Informe um CEP com oito dígitos para cada destino.'; return }
  if (groups.some(group => !group.address.trim() || !group.number.trim())) { state.error='Preencha o logradouro e o número de cada destino.'; return }
  const request = ++state.request, key = freightInputKey(leg)
  state.loading = true
  try {
    const estimates = []
    for (const group of groups) {
      const {data} = await api.get('/rental-quotes/lookup-address/', {params:{
        cep:group.cep, address:group.address, number:group.number, leg:leg === 'return' ? 'RETURN' : 'DELIVERY',
        equipment_ids:group.items.map(item => item.equipment_id).join(','),
        periods:JSON.stringify(group.items.map(({equipment_id,start_date,end_date,time}) => ({equipment_id,start_date,end_date,time}))), allow_approximate:true,
      },timeout:25000})
      if (!modal.value || session !== editorSession || request !== state.request || key !== freightInputKey(leg)) return
      if (data.estimate?.fee == null) {state.result=data;state.error=data.estimate?.reason || 'Não foi possível calcular este destino.';return}
      estimates.push({...data.estimate,address:fullAddress(group.address,group.number),items:group.items})
    }
    state.result={estimate:{
      fee:estimates.reduce((sum,item) => sum+Number(item.fee),0).toFixed(2),
      trip_count:estimates.reduce((sum,item) => sum+Number(item.trip_count || 1),0),
      group_count:estimates.length, approximate_destination:estimates.some(item => item.approximate_destination),
      groups:estimates,
    }}
    applyFreightEstimate()
  } catch(event) {if(session===editorSession && request===state.request)state.error=apiError(event)}
  finally {if(session===editorSession && request===state.request)state.loading=false}
}

function useDeliveryAddressForReturn() {
  addressSource.return = 'custom'
  addressLookup.return.cep = addressLookup.delivery.cep
  form.return_cep = form.delivery_cep
  form.return_address = form.delivery_address
  form.return_number = form.delivery_number
  form.return_complement = form.delivery_complement
  // Mesmo endereço não significa mesma rota: a coleta percorre o sentido inverso.
  invalidateFreight('return')
}


async function checkSelectedAvailability() {
  const request = ++selectionRequest
  selectionChecked.value = false; selectionConflicts.value = []
  if (!datesValid.value || !form.items.length || !modal.value) { selectionLoading.value = false; return }
  selectionLoading.value = true
  try {
    let next = 1
    const found = new Set(), conflicts = []
    for (const group of periodGroups(form.items)) {
    next = 1
    while (next) {
      const { data } = await api.get('/rental-quotes/availability/', { params: {
        start: group.start, end: group.end, equipment_ids: group.items.map(item => item.equipment_id).join(','),
        ignore_quote: editing.value?.id, page: next, page_size: 100,
      } })
      if (request !== selectionRequest || !modal.value) return
      for (const item of [...data.available, ...data.blocked]) found.add(item.equipment.id)
      conflicts.push(...data.blocked); next = data.next_page
    }
    }
    for (const item of form.items) if (!found.has(item.equipment_id)) conflicts.push({ equipment: { id: item.equipment_id }, reason: 'Equipamento não encontrado.' })
    selectionConflicts.value = conflicts; selectionChecked.value = true
  } catch (event) { if (request === selectionRequest) error.value = apiError(event) }
  finally { if (request === selectionRequest) selectionLoading.value = false }
}
watch(() => [form.start_date, form.end_date, form.items.map(item => `${item.equipment_id}:${item.start_date}:${item.end_date}`).join(',')], () => { if (modal.value) checkSelectedAvailability() }, { flush: 'sync' })

async function loadAvailability(append = false) {
  const request = ++availabilityRequest
  if (!append) {
    availabilityChecked.value = false
    availableEquipment.value = []
    blockedEquipment.value = []
    availabilityNext.value = null
  }
  if (!pickerDatesValid.value || !showList.value) {
    availabilityLoading.value = false
    return
  }
  availabilityLoading.value = true
  error.value = ''
  try {
    const params = { start: pickerPeriod.start_date, end: pickerPeriod.end_date, page: append ? availabilityNext.value : 1, page_size: 50, search: equipmentSearch.value || undefined, category: !equipmentSearch.value.trim() ? selectedCategory.value?.id || undefined : undefined, ordering: pickerOrdering.value, brand: pickerBrand.value || undefined, min_daily_rate: pickerMinRate.value === '' ? undefined : pickerMinRate.value, max_daily_rate: pickerMaxRate.value === '' ? undefined : pickerMaxRate.value }
    if (editing.value) params.ignore_quote = editing.value.id
    const { data } = await api.get('/rental-quotes/availability/', { params })
    if (request !== availabilityRequest || !modal.value) return
    const newAvailable = data.available.map(item => item.equipment)
    availableEquipment.value = append ? [...availableEquipment.value, ...newAvailable] : newAvailable
    blockedEquipment.value = append ? [...blockedEquipment.value, ...data.blocked] : data.blocked
    availabilityNext.value = data.next_page
    availabilityCount.value = data.count || 0
    availabilityChecked.value = true
  } catch (e) {
    if (request === availabilityRequest && modal.value) error.value = apiError(e)
  } finally {
    if (request === availabilityRequest) availabilityLoading.value = false
  }
}

async function loadCategories() {
  if (!pickerDatesValid.value) { categorySummary.value = []; return }
  const request = ++categoryRequest
  categoryLoading.value = true
  try {
    const params = { start: pickerPeriod.start_date, end: pickerPeriod.end_date }
    if (editing.value) params.ignore_quote = editing.value.id
    const { data } = await api.get('/rental-quotes/availability-categories/', { params })
    if (request === categoryRequest) categorySummary.value = data.results || []
  } catch (e) {
    if (request === categoryRequest && modal.value) error.value = apiError(e)
  } finally {
    if (request === categoryRequest) categoryLoading.value = false
  }
}

function chooseCategory(category) {
  selectedCategory.value = category
  equipmentSearch.value = ''
  loadAvailability(false)
}

function clearCategory() {
  pickerOrdering.value = 'code'; pickerBrand.value = ''; pickerMinRate.value = ''; pickerMaxRate.value = ''
  selectedCategory.value = null
  equipmentSearch.value = ''
  availableEquipment.value = []
  blockedEquipment.value = []
  availabilityChecked.value = false
  loadCategories()
}

async function loadAllCategories() {
  try {
    const { data } = await fetchAll('/categories/')
    allCategories.value = rows(data)
  } catch { allCategories.value = [] }
}

const lostCategoryOptions = computed(() => {
  // Usa o catálogo completo; se ele não carregar, cai para o resumo da disponibilidade.
  const source = allCategories.value.length ? allCategories.value : categorySummary.value
  const byId = new Map(source.map(item => [item.id, item]))
  return source
    .map(item => ({ id: item.id, label: item.parent && byId.get(item.parent) ? `${byId.get(item.parent).name} › ${item.name}` : item.name }))
    .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'))
})

// Diária sugerida para a categoria: a padrão cadastrada ou, sem ela, o ponto médio da faixa dos equipamentos.
function categoryRate(categoryId) {
  if (!categoryId) return null
  const full = allCategories.value.find(item => item.id === categoryId)
  const summary = categorySummary.value.find(item => item.id === categoryId)
  const fallback = summary && summary.min_daily_rate != null ? (Number(summary.min_daily_rate) + Number(summary.max_daily_rate ?? summary.min_daily_rate)) / 2 : null
  const value = Number(full?.default_daily_rate) > 0 ? Number(full.default_daily_rate) : fallback
  return value > 0 ? Math.round(value * 100) / 100 : null
}
const lostEstimate = computed(() => { const v = Number(lostForm.expected_daily_rate) * Number(lostForm.requested_days || 0) * Number(lostForm.quantity || 0); return v > 0 ? v : 0 })
const lostRateHint = computed(() => {
  const rate = categoryRate(lostForm.category)
  if (!rate) return lostForm.category ? 'Esta categoria não tem diária cadastrada: informe o valor esperado.' : 'Categoria nova: informe a diária esperada.'
  const summary = categorySummary.value.find(item => item.id === lostForm.category)
  const range = summary && summary.min_daily_rate != null && Number(summary.min_daily_rate) !== Number(summary.max_daily_rate) ? ` (equipamentos de ${money(summary.min_daily_rate)} a ${money(summary.max_daily_rate)})` : ''
  return lostRateAuto.value ? `Preenchida com a diária da categoria: ${money(rate)}${range}. Você pode alterar.` : `Diária da categoria: ${money(rate)}${range}.`
})
function applyLostRate() {
  if (!lostRateAuto.value) return
  const rate = categoryRate(lostForm.category)
  lostForm.expected_daily_rate = rate != null ? String(rate) : ''
}
watch(() => lostForm.category, applyLostRate)
watch(allCategories, applyLostRate)

function openLostDemand(category = null) {
  lostError.value = ''
  lostRateAuto.value = true
  loadAllCategories()
  Object.assign(lostForm, { category: category?.id || selectedCategory.value?.id || '', new_category_name: '', requested_item: equipmentSearch.value.trim(), quantity: 1, requested_days: days.value, expected_daily_rate: '', reason: 'UNAVAILABLE', notes: '' })
  applyLostRate()
  lostModal.value = true
}

async function saveLostDemand() {
  lostBusy.value = true
  lostError.value = ''
  try {
    const d = new Date()
    const today = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    await api.post('/ai/unfulfilled-demands/', {
      customer: form.customer || null,
      category: lostForm.category || null,
      new_category_name: lostForm.category ? '' : lostForm.new_category_name.trim(),
      requested_item: lostForm.requested_item.trim(),
      quantity: Number(lostForm.quantity || 1),
      requested_days: Math.max(1, Math.round(Number(lostForm.requested_days) || 1)),
      requested_at: today,
      expected_daily_rate: lostForm.expected_daily_rate || null,
      reason: lostForm.reason,
      notes: lostForm.notes,
    })
    lostModal.value = false
    notice.value = 'Pedido não atendido registrado. A IA vai considerá-lo na sugestão de aquisição de equipamentos.'
    loadCategories()
  } catch (e) { lostError.value = apiError(e) }
  finally { lostBusy.value = false }
}

let availabilitySearchTimer
watch([equipmentSearch, pickerOrdering, pickerBrand, pickerMinRate, pickerMaxRate], () => {
  if (!modal.value || !datesValid.value) return
  clearTimeout(availabilitySearchTimer)
  availabilityRequest += 1; availabilityChecked.value = false
  availabilityLoading.value = Boolean(showList.value)
  availabilitySearchTimer = setTimeout(() => {
    if (!showList.value) { availableEquipment.value = []; blockedEquipment.value = []; availabilityChecked.value = false; return }
    loadAvailability(false)
  }, 300)
})

async function applyPackage() {
  const pack = packages.value.find(item => String(item.id) === String(selectedPackageId.value))
  if (!pack) return
  if (!pickerDatesValid.value) { error.value = 'Informe as datas do período antes de adicionar um pacote.'; return }
  const additions = []
  const shortages = []
  try {
    for (const component of pack.components || []) {
      const params = { start: pickerPeriod.start_date, end: pickerPeriod.end_date, category: component.category, page_size: 100 }
      if (editing.value) params.ignore_quote = editing.value.id
      const { data } = await api.get('/rental-quotes/availability/', { params })
      const takenIds = new Set([...form.items.map(line => line.equipment_id), ...additions.map(line => line.equipment_id)])
      const candidates = data.available.map(entry => entry.equipment).filter(asset => !takenIds.has(asset.id))
      if (candidates.length < component.quantity) shortages.push(`${component.category_name}: solicitado ${component.quantity}, disponível ${candidates.length}`)
      candidates.slice(0, component.quantity).forEach(asset => additions.push({ equipment_id: asset.id, name: asset.name, code: asset.internal_code, daily_rate: Number(((Number(component.reference_daily_rate) > 0 ? Number(component.reference_daily_rate) : Number(asset.daily_rate)) * (1 - Number(pack.promotional_discount_percent || 0) / 100)).toFixed(2)), quantity_days: periodDays(pickerPeriod.start_date,pickerPeriod.end_date), start_date: pickerPeriod.start_date, end_date: pickerPeriod.end_date, uses_default_period: pickerPeriod.start_date === form.start_date && pickerPeriod.end_date === form.end_date }))
    }
  } catch (e) { error.value = apiError(e); return }
  if (shortages.length) { error.value = `Não foi possível incluir o pacote: ${shortages.join('; ')}.`; return }
  const unique = new Set(form.items.map(line => line.equipment_id))
  additions.forEach(line => { if (!unique.has(line.equipment_id)) form.items.push(line) })
  selectedPackageId.value = ''
  error.value = ''
  refreshFreightForLoad()
}

function toggle(item) {
  const index = form.items.findIndex(line => line.equipment_id === item.id)
  if (index >= 0) form.items.splice(index, 1)
  else form.items.push({ equipment_id: item.id, name: item.name, code: item.internal_code, daily_rate: item.daily_rate, quantity_days: periodDays(pickerPeriod.start_date,pickerPeriod.end_date), start_date: pickerPeriod.start_date, end_date: pickerPeriod.end_date, uses_default_period: pickerPeriod.start_date === form.start_date && pickerPeriod.end_date === form.end_date })
  refreshFreightForLoad()
}

watch(() => [form.start_date, form.end_date], () => {
  availabilityChecked.value = false
  if (initializingEditor) return
  Object.assign(pickerPeriod, { start_date: form.start_date, end_date: form.end_date })
  form.items.forEach(item => { useDefaultPeriod(item); item.quantity_days = lineDays(item) })
  if (modal.value) { loadCategories(); loadAvailability() }
}, { flush: 'sync' })
watch(() => [pickerPeriod.start_date, pickerPeriod.end_date], () => { if (modal.value && !initializingEditor) { loadCategories(); loadAvailability() } }, { flush: 'sync' })

watch(() => [form.delivery_transport_required, form.return_transport_required], ([delivery, returning]) => {
  if (initializingEditor) return
  freightNeedsCalculation.value = true
  if (!delivery && !returning) {
    form.transport_fee = 0
    form.estimated_transport_fee = 0
    form.transport_fee_adjustment_reason = ''
    freightManuallyEdited.value = false
  } else applyFreightEstimate()
}, { flush: 'sync' })

async function openWhatsApp(quote) {
  const popup = window.open('about:blank', '_blank')
  try {
    const { data } = await api.get(`/rental-quotes/${quote.id}/whatsapp-link/`)
    if (popup) popup.location.href = data.url
    else window.location.href = data.url
  } catch (event) {
    if (popup) popup.close()
    error.value = apiError(event)
  }
}

async function openExtensionWhatsApp(quote) {
  const popup = window.open('about:blank', '_blank')
  try {
    const { data } = await api.get(`/rental-quotes/${quote.id}/whatsapp-extension-link/`)
    if (popup) popup.location.href = data.url
    else window.location.href = data.url
    notice.value = data.detail
  } catch (event) {
    if (popup) popup.close()
    error.value = apiError(event)
  }
}

function stepProblem(index) {
  if (index === 0) return !form.customer ? 'Selecione o cliente.' : !datesValid.value ? 'Informe um período válido.' : ''
  if (index === 1) {
    if (!form.items.length) return 'Selecione pelo menos um equipamento.'
    if (form.items.some(item => !lineDays(item))) return 'Informe um período válido para cada equipamento.'
    if (selectionLoading.value || !selectionChecked.value) return 'Aguarde a conferência dos equipamentos selecionados.'
    if (selectedConflicts.value.length && form.status === 'APPROVED') return 'Resolva a indisponibilidade dos equipamentos antes de aprovar a reserva.'
    if (form.items.some(item => item.daily_rate === '' || !Number.isFinite(Number(item.daily_rate)) || Number(item.daily_rate) < 0)) return 'Informe diárias válidas.'
  }
  if (index === 2) {
    if (addressLookup.delivery.cepLoading || addressLookup.return.cepLoading || destinationLookups.size) return 'Aguarde a consulta do CEP antes de continuar.'
    for (const leg of ['delivery','return']) if (form[`${leg}_transport_required`] && destinationsFor(leg).some(group => !group.address.trim() || !group.number.trim())) return 'Preencha o endereço e o número de cada destino.'
    for (const leg of ['delivery','return']) if (form[`${leg}_transport_required`] && separateDestinations.value && form.items.some(item => Object.keys(item[`${leg}_location`] || {}).length && !/^\d{8}$/.test(item[`${leg}_location`].cep))) return 'Informe o CEP de cada destino específico.'
    if (scheduleDelivery.value && usesCommon('delivery') && !form.requested_delivery_at) return form.delivery_transport_required ? 'Informe o horário de entrega combinado.' : 'Informe o horário de retirada na loja.'
    if (scheduleReturn.value && usesCommon('return') && !form.requested_return_at) return form.return_transport_required ? 'Informe o horário de coleta combinado.' : 'Informe o horário de devolução na loja.'
    if (scheduleDelivery.value && scheduleReturn.value && form.items.some(item => !separateDestinations.value || !Object.keys(item.delivery_location || {}).length && !Object.keys(item.return_location || {}).length) && form.requested_return_at < form.requested_delivery_at) return 'A devolução não pode ocorrer antes da entrega.'
    if (form.items.some(item => item.start_date === item.end_date && effectiveLocation(item,destinationDefaults.value,'delivery',separateDestinations.value).time && effectiveLocation(item,destinationDefaults.value,'return',separateDestinations.value).time && effectiveLocation(item,destinationDefaults.value,'return',separateDestinations.value).time < effectiveLocation(item,destinationDefaults.value,'delivery',separateDestinations.value).time)) return 'Para itens de um dia, o horário de devolução deve ser posterior ao de retirada.'
    if ((form.delivery_cep && !/^\d{8}$/.test(form.delivery_cep)) || (form.return_cep && !/^\d{8}$/.test(form.return_cep))) return 'Informe CEPs com oito dígitos.'
  }
  if (index === 3) {
    if (discountPercent.value === '' || !Number.isFinite(Number(discountPercent.value)) || Number(discountPercent.value) < 0 || Number(discountPercent.value) > 100) return 'Informe um desconto entre 0% e 100%.'
    if (!Number.isFinite(Number(form.transport_fee)) || Number(form.transport_fee) < 0) return 'Informe um valor de transporte válido.'
    if ((form.delivery_transport_required || form.return_transport_required) && freightNeedsCalculation.value && !freightManuallyEdited.value) return 'Calcule o frete dos trechos selecionados ou informe um valor manual.'
    if ((Number(form.transport_fee) !== Number(form.estimated_transport_fee) || freightNeedsCalculation.value && freightManuallyEdited.value) && !form.transport_fee_adjustment_reason.trim()) return 'Justifique o ajuste do frete.'
  }
  return ''
}
async function nextStep() {
  if (quoteStep.value === 1) await checkSelectedAvailability()
  error.value = stepProblem(quoteStep.value)
  if (error.value) return
  furthestStep.value = Math.max(furthestStep.value, quoteStep.value + 1)
  quoteStep.value += 1
}
function goToStep(index) { if (index <= furthestStep.value) { quoteStep.value = index; error.value = '' } }
function submitWizard() { if (quoteStep.value < 4) nextStep(); else save() }
async function save() {
  for (let index = 0; index < 4; index++) {
    const problem = stepProblem(index)
    if (problem) { quoteStep.value = index; error.value = problem; return }
  }
  if (form.status === 'APPROVED' && !form.conditions.trim()) { quoteStep.value = 3; error.value = 'Registre as condições antes de reservar.'; return }
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const payload = { ...form, ...envelope.value,
      requested_delivery_at: scheduleDelivery.value ? toDateTimePayload(form.requested_delivery_at) : null,
      requested_return_at: scheduleReturn.value ? toDateTimePayload(form.requested_return_at) : null,
      discount_percent: Number(discountPercent.value), discount: discountAmount.value,
      items: form.items.map(({ equipment_id, daily_rate, start_date, end_date, delivery_location, return_location }) => ({ equipment_id, daily_rate, start_date, end_date, delivery_location: separateDestinations.value ? delivery_location || {} : {}, return_location: separateDestinations.value ? return_location || {} : {} })),
    }
    editing.value ? await api.patch(`/rental-quotes/${editing.value.id}/`, payload) : await api.post('/rental-quotes/', payload)
    modal.value = false; editing.value = null
    await load()
  } catch (event) { error.value = event.message && !event.response ? event.message : apiError(event) }
  finally { busy.value = false }
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
function handleRentalAction(action, quote) {
  const handlers = {
    flow: () => { flowQuote.value = quote }, edit: () => open(quote), reserve: () => reserve(quote),
    deliver: () => openOperation('deliver', quote), extend: () => openOperation('extend', quote),
    return: () => openOperation('return', quote), finalize: () => finalizeReturn(quote),
    cancel: () => openOperation('cancel', quote), delete: () => { deleting.value = quote },
    whatsapp: () => openWhatsApp(quote), whatsappExtension: () => openExtensionWhatsApp(quote),
    preInspection: () => router.push({ name: 'maintenance', query: { quote: quote.number } }),
    postInspection: () => router.push({ name: 'maintenance', query: { quote: quote.number } }),
    deliveryTransport: () => router.push({ name: 'logistics', query: { quote: quote.number } }),
    returnTransport: () => router.push({ name: 'logistics', query: { quote: quote.number } }),
  }
  handlers[action]?.()
}
function showLinkedQuote() {
  if (!route.query.quote) return
  const matched = quotes.value.find(quote => quote.number === String(route.query.quote))
  if (matched) {
    statusFilter.value = 'ALL'
    quoteSearch.value = matched.number
    flowQuote.value = matched
  }
}
watch(() => route.query.quote, showLinkedQuote)
onMounted(async () => {
  const requestedStatus = String(route.query.status || '')
  if (['PROPOSAL', 'APPROVED', 'ACTIVE', 'RETURNED', 'COMPLETED', 'CLOSED'].includes(requestedStatus)) statusFilter.value = requestedStatus
  if (route.query.quote) quoteSearch.value = String(route.query.quote)
  await load()
  showLinkedQuote()
})

const { page: quotePage, items: quoteRows } = usePagination(filteredQuotes, [statusFilter, quoteSearch, quoteCustomer, quoteTransport, quoteFrom, quoteTo, quoteOrdering])
onBeforeUnmount(() => { for (const leg of ['delivery','return']) clearTimeout(autoFreightTimers[leg]); clearTimeout(availabilitySearchTimer); editorSession += 1; availabilityRequest += 1; categoryRequest += 1; selectionRequest += 1 })
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">COMERCIAL</span><h1>Locações e orçamentos</h1><p>Disponibilidade antecipada, composição de preço e acompanhamento do funil.</p></div><button v-if="can('rentals.manage')" class="btn primary" @click="open()"><Plus :size="18" />Gerar orçamento</button></header>
    <SuccessNotice v-if="notice" :message="notice" :action="maintenanceShortcut && can('maintenance.view') ? {label:'Ver na Manutenção',to:{name:'maintenance',query:{quote:maintenanceShortcut}}} : transportShortcut && can('logistics.view') ? {label:'Ver em Transporte',to:{name:'logistics',query:{quote:transportShortcut}}} : undefined" @close="notice = ''" />
    <GeneralError v-if="error && !modal && !operation" :message="error" @close="error = ''" />

    <div class="workflow-tabs quote-tabs" role="tablist" aria-label="Filtrar orçamentos por status"><button v-for="item in statusTabs" :key="item.key" :class="{ active: statusFilter === item.key }" @click="statusFilter = item.key"><span>{{ item.label }}</span><b>{{ item.count }}</b></button></div>

    <section class="panel list-panel">
      <header class="list-toolbar list-controls"><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="quoteSearch" type="search" placeholder="Número, cliente ou equipamento" aria-label="Pesquisar locações" /></span></label><label class="list-control"><span>Cliente</span><AppSelect searchable v-model="quoteCustomer"><option value="">Todos</option><option v-for="[id, name] in quoteCustomerOptions" :key="id" :value="id">{{ name }}</option></AppSelect></label><label class="list-control"><span>Transporte</span><AppSelect v-model="quoteTransport"><option value="">Todos</option><option value="any">Com transporte</option><option value="delivery">Com entrega</option><option value="return">Com coleta</option><option value="none">Retirada e devolução na loja</option></AppSelect></label><label class="list-control"><span>Período a partir de</span><AppDateTime v-model="quoteFrom" type="date" /></label><label class="list-control"><span>Período até</span><AppDateTime v-model="quoteTo" type="date" :min="quoteFrom" /></label><ListOrdering v-model="quoteOrdering" :options="quoteSortOptions" /><div class="filter-meta"><span class="result-count">{{ filteredQuotes.length }} orçamento(s)</span><button type="button" class="btn secondary" @click="clearQuoteFilters">Limpar filtros</button></div></header>
      <div class="table-wrap desktop-list"><table><thead><tr><th>Orçamento</th><th>Cliente</th><th>Período</th><th>Itens</th><th>Status</th><th class="right">Total</th><th class="right">Ações</th></tr></thead><tbody>
        <template v-for="quote in quoteRows" :key="quote.id"><tr>
          <td><strong>{{ quote.number }}</strong><small>{{ shortDate(quote.created_at?.slice(0, 10)) }} · {{ quote.created_by_name }}</small></td>
          <td>{{ quote.customer_name }}</td><td>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</td><td><RentalEquipmentSummary :quote="quote" @open="equipmentQuote = $event" /></td>
          <td><StatusBadge :value="quote.status" :label="quote.status_label" /><small v-if="quote.status === 'APPROVED'">Manutenção · pré-inspeção {{ inspectionProgress(quote, 'PRE_RENTAL').done }}/{{ inspectionProgress(quote, 'PRE_RENTAL').total }}</small><small v-if="quote.status === 'RETURNED'">Manutenção · inspeção final {{ inspectionProgress(quote, 'RETURN').done }}/{{ inspectionProgress(quote, 'RETURN').total }}</small><small v-if="quote.delivery_transport_required || quote.return_transport_required">Transporte {{ quote.delivery_transport_required && quote.return_transport_required ? 'ida e volta' : quote.delivery_transport_required ? 'de entrega' : 'de coleta' }}</small></td>
          <td class="right"><strong>{{ money(quote.total) }}</strong></td><td class="rental-action-cell"><button type="button" class="icon-btn rental-actions-toggle" :class="{ active: expandedActions === quote.id }" :aria-expanded="expandedActions === quote.id" :aria-label="expandedActions === quote.id ? 'Ocultar ações' : 'Mostrar ações'" :title="expandedActions === quote.id ? 'Ocultar ações' : 'Mostrar ações'" @click="expandedActions = expandedActions === quote.id ? null : quote.id"><component :is="expandedActions === quote.id ? EyeOff : Eye" :size="19" /></button></td>
        </tr><tr v-if="expandedActions === quote.id" class="rental-actions-row"><td colspan="7"><RentalActions :quote="quote" :busy="busy" @action="handleRentalAction($event, quote)" /></td></tr></template><tr v-if="!filteredQuotes.length"><td colspan="7" class="empty-cell">Nenhuma locação nesta etapa.</td></tr>
      </tbody></table></div>
      <div class="mobile-card-list"><article v-for="quote in quoteRows" :key="quote.id" class="mobile-record-card rental-mobile-card"><header><div><span class="eyebrow">{{ quote.number }}</span><strong>{{ quote.customer_name }}</strong></div><StatusBadge :value="quote.status" :label="quote.status_label" /></header><RentalEquipmentSummary :quote="quote" @open="equipmentQuote = $event" /><dl><div><dt>Período</dt><dd>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</dd></div><div><dt>Total</dt><dd><strong>{{ money(quote.total) }}</strong></dd></div></dl><footer><button type="button" class="icon-btn rental-actions-toggle" :class="{ active: expandedActions === quote.id }" :aria-expanded="expandedActions === quote.id" :aria-label="expandedActions === quote.id ? 'Ocultar ações' : 'Mostrar ações'" :title="expandedActions === quote.id ? 'Ocultar ações' : 'Mostrar ações'" @click="expandedActions = expandedActions === quote.id ? null : quote.id"><component :is="expandedActions === quote.id ? EyeOff : Eye" :size="19" /></button><RentalActions v-if="expandedActions === quote.id" :quote="quote" :busy="busy" @action="handleRentalAction($event, quote)" /></footer></article></div>
      <PaginationBar v-model="quotePage" :total="(filteredQuotes).length" />
    </section>

    <ModalDialog v-if="modal" :title="editing ? `Editar ${editing.number}` : 'Novo orçamento de locação'" wide @close="modal = false; error = ''">
      <form class="quote-editor" novalidate @submit.prevent="submitWizard">
        <nav class="quote-wizard-nav" aria-label="Etapas do orçamento"><button v-for="(label, index) in quoteSteps" :key="label" type="button" :disabled="index > furthestStep" :aria-current="quoteStep === index ? 'step' : undefined" :class="{ active: quoteStep === index, completed: index < furthestStep }" @click="goToStep(index)"><b>{{ index + 1 }}</b><span>{{ label }}</span></button></nav>
<div v-show="quoteStep === 0">        <p class="quote-editor-lead">Escolha o cliente e o período. Os equipamentos disponíveis e o valor aparecem aqui mesmo.</p>
        <div class="form-grid quote-editor-basics"><div class="form-field span-2"><label for="quote-customer">Cliente<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable id="quote-customer" v-model="form.customer" :disabled="customersLoading" required><option value="" disabled>Selecione o cliente</option><option v-for="customer in customers" :key="customer.id" :value="customer.id">{{ customer.name }} · {{ formatTaxId(customer.document, customer.person_type) }}</option></AppSelect><small v-if="selectedCustomer?.notes" class="customer-internal-note">Observações internas: {{ selectedCustomer.notes }}</small><small v-if="customersLoading" role="status">Carregando clientes...</small><small v-else-if="!customers.length">Cadastre um cliente antes de criar o orçamento.</small></div><div class="form-field"><label for="quote-start">Retirada<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime id="quote-start" v-model="form.start_date" type="date" required /></div><div class="form-field"><label for="quote-end">Devolução prevista<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime id="quote-end" v-model="form.end_date" type="date" :min="form.start_date" required /></div></div>
        <div class="quote-period-hint"><CalendarRange :size="17" /><span v-if="datesValid">{{ days }} diária(s) · {{ shortDate(form.start_date) }} a {{ shortDate(form.end_date) }}</span><span v-else>Informe uma devolução igual ou posterior à retirada.</span></div>

</div><div v-show="quoteStep === 1" class="quote-equipment-step">        <section class="quote-editor-section"><header><div><h3>Equipamentos</h3><p>Escolha a categoria e depois os itens disponíveis nesse período.</p></div><div class="search-box"><Search :size="16" /><input v-model="equipmentSearch" placeholder="Buscar em todas as categorias" aria-label="Buscar equipamento" :disabled="!datesValid" /></div></header><div class="form-grid quote-picker-period"><div class="form-field"><label>Retirada para a busca<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime v-model="pickerPeriod.start_date" type="date" required /></div><div class="form-field"><label>Devolução para a busca<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime v-model="pickerPeriod.end_date" type="date" :min="pickerPeriod.start_date" required /></div><small class="span-2">Os novos itens usam este período. Você pode ajustar as datas de cada equipamento abaixo.</small></div><div class="list-controls quote-picker-filters"><label class="list-control"><span>Marca</span><input v-model="pickerBrand" type="search" placeholder="Todas as marcas" aria-label="Filtrar marca dos equipamentos" :disabled="!datesValid" /></label><label class="list-control"><span>Diária mínima (R$)</span><AppInput mask="money" placeholder="Ex.: 50,00" v-model="pickerMinRate" min="0" step="0.01" :disabled="!datesValid" /></label><label class="list-control"><span>Diária máxima (R$)</span><AppInput mask="money" placeholder="Ex.: 300,00" v-model="pickerMaxRate" min="0" step="0.01" :disabled="!datesValid" /></label><ListOrdering v-model="pickerOrdering" :options="pickerSortOptions" /><div v-if="pickerBrand || pickerMinRate !== '' || pickerMaxRate !== '' || pickerOrdering !== 'code'" class="filter-meta"><button type="button" class="btn secondary" @click="clearPickerFilters">Limpar filtros</button></div></div>
          <div v-if="packages.length" class="package-quick-add"><AppSelect searchable v-model="selectedPackageId"><option value="">Adicionar pacote pronto...</option><option v-for="pack in packages" :key="pack.id" :value="String(pack.id)">{{ pack.name }}</option></AppSelect><button type="button" class="btn secondary" :disabled="!selectedPackageId || !datesValid" @click="applyPackage">Adicionar pacote</button></div>
          <div v-if="!datesValid" class="quote-picker-placeholder">Informe as datas para consultar os equipamentos.</div>
          <div v-else-if="showList && availabilityLoading" class="quote-picker-placeholder"><Clock3 :size="18" />Consultando disponibilidade...</div>
          <div v-else-if="!showList && categoryLoading && !categorySummary.length" class="quote-picker-placeholder"><Clock3 :size="18" />Carregando categorias...</div>
          <template v-else-if="showList && availabilityChecked"><div v-if="selectedCategory && !equipmentSearch.trim()" class="category-breadcrumb"><button type="button" class="btn secondary" @click="clearCategory">← Categorias</button><strong>{{ selectedCategory.name }}</strong></div><div class="quote-stock-count"><CheckCircle2 :size="16" />{{ availableEquipment.length }} disponível(is) no período</div><div v-if="visibleAvailable.length" class="quote-picker-layout"><div class="equipment-picker quote-editor-picker"><button v-for="item in visibleAvailable" :key="item.id" type="button" :aria-pressed="form.items.some(line => line.equipment_id === item.id)" :class="{ selected: form.items.some(line => line.equipment_id === item.id) }" @click="toggle(item)"><span class="select-check"><Check :size="15" /></span><img v-if="item.photo_url" class="quote-equipment-photo" :src="item.photo_url" :alt="item.name" loading="lazy"/><span v-else class="quote-equipment-placeholder"><PackageCheck :size="19"/></span><div><strong>{{ item.name }}</strong><small>{{ item.internal_code }} · {{ item.category_name }}</small></div><b>{{ money(item.daily_rate) }}<small>/dia</small></b></button></div></div><p v-else class="quote-picker-placeholder">Nenhum equipamento encontrado. Tente outra busca ou período.</p><div v-if="availabilityNext" class="availability-load-more"><small>Exibindo {{ availableEquipment.length + blockedEquipment.length }} de {{ availabilityCount }} equipamentos.</small><button type="button" class="btn secondary" :disabled="availabilityLoading" @click="loadAvailability(true)">{{ availabilityLoading ? 'Carregando...' : 'Carregar mais equipamentos' }}</button></div><details v-if="visibleBlocked.length" class="blocked-equipment"><summary><AlertCircle :size="17" />{{ visibleBlocked.length }} indisponível(is) neste período</summary><article v-for="item in visibleBlocked" :key="item.equipment.id"><div><strong>{{ item.equipment.internal_code }} · {{ item.equipment.name }}</strong><span>{{ item.reason }}</span></div></article></details><button v-if="can('rentals.manage')" type="button" class="lost-demand-link" @click="openLostDemand()">O cliente quer algo que não temos ou que está indisponível? Registrar pedido</button></template>
          <template v-else><p class="quote-picker-placeholder" style="margin:8px 0 0">Escolha uma categoria para ver os equipamentos disponíveis, ou digite na busca para procurar em todas.</p><div class="category-grid"><button v-for="category in categorySummary" :key="category.id" type="button" class="category-card" :disabled="!category.available" @click="chooseCategory(category)"><strong>{{ category.name }}</strong><span class="badge-count" :class="{ none: !category.available }">{{ category.available }} de {{ category.total }} disponível(is)</span><small v-if="category.min_daily_rate !== null">{{ Number(category.min_daily_rate) === Number(category.max_daily_rate) ? money(category.min_daily_rate) : `${money(category.min_daily_rate)} a ${money(category.max_daily_rate)}` }} /dia</small></button></div><button v-if="can('rentals.manage')" type="button" class="lost-demand-link" @click="openLostDemand()">O cliente pediu algo que não aparece aqui? Registrar pedido não atendido</button></template>
        </section>

        <section class="quote-editor-section"><header><div><h3>Itens do orçamento</h3><p v-if="!form.items.length">Selecione um equipamento acima para começar.</p><p v-else>{{ form.items.length }} equipamento(s) · ajuste a diária se necessário.</p></div></header><div class="quote-lines"><div v-for="item in form.items" :key="item.equipment_id" class="quote-line quote-line-period"><div><strong>{{ item.name }}</strong><span>{{ item.code }} · {{ lineDays(item) }} diária(s)</span></div><label class="rate-editor"><span>Diária (R$)<span class="required-mark" aria-hidden="true"> *</span></span><AppInput mask="money" placeholder="Ex.: 150,00" v-model="item.daily_rate" min="0" step="0.01" required /></label><strong>{{ money(Number(item.daily_rate) * lineDays(item)) }}</strong><button type="button" class="icon-btn" :aria-label="`Remover ${item.name}`" @click="toggle({ id: item.equipment_id })"><Trash2 :size="17" /></button><div class="quote-item-period"><label class="check-line"><input v-model="item.uses_default_period" type="checkbox" @change="useDefaultPeriod(item)" />Usar período inicial</label><label><span class="field-caption">Retirada<span class="required-mark" aria-hidden="true"> *</span></span><AppDateTime v-model="item.start_date" type="date" required @update:model-value="item.uses_default_period = false" /></label><label><span class="field-caption">Devolução<span class="required-mark" aria-hidden="true"> *</span></span><AppDateTime v-model="item.end_date" type="date" :min="item.start_date" required @update:model-value="item.uses_default_period = false" /></label></div></div></div><div class="quote-selection-total"><span>{{ form.items.length }} equipamento(s) · períodos individuais</span><strong>Subtotal {{ money(subtotal) }}</strong></div><div v-if="selectedConflicts.length" class="quote-conflict"><AlertCircle :size="17" /><div><strong>{{ selectedConflicts.length }} equipamento(s) com pendência de disponibilidade</strong><ul><li v-for="conflict in selectionConflicts.filter(conflict => form.items.some(item => item.equipment_id === conflict.equipment.id))" :key="conflict.equipment.id">{{ conflict.equipment.name || conflict.equipment.internal_code }}: {{ conflict.reason }}</li></ul><p>Você pode salvar o orçamento como rascunho ou enviado e continuar incluindo equipamentos disponíveis. Resolva as pendências antes de aprovar a reserva.</p></div></div></section>

</div><div v-show="quoteStep === 2">        <section class="quote-editor-section"><header><div><h3>Transporte</h3><p>Selecione os serviços combinados com o cliente.</p></div></header><div class="form-grid"><div class="form-field span-2"><label>Transporte</label><div class="transport-choices"><label><input v-model="form.delivery_transport_required" type="checkbox" /> Entrega com veículo</label><label><input v-model="form.return_transport_required" type="checkbox" /> Coleta na devolução</label></div><small>Se não marcar, a retirada e a devolução são no balcão.</small></div>
          <template v-for="leg in ['delivery', 'return']" :key="leg">
            <div v-if="form[`${leg}_transport_required`]" class="address-search-group span-2">
              <div class="address-group-heading"><strong>{{ leg === 'delivery' ? 'Entrega' : 'Coleta na devolução' }}</strong><button v-if="leg === 'return' && form.delivery_transport_required && form.delivery_address" type="button" @click="useDeliveryAddressForReturn">Usar endereço da entrega</button></div>
              <div class="customer-address-choice"><p v-if="addressSource[leg] === 'customer' && selectedCustomer?.address"><strong>Endereço do cadastro</strong>{{ form[`${leg}_address`] }}<span v-if="!form[`${leg}_cep`]">Complete o CEP abaixo para calcular a rota.</span></p><button v-if="addressSource[leg] === 'customer' && selectedCustomer?.address" type="button" class="btn secondary" @click="addressSource[leg] = 'custom'">Alterar endereço nesta locação</button><button v-else-if="selectedCustomer?.address" type="button" class="btn secondary" @click="useCustomerAddress(leg)">Usar endereço do cliente</button></div>
              <div class="form-field"><label :for="`quote-${leg}-cep`">{{ leg === 'delivery' ? 'CEP da entrega' : 'CEP da coleta' }}</label><div class="address-lookup-row"><AppInput mask="cep" :id="`quote-${leg}-cep`" v-model="addressLookup[leg].cep" inputmode="numeric" placeholder="00000-000" @input="onCepInput(leg)" /><button type="button" class="btn secondary" :disabled="addressLookup[leg].cepLoading" @click="searchAddress(leg)">Buscar CEP</button></div><small>O CEP preenche o logradouro. Informe o número no campo ao lado.</small></div>
              <div class="form-field"><label :for="`quote-${leg}-number`">Número<span v-if="usesCommon(leg)" class="required-mark" aria-hidden="true"> *</span></label><input :id="`quote-${leg}-number`" v-model="form[`${leg}_number`]" maxlength="20" :required="usesCommon(leg)" placeholder="Ex.: 120 ou S/N" /></div><div class="form-field"><label :for="`quote-${leg}-address`">{{ leg === 'delivery' ? 'Logradouro da entrega' : 'Logradouro da coleta' }}<span v-if="usesCommon(leg)" class="required-mark" aria-hidden="true"> *</span></label><input :id="`quote-${leg}-address`" v-model="form[`${leg}_address`]" :required="usesCommon(leg)" maxlength="230" placeholder="Logradouro, bairro e cidade/UF" :readonly="addressSource[leg] === 'customer' && Boolean(selectedCustomer?.address)" @input="invalidateFreight(leg)" /></div>
              <div class="form-field"><label :for="`quote-${leg}-complement`">Complemento (opcional)</label><input :id="`quote-${leg}-complement`" v-model="form[`${leg}_complement`]" maxlength="120" placeholder="Bloco, apartamento, portão ou ponto de referência" /></div>
              <button type="button" class="btn secondary freight-calculate" :data-leg="leg" :disabled="addressLookup[leg].loading" @click="calculateFreight(leg)">{{ addressLookup[leg].loading ? 'Consultando...' : 'Calcular frete' }}</button>
              <p v-if="addressLookup[leg].error" class="address-lookup-error" role="alert">{{ addressLookup[leg].error }}</p>
              <div v-if="addressLookup[leg].result?.estimate?.fee != null" class="freight-leg-note" role="status"><p><strong>{{ money(addressLookup[leg].result.estimate.fee) }}</strong> · {{ addressLookup[leg].result.estimate.trip_count }} viagem(ns)</p><ul v-if="addressLookup[leg].result.estimate.groups?.length > 1"><li v-for="(group,index) in addressLookup[leg].result.estimate.groups" :key="index">{{ group.address }} · {{ money(group.fee) }}</li></ul></div>
            </div>
          </template>


        </div></section><section class="quote-editor-section"><header><div><h3>Horários combinados</h3><p>Ative apenas os horários definidos com o cliente. As datas seguem o período de cada equipamento; o horário vale para as movimentações de cada dia.</p></div></header><div class="form-grid"><div class="schedule-choice"><label class="check-line"><input v-model="scheduleDelivery" type="checkbox" />{{ form.delivery_transport_required ? 'Definir horário de entrega' : 'Definir horário de retirada na loja' }}</label><div v-show="scheduleDelivery" class="form-field"><label for="quote-delivery-datetime">{{ form.delivery_transport_required ? 'Horário de entrega' : 'Horário de retirada na loja' }}<span class="required-mark" aria-hidden="true" v-if="scheduleDelivery && usesCommon('delivery')"> *</span></label><AppDateTime id="quote-delivery-datetime" v-model="deliveryClock" type="time" :required="scheduleDelivery && usesCommon('delivery')" /></div></div><div class="schedule-choice"><label class="check-line"><input v-model="scheduleReturn" type="checkbox" />{{ form.return_transport_required ? 'Definir horário de coleta' : 'Definir horário de devolução na loja' }}</label><div v-show="scheduleReturn" class="form-field"><label for="quote-return-datetime">{{ form.return_transport_required ? 'Horário de coleta' : 'Horário de devolução na loja' }}<span class="required-mark" aria-hidden="true" v-if="scheduleReturn && usesCommon('return')"> *</span></label><AppDateTime id="quote-return-datetime" v-model="returnClock" type="time" :required="scheduleReturn && usesCommon('return')"  /></div></div><div class="form-field span-2"><label>Observações dos horários</label><input placeholder="Ex.: avisar na portaria ao chegar" v-model="form.requested_delivery_notes" maxlength="1000" /></div></div></section><section v-if="customDestinationsAllowed" class="quote-editor-section quote-item-destinations"><header><div><h3>Condições por equipamento</h3><p>Use esta opção para combinar endereços ou horários diferentes.</p></div></header><label class="check-line"><input v-model="separateDestinations" type="checkbox" />Definir entrega e devolução por equipamento</label><div v-if="separateDestinations" class="item-destination-list"><article v-for="item in form.items" :key="item.equipment_id" class="item-destination-card"><header><strong>{{ item.name }}</strong><small>{{ item.code }} · {{ shortDate(item.start_date) }} a {{ shortDate(item.end_date) }}</small></header><section v-for="leg in ['delivery','return']" :key="leg"><h4>{{ leg === 'delivery' ? (form.delivery_transport_required ? 'Entrega' : 'Retirada na loja') : (form.return_transport_required ? 'Coleta' : 'Devolução na loja') }}</h4><label class="check-line"><input type="checkbox" :checked="Boolean(Object.keys(item[`${leg}_location`] || {}).length)" @change="changeItemDestination(item,leg,$event.target.checked)" />Usar condições específicas</label><ItemDestinationEditor v-if="Object.keys(item[`${leg}_location`] || {}).length" v-model="item[`${leg}_location`]" @lookup-state="setDestinationLookup(item.equipment_id,leg,$event)" :transport="form[`${leg}_transport_required`]" :label="leg === 'delivery' ? 'Entrega' : 'Coleta'"/><small v-else class="muted-text">{{ fullAddress(effectiveLocation(item,destinationDefaults,leg,false).address,effectiveLocation(item,destinationDefaults,leg,false).number) || 'Endereço padrão' }} · {{ effectiveLocation(item,destinationDefaults,leg,false).time || 'Horário a combinar' }}</small></section></article></div></section></div><div v-show="quoteStep === 3"><section class="quote-editor-section"><header><div><h3>Condições comerciais</h3></div></header><div class="form-grid">          <div class="form-field span-2"><label for="quote-conditions">Condições comerciais<span class="required-mark" aria-hidden="true" v-if="form.status === 'APPROVED'"> *</span></label><textarea id="quote-conditions" placeholder="Ex.: pagamento na devolução, utilização e cuidados combinados." v-model="form.conditions" :required="form.status === 'APPROVED'" rows="2" /></div><div class="form-field span-2"><label for="quote-notes">Observações internas</label><textarea id="quote-notes" v-model="form.notes" rows="2" placeholder="Não aparecem nas condições enviadas ao cliente." /></div></div></section>        <div class="quote-editor-footer"><div class="quote-editor-values"><span>Equipamentos <strong>{{ money(subtotal) }}</strong></span><label v-if="form.delivery_transport_required || form.return_transport_required">Transporte (R$)<AppInput mask="money" v-model="form.transport_fee" placeholder="Ex.: 25,00" min="0" step="0.01" @input="freightManuallyEdited = true" /></label><label v-if="freightManuallyEdited && (Number(form.transport_fee) !== Number(form.estimated_transport_fee) || freightNeedsCalculation)">Justificativa do ajuste<span class="required-mark" aria-hidden="true"> *</span><input v-model="form.transport_fee_adjustment_reason" type="text" maxlength="1000" placeholder="Informe o motivo do ajuste manual" required /></label><label>Desconto (%)<AppInput mask="percent" v-model="discountPercent" placeholder="Ex.: 5,00" min="0" max="100" step="0.01" /></label><div v-if="freightManuallyEdited && freightEstimatesReady" class="freight-calculated-action"><small>Frete calculado: {{ money(form.estimated_transport_fee) }}</small><button type="button" class="btn secondary" @click="useCalculatedFreight">Usar valor calculado</button></div><span class="discount-breakdown">{{ money(discountAmount) }} de desconto sobre equipamentos + transporte</span><div>Total estimado <strong>{{ money(total) }}</strong></div></div></div></div><section v-show="quoteStep === 4" class="quote-review"><h3>Revise antes de concluir</h3><dl><div><dt>Cliente</dt><dd>{{ customers.find(item => String(item.id) === String(form.customer))?.name }}</dd></div><div><dt>Período</dt><dd>{{ shortDate(envelope.start_date) }} a {{ shortDate(envelope.end_date) }} · datas por equipamento</dd></div><div><dt>{{ form.delivery_transport_required ? 'Entrega' : 'Retirada na loja' }}</dt><dd>{{ scheduleDelivery ? form.requested_delivery_at.replace('T', ' às ') : 'Horário a combinar' }}</dd></div><div><dt>{{ form.return_transport_required ? 'Coleta' : 'Devolução na loja' }}</dt><dd>{{ scheduleReturn ? form.requested_return_at.replace('T', ' às ') : 'Horário a combinar' }}</dd></div><div><dt>Transporte</dt><dd>{{ form.delivery_transport_required ? `Entrega: ${form.delivery_address}` : 'Retirada pelo cliente' }}<br />{{ form.return_transport_required ? `Coleta: ${form.return_address}` : 'Devolução pelo cliente' }}</dd></div></dl><ul><li v-for="item in form.items" :key="item.equipment_id"><strong>{{ item.name }}<small v-for="leg in ['delivery','return']" :key="leg" class="quote-destination-review">{{ leg === 'delivery' ? 'Entrega / retirada' : 'Coleta / devolução' }}: {{ form[`${leg}_transport_required`] ? fullAddress(effectiveLocation(item,destinationDefaults,leg,separateDestinations).address,effectiveLocation(item,destinationDefaults,leg,separateDestinations).number) : 'Na loja' }} · {{ effectiveLocation(item,destinationDefaults,leg,separateDestinations).time || 'Horário a combinar' }}</small></strong><span>{{ shortDate(item.start_date) }} a {{ shortDate(item.end_date) }} · {{ lineDays(item) }} × {{ money(item.daily_rate) }} = {{ money(Number(item.daily_rate) * lineDays(item)) }}</span></li></ul><p v-if="form.transport_fee_adjustment_reason" class="muted-text">Frete: {{ form.transport_fee_adjustment_reason }}</p><div class="quote-review-total"><span>Equipamentos {{ money(subtotal) }} + frete {{ money(form.transport_fee) }} − desconto {{ money(discountAmount) }}</span><strong>{{ money(total) }}</strong></div><div class="form-field quote-editor-status"><label for="quote-status">Etapa<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required id="quote-status" v-model="form.status"><option value="DRAFT">Rascunho</option><option value="SENT">Enviado ao cliente</option><option v-if="can('rentals.approve')" value="APPROVED">Aprovado / reservar</option></AppSelect><small>Rascunho e enviado não reservam estoque. Aprovado confirma a reserva após as validações.</small></div></section>
        <div v-if="error" class="error-message" role="alert">{{ error }}</div><div class="modal-actions"><button v-if="quoteStep > 0" type="button" class="btn secondary" @click="goToStep(quoteStep - 1)">Voltar</button><span v-if="quoteStep === 1" class="quote-step-total" aria-live="polite">{{ form.items.length }} equipamento(s) · {{ money(subtotal) }}</span><span class="spacer" /><button v-if="quoteStep < 4" type="button" class="btn primary" :disabled="busy" @click="nextStep">Continuar</button><button v-else class="btn primary" :disabled="busy || selectionLoading">{{ busy ? 'Salvando...' : editing ? 'Salvar alterações' : 'Concluir orçamento' }}</button></div>
      </form>
    </ModalDialog>
    <ModalDialog v-if="equipmentQuote" :title="`Equipamentos · ${equipmentQuote.number}`" wide @close="equipmentQuote = null">
      <div class="rental-equipment-context"><strong>{{ equipmentQuote.customer_name }}</strong><span>{{ shortDate(equipmentQuote.start_date) }} a {{ shortDate(equipmentQuote.end_date) }} · {{ equipmentQuote.items.length }} equipamento(s)</span></div>
      <div class="table-wrap rental-equipment-detail"><table><thead><tr><th>Código</th><th>Equipamento</th><th>Período / etapa</th><th class="right">Diária</th></tr></thead><tbody><tr v-for="item in equipmentRows" :key="item.id || item.equipment"><td>{{ item.internal_code }}</td><td><strong>{{ item.equipment_name }}</strong></td><td>{{ shortDate(item.start_date || equipmentQuote.start_date) }} a {{ shortDate(item.end_date || equipmentQuote.end_date) }}<small class="equipment-stage">{{ item.quantity_days }} diária(s) · {{ item.stage_label || itemStage(equipmentQuote, item) }}</small></td><td class="right">{{ money(item.daily_rate) }}</td></tr></tbody></table></div>
      <PaginationBar v-model="equipmentPage" :total="equipmentQuote.items.length" />
    </ModalDialog>

    <ModalDialog v-if="flowQuote" :title="`Fluxo da locação · ${flowQuote.number}`" @close="flowQuote = null">
      <div class="operation-context"><span class="eyebrow">{{ flowQuote.customer_name }}</span><strong>{{ shortDate(flowQuote.start_date) }} → {{ shortDate(flowQuote.end_date) }}</strong><small>{{ flowQuote.items.length }} equipamento(s) · {{ money(flowQuote.total) }}</small></div>
      <ol class="rental-flow-list"><li v-for="(item, index) in flowSteps(flowQuote)" :key="index" :class="{ done: item.done }"><span class="flow-step-icon"><Check v-if="item.done" :size="16" /><span v-else>{{ index + 1 }}</span></span><div><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></div><router-link v-if="item.link" class="btn secondary" :to="item.link" @click="flowQuote = null">Abrir</router-link></li></ol>
      <div v-if="flowQuote.status === 'CANCELLED'" class="period-callout">Reserva cancelada: {{ flowQuote.cancellation_reason }}</div>
      <RentalDocumentsPanel v-if="can('rentals.view')" :key="flowQuote.id" :quote="flowQuote" />
      <div class="modal-actions"><span class="spacer" /><button type="button" class="btn secondary" @click="flowQuote = null">Fechar</button></div>
    </ModalDialog>
    <ModalDialog v-if="operation && operationQuote" :title="({ deliver: 'Registrar entrega', extend: 'Prorrogar locação', return: 'Registrar devolução', finalize: 'Concluir devolução por equipamento', cancel: 'Cancelar locação' })[operation]" @close="operation = null; error = ''">
      <form @submit.prevent="submitOperation"><div class="form-grid">
        <div class="operation-context span-2"><span class="eyebrow">{{ operationQuote.number }}</span><strong>{{ operationQuote.customer_name }}</strong><small>{{ shortDate(operationQuote.start_date) }} → {{ shortDate(operationQuote.end_date) }} · {{ operationQuote.items.length }} equipamento(s)</small></div>
        <fieldset v-if="operation !== 'cancel'" class="operation-item-selection span-2"><legend>Equipamentos desta operação <span class="required-mark" aria-hidden="true">*</span></legend><label v-for="item in operationItems" :key="item.equipment"><input v-model="operationForm.equipment_ids" type="checkbox" :value="item.equipment" :disabled="Boolean(item.problem)" /><span><strong>{{ item.internal_code }} · {{ item.equipment_name }}</strong><small>{{ shortDate(item.start_date || operationQuote.start_date) }} a {{ shortDate(item.end_date || operationQuote.end_date) }}</small><small v-if="['deliver','return'].includes(operation)">{{ operationQuote[operation === 'return' ? 'return_transport_required' : 'delivery_transport_required'] ? fullAddress(item.destination.address,item.destination.number) : 'Na loja' }} · {{ item.destination.time || 'Horário a combinar' }}</small><small v-if="item.problem">{{ item.problem }}</small></span></label><p v-if="!operationItems.length" class="muted-text">Nenhum equipamento nesta etapa.</p></fieldset><div v-if="['deliver', 'return'].includes(operation)" class="form-field span-2"><label>{{ operation === 'deliver' ? 'Data e hora da entrega' : 'Data e hora da devolução' }}<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime v-model="operationForm.date" type="datetime-local" required /></div>
        <div v-if="operation === 'extend'" class="form-field span-2"><label>Nova data de término<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime v-model="operationForm.new_end_date" type="date" required /></div>
        <div v-if="!['cancel', 'finalize'].includes(operation)" class="form-field span-2"><label>Condições e observações</label><textarea v-model="operationForm.conditions" rows="4" :placeholder="operation === 'deliver' ? 'Responsável pela retirada, acessórios e condições da entrega.' : (operation === 'return' ? 'Estado informado no recebimento; a inspeção detalhada vem na próxima etapa.' : 'Condições comerciais da prorrogação.')" /></div>
        <div v-if="operation === 'cancel'" class="form-field span-2"><label>Motivo do cancelamento<span class="required-mark" aria-hidden="true"> *</span></label><textarea v-model="operationForm.reason" rows="4" required placeholder="Registre por que a reserva foi cancelada." /></div>
      </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="operation = null; error = ''">Voltar</button><span class="spacer" /><button class="btn" :class="operation === 'cancel' ? 'danger' : 'primary'" :disabled="busy">{{ busy ? 'Processando...' : 'Confirmar' }}</button></div></form>
    </ModalDialog>
    <ModalDialog v-if="lostModal" title="Registrar pedido não atendido" @close="lostModal = false"><form @submit.prevent="saveLostDemand">
      <p class="muted-text" style="margin:0 0 12px">Use quando o cliente pediu um item que não existe no catálogo ou estava indisponível e a locação foi perdida. A IA usa isso para sugerir a compra de novos equipamentos.</p>
      <div class="form-grid">
        <div class="form-field span-2"><label>Categoria</label><AppSelect searchable v-model="lostForm.category"><option value="">Outra / categoria nova</option><option v-for="category in lostCategoryOptions" :key="category.id" :value="category.id">{{ category.label }}</option></AppSelect></div>
        <div v-if="!lostForm.category" class="form-field span-2"><label>Nome da nova categoria (se não existir)</label><input v-model="lostForm.new_category_name" maxlength="100" placeholder="Ex.: Andaime fachadeiro" /></div>
        <div class="form-field span-2"><label>Item que o cliente pediu</label><input v-model="lostForm.requested_item" maxlength="160" placeholder="Ex.: Plataforma elevatória 10 m" /></div>
        <div class="form-field"><label>Quantidade<span class="required-mark" aria-hidden="true"> *</span></label><input placeholder="Ex.: 2" v-model.number="lostForm.quantity" type="number" min="1" max="100" required /></div><div class="form-field"><label>Dias de aluguel<span class="required-mark" aria-hidden="true"> *</span></label><input placeholder="Ex.: 5" v-model.number="lostForm.requested_days" type="number" inputmode="numeric" min="1" max="365" required /></div>
        <div class="form-field span-2"><label>Diária esperada (R$)</label><AppInput mask="money" v-model="lostForm.expected_daily_rate" inputmode="decimal" min="0" step="0.01" placeholder="Ex.: 150,00" @input="lostRateAuto = false" /></div><p class="form-hint span-2">{{ lostRateHint }}<template v-if="lostEstimate"> Receita estimada deste pedido: <strong>{{ money(lostEstimate) }}</strong>.</template></p>
        <div class="form-field span-2"><label>Motivo</label><AppSelect v-model="lostForm.reason"><option value="UNAVAILABLE">Sem unidade disponível no período</option><option value="MAINTENANCE">Equipamento em manutenção</option><option value="FLEET_CAPACITY">Capacidade insuficiente da frota</option><option value="OTHER">Não temos esse item (outro motivo)</option></AppSelect></div>
        <div class="form-field span-2"><label>Observações</label><input v-model="lostForm.notes" maxlength="2000" placeholder="Ex.: cliente fechou com outra locadora" /></div>
      </div>
      <p class="muted-text" style="margin:10px 0 0">Cliente: {{ customers.find(c => String(c.id) === String(form.customer))?.name || 'não selecionado' }}.</p>
      <div v-if="lostError" class="error-message">{{ lostError }}</div>
      <div class="modal-actions"><button type="button" class="btn secondary" @click="lostModal = false">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="lostBusy">{{ lostBusy ? 'Registrando...' : 'Registrar pedido' }}</button></div>
    </form></ModalDialog>
    <ConfirmDialog v-if="deleting" title="Excluir orçamento" :message="`Excluir “${deleting.number}”? A operação pode ser impedida se houver vínculos posteriores.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
