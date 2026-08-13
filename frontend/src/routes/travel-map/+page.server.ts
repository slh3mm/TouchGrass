const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
import type { Country, Region, TravelProfile } from '$lib/types';
import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

export const load = (async (event) => {
	if (!event.locals.user) return redirect(302, '/login');

	const headers = { Cookie: `sessionid=${event.cookies.get('sessionid')}` };
	const [countriesResponse, profilesResponse, regionsResponse] = await Promise.all([
		event.fetch(`${endpoint}/api/countries/`, { headers }),
		event.fetch(`${endpoint}/api/travel-profiles/`, { headers }),
		event.fetch(`${endpoint}/api/travel-region-map/`, { headers })
	]);
	if (!countriesResponse.ok || !profilesResponse.ok || !regionsResponse.ok) {
		console.error('Failed to load the travel map');
		return { status: 500 };
	}

	return {
		props: {
			countries: (await countriesResponse.json()) as Country[],
			profiles: (await profilesResponse.json()) as TravelProfile[],
			regions: (await regionsResponse.json()) as Region[]
		}
	};
}) satisfies PageServerLoad;
