import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'Dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/stacks', name: 'Stacks', component: () => import('./views/Stacks.vue') },
  { path: '/services', name: 'Services', component: () => import('./views/Services.vue') },
  { path: '/containers', name: 'Containers', component: () => import('./views/Containers.vue') },
  { path: '/images', name: 'Images', component: () => import('./views/Images.vue') },
  { path: '/vms', name: 'VMs', component: () => import('./views/VMs.vue') },
  { path: '/vms/create', name: 'VMCreate', component: () => import('./views/VMCreate.vue') },
  { path: '/vms/:name', name: 'VMDetail', component: () => import('./views/VMDetail.vue') },
  { path: '/slurm/jobs', name: 'SlurmJobs', component: () => import('./views/SlurmJobs.vue') },
  { path: '/slurm/cluster', name: 'SlurmCluster', component: () => import('./views/SlurmCluster.vue') },
  { path: '/network', name: 'Networks', component: () => import('./views/Networks.vue') },
  { path: '/storage', name: 'Storage', component: () => import('./views/Storage.vue') },
  { path: '/files', name: 'FileBrowser', component: () => import('./views/FileBrowser.vue') },
  { path: '/traefik', name: 'Traefik', component: () => import('./views/Traefik.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  const token = localStorage.getItem('token')
  if (!token) return { name: 'Login' }
  return true
})

export default router
