<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { get, post, del } = useApi()

const nodes = ref([])
const exports_ = ref([])
const mounts = ref([])
const diskUsage = ref({})
const loading = ref(true)
const error = ref('')

const showExport = ref(false)
const exportForm = ref({ path: '', clients: '', options: 'rw,sync,no_subtree_check', node: '' })
const exportSubmitting = ref(false)
const exportError = ref('')

const deleteConfirm = ref('')

async function fetchNodes() {
  const health = await get('/health')
  nodes.value = health.nodes || []
}

async function fetchAll() {
  loading.value = true
  error.value = ''
  try {
    await fetchNodes()
    const firstNode = nodes.value[0] || 'spark-1'
    const promises = [
      get('/storage/exports'),
      get(`/storage/mounts?node=${firstNode}`),
      ...nodes.value.map(n => get(`/storage/disk-usage?node=${n}`)),
    ]
    const results = await Promise.all(promises)
    exports_.value = results[0]
    mounts.value = results[1]
    const du = {}
    nodes.value.forEach((n, i) => { du[n] = results[2 + i] })
    diskUsage.value = du
  } catch (e) {
    error.value = e.message || 'Failed to load storage info'
  }
  loading.value = false
}

onMounted(fetchAll)

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let val = bytes
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024
    i++
  }
  return `${val.toFixed(1)} ${units[i]}`
}

function usagePercent(used, total) {
  if (!total || total <= 0) return 0
  return Math.min(100, Math.round((used / total) * 100))
}

function usageBarColor(pct) {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-orange-500'
  return 'bg-nvidia'
}

function openExport() {
  exportForm.value = { path: '', clients: '', options: 'rw,sync,no_subtree_check', node: nodes.value[0] || '' }
  exportError.value = ''
  showExport.value = true
}

async function addExport() {
  if (!exportForm.value.path.trim() || !exportForm.value.clients.trim()) {
    exportError.value = 'Path and clients are required'
    return
  }
  exportSubmitting.value = true
  exportError.value = ''
  try {
    const node = exportForm.value.node || nodes.value[0]
    await post(`/storage/exports?node=${encodeURIComponent(node)}`, {
      path: exportForm.value.path.trim(),
      clients: exportForm.value.clients.trim(),
      options: exportForm.value.options.trim(),
    })
    showExport.value = false
    await fetchAll()
  } catch (e) {
    exportError.value = e.message || 'Failed'
  }
  exportSubmitting.value = false
}

async function removeExport(exp) {
  const key = `${exp.node}:${exp.path}:${exp.clients}`
  if (deleteConfirm.value !== key) {
    deleteConfirm.value = key
    setTimeout(() => { deleteConfirm.value = '' }, 3000)
    return
  }
  try {
    await del(`/storage/exports?path=${encodeURIComponent(exp.path)}&clients=${encodeURIComponent(exp.clients)}&node=${encodeURIComponent(exp.node)}`)
    deleteConfirm.value = ''
    await fetchAll()
  } catch (e) {
    error.value = e.message || 'Delete failed'
  }
}
</script>

<template>
  <div>
    <h2 class="text-2xl font-bold text-gray-100 mb-6">Storage</h2>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading storage info...
    </div>

    <template v-else>
      <!-- NFS Exports -->
      <section class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-200">NFS Exports</h3>
          <button
            @click="openExport"
            class="px-3 py-1.5 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 transition-colors"
          >
            Add Export
          </button>
        </div>

        <div v-if="!exports_.length" class="text-center py-10 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
          <p>No NFS exports configured</p>
        </div>

        <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
                <th class="py-3 px-4 font-medium">Node</th>
                <th class="py-3 px-4 font-medium">Path</th>
                <th class="py-3 px-4 font-medium">Clients</th>
                <th class="py-3 px-4 font-medium">Options</th>
                <th class="py-3 px-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="exp in exports_" :key="`${exp.node}:${exp.path}:${exp.clients}`"
                class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
              >
                <td class="py-3 px-4">
                  <span class="px-2 py-0.5 text-xs rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                    {{ exp.node }}
                  </span>
                </td>
                <td class="py-3 px-4 font-mono text-gray-100">{{ exp.path }}</td>
                <td class="py-3 px-4 text-gray-300">{{ exp.clients }}</td>
                <td class="py-3 px-4 text-gray-400 text-xs font-mono">{{ exp.options }}</td>
                <td class="py-3 px-4 text-right">
                  <button
                    @click="removeExport(exp)"
                    class="px-2.5 py-1 text-xs rounded-md transition-colors"
                    :class="deleteConfirm === `${exp.node}:${exp.path}:${exp.clients}`
                      ? 'bg-red-500 text-white'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                  >
                    {{ deleteConfirm === `${exp.node}:${exp.path}:${exp.clients}` ? 'Confirm?' : 'Delete' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Mounts -->
      <section class="mb-8">
        <h3 class="text-lg font-semibold text-gray-200 mb-4">Mounts</h3>

        <div v-if="!mounts.length" class="text-center py-10 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
          <p>No mounts found</p>
        </div>

        <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
                  <th class="py-3 px-4 font-medium">Device</th>
                  <th class="py-3 px-4 font-medium">Mount Point</th>
                  <th class="py-3 px-4 font-medium">Type</th>
                  <th class="py-3 px-4 font-medium min-w-[200px]">Usage</th>
                  <th class="py-3 px-4 font-medium">Total</th>
                  <th class="py-3 px-4 font-medium">Used</th>
                  <th class="py-3 px-4 font-medium">Free</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in mounts" :key="`${m.device}:${m.mountpoint}`"
                  class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
                >
                  <td class="py-3 px-4 font-mono text-gray-200 text-xs">{{ m.device }}</td>
                  <td class="py-3 px-4 font-mono text-gray-100">{{ m.mountpoint }}</td>
                  <td class="py-3 px-4">
                    <span class="px-2 py-0.5 text-xs rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {{ m.fstype }}
                    </span>
                  </td>
                  <td class="py-3 px-4">
                    <div v-if="m.total > 0" class="space-y-1">
                      <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          class="h-full rounded-full transition-all"
                          :class="usageBarColor(usagePercent(m.used, m.total))"
                          :style="{ width: `${usagePercent(m.used, m.total)}%` }"
                        />
                      </div>
                      <div class="text-xs text-gray-500">{{ usagePercent(m.used, m.total) }}%</div>
                    </div>
                    <span v-else class="text-xs text-gray-600">—</span>
                  </td>
                  <td class="py-3 px-4 text-gray-400 text-xs">{{ formatBytes(m.total) }}</td>
                  <td class="py-3 px-4 text-gray-400 text-xs">{{ formatBytes(m.used) }}</td>
                  <td class="py-3 px-4 text-gray-400 text-xs">{{ formatBytes(m.free) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- Disk Usage -->
      <section>
        <h3 class="text-lg font-semibold text-gray-200 mb-4">Disk Usage</h3>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div v-for="nodeName in nodes" :key="nodeName">
            <h4 class="text-sm font-medium text-gray-400 mb-3">{{ nodeName }}</h4>
            <div v-if="!diskUsage[nodeName]?.length" class="text-center py-8 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <p class="text-sm">No disk data</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="d in diskUsage[nodeName]" :key="`${nodeName}:${d.device}:${d.mountpoint}`"
                class="bg-gray-800 rounded-xl border border-gray-700 p-4"
              >
                <div class="flex items-center justify-between mb-2">
                  <div>
                    <div class="text-sm font-mono text-gray-100">{{ d.mountpoint }}</div>
                    <div class="text-xs text-gray-500 font-mono">{{ d.device }}</div>
                  </div>
                  <div class="text-right">
                    <div class="text-lg font-bold" :class="(d.percent ?? 0) >= 90 ? 'text-red-400' : (d.percent ?? 0) >= 70 ? 'text-orange-400' : 'text-gray-100'">
                      {{ (d.percent ?? 0).toFixed(0) }}%
                    </div>
                    <div class="text-xs text-gray-500">{{ formatBytes(d.used) }} / {{ formatBytes(d.total) }}</div>
                  </div>
                </div>
                <div class="h-2.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="usageBarColor(d.percent)"
                    :style="{ width: `${d.percent}%` }"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- Add Export Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showExport" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showExport = false">
          <div class="w-full max-w-lg bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Add NFS Export</h3>
              <button @click="showExport = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div v-if="exportError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ exportError }}</div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Node</label>
                <select v-model="exportForm.node" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50">
                  <option v-for="n in nodes" :key="n" :value="n">{{ n }}</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Path</label>
                <input v-model="exportForm.path" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500" placeholder="/data/shared" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Clients</label>
                <input v-model="exportForm.clients" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500" placeholder="192.168.1.0/24 or *" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Options</label>
                <input v-model="exportForm.options" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500" placeholder="rw,sync,no_subtree_check" />
              </div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showExport = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="addExport" :disabled="exportSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ exportSubmitting ? 'Adding...' : 'Add Export' }}
              </button>
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
