# Spark Cluster Manager

A lightweight web-based management interface purpose-built for a two-node
**NVIDIA DGX Spark (GB10)** cluster. It brings Docker Swarm orchestration,
KVM virtualisation, Slurm GPU scheduling, host networking, NFS storage and
Traefik routing under a single dashboard accessible from any browser.

## Features

| Area | What you get |
|------|-------------|
| **Dashboard** | Live per-node CPU/GPU/memory/thermal/NVMe metrics, network throughput, quick actions |
| **Docker Swarm** | Compose-based stack deployment, service scaling, container logs (WebSocket), in-browser exec (xterm.js) |
| **KVM Virtual Machines** | Full VM lifecycle, noVNC console, ISO/disk/pool management, snapshots, disk hot-plug |
| **Slurm GPU Jobs** | Submit, monitor and cancel jobs, Enroot/Pyxis container support, live job output streaming |
| **Networking** | Linux bridges, VLANs, bonds, IP address and route management, CX7 interconnect diagram |
| **Traefik** | View routers, services, middlewares and entrypoints from the cluster Traefik instance |
| **NFS & Storage** | Per-node NFS export management, mount overview, disk usage, NVMe health |
| **File Browser** | Upload, download, browse, rename, chmod files on both nodes |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser — Vue 3 · Tailwind CSS · noVNC · xterm.js  │
├─────────────────────────────────────────────────────┤
│  Backend — FastAPI · asyncssh · docker SDK · libvirt │
├──────────────────────┬──────────────────────────────┤
│  Docker Swarm        │  libvirt / QEMU / KVM        │
│  Slurm + Enroot      │  NFS cross-mount             │
├──────────────────────┴──────────────────────────────┤
│  ConnectX-7 bond (4×200G) │ 1 GbE mgmt │ bridges   │
├─────────────────────────────────────────────────────┤
│  DGX OS — Ubuntu · aarch64 · kernel 6.17            │
└─────────────────────────────────────────────────────┘
```

The manager runs as a Docker Swarm service on the **manager node**.
It reaches both nodes over SSH (asyncssh) and talks to Docker / libvirt /
Slurm through their respective sockets and CLIs.

## Prerequisites

- Two NVIDIA DGX Spark GB10 nodes running DGX OS (Ubuntu-based, aarch64)
- ConnectX-7 NICs cabled back-to-back (QSFP56 DAC) for the data plane
- 1 GbE management network with internet access
- A control machine with **Ansible ≥ 2.15** and SSH access to both nodes
- **Docker ≥ 24** and **Python ≥ 3.12** (installed by Ansible roles)

## Deployment with Ansible

### 1. Configure the inventory

Edit `ansible/inventory/hosts.yml` with your node management IPs,
CX7 bond IPs, NFS paths and desired hostnames:

```yaml
all:
  children:
    managers:
      hosts:
        spark-1:
          ansible_host: <MGMT_IP_NODE1>
          cx7_ip: <CX7_IP_NODE1>
          nfs_export_dir: /data/shared1
          nfs_mount_from: <CX7_IP_NODE2>:/data/shared2
          nfs_mount_to: /data/shared2
    workers:
      hosts:
        spark-2:
          ansible_host: <MGMT_IP_NODE2>
          cx7_ip: <CX7_IP_NODE2>
          nfs_export_dir: /data/shared2
          nfs_mount_from: <CX7_IP_NODE1>:/data/shared1
          nfs_mount_to: /data/shared1
  vars:
    ansible_user: user
    ansible_become: true
```

> **Security note**: never store `ansible_become_pass` in plain text.
> Use `--ask-become-pass` at runtime or encrypt the value with
> `ansible-vault`.

### 2. Run the full playbook

```bash
cd ansible
ansible-playbook playbooks/site.yml --ask-become-pass
```

This executes every role in order:

| Play | Role | Scope |
|------|------|-------|
| Base system | `common` | all nodes |
| Network bonding & bridges | `networking` | all nodes |
| NFS server & cross-mounts | `nfs` | all nodes |
| Docker Swarm initialisation | `docker_swarm` | all nodes |
| KVM hypervisor setup | `kvm` | all nodes |
| Slurm controller + worker | `slurm` | all nodes |
| NCCL communication tests | `nccl` | managers |
| Traefik ingress | `traefik` | all nodes |
| Spark Manager UI | `spark_manager` | managers |

### 3. Partial playbooks

Run only what you need:

```bash
ansible-playbook playbooks/infra.yml --ask-become-pass   # everything except Traefik & UI
ansible-playbook playbooks/ui.yml --ask-become-pass       # Spark Manager only
ansible-playbook playbooks/traefik-only.yml --ask-become-pass
ansible-playbook playbooks/slurm-only.yml --ask-become-pass
ansible-playbook playbooks/nccl-only.yml --ask-become-pass
```

## Manual / Development Setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8443 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `localhost:8443`.

### Production Docker image

```bash
docker build -t spark-manager:latest -f deploy/Dockerfile .
docker stack deploy -c deploy/docker-compose.prod.yml spark-manager
```

Access the UI at `http://<spark-1-ip>:8443`.
Default credentials: **admin / admin** (change via environment variables).

## Configuration

All settings are controlled via environment variables with the
`SPARK_MANAGER_` prefix. Set them in your Docker Compose file or shell.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `changeme-in-production` | JWT signing key |
| `NODE1_HOSTNAME` | `spark-1` | First node hostname |
| `NODE2_HOSTNAME` | `spark-2` | Second node hostname |
| `NODE1_IP` | `10.10.10.1` | First node CX7 bond IP |
| `NODE2_IP` | `10.10.10.2` | Second node CX7 bond IP |
| `SSH_USER` | `user` | SSH user for remote commands |
| `SSH_KEY_PATH` | `/root/.ssh/id_ed25519` | SSH private key inside container |
| `ADMIN_USER` | `admin` | Web UI login username |
| `ADMIN_PASS` | `admin` | Web UI login password |
| `NFS_ROOTS` | `/data/shared1,/data/shared2` | NFS root directories |
| `DOCKER_SOCKET` | `unix:///var/run/docker.sock` | Docker daemon socket |

## Project Structure

```
spark-cluster/
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/
│   │   └── hosts.yml            # Node IPs, variables (do not commit secrets)
│   ├── group_vars/
│   │   ├── all.yml              # Shared variables
│   │   ├── managers.yml
│   │   └── workers.yml
│   ├── playbooks/
│   │   ├── site.yml             # Full deployment
│   │   ├── infra.yml            # Infrastructure only
│   │   ├── ui.yml               # Spark Manager only
│   │   ├── traefik-only.yml
│   │   ├── slurm-only.yml
│   │   ├── nccl-only.yml
│   │   ├── nccl-manager.yml
│   │   └── manager-only.yml
│   └── roles/
│       ├── common/              # Base packages, hostname, Wi-Fi disable
│       ├── networking/          # CX7 bond, Netplan, bridges
│       ├── nfs/                 # NFS server, exports, cross-mounts
│       ├── docker_swarm/        # Docker install, Swarm init/join
│       ├── kvm/                 # libvirt, QEMU, bridge XML
│       ├── slurm/               # slurmctld, slurmd, config templates
│       ├── nccl/                # NCCL all-reduce tests
│       ├── traefik/             # Traefik stack, config templates
│       └── spark_manager/       # Build & deploy the manager container
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI application, route mounts
│       ├── config.py            # Pydantic settings (env-driven)
│       ├── auth.py              # JWT authentication
│       ├── routers/             # docker, images, vms, vnc, slurm,
│       │                        # network, storage, files, system, traefik
│       ├── services/            # docker_svc, libvirt_svc, slurm_svc,
│       │                        # network_svc, file_svc, node_svc
│       └── models/              # Pydantic request/response schemas
├── frontend/
│   ├── package.json
│   ├── vite.config.js           # Proxy /api → backend
│   └── src/
│       ├── App.vue              # Shell layout, sidebar navigation
│       ├── router.js            # Route definitions
│       ├── views/               # Dashboard, Stacks, Services, Containers,
│       │                        # Images, VMs, VMCreate, VMDetail,
│       │                        # SlurmJobs, SlurmCluster, Networks,
│       │                        # Storage, FileBrowser, Traefik, Login
│       ├── components/          # VncConsole, LogViewer, ComposeEditor
│       └── composables/         # useApi, useWebSocket
└── deploy/
    ├── Dockerfile               # Multi-stage: Node 20 + Python 3.12
    ├── docker-compose.yml       # Dev / build compose
    └── docker-compose.prod.yml  # Production Swarm + Traefik labels
```

## Network Layout

| Network | Purpose | Speed |
|---------|---------|-------|
| **CX7 Bond** (`bond0`) | Inter-node GPU traffic (NCCL/RoCE), NFS, container overlay | 4 × 200G (PCIe-limited to ~252 Gbps) |
| **Management LAN** (`enP7s7`) | SSH, Web UI, internet access | 1 GbE |
| **Linux Bridges** (`br-containers`, `br-vms`) | VM and container network isolation | — |

Each node has two ConnectX-7 NICs (QSFP56, 8 SerDes lanes each), firmware-split
into 2 × 200G sub-ports, all bonded into `bond0` with balance-xor.

## License

Private use.
