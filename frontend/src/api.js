export async function requestJSON(url, options, fetchImpl = fetch) {
  let response
  try {
    response = await fetchImpl(url, options)
  } catch (e) {
    return { ok: false, status: 0, data: null, error: e && e.message ? e.message : String(e) }
  }
  let data = null
  try {
    data = await response.json()
  } catch (e) {
    data = null
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' && data.detail !== undefined ? data.detail : null
    let error
    if (typeof detail === 'string') {
      error = detail
    } else if (detail !== null && detail !== undefined) {
      try {
        error = JSON.stringify(detail)
      } catch (e) {
        error = String(detail)
      }
    } else if (response.status > 0) {
      error = `HTTP ${response.status}`
    } else {
      error = 'Invalid response'
    }
    return { ok: false, status: response.status, data, error }
  }
  if (data === null || data === undefined) {
    return { ok: false, status: response.status, data: null, error: 'Invalid response' }
  }
  return { ok: true, status: response.status, data, error: null }
}
