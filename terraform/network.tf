# VPC network
resource "google_compute_network" "vpc" {
  name                    = "decay-vpc"
  auto_create_subnetworks = true
}

# Static external IP
resource "google_compute_address" "static_ip" {
  name   = "decay-static-ip"
  region = var.region
}

# Allow HTTP and HTTPS
resource "google_compute_firewall" "allow_http" {
  name    = "decay-allow-http"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["decay-web"]
}

# Allow SSH
resource "google_compute_firewall" "allow_ssh" {
  name    = "decay-allow-ssh"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Tighten this to your IP in production
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["decay-web"]
}
