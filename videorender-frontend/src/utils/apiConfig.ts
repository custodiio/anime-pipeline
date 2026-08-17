/**
 * Helper para obter a URL base da API no VideoRender.
 * Suporta o parâmetro ?api= na URL, variável de ambiente ou proxy Vercel.
 */
export function getApiBase(): string {
  if (typeof window === 'undefined') return '';
  const params = new URLSearchParams(window.location.search);
  const apiUrlParam = params.get('api');
  if (apiUrlParam) return apiUrlParam.replace(/\/$/, '');
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  return '';
}

export function getApiUrl(endpoint: string): string {
  const base = getApiBase();
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return base ? `${base}${cleanEndpoint}` : cleanEndpoint;
}
