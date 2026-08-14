import type { PageServerLoad } from './$types';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

async function fetchJson<T>(
	fetcher: typeof globalThis.fetch,
	url: string,
	headers: HeadersInit,
	fallback: T
): Promise<T> {
	try {
		const response = await fetcher(url, { headers });
		if (!response.ok) {
			console.error(`Trips loader request failed: ${url} (${response.status})`);
			return fallback;
		}
		return (await response.json()) as T;
	} catch (error) {
		console.error(`Trips loader could not read: ${url}`, error);
		return fallback;
	}
}

export const load: PageServerLoad = async ({ fetch, cookies }) => {
	const headers = { Cookie: `sessionid=${cookies.get('sessionid') || ''}` };
	const [trips, profiles, skylight] = await Promise.all([
		fetchJson<any[]>(fetch, `${endpoint}/api/trips/?format=json`, headers, []),
		fetchJson<any[]>(fetch, `${endpoint}/api/travel-profiles/?format=json`, headers, []),
		fetchJson<any | null>(fetch, `${endpoint}/api/skylight/?format=json`, headers, null)
	]);

	return { trips, profiles, skylight };
};
