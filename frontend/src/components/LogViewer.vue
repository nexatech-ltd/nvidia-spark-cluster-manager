<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { useWebSocket } from '../composables/useWebSocket'

const props = defineProps({
  wsUrl: { type: String, required: true },
  title: { type: String, default: 'Logs' },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const MAX_LINES = 5000
const follow = ref(true)
const logEl = ref(null)
const lines = ref([])
let ws = null
let stopWatcher = null

function connectWs() {
  if (stopWatcher) { stopWatcher(); stopWatcher = null }
  if (ws) ws.close()
  ws = useWebSocket(props.wsUrl)
  ws.connect()
  stopWatcher = watch(ws.messages, (msgs) => {
    lines.value = msgs.slice(-MAX_LINES)
    if (follow.value) scrollToBottom()
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function clearLogs() {
  lines.value = []
  if (ws) ws.messages.value = []
}

function handleClose() {
  if (stopWatcher) { stopWatcher(); stopWatcher = null }
  if (ws) ws.close()
  ws = null
  lines.value = []
  emit('close')
}

watch(() => props.visible, (val) => {
  if (val && props.wsUrl) {
    connectWs()
  } else if (!val && ws) {
    if (stopWatcher) { stopWatcher(); stopWatcher = null }
    ws.close()
    ws = null
    lines.value = []
  }
})

onUnmounted(() => {
  if (stopWatcher) stopWatcher()
  if (ws) ws.close()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
        @mousedown.self="handleClose"
      >
        <div class="w-full max-w-6xl h-[85vh] bg-gray-900 rounded-xl border border-gray-700 flex flex-col shadow-2xl">
          <!-- Header -->
          <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
            <div class="flex items-center gap-3">
              <div
                class="w-2.5 h-2.5 rounded-full shrink-0"
                :class="ws?.connected?.value ? 'bg-green-400 shadow-green-400/50 shadow-sm' : 'bg-gray-600'"
              />
              <h3 class="text-sm font-semibold text-gray-100 truncate">{{ title }}</h3>
            </div>
            <div class="flex items-center gap-2">
              <button
                @click="clearLogs"
                class="px-2.5 py-1 text-xs rounded-md bg-gray-800 text-gray-400 hover:text-gray-200 hover:bg-gray-700 border border-gray-600 transition-colors"
              >
                Clear
              </button>
              <button
                @click="follow = !follow"
                class="px-2.5 py-1 text-xs rounded-md border transition-colors"
                :class="follow
                  ? 'bg-green-500/10 text-green-400 border-green-500/30 hover:bg-green-500/20'
                  : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
              >
                Follow {{ follow ? 'ON' : 'OFF' }}
              </button>
              <button
                @click="handleClose"
                class="ml-1 p-1 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Log content -->
          <div
            ref="logEl"
            class="flex-1 overflow-y-auto overflow-x-auto bg-gray-950 font-mono text-xs leading-5 text-gray-300 p-4"
          >
            <pre v-if="lines.length" class="whitespace-pre-wrap break-all">{{ lines.join('') }}</pre>
            <div v-else class="text-gray-600 italic">Waiting for logs...</div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
