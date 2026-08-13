const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
import type { Country, Region, TravelProfile } from '$lib/types';
import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

export const load = (async (event) => {
	if (!event.locals.user) {
		return redirect(302, '/login');
	} else {
		const headers = { Cookie: `sessionid=${event.cookies.get('sessionid')}` };
		const wantsMap = event.url.searchParams.get('view') === 'map';
		const [countriesResponse, profilesResponse, regionsResponse] = await Promise.all([
			event.fetch(`${endpoint}/api/countries/`, { headers }),
			event.fetch(`${endpoint}/api/travel-profiles/`, { headers }),
			wantsMap ? event.fetch(`${endpoint}/api/travel-region-map/`, { headers }) : null
		]);
		if (!countriesResponse.ok || !profilesResponse.ok || (regionsResponse && !regionsResponse.ok)) {
			console.error('Failed to fetch countries');
			return { status: 500 };
		} else {
			const countries = (await countriesResponse.json()) as Country[];
			const profiles = (await profilesResponse.json()) as TravelProfile[];
			const regions = regionsResponse ? ((await regionsResponse.json()) as Region[]) : [];
			return {
				props: {
					countries,
					profiles,
					regions
				}
			};
		}
	}
}) satisfies PageServerLoad;
