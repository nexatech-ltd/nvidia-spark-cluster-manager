<script setup>
import { ref, computed, watch, onMounted, nextTick, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi'
import LogViewer from '../components/LogViewer.vue'

const { get, post } = useApi()

const containers = ref([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')
const statusFilter = ref('all')

const showLogs = ref(false)
const logTitle = ref('')
const logWsUrl = ref('')

const showExec = ref(false)
const execContainer = ref(null)
const execInput = ref('')
const execOutput = ref([])
const execConnected = ref(false)
const execEl = ref(null)
let execSocket = null

const removeConfirm = ref('')

const STATUS_COLORS = {
  running: 'bg-green-500/15 text-green-400 border-green-500/30',
  exited: 'bg-red-500/15 text-red-400 border-red-500/30',
  paused: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  created: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

function statusClass(status) {
  return STATUS_COLORS[status] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'
}

const filteredContainers = computed(() => {
  let result = containers.value
  if (statusFilter.value !== 'all') {
    result = result.filter(c => c.status === statusFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(c => c.name.toLowerCase().includes(q))
  }
  return result
})

async function fetchContainers() {
  loading.value = true
  error.value = ''
  try {
    containers.value = await get('/docker/containers?all=true')
  } catch (e) {
    error.value = e.message || 'Failed to load containers'
  }
  loading.value = false
}

onMounted(fetchContainers)

async function doAction(container, action) {
  if (action === 'remove') {
    if (removeConfirm.value !== container.id) {
      removeConfirm.value = container.id
      setTimeout(() => { removeConfirm.value = '' }, 3000)
      return
    }
    removeConfirm.value = ''
  }
  try {
    await post(`/docker/containers/${container.id}/${action}`)
    await fetchContainers()
  } catch (e) {
    error.value = e.message || `Action '${action}' failed`
  }
}

function openLogs(container) {
  logTitle.value = `Container Logs: ${container.name}`
  logWsUrl.value = `/api/docker/ws/logs/container/${container.id}`
  showLogs.value = true
}

function openExec(container) {
  execContainer.value = container
  execOutput.value = []
  execInput.value = ''
  execConnected.value = false
  showExec.value = true

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  execSocket = new WebSocket(`${protocol}//${location.host}/api/docker/ws/exec/${container.id}`)
  execSocket.binaryType = 'arraybuffer'
  execSocket.onopen = () => { execConnected.value = true }
  execSocket.onclose = () => { execConnected.value = false }
  execSocket.onmessage = (e) => {
    const text = typeof e.data === 'string' ? e.data : new TextDecoder().decode(e.data)
    execOutput.value.push(text)
    if (execOutput.value.length > 5000) {
      execOutput.value = execOutput.value.slice(-4000)
    }
    scrollExec()
  }
}

function sendExecCommand() {
  if (!execInput.value && !execSocket) return
  const cmd = execInput.value + '\n'
  if (execSocket?.readyState === WebSocket.OPEN) {
    execSocket.send(new TextEncoder().encode(cmd))
  }
  execInput.value = ''
}

function scrollExec() {
  nextTick(() => {
    if (execEl.value) execEl.value.scrollTop = execEl.value.scrollHeight
  })
}

function closeExec() {
  if (execSocket) {
    execSocket.close()
    execSocket = null
  }
  showExec.value = false
}

onUnmounted(() => {
  if (execSocket) execSocket.close()
})

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleString()
  } catch {
    return dateStr
  }
}

const statusOptions = ['all', 'running', 'exited', 'paused', 'created']
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Containers</h2>
      <button
        @click="fetchContainers"
        class="px-3 py-1.5 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
      >
        Refresh
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 mb-4">
      <input
        v-model="searchQuery"
        placeholder="Search by name..."
        class="px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500 w-64"
      />
      <div class="flex gap-1">
        <button
          v-for="s in statusOptions"
          :key="s"
          @click="statusFilter = s"
          class="px-3 py-1.5 text-xs rounded-lg border transition-colors capitalize"
          :class="statusFilter === s
            ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
            : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading containers...
    </div>

    <!-- Empty -->
    <div v-else-if="!filteredContainers.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">▣</div>
      <p v-if="containers.length">No containers match your filters</p>
      <p v-else>No containers found</p>
    </div>

    <!-- Containers table -->
    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
              <th class="py-3 px-4 font-medium">Name</th>
              <th class="py-3 px-4 font-medium">Image</th>
              <th class="py-3 px-4 font-medium">Status</th>
              <th class="py-3 px-4 font-medium">Node</th>
              <th class="py-3 px-4 font-medium">Ports</th>
              <th class="py-3 px-4 font-medium">Created</th>
              <th class="py-3 px-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in filteredContainers"
              :key="c.id"
              class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
            >
              <td class="py-3 px-4 font-medium text-gray-100 whitespace-nowrap">{{ c.name }}</td>
              <td class="py-3 px-4 text-gray-400 font-mono text-xs truncate max-w-[200px]" :title="c.image">
                {{ c.image }}
              </td>
              <td class="py-3 px-4">
                <span
                  class="px-2 py-0.5 text-xs rounded-full border"
                  :class="statusClass(c.status)"
                >
                  {{ c.status }}
                </span>
              </td>
              <td class="py-3 px-4 text-gray-400 text-xs">{{ c.node }}</td>
              <td class="py-3 px-4 text-xs">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="p in c.ports"
                    :key="p"
                    class="px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400 font-mono"
                  >
                    {{ p }}
                  </span>
                  <span v-if="!c.ports.length" class="text-gray-600">—</span>
                </div>
              </td>
              <td class="py-3 px-4 text-gray-500 text-xs whitespace-nowrap">{{ formatDate(c.created) }}</td>
              <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end gap-1 flex-wrap">
                  <button
                    v-if="c.status !== 'running'"
                    @click="doAction(c, 'start')"
                    class="px-2 py-1 text-xs rounded-md bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
                  >
                    Start
                  </button>
                  <button
                    v-if="c.status === 'running'"
                    @click="doAction(c, 'stop')"
                    class="px-2 py-1 text-xs rounded-md bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 hover:bg-yellow-500/20 transition-colors"
                  >
                    Stop
                  </button>
                  <button
                    v-if="c.status === 'running'"
                    @click="doAction(c, 'restart')"
                    class="px-2 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                  >
                    Restart
                  </button>
                  <button
                    @click="openLogs(c)"
                    class="px-2 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
                  >
                    Logs
                  </button>
                  <button
                    v-if="c.status === 'running'"
                    @click="openExec(c)"
                    class="px-2 py-1 text-xs rounded-md bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors"
                  >
                    Exec
                  </button>
                  <button
                    @click="doAction(c, 'remove')"
                    class="px-2 py-1 text-xs rounded-md transition-colors"
                    :class="removeConfirm === c.id
                      ? 'bg-red-500 text-white'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                  >
                    {{ removeConfirm === c.id ? 'Confirm?' : 'Remove' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Log Viewer -->
    <LogViewer
      :wsUrl="logWsUrl"
      :title="logTitle"
      :visible="showLogs"
      @close="showLogs = false"
    />

    <!-- Exec Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showExec" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="closeExec">
          <div class="w-full max-w-4xl h-[80vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
              <div class="flex items-center gap-3">
                <div
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :class="execConnected ? 'bg-green-400 shadow-green-400/50 shadow-sm' : 'bg-gray-600'"
                />
                <h3 class="text-sm font-semibold text-gray-100">
                  Terminal: {{ execContainer?.name }}
                </h3>
              </div>
              <button
                @click="closeExec"
                class="p-1 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div
              ref="execEl"
              class="flex-1 overflow-y-auto bg-gray-950 font-mono text-xs leading-5 text-green-400 p-4"
            >
              <pre v-if="execOutput.length" class="whitespace-pre-wrap break-all">{{ execOutput.join('') }}</pre>
              <div v-else class="text-gray-600 italic">Connecting to shell...</div>
            </div>

            <div class="border-t border-gray-700 px-4 py-3 shrink-0">
              <div class="flex items-center gap-2">
                <span class="text-green-400 font-mono text-sm shrink-0">$</span>
                <input
                  v-model="execInput"
                  @keydown.enter="sendExecCommand"
                  class="flex-1 bg-transparent text-gray-100 font-mono text-sm outline-none placeholder-gray-600"
                  placeholder="Type a command..."
                  autofocus
                />
                <button
                  @click="sendExecCommand"
                  class="px-3 py-1 text-xs rounded-md bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
