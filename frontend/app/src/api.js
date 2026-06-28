const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function handleResponse(response) {
  let json = null
  try {
    json = await response.json()
  } catch (e) {
    // non-JSON response - caller handles separately
  }

  if (!response.ok || (json && json.success === false)) {
    const message = json?.errors?.[0]?.detail || json?.message || `Request failed (${response.status})`
    throw new Error(message)
  }

  return json?.data
}

export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, {
    method: 'POST',
    body: formData,
  })
  return handleResponse(response)
}

export async function startPipelineRun(documentId, options = {}) {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/pipeline-runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: 'FULL_VERIFICATION',
      use_cache: true,
      use_rag: true,
      use_genai_safety_review: true,
      generate_report: false,
      priority: 'NORMAL',
      ...options,
    }),
  })
  return handleResponse(response)
}

export async function getDocumentStatus(documentId) {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/status`)
  return handleResponse(response)
}

export async function getVerificationResults(documentId) {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/verification-results`)
  return handleResponse(response)
}

export const TERMINAL_SUCCESS_STATUSES = ['SUCCEEDED', 'COMPLETED', 'VERIFIED']
export const TERMINAL_FAILURE_STATUSES = ['FAILED', 'CANCELLED', 'ERROR']