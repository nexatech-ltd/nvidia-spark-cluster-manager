from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SPARK_MANAGER_"}

    secret_key: str = "changeme-in-production"
    node1_hostname: str = "spark-1"
    node2_hostname: str = "spark-2"
    node1_ip: str = "10.10.10.1"
    node2_ip: str = "10.10.10.2"
    nfs_roots: list[str] = ["/data/shared1", "/data/shared2"]
    ssh_user: str = "user"
    ssh_key_path: str = "/root/.ssh/id_ed25519"
    docker_socket: str = "unix:///var/run/docker.sock"
    libvirt_uri_local: str = "qemu:///system"
    libvirt_uri_remote_template: str = "qemu+ssh://{user}@{host}/system"
    slurm_spool_dir: str = "/var/spool/slurmd"
    iso_storage_path: str = "/var/lib/libvirt/isos"
    vm_storage_path: str = "/var/lib/libvirt/images"


settings = Settings()
