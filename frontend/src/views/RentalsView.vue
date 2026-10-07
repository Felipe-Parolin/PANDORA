<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  AlertCircle, CalendarRange, Check, CheckCircle2, ChevronRight, CirclePlus,
  ClipboardCheck, Clock3, PackageCheck, Pencil, Plus, RotateCcw, Search, Trash2,
  Truck, XCircle,
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
const step = ref(1)
const busy = ref(false)
const statusFilter = ref('ALL')
const quoteSearch = ref('')
const equipmentSearch = ref('')
const availableEquipment = ref([])
const blockedEquipment = ref([])
const availabilityLoading = ref(false)
const availabilityChecked = ref(false)
const inspectionContext = ref(null)
const operation = ref(null)
const operationQuote = ref(null)
const notice = ref('')
const operationForm = reactive({ date: '', conditions: '', new_end_date: '', reason: '' })

const form = reactive({ customer: '', start_date: '', end_date: '', status: 'DRAFT', conditions: '', discount: 0, notes: '', items: [] })
const days = computed(() => form.start_date && form.end_date ? Math.max(Math.round((new Date(`${form.end_date}T12:00:00`) - new Date(`${form.start_date}T12:00:00`)) / 86400000) + 1, 1) : 1)
const periodValid = computed(() => form.customer && form.start_date && form.end_date && form.end_date >= form.start_date)
const subtotal = computed(() => form.items.reduce((sum, item) => sum + Number(item.daily_rate) * days.value, 0))
const total = computed(() => Math.max(subtotal.value - Number(form.discount || 0), 0))
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
    notice.value = `${quote.number} reservada. A inspeção pré-locação já pode ser realizada.`
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
  step.value = 1
  modal.value = true
  availableEquipment.value = []
  blockedEquipment.value = []
  availabilityChecked.value = false
  equipmentSearch.value = ''
  if (item) {
    Object.assign(form, {
      customer: item.customer, start_date: item.start_date, end_date: item.end_date, status: item.status,
      conditions: item.conditions, discount: item.discount, notes: item.notes,
      items: item.items.map(line => ({ equipment_id: line.equipment, name: line.equipment_name, code: line.internal_code, daily_rate: line.daily_rate, quantity_days: line.quantity_days })),
    })
  } else {
    const today = new Date()
    const later = new Date(Date.now() + 3 * 86400000)
    Object.assign(form, {
      customer: customers.value[0]?.id || '', start_date: today.toISOString().slice(0, 10), end_date: later.toISOString().slice(0, 10), status: 'DRAFT',
      conditions: 'Retirada e devolução no balcão. Combustível e transporte por conta do cliente.', discount: 0, notes: '', items: [],
    })
  }
}

async function loadAvailability() {
  if (!periodValid.value) return
  availabilityLoading.value = true
  error.value = ''
  try {
    const params = { start: form.start_date, end: form.end_date }
    if (editing.value) params.ignore_quote = editing.value.id
    const { data } = await api.get('/rental-quotes/availability/', { params })
    availableEquipment.value = data.available.map(item => item.equipment)
    blockedEquipment.value = data.blocked
    availabilityChecked.value = true
  } catch (e) {
    error.value = apiError(e)
  } finally {
    availabilityLoading.value = false
  }
}

async function nextStep() {
  if (step.value === 1) {
    await loadAvailability()
    if (!availabilityChecked.value) return
  }
  step.value += 1
}

function toggle(item) {
  const index = form.items.findIndex(line => line.equipment_id === item.id)
  if (index >= 0) form.items.splice(index, 1)
  else form.items.push({ equipment_id: item.id, name: item.name, code: item.internal_code, daily_rate: item.daily_rate, quantity_days: days.value })
}

watch(() => [form.start_date, form.end_date], () => {
  availabilityChecked.value = false
  form.items.forEach(item => { item.quantity_days = days.value })
})

async function save() {
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
          <td><StatusBadge :value="quote.status" :label="quote.status_label" /><small v-if="quote.status === 'APPROVED'">Pré-inspeção {{ inspectionProgress(quote, 'PRE_RENTAL').done }}/{{ inspectionProgress(quote, 'PRE_RENTAL').total }}</small><small v-if="quote.status === 'RETURNED'">Inspeção final {{ inspectionProgress(quote, 'RETURN').done }}/{{ inspectionProgress(quote, 'RETURN').total }}</small></td>
          <td class="right"><strong>{{ money(quote.total) }}</strong></td>
          <td class="right"><div class="row-actions rental-row-actions">
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT'].includes(quote.status)" class="icon-btn table-action" title="Editar orçamento" @click="open(quote)"><Pencil :size="17" /></button>
            <button v-if="can('rentals.approve') && ['DRAFT', 'SENT'].includes(quote.status)" class="icon-btn success-action" title="Aprovar e reservar" :disabled="busy" @click="reserve(quote)"><PackageCheck :size="17" /></button>
            <button v-if="['APPROVED'].includes(quote.status)" class="icon-btn table-action" title="Inspeção pré-locação" @click="inspectionContext = { quote, type: 'PRE_RENTAL' }"><ClipboardCheck :size="17" /></button>
            <button v-if="can('rentals.dispatch') && quote.status === 'APPROVED'" class="icon-btn success-action" title="Registrar entrega" @click="openOperation('deliver', quote)"><Truck :size="17" /></button>
            <button v-if="can('rentals.extend') && ['APPROVED', 'ACTIVE'].includes(quote.status)" class="icon-btn table-action" title="Prorrogar locação" @click="openOperation('extend', quote)"><CalendarRange :size="17" /></button>
            <button v-if="can('rentals.return') && quote.status === 'ACTIVE'" class="icon-btn table-action" title="Registrar devolução" @click="openOperation('return', quote)"><RotateCcw :size="17" /></button>
            <button v-if="['RETURNED', 'COMPLETED'].includes(quote.status)" class="icon-btn table-action" title="Inspeção final" @click="inspectionContext = { quote, type: 'RETURN' }"><ClipboardCheck :size="17" /></button>
            <button v-if="can('rentals.return') && quote.status === 'RETURNED'" class="icon-btn success-action" title="Concluir devolução" :disabled="inspectionProgress(quote, 'RETURN').done !== inspectionProgress(quote, 'RETURN').total" @click="finalizeReturn(quote)"><CheckCircle2 :size="17" /></button>
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT', 'APPROVED'].includes(quote.status)" class="icon-btn danger-icon" title="Cancelar" @click="openOperation('cancel', quote)"><XCircle :size="17" /></button>
            <button v-if="can('rentals.manage') && ['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(quote.status)" class="icon-btn danger-icon" title="Excluir" @click="deleting = quote"><Trash2 :size="17" /></button>
          </div></td>
        </tr><tr v-if="!filteredQuotes.length"><td colspan="7" class="empty-cell">Nenhuma locação nesta etapa.</td></tr>
      </tbody></table></div>
      <div class="mobile-card-list"><article v-for="quote in filteredQuotes" :key="quote.id" class="mobile-record-card rental-mobile-card"><header><div><span class="eyebrow">{{ quote.number }}</span><strong>{{ quote.customer_name }}</strong></div><StatusBadge :value="quote.status" :label="quote.status_label" /></header><dl><div><dt>Período</dt><dd>{{ shortDate(quote.start_date) }} → {{ shortDate(quote.end_date) }}</dd></div><div><dt>Equipamentos</dt><dd>{{ quote.items.length }}</dd></div><div><dt>Total</dt><dd><strong>{{ money(quote.total) }}</strong></dd></div></dl><footer>
        <button v-if="can('rentals.manage') && ['DRAFT', 'SENT'].includes(quote.status)" class="btn secondary" @click="open(quote)"><Pencil :size="15" />Editar</button>
        <button v-if="can('rentals.approve') && ['DRAFT', 'SENT'].includes(quote.status)" class="btn primary" @click="reserve(quote)"><PackageCheck :size="15" />Reservar</button>
        <button v-if="quote.status === 'APPROVED'" class="btn secondary" @click="inspectionContext = { quote, type: 'PRE_RENTAL' }"><ClipboardCheck :size="15" />Inspecionar</button>
        <button v-if="can('rentals.dispatch') && quote.status === 'APPROVED'" class="btn primary" @click="openOperation('deliver', quote)"><Truck :size="15" />Entregar</button>
        <button v-if="can('rentals.extend') && ['APPROVED', 'ACTIVE'].includes(quote.status)" class="btn secondary" @click="openOperation('extend', quote)"><CalendarRange :size="15" />Prorrogar</button>
        <button v-if="can('rentals.return') && quote.status === 'ACTIVE'" class="btn primary" @click="openOperation('return', quote)"><RotateCcw :size="15" />Devolver</button>
        <button v-if="['RETURNED', 'COMPLETED'].includes(quote.status)" class="btn secondary" @click="inspectionContext = { quote, type: 'RETURN' }"><ClipboardCheck :size="15" />Inspeção final</button>
        <button v-if="can('rentals.return') && quote.status === 'RETURNED'" class="btn primary" :disabled="inspectionProgress(quote, 'RETURN').done !== inspectionProgress(quote, 'RETURN').total" @click="finalizeReturn(quote)"><CheckCircle2 :size="15" />Concluir</button>
      </footer></article></div>
    </section>

    <ModalDialog v-if="modal" :title="editing ? `Editar ${editing.number}` : 'Novo orçamento de locação'" wide @close="modal = false">
      <div class="stepper"><span :class="{ active: step >= 1, current: step === 1 }"><i>1</i><em>Cliente e período</em></span><ChevronRight :size="16" /><span :class="{ active: step >= 2, current: step === 2 }"><i>2</i><em>Disponibilidade</em></span><ChevronRight :size="16" /><span :class="{ active: step >= 3, current: step === 3 }"><i>3</i><em>Preço e resumo</em></span></div>
      <form @submit.prevent="save">
        <div v-if="step === 1" class="form-grid">
          <div class="form-field span-2"><label>Cliente</label><select v-model="form.customer" required><option v-for="customer in customers" :key="customer.id" :value="customer.id">{{ customer.name }} · {{ customer.document }}</option></select></div>
          <div class="form-field"><label>Início</label><input v-model="form.start_date" type="date" required /></div><div class="form-field"><label>Fim previsto</label><input v-model="form.end_date" type="date" :min="form.start_date" required /></div>
          <div class="form-field span-2"><label>Etapa comercial</label><select v-model="form.status"><option value="DRAFT">Rascunho</option><option value="SENT">Enviado ao cliente</option></select></div>
          <div class="period-callout span-2"><CalendarRange :size="20" /><div><strong>{{ days }} diária(s)</strong><span>A próxima etapa valida conflitos de locação e bloqueios de manutenção.</span></div></div>
        </div>

        <div v-if="step === 2" class="availability-step">
          <div class="availability-toolbar"><div><span class="eyebrow">PERÍODO VALIDADO</span><strong>{{ shortDate(form.start_date) }} → {{ shortDate(form.end_date) }}</strong></div><div class="search-box"><Search :size="17" /><input v-model="equipmentSearch" placeholder="Buscar equipamento" /></div></div>
          <div v-if="availabilityLoading" class="availability-loading"><Clock3 :size="22" />Consultando disponibilidade...</div>
          <template v-else>
            <div class="availability-result success"><CheckCircle2 :size="18" /><span><strong>{{ visibleAvailable.length }} disponíveis</strong> para selecionar no período</span></div>
            <div class="equipment-picker"><button v-for="item in visibleAvailable" :key="item.id" type="button" :class="{ selected: form.items.some(line => line.equipment_id === item.id) }" @click="toggle(item)"><span class="select-check"><Check :size="15" /></span><div><strong>{{ item.name }}</strong><small>{{ item.internal_code }} · {{ item.category_name }}</small></div><b>{{ money(item.daily_rate) }}<small>/dia</small></b></button></div>
            <details v-if="visibleBlocked.length" class="blocked-equipment"><summary><AlertCircle :size="17" />{{ visibleBlocked.length }} equipamento(s) indisponível(is)</summary><article v-for="item in visibleBlocked" :key="item.equipment.id"><div><strong>{{ item.equipment.internal_code }} · {{ item.equipment.name }}</strong><span>{{ item.reason }}</span></div><StatusBadge value="MAINTENANCE" label="Bloqueado" /></article></details>
          </template>
        </div>

        <div v-if="step === 3" class="quote-builder">
          <div class="quote-lines"><div v-for="item in form.items" :key="item.equipment_id" class="quote-line"><div><strong>{{ item.name }}</strong><span>{{ item.code }} · {{ days }} diária(s)</span></div><label class="rate-editor"><span>Diária</span><input v-model="item.daily_rate" type="number" min="0" step="0.01" /></label><strong>{{ money(Number(item.daily_rate) * days) }}</strong><button type="button" class="icon-btn" title="Remover equipamento" @click="toggle({ id: item.equipment_id })"><Trash2 :size="17" /></button></div><div class="form-field"><label>Condições comerciais</label><textarea v-model="form.conditions" rows="3" /></div><div class="form-field"><label>Observações internas</label><textarea v-model="form.notes" rows="3" placeholder="Informações que não fazem parte das condições enviadas ao cliente." /></div></div>
          <aside class="quote-total"><span>Subtotal <strong>{{ money(subtotal) }}</strong></span><label>Desconto <input v-model="form.discount" type="number" min="0" :max="subtotal" step="0.01" /></label><div>Total <strong>{{ money(total) }}</strong></div><p>A aprovação reserva os equipamentos e repete a validação de conflitos.</p></aside>
        </div>

        <div v-if="error" class="error-message">{{ error }}</div>
        <div class="modal-actions"><button v-if="step > 1" type="button" class="btn secondary" @click="step--">Voltar</button><button v-else type="button" class="btn secondary" @click="modal = false">Cancelar</button><span class="spacer" /><button v-if="step < 3" type="button" class="btn primary" :disabled="busy || availabilityLoading || (step === 1 && !periodValid) || (step === 2 && !form.items.length)" @click="nextStep">{{ availabilityLoading ? 'Validando...' : 'Continuar' }} <ChevronRight :size="17" /></button><button v-else class="btn primary" :disabled="busy || !form.items.length"><CirclePlus :size="17" />{{ busy ? 'Salvando...' : (editing ? 'Salvar alterações' : 'Salvar orçamento') }}</button></div>
      </form>
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
