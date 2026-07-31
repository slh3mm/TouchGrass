const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';
import { json } from '@sveltejs/kit';

/** @type {import('./$types').RequestHandler} */
export async function GET(event) {
	const { url, params, request, fetch, cookies } = event;
	const searchParam = url.search ? `${url.search}&format=json` : '?format=json';
	return handleRequest(url, params, request, fetch, cookies, searchParam);
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ url, params, request, fetch, cookies }) {
	const searchParam = url.search ? `${url.search}` : '';
	return handleRequest(url, params, request, fetch, cookies, searchParam, true);
}

export async function PATCH({ url, params, request, fetch, cookies }) {
	const searchParam = url.search ? `${url.search}&format=json` : '?format=json';
	return handleRequest(url, params, request, fetch, cookies, searchParam, true);
}

export async function PUT({ url, params, request, fetch, cookies }) {
	const searchParam = url.search ? `${url.search}&format=json` : '?format=json';
	return handleRequest(url, params, request, fetch, cookies, searchParam, true);
}

export async function DELETE({ url, params, request, fetch, cookies }) {
	const searchParam = url.search ? `${url.search}&format=json` : '?format=json';
	return handleRequest(url, params, request, fetch, cookies, searchParam, true);
}

async function handleRequest(
	url: any,
	params: any,
	request: any,
	fetch: any,
	cookies: any,
	searchParam: string,
	requreTrailingSlash: boolean | undefined = false
) {
	const path = params.path;
	let targetUrl = `${endpoint}/api/${path}`;

	// Ensure the path ends with a trailing slash
	if (requreTrailingSlash && !targetUrl.endsWith('/')) {
		targetUrl += '/';
	}

	// Append query parameters to the path correctly
	targetUrl += searchParam; // This will add ?format=json or &format=json to the URL

	// Django's response token and CSRF cookie are related but not interchangeable.
	// Fetch both from the same request and forward the actual cookie secret.
	const sessionId = cookies.get('sessionid');
	const csrfResponse = await fetch(`${endpoint}/csrf/`, {
		headers: sessionId ? { Cookie: `sessionid=${sessionId}` } : undefined
	});
	if (!csrfResponse.ok) {
		return json({ error: 'CSRF token is missing or invalid' }, { status: 400 });
	}
	const csrfToken = (await csrfResponse.json()).csrfToken as string;
	const csrfCookieHeader = csrfResponse.headers.get('set-cookie') || '';
	const csrfCookie = /csrftoken=([^;]+)/.exec(csrfCookieHeader)?.[1];
	if (!csrfToken || !csrfCookie) {
		return json({ error: 'CSRF cookie is missing or invalid' }, { status: 400 });
	}

	const cookieHeader = `csrftoken=${csrfCookie}` + (sessionId ? `; sessionid=${sessionId}` : '');
	const forwardHeaders = new Headers(request.headers);
	forwardHeaders.delete('cookie');
	forwardHeaders.delete('x-csrftoken');
	forwardHeaders.delete('host');
	forwardHeaders.delete('content-length');
	forwardHeaders.set('X-CSRFToken', csrfToken);
	forwardHeaders.set('Cookie', cookieHeader);

	try {
		const response = await fetch(targetUrl, {
			method: request.method,
			headers: forwardHeaders,
			body:
				request.method !== 'GET' && request.method !== 'HEAD' ? await request.text() : undefined,
			credentials: 'include' // This line ensures cookies are sent with the request
		});

		if (response.status === 204) {
			return new Response(null, {
				status: 204,
				headers: response.headers
			});
		}

		const responseData = await response.arrayBuffer();
		// Create a new Headers object without the 'set-cookie' header
		const cleanHeaders = new Headers(response.headers);
		cleanHeaders.delete('set-cookie');

		return new Response(responseData, {
			status: response.status,
			headers: cleanHeaders
		});
	} catch (error) {
		console.error('Error forwarding request:', error);
		return json({ error: 'Internal Server Error' }, { status: 500 });
	}
}
