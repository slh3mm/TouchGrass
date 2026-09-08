import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const serverEndpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

const emptyStats = {
	visited_country_count: 0,
	visited_region_count: 0,
	visited_city_count: 0
};

export const load = (async (event) => {
	if (!event.locals.user) redirect(302, '/login');

	const response = await event.fetch(`${serverEndpoint}/api/travel-stats/?format=json`, {
		headers: { Cookie: `sessionid=${event.cookies.get('sessionid') || ''}` }
	});

	return {
		props: {
			stats: response.ok ? await response.json() : emptyStats
		}
	};
}) satisfies PageServerLoad;
