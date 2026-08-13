export type TravelSearchKind = 'country' | 'state' | 'province';

export type TravelSearchItem = {
	id: string;
	targetId: string;
	kind: TravelSearchKind;
	label: string;
	code: string;
	subtitle: string;
	keywords: string[];
	colors: string[];
	flagUrl?: string;
};

export const countrySearchAliases: Record<string, string[]> = {
	AE: ['UAE'],
	CI: ['Ivory Coast'],
	CZ: ['Czech Republic'],
	GB: ['UK', 'Britain', 'Great Britain'],
	KR: ['South Korea'],
	KP: ['North Korea'],
	RU: ['Russia'],
	US: ['USA', 'United States of America']
};

export function normalizeTravelSearch(value: string) {
	return value
		.normalize('NFD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLocaleLowerCase()
		.replace(/[^a-z0-9]+/g, ' ')
		.trim();
}

function editDistance(left: string, right: string) {
	const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
	for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
		let diagonal = previous[0];
		previous[0] = leftIndex;
		for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
			const above = previous[rightIndex];
			previous[rightIndex] = Math.min(
				previous[rightIndex] + 1,
				previous[rightIndex - 1] + 1,
				diagonal + (left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1)
			);
			diagonal = above;
		}
	}
	return previous[right.length];
}

export function travelSearchScore(item: TravelSearchItem, rawQuery: string) {
	const query = normalizeTravelSearch(rawQuery);
	if (!query) return 0;

	const label = normalizeTravelSearch(item.label);
	const code = normalizeTravelSearch(item.code);
	const fields = [label, code, item.subtitle, ...item.keywords]
		.map(normalizeTravelSearch)
		.filter(Boolean);

	if (label === query) return 0;
	if (code === query) return 2;
	if (label.startsWith(query)) return 10 + Math.min(label.length - query.length, 8);
	if (label.split(' ').some((word) => word.startsWith(query))) return 22;
	if (label.includes(query)) return 30 + label.indexOf(query);
	if (fields.some((field) => field.startsWith(query))) return 38;
	if (fields.some((field) => field.includes(query))) return 46;

	if (query.length >= 3) {
		const threshold = query.length >= 6 ? 2 : 1;
		const candidates = fields.flatMap((field) => [field, ...field.split(' ')]);
		const distance = Math.min(...candidates.map((candidate) => editDistance(candidate, query)));
		if (distance <= threshold) return 60 + distance;
	}

	return Number.POSITIVE_INFINITY;
}

export function matchesTravelSearch(item: TravelSearchItem, query: string) {
	return Number.isFinite(travelSearchScore(item, query));
}

export function travelSearchSuggestions(items: TravelSearchItem[], query: string, limit = 8) {
	if (!normalizeTravelSearch(query)) return [];
	return items
		.map((item) => ({ item, score: travelSearchScore(item, query) }))
		.filter((result) => Number.isFinite(result.score))
		.sort((left, right) => left.score - right.score || left.item.label.localeCompare(right.item.label))
		.slice(0, limit)
		.map((result) => result.item);
}
