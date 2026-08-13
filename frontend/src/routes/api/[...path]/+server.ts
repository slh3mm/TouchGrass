import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';
const CSRF_TTL_MS = 30 * 60 * 1000;
const MAX_CSRF_SESSIONS = 512;

type CsrfMaterial = { token: string; cookie: string; expiresAt: number };
const csrfBySession = new Map<string, CsrfMaterial>();

export const trailingSlash = 'ignore';

export const GET: RequestHandler = (event) => handleRequest(event, false, true);
export const POST: RequestHandler = (event) => handleRequest(event, true, true);
export const PATCH: RequestHandler = (event) => handleRequest(event, true, true);
export const PUT: RequestHandler = (event) => handleRequest(event, true, true);
export const DELETE: RequestHandler = (event) => handleRequest(event, true, true);

function rejectCrossSiteMutation(request: Request, url: URL) {
	const fetchSite = request.headers.get('sec-fetch-site');
	if (fetchSite === 'cross-site') return true;
	const origin = request.headers.get('origin');
	return Boolean(origin && origin !== url.origin);
}

function pruneCsrfCache() {
	const now = Date.now();
	for (const [key, value] of csrfBySession) {
		if (value.expiresAt <= now) csrfBySession.delete(key);
	}
	while (csrfBySession.size >= MAX_CSRF_SESSIONS) {
		const oldestKey = csrfBySession.keys().next().value;
		if (!oldestKey) break;
		csrfBySession.delete(oldestKey);
	}
}

async function getCsrfMaterial(
	sessionId: string,
	fetch: typeof globalThis.fetch,
	forceRefresh = false
) {
	if (!forceRefresh) {
		const cached = csrfBySession.get(sessionId);
		if (cached && cached.expiresAt > Date.now()) return cached;
	}

	const response = await fetch(`${endpoint}/csrf/`, {
		headers: { Cookie: `sessionid=${sessionId}` }
	});
	if (!response.ok) return null;

	const token = String((await response.json()).csrfToken || '');
	const cookie = /csrftoken=([^;]+)/.exec(response.headers.get('set-cookie') || '')?.[1] || '';
	if (!token || !cookie) return null;

	pruneCsrfCache();
	const material = { token, cookie, expiresAt: Date.now() + CSRF_TTL_MS };
	csrfBySession.set(sessionId, material);
	return material;
}

async function handleRequest(
	{ url, params, request, fetch, cookies }: Parameters<RequestHandler>[0],
	unsafe: boolean,
	requireTrailingSlash: boolean
) {
	if (unsafe && rejectCrossSiteMutation(request, url)) {
		return json({ error: 'Cross-site API requests are not allowed' }, { status: 403 });
	}

	const sessionId = cookies.get('sessionid');
	if (!sessionId) return json({ error: 'Authentication is required' }, { status: 401 });

	let targetPath = `${endpoint}/api/${params.path}`;
	if (requireTrailingSlash && !targetPath.endsWith('/')) targetPath += '/';
	const targetUrl = new URL(targetPath);
	for (const [key, value] of url.searchParams) targetUrl.searchParams.append(key, value);
	if (request.method !== 'POST' && !targetUrl.searchParams.has('format')) {
		targetUrl.searchParams.set('format', 'json');
	}

	const body = unsafe ? await request.text() : undefined;
	const cachedCsrf = sessionId ? csrfBySession.get(sessionId) : undefined;
	const usedCachedCsrf = Boolean(unsafe && cachedCsrf && cachedCsrf.expiresAt > Date.now());

	try {
		const forward = async (forceCsrfRefresh = false) => {
			const headers = new Headers(request.headers);
			headers.delete('cookie');
			headers.delete('x-csrftoken');
			headers.delete('host');
			headers.delete('content-length');

			let cookieHeader = `sessionid=${sessionId}`;
			if (unsafe) {
				const csrf = await getCsrfMaterial(sessionId, fetch, forceCsrfRefresh);
				if (!csrf) return null;
				cookieHeader = `csrftoken=${csrf.cookie}; ${cookieHeader}`;
				headers.set('X-CSRFToken', csrf.token);
			}
			headers.set('Cookie', cookieHeader);

			return fetch(targetUrl, {
				method: request.method,
				headers,
				body,
				credentials: 'include'
			});
		};

		let response = await forward();
		if (!response) return json({ error: 'Could not initialize CSRF protection' }, { status: 400 });

		// Django rotates/rejects CSRF material independently of the session. Refresh
		// once before returning a genuine authorization failure to the client.
		if (unsafe && usedCachedCsrf && response.status === 403) {
			await response.body?.cancel();
			csrfBySession.delete(sessionId);
			response = await forward(true);
			if (!response) return json({ error: 'Could not refresh CSRF protection' }, { status: 400 });
		}

		const headers = new Headers(response.headers);
		headers.delete('set-cookie');
		headers.delete('content-length');
		headers.delete('content-encoding');
		headers.delete('transfer-encoding');
		return new Response(response.status === 204 ? null : response.body, {
			status: response.status,
			headers
		});
	} catch (error) {
		console.error('Error forwarding request:', error);
		return json({ error: 'Internal Server Error' }, { status: 500 });
	}
}
