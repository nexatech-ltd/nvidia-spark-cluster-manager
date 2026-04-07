<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import VncConsole from '../components/VncConsole.vue'

const route = useRoute()
const router = useRouter()
const { get, post, put, del } = useApi()

const vmName = computed(() => route.params.name)
const node = computed(() => route.query.node || '')

const vm = ref(null)
const loading = ref(true)
const error = ref('')
const actionLoading = ref('')
const activeTab = ref('console')

const TABS = [
  { id: 'console', label: 'Console', icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z' },
  { id: 'info', label: 'Info', icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'snapshots', label: 'Snapshots', icon: 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z' },
  { id: 'disks', label: 'Disks', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4' },
  { id: 'config', label: 'Config', icon: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4' },
]

const STATE_STYLES = {
  running: 'bg-green-500/15 text-green-400 border-green-500/30',
  shutoff: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  paused: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  crashed: 'bg-red-500/15 text-red-400 border-red-500/30',
  pmsuspended: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

function stateClass(state) {
  return STATE_STYLES[state] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'
}

async function fetchVM() {
  if (!node.value) {
    error.value = 'No node specified. Please navigate from the VMs list.'
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    vm.value = await get(`/vms/${vmName.value}?node=${node.value}`)
  } catch (e) {
    error.value = e.message || 'Failed to load VM'
  }
  loading.value = false
}

onMounted(fetchVM)

async function doAction(action) {
  if (!node.value) return
  actionLoading.value = action
  error.value = ''
  try {
    const payload = { action }
    if (action === 'shutdown') payload.timeout = 60
    await post(`/vms/${vmName.value}/action?node=${node.value}`, payload)
    await fetchVM()
  } catch (e) {
    error.value = e.message || `Action '${action}' failed`
  }
  actionLoading.value = ''
}

// ── Autostart ────────────────────────────────────────────────────────────

const autostartLoading = ref(false)

async function toggleAutostart() {
  if (!vm.value) return
  autostartLoading.value = true
  try {
    await post(`/vms/${vmName.value}/autostart?node=${node.value}`, {
      enabled: !vm.value.autostart,
    })
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to toggle autostart'
  }
  autostartLoading.value = false
}

// ── Snapshots ────────────────────────────────────────────────────────────

const snapshots = ref([])
const snapshotsLoading = ref(false)
const newSnapName = ref('')
const snapActionLoading = ref('')
const snapDeleteConfirm = ref('')

async function fetchSnapshots() {
  if (!node.value) return
  snapshotsLoading.value = true
  try {
    snapshots.value = await get(`/vms/${vmName.value}/snapshots?node=${node.value}`)
  } catch (e) {
    error.value = e.message || 'Failed to load snapshots'
  }
  snapshotsLoading.value = false
}

async function createSnapshot() {
  if (!newSnapName.value.trim()) return
  snapActionLoading.value = 'create'
  try {
    await post(`/vms/${vmName.value}/snapshots?node=${node.value}`, {
      name: newSnapName.value.trim(),
    })
    newSnapName.value = ''
    await fetchSnapshots()
  } catch (e) {
    error.value = e.message || 'Failed to create snapshot'
  }
  snapActionLoading.value = ''
}

async function restoreSnapshot(snapName) {
  snapActionLoading.value = `restore-${snapName}`
  try {
    await post(`/vms/${vmName.value}/snapshots/${snapName}/restore?node=${node.value}`)
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to restore snapshot'
  }
  snapActionLoading.value = ''
}

async function deleteSnapshot(snapName) {
  if (snapDeleteConfirm.value !== snapName) {
    snapDeleteConfirm.value = snapName
    setTimeout(() => { snapDeleteConfirm.value = '' }, 3000)
    return
  }
  snapDeleteConfirm.value = ''
  snapActionLoading.value = `delete-${snapName}`
  try {
    await del(`/vms/${vmName.value}/snapshots/${snapName}?node=${node.value}`)
    await fetchSnapshots()
  } catch (e) {
    error.value = e.message || 'Failed to delete snapshot'
  }
  snapActionLoading.value = ''
}

function formatSnapDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

// ── Disks ────────────────────────────────────────────────────────────────

const poolDisks = ref([])
const pools = ref([])
const selectedPool = ref('default')
const disksLoading = ref(false)
const diskActionLoading = ref('')
const selectedDiskPath = ref('')
const diskDetachConfirm = ref('')

async function fetchPoolDisks() {
  disksLoading.value = true
  try {
    poolDisks.value = await get(`/vms/disks/?pool=${selectedPool.value}&node=${node.value}`)
  } catch (e) {
    error.value = e.message || 'Failed to load disks'
  }
  disksLoading.value = false
}

async function fetchPools() {
  try {
    pools.value = await get(`/vms/pools/?node=${node.value}`)
  } catch { /* ignore */ }
}

async function attachDisk() {
  if (!selectedDiskPath.value) return
  diskActionLoading.value = 'attach'
  try {
    await post(`/vms/${vmName.value}/disks/attach?node=${node.value}`, {
      path: selectedDiskPath.value,
    })
    selectedDiskPath.value = ''
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to attach disk'
  }
  diskActionLoading.value = ''
}

async function detachDisk(diskPath) {
  if (diskDetachConfirm.value !== diskPath) {
    diskDetachConfirm.value = diskPath
    setTimeout(() => { diskDetachConfirm.value = '' }, 3000)
    return
  }
  diskDetachConfirm.value = ''
  diskActionLoading.value = `detach-${diskPath}`
  try {
    await post(`/vms/${vmName.value}/disks/detach?node=${node.value}`, {
      path: diskPath,
    })
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to detach disk'
  }
  diskActionLoading.value = ''
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
}

// ── ISOs ─────────────────────────────────────────────────────────────────

const isos = ref([])
const isosLoading = ref(false)
const selectedIso = ref('')

async function fetchISOs() {
  isosLoading.value = true
  try {
    isos.value = await get(`/vms/isos/?node=${node.value}`)
  } catch { /* ignore */ }
  isosLoading.value = false
}

function currentISO() {
  if (!vm.value) return null
  const cdrom = vm.value.disks.find(d => d.device === 'cdrom')
  return cdrom?.source || null
}

// ── Boot order ───────────────────────────────────────────────────────────

const bootOrder = ref([])
const bootSaving = ref(false)
const cdromLoading = ref('')

const BOOT_LABELS = { hd: 'Hard Disk', cdrom: 'CD-ROM', network: 'Network (PXE)', fd: 'Floppy' }

function initBootOrder() {
  if (vm.value?.boot_order?.length) {
    bootOrder.value = [...vm.value.boot_order]
  }
}

function moveBootDevice(idx, dir) {
  const target = idx + dir
  if (target < 0 || target >= bootOrder.value.length) return
  const arr = [...bootOrder.value]
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
  bootOrder.value = arr
}

async function saveBootOrder() {
  bootSaving.value = true
  try {
    await put(`/vms/${vmName.value}/boot?node=${node.value}`, { order: bootOrder.value })
    await fetchVM()
    initBootOrder()
  } catch (e) {
    error.value = e.message || 'Failed to save boot order'
  }
  bootSaving.value = false
}

async function ejectCdrom() {
  cdromLoading.value = 'eject'
  try {
    await post(`/vms/${vmName.value}/cdrom?node=${node.value}`, { iso: null })
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to eject CDROM'
  }
  cdromLoading.value = ''
}

async function insertCdrom() {
  if (!selectedIso.value) return
  cdromLoading.value = 'insert'
  try {
    await post(`/vms/${vmName.value}/cdrom?node=${node.value}`, { iso: selectedIso.value })
    await fetchVM()
    selectedIso.value = ''
  } catch (e) {
    error.value = e.message || 'Failed to insert ISO'
  }
  cdromLoading.value = ''
}

// ── VM XML config ────────────────────────────────────────────────────────

const vmXml = ref('')
const vmXmlOriginal = ref('')
const xmlLoading = ref(false)
const xmlSaving = ref(false)
const xmlDirty = computed(() => vmXml.value !== vmXmlOriginal.value)
const xmlPreRef = ref(null)
const xmlTextareaRef = ref(null)

function _esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function _hlTag(tag) {
  const m = tag.match(/^(<\/?)(\S+?)((?:\s[\s\S]*?)?)(\/?>)$/)
  if (!m) return _esc(tag)
  const [, open, name, attrs, close] = m
  let r = `<span class="xb">${_esc(open)}</span><span class="xt">${_esc(name)}</span>`
  if (attrs) {
    let last = 0
    const re = /([\w:-]+)\s*=\s*("[^"]*"|'[^']*')/g
    let am
    while ((am = re.exec(attrs)) !== null) {
      if (am.index > last) r += _esc(attrs.slice(last, am.index))
      r += `<span class="xa">${_esc(am[1])}</span>=<span class="xv">${_esc(am[2])}</span>`
      last = am.index + am[0].length
    }
    if (last < attrs.length) r += _esc(attrs.slice(last))
  }
  r += `<span class="xb">${_esc(close)}</span>`
  return r
}

function highlightXml(raw) {
  if (!raw) return ''
  let out = '', i = 0
  const len = raw.length
  while (i < len) {
    if (raw[i] === '<') {
      if (raw.startsWith('<!--', i)) {
        const end = raw.indexOf('-->', i + 4)
        const j = end < 0 ? len : end + 3
        out += `<span class="xc">${_esc(raw.slice(i, j))}</span>`
        i = j
      } else if (raw.startsWith('<?', i)) {
        const end = raw.indexOf('?>', i + 2)
        const j = end < 0 ? len : end + 2
        out += `<span class="xp">${_esc(raw.slice(i, j))}</span>`
        i = j
      } else {
        let j = i + 1, inQ = false, qC = ''
        while (j < len) {
          if (inQ) { if (raw[j] === qC) inQ = false }
          else if (raw[j] === '"' || raw[j] === "'") { inQ = true; qC = raw[j] }
          else if (raw[j] === '>') { j++; break }
          j++
        }
        out += _hlTag(raw.slice(i, j))
        i = j
      }
    } else {
      const next = raw.indexOf('<', i)
      const j = next < 0 ? len : next
      out += _esc(raw.slice(i, j))
      i = j
    }
  }
  return out
}

const highlightedXml = computed(() => highlightXml(vmXml.value))

function syncScroll() {
  if (xmlPreRef.value && xmlTextareaRef.value) {
    xmlPreRef.value.scrollTop = xmlTextareaRef.value.scrollTop
    xmlPreRef.value.scrollLeft = xmlTextareaRef.value.scrollLeft
  }
}

async function fetchXml() {
  xmlLoading.value = true
  try {
    const res = await get(`/vms/${vmName.value}/xml?node=${node.value}`)
    vmXml.value = res.xml || ''
    vmXmlOriginal.value = vmXml.value
  } catch (e) {
    error.value = e.message || 'Failed to load VM XML'
  }
  xmlLoading.value = false
}

async function saveXml() {
  xmlSaving.value = true
  try {
    await put(`/vms/${vmName.value}/xml?node=${node.value}`, { xml: vmXml.value })
    vmXmlOriginal.value = vmXml.value
    await fetchVM()
  } catch (e) {
    error.value = e.message || 'Failed to save VM XML'
  }
  xmlSaving.value = false
}

function resetXml() {
  vmXml.value = vmXmlOriginal.value
}

// ── Tab switching data loads ─────────────────────────────────────────────

watch(activeTab, (tab) => {
  if (tab === 'snapshots') fetchSnapshots()
  if (tab === 'disks') {
    fetchPoolDisks()
    fetchPools()
  }
  if (tab === 'info') {
    fetchISOs()
    initBootOrder()
  }
  if (tab === 'config') fetchXml()
})

const actionButtons = computed(() => {
  if (!vm.value) return []
  const s = vm.value.state
  const btns = []
  if (s !== 'running') btns.push({ action: 'start', label: 'Start', cls: 'bg-green-500/10 text-green-400 border-green-500/20 hover:bg-green-500/20' })
  if (s === 'running') btns.push({ action: 'shutdown', label: 'Shutdown', cls: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20 hover:bg-yellow-500/20' })
  if (s === 'running') btns.push({ action: 'reboot', label: 'Reboot', cls: 'bg-blue-500/10 text-blue-400 border-blue-500/20 hover:bg-blue-500/20' })
  if (s === 'running') btns.push({ action: 'suspend', label: 'Pause', cls: 'bg-purple-500/10 text-purple-400 border-purple-500/20 hover:bg-purple-500/20' })
  if (s === 'paused') btns.push({ action: 'resume', label: 'Resume', cls: 'bg-green-500/10 text-green-400 border-green-500/20 hover:bg-green-500/20' })
  if (s === 'running') btns.push({ action: 'destroy', label: 'Force Stop', cls: 'bg-red-500/10 text-red-400 border-red-500/20 hover:bg-red-500/20' })
  return btns
})
</script>

<template>
  <div>
    <!-- Back nav -->
    <button
      class="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1 transition-colors"
      @click="router.push('/vms')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Back to VMs
    </button>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-gray-400 py-12 justify-center">
      <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading VM...
    </div>

    <!-- Not found -->
    <div v-else-if="!vm" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">⊟</div>
      <p>VM not found</p>
    </div>

    <template v-else>
      <!-- Error -->
      <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
        <span>{{ error }}</span>
        <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
      </div>

      <!-- Header -->
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-5">
        <div class="flex items-center gap-3">
          <h2 class="text-2xl font-bold text-gray-100">{{ vm.name }}</h2>
          <span class="px-2.5 py-0.5 text-xs rounded-full border" :class="stateClass(vm.state)">
            {{ vm.state }}
          </span>
          <span class="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">{{ vm.node }}</span>
        </div>
        <div class="flex items-center gap-1.5 flex-wrap">
          <button
            v-for="btn in actionButtons"
            :key="btn.action"
            @click="doAction(btn.action)"
            :disabled="actionLoading !== ''"
            class="px-2.5 py-1 text-xs rounded-md border transition-colors disabled:opacity-50"
            :class="btn.cls"
          >
            <span v-if="actionLoading === btn.action" class="flex items-center gap-1">
              <svg class="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ btn.label }}...
            </span>
            <span v-else>{{ btn.label }}</span>
          </button>
          <button
            @click="fetchVM"
            class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex gap-1 mb-4 border-b border-gray-700 pb-px overflow-x-auto">
        <button
          v-for="tab in TABS"
          :key="tab.id"
          @click="activeTab = tab.id"
          class="flex items-center gap-1.5 px-3 py-2 text-sm rounded-t-lg transition-colors whitespace-nowrap -mb-px"
          :class="activeTab === tab.id
            ? 'bg-gray-800 text-white border border-gray-700 border-b-gray-800'
            : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 border border-transparent'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="tab.icon" />
          </svg>
          {{ tab.label }}
        </button>
      </div>

      <!-- ═══ Console Tab ═══ -->
      <div v-if="activeTab === 'console'" class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden" style="height: 70vh;">
        <VncConsole
          v-if="vm.state === 'running'"
          :vm-name="vmName"
          :node="node"
        />
        <div v-else class="h-full flex flex-col items-center justify-center text-gray-500 gap-3">
          <svg class="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <p>VM must be running to access console</p>
          <button
            v-if="vm.state === 'shutoff'"
            @click="doAction('start')"
            class="px-3 py-1.5 text-xs rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
          >
            Start VM
          </button>
        </div>
      </div>

      <!-- ═══ Info Tab ═══ -->
      <div v-if="activeTab === 'info'" class="space-y-4">
        <!-- System Info -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
          <h3 class="text-sm font-semibold text-gray-300 mb-4">System Information</h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div class="bg-gray-900/50 rounded-lg p-3">
              <div class="text-xs text-gray-500 mb-1">vCPUs</div>
              <div class="text-lg font-semibold text-gray-100">{{ vm.vcpus }}</div>
            </div>
            <div class="bg-gray-900/50 rounded-lg p-3">
              <div class="text-xs text-gray-500 mb-1">Memory</div>
              <div class="text-lg font-semibold text-gray-100">{{ vm.memory_mb }} MB</div>
            </div>
            <div class="bg-gray-900/50 rounded-lg p-3">
              <div class="text-xs text-gray-500 mb-1">Node</div>
              <div class="text-lg font-semibold text-gray-100">{{ vm.node }}</div>
            </div>
            <div class="bg-gray-900/50 rounded-lg p-3">
              <div class="text-xs text-gray-500 mb-1">VNC Port</div>
              <div class="text-lg font-semibold text-gray-100">{{ vm.vnc_port ?? '—' }}</div>
            </div>
            <div class="bg-gray-900/50 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div class="text-xs text-gray-500 mb-1">Autostart</div>
                <div class="text-lg font-semibold" :class="vm.autostart ? 'text-green-400' : 'text-gray-400'">
                  {{ vm.autostart ? 'Enabled' : 'Disabled' }}
                </div>
              </div>
              <button
                @click="toggleAutostart"
                :disabled="autostartLoading"
                class="relative w-11 h-6 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-nvidia/50 disabled:opacity-50"
                :class="vm.autostart ? 'bg-nvidia' : 'bg-gray-600'"
              >
                <span
                  class="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform"
                  :class="vm.autostart ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </div>
          </div>
        </div>

        <!-- Disk Info -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
          <h3 class="text-sm font-semibold text-gray-300 mb-4">Disks</h3>
          <div v-if="!vm.disks.length" class="text-sm text-gray-500">No disks attached</div>
          <div v-else class="space-y-2">
            <div
              v-for="(disk, i) in vm.disks"
              :key="i"
              class="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3 text-sm"
            >
              <span
                class="px-2 py-0.5 text-xs rounded border shrink-0"
                :class="disk.device === 'cdrom'
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : 'bg-blue-500/15 text-blue-400 border-blue-500/30'"
              >
                {{ disk.device }}
              </span>
              <span class="text-gray-300 font-mono text-xs truncate flex-1" :title="disk.source">
                {{ disk.source || '(empty)' }}
              </span>
              <span class="text-gray-500 text-xs shrink-0">{{ disk.target }} / {{ disk.bus }}</span>
            </div>
          </div>
        </div>

        <!-- Network Interfaces -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
          <h3 class="text-sm font-semibold text-gray-300 mb-4">Network Interfaces</h3>
          <div v-if="!vm.interfaces.length" class="text-sm text-gray-500">No interfaces configured</div>
          <div v-else class="space-y-2">
            <div
              v-for="(iface, i) in vm.interfaces"
              :key="i"
              class="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3 text-sm"
            >
              <span class="px-2 py-0.5 text-xs rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shrink-0">
                {{ iface.type }}
              </span>
              <span class="text-gray-300">{{ iface.source }}</span>
              <span class="text-gray-500 font-mono text-xs">{{ iface.mac }}</span>
              <span v-if="iface.model" class="text-gray-600 text-xs">{{ iface.model }}</span>
            </div>
          </div>
        </div>

        <!-- Boot Order -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-semibold text-gray-300">Boot Order</h3>
            <button
              @click="saveBootOrder"
              :disabled="bootSaving"
              class="px-3 py-1 text-xs rounded-md bg-nvidia/10 text-nvidia border border-nvidia/30 hover:bg-nvidia/20 transition-colors disabled:opacity-50"
            >
              {{ bootSaving ? 'Saving...' : 'Save' }}
            </button>
          </div>
          <div v-if="bootOrder.length" class="space-y-1.5">
            <div
              v-for="(dev, idx) in bootOrder"
              :key="dev"
              class="flex items-center gap-3 bg-gray-900/50 rounded-lg px-3 py-2.5"
            >
              <span class="text-xs text-gray-500 w-5 text-right shrink-0">{{ idx + 1 }}.</span>
              <span
                class="px-2 py-0.5 text-xs rounded border shrink-0"
                :class="dev === 'cdrom'
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : dev === 'hd'
                    ? 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                    : 'bg-gray-500/15 text-gray-400 border-gray-500/30'"
              >{{ dev }}</span>
              <span class="text-sm text-gray-300 flex-1">{{ BOOT_LABELS[dev] || dev }}</span>
              <div class="flex gap-1 shrink-0">
                <button
                  @click="moveBootDevice(idx, -1)"
                  :disabled="idx === 0"
                  class="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                  title="Move up"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/></svg>
                </button>
                <button
                  @click="moveBootDevice(idx, 1)"
                  :disabled="idx === bootOrder.length - 1"
                  class="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                  title="Move down"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                </button>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-500">No boot devices configured</p>
        </div>

        <!-- CD-ROM / ISO -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
          <h3 class="text-sm font-semibold text-gray-300 mb-4">CD-ROM</h3>
          <div class="flex items-center gap-3 text-sm mb-3">
            <span class="text-gray-400 shrink-0">Current:</span>
            <span class="text-gray-200 font-mono text-xs truncate">{{ currentISO() || '(empty)' }}</span>
            <button
              v-if="currentISO()"
              @click="ejectCdrom"
              :disabled="cdromLoading === 'eject'"
              class="ml-auto px-2.5 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50 shrink-0"
            >
              {{ cdromLoading === 'eject' ? 'Ejecting...' : 'Eject' }}
            </button>
          </div>
          <div class="flex items-center gap-2">
            <select
              v-model="selectedIso"
              class="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            >
              <option value="">Select ISO...</option>
              <option v-for="iso in isos" :key="iso.path" :value="iso.path">
                {{ iso.name }} ({{ formatBytes(iso.size) }})
              </option>
            </select>
            <button
              @click="insertCdrom"
              :disabled="!selectedIso || cdromLoading === 'insert'"
              class="px-3 py-2 text-xs rounded-lg bg-nvidia/10 text-nvidia border border-nvidia/30 hover:bg-nvidia/20 transition-colors disabled:opacity-50 shrink-0"
            >
              {{ cdromLoading === 'insert' ? 'Inserting...' : 'Insert' }}
            </button>
          </div>
          <p v-if="isosLoading" class="text-xs text-gray-500 mt-2">Loading ISOs...</p>
        </div>
      </div>

      <!-- ═══ Snapshots Tab ═══ -->
      <div v-if="activeTab === 'snapshots'" class="space-y-4">
        <!-- Create snapshot -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
          <h3 class="text-sm font-semibold text-gray-300 mb-3">Create Snapshot</h3>
          <form @submit.prevent="createSnapshot" class="flex gap-2">
            <input
              v-model="newSnapName"
              required
              placeholder="Snapshot name..."
              class="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
            />
            <button
              type="submit"
              :disabled="snapActionLoading === 'create' || !newSnapName.trim()"
              class="px-4 py-2 text-sm rounded-lg bg-nvidia hover:bg-nvidia-dark text-black font-medium transition-colors disabled:opacity-50"
            >
              {{ snapActionLoading === 'create' ? 'Creating...' : 'Create' }}
            </button>
          </form>
        </div>

        <!-- Snapshot list -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div v-if="snapshotsLoading" class="p-6 flex items-center gap-2 text-gray-400 text-sm">
            <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading snapshots...
          </div>
          <div v-else-if="!snapshots.length" class="p-6 text-center text-gray-500 text-sm">
            No snapshots for this VM
          </div>
          <div v-else class="divide-y divide-gray-700/50">
            <div
              v-for="snap in snapshots"
              :key="snap.name"
              class="flex items-center justify-between px-5 py-3 hover:bg-gray-700/20 transition-colors"
            >
              <div class="min-w-0">
                <div class="text-sm font-medium text-gray-100">{{ snap.name }}</div>
                <div class="text-xs text-gray-500 mt-0.5">
                  {{ formatSnapDate(snap.creation_time) }}
                  <span class="ml-2 px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400">{{ snap.state }}</span>
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0 ml-4">
                <button
                  @click="restoreSnapshot(snap.name)"
                  :disabled="snapActionLoading.startsWith('restore')"
                  class="px-2 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                >
                  {{ snapActionLoading === `restore-${snap.name}` ? 'Restoring...' : 'Restore' }}
                </button>
                <button
                  @click="deleteSnapshot(snap.name)"
                  :disabled="snapActionLoading.startsWith('delete')"
                  class="px-2 py-1 text-xs rounded-md transition-colors disabled:opacity-50"
                  :class="snapDeleteConfirm === snap.name
                    ? 'bg-red-500 text-white'
                    : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                >
                  {{ snapDeleteConfirm === snap.name ? 'Confirm?' : 'Delete' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Disks Tab ═══ -->
      <div v-if="activeTab === 'disks'" class="space-y-4">
        <!-- Attached disks -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
          <h3 class="text-sm font-semibold text-gray-300 mb-3">Attached Disks</h3>
          <div v-if="!vm.disks.length" class="text-sm text-gray-500">No disks attached</div>
          <div v-else class="space-y-2">
            <div
              v-for="(disk, i) in vm.disks"
              :key="i"
              class="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3 text-sm"
            >
              <span
                class="px-2 py-0.5 text-xs rounded border shrink-0"
                :class="disk.device === 'cdrom'
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : 'bg-blue-500/15 text-blue-400 border-blue-500/30'"
              >
                {{ disk.device }}
              </span>
              <span class="text-gray-300 font-mono text-xs truncate flex-1" :title="disk.source">
                {{ disk.source || '(empty)' }}
              </span>
              <span class="text-gray-500 text-xs shrink-0">{{ disk.target }}</span>
              <button
                v-if="disk.device !== 'cdrom' && disk.source"
                @click="detachDisk(disk.source)"
                :disabled="diskActionLoading.startsWith('detach')"
                class="px-2 py-1 text-xs rounded-md transition-colors shrink-0 disabled:opacity-50"
                :class="diskDetachConfirm === disk.source
                  ? 'bg-red-500 text-white'
                  : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
              >
                {{ diskDetachConfirm === disk.source ? 'Confirm?' : 'Detach' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Attach from pool -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
          <h3 class="text-sm font-semibold text-gray-300 mb-3">Attach Disk from Pool</h3>
          <div class="flex flex-col sm:flex-row gap-2 mb-3">
            <select
              v-model="selectedPool"
              @change="fetchPoolDisks"
              class="bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            >
              <option v-for="p in pools" :key="p.name" :value="p.name">{{ p.name }}</option>
              <option v-if="!pools.length" value="default">default</option>
            </select>
            <select
              v-model="selectedDiskPath"
              class="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            >
              <option value="" disabled>Select a disk...</option>
              <option v-for="d in poolDisks" :key="d.path" :value="d.path">
                {{ d.name }} ({{ formatBytes(d.size) }}, {{ d.format }})
              </option>
            </select>
            <button
              @click="attachDisk"
              :disabled="!selectedDiskPath || diskActionLoading === 'attach'"
              class="px-4 py-2 text-sm rounded-lg bg-nvidia hover:bg-nvidia-dark text-black font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
            >
              {{ diskActionLoading === 'attach' ? 'Attaching...' : 'Attach' }}
            </button>
          </div>
          <div v-if="disksLoading" class="text-xs text-gray-500">Loading pool volumes...</div>
        </div>
      </div>

      <!-- ═══ Config Tab ═══ -->
      <div v-if="activeTab === 'config'" class="space-y-4">
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-gray-300">VM XML Configuration</h3>
            <div class="flex items-center gap-2">
              <span v-if="xmlDirty" class="text-xs text-amber-400">Unsaved changes</span>
              <button
                @click="resetXml"
                :disabled="!xmlDirty || xmlSaving"
                class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors disabled:opacity-30"
              >Reset</button>
              <button
                @click="saveXml"
                :disabled="!xmlDirty || xmlSaving"
                class="px-3 py-1 text-xs rounded-md bg-nvidia/10 text-nvidia border border-nvidia/30 hover:bg-nvidia/20 transition-colors disabled:opacity-30"
              >{{ xmlSaving ? 'Saving...' : 'Save & Apply' }}</button>
            </div>
          </div>
          <div v-if="xmlLoading" class="flex items-center gap-2 text-gray-400 text-sm py-8 justify-center">
            <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading XML...
          </div>
          <div v-else class="xml-editor">
            <pre ref="xmlPreRef" class="xml-highlight" aria-hidden="true"><code v-html="highlightedXml + '\n'"></code></pre>
            <textarea
              ref="xmlTextareaRef"
              v-model="vmXml"
              @scroll="syncScroll"
              spellcheck="false"
              class="xml-input"
            />
          </div>
          <p class="text-xs text-gray-500 mt-2">
            Edit the raw libvirt XML definition. Changes are applied via <code class="text-gray-400">virsh define</code>. A running VM will pick up most changes after restart.
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.xml-editor {
  position: relative;
  height: 60vh;
  min-height: 300px;
  border-radius: 0.5rem;
  border: 1px solid #374151;
  background: #111827;
  overflow: hidden;
  resize: vertical;
}
.xml-highlight,
.xml-input {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 0.75rem 1rem;
  font-family: ui-monospace, SFMono-Regular, 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.75rem;
  line-height: 1.625;
  white-space: pre;
  overflow: auto;
  tab-size: 2;
  border: none;
  outline: none;
  background: transparent;
  word-break: normal;
  overflow-wrap: normal;
}
.xml-highlight {
  pointer-events: none;
  color: #d1d5db;
}
.xml-input {
  color: transparent;
  caret-color: #e5e7eb;
  resize: none;
  -webkit-text-fill-color: transparent;
}
.xml-input::selection {
  background: rgba(118, 185, 0, 0.3);
}
.xml-input::-moz-selection {
  background: rgba(118, 185, 0, 0.3);
}
.xml-highlight :deep(.xb) { color: #6b7280; }
.xml-highlight :deep(.xt) { color: #38bdf8; }
.xml-highlight :deep(.xa) { color: #fbbf24; }
.xml-highlight :deep(.xv) { color: #4ade80; }
.xml-highlight :deep(.xc) { color: #6b7280; font-style: italic; }
.xml-highlight :deep(.xp) { color: #a78bfa; }
</style>
