const configuredUrl = process.env.REACT_APP_BACKEND_URL?.trim().replace(/\/+$/, "");
const fallbackUrl = typeof window !== "undefined" ? window.location.origin : "";
const developmentUrl = "http://localhost:8001";

export const API_BASE_URL = process.env.NODE_ENV === "development"
  ? developmentUrl
  : (configuredUrl || fallbackUrl);

export function apiUrl(path) {
  return `${API_BASE_URL}/api/${path.replace(/^\/+/, "")}`;
}
