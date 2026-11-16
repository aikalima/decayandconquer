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

variable "massive_s3_access_key" {
  description = "Massive.com flat-files S3 access key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "massive_s3_secret_key" {
  description = "Massive.com flat-files S3 secret key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Legacy retained secret value, unused by the app; kept to avoid deleting existing secrets"
  type        = string
  sensitive   = true
}

variable "chat_model" {
  description = "Gemini model ID for Dacey's Google ADK agent"
  type        = string
  default     = "gemini-3.8-flash"
}

variable "market_context_model" {
  description = "Gemini model ID for Google Search-grounded market context"
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "google_api_key" {
  description = "Google API key for Gemini (Dacey and market context)"
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
