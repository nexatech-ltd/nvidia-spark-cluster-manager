<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const textareaEl = ref(null)

const lineCount = computed(() => {
  const count = (props.modelValue || '').split('\n').length
  return Math.max(count, 1)
})

function onInput(e) {
  emit('update:modelValue', e.target.value)
}

function handleKeydown(e) {
  if (e.key === 'Tab') {
    e.preventDefault()
    const ta = e.target
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const val = props.modelValue
    const newVal = val.substring(0, start) + '  ' + val.substring(end)
    emit('update:modelValue', newVal)
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = start + 2
    })
  }
}
</script>

<template>
  <div class="compose-editor relative rounded-lg border border-gray-600 overflow-hidden bg-gray-950">
    <!-- Line numbers gutter -->
    <div class="absolute top-0 left-0 w-10 h-full bg-gray-900/80 border-r border-gray-700 pointer-events-none z-10 overflow-hidden">
      <div class="py-3 px-1 text-right font-mono text-[11px] leading-[1.625rem] text-gray-600 select-none">
        <div v-for="n in lineCount" :key="n">{{ n }}</div>
      </div>
    </div>
    <textarea
      ref="textareaEl"
      :value="modelValue"
      :readonly="readonly"
      @input="onInput"
      @keydown="handleKeydown"
      class="w-full min-h-[300px] bg-transparent text-gray-200 font-mono text-sm leading-[1.625rem] py-3 pr-4 pl-12 resize-y outline-none focus:ring-1 focus:ring-nvidia/40 placeholder-gray-600"
      :class="{ 'opacity-70 cursor-not-allowed': readonly }"
      spellcheck="false"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      placeholder="version: '3.8'&#10;services:&#10;  web:&#10;    image: nginx:latest&#10;    ports:&#10;      - '80:80'"
    />
  </div>
</template>
