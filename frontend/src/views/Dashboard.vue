<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { get } = useApi()

const dashboard = ref(null)
const prevDashboard = ref(null)
const loading = ref(true)
const error = ref('')
let refreshTimer = null

async function fetchDashboard() {
  try {
    const data = await get('/system/dashboard/detailed')
    prevDashboard.value = dashboard.value
    dashboard.value = data
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Failed to load dashboard'
  }
  loading.value = false
}

onMounted(() => {
  fetchDashboard()
  refreshTimer = setInterval(fetchDashboard, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const nodes = computed(() => dashboard.value?.nodes ?? [])

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0; let val = bytes
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++ }
  return `${val.toFixed(1)} ${units[i]}`
}

function formatSpeed(mbps) {
  if (!mbps || mbps <= 0) return '—'
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(0)}G`
  return `${mbps}M`
}

function formatRate(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return '0 B/s'
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  let i = 0; let val = bytesPerSec
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++ }
  return `${val.toFixed(1)} ${units[i]}`
}

function cpuTotalPercent(node) {
  const t = node.cpu_total
  if (!t) return 0
  const total = t.user + t.nice + t.system + t.idle + t.iowait + t.irq + t.softirq
  const busy = total - t.idle - t.iowait
  return total > 0 ? Math.round(busy / total * 100) : 0
}

function cpuDeltaPercent(cur, prev) {
  if (!prev) return null
  const curT = cur.cpu_total
  const prevT = prev.cpu_total
  const delta = (k) => (curT[k] || 0) - (prevT[k] || 0)
  const dTotal = delta('user') + delta('nice') + delta('system') + delta('idle') + delta('iowait') + delta('irq') + delta('softirq')
  const dBusy = dTotal - delta('idle') - delta('iowait')
  return dTotal > 0 ? Math.round(dBusy / dTotal * 100) : 0
}

function coreDeltaPercent(curCore, prevCores) {
  if (!prevCores) return null
  const prev = prevCores.find(c => c.core_id === curCore.core_id)
  if (!prev) return null
  const delta = (k) => (curCore[k] || 0) - (prev[k] || 0)
  const dTotal = delta('user') + delta('nice') + delta('system') + delta('idle') + delta('iowait') + delta('irq') + delta('softirq')
  const dBusy = dTotal - delta('idle') - delta('iowait')
  return dTotal > 0 ? Math.round(dBusy / dTotal * 100) : 0
}

function coreGroupUsage(cores, type, prevCores) {
  const group = cores.filter(c => c.core_type === type)
  if (!group.length) return 0
  let totalBusy = 0, totalAll = 0
  for (const c of group) {
    const prev = prevCores?.find(p => p.core_id === c.core_id)
    if (prev) {
      const delta = (k) => (c[k] || 0) - (prev[k] || 0)
      const dTotal = delta('user') + delta('nice') + delta('system') + delta('idle') + delta('iowait') + delta('irq') + delta('softirq')
      const dBusy = dTotal - delta('idle') - delta('iowait')
      totalBusy += dBusy
      totalAll += dTotal
    }
  }
  return totalAll > 0 ? Math.round(totalBusy / totalAll * 100) : 0
}

function prevNodeFor(hostname) {
  return prevDashboard.value?.nodes?.find(n => n.hostname === hostname)
}

function memPercent(node) {
  if (!node.mem_total) return 0
  return Math.round(node.mem_used / node.mem_total * 100)
}

function netRateFor(nodeIdx, ifaceName, direction) {
  const cur = dashboard.value?.nodes?.[nodeIdx]
  const prev = prevDashboard.value?.nodes?.[nodeIdx]
  if (!cur || !prev) return null
  const curIf = cur.net_interfaces.find(n => n.name === ifaceName)
  const prevIf = prev.net_interfaces.find(n => n.name === ifaceName)
  if (!curIf || !prevIf) return null
  const key = direction === 'rx' ? 'rx_bytes' : 'tx_bytes'
  const delta = curIf[key] - prevIf[key]
  return delta >= 0 ? delta / 5 : null  // 5s poll interval
}

function barColor(pct) {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-orange-500'
  return 'bg-nvidia'
}

function tempColor(temp) {
  if (temp >= 80) return 'text-red-400'
  if (temp >= 60) return 'text-orange-400'
  return 'text-green-400'
}

function maxTemp(zones) {
  if (!zones?.length) return null
  return Math.max(...zones.map(z => z.temp_c))
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-bold text-gray-100">DGX Spark Cluster</h2>
        <p class="text-xs text-gray-500 mt-0.5">NVIDIA GB10 Grace Blackwell Superchip</p>
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <div class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        Auto-refresh 5s
      </div>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <!-- Loading Skeleton -->
    <div v-if="loading" class="space-y-4">
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div v-for="i in 2" :key="i" class="bg-gray-800 rounded-xl border border-gray-700 p-6 animate-pulse">
          <div class="h-5 bg-gray-700 rounded w-32 mb-4" />
          <div class="space-y-3">
            <div class="h-3 bg-gray-700 rounded w-full" />
            <div class="h-3 bg-gray-700 rounded w-3/4" />
            <div class="h-3 bg-gray-700 rounded w-5/6" />
            <div class="h-3 bg-gray-700 rounded w-2/3" />
          </div>
        </div>
      </div>
    </div>

    <template v-else-if="dashboard">
      <!-- Quick Stats Row -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        <div class="bg-gray-800 rounded-xl border border-gray-700 px-4 py-3">
          <div class="text-[10px] text-gray-500 uppercase tracking-wider">Docker Stacks</div>
          <div class="text-xl font-bold text-gray-100">{{ dashboard.stacks }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl border border-gray-700 px-4 py-3">
          <div class="text-[10px] text-gray-500 uppercase tracking-wider">Containers</div>
          <div class="text-xl font-bold text-gray-100">{{ dashboard.containers }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl border border-gray-700 px-4 py-3">
          <div class="text-[10px] text-gray-500 uppercase tracking-wider">Virtual Machines</div>
          <div class="text-xl font-bold text-gray-100">{{ dashboard.vms }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl border border-gray-700 px-4 py-3">
          <div class="text-[10px] text-gray-500 uppercase tracking-wider">Slurm Jobs</div>
          <div class="text-xl font-bold text-gray-100">
            <span class="text-green-400">{{ dashboard.slurm_jobs_running }}</span>
            <span class="text-gray-600 text-sm mx-0.5">/</span>
            <span class="text-yellow-400 text-lg">{{ dashboard.slurm_jobs_pending }}</span>
          </div>
        </div>
      </div>

      <!-- Node Cards -->
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div
          v-for="(node, nodeIdx) in nodes" :key="node.hostname"
          class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden"
        >
          <!-- Node Header -->
          <div class="flex items-center justify-between px-5 py-3 border-b border-gray-700 bg-gray-800/80">
            <div class="flex items-center gap-3">
              <div class="w-2.5 h-2.5 rounded-full" :class="node.error ? 'bg-red-400' : 'bg-green-400 shadow-sm shadow-green-400/50'" />
              <h3 class="font-semibold text-gray-100">{{ node.hostname }}</h3>
              <span class="text-[10px] text-gray-500">{{ node.ip }}</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-gray-500">uptime {{ node.uptime }}</span>
              <span v-if="!node.error" class="px-2 py-0.5 text-[10px] rounded-full bg-green-500/10 text-green-400 border border-green-500/20">Online</span>
              <span v-else class="px-2 py-0.5 text-[10px] rounded-full bg-red-500/10 text-red-400 border border-red-500/20">Error</span>
            </div>
          </div>

          <div v-if="node.error" class="p-5 text-red-400 text-sm">{{ node.error }}</div>

          <div v-else class="p-5 space-y-5">
            <!-- CPU Section -->
            <div>
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-medium text-gray-400 uppercase tracking-wider">CPU — ARM big.LITTLE</span>
                <span class="text-xs text-gray-300 font-mono">
                  {{ cpuDeltaPercent(node, prevNodeFor(node.hostname)) ?? cpuTotalPercent(node) }}%
                </span>
              </div>
              <div class="h-2 bg-gray-700 rounded-full overflow-hidden mb-3">
                <div
                  class="h-full rounded-full transition-all duration-700"
                  :class="barColor(cpuDeltaPercent(node, prevNodeFor(node.hostname)) ?? cpuTotalPercent(node))"
                  :style="{ width: `${cpuDeltaPercent(node, prevNodeFor(node.hostname)) ?? cpuTotalPercent(node)}%` }"
                />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <!-- Performance Cores -->
                <div class="bg-gray-900/50 rounded-lg p-3 border border-gray-700/50">
                  <div class="flex items-center justify-between mb-2">
                    <div>
                      <span class="text-xs font-medium text-orange-400">Cortex-X925</span>
                      <span class="text-[10px] text-gray-500 ml-1">Performance</span>
                    </div>
                    <span class="text-xs text-gray-400 font-mono">{{ node.perf_core_count }} cores</span>
                  </div>
                  <div class="flex items-center gap-2 mb-1.5">
                    <span class="text-sm font-bold text-gray-200">
                      {{ coreGroupUsage(node.cpu_cores, 'X925', prevNodeFor(node.hostname)?.cpu_cores) }}%
                    </span>
                    <span class="text-[10px] text-gray-500">
                      {{ node.cpu_cores.filter(c => c.core_type === 'X925')[0]?.freq_mhz ?? '—' }} MHz
                    </span>
                  </div>
                  <div class="flex gap-0.5">
                    <div
                      v-for="core in node.cpu_cores.filter(c => c.core_type === 'X925')"
                      :key="core.core_id"
                      class="flex-1 h-1.5 bg-gray-700 rounded-sm overflow-hidden"
                      :title="`Core ${core.core_id}: ${coreDeltaPercent(core, prevNodeFor(node.hostname)?.cpu_cores) ?? 0}%`"
                    >
                      <div
                        class="h-full rounded-sm bg-orange-400 transition-all duration-700"
                        :style="{ width: `${coreDeltaPercent(core, prevNodeFor(node.hostname)?.cpu_cores) ?? 0}%` }"
                      />
                    </div>
                  </div>
                </div>
                <!-- Efficiency Cores -->
                <div class="bg-gray-900/50 rounded-lg p-3 border border-gray-700/50">
                  <div class="flex items-center justify-between mb-2">
                    <div>
                      <span class="text-xs font-medium text-blue-400">Cortex-A725</span>
                      <span class="text-[10px] text-gray-500 ml-1">Efficiency</span>
                    </div>
                    <span class="text-xs text-gray-400 font-mono">{{ node.eff_core_count }} cores</span>
                  </div>
                  <div class="flex items-center gap-2 mb-1.5">
                    <span class="text-sm font-bold text-gray-200">
                      {{ coreGroupUsage(node.cpu_cores, 'A725', prevNodeFor(node.hostname)?.cpu_cores) }}%
                    </span>
                    <span class="text-[10px] text-gray-500">
                      {{ node.cpu_cores.filter(c => c.core_type === 'A725')[0]?.freq_mhz ?? '—' }} MHz
                    </span>
                  </div>
                  <div class="flex gap-0.5">
                    <div
                      v-for="core in node.cpu_cores.filter(c => c.core_type === 'A725')"
                      :key="core.core_id"
                      class="flex-1 h-1.5 bg-gray-700 rounded-sm overflow-hidden"
                      :title="`Core ${core.core_id}: ${coreDeltaPercent(core, prevNodeFor(node.hostname)?.cpu_cores) ?? 0}%`"
                    >
                      <div
                        class="h-full rounded-sm bg-blue-400 transition-all duration-700"
                        :style="{ width: `${coreDeltaPercent(core, prevNodeFor(node.hostname)?.cpu_cores) ?? 0}%` }"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Unified Memory (URAM) -->
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-xs font-medium text-gray-400 uppercase tracking-wider">Unified Memory (URAM)</span>
                <span class="text-xs text-gray-300">{{ formatBytes(node.mem_used) }} / {{ formatBytes(node.mem_total) }}</span>
              </div>
              <div class="h-2 bg-gray-700 rounded-full overflow-hidden mb-1.5">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="barColor(memPercent(node))"
                  :style="{ width: `${memPercent(node)}%` }"
                />
              </div>
              <div class="flex items-center justify-between text-[10px] text-gray-500">
                <span>{{ memPercent(node) }}% used</span>
                <span>Buffers {{ formatBytes(node.mem_buffers) }} · Cache {{ formatBytes(node.mem_cached) }}</span>
              </div>
              <div class="mt-1 text-[10px] text-gray-600 italic">
                CPU + GPU share unified memory — no separate VRAM
              </div>
            </div>

            <!-- GPU + Temperatures row -->
            <div class="grid grid-cols-2 gap-3">
              <!-- GPU -->
              <div v-if="node.gpu" class="bg-gray-900/50 rounded-lg p-3 border border-nvidia/20">
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-xs font-medium text-nvidia">{{ node.gpu.name }}</span>
                  <span v-if="node.gpu.pstate" class="text-[10px] text-gray-500">{{ node.gpu.pstate }}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 text-center">
                  <div>
                    <div class="text-lg font-bold text-gray-100">{{ node.gpu.utilization != null ? node.gpu.utilization + '%' : '—' }}</div>
                    <div class="text-[10px] text-gray-500">Utilization</div>
                  </div>
                  <div>
                    <div class="text-lg font-bold" :class="node.gpu.temperature != null ? tempColor(node.gpu.temperature) : 'text-gray-500'">
                      {{ node.gpu.temperature != null ? node.gpu.temperature + '°C' : '—' }}
                    </div>
                    <div class="text-[10px] text-gray-500">GPU Temp</div>
                  </div>
                  <div>
                    <div class="text-sm font-bold text-gray-200">{{ node.gpu.power_draw != null ? node.gpu.power_draw.toFixed(1) + 'W' : '—' }}</div>
                    <div class="text-[10px] text-gray-500">Power</div>
                  </div>
                  <div>
                    <div class="text-sm font-bold text-gray-200">{{ node.gpu.clock_mhz ?? '—' }} <span class="text-[10px] text-gray-500">MHz</span></div>
                    <div class="text-[10px] text-gray-500">Clock</div>
                  </div>
                </div>
                <div class="mt-2 text-[10px] text-gray-600">
                  Driver {{ node.gpu.driver_version ?? '—' }} · CUDA 13.0
                </div>
              </div>

              <!-- Temperatures -->
              <div class="bg-gray-900/50 rounded-lg p-3 border border-gray-700/50">
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs font-medium text-gray-400">Temperatures</span>
                  <span
                    v-if="maxTemp(node.thermal_zones) != null"
                    class="text-xs font-bold"
                    :class="tempColor(maxTemp(node.thermal_zones))"
                  >
                    {{ maxTemp(node.thermal_zones).toFixed(0) }}°C max
                  </span>
                </div>
                <div v-if="node.gpu" class="flex items-center justify-between mb-2 pb-2 border-b border-gray-700/50">
                  <span class="text-[10px] text-gray-500">GPU</span>
                  <span class="text-sm font-mono" :class="tempColor(node.gpu.temperature ?? 0)">
                    {{ node.gpu.temperature ?? '—' }}°C
                  </span>
                </div>
                <div class="space-y-1">
                  <div
                    v-for="(tz, idx) in node.thermal_zones"
                    :key="idx"
                    class="flex items-center gap-2"
                  >
                    <span class="text-[10px] text-gray-500 w-14 shrink-0">CPU #{{ idx }}</span>
                    <div class="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        class="h-full rounded-full transition-all duration-500"
                        :class="tz.temp_c >= 80 ? 'bg-red-500' : tz.temp_c >= 60 ? 'bg-orange-400' : 'bg-emerald-400'"
                        :style="{ width: `${Math.min(tz.temp_c, 100)}%` }"
                      />
                    </div>
                    <span class="text-[10px] font-mono w-10 text-right" :class="tempColor(tz.temp_c)">
                      {{ tz.temp_c.toFixed(0) }}°C
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- NVMe Storage -->
            <div v-if="node.nvme">
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-xs font-medium text-gray-400 uppercase tracking-wider">NVMe Storage</span>
                <span class="text-xs text-gray-300">
                  {{ formatBytes(node.nvme.used) }} / {{ formatBytes(node.nvme.total) }}
                </span>
              </div>
              <div class="h-2 bg-gray-700 rounded-full overflow-hidden mb-1">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="barColor(node.nvme.percent)"
                  :style="{ width: `${node.nvme.percent}%` }"
                />
              </div>
              <div class="flex items-center justify-between text-[10px] text-gray-500">
                <span>{{ node.nvme.percent.toFixed(1) }}% used</span>
                <span>{{ formatBytes(node.nvme.free) }} free</span>
              </div>
            </div>

            <!-- Network Interfaces -->
            <div>
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-medium text-gray-400 uppercase tracking-wider">Network</span>
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="ni in node.net_interfaces"
                  :key="ni.name"
                  class="flex items-center gap-3 bg-gray-900/50 rounded-lg px-3 py-2 border border-gray-700/30"
                >
                  <div
                    class="w-1.5 h-1.5 rounded-full shrink-0"
                    :class="ni.state === 'up' ? 'bg-green-400' : 'bg-gray-600'"
                  />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-medium text-gray-200">{{ ni.name }}</span>
                      <span v-if="ni.kind" class="text-[10px] text-gray-500">{{ ni.kind }}</span>
                      <span v-if="ni.speed_mbps && ni.speed_mbps > 0" class="text-[10px] text-gray-500 ml-auto">
                        {{ formatSpeed(ni.speed_mbps) }}
                      </span>
                    </div>
                  </div>
                  <div class="flex items-center gap-3 text-[10px] font-mono shrink-0">
                    <div class="text-right">
                      <div class="text-green-400">
                        <span class="text-gray-600">RX</span>
                        {{ formatRate(netRateFor(nodeIdx, ni.name, 'rx')) }}
                      </div>
                      <div class="text-[9px] text-gray-600">{{ formatBytes(ni.rx_bytes) }}</div>
                    </div>
                    <div class="text-right">
                      <div class="text-blue-400">
                        <span class="text-gray-600">TX</span>
                        {{ formatRate(netRateFor(nodeIdx, ni.name, 'tx')) }}
                      </div>
                      <div class="text-[9px] text-gray-600">{{ formatBytes(ni.tx_bytes) }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="mt-5">
        <h3 class="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Quick Actions</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <button
            @click="router.push('/stacks')"
            class="flex items-center gap-3 bg-gray-800 rounded-xl border border-gray-700 px-4 py-3 hover:bg-gray-700/50 hover:border-gray-600 transition-colors group"
          >
            <div class="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400 group-hover:bg-blue-500/20 transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
            </div>
            <span class="text-sm text-gray-300 group-hover:text-white transition-colors">Deploy Stack</span>
          </button>
          <button
            @click="router.push('/vms/create')"
            class="flex items-center gap-3 bg-gray-800 rounded-xl border border-gray-700 px-4 py-3 hover:bg-gray-700/50 hover:border-gray-600 transition-colors group"
          >
            <div class="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400 group-hover:bg-purple-500/20 transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
            </div>
            <span class="text-sm text-gray-300 group-hover:text-white transition-colors">Create VM</span>
          </button>
          <button
            @click="router.push('/slurm/jobs')"
            class="flex items-center gap-3 bg-gray-800 rounded-xl border border-gray-700 px-4 py-3 hover:bg-gray-700/50 hover:border-gray-600 transition-colors group"
          >
            <div class="w-8 h-8 rounded-lg bg-nvidia/10 flex items-center justify-center text-nvidia group-hover:bg-nvidia/20 transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </div>
            <span class="text-sm text-gray-300 group-hover:text-white transition-colors">Submit Job</span>
          </button>
          <button
            @click="router.push('/files')"
            class="flex items-center gap-3 bg-gray-800 rounded-xl border border-gray-700 px-4 py-3 hover:bg-gray-700/50 hover:border-gray-600 transition-colors group"
          >
            <div class="w-8 h-8 rounded-lg bg-yellow-500/10 flex items-center justify-center text-yellow-400 group-hover:bg-yellow-500/20 transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
            </div>
            <span class="text-sm text-gray-300 group-hover:text-white transition-colors">Browse Files</span>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
