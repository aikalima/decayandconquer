# Persistent SSD data disk for DuckDB + flat files
resource "google_compute_disk" "data" {
  name = "decay-data-disk"
  type = "pd-ssd"
  size = var.data_disk_size
  zone = var.zone

  labels = {
    app = "decay-core"
  }
}

# Main VM
resource "google_compute_instance" "decay" {
  name         = "decay-core"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["decay-web"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "decay-data"
    mode        = "READ_WRITE"
  }

  network_interface {
    network = google_compute_network.vpc.name
    access_config {
      nat_ip = google_compute_address.static_ip.address
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${file(var.ssh_pub_key_path)}"
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh", {
    app_repo_url = var.app_repo_url
    domain_name  = var.domain_name
    ssh_user     = var.ssh_user
  })

  service_account {
    scopes = ["cloud-platform"]
  }

  labels = {
    app = "decay-core"
    env = "production"
  }

  # Don't recreate VM if startup script changes — SSH in and re-run manually
  lifecycle {
    ignore_changes = [metadata_startup_script]
  }

  depends_on = [
    google_project_service.compute,
    google_secret_manager_secret_version.massive_api_key,
    google_secret_manager_secret_version.anthropic_api_key,
  ]
}
