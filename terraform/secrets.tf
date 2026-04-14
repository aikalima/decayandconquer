# Grant the default compute service account access to secrets
data "google_project" "current" {}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Massive.com API key
resource "google_secret_manager_secret" "massive_api_key" {
  secret_id = "massive-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "massive_api_key" {
  secret      = google_secret_manager_secret.massive_api_key.id
  secret_data = var.massive_api_key
}

# Anthropic API key
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

# Google API key (optional, for Gemini market context)
resource "google_secret_manager_secret" "google_api_key" {
  count     = var.google_api_key != "" ? 1 : 0
  secret_id = "google-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "google_api_key" {
  count       = var.google_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.google_api_key[0].id
  secret_data = var.google_api_key
}
