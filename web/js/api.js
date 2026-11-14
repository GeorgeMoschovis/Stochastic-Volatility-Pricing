// Thin wrapper around fetch: JSON in, JSON out, readable error messages.

// FastAPI reports validation problems as a list of {loc, msg}; turn that into one sentence.
function describe(data) {
  if (!data || !data.detail) return null;
  if (typeof data.detail === "string") return data.detail;
  return data.detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join("; ");
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the server. Check that uvicorn is still running.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(describe(data) || `The server returned an error (${response.status}).`);
  }
  return data;
}

export function getJSON(path, params = {}) {
  return request(`${path}?${new URLSearchParams(params)}`);
}

export function postJSON(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
