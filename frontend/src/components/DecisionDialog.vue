<script setup>
import { ref } from 'vue'
import { CheckCircle2 } from 'lucide-vue-next'
import ModalDialog from './ModalDialog.vue'

defineProps({
  title: String,
  message: String,
  confirmLabel: { type: String, default: 'Confirmar' },
  danger: Boolean,
  busy: Boolean,
})
const emit = defineEmits(['cancel', 'confirm'])
const reason = ref('')
</script>

<template>
  <ModalDialog :title="title" @close="emit('cancel')">
    <div class="confirm-content">
      <div class="confirm-icon" :class="{ ok: !danger }"><CheckCircle2 :size="25" /></div>
      <p>{{ message }}</p>
    </div>
    <div class="form-field decision-reason">
      <label for="decision-reason">Observação (opcional)</label>
      <textarea id="decision-reason" v-model="reason" rows="3" maxlength="500" placeholder="Ex.: validar custos com o financeiro antes de decidir" />
    </div>
    <div class="modal-actions">
      <button type="button" class="btn secondary" @click="emit('cancel')">Fechar</button>
      <span class="spacer" />
      <button type="button" class="btn" :class="danger ? 'danger' : 'primary'" :disabled="busy" @click="emit('confirm', reason.trim())">{{ busy ? 'Registrando...' : confirmLabel }}</button>
    </div>
  </ModalDialog>
</template>
