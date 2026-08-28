export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/analytics/stats`);
  if (!res.ok) throw new Error(`Stats request failed: ${res.statusText}`);
  return res.json();
}

export async function fetchVectors() {
  const res = await fetch(`${API_BASE}/analytics/vectors`);
  if (!res.ok) throw new Error(`Vectors request failed: ${res.statusText}`);
  return res.json();
}

export async function fetchTopics() {
  const res = await fetch(`${API_BASE}/analytics/topics`);
  if (!res.ok) throw new Error(`Topics request failed: ${res.statusText}`);
  return res.json();
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Upload failed with status ${res.status}`);
  }

  return res.json();
}
