output "external_ip" {
  description = "Static external IP of the VM"
  value       = google_compute_address.static_ip.address
}

output "ssh_command" {
  description = "SSH command to connect to the VM"
  value       = "ssh ${var.ssh_user}@${google_compute_address.static_ip.address}"
}

output "app_url" {
  description = "Application URL"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${google_compute_address.static_ip.address}"
}

output "instance_name" {
  description = "VM instance name (for gcloud compute scp)"
  value       = google_compute_instance.decay.name
}
