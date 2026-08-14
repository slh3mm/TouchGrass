import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const response = await fetch('/api/skylight/events/?format=json');
	if (!response.ok) {
		return {
			reviewData: {
				connected: false,
				last_sync_at: null,
				future_cutoff: null,
				counts: { all: 0, unreviewed: 0, trip: 0, not_trip: 0 },
				events: []
			}
		};
	}
	return { reviewData: await response.json() };
};
