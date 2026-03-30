<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  vmName: { type: String, required: true },
  node: { type: String, required: true },
})

const container = ref(null)
const status = ref('disconnected')
const error = ref('')
let rfb = null

function getWsUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/api/vnc/ws/${props.vmName}?node=${props.node}`
}

async function connect() {
  disconnect()
  error.value = ''
  status.value = 'connecting'

  await nextTick()
  if (!container.value) return

  try {
    const mod = await import('@novnc/novnc')
    const RFB = mod.default || mod
    const url = getWsUrl()
    rfb = new RFB(container.value, url)
    rfb.scaleViewport = true
    rfb.resizeSession = true
    rfb.clipViewport = true

    rfb.addEventListener('connect', () => {
      status.value = 'connected'
      error.value = ''
    })
    rfb.addEventListener('disconnect', (e) => {
      status.value = 'disconnected'
      if (e.detail?.clean === false) {
        error.value = 'Connection lost unexpectedly'
      }
      rfb = null
    })
    rfb.addEventListener('credentialsrequired', () => {
      rfb.sendCredentials({ password: '' })
    })
  } catch (e) {
    status.value = 'disconnected'
    error.value = e.message || 'Failed to initialize VNC'
  }
}

function disconnect() {
  if (rfb) {
    rfb.disconnect()
    rfb = null
  }
  status.value = 'disconnected'
}

function sendCtrlAltDel() {
  rfb?.sendCtrlAltDel()
}

function toggleFullscreen() {
  if (!container.value) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    container.value.requestFullscreen()
  }
}

let resizeObserver = null
onMounted(() => {
  connect()
  if (container.value) {
    resizeObserver = new ResizeObserver(() => {
      if (rfb) {
        rfb.scaleViewport = true
      }
    })
    resizeObserver.observe(container.value)
  }
})

onBeforeUnmount(() => {
  disconnect()
  resizeObserver?.disconnect()
})

watch(() => [props.vmName, props.node], () => {
  connect()
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 px-3 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
      <div
        class="w-2.5 h-2.5 rounded-full shrink-0"
        :class="{
          'bg-green-400 shadow-green-400/50 shadow-sm': status === 'connected',
          'bg-yellow-400 shadow-yellow-400/50 shadow-sm animate-pulse': status === 'connecting',
          'bg-gray-600': status === 'disconnected',
        }"
      />
      <span class="text-xs text-gray-400 capitalize">{{ status }}</span>

      <div class="flex-1" />

      <button
        v-if="status === 'disconnected'"
        @click="connect"
        class="px-2.5 py-1 text-xs rounded-md bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
      >
        Connect
      </button>
      <button
        v-if="status === 'connected'"
        @click="disconnect"
        class="px-2.5 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
      >
        Disconnect
      </button>
      <button
        v-if="status === 'connected'"
        @click="sendCtrlAltDel"
        class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        title="Send Ctrl+Alt+Del"
      >
        Ctrl+Alt+Del
      </button>
      <button
        @click="toggleFullscreen"
        class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        title="Toggle fullscreen"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
        </svg>
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="px-3 py-2 bg-red-500/10 border-b border-red-500/30 text-red-400 text-xs flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-2">&times;</button>
    </div>

    <!-- VNC Canvas Container -->
    <div
      ref="container"
      class="flex-1 bg-black overflow-hidden relative min-h-0"
    >
      <div
        v-if="status === 'disconnected' && !error"
        class="absolute inset-0 flex flex-col items-center justify-center text-gray-500 gap-3"
      >
        <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        <span class="text-sm">VNC console disconnected</span>
        <button
          @click="connect"
          class="px-3 py-1.5 text-xs rounded-lg bg-nvidia/10 text-nvidia border border-nvidia/30 hover:bg-nvidia/20 transition-colors"
        >
          Connect
        </button>
      </div>
      <div
        v-if="status === 'connecting'"
        class="absolute inset-0 flex items-center justify-center text-gray-400"
      >
        <svg class="animate-spin h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="text-sm">Connecting...</span>
      </div>
    </div>
  </div>
</template>
