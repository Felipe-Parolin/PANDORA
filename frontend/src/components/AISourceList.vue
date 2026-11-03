<script setup>
import { FileText, Wrench } from 'lucide-vue-next'

defineProps({ sources: { type: Array, default: () => [] }, highlight: { type: String, default: '' }, empty: { type: String, default: 'Nenhuma fonte encontrada nos registros autorizados.' } })
</script>

<template>
  <div class="ai-sources">
    <article v-for="source in sources" :id="`ai-source-${source.id}`" :key="source.id" class="ai-source" :class="{ highlighted: highlight === source.id }">
      <header>
        <span class="ai-source-id">{{ source.id }}</span>
        <component :is="source.kind === 'manual' ? FileText : Wrench" :size="15" />
        <strong>{{ source.kind === 'manual' ? `${source.manual_name} · p. ${source.page}` : source.title }}</strong>
        <small>{{ Math.round(source.relevance * 100) }}% de relevância</small>
      </header>
      <p>{{ source.excerpt }}</p>
      <footer v-if="source.kind === 'service_order'">
        <span>{{ source.type_label }} · {{ source.status_label }} · {{ source.date }}<template v-if="source.same_equipment"> · mesmo equipamento</template></span>
        <router-link :to="source.url">Abrir OS</router-link>
      </footer>
      <footer v-else><span>{{ source.equipment_name || 'Manual' }}</span></footer>
    </article>
    <p v-if="!sources.length" class="ai-empty">{{ empty }}</p>
  </div>
</template>
