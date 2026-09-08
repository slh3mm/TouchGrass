<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { onDestroy, tick } from 'svelte';
	import type { Country, ProfileTravelVisit, Region, TravelProfile } from '$lib/types';
	import type { PageData } from './$types';
	import { addToast } from '$lib/toasts';
	import MapIcon from '~icons/mdi/map-outline';
	import GridIcon from '~icons/mdi/view-grid-outline';
	import PlusIcon from '~icons/mdi/plus';
	import CloseIcon from '~icons/mdi/close';
	import CheckIcon from '~icons/mdi/check';
	import AirplaneIcon from '~icons/mdi/airplane';
	import { ManageProfilesButton, ProfileBar, ProfileChip } from '$lib/components/touchgrass';
	import LazyFlag from '$lib/components/travel/LazyFlag.svelte';
	import TravelSearch from '$lib/components/travel/TravelSearch.svelte';
	import type { TravelSearchItem } from '$lib/components/travel/travelSearch';
	import {
		countrySearchAliases,
		matchesTravelSearch,
		normalizeTravelSearch
	} from '$lib/components/travel/travelSearch';

	export let data: PageData;

	let countries: Country[] = data.props?.countries || [];
	let profiles: TravelProfile[] = data.props?.profiles || [];
	let allRegions: Region[] = data.props?.regions || [];
	let editingProfileId =
		profiles.find((profile) => profile.is_default)?.id || profiles[0]?.id || '';
	let selectedProfileIds = new Set(profiles.map((profile) => profile.id));
	let displayMode: 'atlas' | 'map' = $page.url.searchParams.get('view') === 'map' ? 'map' : 'atlas';
	let atlasSection: 'countries' | 'us' | 'ca' = 'countries';
	let showProfiles = false;
	let selectedCountry: Country | null = null;
	let countryRegions: Region[] = [];
	let loadingRegions = false;
	let selectedHistoryRegion: Region | null = null;
	let visitHistory: ProfileTravelVisit[] = [];
	let loadingHistory = false;
	let savingHistory = false;
	let historyDate = new Date().toISOString().slice(0, 10);
	let historyEndDate = historyDate;
	let historyNotes = '';
	let historySection: HTMLElement;
	let countryInspector: HTMLElement;
	let newProfile = { name: '', color: '#fb8072', avatar: '' };
	let savingProfile = false;
	let savingVisitKey = '';
	let searchQuery = $page.url.searchParams.get('q') || '';
	let searchSelection: TravelSearchItem | null = null;
	let searchFocusTimer: ReturnType<typeof setTimeout> | null = null;
	let shareUsername = '';
	let sharingCalendar = false;
	let countryRenderLimit = 72;
	let countryBatchTimer: ReturnType<typeof setTimeout> | null = null;
	const subdivisionCountryCodes = new Set(['US', 'CA']);
	let mapRegions: Region[] = [];
	let requestedDisplayMode: 'atlas' | 'map' = 'atlas';
	let TravelProfileMapComponent: any = null;
	let mapComponentPromise: Promise<void> | null = null;
	let subdivisionCatalogPromise: Promise<void> | null = null;
	let subdivisionSearchRegions: Array<{
		id: string;
		name: string;
		code: string;
		countryCode: string;
	}> = [];
	type TripChoice = {
		id: string;
		title: string;
		start_date: string;
		end_date: string;
		destinations?: Array<{ country: number; region: string | null }>;
	};
	let tripChoices: TripChoice[] = [];
	let tripPickerOpen = false;
	let loadingTripChoices = false;
	let addingTripId = '';
	let lastMapSelection: { country: Country; region: Region } | null = null;
	let showAcceptedPlaces = false;
	let mapTripId = '';

	function ensureSubdivisionCatalog() {
		if (!browser || subdivisionSearchRegions.length || subdivisionCatalogPromise) {
			return subdivisionCatalogPromise || Promise.resolve();
		}
		subdivisionCatalogPromise = fetch('/geo/us-ca-admin1.compact.geojson')
			.then((response) => (response.ok ? response.json() : null))
			.then((collection) => {
				subdivisionSearchRegions = (collection?.features || []).map((feature: any) => ({
					id: feature.properties.id,
					name: feature.properties.name,
					code: feature.properties.code,
					countryCode: feature.properties.countryCode
				}));
			});
		return subdivisionCatalogPromise;
	}

	function ensureMapComponent() {
		if (!browser || TravelProfileMapComponent || mapComponentPromise) return;
		mapComponentPromise = Promise.all([
			import('$lib/components/map/TravelProfileMap.svelte'),
			ensureSubdivisionCatalog()
		]).then(([module]) => {
			TravelProfileMapComponent = module.default;
		});
	}

	$: requestedDisplayMode =
		$page.url.pathname === '/travel-map' || $page.url.searchParams.get('view') === 'map'
			? 'map'
			: 'atlas';
	$: if (displayMode !== requestedDisplayMode) displayMode = requestedDisplayMode;
	$: if (displayMode === 'map') ensureMapComponent();
	$: if (browser && displayMode === 'atlas') ensureSubdivisionCatalog();

	$: selectedProfiles = profiles.filter((profile) => selectedProfileIds.has(profile.id));
	$: primaryProfile =
		profiles.find((profile) => profile.id === editingProfileId) ?? profiles[0] ?? null;
	$: inspectedProfileIds = selectedHistoryRegion?.profile_ids || selectedCountry?.profile_ids || [];
	$: jointProfile =
		profiles.find((profile) => profile.name.trim().toLowerCase() === 'joint') ?? null;
	$: stateCountProfileIds = new Set([
		...(primaryProfile ? [primaryProfile.id] : []),
		...(primaryProfile && jointProfile && primaryProfile.id !== jointProfile.id
			? [jointProfile.id]
			: [])
	]);
	$: mapRegions = allRegions.filter((region) =>
		subdivisionCountryCodes.has(region.id.split('-')[0])
	);
	$: countrySearchItems = countries.map(
		(country): TravelSearchItem => ({
			id: `country-${country.country_code}`,
			targetId: country.country_code,
			kind: 'country',
			label: country.name,
			code: country.country_code,
			subtitle:
				[country.capital, country.subregion].filter(Boolean).join(' · ') || country.country_code,
			keywords: [
				country.capital,
				country.subregion,
				...(countrySearchAliases[country.country_code] || [])
			].filter(Boolean) as string[],
			colors: profiles
				.filter((profile) => country.profile_ids.includes(profile.id))
				.map((profile) => profile.color),
			flagUrl: `/flags/${country.country_code.toLowerCase()}.png`
		})
	);
	$: regionSearchItems = subdivisionSearchRegions.map((region): TravelSearchItem => {
		const profileIds = mapRegions.find((item) => item.id === region.id)?.profile_ids || [];
		return {
			id: `region-${region.id}`,
			targetId: region.id,
			kind: region.countryCode === 'CA' ? 'province' : 'state',
			label: region.name,
			code: region.code,
			subtitle: `${region.countryCode === 'CA' ? 'Canada' : 'United States'} · ${region.id}`,
			keywords: [region.id, region.countryCode === 'CA' ? 'Canada' : 'USA United States'],
			colors: profiles
				.filter((profile) => profileIds.includes(profile.id))
				.map((profile) => profile.color)
		};
	});
	$: atlasRegionItems = regionSearchItems.filter((item) =>
		atlasSection === 'us'
			? item.kind === 'state'
			: atlasSection === 'ca'
				? item.kind === 'province'
				: false
	);
	$: travelSearchItems = [...countrySearchItems, ...regionSearchItems];
	$: if (historyEndDate < historyDate) historyEndDate = historyDate;
	$: if (
		searchSelection &&
		normalizeTravelSearch(searchQuery) !== normalizeTravelSearch(searchSelection.label)
	)
		clearSearchFocus();
	$: filteredCountries = searchQuery.trim()
		? countries.filter((country) => {
				const item = countrySearchItems.find(
					(candidate) => candidate.targetId === country.country_code
				);
				return item ? matchesTravelSearch(item, searchQuery) : false;
			})
		: countries;
	$: filteredAtlasRegions = searchQuery.trim()
		? atlasRegionItems.filter((item) => matchesTravelSearch(item, searchQuery))
		: atlasRegionItems;
	$: renderedCountries = searchQuery.trim()
		? filteredCountries
		: filteredCountries.slice(0, countryRenderLimit);
	$: if (
		browser &&
		displayMode === 'atlas' &&
		atlasSection === 'countries' &&
		countryRenderLimit < filteredCountries.length
	)
		scheduleCountryBatch();
	$: visitedCount = countries.filter((country) =>
		country.profile_ids.some((id) => selectedProfileIds.has(id))
	).length;
	$: visitedStateCount = new Set(
		allRegions
			.filter(
				(region) =>
					region.id.startsWith('US-') &&
					region.id !== 'US-DC' &&
					region.profile_ids.some((id) => stateCountProfileIds.has(id))
			)
			.map((region) => region.id)
	).size;

	function csrfToken() {
		return (
			document.cookie
				.split('; ')
				.find((row) => row.startsWith('csrftoken='))
				?.split('=')[1] || ''
		);
	}

	function applyProfilePrecedence(profileIds: string[]) {
		const uniqueIds = [...new Set(profileIds)];
		const jointIds = new Set(
			profiles
				.filter((profile) => profile.name.trim().toLowerCase() === 'joint')
				.map((profile) => profile.id)
		);
		const jointMatches = uniqueIds.filter((id) => jointIds.has(id));
		return jointMatches.length ? jointMatches : uniqueIds;
	}

	function profileGradient(profileIds: string[], muted = '#d5d0c8') {
		const visibleIds = applyProfilePrecedence(profileIds);
		const colors = profiles
			.filter((profile) => visibleIds.includes(profile.id))
			.map((profile) => profile.color);
		if (!colors.length) return muted;
		if (colors.length === 1) return colors[0];
		const stops = colors.flatMap((color, index) => {
			const start = (index / colors.length) * 100;
			const end = ((index + 1) / colors.length) * 100;
			return [`${color} ${start}%`, `${color} ${end}%`];
		});
		return `linear-gradient(90deg, ${stops.join(', ')})`;
	}

	function visibleProfileIds(country: Country) {
		return applyProfilePrecedence(country.profile_ids.filter((id) => selectedProfileIds.has(id)));
	}

	function selectSearchResult(event: CustomEvent<TravelSearchItem>) {
		clearSearchFocus();
		searchSelection = event.detail;
		if (displayMode === 'map') {
			searchFocusTimer = setTimeout(() => {
				searchSelection = null;
				searchFocusTimer = null;
			}, 3500);
		}
		if (displayMode === 'atlas') {
			atlasSection =
				event.detail.kind === 'country' ? 'countries' : event.detail.kind === 'state' ? 'us' : 'ca';
			const prefix = event.detail.kind === 'country' ? 'country-card' : 'region-card';
			tick().then(() =>
				document
					.getElementById(`${prefix}-${event.detail.targetId}`)
					?.scrollIntoView({ behavior: 'smooth', block: 'center' })
			);
		}
	}

	async function selectAtlasSection(section: 'countries' | 'us' | 'ca') {
		atlasSection = section;
		searchQuery = '';
		clearSearchFocus();
		if (section !== 'countries') await ensureSubdivisionCatalog();
	}

	function clearSearchFocus() {
		if (searchFocusTimer) clearTimeout(searchFocusTimer);
		searchFocusTimer = null;
		searchSelection = null;
	}

	function scheduleCountryBatch() {
		if (countryBatchTimer) return;
		countryBatchTimer = setTimeout(() => {
			countryBatchTimer = null;
			countryRenderLimit = Math.min(countryRenderLimit + 48, filteredCountries.length);
		}, 220);
	}

	onDestroy(() => {
		if (searchFocusTimer) clearTimeout(searchFocusTimer);
		if (countryBatchTimer) clearTimeout(countryBatchTimer);
		if (browser) document.documentElement.classList.remove('tg-inspector-open');
	});

	$: if (browser)
		document.documentElement.classList.toggle(
			'tg-inspector-open',
			Boolean(selectedCountry || tripPickerOpen)
		);

	function editAs(profile: TravelProfile) {
		editingProfileId = profile.id;
	}

	async function shareCalendar() {
		if (!shareUsername.trim()) return;
		sharingCalendar = true;
		try {
			const response = await fetch('/api/travel-profiles/share/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify({ username: shareUsername.trim() })
			});
			const result = await response.json();
			if (!response.ok) return addToast('error', result.error || 'Could not share calendar');
			addToast('success', `Calendar shared with ${result.shared_with}`);
			shareUsername = '';
		} catch {
			addToast('error', 'Could not share calendar');
		} finally {
			sharingCalendar = false;
		}
	}

	async function toggleCountryVisit(country: Country, profile = primaryProfile) {
		if (!profile) return;
		if (savingVisitKey === `country-${country.country_code}-${profile.id}`) return;
		const visited = country.profile_ids.includes(profile.id);
		savingVisitKey = `country-${country.country_code}-${profile.id}`;
		try {
			const response = await fetch(
				`/api/travel-profiles/${profile.id}/countries/${country.country_code}/`,
				{
					method: visited ? 'DELETE' : 'PUT',
					headers: { 'X-CSRFToken': csrfToken() }
				}
			);
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${country.name}`);
				return;
			}
			const result = await response.json().catch(() => ({ visited: !visited }));
			const nowVisited = Boolean(result.visited);
			country.profile_ids = applyProfilePrecedence(
				nowVisited
					? [...new Set([...country.profile_ids, profile.id])]
					: country.profile_ids.filter((id) => id !== profile.id)
			);
			countries = [...countries];
			if (!nowVisited) {
				allRegions = allRegions.map((region) =>
					region.id.startsWith(`${country.country_code}-`)
						? { ...region, profile_ids: region.profile_ids.filter((id) => id !== profile.id) }
						: region
				);
				countryRegions = countryRegions.map((region) => ({
					...region,
					profile_ids: region.profile_ids.filter((id) => id !== profile.id)
				}));
			}
			addToast(
				'success',
				result.source === 'trip'
					? `${country.name} remains visited from ${profile.name}'s trip history`
					: `${country.name} ${nowVisited ? 'added to' : 'removed from'} ${profile.name}`,
				5000,
				profile.color
			);
		} catch {
			addToast('error', `Could not update ${country.name}`);
		} finally {
			savingVisitKey = '';
		}
	}

	async function loadVisitHistory(country: Country, region: Region | null = null) {
		selectedHistoryRegion = region;
		visitHistory = [];
		loadingHistory = true;
		try {
			const params = new URLSearchParams({ country: country.country_code });
			if (region) params.set('region', region.id);
			const response = await fetch(`/api/travel-visit-history/?${params}`);
			if (response.ok) {
				const result = await response.json();
				const items: ProfileTravelVisit[] = Array.isArray(result) ? result : result.results || [];
				visitHistory = region ? items.filter((visit) => visit.region === region.id) : items;
			} else {
				addToast('error', `Could not load ${region?.name || country.name} visit history`);
			}
		} finally {
			loadingHistory = false;
		}
		if (region) {
			await tick();
			await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
			countryInspector.scrollTop = Math.max(0, historySection.offsetTop - 16);
		}
	}

	function openRegionHistory(event: MouseEvent, region: Region) {
		(event.currentTarget as HTMLButtonElement).blur();
		if (selectedCountry) loadVisitHistory(selectedCountry, region);
	}

	async function openCountry(country: Country, historyRegionId = '') {
		selectedCountry = country;
		countryRegions = [];
		selectedHistoryRegion = null;
		visitHistory = [];
		const supportsSubdivisions = subdivisionCountryCodes.has(country.country_code);
		loadingRegions = supportsSubdivisions;
		if (supportsSubdivisions) {
			try {
				const response = await fetch(`/api/${country.country_code}/regions/`);
				if (response.ok) countryRegions = await response.json();
			} finally {
				loadingRegions = false;
			}
		}
		const historyRegion = historyRegionId
			? countryRegions.find((region) => region.id === historyRegionId) || null
			: null;
		let resolvedHistoryRegion = historyRegion;
		if (historyRegionId && !resolvedHistoryRegion) {
			const response = await fetch(`/api/regions/${encodeURIComponent(historyRegionId)}/`);
			if (response.ok) {
				const region: Region = await response.json();
				if (region.id.split('-')[0] === country.country_code) {
					resolvedHistoryRegion = region;
					countryRegions = [...countryRegions, region];
					if (!allRegions.some((item) => item.id === region.id))
						allRegions = [...allRegions, region];
				}
			}
		}
		if (historyRegionId && !resolvedHistoryRegion) {
			addToast(
				'error',
				'Could not resolve that state or province. Country history was not loaded.'
			);
			selectedCountry = null;
			return;
		}
		await loadVisitHistory(country, resolvedHistoryRegion);
	}

	function atlasRegion(item: TravelSearchItem): Region | null {
		const catalog = subdivisionSearchRegions.find((region) => region.id === item.targetId);
		const country = countries.find((candidate) => candidate.country_code === catalog?.countryCode);
		if (!catalog || !country) return null;
		const existing = allRegions.find((region) => region.id === catalog.id);
		return {
			id: catalog.id,
			name: catalog.name,
			country: String(country.id),
			country_name: country.name,
			latitude: existing?.latitude || 0,
			longitude: existing?.longitude || 0,
			num_cities: existing?.num_cities || 0,
			profile_ids: [...(existing?.profile_ids || [])]
		};
	}

	async function openAtlasRegion(item: TravelSearchItem) {
		const countryCode = item.kind === 'state' ? 'US' : 'CA';
		const country = countries.find((candidate) => candidate.country_code === countryCode);
		if (country) await openCountry(country, item.targetId);
	}

	async function toggleAtlasRegion(item: TravelSearchItem) {
		const region = atlasRegion(item);
		if (region) await toggleRegionVisit(region);
	}

	async function addVisitHistory() {
		if (!selectedCountry || !primaryProfile || !historyDate || savingHistory) return;
		savingHistory = true;
		try {
			const response = await fetch('/api/travel-visit-history/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify({
					profile: primaryProfile.id,
					country: selectedCountry.id,
					region: selectedHistoryRegion?.id || null,
					visit_date: historyDate,
					end_date: historyEndDate,
					notes: historyNotes.trim()
				})
			});
			if (!response.ok) {
				const result = await response.json().catch(() => null);
				addToast('error', result ? JSON.stringify(result) : 'Could not add this visit');
				return;
			}
			const created: ProfileTravelVisit = await response.json();
			visitHistory = [created, ...visitHistory].sort((a, b) =>
				b.visit_date.localeCompare(a.visit_date)
			);
			historyNotes = '';
			if (!selectedCountry.profile_ids.includes(primaryProfile.id)) {
				selectedCountry.profile_ids = applyProfilePrecedence([
					...selectedCountry.profile_ids,
					primaryProfile.id
				]);
				countries = [...countries];
			}
			if (selectedHistoryRegion && !selectedHistoryRegion.profile_ids.includes(primaryProfile.id)) {
				selectedHistoryRegion.profile_ids = applyProfilePrecedence([
					...selectedHistoryRegion.profile_ids,
					primaryProfile.id
				]);
				const globalRegion = allRegions.find((region) => region.id === selectedHistoryRegion?.id);
				if (globalRegion) globalRegion.profile_ids = [...selectedHistoryRegion.profile_ids];
				countryRegions = [...countryRegions];
				allRegions = globalRegion ? [...allRegions] : [...allRegions, selectedHistoryRegion];
			}
			addToast(
				'success',
				`${created.region_name || created.country_name} visit added for ${primaryProfile.name}`,
				5000,
				primaryProfile.color
			);
		} finally {
			savingHistory = false;
		}
	}

	async function deleteVisitHistory(visit: ProfileTravelVisit) {
		if (visit.read_only) return;
		const response = await fetch(`/api/travel-visit-history/${visit.id}/`, {
			method: 'DELETE',
			headers: { 'X-CSRFToken': csrfToken() }
		});
		if (response.ok) {
			visitHistory = visitHistory.filter((item) => item.id !== visit.id);
			addToast('success', 'Visit date removed', 5000, visit.profile_color);
		}
	}

	function formatVisitDates(visit: ProfileTravelVisit) {
		const format = (value: string) =>
			new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'short',
				day: 'numeric'
			});
		return visit.end_date && visit.end_date !== visit.visit_date
			? `${format(visit.visit_date)} – ${format(visit.end_date)}`
			: format(visit.visit_date);
	}

	async function toggleRegionVisit(region: Region, profile = primaryProfile) {
		if (!profile) return;
		if (savingVisitKey === `region-${region.id}-${profile.id}`) return;
		const visited = region.profile_ids.includes(profile.id);
		savingVisitKey = `region-${region.id}-${profile.id}`;
		try {
			const response = await fetch(`/api/travel-profiles/${profile.id}/regions/${region.id}/`, {
				method: visited ? 'DELETE' : 'PUT',
				headers: { 'X-CSRFToken': csrfToken() }
			});
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${region.name}`);
				return;
			}
			const result = await response.json().catch(() => ({ visited: !visited }));
			const nowVisited = Boolean(result.visited);
			region.profile_ids = applyProfilePrecedence(
				nowVisited
					? [...new Set([...region.profile_ids, profile.id])]
					: region.profile_ids.filter((id) => id !== profile.id)
			);
			countryRegions = [...countryRegions];
			const globalRegion = allRegions.find((item) => item.id === region.id);
			if (globalRegion && globalRegion !== region)
				globalRegion.profile_ids = [...region.profile_ids];
			allRegions = globalRegion ? [...allRegions] : [...allRegions, region];
			const regionCountry = countries.find(
				(country) => country.country_code === region.id.split('-')[0]
			);
			if (nowVisited && regionCountry && !regionCountry.profile_ids.includes(profile.id)) {
				regionCountry.profile_ids = applyProfilePrecedence([
					...regionCountry.profile_ids,
					profile.id
				]);
				countries = [...countries];
			}
			addToast(
				'success',
				result.source === 'trip'
					? `${region.name} remains visited from ${profile.name}'s trip history`
					: `${region.name} updated for ${profile.name}`,
				5000,
				profile.color
			);
		} catch {
			addToast('error', `Could not update ${region.name}`);
		} finally {
			savingVisitKey = '';
		}
	}

	async function createProfile() {
		if (!newProfile.name.trim()) return;
		savingProfile = true;
		try {
			const response = await fetch('/api/travel-profiles/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify(newProfile)
			});
			if (!response.ok) return;
			const profile: TravelProfile = await response.json();
			profiles = [...profiles, profile];
			selectedProfileIds = new Set([...selectedProfileIds, profile.id]);
			newProfile = { name: '', color: '#fb8072', avatar: '' };
		} finally {
			savingProfile = false;
		}
	}

	async function updateProfile(profile: TravelProfile) {
		const response = await fetch(`/api/travel-profiles/${profile.id}/`, {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
			body: JSON.stringify({ name: profile.name, color: profile.color, avatar: profile.avatar })
		});
		if (response.ok) profiles = [...profiles];
	}

	async function deleteProfile(profile: TravelProfile) {
		if (
			profiles.length === 1 ||
			!confirm(`Delete ${profile.name}? Their manual travel history will also be removed.`)
		)
			return;
		const response = await fetch(`/api/travel-profiles/${profile.id}/`, {
			method: 'DELETE',
			headers: { 'X-CSRFToken': csrfToken() }
		});
		if (response.ok) {
			profiles = profiles.filter((item) => item.id !== profile.id);
			selectedProfileIds.delete(profile.id);
			selectedProfileIds = new Set(selectedProfileIds);
		}
	}

	async function handleMapCountry(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) {
			lastMapSelection = null;
			await toggleCountryVisit(country);
		}
	}

	async function handleMapCountryInspect(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) await openCountry(country);
	}

	async function handleMapRegion(event: CustomEvent<{ regionId: string }>) {
		if (!subdivisionCountryCodes.has(event.detail.regionId?.split('-')[0])) return;
		let region =
			allRegions.find((item) => item.id === event.detail.regionId) ??
			countryRegions.find((item) => item.id === event.detail.regionId);
		if (!region?.name) {
			const response = await fetch(`/api/regions/${event.detail.regionId}/`);
			if (response.ok) {
				const fullRegion: Region = await response.json();
				if (region) fullRegion.profile_ids = [...region.profile_ids];
				region = fullRegion;
			}
		}
		if (region) {
			await toggleRegionVisit(region);
			const country = countries.find((item) => item.country_code === region?.id.split('-')[0]);
			if (country) lastMapSelection = { country, region };
		}
	}

	async function handleMapRegionInspect(event: CustomEvent<{ regionId: string }>) {
		const countryCode = event.detail.regionId?.split('-')[0];
		if (!subdivisionCountryCodes.has(countryCode)) return;
		const country = countries.find((item) => item.country_code === countryCode);
		if (country) await openCountry(country, event.detail.regionId);
	}

	async function openTripPicker() {
		if (!selectedCountry) return;
		tripPickerOpen = true;
		loadingTripChoices = true;
		try {
			const response = await fetch('/api/trips/?format=json');
			tripChoices = response.ok ? await response.json() : [];
		} finally {
			loadingTripChoices = false;
		}
	}

	async function ensureTripChoices() {
		if (tripChoices.length || loadingTripChoices) return;
		loadingTripChoices = true;
		try {
			const response = await fetch('/api/trips/?format=json');
			tripChoices = response.ok ? await response.json() : [];
		} finally {
			loadingTripChoices = false;
		}
	}

	$: if (browser && displayMode === 'map' && showAcceptedPlaces) ensureTripChoices();

	async function addLocationToTrip(trip: TripChoice) {
		if (!selectedCountry || addingTripId) return;
		addingTripId = trip.id;
		try {
			const response = await fetch(`/api/trips/${trip.id}/destinations/`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify({
					country: selectedCountry.id,
					region: selectedHistoryRegion?.id || null
				})
			});
			if (!response.ok) {
				const result = await response.json().catch(() => ({}));
				throw new Error(result.detail || 'Could not add this location to the trip.');
			}
			addToast(
				'success',
				`${selectedHistoryRegion?.name || selectedCountry.name} added to ${trip.title}`,
				5000,
				primaryProfile?.color
			);
			tripPickerOpen = false;
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not add this location to the trip.'
			);
		} finally {
			addingTripId = '';
		}
	}

	function createTripWithLocation() {
		if (!selectedCountry) return;
		const params = new URLSearchParams({
			new: '1',
			country: String(selectedCountry.id),
			country_code: selectedCountry.country_code,
			place: selectedHistoryRegion?.name || selectedCountry.name
		});
		if (selectedHistoryRegion) params.set('region', selectedHistoryRegion.id);
		if (primaryProfile) params.set('profile', primaryProfile.id);
		goto(`/trips?${params}`);
	}
</script>

<svelte:head>
	<title>Travel Passport - TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link
		href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<main class="travel-shell">
	<div class="travel-backdrop"></div>
	<div class="dashboard">
		<header class="hero">
			<div class="hero-copy">
				<h1>{displayMode === 'map' ? 'Travel Map' : 'Travel Passport'}</h1>
				<TravelSearch
					items={travelSearchItems}
					bind:query={searchQuery}
					placeholder="Find a country, state, or province"
					on:select={selectSearchResult}
					on:clear={clearSearchFocus}
					on:dismiss={clearSearchFocus}
				/>
			</div>
			<div
				class="journey-stat"
				aria-label={`${visitedCount} of ${countries.length} countries visited; ${primaryProfile?.name || 'selected profile'} has visited ${visitedStateCount} of 50 states`}
			>
				<div class="journey-stat-line primary">
					<strong>{visitedCount}</strong><span>of {countries.length} countries</span>
				</div>
				<div class="journey-stat-line secondary">
					<strong>{visitedStateCount}</strong><span>of 50 states</span>
				</div>
			</div>
		</header>

		<ProfileBar
			label="Choose the profile to edit"
			helper={`Editing visits for ${primaryProfile?.name || 'no profile selected'}`}
		>
			{#each profiles as profile}
				<ProfileChip
					name={profile.name}
					color={profile.color}
					avatar={profile.avatar}
					active={editingProfileId === profile.id}
					on:select={() => editAs(profile)}
				/>
			{/each}
			<ManageProfilesButton on:click={() => (showProfiles = true)} />
		</ProfileBar>

		{#if displayMode === 'map'}
			<section class="map-panel">
				<div class="places-layer-controls">
					<label
						><input type="checkbox" bind:checked={showAcceptedPlaces} /><span>Places</span></label
					>{#if showAcceptedPlaces}<select bind:value={mapTripId} aria-label="Filter Places by trip"
							><option value="">Every trip</option>{#each tripChoices as trip}<option
									value={trip.id}>{trip.title}</option
								>{/each}</select
						>{/if}
				</div>
				{#if TravelProfileMapComponent}
					<svelte:component
						this={TravelProfileMapComponent}
						{countries}
						regions={mapRegions}
						{profiles}
						{selectedProfileIds}
						showPlaces={showAcceptedPlaces}
						placeTripId={mapTripId}
						focusTarget={searchSelection}
						on:countrySelect={handleMapCountry}
						on:countryInspect={handleMapCountryInspect}
						on:regionSelect={handleMapRegion}
						on:regionInspect={handleMapRegionInspect}
					/>
				{:else}
					<div class="loading-state">Loading the travel map…</div>
				{/if}
				{#if lastMapSelection}
					<div class="map-selection-bar">
						<div>
							<strong>{lastMapSelection.region.name}</strong><span
								>{lastMapSelection.country.name}</span
							>
						</div>
						<button
							on:click={() =>
								lastMapSelection &&
								openCountry(lastMapSelection.country, lastMapSelection.region.id)}
							>Visit dates &amp; trips</button
						>
						<button on:click={() => lastMapSelection && openCountry(lastMapSelection.country)}
							>Country actions</button
						>
						<button
							class="dismiss"
							aria-label="Dismiss selected state actions"
							on:click={() => (lastMapSelection = null)}><CloseIcon /></button
						>
					</div>
				{/if}
			</section>
		{:else}
			<section class="atlas-panel">
				<div class="passport-tabs" aria-label="Travel passport sections">
					<button
						class:active={atlasSection === 'countries'}
						on:click={() => selectAtlasSection('countries')}>Countries</button
					>
					<button class:active={atlasSection === 'us'} on:click={() => selectAtlasSection('us')}
						>US states</button
					>
					<button class:active={atlasSection === 'ca'} on:click={() => selectAtlasSection('ca')}
						>Canada provinces</button
					>
				</div>
				<div class="atlas-heading">
					<div>
						<span class="eyebrow"
							>{atlasSection === 'countries' ? 'Flag atlas' : 'Regional passport'}</span
						>
						<h2>
							{atlasSection === 'countries'
								? `${filteredCountries.length} destinations`
								: `${filteredAtlasRegions.length} ${atlasSection === 'us' ? 'states' : 'provinces & territories'}`}
						</h2>
					</div>
					<span>Open any place to see trip dates</span>
				</div>
				{#if atlasSection === 'countries'}
					<div class="flag-grid">
						{#each renderedCountries as country, index}
							{@const visibleIds = visibleProfileIds(country)}
							<article
								id={`country-card-${country.country_code}`}
								class:unvisited={!visibleIds.length}
								class:search-target={searchSelection?.targetId === country.country_code}
								class="country-tile"
							>
								<button
									class="flag-button"
									on:click={() => openCountry(country)}
									aria-label={`Open ${country.name}`}
								>
									<LazyFlag
										src={`/flags/${country.country_code.toLowerCase()}.png`}
										alt={`${country.name} flag`}
										countryCode={country.country_code}
										eager={index < 12}
									/>
									<span class="color-band" style={`background:${profileGradient(visibleIds)}`}
									></span>
								</button>
								<div class="country-label">
									<button on:click={() => openCountry(country)}>{country.name}</button><button
										disabled={savingVisitKey ===
											`country-${country.country_code}-${primaryProfile?.id}`}
										class:checked={primaryProfile &&
											country.profile_ids.includes(primaryProfile.id)}
										class="visit-check"
										on:click={() => toggleCountryVisit(country)}
										title={`Toggle ${primaryProfile?.name}'s visit`}><CheckIcon /></button
									>
								</div>
							</article>
						{/each}
					</div>
				{:else}
					<div class="subdivision-grid">
						{#each filteredAtlasRegions as item}
							{@const region = atlasRegion(item)}
							{@const visibleIds = (region?.profile_ids || []).filter((id) =>
								selectedProfileIds.has(id)
							)}
							<article
								id={`region-card-${item.targetId}`}
								class:unvisited={!visibleIds.length}
								class:search-target={searchSelection?.targetId === item.targetId}
								class="subdivision-tile"
								style={`--subdivision-fill:${profileGradient(visibleIds)}`}
							>
								<button class="subdivision-main" on:click={() => openAtlasRegion(item)}
									><span>{item.code}</span><strong>{item.label}</strong><small
										>{visibleIds.length ? 'View trip history' : 'No visits yet'}</small
									></button
								>
								<button
									class:checked={primaryProfile &&
										(region?.profile_ids || []).includes(primaryProfile.id)}
									class="visit-check"
									disabled={savingVisitKey === `region-${item.targetId}-${primaryProfile?.id}`}
									on:click={() => toggleAtlasRegion(item)}
									aria-label={`Toggle ${item.label} for ${primaryProfile?.name}`}
									><CheckIcon /></button
								>
							</article>
						{/each}
					</div>
				{/if}
			</section>
		{/if}
	</div>
</main>

{#if selectedCountry}
	<div
		class="inspector-backdrop"
		on:click={() => (selectedCountry = null)}
		role="presentation"
	></div>
	<aside class="country-inspector" bind:this={countryInspector}>
		<button
			class="close"
			aria-label="Close country details"
			on:click={() => (selectedCountry = null)}><CloseIcon /></button
		>
		<img
			src={`/flags/${selectedCountry.country_code.toLowerCase()}.png`}
			alt={`${selectedCountry.name} flag`}
			width="110"
			height="70"
			decoding="async"
		/>
		<span class="eyebrow"
			>{selectedHistoryRegion
				? selectedCountry.country_code === 'US'
					? 'State'
					: 'Province or territory'
				: selectedCountry.subregion}</span
		>
		<h2>{selectedHistoryRegion?.name || selectedCountry.name}</h2>
		{#if selectedHistoryRegion}
			<p class="parent-country">{selectedCountry.name}</p>
		{/if}
		<div class="inspector-band" style={`background:${profileGradient(inspectedProfileIds)}`}></div>
		<button class="add-to-trip" on:click={openTripPicker}
			><AirplaneIcon /> Add {selectedHistoryRegion?.name || selectedCountry.name} to a trip</button
		>
		<span class="action-label"
			>{selectedHistoryRegion
				? selectedCountry.country_code === 'US'
					? 'State visit for each profile'
					: 'Province visit for each profile'
				: 'Country visit for each profile'}</span
		>
		<div class="country-profile-actions">
			{#each profiles as profile}<button
					disabled={selectedHistoryRegion
						? savingVisitKey === `region-${selectedHistoryRegion.id}-${profile.id}`
						: savingVisitKey === `country-${selectedCountry.country_code}-${profile.id}`}
					class:visited={inspectedProfileIds.includes(profile.id)}
					style={`--profile-color:${profile.color}`}
					on:click={() =>
						selectedHistoryRegion
							? toggleRegionVisit(selectedHistoryRegion, profile)
							: selectedCountry && toggleCountryVisit(selectedCountry, profile)}
					><span>{profile.avatar || profile.name.slice(0, 1).toUpperCase()}</span><strong
						>{profile.name}</strong
					><small
						>{inspectedProfileIds.includes(profile.id) ? 'Remove visit' : 'Mark visited'}</small
					></button
				>{/each}
		</div>
		<section class="visit-history" bind:this={historySection}>
			<header>
				<div>
					<span class="eyebrow">Visit history</span>
					<h3>{selectedHistoryRegion?.name || selectedCountry.name}</h3>
				</div>
			</header>
			<div class="history-form">
				<label class="date-field"
					><span>Start</span><input
						type="date"
						bind:value={historyDate}
						aria-label="Visit start date"
					/></label
				>
				<label class="date-field"
					><span>End</span><input
						type="date"
						bind:value={historyEndDate}
						min={historyDate}
						aria-label="Visit end date"
					/></label
				>
				<input
					bind:value={historyNotes}
					maxlength="500"
					placeholder="Optional note"
					aria-label="Visit note"
				/>
				<button
					disabled={savingHistory ||
						!historyDate ||
						!historyEndDate ||
						historyEndDate < historyDate ||
						!primaryProfile}
					on:click={addVisitHistory}>Add for {primaryProfile?.name}</button
				>
			</div>
			{#if loadingHistory}
				<div class="loading-state">Loading visit history…</div>
			{:else if visitHistory.length}
				<div class="history-list">
					{#each visitHistory as visit}
						<article style={`--history-color:${visit.profile_color}`}>
							<span>{visit.profile_avatar || visit.profile_name.slice(0, 1).toUpperCase()}</span>
							<div>
								<strong>{visit.source_title || formatVisitDates(visit)}</strong>
								<small
									>{formatVisitDates(visit)} · {visit.profile_name}{visit.region_name
										? ` · ${visit.region_name}`
										: ''}</small
								>
								{#if visit.source === 'skylight'}<em>Skylight trip</em>{/if}
								{#if visit.notes}<p>{visit.notes}</p>{/if}
							</div>
							{#if !visit.read_only}<button
									aria-label={`Delete ${visit.visit_date} visit`}
									on:click={() => deleteVisitHistory(visit)}>Delete</button
								>{/if}
						</article>
					{/each}
				</div>
			{:else}
				<p class="empty-history">No dated visits yet.</p>
			{/if}
		</section>
		{#if subdivisionCountryCodes.has(selectedCountry.country_code) && !selectedHistoryRegion}
			<div class="region-heading">
				<h3>{selectedCountry.country_code === 'US' ? 'States visited' : 'Provinces visited'}</h3>
				<span>{countryRegions.length}</span>
			</div>
			{#if loadingRegions}
				<div class="loading-state">Loading regions…</div>
			{:else}
				<div class="state-grid">
					{#each countryRegions as region}
						<div
							class:visited={region.profile_ids.some((id) => selectedProfileIds.has(id))}
							class="region-card"
							style={`--region-fill:${profileGradient(region.profile_ids)}`}
						>
							<button class="region-name" on:click={(event) => openRegionHistory(event, region)}
								><span></span><span>{region.name}<small>View dates</small></span></button
							>
							<button
								class="region-toggle"
								disabled={savingVisitKey === `region-${region.id}-${primaryProfile?.id}`}
								on:click={() => toggleRegionVisit(region)}
								aria-label={`Toggle ${region.name} for ${primaryProfile?.name}`}
								><CheckIcon /></button
							>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
		{#if subdivisionCountryCodes.has(selectedCountry.country_code)}
			<button
				class="details-link"
				on:click={() => goto(`/worldtravel/${selectedCountry?.country_code}`)}
				>Open full country details</button
			>
		{/if}
	</aside>
{/if}

{#if tripPickerOpen && selectedCountry}
	<button
		class="trip-picker-backdrop"
		type="button"
		aria-label="Close trip picker"
		on:click={() => (tripPickerOpen = false)}
	></button>
	<section class="trip-picker" role="dialog" aria-modal="true" aria-label="Add location to a trip">
		<header>
			<div>
				<span class="eyebrow">Add destination</span>
				<h2>{selectedHistoryRegion?.name || selectedCountry.name}</h2>
			</div>
			<button aria-label="Close trip picker" on:click={() => (tripPickerOpen = false)}
				><CloseIcon /></button
			>
		</header>
		<button class="new-trip-choice" on:click={createTripWithLocation}
			><PlusIcon /><span
				><strong>Create a new trip</strong><small
					>The destination and active profile will carry over.</small
				></span
			></button
		>
		{#if loadingTripChoices}
			<p class="loading-state">Loading trips…</p>
		{:else if tripChoices.length}
			<div class="trip-choice-list">
				{#each tripChoices as trip}
					<button disabled={Boolean(addingTripId)} on:click={() => addLocationToTrip(trip)}
						><span
							><strong>{trip.title}</strong><small>{trip.start_date} – {trip.end_date}</small></span
						><span>{addingTripId === trip.id ? 'Adding…' : 'Add'}</span></button
					>
				{/each}
			</div>
		{:else}
			<p class="empty-history">No trips yet. Create one above.</p>
		{/if}
	</section>
{/if}

{#if showProfiles}
	<div class="modal-backdrop" role="presentation" on:click={() => (showProfiles = false)}></div>
	<section class="profile-modal">
		<header>
			<div>
				<span class="eyebrow">Household</span>
				<h2>Travel profiles</h2>
			</div>
			<button aria-label="Close travel profiles" on:click={() => (showProfiles = false)}
				><CloseIcon /></button
			>
		</header>
		<div class="profile-editor-list">
			{#each profiles as profile}<div class="profile-editor">
					<input
						type="color"
						bind:value={profile.color}
						aria-label={`${profile.name} color`}
					/><input
						bind:value={profile.avatar}
						maxlength="8"
						class="avatar-input"
						aria-label="Avatar"
					/><input bind:value={profile.name} aria-label="Profile name" /><button
						on:click={() => updateProfile(profile)}>Save</button
					><button class="delete" on:click={() => deleteProfile(profile)}>Delete</button>
				</div>{/each}
		</div>
		<div class="share-calendar">
			<h3>Share this household calendar</h3>
			<p>
				Enter another TouchGrass username to share profiles, calendar entries, and travel history.
			</p>
			<div>
				<input bind:value={shareUsername} placeholder="TouchGrass username" /><button
					disabled={sharingCalendar || !shareUsername.trim()}
					on:click={shareCalendar}>Share</button
				>
			</div>
		</div>
		<div class="new-profile">
			<h3>Add a profile</h3>
			<div>
				<input type="color" bind:value={newProfile.color} aria-label="New profile color" /><input
					bind:value={newProfile.avatar}
					maxlength="8"
					class="avatar-input"
					placeholder="🙂"
				/><input bind:value={newProfile.name} placeholder="Profile name" /><button
					disabled={savingProfile || !newProfile.name.trim()}
					on:click={createProfile}><PlusIcon /> Add</button
				>
			</div>
		</div>
	</section>
{/if}

<style>
	.travel-shell {
		position: relative;
		min-height: calc(100dvh - var(--tg-navbar-height));
		color: var(--tg-ink);
		font-family: var(--tg-font-body);
	}
	.travel-backdrop {
		position: fixed;
		inset: 0;
		background: var(--tg-canvas);
	}
	.dashboard {
		position: relative;
		z-index: 1;
		width: min(var(--tg-content-width), 100%);
		margin: auto;
		padding: clamp(1rem, 2vw, 2.25rem);
	}
	.hero {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 2rem;
		padding: 1.5rem 1.5rem 2rem;
	}
	.hero-copy {
		display: grid;
		gap: 1.2rem;
		min-width: min(520px, 100%);
	}
	h1,
	h2 {
		margin: 0.1rem 0;
		font-family: var(--tg-font-display);
		font-weight: 400;
	}
	h1 {
		font-size: clamp(3.2rem, 5vw, 6rem);
		line-height: 1;
	}
	.eyebrow {
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	.journey-stat {
		display: grid;
		justify-items: end;
		gap: 0.05rem;
		white-space: nowrap;
	}
	.journey-stat-line {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
	}
	.journey-stat strong {
		font-family: 'Ovo', serif;
		font-size: 4rem;
		font-weight: 400;
	}
	.journey-stat-line.secondary strong {
		font-size: 1.65rem;
	}
	.journey-stat-line.secondary span {
		color: var(--tg-ink-muted);
		font-size: 0.86rem;
	}
	.atlas-panel,
	.map-panel {
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		padding: 1.25rem;
		background: var(--tg-surface-glass);
		backdrop-filter: blur(var(--tg-blur-panel));
		box-shadow: var(--tg-shadow-card);
	}
	.map-panel {
		position: relative;
		overflow: hidden;
	}
	.atlas-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		margin-bottom: 1rem;
	}
	.atlas-heading h2 {
		font-size: 2.2rem;
	}
	.atlas-heading > span {
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	.places-layer-controls {
		position: absolute;
		z-index: 14;
		top: 2rem;
		right: 2rem;
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.places-layer-controls label,
	.places-layer-controls select {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 40px;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-control);
		font-size: 0.78rem;
		font-weight: 850;
	}
	.places-layer-controls input {
		accent-color: var(--tg-action);
	}
	.flag-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(135px, 1fr));
		gap: 0.85rem;
	}
	.country-tile {
		min-width: 0;
		content-visibility: auto;
		contain-intrinsic-size: 135px 128px;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-card);
		background: var(--tg-surface);
		overflow: hidden;
		transition:
			transform var(--tg-motion-fast),
			box-shadow var(--tg-motion-fast);
	}
	.country-tile:hover {
		transform: translateY(-2px);
		box-shadow: var(--tg-shadow-card);
	}
	.country-tile.search-target {
		outline: 3px solid var(--tg-action);
		outline-offset: 3px;
		box-shadow: 0 12px 30px color-mix(in srgb, var(--tg-action) 24%, transparent);
	}
	.flag-button {
		position: relative;
		display: block;
		width: 100%;
		height: 82px;
		padding: 0;
		border: 0;
		background: var(--tg-canvas-deep);
		cursor: pointer;
		overflow: hidden;
	}
	.flag-button :global(.lazy-flag) {
		width: 100%;
		height: 100%;
	}
	.country-tile.unvisited :global(.lazy-flag) {
		filter: grayscale(1);
		opacity: 0.3;
	}
	.color-band {
		position: absolute;
		inset: auto 0 0;
		height: 6px;
	}
	.country-label {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.62rem 0.65rem;
	}
	.country-label > button:first-child {
		min-width: 0;
		flex: 1;
		overflow: hidden;
		border: 0;
		background: none;
		color: var(--tg-ink);
		text-align: left;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.78rem;
		font-weight: 600;
		cursor: pointer;
	}
	.visit-check {
		display: grid;
		width: 25px;
		height: 25px;
		place-items: center;
		border: 1px solid var(--tg-border-strong);
		border-radius: 50%;
		background: var(--tg-surface);
		color: transparent;
		cursor: pointer;
	}
	.visit-check.checked {
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.visit-check :global(svg) {
		width: 0.85rem;
	}
	.inspector-backdrop {
		position: fixed;
		inset: 0;
		z-index: calc(var(--tg-layer-sidebar) - 1);
		background: var(--tg-scrim);
	}
	.modal-backdrop {
		position: fixed;
		inset: 0;
		z-index: calc(var(--tg-layer-modal) - 1);
		background: transparent;
	}
	.country-inspector {
		position: fixed;
		z-index: var(--tg-layer-sidebar);
		top: 0;
		right: 0;
		width: min(560px, 100%);
		height: 100dvh;
		padding: 2rem;
		border-left: 1px solid var(--tg-border);
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-overlay);
		overflow: auto;
		font-family: var(--tg-font-body);
		isolation: isolate;
	}
	.country-inspector > img {
		width: 110px;
		height: 70px;
		margin-bottom: 1.25rem;
		border-radius: 10px;
		object-fit: cover;
		box-shadow: var(--tg-shadow-control);
	}
	.country-inspector h2,
	.profile-modal h2 {
		color: var(--tg-ink-strong);
		font-size: 3rem;
	}
	.country-inspector .eyebrow {
		color: var(--tg-ink-muted);
	}
	.close {
		position: absolute;
		top: 1.25rem;
		right: 1.25rem;
		display: grid;
		width: 40px;
		height: 40px;
		place-items: center;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		cursor: pointer;
	}
	.inspector-band {
		height: 10px;
		margin: 1rem 0;
		border-radius: 999px;
	}
	.details-link {
		width: 100%;
		padding: 0.85rem 1rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 700;
		cursor: pointer;
	}
	.visit-check:disabled,
	.state-grid button:disabled,
	.history-form button:disabled {
		opacity: 0.55;
		cursor: wait;
	}
	.region-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin: 2rem 0 0.75rem;
		color: var(--tg-ink);
	}
	.region-heading h3 {
		color: var(--tg-ink-strong);
		font-weight: 700;
	}
	.state-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.5rem;
	}
	.region-card {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 42px;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-surface);
		overflow: hidden;
	}
	.region-name,
	.region-toggle {
		border: 0;
		background: transparent;
		color: var(--tg-ink);
		cursor: pointer;
	}
	.region-name {
		display: flex;
		align-items: stretch;
		gap: 0.55rem;
		padding: 0.65rem;
		text-align: left;
		font-weight: 700;
	}
	.region-name > span:first-child {
		width: 8px;
		flex: 0 0 auto;
		border-radius: 99px;
		background: var(--tg-border-strong);
	}
	.region-card.visited .region-name > span:first-child {
		background: var(--region-fill);
	}
	.region-name > span:last-child {
		min-width: 0;
	}
	.region-name small {
		display: block;
		margin-top: 0.12rem;
		color: var(--tg-ink-muted);
		font-size: 0.66rem;
		font-weight: 700;
	}
	.region-toggle {
		display: grid;
		place-items: center;
		border-left: 1px solid var(--tg-border);
	}
	.region-toggle :global(svg) {
		width: 1rem;
		color: transparent;
	}
	.region-card.visited .region-toggle :global(svg) {
		color: var(--tg-ink);
	}
	.loading-state {
		color: var(--tg-ink-muted);
	}
	.details-link {
		margin-top: 1.5rem;
	}
	.visit-history {
		margin-top: 1.5rem;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 16px;
		background: var(--tg-surface-glass);
	}
	.visit-history header {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 0.8rem;
	}
	.visit-history h3 {
		margin: 0.12rem 0 0;
		color: var(--tg-ink-strong);
		font-size: 1.25rem;
	}
	.history-form {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		align-items: end;
		gap: 0.55rem;
	}
	.date-field {
		display: grid;
		gap: 0.2rem;
	}
	.date-field > span {
		color: var(--tg-ink-muted);
		font-size: 0.66rem;
		font-weight: 800;
	}
	.history-form > input,
	.history-form > button {
		grid-column: 1/-1;
	}
	.history-form input {
		width: 100%;
		min-width: 0;
		padding: 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.history-form button {
		min-height: 42px;
		padding: 0.65rem 0.8rem;
		border: 0;
		border-radius: 10px;
		background: var(--tg-action);
		color: var(--tg-action-text);
		font-weight: 800;
		cursor: pointer;
	}
	.history-list {
		display: grid;
		gap: 0.45rem;
		margin-top: 0.8rem;
	}
	.history-list article {
		display: grid;
		grid-template-columns: 34px minmax(0, 1fr) auto;
		align-items: start;
		gap: 0.6rem;
		padding: 0.6rem;
		border: 1px solid var(--tg-border);
		border-left: 5px solid var(--history-color);
		border-radius: 11px;
		background: var(--tg-surface);
	}
	.history-list article > span {
		display: grid;
		width: 32px;
		height: 32px;
		place-items: center;
		border-radius: 50%;
		background: color-mix(in srgb, var(--history-color) 62%, white);
		color: #171717;
		font-weight: 800;
	}
	.history-list strong,
	.history-list small {
		display: block;
	}
	.history-list small {
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
	}
	.history-list p {
		margin: 0.25rem 0 0;
		color: var(--tg-ink);
		font-size: 0.78rem;
	}
	.history-list article > button {
		align-self: center;
		border: 0;
		background: transparent;
		color: var(--tg-danger);
		font-size: 0.7rem;
		font-weight: 800;
		cursor: pointer;
	}
	.empty-history {
		margin: 0.8rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	:global(html.tg-inspector-open),
	:global(html.tg-inspector-open body) {
		overflow: hidden !important;
	}
	.country-profile-actions {
		display: grid;
		gap: 0.5rem;
		margin: 1rem 0;
	}
	.country-profile-actions button {
		display: grid;
		grid-template-columns: 36px 1fr auto;
		align-items: center;
		gap: 0.65rem;
		padding: 0.65rem 0.8rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		text-align: left;
		cursor: pointer;
	}
	.country-profile-actions button > span {
		display: grid;
		width: 34px;
		height: 34px;
		place-items: center;
		border-radius: 50%;
		background: color-mix(in srgb, var(--profile-color) 55%, var(--tg-surface));
	}
	.country-profile-actions button small {
		color: var(--tg-ink-muted);
		font-weight: 700;
	}
	.country-profile-actions button.visited {
		border-color: var(--profile-color);
		box-shadow: inset 5px 0 var(--profile-color);
	}
	.country-profile-actions button:disabled {
		opacity: 0.55;
		cursor: wait;
	}
	.history-list em {
		display: inline-flex;
		margin-top: 0.3rem;
		padding: 0.18rem 0.4rem;
		border-radius: 999px;
		background: color-mix(in srgb, var(--history-color) 18%, var(--tg-surface));
		color: var(--tg-ink);
		font-size: 0.62rem;
		font-style: normal;
		font-weight: 800;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.passport-tabs {
		display: flex;
		gap: 0.4rem;
		margin-bottom: 1.2rem;
		padding: 0.3rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		width: max-content;
		max-width: 100%;
		overflow: auto;
		scrollbar-width: none;
	}
	.passport-tabs::-webkit-scrollbar {
		display: none;
	}
	.passport-tabs button {
		flex: 0 0 auto;
		padding: 0.58rem 0.9rem;
		border: 0;
		border-radius: 999px;
		background: transparent;
		color: var(--tg-ink-muted);
		font: inherit;
		font-size: 0.78rem;
		font-weight: 800;
		cursor: pointer;
	}
	.passport-tabs button.active {
		background: var(--tg-surface);
		color: var(--tg-ink-strong);
		box-shadow: var(--tg-shadow-control);
	}
	.subdivision-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
		gap: 0.75rem;
	}
	.subdivision-tile {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 42px;
		min-height: 92px;
		border: 1px solid var(--tg-border);
		border-left: 8px solid var(--subdivision-fill);
		border-radius: 15px;
		background: var(--tg-surface);
		overflow: hidden;
		transition:
			transform 0.18s,
			box-shadow 0.18s;
	}
	.subdivision-tile:hover {
		transform: translateY(-2px);
		box-shadow: var(--tg-shadow-card);
	}
	.subdivision-tile.unvisited {
		border-left-color: var(--tg-border-strong);
		opacity: 0.72;
	}
	.subdivision-tile.search-target {
		outline: 3px solid var(--tg-action);
		outline-offset: 3px;
	}
	.subdivision-main {
		display: grid;
		grid-template-columns: 44px minmax(0, 1fr);
		grid-template-rows: auto auto;
		align-content: center;
		column-gap: 0.7rem;
		padding: 0.8rem;
		border: 0;
		background: transparent;
		color: var(--tg-ink);
		text-align: left;
		cursor: pointer;
	}
	.subdivision-main > span {
		grid-row: 1/3;
		display: grid;
		width: 44px;
		height: 44px;
		place-items: center;
		border-radius: 12px;
		background: var(--subdivision-fill);
		color: #171717;
		font-weight: 900;
	}
	.subdivision-tile.unvisited .subdivision-main > span {
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
	}
	.subdivision-main strong {
		align-self: end;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.subdivision-main small {
		color: var(--tg-ink-muted);
		font-size: 0.68rem;
	}
	.subdivision-tile > .visit-check {
		align-self: center;
	}
	.profile-modal {
		position: fixed;
		z-index: var(--tg-layer-modal);
		top: 50%;
		left: 50%;
		width: min(760px, calc(100% - 2rem));
		max-height: 88dvh;
		padding: 1.5rem;
		transform: translate(-50%, -50%);
		overflow: auto;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		opacity: 1;
		isolation: isolate;
		box-shadow: var(--tg-shadow-overlay);
	}
	.profile-modal header {
		display: flex;
		justify-content: space-between;
		align-items: start;
	}
	.profile-modal header button {
		display: grid;
		width: 40px;
		height: 40px;
		padding: 0;
		place-items: center;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		cursor: pointer;
	}
	.profile-editor-list {
		display: grid;
		gap: 0.6rem;
		margin: 1.25rem 0;
	}
	.profile-editor,
	.new-profile > div {
		display: grid;
		grid-template-columns: 44px 60px 1fr auto auto;
		gap: 0.5rem;
	}
	.profile-editor input,
	.new-profile input {
		min-width: 0;
		padding: 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
	}
	.profile-editor input[type='color'],
	.new-profile input[type='color'] {
		padding: 4px;
	}
	.profile-editor button,
	.new-profile button {
		border: 0;
		border-radius: 10px;
		padding: 0.6rem 0.8rem;
		background: var(--tg-action);
		color: var(--tg-action-text);
		cursor: pointer;
	}
	.profile-editor .delete {
		background: var(--tg-danger);
		color: var(--tg-danger-text);
	}
	.new-profile,
	.share-calendar {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--tg-border);
	}
	.new-profile > div {
		grid-template-columns: 44px 60px 1fr auto;
	}
	.new-profile button {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}
	.share-calendar p {
		color: var(--tg-ink-muted);
		font-size: 0.85rem;
	}
	.share-calendar > div {
		display: flex;
		gap: 0.5rem;
	}
	.share-calendar input {
		flex: 1;
		min-width: 0;
		padding: 0.7rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
	}
	.share-calendar button {
		padding: 0.7rem 1rem;
		border: 0;
		border-radius: 10px;
		background: var(--tg-action);
		color: var(--tg-action-text);
		font-weight: 700;
	}
	.map-selection-bar {
		position: absolute;
		z-index: 12;
		right: 2rem;
		bottom: 2rem;
		left: 2rem;
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 16px;
		background: var(--tg-overlay-surface);
		box-shadow: var(--tg-shadow-overlay);
	}
	.map-selection-bar > div {
		min-width: 0;
		flex: 1;
	}
	.map-selection-bar strong,
	.map-selection-bar span {
		display: block;
	}
	.map-selection-bar span {
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
	}
	.map-selection-bar button,
	.add-to-trip {
		min-height: 40px;
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
		cursor: pointer;
	}
	.map-selection-bar .dismiss {
		display: grid;
		width: 40px;
		padding: 0;
		place-items: center;
		border-radius: 50%;
	}
	.map-selection-bar :global(svg) {
		width: 18px;
	}
	.add-to-trip {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: center;
		gap: 0.45rem;
		margin: 0.8rem 0;
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.action-label {
		display: block;
		margin: 1rem 0 0.35rem;
		color: var(--tg-ink-muted);
		font-size: 0.68rem;
		font-weight: 850;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.trip-picker-backdrop {
		position: fixed;
		inset: 0;
		z-index: calc(var(--tg-layer-modal) - 1);
		width: 100%;
		height: 100%;
		border: 0;
		background: var(--tg-scrim);
	}
	.trip-picker {
		position: fixed;
		z-index: var(--tg-layer-modal);
		top: 50%;
		left: 50%;
		width: min(560px, calc(100% - 2rem));
		max-height: 82dvh;
		padding: 1.4rem;
		transform: translate(-50%, -50%);
		overflow: auto;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-overlay-surface);
		box-shadow: var(--tg-shadow-overlay);
	}
	.trip-picker header {
		display: flex;
		align-items: start;
		justify-content: space-between;
	}
	.trip-picker h2 {
		font-size: 2.5rem;
	}
	.trip-picker header > button {
		display: grid;
		width: 40px;
		height: 40px;
		place-items: center;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-surface);
		color: var(--tg-ink);
		cursor: pointer;
	}
	.new-trip-choice,
	.trip-choice-list button {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 0.7rem;
		padding: 0.8rem;
		border: 1px solid var(--tg-border);
		border-radius: 14px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		text-align: left;
		cursor: pointer;
	}
	.new-trip-choice {
		margin: 1rem 0;
		border-color: var(--tg-action);
	}
	.new-trip-choice > span,
	.trip-choice-list button > span:first-child {
		min-width: 0;
		flex: 1;
	}
	.new-trip-choice strong,
	.new-trip-choice small,
	.trip-choice-list strong,
	.trip-choice-list small {
		display: block;
	}
	.new-trip-choice small,
	.trip-choice-list small {
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
	}
	.trip-choice-list {
		display: grid;
		gap: 0.5rem;
	}
	.trip-choice-list button > span:last-child {
		color: var(--tg-action);
		font-weight: 850;
	}
	.trip-choice-list button:disabled {
		opacity: 0.6;
		cursor: wait;
	}
	.parent-country {
		margin: 0.1rem 0 0;
		color: var(--tg-ink-muted);
		font-weight: 750;
	}
	/* Theme-safe semantic overrides for the custom travel UI. */
	.eyebrow,
	.atlas-heading > span,
	.loading-state,
	.share-calendar p {
		color: var(--tg-ink-muted);
	}
	.country-tile,
	.visit-check,
	.country-profile-actions button,
	.region-card,
	.region-name,
	.region-toggle,
	.profile-editor input,
	.new-profile input,
	.share-calendar input {
		background: var(--tg-surface);
		color: var(--tg-ink);
		border-color: var(--tg-border-strong);
	}
	.country-label > button:first-child,
	.country-profile-actions button strong,
	.region-name,
	.region-toggle {
		color: var(--tg-ink);
	}
	.country-profile-actions button small {
		color: var(--tg-ink-muted);
	}
	.country-inspector,
	.profile-modal {
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		opacity: 1;
		isolation: isolate;
	}
	.country-inspector h2,
	.profile-modal h2,
	.region-heading h3,
	.region-heading {
		color: var(--tg-ink-strong);
	}
	.close {
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.details-link {
		color: var(--tg-ink);
		border-color: var(--tg-ink);
	}
	.profile-editor button,
	.new-profile button,
	.share-calendar button {
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.profile-editor .delete {
		background: var(--tg-danger);
		color: var(--tg-danger-text);
	}
	.new-profile,
	.share-calendar {
		border-color: var(--tg-border);
	}
	@media (max-width: 900px) {
		.hero {
			align-items: start;
			flex-wrap: wrap;
		}
		.hero-copy {
			width: 100%;
		}
		.journey-stat {
			width: 100%;
			justify-items: start;
		}
		.journey-stat-line.primary strong {
			font-size: 2.8rem;
		}
		.flag-grid {
			grid-template-columns: repeat(auto-fill, minmax(115px, 1fr));
		}
		.profile-editor {
			grid-template-columns: 44px 52px 1fr auto;
		}
		.profile-editor .delete {
			grid-column: 3/5;
		}
	}
	@media (max-width: 560px) {
		.dashboard {
			padding: 0.5rem;
		}
		.hero {
			padding: 1.25rem 0.5rem;
		}
		.hero h1 {
			font-size: 3.2rem;
		}
		.atlas-heading > span {
			display: none;
		}
		.atlas-panel {
			padding: 0.65rem;
		}
		.passport-tabs {
			width: 100%;
		}
		.flag-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
			gap: 0.45rem;
		}
		.subdivision-grid {
			grid-template-columns: 1fr;
		}
		.flag-button {
			height: 58px;
		}
		.country-label {
			padding: 0.48rem;
		}
		.country-label > button:first-child {
			font-size: 0.68rem;
		}
		.state-grid {
			grid-template-columns: 1fr;
		}
		.history-form {
			grid-template-columns: 1fr;
		}
		.map-selection-bar {
			right: 0.75rem;
			bottom: 0.75rem;
			left: 0.75rem;
			align-items: stretch;
			flex-direction: column;
		}
		.map-selection-bar .dismiss {
			position: absolute;
			top: 0.55rem;
			right: 0.55rem;
		}
		.map-selection-bar > div {
			padding-right: 2.5rem;
		}
		.new-profile > div {
			grid-template-columns: 44px 52px 1fr;
		}
		.new-profile button {
			grid-column: 3;
		}
		.profile-editor {
			grid-template-columns: 44px 52px 1fr;
		}
		.profile-editor button {
			grid-column: auto;
		}
		.profile-editor .delete {
			grid-column: 3;
		}
	}
</style>
