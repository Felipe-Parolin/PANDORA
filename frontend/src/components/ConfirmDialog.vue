<script setup>
import { AlertTriangle } from 'lucide-vue-next'
import ModalDialog from './ModalDialog.vue'

defineProps({ title: String, message: String, confirmLabel: { type: String, default: 'Excluir' }, busy: Boolean })
defineEmits(['cancel', 'confirm'])
</script>

<template>
  <ModalDialog :title="title || 'Confirmar exclusão'" @close="$emit('cancel')">
    <div class="confirm-content">
      <div class="confirm-icon"><AlertTriangle :size="25" /></div>
      <p>{{ message }}</p>
    </div>
    <div class="modal-actions">
      <button type="button" class="btn secondary" @click="$emit('cancel')">Cancelar</button>
      <span class="spacer" />
      <button type="button" class="btn danger" :disabled="busy" @click="$emit('confirm')">{{ busy ? 'Excluindo...' : confirmLabel }}</button>
    </div>
  </ModalDialog>
</template>
