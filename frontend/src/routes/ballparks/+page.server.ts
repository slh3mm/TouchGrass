import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ locals, fetch, cookies }) => {
	if (!locals.user) redirect(302, '/login');

	const headers = { Cookie: `sessionid=${cookies.get('sessionid') || ''}` };
	const [profilesResponse, visitsResponse] = await Promise.all([
		fetch(`${endpoint}/api/travel-profiles/?format=json`, { headers }),
		fetch(`${endpoint}/api/ballpark-visits/?format=json`, { headers })
	]);

	return {
		profiles: profilesResponse.ok ? await profilesResponse.json() : [],
		visits: visitsResponse.ok ? await visitsResponse.json() : []
	};
};
