const configuredUrl = process.env.REACT_APP_BACKEND_URL?.trim().replace(/\/+$/, "");
const developmentUrl = "http://localhost:8001";
const productionUrl = "https://alphalense-backend.onrender.com";

export const API_BASE_URL = process.env.NODE_ENV === "development"
  ? developmentUrl
  : (configuredUrl === productionUrl ? configuredUrl : productionUrl);

export function apiUrl(path) {
  return `${API_BASE_URL}/api/${path.replace(/^\/+/, "")}`;
}
