<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { X } from 'lucide-vue-next'
defineProps({ title: String, wide: Boolean })
const emit = defineEmits(['close'])
const closeOnEscape = event => { if (event.key === 'Escape') emit('close') }
const updateModalLock = delta => {
  const count = Math.max(Number(document.body.dataset.pandoraModalCount || 0) + delta, 0)
  document.body.dataset.pandoraModalCount = String(count)
  document.body.classList.toggle('modal-open', count > 0)
}
onMounted(() => {
  document.addEventListener('keydown', closeOnEscape)
  updateModalLock(1)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', closeOnEscape)
  updateModalLock(-1)
})
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @mousedown.self="$emit('close')">
      <section class="modal" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
        <header><div><span class="eyebrow">PANDORA</span><h2>{{ title }}</h2></div><button class="icon-btn modal-close" aria-label="Fechar janela" @click="$emit('close')"><X :size="20" /></button></header>
        <div class="modal-body"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>
