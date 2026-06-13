/** In production, nginx proxies /api to the orchestrator (same origin). In dev, hit port 8000 directly. */
export const API = import.meta.env.PROD ? '' : 'http://127.0.0.1:8000';
