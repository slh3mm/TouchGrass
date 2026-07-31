import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const [tripsResponse, profilesResponse] = await Promise.all([
		fetch('/api/trips/?format=json'),
		fetch('/api/travel-profiles/?format=json')
	]);
	return {
		trips: tripsResponse.ok ? await tripsResponse.json() : [],
		profiles: profilesResponse.ok ? await profilesResponse.json() : []
	};
};
