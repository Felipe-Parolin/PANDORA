<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  AlertTriangle, Ban, CalendarDays, CheckCircle2, ClipboardPlus, Files,
  PauseCircle, Pencil, PlayCircle, Plus, Search, Trash2, UserRoundX, Wrench,
} from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, rows, shortDate } from '../services/api'

const tab = ref('orders')
const queue = ref('ALL')
const search = ref('')
const orders = ref([])
const plans = ref([])
const equipment = ref([])
const technicians = ref([])
const modal = ref(null)
const editing = ref(null)
const deleting = ref(null)
const mediaEquipment = ref(null)
const error = ref('')
const busy = ref(false)

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
const terminalStatuses = ['COMPLETED', 'CANCELLED']
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
  { key: 'ALL', label: 'Todos', icon: Wrench },
  { key: 'UNASSIGNED', label: 'Sem técnico', icon: UserRoundX },
  { key: 'READY', label: 'Aguardando início', icon: CalendarDays },
  { key: 'IN_PROGRESS', label: 'Em andamento', icon: PlayCircle },
  { key: 'WAITING_PARTS', label: 'Aguardando peças', icon: PauseCircle },
  { key: 'ABANDONED', label: 'Abandonados', icon: Ban },
  { key: 'COMPLETED', label: 'Concluídos', icon: CheckCircle2 },
].map(item => ({ ...item, count: orders.value.filter(order => matchesQueue(order, item.key)).length })))
const filteredOrders = computed(() => {
  const term = search.value.trim().toLocaleLowerCase('pt-BR')
  return orders.value.filter(order => matchesQueue(order, queue.value)).filter(order => !term || [
    order.number, order.equipment_name, order.technician_name, order.symptoms,
  ].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
})
const activeCount = computed(() => orders.value.filter(item => !terminalStatuses.includes(item.status)).length)
const unassignedCount = computed(() => orders.value.filter(item => matchesQueue(item, 'UNASSIGNED')).length)
const equipmentById = id => equipment.value.find(item => item.id === id)

async function load() {
  const [o, p, e, u] = await Promise.all([
    api.get('/service-orders/'), api.get('/maintenance-plans/'), api.get('/equipment/'), api.get('/users/'),
  ])
  orders.value = rows(o.data)
  plans.value = rows(p.data)
  equipment.value = rows(e.data)
  technicians.value = rows(u.data).filter(user => user.permissions.includes('*') || user.permissions.includes('maintenance.manage'))
}

function openOrder(item = null) {
  editing.value = item
  modal.value = 'order'
  error.value = ''
  Object.assign(orderForm, item ? {
    equipment: item.equipment,
    maintenance_type: item.maintenance_type,
    priority: item.priority,
    symptoms: item.symptoms,
    diagnosis: item.diagnosis,
    technician: item.technician || '',
    status: item.status,
    scheduled_at: item.scheduled_at?.slice(0, 16) || '',
    final_tests: item.final_tests,
    released: item.released,
    labor_hours: item.labor_hours,
    parts_used: item.parts_used,
    abandoned_reason: item.abandoned_reason || '',
  } : {
    equipment: equipment.value[0]?.id || '', maintenance_type: 'CORRECTIVE', priority: 'NORMAL',
    symptoms: '', diagnosis: '', technician: '', status: 'OPEN', scheduled_at: '', final_tests: '',
    released: false, labor_hours: 0, parts_used: '', abandoned_reason: '',
  })
}

function openPlan(item = null) {
  editing.value = item
  modal.value = 'plan'
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

const saveOrder = () => persist('/service-orders/', {
  ...orderForm,
  technician: orderForm.technician || null,
  scheduled_at: orderForm.scheduled_at || null,
  abandoned_reason: orderForm.status === 'ABANDONED' ? orderForm.abandoned_reason : '',
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
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-heading compact">
      <div><span class="eyebrow">CONFIABILIDADE DA FROTA</span><h1>Manutenção</h1><p>Organize chamados por fila, responsável e etapa da execução.</p></div>
      <button v-if="can('maintenance.manage')" class="btn primary" @click="tab === 'orders' ? openOrder() : openPlan()"><Plus :size="18" />{{ tab === 'orders' ? 'Novo chamado' : 'Novo plano' }}</button>
    </header>

    <section v-if="alerts.length" class="alert-strip"><AlertTriangle :size="20" /><div><strong>{{ alerts.length }} alertas de manutenção</strong><span>Revise os planos próximos ou vencidos antes de liberar equipamentos.</span></div></section>
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>

    <section class="maintenance-overview">
      <button @click="tab = 'orders'; queue = 'UNASSIGNED'"><UserRoundX :size="20" /><span>Sem técnico<strong>{{ unassignedCount }}</strong></span></button>
      <button @click="tab = 'orders'; queue = 'IN_PROGRESS'"><PlayCircle :size="20" /><span>Em andamento<strong>{{ orders.filter(item => item.status === 'IN_PROGRESS').length }}</strong></span></button>
      <button @click="tab = 'orders'; queue = 'ABANDONED'"><Ban :size="20" /><span>Abandonados<strong>{{ orders.filter(item => item.status === 'ABANDONED').length }}</strong></span></button>
      <button @click="tab = 'orders'; queue = 'ALL'"><Wrench :size="20" /><span>Chamados ativos<strong>{{ activeCount }}</strong></span></button>
    </section>

    <div class="tabs section-tabs">
      <button :class="{ active: tab === 'orders' }" @click="tab = 'orders'"><Wrench :size="17" />Chamados</button>
      <button :class="{ active: tab === 'plans' }" @click="tab = 'plans'"><CalendarDays :size="17" />Planos e agenda</button>
    </div>

    <template v-if="tab === 'orders'">
      <div class="workflow-tabs" role="tablist" aria-label="Filtrar chamados por etapa">
        <button v-for="item in queueTabs" :key="item.key" :class="{ active: queue === item.key }" @click="queue = item.key">
          <component :is="item.icon" :size="16" /><span>{{ item.label }}</span><b>{{ item.count }}</b>
        </button>
      </div>
      <section class="panel list-panel">
        <header class="list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Buscar OS, equipamento, técnico ou relato" /></div><span class="result-count">{{ filteredOrders.length }} chamado(s)</span></header>
        <div class="table-wrap desktop-list"><table><thead><tr><th>OS</th><th>Equipamento</th><th>Tipo</th><th>Técnico</th><th>Abertura</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody>
          <tr v-for="order in filteredOrders" :key="order.id"><td><strong>{{ order.number }}</strong><small>{{ order.priority }}</small></td><td>{{ order.equipment_name }}</td><td>{{ order.maintenance_type_label }}</td><td><span :class="{ 'unassigned-label': !order.technician_name }">{{ order.technician_name || 'Sem técnico' }}</span></td><td>{{ shortDate(order.opened_at?.slice(0, 10)) }}</td><td><StatusBadge :value="order.status" :label="order.status_label" /><small v-if="order.status === 'ABANDONED'" class="abandoned-note">{{ order.abandoned_reason }}</small></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Mídias do equipamento" @click="mediaEquipment = equipmentById(order.equipment)"><Files :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn table-action" title="Editar chamado" @click="openOrder(order)"><Pencil :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn danger-icon" title="Excluir chamado" @click="requestDelete('order', order)"><Trash2 :size="17" /></button></div></td></tr>
          <tr v-if="!filteredOrders.length"><td colspan="7" class="empty-cell"><ClipboardPlus :size="22" />Nenhum chamado nesta fila.</td></tr>
        </tbody></table></div>
        <div class="mobile-card-list">
          <article v-for="order in filteredOrders" :key="order.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ order.number }} · {{ order.priority }}</span><strong>{{ order.equipment_name }}</strong></div><StatusBadge :value="order.status" :label="order.status_label" /></header><dl><div><dt>Tipo</dt><dd>{{ order.maintenance_type_label }}</dd></div><div><dt>Técnico</dt><dd>{{ order.technician_name || 'Sem técnico' }}</dd></div><div><dt>Abertura</dt><dd>{{ shortDate(order.opened_at?.slice(0, 10)) }}</dd></div></dl><p v-if="order.status === 'ABANDONED'" class="abandoned-callout"><strong>Motivo do abandono</strong>{{ order.abandoned_reason }}</p><footer><button class="btn secondary" @click="mediaEquipment = equipmentById(order.equipment)"><Files :size="16" />Mídias</button><button v-if="can('maintenance.manage')" class="btn secondary" @click="openOrder(order)"><Pencil :size="16" />Editar</button></footer></article>
          <div v-if="!filteredOrders.length" class="empty-state compact"><ClipboardPlus :size="26" /><h2>Nenhum chamado nesta fila</h2></div>
        </div>
      </section>
    </template>

    <section v-else class="panel list-panel">
      <div class="table-wrap desktop-list"><table><thead><tr><th>Plano</th><th>Equipamento</th><th>Modalidade</th><th>Próxima execução</th><th>Gatilho por uso</th><th>Criticidade</th><th>Alerta</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="plan in plans" :key="plan.id"><td><strong>{{ plan.name }}</strong><small v-if="!plan.active">Plano inativo</small></td><td>{{ plan.equipment_name }}</td><td>{{ plan.maintenance_type_label }}</td><td><strong>{{ plan.due_date ? shortDate(plan.due_date) : 'Sem data' }}</strong><small v-if="plan.interval_days">a cada {{ plan.interval_days }} dias</small></td><td><strong>{{ plan.due_usage_hours !== null ? `${plan.due_usage_hours} h` : 'Não configurado' }}</strong><small v-if="plan.usage_remaining !== null">{{ plan.usage_remaining >= 0 ? `${plan.usage_remaining} h restantes` : `${Math.abs(plan.usage_remaining)} h excedidas` }}</small></td><td>{{ plan.criticality_label }}</td><td><StatusBadge :value="plan.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Mídias do equipamento" @click="mediaEquipment = equipmentById(plan.equipment)"><Files :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn table-action" title="Editar plano" @click="openPlan(plan)"><Pencil :size="17" /></button><button v-if="can('maintenance.manage')" class="icon-btn danger-icon" title="Excluir plano" @click="requestDelete('plan', plan)"><Trash2 :size="17" /></button></div></td></tr><tr v-if="!plans.length"><td colspan="8" class="empty-cell">Nenhum plano de manutenção cadastrado.</td></tr></tbody></table></div>
      <div class="mobile-card-list"><article v-for="plan in plans" :key="plan.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ plan.maintenance_type_label }} · {{ plan.criticality_label }}</span><strong>{{ plan.name }}</strong><small>{{ plan.equipment_name }}</small></div><StatusBadge :value="plan.alert_status" :label="({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status]" /></header><dl><div><dt>Próxima data</dt><dd>{{ plan.due_date ? shortDate(plan.due_date) : 'Não configurada' }}</dd></div><div><dt>Próximo uso</dt><dd>{{ plan.due_usage_hours !== null ? `${plan.due_usage_hours} h` : 'Não configurado' }}</dd></div><div><dt>Margem de uso</dt><dd>{{ plan.usage_remaining !== null ? `${plan.usage_remaining} h` : '—' }}</dd></div></dl><footer><button class="btn secondary" @click="mediaEquipment = equipmentById(plan.equipment)"><Files :size="15" />Mídias</button><button v-if="can('maintenance.manage')" class="btn secondary" @click="openPlan(plan)"><Pencil :size="15" />Editar plano</button></footer></article><div v-if="!plans.length" class="empty-state compact"><CalendarDays :size="26" /><h2>Nenhum plano cadastrado</h2></div></div>
    </section>

    <ModalDialog v-if="modal === 'order'" :title="editing ? `Editar ${editing.number}` : 'Abrir chamado de manutenção'" wide @close="modal = null">
      <form @submit.prevent="saveOrder"><div class="form-grid three">
        <div class="form-field span-2"><label>Equipamento</label><select v-model="orderForm.equipment" required><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></select></div>
        <div class="form-field"><label>Status do chamado</label><select v-model="orderForm.status"><option value="OPEN">Aberto</option><option value="SCHEDULED">Agendado</option><option value="IN_PROGRESS">Em andamento</option><option value="WAITING_PARTS">Aguardando peças</option><option value="ABANDONED">Abandonado</option><option value="COMPLETED">Concluído</option><option value="CANCELLED">Cancelado</option></select></div>
        <div class="form-field"><label>Tipo</label><select v-model="orderForm.maintenance_type"><option value="CORRECTIVE">Corretiva</option><option value="PREVENTIVE">Preventiva</option><option value="SCHEDULED">Agendada</option><option value="PRE_RENTAL">Antes da locação</option><option value="POST_RENTAL">Pós-locação</option></select></div>
        <div class="form-field"><label>Prioridade</label><select v-model="orderForm.priority"><option>NORMAL</option><option>ALTA</option><option>CRÍTICA</option></select></div>
        <div class="form-field"><label>Agendamento</label><input v-model="orderForm.scheduled_at" type="datetime-local" /></div>
        <div class="form-field span-2"><label>Técnico responsável</label><select v-model="orderForm.technician" :required="['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(orderForm.status)"><option value="">Sem técnico / fila de triagem</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
        <div class="form-field span-3"><label>Sintomas / relato inicial</label><textarea v-model="orderForm.symptoms" rows="3" required /></div>
        <div v-if="orderForm.status === 'ABANDONED'" class="form-field span-3 abandonment-field"><label>Motivo do abandono</label><textarea v-model="orderForm.abandoned_reason" rows="3" required placeholder="Descreva por que o atendimento foi interrompido e o que falta para retomá-lo." /><small>O chamado fica destacado para redistribuição e o equipamento continua bloqueado.</small></div>
        <template v-if="editing"><div class="form-field span-2"><label>Diagnóstico</label><textarea v-model="orderForm.diagnosis" rows="3" /></div><div class="form-field"><label>Horas de mão de obra</label><input v-model="orderForm.labor_hours" type="number" min="0" step="0.25" /></div><div class="form-field span-2"><label>Testes finais</label><textarea v-model="orderForm.final_tests" rows="3" /></div><div class="form-field"><label>Peças utilizadas</label><textarea v-model="orderForm.parts_used" rows="3" /></div><label v-if="can('maintenance.release') && orderForm.status === 'COMPLETED'" class="check-line span-3"><input v-model="orderForm.released" type="checkbox" />Liberar equipamento após validação técnica</label></template>
      </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar chamado' }}</button></div></form>
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
    <ConfirmDialog v-if="deleting" :title="deleting.kind === 'order' ? 'Excluir chamado' : 'Excluir plano'" :message="`Excluir “${deleting.item.number || deleting.item.name}”? Esta ação não pode ser desfeita.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
