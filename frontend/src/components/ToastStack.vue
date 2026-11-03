<script setup>
import { Check, AlertCircle, X } from 'lucide-vue-next'
import { notices, dismissNotice } from '../services/notices'
</script>
<template>
  <Teleport to="body"><div class="toast-stack" aria-label="Avisos do sistema"><TransitionGroup name="toast"><section v-for="item in notices" :key="item.id" class="toast-notice" :class="item.type" :role="item.type === 'error' ? 'alert' : 'status'" aria-atomic="true"><component :is="item.type === 'error' ? AlertCircle : Check" :size="19" class="toast-icon"/><div><strong>{{ item.type === 'error' ? 'Não foi possível concluir' : 'Concluído' }}</strong><p>{{ item.message }}</p><router-link v-if="item.action" :to="item.action.to" @click="dismissNotice(item.id)">{{ item.action.label }}</router-link></div><button type="button" class="toast-close" aria-label="Fechar aviso" @click="dismissNotice(item.id)"><X :size="17"/></button></section></TransitionGroup></div></Teleport>
</template>
