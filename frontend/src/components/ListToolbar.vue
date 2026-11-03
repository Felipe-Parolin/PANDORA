<template>
  <header class="list-toolbar list-controls list-toolbar-aligned">
    <div class="list-toolbar-search"><slot name="search" /></div>
    <div class="list-toolbar-filters"><slot name="filters" /></div>
    <div v-if="$slots.meta" class="list-toolbar-meta"><slot name="meta" /></div>
    <div v-if="$slots.more" class="list-toolbar-more"><slot name="more" /></div>
  </header>
</template>
