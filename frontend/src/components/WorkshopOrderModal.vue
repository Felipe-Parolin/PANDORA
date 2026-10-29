<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { CheckCircle2, Files, Save, Trash2 } from 'lucide-vue-next'
import EquipmentConditionChoice from './EquipmentConditionChoice.vue'
import EquipmentMediaModal from './EquipmentMediaModal.vue'
import ModalDialog from './ModalDialog.vue'
import StatusBadge from './StatusBadge.vue'
import { api, apiError, can, shortDate } from '../services/api'
import { serviceOrderState, serviceOrderStateLabel } from '../services/maintenance'

const props = defineProps({ order: { type: Object, required: true }, equipment: { type: Object, default: null }, technicians: { type: Array, default: () => [] } })
const emit = defineEmits(['close', 'changed', 'delete'])
const equipmentDetails = ref(props.equipment)
const mediaOpen = ref(false)
const error = ref('')
const busy = ref(false)
const editable = computed(() => can('maintenance.manage') && !['COMPLETED', 'CANCELLED'].includes(props.order.status))
const form = reactive({
  technician: props.order.technician || '', diagnosis: props.order.diagnosis || '',
  equipment_condition: props.order.operational_status || props.order.equipment_condition || (props.order.released ? 'OPERATING' : 'PENDING'),
  final_tests: props.order.final_tests || '',
})
const canConclude = computed(() => editable.value && can('maintenance.release') && form.equipment_condition === 'OPERATING')
function chooseCondition(value) {
  if (!editable.value) return
  form.equipment_condition = value
  error.value = ''
}
async function save(conclude = false) {
  if (!editable.value) return
  error.value = ''
  if ((conclude || ['IN_PROGRESS', 'WAITING_PARTS', 'ABANDONED'].includes(props.order.status)) && !form.technician) {
    error.value = 'Escolha o técnico responsável por este atendimento.'; return
  }
  if (form.equipment_condition === 'BROKEN' && !form.diagnosis.trim()) { error.value = 'Descreva o problema encontrado.'; return }
  if (conclude && (!canConclude.value || !form.final_tests.trim())) {
    error.value = 'Para concluir, confirme Operante e registre os testes finais. A liberação exige a permissão correspondente.'; return
  }
  busy.value = true
  try {
    await api.patch(`/service-orders/${props.order.id}/`, {
      ...form, technician: form.technician || null,
      ...(conclude ? { status: 'COMPLETED', released: true } : {}),
    })
    emit('changed')
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}
onMounted(async () => {
  if (!equipmentDetails.value && can('assets.view')) {
    try { equipmentDetails.value = (await api.get(`/equipment/${props.order.equipment}/`)).data }
    catch { /* The OS remains readable when the equipment detail is unavailable. */ }
  }
})
</script>

<template>
  <ModalDialog v-if="!mediaOpen" :title="`OS · ${order.number}`" wide @close="emit('close')">
    <div class="workshop-order-context"><div><span class="eyebrow">{{ order.maintenance_type_label }}</span><h3>{{ equipmentDetails?.internal_code }}{{ equipmentDetails?.internal_code ? ' · ' : '' }}{{ order.equipment_name }}</h3><p v-if="order.plan_name">Revisão automática · {{ order.plan_name }}</p></div><StatusBadge :value="serviceOrderState(order.status)" :label="serviceOrderStateLabel(order.status)" /></div>
    <form class="workshop-order-form" @submit.prevent="save()">
      <section class="workshop-details-panel" aria-label="Detalhes da ordem de serviço">
        <dl class="inspection-equipment-details"><div><dt>Marca e modelo</dt><dd>{{ [equipmentDetails?.brand, equipmentDetails?.model].filter(Boolean).join(' · ') || 'Não informado' }}</dd></div><div><dt>Número de série</dt><dd>{{ equipmentDetails?.serial_number || 'Não informado' }}</dd></div><div><dt>Abertura</dt><dd>{{ shortDate(order.opened_at?.slice(0, 10)) }}</dd></div></dl>
        <div class="order-request-readout"><span class="eyebrow">SOLICITAÇÃO ORIGINAL</span><p>{{ order.symptoms }}</p><small v-if="order.plan_due_date">Vencimento da revisão: {{ shortDate(order.plan_due_date) }}</small></div>
        <fieldset class="workshop-order-fields" :disabled="!editable || busy"><div class="form-grid">
          <div class="form-field span-2"><label for="workshop-technician">Técnico responsável</label><select id="workshop-technician" v-model="form.technician"><option value="">A definir</option><option v-for="user in technicians" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
          <div v-if="order.abandoned_reason" class="form-field span-2"><span class="order-readout-label">Motivo do abandono registrado</span><div class="order-readout">{{ order.abandoned_reason }}</div></div>
        </div>
        </fieldset>
      </section>
      <section class="workshop-condition-panel" aria-label="Avaliação do equipamento">
        <EquipmentConditionChoice :model-value="form.equipment_condition" :disabled="!editable || busy" operating-hint="Funcionamento verificado. Pode ser liberado ao concluir a OS." @update:model-value="chooseCondition" />
        <p v-if="form.equipment_condition === 'PENDING'" class="workshop-condition-note">A condição ainda não foi avaliada.</p>
        <div class="form-field"><label for="workshop-diagnosis">{{ form.equipment_condition === 'BROKEN' ? 'Qual é o problema?' : 'Avaliação e serviço realizado' }}</label><textarea id="workshop-diagnosis" v-model="form.diagnosis" :disabled="!editable || busy" rows="4" placeholder="Descreva o que foi verificado e o andamento do reparo." /></div>
        <div v-if="form.equipment_condition === 'OPERATING' || form.final_tests" class="form-field"><label for="workshop-tests">Testes finais (para concluir e liberar)</label><textarea id="workshop-tests" v-model="form.final_tests" :disabled="!editable || busy" rows="3" placeholder="Como o funcionamento e a segurança foram verificados?" /></div>
        <p class="workshop-condition-note">{{ form.equipment_condition === 'BROKEN' ? 'O equipamento inoperante permanece bloqueado até o reparo e a liberação.' : 'Salve a avaliação para registrar o atendimento. Quando estiver operante e testado, use “Concluir e liberar”.' }}</p>
      </section>
      <div v-if="can('media.view') && equipmentDetails" class="maintenance-order-tools"><button type="button" class="btn secondary" @click="mediaOpen = true"><Files :size="16" />Mídias do equipamento</button></div>
      <div v-if="error" class="error-message">{{ error }}</div>
      <div class="modal-actions"><button type="button" class="btn secondary" @click="emit('close')">{{ editable ? 'Cancelar' : 'Fechar' }}</button><button v-if="editable && !order.plan_due_date && order.equipment_condition !== 'BROKEN'" type="button" class="btn secondary" :disabled="busy" @click="emit('delete')"><Trash2 :size="15" />Excluir OS</button><span class="spacer" /><button v-if="editable" class="btn" :class="canConclude ? 'secondary' : 'primary'" :disabled="busy"><Save :size="16" />{{ busy ? 'Salvando...' : 'Salvar avaliação' }}</button><button v-if="canConclude" type="button" class="btn primary" :disabled="busy" @click="save(true)"><CheckCircle2 :size="16" />Concluir e liberar</button></div>
    </form>
  </ModalDialog>
  <EquipmentMediaModal v-else :equipment="equipmentDetails" @close="mediaOpen = false" />
</template>
