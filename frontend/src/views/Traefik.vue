<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi'

const { get } = useApi()

const overview = ref([])
const routers = ref([])
const services = ref([])
const entrypoints = ref([])
const activeTab = ref('overview')
const loading = ref(true)
const error = ref('')
const netInfo = ref({ spark1: null, spark2: null })

let poll = null

function findIface(ifaces, name) {
  const iface = ifaces.find(i => i.name === name)
  if (!iface) return { name, ip: '—' }
  const v4 = iface.addresses.find(a => !a.includes(':'))
  return { name: iface.name, ip: v4 ? v4.split('/')[0] : '—' }
}

async function fetchNet() {
  try {
    const [ifaces1, ifaces2] = await Promise.all([
      get('/network/interfaces?node=spark-1'),
      get('/network/interfaces?node=spark-2'),
    ])
    netInfo.value = {
      spark1: { uplink: findIface(ifaces1, 'enP7s7'), bond: findIface(ifaces1, 'bond0') },
      spark2: { uplink: findIface(ifaces2, 'enP7s7'), bond: findIface(ifaces2, 'bond0') },
    }
  } catch { /* diagram falls back to '—' */ }
}

const n1 = computed(() => netInfo.value.spark1 || { uplink: { name: 'enP7s7', ip: '...' }, bond: { name: 'bond0', ip: '...' } })
const n2 = computed(() => netInfo.value.spark2 || { uplink: { name: 'enP7s7', ip: '...' }, bond: { name: 'bond0', ip: '...' } })

async function fetchAll() {
  try {
    const [ov, rt, sv, ep] = await Promise.all([
      get('/traefik/overview'),
      get('/traefik/routers'),
      get('/traefik/services'),
      get('/traefik/entrypoints'),
    ])
    overview.value = ov
    routers.value = rt
    services.value = sv
    entrypoints.value = ep
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Failed to load Traefik data'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchAll()
  fetchNet()
  poll = setInterval(fetchAll, 10000)
})

onUnmounted(() => {
  if (poll) clearInterval(poll)
})

function statusColor(s) {
  if (s === 'enabled' || s === 'up') return 'text-green-400'
  if (s === 'warning') return 'text-yellow-400'
  return 'text-red-400'
}

function badge(status) {
  const colors = {
    enabled: 'bg-green-500/20 text-green-400',
    up: 'bg-green-500/20 text-green-400',
    disabled: 'bg-gray-500/20 text-gray-400',
    down: 'bg-red-500/20 text-red-400',
  }
  return colors[status] || 'bg-gray-500/20 text-gray-400'
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold text-white">Traefik Ingress</h2>
      <button
        @click="fetchAll"
        class="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors"
      >
        Refresh
      </button>
    </div>

    <div v-if="error" class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400 text-sm">
      {{ error }}
    </div>

    <!-- Node status cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="node in overview"
        :key="node.node"
        class="bg-gray-800 rounded-xl border border-gray-700 p-5"
      >
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-3">
            <div :class="['w-3 h-3 rounded-full', node.status === 'up' ? 'bg-green-500' : 'bg-red-500']" />
            <span class="text-white font-semibold text-lg">{{ node.node }}</span>
          </div>
          <span class="text-xs text-gray-500">{{ node.ip }}</span>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span class="text-gray-500">Status</span>
            <div :class="statusColor(node.status)">{{ node.status }}</div>
          </div>
          <div>
            <span class="text-gray-500">Version</span>
            <div class="text-gray-300">{{ node.version || '—' }}</div>
          </div>
          <template v-if="node.overview">
            <div>
              <span class="text-gray-500">HTTP Routers</span>
              <div class="text-gray-300">{{ node.overview.http?.routers?.total || 0 }}</div>
            </div>
            <div>
              <span class="text-gray-500">HTTP Services</span>
              <div class="text-gray-300">{{ node.overview.http?.services?.total || 0 }}</div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-700">
      <nav class="flex gap-4">
        <button
          v-for="tab in ['overview', 'routers', 'services', 'entrypoints']"
          :key="tab"
          @click="activeTab = tab"
          :class="[
            'pb-3 px-1 text-sm font-medium border-b-2 transition-colors capitalize',
            activeTab === tab
              ? 'border-nvidia text-nvidia'
              : 'border-transparent text-gray-400 hover:text-white'
          ]"
        >
          {{ tab }}
        </button>
      </nav>
    </div>

    <div v-if="loading" class="text-gray-500 text-sm">Loading...</div>

    <!-- Routers table -->
    <div v-if="activeTab === 'routers'" class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-700 text-gray-400 text-left">
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">Rule</th>
            <th class="px-4 py-3 font-medium">Entrypoints</th>
            <th class="px-4 py-3 font-medium">Service</th>
            <th class="px-4 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in routers"
            :key="r.name"
            class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
          >
            <td class="px-4 py-3 text-white font-mono text-xs">{{ r.name }}</td>
            <td class="px-4 py-3 text-gray-300 font-mono text-xs max-w-xs truncate">{{ r.rule }}</td>
            <td class="px-4 py-3">
              <span
                v-for="ep in (r.entryPoints || [])"
                :key="ep"
                class="inline-block px-2 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400 mr-1"
              >
                {{ ep }}
              </span>
            </td>
            <td class="px-4 py-3 text-gray-400 text-xs">{{ r.service }}</td>
            <td class="px-4 py-3">
              <span :class="['px-2 py-0.5 rounded text-xs', badge(r.status)]">
                {{ r.status }}
              </span>
            </td>
          </tr>
          <tr v-if="routers.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-gray-500">No routers configured</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Services table -->
    <div v-if="activeTab === 'services'" class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-700 text-gray-400 text-left">
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">Type</th>
            <th class="px-4 py-3 font-medium">Servers</th>
            <th class="px-4 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in services"
            :key="s.name"
            class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
          >
            <td class="px-4 py-3 text-white font-mono text-xs">{{ s.name }}</td>
            <td class="px-4 py-3 text-gray-400 text-xs">{{ s.type || 'loadbalancer' }}</td>
            <td class="px-4 py-3">
              <div v-if="s.loadBalancer?.servers" class="space-y-1">
                <div
                  v-for="(srv, i) in s.loadBalancer.servers"
                  :key="i"
                  class="text-xs font-mono text-gray-300"
                >
                  {{ srv.url }}
                </div>
              </div>
              <span v-else class="text-gray-500 text-xs">—</span>
            </td>
            <td class="px-4 py-3">
              <span :class="['px-2 py-0.5 rounded text-xs', badge(s.status)]">
                {{ s.status }}
              </span>
            </td>
          </tr>
          <tr v-if="services.length === 0">
            <td colspan="4" class="px-4 py-8 text-center text-gray-500">No services registered</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Entrypoints -->
    <div v-if="activeTab === 'entrypoints'" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div
        v-for="ep in entrypoints"
        :key="ep.name"
        class="bg-gray-800 rounded-xl border border-gray-700 p-5"
      >
        <div class="text-white font-semibold mb-2">{{ ep.name }}</div>
        <div class="text-sm text-gray-400">{{ ep.address }}</div>
      </div>
      <div v-if="entrypoints.length === 0" class="col-span-3 text-center text-gray-500 py-8">
        No entrypoints found
      </div>
    </div>

    <!-- Overview -->
    <div v-if="activeTab === 'overview'" class="space-y-4">
      <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 class="text-white font-semibold mb-4">Architecture</h3>
        <div class="text-sm text-gray-400 space-y-2 mb-6">
          <p>Traefik runs as a <span class="text-nvidia">global service</span> on both DGX Spark nodes.</p>
          <p>Incoming requests arrive on the <span class="text-white font-mono">{{ n1.uplink.name }}</span> 10G interfaces (<span class="text-white">{{ n1.uplink.ip }}</span>, <span class="text-white">{{ n2.uplink.ip }}</span>) on ports <span class="text-white">80</span> / <span class="text-white">443</span>.</p>
          <p>If the target service lives on the other node, Traefik forwards via the <span class="text-white">200G</span> <span class="text-white font-mono">{{ n1.bond.name }}</span> link (<span class="text-white">{{ n1.bond.ip }}</span> ↔ <span class="text-white">{{ n2.bond.ip }}</span>).</p>
          <p>Services are auto-discovered via Docker Swarm labels on the <span class="text-white font-mono">traefik-public</span> overlay network.</p>
        </div>

        <!-- SVG Architecture Diagram -->
        <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
          <svg viewBox="0 0 800 400" class="w-full max-w-3xl mx-auto" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="arrowGray" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6" fill="none" stroke="#6b7280" stroke-width="1"/>
              </marker>
              <marker id="arrowGreen" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6" fill="none" stroke="#76b900" stroke-width="1" stroke-opacity="0.5"/>
              </marker>
            </defs>

            <!-- ── External network / incoming ── -->
            <text x="400" y="18" text-anchor="middle" fill="#9ca3af" font-size="11" font-family="system-ui">External Network</text>

            <!-- Incoming to spark-1 10G -->
            <text x="195" y="42" text-anchor="middle" fill="#e5e7eb" font-size="10" font-family="monospace">{{ n1.uplink.name }}</text>
            <text x="195" y="54" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">{{ n1.uplink.ip }}</text>
            <path d="M195 58 L195 90" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrowGray)"/>

            <!-- Incoming to spark-2 10G -->
            <text x="605" y="42" text-anchor="middle" fill="#e5e7eb" font-size="10" font-family="monospace">{{ n2.uplink.name }}</text>
            <text x="605" y="54" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">{{ n2.uplink.ip }}</text>
            <path d="M605 58 L605 90" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrowGray)"/>

            <!-- Incoming labels -->
            <text x="155" y="78" text-anchor="end" fill="#6b7280" font-size="8" font-family="monospace">:80 / :443</text>
            <text x="645" y="78" text-anchor="start" fill="#6b7280" font-size="8" font-family="monospace">:80 / :443</text>

            <!-- ── spark-1 node ── -->
            <rect x="30" y="90" width="330" height="260" rx="12" fill="none" stroke="#374151" stroke-width="1.5"/>
            <text x="195" y="114" text-anchor="middle" fill="#e5e7eb" font-size="14" font-weight="600" font-family="system-ui">spark-1</text>

            <!-- Traefik on spark-1 -->
            <rect x="65" y="130" width="260" height="56" rx="8" fill="#76b900" fill-opacity="0.08" stroke="#76b900" stroke-width="1" stroke-opacity="0.4"/>
            <text x="195" y="154" text-anchor="middle" fill="#76b900" font-size="12" font-weight="600" font-family="system-ui">Traefik</text>
            <text x="195" y="174" text-anchor="middle" fill="#9ca3af" font-size="10" font-family="monospace">:80  :443  :8080</text>

            <!-- Containers on spark-1 -->
            <rect x="75" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="111" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc A</text>
            <rect x="159" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="195" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc B</text>
            <rect x="243" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="279" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc C</text>

            <line x1="130" y1="186" x2="111" y2="210" stroke="#4b5563" stroke-width="1"/>
            <line x1="195" y1="186" x2="195" y2="210" stroke="#4b5563" stroke-width="1"/>
            <line x1="260" y1="186" x2="279" y2="210" stroke="#4b5563" stroke-width="1"/>

            <!-- Overlay label spark-1 -->
            <line x1="60" y1="280" x2="340" y2="280" stroke="#4b5563" stroke-width="0.5" stroke-dasharray="2 2"/>
            <text x="195" y="296" text-anchor="middle" fill="#6b7280" font-size="9" font-family="monospace" font-style="italic">traefik-public overlay</text>

            <!-- ── spark-2 node ── -->
            <rect x="440" y="90" width="330" height="260" rx="12" fill="none" stroke="#374151" stroke-width="1.5"/>
            <text x="605" y="114" text-anchor="middle" fill="#e5e7eb" font-size="14" font-weight="600" font-family="system-ui">spark-2</text>

            <!-- Traefik on spark-2 -->
            <rect x="475" y="130" width="260" height="56" rx="8" fill="#76b900" fill-opacity="0.08" stroke="#76b900" stroke-width="1" stroke-opacity="0.4"/>
            <text x="605" y="154" text-anchor="middle" fill="#76b900" font-size="12" font-weight="600" font-family="system-ui">Traefik</text>
            <text x="605" y="174" text-anchor="middle" fill="#9ca3af" font-size="10" font-family="monospace">:80  :443  :8080</text>

            <!-- Containers on spark-2 -->
            <rect x="485" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="521" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc D</text>
            <rect x="569" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="605" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc E</text>
            <rect x="653" y="210" width="72" height="44" rx="6" fill="#3b82f6" fill-opacity="0.1" stroke="#3b82f6" stroke-width="0.8" stroke-opacity="0.3"/>
            <text x="689" y="237" text-anchor="middle" fill="#60a5fa" font-size="9" font-family="monospace">svc F</text>

            <line x1="540" y1="186" x2="521" y2="210" stroke="#4b5563" stroke-width="1"/>
            <line x1="605" y1="186" x2="605" y2="210" stroke="#4b5563" stroke-width="1"/>
            <line x1="670" y1="186" x2="689" y2="210" stroke="#4b5563" stroke-width="1"/>

            <!-- Overlay label spark-2 -->
            <line x1="460" y1="280" x2="740" y2="280" stroke="#4b5563" stroke-width="0.5" stroke-dasharray="2 2"/>
            <text x="605" y="296" text-anchor="middle" fill="#6b7280" font-size="9" font-family="monospace" font-style="italic">traefik-public overlay</text>

            <!-- ── Bond0 interconnect (between Traefik boxes) ── -->
            <line x1="360" y1="158" x2="440" y2="158" stroke="#76b900" stroke-width="2.5" stroke-opacity="0.6"/>
            <text x="400" y="146" text-anchor="middle" fill="#76b900" font-size="9" font-weight="600" font-family="monospace">200G {{ n1.bond.name }}</text>

            <!-- Bond IP labels near edges -->
            <text x="362" y="170" text-anchor="end" fill="#76b900" font-size="8" font-family="monospace" opacity="0.7">{{ n1.bond.ip }}</text>
            <text x="438" y="170" text-anchor="start" fill="#76b900" font-size="8" font-family="monospace" opacity="0.7">{{ n2.bond.ip }}</text>

            <!-- Cross-route arrows (service forwarding via bond) -->
            <path d="M325 178 C365 205 435 205 475 178" stroke="#76b900" stroke-width="1" stroke-opacity="0.35" stroke-dasharray="3 2" fill="none" marker-end="url(#arrowGreen)"/>
            <path d="M475 170 C435 143 365 143 325 170" stroke="#76b900" stroke-width="1" stroke-opacity="0.35" stroke-dasharray="3 2" fill="none" marker-end="url(#arrowGreen)"/>

            <!-- ── Legend / explanation ── -->
            <text x="400" y="340" text-anchor="middle" fill="#9ca3af" font-size="9" font-family="system-ui">Clients reach either node via 10G uplinks. If the target service is on the peer node,</text>
            <text x="400" y="354" text-anchor="middle" fill="#9ca3af" font-size="9" font-family="system-ui">Traefik forwards the request over the 200G bond0 high-speed interconnect.</text>
          </svg>
        </div>
      </div>

      <div class="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 class="text-white font-semibold mb-3">Adding services to Traefik</h3>
        <div class="text-sm text-gray-400 mb-3">
          Add these labels to your Docker Swarm service deploy section:
        </div>
        <div class="bg-gray-900 rounded-lg p-4 font-mono text-xs text-gray-300 overflow-x-auto">
          <pre>deploy:
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.myapp.rule=Host(`myapp.spark.local`)"
    - "traefik.http.routers.myapp.entrypoints=web"
    - "traefik.http.services.myapp.loadbalancer.server.port=8000"
networks:
  - traefik-public</pre>
        </div>
      </div>
    </div>
  </div>
</template>
