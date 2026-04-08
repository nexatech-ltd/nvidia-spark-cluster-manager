<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { highlightXml } from '../composables/useXmlHighlight'

const router = useRouter()
const { get, post } = useApi()

// ── Option lists (aligned with Proxmox VE) ──────────────────────────────
const MEMORY_PRESETS = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]
const DISK_BUS_OPTIONS = ['virtio', 'scsi', 'sata', 'ide']
const SCSIHW_OPTIONS = [
  { value: 'virtio-scsi-pci', label: 'VirtIO SCSI' },
  { value: 'lsi', label: 'LSI 53C895A' },
  { value: 'megasas', label: 'MegaRAID SAS' },
  { value: 'pvscsi', label: 'VMware PVSCSI' },
]
const NIC_MODEL_OPTIONS = ['virtio', 'e1000e', 'e1000', 'vmxnet3', 'rtl8139']
const VIDEO_OPTIONS = [
  { value: 'virtio', label: 'VirtIO GPU' },
  { value: 'std', label: 'Standard VGA' },
  { value: 'qxl', label: 'QXL (SPICE)' },
  { value: 'cirrus', label: 'Cirrus' },
  { value: 'vmware', label: 'VMware SVGA' },
  { value: 'none', label: 'None (serial)' },
]
const CPU_OPTIONS_ARM = [
  { value: 'host-passthrough', label: 'host (passthrough)' },
  { value: 'max', label: 'max' },
  { value: 'neoverse-n1', label: 'Neoverse N1' },
  { value: 'neoverse-n2', label: 'Neoverse N2' },
  { value: 'neoverse-v1', label: 'Neoverse V1' },
  { value: 'cortex-a76', label: 'Cortex-A76' },
  { value: 'cortex-a72', label: 'Cortex-A72' },
  { value: 'cortex-a57', label: 'Cortex-A57' },
]
const CPU_OPTIONS_X86 = [
  { value: 'host-passthrough', label: 'host (passthrough)' },
  { value: 'host-model', label: 'host-model' },
  { value: 'max', label: 'max' },
  { value: 'x86-64-v3', label: 'x86-64-v3' },
  { value: 'x86-64-v2-AES', label: 'x86-64-v2-AES' },
  { value: 'kvm64', label: 'kvm64' },
  { value: 'qemu64', label: 'qemu64' },
]
const CACHE_OPTIONS = [
  { value: 'none', label: 'None (Direct I/O)' },
  { value: 'writeback', label: 'Write Back' },
  { value: 'writethrough', label: 'Write Through' },
  { value: 'directsync', label: 'Direct Sync' },
  { value: 'unsafe', label: 'Unsafe' },
]
const BIOS_OPTIONS = [
  { value: 'uefi', label: 'OVMF (UEFI)' },
  { value: 'bios', label: 'SeaBIOS' },
]

const nodes = ref([])
const isos = ref([])
const bridges = ref([])
const osVariants = ref([])
const isosLoading = ref(false)
const bridgesLoading = ref(false)
const osVariantsLoading = ref(false)
const submitting = ref(false)
const error = ref('')
const osSearch = ref('')
const osDropdownOpen = ref(false)
const hwFamily = ref('')
const showAdvanced = ref(false)
const previewXml = ref('')
const previewLoading = ref(false)
const useCustomXml = ref(false)
const customXml = ref('')

const virtioWin = ref({ exists: false, path: null, local_size: 0, remote_size: 0, update_available: false })
const virtioWinLoading = ref(false)
const virtioWinDownloading = ref(false)
const attachVirtioWin = ref(false)

const form = ref({
  name: '',
  node: '',
  // CPU (PVE-style: sockets × cores)
  sockets: 1,
  cores: 4,
  cpu_type: 'host-passthrough',
  // Memory
  memory_mb: 4096,
  balloon: null,
  // Disk
  disk_size_gb: 20,
  disk_format: 'qcow2',
  disk_bus: 'virtio',
  cache: 'none',
  discard: 'ignore',
  io_thread: false,
  scsihw: 'virtio-scsi-pci',
  // Network
  nic_model: 'virtio',
  network: '',
  network_type: 'bridge',
  // Media
  iso: '',
  drivers_iso: null,
  // Display
  video: 'virtio',
  // Firmware
  bios: 'uefi',
  machine_type: null,
  tpm: null,
  secure_boot: false,
  // OS
  os_variant: 'generic',
  // Guest features
  agent: true,
  tablet: true,
  onboot: false,
})

const totalVcpus = computed(() => form.value.sockets * form.value.cores)
const cpuOptions = computed(() => CPU_OPTIONS_ARM) // ARM-first, servers are aarch64
const isWindows = computed(() => hwFamily.value === 'windows')

const filteredVariants = computed(() => {
  const q = osSearch.value.toLowerCase()
  if (!q) return osVariants.value
  return osVariants.value.filter(v =>
    v.id.toLowerCase().includes(q) || v.label.toLowerCase().includes(q)
  )
})

async function fetchNodes() {
  try {
    const health = await get('/health')
    nodes.value = health.nodes || []
    if (nodes.value.length && !form.value.node) {
      form.value.node = nodes.value[0]
    }
  } catch { /* ignore */ }
}

async function fetchISOs() {
  isosLoading.value = true
  try {
    isos.value = await get(`/vms/isos/?node=${form.value.node}`)
  } catch { /* ignore */ }
  isosLoading.value = false
}

async function fetchBridges() {
  bridgesLoading.value = true
  try {
    bridges.value = await get(`/vms/bridges/?node=${form.value.node}`)
    if (bridges.value.length && !bridges.value.find(b => b.name === form.value.network)) {
      form.value.network = bridges.value[0].name
      form.value.network_type = bridges.value[0].type || 'bridge'
    }
  } catch { /* ignore */ }
  bridgesLoading.value = false
}

async function fetchOsVariants() {
  osVariantsLoading.value = true
  try {
    osVariants.value = await get(`/vms/os-variants/?node=${form.value.node}`)
  } catch { /* ignore */ }
  osVariantsLoading.value = false
}

watch(() => form.value.node, (val) => {
  if (val) {
    form.value.iso = ''
    fetchISOs()
    fetchBridges()
    fetchOsVariants()
  }
})

watch(() => form.value.network, (val) => {
  const br = bridges.value.find(b => b.name === val)
  if (br) form.value.network_type = br.type || 'bridge'
})

watch(attachVirtioWin, (val) => {
  form.value.drivers_iso = val && virtioWin.value.path ? virtioWin.value.path : null
})

onMounted(async () => {
  await fetchNodes()
  if (form.value.node) {
    fetchISOs()
    fetchBridges()
    fetchOsVariants()
  }
})

async function checkVirtioWin() {
  if (!form.value.node) return
  virtioWinLoading.value = true
  try {
    virtioWin.value = await get(`/vms/virtio-win/?node=${form.value.node}`)
    if (virtioWin.value.exists) {
      attachVirtioWin.value = true
      form.value.drivers_iso = virtioWin.value.path
    }
  } catch { /* ignore */ }
  virtioWinLoading.value = false
}

async function downloadVirtioWin() {
  virtioWinDownloading.value = true
  try {
    const res = await post(`/vms/virtio-win/download?node=${form.value.node}`, {})
    virtioWin.value = { exists: true, path: res.path, local_size: res.size, remote_size: res.size, update_available: false }
    attachVirtioWin.value = true
    form.value.drivers_iso = res.path
  } catch { /* ignore */ }
  virtioWinDownloading.value = false
}

async function selectOsVariant(variant) {
  form.value.os_variant = variant.id
  osDropdownOpen.value = false
  osSearch.value = ''
  try {
    const p = await get(`/vms/hw-profile/?os_variant=${encodeURIComponent(variant.id)}`)
    if (p.disk_bus) form.value.disk_bus = p.disk_bus
    if (p.nic_model) form.value.nic_model = p.nic_model
    if (p.tpm !== undefined) form.value.tpm = p.tpm || null
    if (p.secure_boot !== undefined) form.value.secure_boot = !!p.secure_boot
    if (p.video) form.value.video = p.video
    if (p.scsihw) form.value.scsihw = p.scsihw
    if (p.cache) form.value.cache = p.cache
    if (p.discard) form.value.discard = p.discard
    if (p.balloon !== undefined) form.value.balloon = p.balloon
    hwFamily.value = p.family || ''
    if (p.family === 'windows') {
      checkVirtioWin()
    } else {
      attachVirtioWin.value = false
      form.value.drivers_iso = null
    }
  } catch { /* ignore */ }
}

function setMemoryPreset(mb) {
  form.value.memory_mb = mb
}

async function fetchPreview() {
  if (!form.value.name.trim() || !form.value.node) return
  previewLoading.value = true
  try {
    const payload = { ...form.value }
    if (!payload.iso) payload.iso = null
    if (!payload.drivers_iso) payload.drivers_iso = null
    const res = await post('/vms/preview', payload)
    previewXml.value = res.xml || ''
    customXml.value = res.xml || ''
  } catch (e) {
    previewXml.value = `Error: ${e.message}`
  }
  previewLoading.value = false
}

async function create() {
  error.value = ''
  if (!form.value.name.trim()) {
    error.value = 'VM name is required'
    return
  }
  submitting.value = true
  try {
    const payload = { ...form.value }
    if (!payload.iso) payload.iso = null
    if (!payload.drivers_iso) payload.drivers_iso = null
    if (useCustomXml.value && customXml.value.trim()) {
      payload.custom_xml = customXml.value.trim()
    }
    await post('/vms/', payload)
    router.push('/vms')
  } catch (e) {
    error.value = e.message || 'Failed to create VM'
  }
  submitting.value = false
}

function selectedOsLabel() {
  const v = osVariants.value.find(o => o.id === form.value.os_variant)
  return v ? `${v.id} — ${v.label}` : form.value.os_variant
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
}

// ── XML highlight ───────────────────────────────────────────────────────

const highlightedPreview = computed(() => highlightXml(previewXml.value))
const highlightedCustom = computed(() => highlightXml(customXml.value))

const previewPreRef = ref(null)
const customPreRef = ref(null)
const customTextareaRef = ref(null)

function syncCustomScroll() {
  if (customPreRef.value && customTextareaRef.value) {
    customPreRef.value.scrollTop = customTextareaRef.value.scrollTop
    customPreRef.value.scrollLeft = customTextareaRef.value.scrollLeft
  }
}
</script>

<template>
  <div class="max-w-2xl">
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

    <h2 class="text-2xl font-bold text-gray-100 mb-6">Create Virtual Machine</h2>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
    </div>

    <form @submit.prevent="create" class="space-y-5">
      <!-- ═══ General ═══ -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">VM Name</label>
          <input
            v-model="form.name"
            required
            placeholder="my-vm"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 placeholder-gray-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Node</label>
          <div class="flex gap-2">
            <button
              v-for="n in nodes"
              :key="n"
              type="button"
              @click="form.node = n"
              class="flex-1 px-4 py-2.5 text-sm rounded-lg border transition-colors font-medium"
              :class="form.node === n
                ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
            >
              {{ n }}
            </button>
          </div>
        </div>
      </div>

      <!-- ═══ OS Type ═══ -->
      <div class="grid grid-cols-2 gap-4">
        <div class="relative">
          <label class="block text-sm font-medium text-gray-300 mb-1.5">OS Type</label>
          <button
            type="button"
            @click="osDropdownOpen = !osDropdownOpen"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-left text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 flex items-center justify-between"
          >
            <span class="truncate">{{ selectedOsLabel() }}</span>
            <svg class="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div
            v-if="osDropdownOpen"
            class="absolute z-20 mt-1 w-full bg-gray-800 border border-gray-600 rounded-lg shadow-xl max-h-64 overflow-hidden flex flex-col"
          >
            <input
              v-model="osSearch"
              placeholder="Search..."
              class="px-3 py-2 bg-gray-750 border-b border-gray-600 text-sm text-gray-100 focus:outline-none placeholder-gray-500"
            />
            <ul class="overflow-y-auto max-h-56">
              <li
                v-for="v in filteredVariants"
                :key="v.id"
                @click="selectOsVariant(v)"
                class="px-3 py-1.5 text-sm cursor-pointer transition-colors"
                :class="form.os_variant === v.id
                  ? 'bg-nvidia/10 text-nvidia'
                  : 'text-gray-300 hover:bg-gray-700'"
              >
                <span class="font-medium">{{ v.id }}</span>
                <span class="text-gray-500 ml-1.5 text-xs">{{ v.label }}</span>
              </li>
              <li v-if="!filteredVariants.length" class="px-3 py-2 text-sm text-gray-500">No match</li>
            </ul>
          </div>
          <p v-if="osVariantsLoading" class="text-xs text-gray-500 mt-1">Loading...</p>
        </div>
        <!-- Network Bridge -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Network</label>
          <select
            v-if="bridges.length"
            v-model="form.network"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          >
            <option v-for="br in bridges" :key="br.name" :value="br.name">
              {{ br.name }} ({{ br.type === 'network' ? 'libvirt' : br.state }})
            </option>
          </select>
          <input
            v-else
            v-model="form.network"
            placeholder="e.g. virbr0, br0"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 placeholder-gray-500"
          />
          <p v-if="bridgesLoading" class="text-xs text-gray-500 mt-1">Loading bridges...</p>
        </div>
      </div>

      <!-- ═══ CPU ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">CPU</h3>
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-xs text-gray-400 mb-1">Sockets</label>
            <input
              v-model.number="form.sockets"
              type="number"
              min="1"
              max="4"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Cores</label>
            <input
              v-model.number="form.cores"
              type="number"
              min="1"
              max="72"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            />
          </div>
          <div class="flex items-end pb-0.5">
            <span class="text-sm text-gray-300 font-medium">= {{ totalVcpus }} vCPUs</span>
          </div>
        </div>
        <div class="mt-3">
          <label class="block text-xs text-gray-400 mb-1">Type</label>
          <select v-model="form.cpu_type" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
            <option v-for="c in cpuOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
      </div>

      <!-- ═══ Memory ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Memory</h3>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-xs text-gray-400 mb-1">RAM (MiB)</label>
            <input
              v-model.number="form.memory_mb"
              type="number"
              min="64"
              step="256"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            />
          </div>
          <div class="flex items-end gap-2 pb-0.5">
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" :checked="form.balloon !== 0" @change="form.balloon = $event.target.checked ? null : 0"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">Ballooning</span>
            </label>
          </div>
        </div>
        <div class="flex flex-wrap gap-1.5 mt-2">
          <button
            v-for="preset in MEMORY_PRESETS"
            :key="preset"
            type="button"
            @click="setMemoryPreset(preset)"
            class="px-2 py-0.5 text-xs rounded border transition-colors"
            :class="form.memory_mb === preset
              ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
              : 'bg-gray-800 text-gray-500 border-gray-600 hover:bg-gray-700 hover:text-gray-300'"
          >
            {{ preset >= 1024 ? `${preset / 1024}G` : `${preset}M` }}
          </button>
        </div>
      </div>

      <!-- ═══ Disk ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Hard Disk</h3>
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-xs text-gray-400 mb-1">Size (GB)</label>
            <input
              v-model.number="form.disk_size_gb"
              type="number"
              min="1"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Format</label>
            <div class="flex gap-1.5">
              <button
                v-for="fmt in ['qcow2', 'raw']"
                :key="fmt"
                type="button"
                @click="form.disk_format = fmt"
                class="flex-1 px-2 py-2 text-xs rounded-lg border transition-colors"
                :class="form.disk_format === fmt
                  ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                  : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
              >{{ fmt }}</button>
            </div>
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Bus</label>
            <select v-model="form.disk_bus" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-2 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
              <option v-for="bus in DISK_BUS_OPTIONS" :key="bus" :value="bus">{{ bus }}</option>
            </select>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-4 mt-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">Cache</label>
            <select v-model="form.cache" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
              <option v-for="c in CACHE_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>
          <div v-if="form.disk_bus === 'scsi'" >
            <label class="block text-xs text-gray-400 mb-1">SCSI Controller</label>
            <select v-model="form.scsihw" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
              <option v-for="s in SCSIHW_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </div>
          <div class="flex items-end gap-4 pb-0.5">
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" :checked="form.discard === 'on'" @change="form.discard = $event.target.checked ? 'on' : 'ignore'"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">Discard (TRIM)</span>
            </label>
            <label v-if="form.disk_bus === 'scsi' || form.disk_bus === 'virtio'" class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" v-model="form.io_thread"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">IO Thread</span>
            </label>
          </div>
        </div>
      </div>

      <!-- ═══ Hardware / System ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide">System</h3>
          <span v-if="hwFamily" class="text-xs px-2 py-0.5 rounded border"
            :class="hwFamily === 'windows'
              ? 'bg-blue-500/15 text-blue-400 border-blue-500/30'
              : hwFamily === 'linux'
                ? 'bg-green-500/15 text-green-400 border-green-500/30'
                : 'bg-gray-500/15 text-gray-400 border-gray-500/30'"
          >{{ hwFamily }}</span>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-xs text-gray-400 mb-1">NIC Model</label>
            <div class="flex gap-1.5 flex-wrap">
              <button
                v-for="nic in NIC_MODEL_OPTIONS"
                :key="nic"
                type="button"
                @click="form.nic_model = nic"
                class="px-2 py-1.5 text-xs rounded-lg border transition-colors"
                :class="form.nic_model === nic
                  ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                  : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
              >{{ nic }}</button>
            </div>
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Display</label>
            <select v-model="form.video" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
              <option v-for="v in VIDEO_OPTIONS" :key="v.value" :value="v.value">{{ v.label }}</option>
            </select>
          </div>
        </div>

        <!-- Advanced toggle -->
        <button
          type="button"
          @click="showAdvanced = !showAdvanced"
          class="mt-3 text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
        >
          <svg class="w-3 h-3 transition-transform" :class="showAdvanced ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          Advanced options
        </button>

        <div v-if="showAdvanced" class="mt-3 pt-3 border-t border-gray-700 space-y-3">
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-gray-400 mb-1">BIOS</label>
              <select v-model="form.bios" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50">
                <option v-for="b in BIOS_OPTIONS" :key="b.value" :value="b.value">{{ b.label }}</option>
              </select>
            </div>
            <label class="flex items-center gap-2 cursor-pointer self-end pb-1">
              <input type="checkbox" v-model="form.tpm" :true-value="true" :false-value="null"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">TPM 2.0</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer self-end pb-1">
              <input type="checkbox" v-model="form.secure_boot"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">Secure Boot</span>
            </label>
          </div>
          <div class="grid grid-cols-3 gap-4">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="form.agent"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">QEMU Agent</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="form.tablet"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">USB Tablet</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="form.onboot"
                class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50" />
              <span class="text-xs text-gray-400">Start on Boot</span>
            </label>
          </div>
        </div>

        <p v-if="isWindows" class="text-xs text-amber-400/80 mt-3">Windows: Hyper-V enlightenments enabled, clock set to localtime. Win11 requires TPM + Secure Boot.</p>
      </div>

      <!-- ═══ ISO ═══ -->
      <div>
        <label class="block text-sm font-medium text-gray-300 mb-1.5">
          Boot ISO
          <span class="text-gray-500 font-normal">(optional)</span>
        </label>
        <select
          v-model="form.iso"
          class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
        >
          <option value="">None (import existing disk)</option>
          <option v-for="iso in isos" :key="iso.path" :value="iso.path">
            {{ iso.name }} ({{ formatBytes(iso.size) }}) &mdash; {{ iso.path }}
          </option>
        </select>
        <p v-if="isosLoading" class="text-xs text-gray-500 mt-1">Loading ISOs from {{ form.node }}...</p>
        <p v-else class="text-xs text-gray-500 mt-1">
          Place ISO files in <code class="text-gray-400">/var/lib/libvirt/isos</code> on the node, or upload via File Browser to <code class="text-gray-400">/data/shared*</code>
        </p>
      </div>

      <!-- ═══ VirtIO Drivers for Windows ═══ -->
      <div v-if="isWindows" class="bg-blue-500/5 rounded-lg border border-blue-500/20 p-4">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            <h3 class="text-sm font-medium text-blue-300">VirtIO Drivers (virtio-win.iso)</h3>
          </div>
          <span v-if="virtioWinLoading" class="text-xs text-gray-500">Checking...</span>
        </div>

        <p class="text-xs text-gray-400 mb-3">
          Contains VirtIO disk/network/GPU drivers and QEMU Guest Agent for Windows.
          Required for VirtIO disk bus and optimal performance.
        </p>

        <div v-if="virtioWin.exists" class="space-y-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="attachVirtioWin"
              class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50"
            />
            <span class="text-sm text-gray-200">Attach as second CD-ROM</span>
            <span class="text-xs text-gray-500">({{ formatBytes(virtioWin.local_size) }})</span>
          </label>
          <div v-if="virtioWin.update_available" class="flex items-center gap-2 pl-6">
            <span class="text-xs text-amber-400">New version available ({{ formatBytes(virtioWin.remote_size) }})</span>
            <button
              type="button"
              @click="downloadVirtioWin"
              :disabled="virtioWinDownloading"
              class="px-2 py-0.5 text-xs rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 transition-colors disabled:opacity-50"
            >
              {{ virtioWinDownloading ? 'Downloading...' : 'Update' }}
            </button>
          </div>
        </div>

        <div v-else-if="!virtioWinLoading" class="flex items-center gap-3">
          <span class="text-sm text-gray-400">Not found on {{ form.node }}</span>
          <button
            type="button"
            @click="downloadVirtioWin"
            :disabled="virtioWinDownloading"
            class="px-3 py-1.5 text-xs rounded-lg bg-blue-500/15 text-blue-300 border border-blue-500/30 hover:bg-blue-500/25 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <svg v-if="!virtioWinDownloading" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            <svg v-else class="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ virtioWinDownloading ? 'Downloading (~600 MB)...' : 'Download virtio-win.iso' }}
          </button>
        </div>
      </div>

      <!-- ═══ Summary ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Summary</h3>
        <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <span class="text-gray-500">Name:</span>
          <span class="text-gray-200">{{ form.name || '—' }}</span>
          <span class="text-gray-500">Node:</span>
          <span class="text-gray-200">{{ form.node }}</span>
          <span class="text-gray-500">CPU:</span>
          <span class="text-gray-200">{{ form.sockets }}S × {{ form.cores }}C = {{ totalVcpus }} vCPUs ({{ form.cpu_type }})</span>
          <span class="text-gray-500">Memory:</span>
          <span class="text-gray-200">{{ form.memory_mb >= 1024 ? `${(form.memory_mb / 1024).toFixed(1)} GiB` : `${form.memory_mb} MiB` }}{{ form.balloon === 0 ? ' (no balloon)' : '' }}</span>
          <span class="text-gray-500">Disk:</span>
          <span class="text-gray-200">{{ form.disk_size_gb }} GB {{ form.disk_format }}, {{ form.disk_bus }}{{ form.disk_bus === 'scsi' ? ` (${form.scsihw})` : '' }}, cache={{ form.cache }}{{ form.discard === 'on' ? ', discard' : '' }}</span>
          <span class="text-gray-500">Network:</span>
          <span class="text-gray-200">{{ form.network || '—' }} ({{ form.nic_model }})</span>
          <span class="text-gray-500">Display:</span>
          <span class="text-gray-200">{{ VIDEO_OPTIONS.find(v => v.value === form.video)?.label || form.video }}</span>
          <span class="text-gray-500">ISO:</span>
          <span class="text-gray-200">{{ form.iso ? isos.find(i => i.path === form.iso)?.name || form.iso : 'None' }}</span>
          <template v-if="isWindows && attachVirtioWin && virtioWin.path">
            <span class="text-gray-500">Drivers:</span>
            <span class="text-blue-300">virtio-win.iso</span>
          </template>
          <span class="text-gray-500">OS:</span>
          <span class="text-gray-200">{{ selectedOsLabel() }}</span>
          <span class="text-gray-500">BIOS:</span>
          <span class="text-gray-200">{{ form.bios === 'uefi' ? 'OVMF (UEFI)' : 'SeaBIOS' }}{{ form.tpm ? ' + TPM 2.0' : '' }}{{ form.secure_boot ? ' + Secure Boot' : '' }}</span>
        </div>
      </div>

      <!-- ═══ XML Preview ═══ -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide">Domain XML Preview</h3>
          <button
            type="button"
            @click="fetchPreview"
            :disabled="previewLoading || !form.name"
            class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors disabled:opacity-50"
          >
            {{ previewLoading ? 'Loading...' : 'Generate Preview' }}
          </button>
        </div>
        <div v-if="previewXml" class="mt-2">
          <div v-if="!useCustomXml" class="xml-preview">
            <pre ref="previewPreRef" class="xml-highlight"><code v-html="highlightedPreview + '\n'"></code></pre>
          </div>
          <div v-else class="xml-editor">
            <pre ref="customPreRef" class="xml-highlight" aria-hidden="true"><code v-html="highlightedCustom + '\n'"></code></pre>
            <textarea
              ref="customTextareaRef"
              v-model="customXml"
              @scroll="syncCustomScroll"
              spellcheck="false"
              class="xml-input"
            />
          </div>
          <label class="flex items-center gap-2 mt-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="useCustomXml"
              class="rounded border-gray-600 bg-gray-800 text-nvidia focus:ring-nvidia/50"
            />
            <span class="text-xs text-gray-400">Edit and use custom XML</span>
          </label>
        </div>
        <p v-else class="text-xs text-gray-500 mt-1">Fill in the form and click "Generate Preview" to see the libvirt XML</p>
      </div>

      <!-- ═══ Submit ═══ -->
      <div class="flex items-center gap-3 pt-2">
        <button
          type="submit"
          :disabled="submitting"
          class="px-6 py-2.5 bg-nvidia hover:bg-nvidia-dark text-black font-medium rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          <span v-if="submitting" class="flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Creating...
          </span>
          <span v-else>Create VM</span>
        </button>
        <button
          type="button"
          @click="router.push('/vms')"
          class="px-6 py-2.5 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.xml-preview,
.xml-editor {
  position: relative;
  border-radius: 0.5rem;
  border: 1px solid #374151;
  background: #111827;
  overflow: hidden;
}
.xml-preview {
  max-height: 16rem;
  overflow: auto;
}
.xml-editor {
  height: 20rem;
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
.xml-preview .xml-highlight {
  position: static;
  color: #d1d5db;
}
.xml-editor .xml-highlight {
  pointer-events: none;
  color: #d1d5db;
}
.xml-input {
  color: transparent;
  caret-color: #e5e7eb;
  resize: none;
  -webkit-text-fill-color: transparent;
}
.xml-input::selection { background: rgba(118, 185, 0, 0.3); }
.xml-input::-moz-selection { background: rgba(118, 185, 0, 0.3); }
.xml-highlight :deep(.xb) { color: #6b7280; }
.xml-highlight :deep(.xt) { color: #38bdf8; }
.xml-highlight :deep(.xa) { color: #fbbf24; }
.xml-highlight :deep(.xv) { color: #4ade80; }
.xml-highlight :deep(.xc) { color: #6b7280; font-style: italic; }
.xml-highlight :deep(.xp) { color: #a78bfa; }
</style>
