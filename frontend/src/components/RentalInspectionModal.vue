<script setup>
import { computed, onMounted, ref } from 'vue'
import { CheckCircle2, Save, ShieldAlert } from 'lucide-vue-next'
import EquipmentConditionChoice from './EquipmentConditionChoice.vue'
import ModalDialog from './ModalDialog.vue'
import StatusBadge from './StatusBadge.vue'
import { api, apiError, can, rows } from '../services/api'

const props = defineProps({
  quote: { type: Object, required: true },
  type: { type: String, required: true },
  initialId: { type: Number, default: null },
})
const emit = defineEmits(['close', 'changed'])
const inspections = ref([])
const selectedId = ref(props.initialId)
const error = ref('')
const busy = ref(false)
const selected = computed(() => inspections.value.find(item => item.id === selectedId.value) || inspections.value[0])
const title = computed(() => props.type === 'PRE_RENTAL' ? 'Avaliação antes da locação' : 'Avaliação da devolução')
const editable = computed(() => (
  (props.type === 'PRE_RENTAL' && can('maintenance.manage') && props.quote.status === 'APPROVED')
  || (props.type === 'RETURN' && (can('maintenance.manage') || can('maintenance.view') && can('rentals.inspect')) && props.quote.status === 'RETURNED')
))
const completed = computed(() => inspections.value.filter(item => item.result !== 'PENDING').length)
const previous = computed(() => props.quote.inspections?.find(item => item.inspection_type === 'PRE_RENTAL' && item.equipment === selected.value?.equipment))
const decision = computed(() => selected.value?.result === 'PENDING' ? '' : ['DAMAGED', 'CRITICAL'].includes(selected.value?.condition) || selected.value?.result === 'BLOCKED' ? 'BROKEN' : 'OPERATING')

async function load() {
  const { data } = await api.get('/rental-inspections/', { params: { quote: props.quote.id, type: props.type } })
  inspections.value = rows(data)
  if (!inspections.value.some(item => item.id === selectedId.value)) selectedId.value = inspections.value[0]?.id
}

function choose(value) {
  if (!selected.value || !editable.value) return
  selected.value.condition = value === 'BROKEN' ? 'DAMAGED' : 'GOOD'
  selected.value.result = value === 'BROKEN' ? 'BLOCKED' : 'APPROVED'
  selected.value.critical_impediment = false
  error.value = ''
}

async function save() {
  if (!selected.value) return
  if (!decision.value) { error.value = 'Selecione se o equipamento está operante ou inoperante.'; return }
  if (decision.value === 'BROKEN' && !selected.value.observations?.trim()) { error.value = 'Descreva o problema para encaminhar o equipamento ao reparo.'; return }
  busy.value = true
  error.value = ''
  try {
    await api.patch(`/rental-inspections/${selected.value.id}/`, {
      equipment_decision: decision.value === 'BROKEN' ? 'BROKEN' : 'OPERATING',
      observations: selected.value.observations || '',
    })
    await load()
    emit('changed')
  } catch (event) {
    error.value = apiError(event)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <ModalDialog :title="`${title} · ${quote.number}`" wide @close="emit('close')">
    <div class="inspection-progress"><div><span class="eyebrow">EQUIPAMENTOS AVALIADOS</span><strong>{{ completed }} de {{ inspections.length }}</strong></div><div class="progress-track"><i :style="{ width: `${inspections.length ? completed / inspections.length * 100 : 0}%` }" /></div></div>
    <div class="inspection-flow-hint"><ShieldAlert :size="18" /><span>{{ type === 'PRE_RENTAL' ? 'Confirme a condição do equipamento antes da entrega. Se estiver inoperante, a locação fica bloqueada até o reparo.' : 'Registre a condição na devolução. Um equipamento inoperante permanece indisponível e segue para reparo.' }}</span></div>
    <div v-if="inspections.length" class="inspection-layout">
      <nav class="inspection-equipment-list" aria-label="Equipamentos da locação"><button v-for="item in inspections" :key="item.id" :class="{ active: item.id === selected?.id }" @click="selectedId = item.id; error = ''"><span><strong>{{ item.internal_code }}</strong><small>{{ item.equipment_name }}</small></span><StatusBadge :value="item.result" :label="item.result === 'PENDING' ? 'Pendente' : item.result === 'BLOCKED' ? 'Inoperante' : 'Operante'" /></button></nav>
      <section v-if="selected" class="inspection-editor">
        <div v-if="type === 'RETURN' && previous" class="comparison-strip"><div><span class="eyebrow">NA SAÍDA</span><strong>{{ previous.result === 'BLOCKED' ? 'Inoperante' : previous.result === 'PENDING' ? 'Pendente' : 'Operante' }}</strong><small>{{ previous.observations || 'Sem observações.' }}</small></div><div><span class="eyebrow">NA DEVOLUÇÃO</span><strong>{{ decision === 'BROKEN' ? 'Inoperante' : decision === 'OPERATING' ? 'Operante' : 'Aguardando avaliação' }}</strong></div></div>
        <header class="inspection-editor-heading"><div><span class="eyebrow">{{ selected.category_name }}</span><h3>{{ selected.internal_code }} · {{ selected.equipment_name }}</h3></div></header>
        <dl class="inspection-equipment-details"><div><dt>Marca e modelo</dt><dd>{{ [selected.equipment_brand, selected.equipment_model].filter(Boolean).join(' · ') || 'Não informado' }}</dd></div><div><dt>Número de série</dt><dd>{{ selected.equipment_serial_number || 'Não informado' }}</dd></div><div><dt>Situação no cadastro</dt><dd>{{ selected.equipment_status_label || 'Não informada' }}</dd></div></dl>
        <EquipmentConditionChoice :model-value="decision" :disabled="!editable" :operating-hint="type === 'PRE_RENTAL' ? 'Pode liberar a locação.' : 'Pode voltar a ficar disponível.'" broken-hint="Bloqueia o uso e encaminha ao reparo." @update:model-value="choose" />
        <div class="form-field inspection-observations"><label for="inspection-observations">{{ decision === 'BROKEN' ? 'Qual é o problema? *' : 'Observações (opcional)' }}</label><textarea id="inspection-observations" v-model="selected.observations" :disabled="!editable" rows="3" placeholder="Descreva a condição, avaria ou informação importante." /></div>
        <p v-if="selected.performed_by_name" class="inspection-signature"><CheckCircle2 :size="17" />Última avaliação por <strong>{{ selected.performed_by_name }}</strong></p>
      </section>
    </div>
    <div v-else class="empty-state compact"><ShieldAlert :size="28" /><h2>Nenhum equipamento para avaliar</h2><p>Reserve ou registre a devolução antes desta etapa.</p></div>
    <div v-if="error" class="error-message">{{ error }}</div>
    <div class="modal-actions"><button type="button" class="btn secondary" @click="emit('close')">Fechar</button><span class="spacer" /><button v-if="editable && selected" class="btn primary" :disabled="busy" @click="save"><Save :size="17" />{{ busy ? 'Salvando...' : 'Salvar avaliação' }}</button></div>
  </ModalDialog>
</template>
