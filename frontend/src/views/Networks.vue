<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi'

const { get, post, del } = useApi()

const activeTab = ref('spark-1')
const tabs = ['spark-1', 'spark-2', 'CX7 Interconnect', 'Topology']

const interfaces = ref([])
const topology = ref(null)
const loading = ref(true)
const error = ref('')

const expandedIface = ref('')

const showBridge = ref(false)
const bridgeName = ref('')
const bridgeCreating = ref(false)
const bridgeError = ref('')

const showVlan = ref(false)
const vlanParent = ref('')
const vlanId = ref(100)
const vlanCreating = ref(false)
const vlanError = ref('')

const showPort = ref(false)
const portBridge = ref('')
const portIface = ref('')
const portAction = ref('add')
const portSubmitting = ref(false)
const portError = ref('')

const ipIface = ref('')
const ipAddress = ref('')
const ipAction = ref('add')
const ipSubmitting = ref(false)

async function fetchInterfaces() {
  if (activeTab.value === 'Topology' || activeTab.value === 'CX7 Interconnect') return
  loading.value = true
  error.value = ''
  try {
    interfaces.value = await get(`/network/interfaces?node=${activeTab.value}`)
  } catch (e) {
    error.value = e.message || 'Failed to load interfaces'
  }
  loading.value = false
}

async function fetchTopology() {
  loading.value = true
  error.value = ''
  try {
    topology.value = await get('/network/topology')
  } catch (e) {
    error.value = e.message || 'Failed to load topology'
  }
  loading.value = false
}

onMounted(() => fetchInterfaces())

watch(activeTab, () => {
  expandedIface.value = ''
  if (activeTab.value === 'CX7 Interconnect') {
    loading.value = false
  } else if (activeTab.value === 'Topology') {
    fetchTopology()
  } else {
    fetchInterfaces()
  }
})

function stateColor(state) {
  return state === 'UP' ? 'text-green-400' : 'text-red-400'
}

function stateDot(state) {
  return state === 'UP' ? 'bg-green-400' : 'bg-red-400'
}

function typeBadge(type) {
  const map = {
    bridge: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    bond: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    vlan: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    ethernet: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  }
  return map[type] ?? 'bg-gray-500/10 text-gray-400 border-gray-500/20'
}

function toggleExpand(name) {
  expandedIface.value = expandedIface.value === name ? '' : name
}

const bridges = computed(() => interfaces.value.filter(i => i.type === 'bridge'))
const ethernetIfaces = computed(() => interfaces.value.filter(i => i.type === 'ethernet' || i.type === ''))

async function createBridge() {
  if (!bridgeName.value.trim()) { bridgeError.value = 'Name required'; return }
  bridgeCreating.value = true
  bridgeError.value = ''
  try {
    await post('/network/bridges', { name: bridgeName.value.trim(), node: activeTab.value })
    showBridge.value = false
    bridgeName.value = ''
    await fetchInterfaces()
  } catch (e) {
    bridgeError.value = e.message || 'Failed'
  }
  bridgeCreating.value = false
}

async function deleteBridge(name) {
  if (!confirm(`Delete bridge ${name}?`)) return
  try {
    await del(`/network/bridges/${name}?node=${activeTab.value}`)
    await fetchInterfaces()
  } catch (e) {
    error.value = e.message || 'Delete failed'
  }
}

async function createVlan() {
  if (!vlanParent.value) { vlanError.value = 'Select parent'; return }
  vlanCreating.value = true
  vlanError.value = ''
  try {
    await post('/network/vlans', { parent: vlanParent.value, vlan_id: vlanId.value, node: activeTab.value })
    showVlan.value = false
    await fetchInterfaces()
  } catch (e) {
    vlanError.value = e.message || 'Failed'
  }
  vlanCreating.value = false
}

async function manageBridgePort() {
  if (!portBridge.value || !portIface.value) { portError.value = 'Select bridge and interface'; return }
  portSubmitting.value = true
  portError.value = ''
  try {
    await post('/network/bridges/ports', {
      bridge: portBridge.value,
      port: portIface.value,
      action: portAction.value,
      node: activeTab.value,
    })
    showPort.value = false
    await fetchInterfaces()
  } catch (e) {
    portError.value = e.message || 'Failed'
  }
  portSubmitting.value = false
}

async function handleIpAction(ifaceName) {
  if (!ipAddress.value.trim()) return
  ipSubmitting.value = true
  try {
    await post('/network/addresses', {
      interface: ifaceName,
      address: ipAddress.value.trim(),
      action: ipAction.value,
      node: activeTab.value,
    })
    ipAddress.value = ''
    await fetchInterfaces()
  } catch (e) {
    error.value = e.message || 'IP action failed'
  }
  ipSubmitting.value = false
}

async function removeAddress(ifaceName, addr) {
  try {
    await post('/network/addresses', {
      interface: ifaceName,
      address: addr,
      action: 'remove',
      node: activeTab.value,
    })
    await fetchInterfaces()
  } catch (e) {
    error.value = e.message || 'Remove failed'
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Network</h2>
      <div v-if="activeTab !== 'Topology' && activeTab !== 'CX7 Interconnect'" class="flex items-center gap-2">
        <button
          @click="showBridge = true"
          class="px-3 py-1.5 text-sm rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors"
        >
          Create Bridge
        </button>
        <button
          @click="showVlan = true"
          class="px-3 py-1.5 text-sm rounded-lg bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 hover:bg-yellow-500/20 transition-colors"
        >
          Create VLAN
        </button>
        <button
          @click="showPort = true"
          class="px-3 py-1.5 text-sm rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
        >
          Bridge Ports
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex items-center gap-1 mb-6 bg-gray-800 rounded-lg p-1 w-fit border border-gray-700">
      <button
        v-for="tab in tabs" :key="tab"
        @click="activeTab = tab"
        class="px-4 py-1.5 text-sm rounded-md transition-colors"
        :class="activeTab === tab
          ? 'bg-gray-700 text-white font-medium'
          : 'text-gray-400 hover:text-gray-200'"
      >
        {{ tab }}
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading...
    </div>

    <!-- Interfaces -->
    <template v-else-if="activeTab !== 'Topology' && activeTab !== 'CX7 Interconnect'">
      <div v-if="!interfaces.length" class="text-center py-16 text-gray-500">
        <div class="text-4xl mb-3">⇄</div>
        <p>No interfaces found</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="iface in interfaces" :key="iface.name"
          class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden transition-all"
        >
          <!-- Interface header -->
          <div
            class="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-700/30 transition-colors"
            @click="toggleExpand(iface.name)"
          >
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full" :class="stateDot(iface.state)" />
              <span class="font-mono font-semibold text-gray-100">{{ iface.name }}</span>
              <span
                v-if="iface.type"
                class="px-2 py-0.5 text-xs rounded-full border"
                :class="typeBadge(iface.type)"
              >
                {{ iface.type }}
              </span>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs" :class="stateColor(iface.state)">{{ iface.state }}</span>
              <svg
                class="w-4 h-4 text-gray-500 transition-transform"
                :class="expandedIface === iface.name ? 'rotate-180' : ''"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>

          <!-- Interface details -->
          <div class="px-4 pb-3 space-y-2">
            <div class="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-400">
              <span>MAC: <span class="text-gray-300 font-mono">{{ iface.mac }}</span></span>
              <span>MTU: <span class="text-gray-300">{{ iface.mtu }}</span></span>
              <span v-if="iface.master">Master: <span class="text-gray-300 font-mono">{{ iface.master }}</span></span>
            </div>
            <div v-if="iface.addresses?.length" class="space-y-1">
              <div
                v-for="addr in iface.addresses" :key="addr"
                class="flex items-center gap-2"
              >
                <span class="text-sm font-mono text-green-400">{{ addr }}</span>
                <button
                  v-if="expandedIface === iface.name"
                  @click.stop="removeAddress(iface.name, addr)"
                  class="text-xs text-red-400 hover:text-red-300 transition-colors"
                >
                  remove
                </button>
              </div>
            </div>
            <div v-else class="text-xs text-gray-500 italic">No IP addresses</div>
          </div>

          <!-- Expanded: add IP, delete bridge -->
          <div
            v-if="expandedIface === iface.name"
            class="px-4 py-3 border-t border-gray-700 space-y-3"
          >
            <div class="flex items-center gap-2">
              <input
                v-model="ipAddress"
                @click.stop
                class="flex-1 px-3 py-1.5 rounded-md bg-gray-900 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                placeholder="192.168.1.100/24"
              />
              <button
                @click.stop="handleIpAction(iface.name)"
                :disabled="ipSubmitting"
                class="px-3 py-1.5 text-xs rounded-md bg-nvidia/10 text-nvidia border border-nvidia/20 hover:bg-nvidia/20 transition-colors disabled:opacity-50"
              >
                Add IP
              </button>
            </div>
            <button
              v-if="iface.type === 'bridge'"
              @click.stop="deleteBridge(iface.name)"
              class="text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              Delete Bridge
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- CX7 Interconnect -->
    <template v-else-if="activeTab === 'CX7 Interconnect'">
      <div class="space-y-6">

        <!-- SVG Diagram -->
        <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
          <h3 class="text-white font-semibold mb-4">ConnectX-7 NIC Architecture &amp; Cluster Interconnect</h3>
          <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
            <svg viewBox="0 0 960 530" class="w-full mx-auto" style="min-width: 700px;" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <marker id="arrDown" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6" fill="none" stroke="#f59e0b" stroke-width="1"/>
                </marker>
                <marker id="arrRight" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6" fill="none" stroke="#6b7280" stroke-width="1"/>
                </marker>
              </defs>

              <!-- ============ spark-1 (left) ============ -->
              <rect x="10" y="10" width="420" height="415" rx="12" fill="none" stroke="#374151" stroke-width="1.5"/>
              <text x="220" y="36" text-anchor="middle" fill="#e5e7eb" font-size="14" font-weight="600" font-family="system-ui,sans-serif">spark-1</text>
              <text x="220" y="52" text-anchor="middle" fill="#6b7280" font-size="9" font-family="monospace">10.10.10.1 · 192.168.255.2</text>

              <!-- Grace CPU -->
              <rect x="40" y="64" width="360" height="34" rx="6" fill="#76b900" fill-opacity="0.07" stroke="#76b900" stroke-width="0.8" stroke-opacity="0.35"/>
              <text x="220" y="86" text-anchor="middle" fill="#76b900" font-size="11" font-weight="600" font-family="system-ui,sans-serif">NVIDIA Grace ARM CPU</text>

              <!-- PCIe lane 1 (to NIC#1) -->
              <line x1="130" y1="98" x2="130" y2="140" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" marker-end="url(#arrDown)"/>
              <text x="130" y="116" text-anchor="middle" fill="#f59e0b" font-size="7.5" font-family="monospace">PCIe Gen5 ×4</text>
              <text x="130" y="126" text-anchor="middle" fill="#92400e" font-size="7" font-family="monospace">~126 Gbps/dir</text>

              <!-- PCIe lane 2 (to NIC#2) -->
              <line x1="310" y1="98" x2="310" y2="140" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" marker-end="url(#arrDown)"/>
              <text x="310" y="116" text-anchor="middle" fill="#f59e0b" font-size="7.5" font-family="monospace">PCIe Gen5 ×4</text>
              <text x="310" y="126" text-anchor="middle" fill="#92400e" font-size="7" font-family="monospace">~126 Gbps/dir</text>

              <!-- CX7 NIC #1 -->
              <rect x="35" y="146" width="190" height="132" rx="8" fill="#3b82f6" fill-opacity="0.05" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="130" y="164" text-anchor="middle" fill="#3b82f6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">ConnectX-7 #1</text>
              <text x="130" y="177" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="monospace">PCIe 0000:01:00</text>
              <text x="130" y="190" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="system-ui,sans-serif">QSFP56 Port A · 8 SerDes lanes</text>
              <text x="130" y="202" text-anchor="middle" fill="#6b7280" font-size="7" font-family="system-ui,sans-serif">firmware split → 2 × 4 lanes</text>

              <!-- NIC#1 sub-port p0 -->
              <rect x="42" y="210" width="88" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="86" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7.5" font-weight="500" font-family="monospace">enp1s0f0np0</text>
              <text x="86" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p0</text>
              <text x="86" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="86" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: rocep1s0f0</text>

              <!-- NIC#1 sub-port p1 -->
              <rect x="136" y="210" width="82" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="177" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7.5" font-weight="500" font-family="monospace">enp1s0f1np1</text>
              <text x="177" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p1</text>
              <text x="177" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="177" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: rocep1s0f1</text>

              <!-- CX7 NIC #2 -->
              <rect x="235" y="146" width="190" height="132" rx="8" fill="#3b82f6" fill-opacity="0.05" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="330" y="164" text-anchor="middle" fill="#3b82f6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">ConnectX-7 #2</text>
              <text x="330" y="177" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="monospace">PCIe 0002:01:00</text>
              <text x="330" y="190" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="system-ui,sans-serif">QSFP56 Port B · 8 SerDes lanes</text>
              <text x="330" y="202" text-anchor="middle" fill="#6b7280" font-size="7" font-family="system-ui,sans-serif">firmware split → 2 × 4 lanes</text>

              <!-- NIC#2 sub-port p0 -->
              <rect x="242" y="210" width="88" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="286" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7" font-weight="500" font-family="monospace">enP2p1s0f0np0</text>
              <text x="286" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p0</text>
              <text x="286" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="286" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: roceP2p1s0f0</text>

              <!-- NIC#2 sub-port p1 -->
              <rect x="336" y="210" width="82" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="377" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7" font-weight="500" font-family="monospace">enP2p1s0f1np1</text>
              <text x="377" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p1</text>
              <text x="377" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="377" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: roceP2p1s0f1</text>

              <!-- Bond bar spark-1 -->
              <rect x="35" y="290" width="390" height="46" rx="6" fill="#8b5cf6" fill-opacity="0.06" stroke="#8b5cf6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="230" y="310" text-anchor="middle" fill="#8b5cf6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">bond0</text>
              <text x="230" y="324" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="monospace">balance-xor · layer2 · 4 slaves · 800G reported</text>

              <!-- Lines from sub-ports to bond -->
              <line x1="86" y1="268" x2="86" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="177" y1="268" x2="177" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="286" y1="268" x2="286" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="377" y1="268" x2="377" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>

              <!-- Management port spark-1 -->
              <rect x="35" y="350" width="170" height="36" rx="5" fill="#6b7280" fill-opacity="0.06" stroke="#4b5563" stroke-width="0.7"/>
              <text x="120" y="367" text-anchor="middle" fill="#9ca3af" font-size="8" font-weight="500" font-family="monospace">enP7s7</text>
              <text x="120" y="380" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">Realtek r8127 · 1 GbE</text>

              <!-- ============ spark-2 (right) ============ -->
              <rect x="530" y="10" width="420" height="415" rx="12" fill="none" stroke="#374151" stroke-width="1.5"/>
              <text x="740" y="36" text-anchor="middle" fill="#e5e7eb" font-size="14" font-weight="600" font-family="system-ui,sans-serif">spark-2</text>
              <text x="740" y="52" text-anchor="middle" fill="#6b7280" font-size="9" font-family="monospace">10.10.10.2 · 192.168.255.3</text>

              <!-- Grace CPU -->
              <rect x="560" y="64" width="360" height="34" rx="6" fill="#76b900" fill-opacity="0.07" stroke="#76b900" stroke-width="0.8" stroke-opacity="0.35"/>
              <text x="740" y="86" text-anchor="middle" fill="#76b900" font-size="11" font-weight="600" font-family="system-ui,sans-serif">NVIDIA Grace ARM CPU</text>

              <!-- PCIe lanes for spark-2 -->
              <line x1="650" y1="98" x2="650" y2="140" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" marker-end="url(#arrDown)"/>
              <text x="650" y="116" text-anchor="middle" fill="#f59e0b" font-size="7.5" font-family="monospace">PCIe Gen5 ×4</text>
              <text x="650" y="126" text-anchor="middle" fill="#92400e" font-size="7" font-family="monospace">~126 Gbps/dir</text>

              <line x1="830" y1="98" x2="830" y2="140" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" marker-end="url(#arrDown)"/>
              <text x="830" y="116" text-anchor="middle" fill="#f59e0b" font-size="7.5" font-family="monospace">PCIe Gen5 ×4</text>
              <text x="830" y="126" text-anchor="middle" fill="#92400e" font-size="7" font-family="monospace">~126 Gbps/dir</text>

              <!-- CX7 NIC #1 spark-2 -->
              <rect x="555" y="146" width="190" height="132" rx="8" fill="#3b82f6" fill-opacity="0.05" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="650" y="164" text-anchor="middle" fill="#3b82f6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">ConnectX-7 #1</text>
              <text x="650" y="177" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="monospace">PCIe 0000:01:00</text>
              <text x="650" y="190" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="system-ui,sans-serif">QSFP56 Port A · 8 SerDes lanes</text>
              <text x="650" y="202" text-anchor="middle" fill="#6b7280" font-size="7" font-family="system-ui,sans-serif">firmware split → 2 × 4 lanes</text>

              <rect x="562" y="210" width="88" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="606" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7.5" font-weight="500" font-family="monospace">enp1s0f0np0</text>
              <text x="606" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p0</text>
              <text x="606" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="606" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: rocep1s0f0</text>

              <rect x="656" y="210" width="82" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="697" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7.5" font-weight="500" font-family="monospace">enp1s0f1np1</text>
              <text x="697" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p1</text>
              <text x="697" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="697" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: rocep1s0f1</text>

              <!-- CX7 NIC #2 spark-2 -->
              <rect x="755" y="146" width="190" height="132" rx="8" fill="#3b82f6" fill-opacity="0.05" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="850" y="164" text-anchor="middle" fill="#3b82f6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">ConnectX-7 #2</text>
              <text x="850" y="177" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="monospace">PCIe 0002:01:00</text>
              <text x="850" y="190" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="system-ui,sans-serif">QSFP56 Port B · 8 SerDes lanes</text>
              <text x="850" y="202" text-anchor="middle" fill="#6b7280" font-size="7" font-family="system-ui,sans-serif">firmware split → 2 × 4 lanes</text>

              <rect x="762" y="210" width="88" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="806" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7" font-weight="500" font-family="monospace">enP2p1s0f0np0</text>
              <text x="806" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p0</text>
              <text x="806" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="806" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: roceP2p1s0f0</text>

              <rect x="856" y="210" width="82" height="58" rx="5" fill="#0ea5e9" fill-opacity="0.07" stroke="#0ea5e9" stroke-width="0.7" stroke-opacity="0.3"/>
              <text x="897" y="226" text-anchor="middle" fill="#0ea5e9" font-size="7" font-weight="500" font-family="monospace">enP2p1s0f1np1</text>
              <text x="897" y="239" text-anchor="middle" fill="#9ca3af" font-size="7" font-family="monospace">sub-port p1</text>
              <text x="897" y="252" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">4 lanes · 200G</text>
              <text x="897" y="263" text-anchor="middle" fill="#6b7280" font-size="6.5" font-family="monospace">RoCE: roceP2p1s0f1</text>

              <!-- Bond bar spark-2 -->
              <rect x="555" y="290" width="390" height="46" rx="6" fill="#8b5cf6" fill-opacity="0.06" stroke="#8b5cf6" stroke-width="0.8" stroke-opacity="0.3"/>
              <text x="750" y="310" text-anchor="middle" fill="#8b5cf6" font-size="10" font-weight="600" font-family="system-ui,sans-serif">bond0</text>
              <text x="750" y="324" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="monospace">balance-xor · layer2 · 4 slaves · 800G reported</text>

              <line x1="606" y1="268" x2="606" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="697" y1="268" x2="697" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="806" y1="268" x2="806" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>
              <line x1="897" y1="268" x2="897" y2="290" stroke="#8b5cf6" stroke-width="0.6" stroke-opacity="0.4"/>

              <!-- Management port spark-2 -->
              <rect x="755" y="350" width="170" height="36" rx="5" fill="#6b7280" fill-opacity="0.06" stroke="#4b5563" stroke-width="0.7"/>
              <text x="840" y="367" text-anchor="middle" fill="#9ca3af" font-size="8" font-weight="500" font-family="monospace">enP7s7</text>
              <text x="840" y="380" text-anchor="middle" fill="#6b7280" font-size="7" font-family="monospace">Realtek r8127 · 1 GbE</text>

              <!-- ============ Inter-node cables ============ -->
              <!-- "QSFP56 DAC" shared label -->
              <text x="480" y="168" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="system-ui,sans-serif">QSFP56 DAC Cables</text>

              <!-- Cable A (Port A ↔ Port A): full-width line with label overlay -->
              <line x1="430" y1="192" x2="530" y2="192" stroke="#3b82f6" stroke-width="3" stroke-opacity="0.45"/>
              <circle cx="430" cy="192" r="2.5" fill="#3b82f6" fill-opacity="0.6"/>
              <circle cx="530" cy="192" r="2.5" fill="#3b82f6" fill-opacity="0.6"/>
              <rect x="449" y="181" width="62" height="22" rx="3" fill="#111827" stroke="#3b82f6" stroke-width="0.6" stroke-opacity="0.25"/>
              <text x="480" y="195" text-anchor="middle" fill="#60a5fa" font-size="7.5" font-weight="500" font-family="system-ui,sans-serif">A · 400G</text>

              <!-- Cable B (Port B ↔ Port B): full-width line with label overlay -->
              <line x1="430" y1="240" x2="530" y2="240" stroke="#3b82f6" stroke-width="3" stroke-opacity="0.45"/>
              <circle cx="430" cy="240" r="2.5" fill="#3b82f6" fill-opacity="0.6"/>
              <circle cx="530" cy="240" r="2.5" fill="#3b82f6" fill-opacity="0.6"/>
              <rect x="449" y="229" width="62" height="22" rx="3" fill="#111827" stroke="#3b82f6" stroke-width="0.6" stroke-opacity="0.25"/>
              <text x="480" y="243" text-anchor="middle" fill="#60a5fa" font-size="7.5" font-weight="500" font-family="system-ui,sans-serif">B · 400G</text>

              <!-- Dashed guide lines from NIC boxes to node edges -->
              <!-- spark-1 NIC#1 → right edge -->
              <line x1="225" y1="192" x2="430" y2="192" stroke="#3b82f6" stroke-width="1" stroke-opacity="0.15" stroke-dasharray="3 3"/>
              <!-- spark-1 NIC#2 → right edge -->
              <line x1="425" y1="240" x2="430" y2="240" stroke="#3b82f6" stroke-width="1" stroke-opacity="0.15"/>
              <!-- spark-2 NIC#1 ← left edge -->
              <line x1="530" y1="192" x2="555" y2="192" stroke="#3b82f6" stroke-width="1" stroke-opacity="0.15"/>
              <!-- spark-2 NIC#2 ← left edge -->
              <line x1="530" y1="240" x2="755" y2="240" stroke="#3b82f6" stroke-width="1" stroke-opacity="0.15" stroke-dasharray="3 3"/>

              <!-- Management LAN -->
              <line x1="205" y1="368" x2="755" y2="368" stroke="#4b5563" stroke-width="1.5" stroke-dasharray="5 3"/>
              <rect x="380" y="355" width="200" height="26" rx="4" fill="#1f2937" stroke="#374151" stroke-width="0.7"/>
              <text x="480" y="372" text-anchor="middle" fill="#9ca3af" font-size="8" font-family="system-ui,sans-serif">Management LAN · 1 GbE</text>

              <!-- ============ Bandwidth bottleneck indicator ============ -->
              <rect x="200" y="440" width="560" height="80" rx="8" fill="#f59e0b" fill-opacity="0.04" stroke="#f59e0b" stroke-width="0.7" stroke-opacity="0.2"/>
              <text x="480" y="460" text-anchor="middle" fill="#f59e0b" font-size="10" font-weight="600" font-family="system-ui,sans-serif">PCIe Bandwidth Analysis</text>
              <text x="480" y="476" text-anchor="middle" fill="#9ca3af" font-size="8.5" font-family="system-ui,sans-serif">Ethernet link reports 4 × 200G = 800 Gbps per node (bond0)</text>
              <text x="480" y="490" text-anchor="middle" fill="#9ca3af" font-size="8.5" font-family="system-ui,sans-serif">Each CX7 NIC is behind PCIe Gen5 ×4 ≈ 126 Gbps per direction</text>
              <text x="480" y="504" text-anchor="middle" fill="#f59e0b" font-size="9" font-weight="500" font-family="system-ui,sans-serif">Effective aggregate throughput: 2 × ~126 Gbps ≈ 252 Gbps per direction</text>
              <text x="480" y="518" text-anchor="middle" fill="#6b7280" font-size="7.5" font-family="system-ui,sans-serif">NCCL/RDMA uses RoCE v2 on all sub-ports with GPU-Direct for optimal multi-NIC parallelism</text>
            </svg>
          </div>
        </div>

        <!-- Explanation cards -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">

          <!-- Port splitting -->
          <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-2 h-2 rounded-full bg-blue-400"></span>
              <h4 class="text-white font-semibold text-sm">Port Splitting (Dual Sub-port Mode)</h4>
            </div>
            <div class="text-sm text-gray-400 space-y-2">
              <p>Each DGX Spark has <span class="text-white">2 physical ConnectX-7 NICs</span> on separate PCIe root complexes. Each NIC has a single <span class="text-white">QSFP56 400G connector</span> with 8 SerDes lanes running at 50 Gbps each.</p>
              <p>CX7 firmware splits each physical port into <span class="text-cyan-400">2 logical sub-ports</span> of 4 lanes (200G) each. This is why the OS shows 4 network interfaces for what physically are 2 connectors.</p>
              <div class="mt-3 bg-gray-900 rounded-lg p-3 font-mono text-xs text-gray-300 space-y-1">
                <div><span class="text-blue-400">NIC #1</span> (PCIe 0000) QSFP56 Port A:</div>
                <div class="ml-3">p0 → <span class="text-cyan-400">enp1s0f0np0</span> (f0 = function 0, np0 = netport 0)</div>
                <div class="ml-3">p1 → <span class="text-cyan-400">enp1s0f1np1</span> (f1 = function 1, np1 = netport 1)</div>
                <div class="mt-1"><span class="text-blue-400">NIC #2</span> (PCIe 0002) QSFP56 Port B:</div>
                <div class="ml-3">p0 → <span class="text-cyan-400">enP2p1s0f0np0</span> (P2 = PCI domain 2)</div>
                <div class="ml-3">p1 → <span class="text-cyan-400">enP2p1s0f1np1</span></div>
              </div>
            </div>
          </div>

          <!-- Bond configuration -->
          <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-2 h-2 rounded-full bg-purple-400"></span>
              <h4 class="text-white font-semibold text-sm">Bond Configuration</h4>
            </div>
            <div class="text-sm text-gray-400 space-y-2">
              <p>All 4 sub-ports are aggregated into <span class="text-purple-400 font-mono">bond0</span> using <span class="text-white">balance-xor</span> mode with <span class="text-white">layer2</span> hashing. The bond reports 800 Gbps aggregate link speed.</p>
              <p class="text-yellow-400/80">Note: layer2 hashing uses only MAC addresses. In a point-to-point topology, all frames hash to the same slave. For TCP traffic, consider switching to <span class="text-white font-mono">layer3+4</span> to distribute flows across all sub-ports.</p>
              <div class="mt-3 bg-gray-900 rounded-lg p-3 font-mono text-xs text-gray-300 space-y-1">
                <div>Mode: <span class="text-purple-400">balance-xor (mode 2)</span></div>
                <div>Hash: <span class="text-gray-300">layer2</span></div>
                <div>Slaves: <span class="text-gray-300">4</span> (all sub-ports)</div>
                <div>MII poll: <span class="text-gray-300">100ms</span></div>
                <div>Link: <span class="text-green-400">800 Gbps</span> (4 × 200G reported)</div>
              </div>
            </div>
          </div>

          <!-- PCIe bottleneck -->
          <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-2 h-2 rounded-full bg-amber-400"></span>
              <h4 class="text-white font-semibold text-sm">PCIe Bandwidth Bottleneck</h4>
            </div>
            <div class="text-sm text-gray-400 space-y-2">
              <p>Each CX7 NIC connects to the Grace CPU through <span class="text-amber-400">PCIe Gen5 ×4</span> (32 GT/s × 4 lanes). With 128b/130b encoding, this provides ~<span class="text-white">126 Gbps per direction</span> per NIC.</p>
              <p>While the Ethernet link reports 400G per physical port (800G total), the <span class="text-amber-400">PCIe bus limits actual throughput</span> to ~252 Gbps aggregate per direction through both NICs.</p>
              <div class="mt-3 bg-gray-900 rounded-lg p-3 font-mono text-xs text-gray-300 space-y-1">
                <div>Per NIC: PCIe Gen5 ×4 = <span class="text-amber-400">~126 Gbps/dir</span></div>
                <div>Both NICs: 2 × 126 = <span class="text-amber-400">~252 Gbps/dir</span></div>
                <div>Ethernet link: 4 × 200G = <span class="text-gray-500">800 Gbps (nominal)</span></div>
                <div>Effective ratio: <span class="text-gray-300">~31.5% of nominal link</span></div>
              </div>
            </div>
          </div>

          <!-- RoCE / RDMA -->
          <div class="bg-gray-800 rounded-xl border border-gray-700 p-5">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-2 h-2 rounded-full bg-green-400"></span>
              <h4 class="text-white font-semibold text-sm">RoCE v2 &amp; GPU-Direct RDMA</h4>
            </div>
            <div class="text-sm text-gray-400 space-y-2">
              <p>All 4 sub-ports run <span class="text-green-400">RoCE v2</span> (RDMA over Converged Ethernet) in Ethernet link layer mode at <span class="text-white">200 Gb/sec (4X HDR)</span> per port.</p>
              <p>NCCL uses all 4 RoCE endpoints in parallel for GPU-Direct RDMA, maximizing multi-path throughput for distributed training across both DGX Spark nodes.</p>
              <div class="mt-3 bg-gray-900 rounded-lg p-3 font-mono text-xs text-gray-300 space-y-1">
                <div>Protocol: <span class="text-green-400">RoCE v2</span> (not InfiniBand)</div>
                <div>Rate: <span class="text-gray-300">200 Gb/sec (4X HDR) per port</span></div>
                <div>Firmware: <span class="text-gray-300">28.45.4028</span></div>
                <div>Endpoints:</div>
                <div class="ml-3 text-gray-400">rocep1s0f0, rocep1s0f1</div>
                <div class="ml-3 text-gray-400">roceP2p1s0f0, roceP2p1s0f1</div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </template>

    <!-- Topology -->
    <template v-else-if="topology">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div
          v-for="nodeData in topology.nodes" :key="nodeData.hostname"
          class="bg-gray-800 rounded-xl border border-gray-700 p-5"
        >
          <div class="flex items-center gap-3 mb-4 pb-3 border-b border-gray-700">
            <div class="w-3 h-3 rounded-full bg-green-400" />
            <h3 class="text-lg font-semibold text-gray-100">{{ nodeData.hostname }}</h3>
            <span class="text-xs text-gray-500 ml-auto">{{ nodeData.ip }}</span>
          </div>

          <div class="space-y-3">
            <template v-if="nodeData.bridges?.length">
              <div
                v-for="bridge in nodeData.bridges" :key="bridge.name"
                class="bg-purple-500/5 border border-purple-500/20 rounded-lg p-3"
              >
                <div class="flex items-center gap-2 mb-2">
                  <span class="px-2 py-0.5 text-xs rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">bridge</span>
                  <span class="font-mono text-sm text-gray-100">{{ bridge.name }}</span>
                </div>
                <div v-if="bridge.ports?.length" class="flex flex-wrap gap-2 ml-4">
                  <div
                    v-for="port in bridge.ports" :key="port"
                    class="px-2 py-1 text-xs rounded bg-gray-700/50 text-gray-300 font-mono border border-gray-600"
                  >
                    {{ port }}
                  </div>
                </div>
                <div v-else class="ml-4 text-xs text-gray-500 italic">No ports</div>
              </div>
            </template>

            <template v-if="nodeData.interfaces?.length">
              <div
                v-for="iface in nodeData.interfaces" :key="iface.name"
                class="flex items-center gap-3 px-3 py-2 bg-gray-700/30 rounded-lg"
              >
                <div class="w-2 h-2 rounded-full" :class="iface.state === 'UP' ? 'bg-green-400' : 'bg-red-400'" />
                <span class="font-mono text-sm text-gray-200">{{ iface.name }}</span>
                <span v-if="iface.type" class="text-xs text-gray-500">{{ iface.type }}</span>
                <span v-if="iface.addresses?.length" class="ml-auto text-xs font-mono text-gray-400">
                  {{ iface.addresses[0] }}
                </span>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- Create Bridge Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showBridge" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showBridge = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Create Bridge</h3>
              <button @click="showBridge = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div v-if="bridgeError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ bridgeError }}</div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Bridge Name</label>
                <input v-model="bridgeName" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500" placeholder="br0" />
              </div>
              <div class="text-xs text-gray-500">Node: {{ activeTab }}</div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showBridge = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="createBridge" :disabled="bridgeCreating" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ bridgeCreating ? 'Creating...' : 'Create' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Create VLAN Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showVlan" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showVlan = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Create VLAN</h3>
              <button @click="showVlan = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div v-if="vlanError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ vlanError }}</div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Parent Interface</label>
                <select v-model="vlanParent" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50">
                  <option value="">— Select —</option>
                  <option v-for="i in interfaces" :key="i.name" :value="i.name">{{ i.name }}</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">VLAN ID</label>
                <input v-model.number="vlanId" type="number" min="1" max="4094" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50" />
              </div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showVlan = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="createVlan" :disabled="vlanCreating" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ vlanCreating ? 'Creating...' : 'Create' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Bridge Ports Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showPort" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showPort = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Manage Bridge Ports</h3>
              <button @click="showPort = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div v-if="portError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ portError }}</div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Bridge</label>
                <select v-model="portBridge" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50">
                  <option value="">— Select —</option>
                  <option v-for="b in bridges" :key="b.name" :value="b.name">{{ b.name }}</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Interface</label>
                <select v-model="portIface" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50">
                  <option value="">— Select —</option>
                  <option v-for="i in ethernetIfaces" :key="i.name" :value="i.name">{{ i.name }}</option>
                </select>
              </div>
              <div class="flex items-center gap-3">
                <button @click="portAction = 'add'" class="px-3 py-1.5 text-xs rounded-md border transition-colors" :class="portAction === 'add' ? 'bg-nvidia/10 text-nvidia border-nvidia/30' : 'bg-gray-800 text-gray-400 border-gray-600'">Add</button>
                <button @click="portAction = 'remove'" class="px-3 py-1.5 text-xs rounded-md border transition-colors" :class="portAction === 'remove' ? 'bg-red-500/10 text-red-400 border-red-500/30' : 'bg-gray-800 text-gray-400 border-gray-600'">Remove</button>
              </div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showPort = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="manageBridgePort" :disabled="portSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ portSubmitting ? 'Applying...' : 'Apply' }}
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
