variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-east4"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-east4-c"
}

variable "machine_type" {
  description = "VM machine type"
  type        = string
  default     = "e2-medium"
}

variable "data_disk_size" {
  description = "Data disk size in GB (for DuckDB + flat files)"
  type        = number
  default     = 30
}

variable "massive_api_key" {
  description = "Massive.com API key"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude chat"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google API key for Gemini (market context)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ssh_user" {
  description = "SSH username for the VM"
  type        = string
  default     = "decay"
}

variable "ssh_pub_key_path" {
  description = "Path to SSH public key for VM access"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "app_repo_url" {
  description = "Git repository URL for the app"
  type        = string
  default     = "https://github.com/aikalima/decay_core.git"
}

variable "domain_name" {
  description = "Domain name for HTTPS (optional, leave empty to skip certbot)"
  type        = string
  default     = ""
}
