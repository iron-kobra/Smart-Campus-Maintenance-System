const API = '/api'

export async function request(path, options = {}) {
  const token = localStorage.getItem('maintenance_token')
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.message || 'Something went wrong.')
    error.status = response.status
    throw error
  }
  return data
}

export async function requestBlob(path) {
  const token = localStorage.getItem('maintenance_token')
  const response = await fetch(`${API}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const error = new Error(data.message || 'Unable to load the attached image.')
    error.status = response.status
    throw error
  }
  return response.blob()
}
