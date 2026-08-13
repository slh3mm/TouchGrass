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
	import { ManageProfilesButton, ProfileChip } from '$lib/components/touchgrass';
	import LazyFlag from '$lib/components/travel/LazyFlag.svelte';
	import TravelSearch from '$lib/components/travel/TravelSearch.svelte';
	import type { TravelSearchItem } from '$lib/components/travel/travelSearch';
	import { countrySearchAliases, matchesTravelSearch, normalizeTravelSearch } from '$lib/components/travel/travelSearch';

	export let data: PageData;

	let countries: Country[] = data.props?.countries || [];
	let profiles: TravelProfile[] = data.props?.profiles || [];
	let allRegions: Region[] = data.props?.regions || [];
	let editingProfileId = profiles.find((profile) => profile.is_default)?.id || profiles[0]?.id || '';
	let selectedProfileIds = new Set(profiles.map((profile) => profile.id));
	let displayMode: 'atlas' | 'map' = $page.url.searchParams.get('view') === 'map' ? 'map' : 'atlas';
	let showProfiles = false;
	let selectedCountry: Country | null = null;
	let countryRegions: Region[] = [];
	let loadingRegions = false;
	let selectedHistoryRegion: Region | null = null;
	let visitHistory: ProfileTravelVisit[] = [];
	let loadingHistory = false;
	let savingHistory = false;
	let historyDate = new Date().toISOString().slice(0, 10);
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
	const subdivisionCountryCodes = new Set(['US', 'CA']);
	let mapRegions: Region[] = [];
	let requestedDisplayMode: 'atlas' | 'map' = 'atlas';
	let TravelProfileMapComponent: any = null;
	let mapComponentPromise: Promise<void> | null = null;
	let subdivisionSearchRegions: Array<{ id: string; name: string; code: string; countryCode: string }> = [];

	function ensureMapComponent() {
		if (!browser || TravelProfileMapComponent || mapComponentPromise) return;
		mapComponentPromise = Promise.all([
			import('$lib/components/map/TravelProfileMap.svelte'),
			fetch('/geo/us-ca-admin1.compact.geojson').then((response) => response.ok ? response.json() : null)
		]).then(([module, collection]) => {
			TravelProfileMapComponent = module.default;
			subdivisionSearchRegions = (collection?.features || []).map((feature: any) => ({
				id: feature.properties.id,
				name: feature.properties.name,
				code: feature.properties.code,
				countryCode: feature.properties.countryCode
			}));
		});
	}

	$: requestedDisplayMode =
		$page.url.pathname === '/travel-map' || $page.url.searchParams.get('view') === 'map'
			? 'map'
			: 'atlas';
	$: if (displayMode !== requestedDisplayMode) displayMode = requestedDisplayMode;
	$: if (displayMode === 'map') ensureMapComponent();

	$: selectedProfiles = profiles.filter((profile) => selectedProfileIds.has(profile.id));
	$: primaryProfile = profiles.find((profile) => profile.id === editingProfileId) ?? profiles[0] ?? null;
	$: mapRegions = allRegions.filter((region) => subdivisionCountryCodes.has(region.id.split('-')[0]));
	$: countrySearchItems = countries.map((country): TravelSearchItem => ({
		id: `country-${country.country_code}`,
		targetId: country.country_code,
		kind: 'country',
		label: country.name,
		code: country.country_code,
		subtitle: [country.capital, country.subregion].filter(Boolean).join(' · ') || country.country_code,
		keywords: [country.capital, country.subregion, ...(countrySearchAliases[country.country_code] || [])].filter(Boolean) as string[],
		colors: profiles.filter((profile) => country.profile_ids.includes(profile.id)).map((profile) => profile.color),
		flagUrl: `/flags/${country.country_code.toLowerCase()}.png`
	}));
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
			colors: profiles.filter((profile) => profileIds.includes(profile.id)).map((profile) => profile.color)
		};
	});
	$: travelSearchItems = displayMode === 'map' ? [...countrySearchItems, ...regionSearchItems] : countrySearchItems;
	$: if (searchSelection && normalizeTravelSearch(searchQuery) !== normalizeTravelSearch(searchSelection.label)) clearSearchFocus();
	$: filteredCountries = searchQuery.trim()
		? countries.filter((country) => {
			const item = countrySearchItems.find((candidate) => candidate.targetId === country.country_code);
			return item ? matchesTravelSearch(item, searchQuery) : false;
		})
		: countries;
	$: visitedCount = countries.filter((country) =>
		country.profile_ids.some((id) => selectedProfileIds.has(id))
	).length;

	function csrfToken() {
		return document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';
	}

	function profileGradient(profileIds: string[], muted = '#d5d0c8') {
		const colors = profiles.filter((profile) => profileIds.includes(profile.id)).map((profile) => profile.color);
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
		return country.profile_ids.filter((id) => selectedProfileIds.has(id));
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
		if (displayMode === 'atlas' && event.detail.kind === 'country') {
			tick().then(() => document.getElementById(`country-card-${event.detail.targetId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
		}
	}

	function clearSearchFocus() {
		if (searchFocusTimer) clearTimeout(searchFocusTimer);
		searchFocusTimer = null;
		searchSelection = null;
	}

	onDestroy(() => {
		if (searchFocusTimer) clearTimeout(searchFocusTimer);
	});

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
			const response = await fetch(`/api/travel-profiles/${profile.id}/countries/${country.country_code}/`, {
				method: visited ? 'DELETE' : 'PUT',
				headers: { 'X-CSRFToken': csrfToken() }
			});
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${country.name}`);
				return;
			}
			country.profile_ids = visited
				? country.profile_ids.filter((id) => id !== profile.id)
				: [...country.profile_ids, profile.id];
			countries = [...countries];
			if (visited) {
				allRegions = allRegions.map((region) => region.id.startsWith(`${country.country_code}-`)
					? { ...region, profile_ids: region.profile_ids.filter((id) => id !== profile.id) }
					: region);
				countryRegions = countryRegions.map((region) => ({
					...region,
					profile_ids: region.profile_ids.filter((id) => id !== profile.id)
				}));
			}
			addToast('success', `${country.name} ${visited ? 'removed from' : 'added to'} ${profile.name}`, 5000, profile.color);
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
				visitHistory = Array.isArray(result) ? result : result.results || [];
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
		await loadVisitHistory(country, historyRegion);
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
					notes: historyNotes.trim()
				})
			});
			if (!response.ok) {
				const result = await response.json().catch(() => null);
				addToast('error', result ? JSON.stringify(result) : 'Could not add this visit');
				return;
			}
			const created: ProfileTravelVisit = await response.json();
			visitHistory = [created, ...visitHistory].sort((a, b) => b.visit_date.localeCompare(a.visit_date));
			historyNotes = '';
			if (!selectedCountry.profile_ids.includes(primaryProfile.id)) {
				selectedCountry.profile_ids = [...selectedCountry.profile_ids, primaryProfile.id];
				countries = [...countries];
			}
			if (selectedHistoryRegion && !selectedHistoryRegion.profile_ids.includes(primaryProfile.id)) {
				selectedHistoryRegion.profile_ids = [...selectedHistoryRegion.profile_ids, primaryProfile.id];
				const globalRegion = allRegions.find((region) => region.id === selectedHistoryRegion?.id);
				if (globalRegion) globalRegion.profile_ids = [...selectedHistoryRegion.profile_ids];
				countryRegions = [...countryRegions];
				allRegions = globalRegion ? [...allRegions] : [...allRegions, selectedHistoryRegion];
			}
			addToast('success', `${created.region_name || created.country_name} visit added for ${primaryProfile.name}`, 5000, primaryProfile.color);
		} finally {
			savingHistory = false;
		}
	}

	async function deleteVisitHistory(visit: ProfileTravelVisit) {
		const response = await fetch(`/api/travel-visit-history/${visit.id}/`, {
			method: 'DELETE',
			headers: { 'X-CSRFToken': csrfToken() }
		});
		if (response.ok) {
			visitHistory = visitHistory.filter((item) => item.id !== visit.id);
			addToast('success', 'Visit date removed', 5000, visit.profile_color);
		}
	}

	async function toggleRegionVisit(region: Region) {
		if (!primaryProfile) return;
		if (savingVisitKey === `region-${region.id}`) return;
		const visited = region.profile_ids.includes(primaryProfile.id);
		savingVisitKey = `region-${region.id}`;
		try {
			const response = await fetch(`/api/travel-profiles/${primaryProfile.id}/regions/${region.id}/`, {
				method: visited ? 'DELETE' : 'PUT',
				headers: { 'X-CSRFToken': csrfToken() }
			});
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${region.name}`);
				return;
			}
			region.profile_ids = visited
				? region.profile_ids.filter((id) => id !== primaryProfile.id)
				: [...region.profile_ids, primaryProfile.id];
			countryRegions = [...countryRegions];
			const globalRegion = allRegions.find((item) => item.id === region.id);
			if (globalRegion && globalRegion !== region) globalRegion.profile_ids = [...region.profile_ids];
			allRegions = globalRegion ? [...allRegions] : [...allRegions, region];
			if (selectedCountry && !visited && !selectedCountry.profile_ids.includes(primaryProfile.id)) {
				selectedCountry.profile_ids = [...selectedCountry.profile_ids, primaryProfile.id];
				countries = [...countries];
			}
			addToast('success', `${region.name} updated for ${primaryProfile.name}`, 5000, primaryProfile.color);
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
		if (profiles.length === 1 || !confirm(`Delete ${profile.name}? Their manual travel history will also be removed.`)) return;
		const response = await fetch(`/api/travel-profiles/${profile.id}/`, {
			method: 'DELETE', headers: { 'X-CSRFToken': csrfToken() }
		});
		if (response.ok) {
			profiles = profiles.filter((item) => item.id !== profile.id);
			selectedProfileIds.delete(profile.id);
			selectedProfileIds = new Set(selectedProfileIds);
		}
	}

	async function handleMapCountry(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) await toggleCountryVisit(country);
	}

	async function handleMapCountryInspect(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) await openCountry(country);
	}

	async function handleMapRegion(event: CustomEvent<{ regionId: string }>) {
		if (!subdivisionCountryCodes.has(event.detail.regionId?.split('-')[0])) return;
		let region = allRegions.find((item) => item.id === event.detail.regionId)
			?? countryRegions.find((item) => item.id === event.detail.regionId);
		if (!region?.name) {
			const response = await fetch(`/api/regions/${event.detail.regionId}/`);
			if (response.ok) {
				const fullRegion: Region = await response.json();
				if (region) fullRegion.profile_ids = [...region.profile_ids];
				region = fullRegion;
			}
		}
		if (region) await toggleRegionVisit(region);
	}

	async function handleMapRegionInspect(event: CustomEvent<{ regionId: string }>) {
		const countryCode = event.detail.regionId?.split('-')[0];
		if (!subdivisionCountryCodes.has(countryCode)) return;
		const country = countries.find((item) => item.country_code === countryCode);
		if (country) await openCountry(country, event.detail.regionId);
	}
</script>

<svelte:head>
	<title>World Travel - TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
</svelte:head>

<main class="travel-shell">
	<div class="travel-backdrop"></div>
	<div class="dashboard">
		<header class="hero">
			<div class="hero-copy"><h1>{displayMode === 'map' ? 'Travel Map' : 'Countries'}</h1><TravelSearch items={travelSearchItems} bind:query={searchQuery} placeholder={displayMode === 'map' ? 'Find a country, state, or province' : 'Find a country'} on:select={selectSearchResult} on:clear={clearSearchFocus} on:dismiss={clearSearchFocus} /></div>
			<div class="journey-stat"><strong>{visitedCount}</strong><span>of {countries.length} countries</span></div>
		</header>

		<section class="profile-bar">
			<div class="profile-list">
				{#each profiles as profile}
					<ProfileChip name={profile.name} color={profile.color} avatar={profile.avatar} active={editingProfileId === profile.id} on:select={() => editAs(profile)} />
				{/each}
				<ManageProfilesButton on:click={() => (showProfiles = true)} />
			</div>
			<p>Editing visits for <strong>{primaryProfile?.name || 'no profile selected'}</strong></p>
		</section>

		{#if displayMode === 'map'}
			<section class="map-panel">
				{#if TravelProfileMapComponent}
					<svelte:component this={TravelProfileMapComponent} {countries} regions={mapRegions} {profiles} {selectedProfileIds} focusTarget={searchSelection} on:countrySelect={handleMapCountry} on:countryInspect={handleMapCountryInspect} on:regionSelect={handleMapRegion} on:regionInspect={handleMapRegionInspect} />
				{:else}
					<div class="loading-state">Loading the travel map…</div>
				{/if}
			</section>
		{:else}
			<section class="atlas-panel">
				<div class="atlas-heading"><div><span class="eyebrow">Flag atlas</span><h2>{filteredCountries.length} destinations</h2></div><span>Click the check to update {primaryProfile?.name}</span></div>
				<div class="flag-grid">
					{#each filteredCountries as country, index}
						{@const visibleIds = visibleProfileIds(country)}
						<article id={`country-card-${country.country_code}`} class:unvisited={!visibleIds.length} class:search-target={searchSelection?.targetId === country.country_code} class="country-tile">
							<button class="flag-button" on:click={() => openCountry(country)} aria-label={`Open ${country.name}`}>
								<LazyFlag src={`/flags/${country.country_code.toLowerCase()}.png`} alt={`${country.name} flag`} countryCode={country.country_code} eager={index < 12} />
								<span class="color-band" style={`background:${profileGradient(visibleIds)}`}></span>
							</button>
							<div class="country-label"><button on:click={() => openCountry(country)}>{country.name}</button><button disabled={savingVisitKey === `country-${country.country_code}-${primaryProfile?.id}`} class:checked={primaryProfile && country.profile_ids.includes(primaryProfile.id)} class="visit-check" on:click={() => toggleCountryVisit(country)} title={`Toggle ${primaryProfile?.name}'s visit`}><CheckIcon /></button></div>
						</article>
					{/each}
				</div>
			</section>
		{/if}
	</div>
</main>

{#if selectedCountry}
	<div class="inspector-backdrop" on:click={() => (selectedCountry = null)} role="presentation"></div>
	<aside class="country-inspector" bind:this={countryInspector}>
		<button class="close" on:click={() => (selectedCountry = null)}><CloseIcon /></button>
		<img src={`/flags/${selectedCountry.country_code.toLowerCase()}.png`} alt={`${selectedCountry.name} flag`} width="110" height="70" decoding="async" />
		<span class="eyebrow">{selectedCountry.subregion}</span><h2>{selectedCountry.name}</h2>
		<div class="inspector-band" style={`background:${profileGradient(selectedCountry.profile_ids)}`}></div>
		<div class="country-profile-actions">{#each profiles as profile}<button disabled={savingVisitKey === `country-${selectedCountry.country_code}-${profile.id}`} class:visited={selectedCountry.profile_ids.includes(profile.id)} style={`--profile-color:${profile.color}`} on:click={() => selectedCountry && toggleCountryVisit(selectedCountry, profile)}><span>{profile.avatar || profile.name.slice(0,1).toUpperCase()}</span><strong>{profile.name}</strong><small>{selectedCountry.profile_ids.includes(profile.id) ? 'Remove visit' : 'Mark visited'}</small></button>{/each}</div>
		<section class="visit-history" bind:this={historySection}>
			<header>
				<div><span class="eyebrow">Visit history</span><h3>{selectedHistoryRegion?.name || selectedCountry.name}</h3></div>
				{#if selectedHistoryRegion}<button on:click={() => selectedCountry && loadVisitHistory(selectedCountry)}>All country visits</button>{/if}
			</header>
			<div class="history-form">
				<input type="date" bind:value={historyDate} aria-label="Visit date" />
				<input bind:value={historyNotes} maxlength="500" placeholder="Optional note" aria-label="Visit note" />
				<button disabled={savingHistory || !historyDate || !primaryProfile} on:click={addVisitHistory}>Add for {primaryProfile?.name}</button>
			</div>
			{#if loadingHistory}
				<div class="loading-state">Loading visit history…</div>
			{:else if visitHistory.length}
				<div class="history-list">
					{#each visitHistory as visit}
						<article style={`--history-color:${visit.profile_color}`}>
							<span>{visit.profile_avatar || visit.profile_name.slice(0,1).toUpperCase()}</span>
							<div>
								<strong>{new Date(`${visit.visit_date}T00:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</strong>
								<small>{visit.profile_name}{visit.region_name ? ` · ${visit.region_name}` : ''}</small>
								{#if visit.notes}<p>{visit.notes}</p>{/if}
							</div>
							<button aria-label={`Delete ${visit.visit_date} visit`} on:click={() => deleteVisitHistory(visit)}>Delete</button>
						</article>
					{/each}
				</div>
			{:else}
				<p class="empty-history">No dated visits yet.</p>
			{/if}
		</section>
		{#if subdivisionCountryCodes.has(selectedCountry.country_code)}
			<div class="region-heading"><h3>{selectedCountry.country_code === 'US' ? 'States visited' : 'Provinces visited'}</h3><span>{countryRegions.length}</span></div>
			{#if loadingRegions}
				<div class="loading-state">Loading regions…</div>
			{:else}
				<div class="state-grid">
					{#each countryRegions as region}
						<div class:visited={region.profile_ids.some((id) => selectedProfileIds.has(id))} class="region-card" style={`--region-fill:${profileGradient(region.profile_ids)}`}>
							<button class="region-name" on:click={(event) => openRegionHistory(event, region)}><span></span><span>{region.name}<small>View dates</small></span></button>
							<button class="region-toggle" disabled={savingVisitKey === `region-${region.id}`} on:click={() => toggleRegionVisit(region)} aria-label={`Toggle ${region.name} for ${primaryProfile?.name}`}><CheckIcon /></button>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
		{#if subdivisionCountryCodes.has(selectedCountry.country_code)}
			<button class="details-link" on:click={() => goto(`/worldtravel/${selectedCountry?.country_code}`)}>Open full country details</button>
		{/if}
	</aside>
{/if}

{#if showProfiles}
	<div class="modal-backdrop" role="presentation" on:click={() => (showProfiles = false)}></div>
	<section class="profile-modal">
		<header><div><span class="eyebrow">Household</span><h2>Travel profiles</h2></div><button on:click={() => (showProfiles = false)}><CloseIcon /></button></header>
		<div class="profile-editor-list">{#each profiles as profile}<div class="profile-editor"><input type="color" bind:value={profile.color} aria-label={`${profile.name} color`} /><input bind:value={profile.avatar} maxlength="8" class="avatar-input" aria-label="Avatar" /><input bind:value={profile.name} aria-label="Profile name" /><button on:click={() => updateProfile(profile)}>Save</button><button class="delete" on:click={() => deleteProfile(profile)}>Delete</button></div>{/each}</div>
		<div class="share-calendar"><h3>Share this household calendar</h3><p>Enter another TouchGrass username to share profiles, calendar entries, and travel history.</p><div><input bind:value={shareUsername} placeholder="TouchGrass username" /><button disabled={sharingCalendar || !shareUsername.trim()} on:click={shareCalendar}>Share</button></div></div>
		<div class="new-profile"><h3>Add a profile</h3><div><input type="color" bind:value={newProfile.color} aria-label="New profile color" /><input bind:value={newProfile.avatar} maxlength="8" class="avatar-input" placeholder="🙂" /><input bind:value={newProfile.name} placeholder="Profile name" /><button disabled={savingProfile || !newProfile.name.trim()} on:click={createProfile}><PlusIcon /> Add</button></div></div>
	</section>
{/if}

<style>
	.travel-shell { position:relative;min-height:100vh;color:var(--tg-ink);font-family:var(--tg-font-body); }
	.travel-backdrop { position:fixed;inset:0;background:var(--tg-canvas); }
	.dashboard { position:relative;z-index:1;width:min(1800px,100%);margin:auto;padding:clamp(1rem,2vw,2.25rem); }
	.hero { display:flex;align-items:end;justify-content:space-between;gap:2rem;padding:1.5rem 1.5rem 2rem; }.hero-copy{display:grid;gap:1.2rem;min-width:min(520px,100%)}
	h1,h2 { margin:.1rem 0;font-family:'Ovo',Georgia,serif;font-weight:400; } h1 { font-size:clamp(3.2rem,5vw,6rem);line-height:1; }
	.eyebrow { color:#7a746c;font-size:.7rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase; }
	.journey-stat { display:flex;align-items:baseline;gap:.6rem;white-space:nowrap; }.journey-stat strong { font-family:'Ovo',serif;font-size:4rem;font-weight:400; }
	.profile-bar,.atlas-panel,.map-panel { background:var(--tg-surface-glass);backdrop-filter:blur(var(--tg-blur-panel)); }
	.profile-bar { display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.25rem;border-radius:24px 24px 0 0;border-bottom:1px solid rgba(70,63,55,.1); }
	.profile-list { display:flex;align-items:center;gap:.65rem;flex-wrap:wrap; }
	.profile-bar p { margin:0;color:#746e68;font-size:.82rem; }
	.atlas-panel,.map-panel { border-radius:0 0 24px 24px;padding:1.25rem; }.map-panel { overflow:hidden; }.atlas-heading { display:flex;align-items:end;justify-content:space-between;margin-bottom:1rem; }.atlas-heading h2 { font-size:2.2rem; }.atlas-heading>span { color:#77716b;font-size:.8rem; }
	.flag-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:.85rem; }.country-tile { min-width:0;content-visibility:auto;contain-intrinsic-size:135px 128px;border:1px solid rgba(75,67,60,.12);border-radius:14px;background:rgba(255,255,255,.72);overflow:hidden;transition:transform .18s,box-shadow .18s; }.country-tile:hover { transform:translateY(-2px);box-shadow:0 10px 28px rgba(62,54,46,.12); }.country-tile.search-target{outline:3px solid var(--tg-action);outline-offset:3px;box-shadow:0 12px 30px color-mix(in srgb,var(--tg-action) 24%,transparent)}.flag-button { position:relative;display:block;width:100%;height:82px;padding:0;border:0;background:#eee;cursor:pointer;overflow:hidden; }.flag-button :global(.lazy-flag) { width:100%;height:100%; }.country-tile.unvisited :global(.lazy-flag) { filter:grayscale(1);opacity:.3; }.color-band { position:absolute;inset:auto 0 0;height:6px; }.country-label { display:flex;align-items:center;gap:.3rem;padding:.62rem .65rem; }.country-label>button:first-child { min-width:0;flex:1;overflow:hidden;border:0;background:none;text-align:left;text-overflow:ellipsis;white-space:nowrap;font-size:.78rem;font-weight:600;cursor:pointer; }.visit-check { display:grid;width:25px;height:25px;place-items:center;border:1px solid #d7d1ca;border-radius:50%;background:white;color:transparent;cursor:pointer; }.visit-check.checked { border-color:#393745;background:#393745;color:white; }.visit-check :global(svg) { width:.85rem; }
	.inspector-backdrop { position:fixed;inset:0;z-index:1070;background:rgba(30,27,25,.12); }.modal-backdrop { position:fixed;inset:0;z-index:1090;background:transparent; }.country-inspector { position:fixed;z-index:1080;top:0;right:0;width:min(560px,100%);height:100vh;padding:2rem;background:#f7f2e9;color:#302f38;box-shadow:-20px 0 60px rgba(36,30,25,.2);overflow:auto;font-family:'DM Sans',sans-serif; }.country-inspector>img { width:110px;height:70px;margin-bottom:1.25rem;border-radius:10px;object-fit:cover;box-shadow:0 8px 24px rgba(0,0,0,.12); }.country-inspector h2,.profile-modal h2 { color:#25232a;font-size:3rem; }.country-inspector .eyebrow { color:#68615b; }.close { position:absolute;top:1.25rem;right:1.25rem;display:grid;width:40px;height:40px;place-items:center;border:0;border-radius:50%;background:white;color:#302f38;cursor:pointer; }.inspector-band { height:10px;margin:1rem 0;border-radius:999px; }.details-link { width:100%;padding:.85rem 1rem;border:0;border-radius:999px;background:#393745;color:white;font-weight:600;cursor:pointer; }.visit-check:disabled,.state-grid button:disabled,.history-form button:disabled { opacity:.55;cursor:wait; }.region-heading { display:flex;justify-content:space-between;align-items:center;margin:2rem 0 .75rem;color:#302f38; }.region-heading h3 { color:#25232a;font-weight:700; }.state-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem; }.region-card { display:grid;grid-template-columns:minmax(0,1fr) 42px;border:1px solid var(--tg-border-strong);border-radius:10px;background:var(--tg-surface);overflow:hidden; }.region-name,.region-toggle { border:0;background:transparent;color:var(--tg-ink);cursor:pointer; }.region-name { display:flex;align-items:stretch;gap:.55rem;padding:.65rem;text-align:left;font-weight:700; }.region-name>span:first-child { width:8px;flex:0 0 auto;border-radius:99px;background:#aaa39b; }.region-card.visited .region-name>span:first-child { background:var(--region-fill); }.region-name>span:last-child { min-width:0; }.region-name small { display:block;margin-top:.12rem;color:var(--tg-ink-muted);font-size:.66rem;font-weight:700; }.region-toggle { display:grid;place-items:center;border-left:1px solid var(--tg-border); }.region-toggle :global(svg) { width:1rem;color:transparent; }.region-card.visited .region-toggle :global(svg) { color:var(--tg-ink); }.loading-state { color:#514b45; }.details-link { margin-top:1.5rem;background:transparent;color:#302f38;border:1px solid #393745; }
	.visit-history { margin-top:1.5rem;padding:1rem;border:1px solid var(--tg-border);border-radius:16px;background:var(--tg-surface-glass); }.visit-history header { display:flex;align-items:start;justify-content:space-between;gap:1rem;margin-bottom:.8rem; }.visit-history h3 { margin:.12rem 0 0;color:var(--tg-ink-strong);font-size:1.25rem; }.visit-history header>button { border:0;background:transparent;color:var(--tg-action);font-size:.75rem;font-weight:800;cursor:pointer; }.history-form { display:grid;grid-template-columns:140px 1fr auto;gap:.45rem; }.history-form input { min-width:0;padding:.65rem;border:1px solid var(--tg-border-strong);border-radius:10px;background:var(--tg-surface);color:var(--tg-ink); }.history-form button { padding:.65rem .8rem;border:0;border-radius:10px;background:var(--tg-action);color:var(--tg-action-text);font-weight:800;cursor:pointer; }.history-list { display:grid;gap:.45rem;margin-top:.8rem; }.history-list article { display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:start;gap:.6rem;padding:.6rem;border:1px solid var(--tg-border);border-left:5px solid var(--history-color);border-radius:11px;background:var(--tg-surface); }.history-list article>span { display:grid;width:32px;height:32px;place-items:center;border-radius:50%;background:color-mix(in srgb,var(--history-color) 62%,white);color:#171717;font-weight:800; }.history-list strong,.history-list small { display:block; }.history-list small { color:var(--tg-ink-muted);font-size:.7rem; }.history-list p { margin:.25rem 0 0;color:var(--tg-ink);font-size:.78rem; }.history-list article>button { align-self:center;border:0;background:transparent;color:var(--tg-danger);font-size:.7rem;font-weight:800;cursor:pointer; }.empty-history { margin:.8rem 0 0;color:var(--tg-ink-muted);font-size:.8rem; }
	.country-profile-actions { display:grid;gap:.5rem;margin:1rem 0; }.country-profile-actions button { display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:.65rem;padding:.65rem .8rem;border:1px solid #cfc6bb;border-radius:12px;background:white;color:#302f38;text-align:left;cursor:pointer; }.country-profile-actions button>span { display:grid;width:34px;height:34px;place-items:center;border-radius:50%;background:color-mix(in srgb,var(--profile-color) 55%,white); }.country-profile-actions button small { color:#625c56;font-weight:700; }.country-profile-actions button.visited { border-color:var(--profile-color);box-shadow:inset 5px 0 var(--profile-color); }.country-profile-actions button:disabled { opacity:.55;cursor:wait; }
	.profile-modal { position:fixed;z-index:1100;top:50%;left:50%;width:min(760px,calc(100% - 2rem));max-height:88vh;padding:1.5rem;transform:translate(-50%,-50%);overflow:auto;border:1px solid oklch(var(--bc)/.2);border-radius:24px;background:oklch(var(--b1)) !important;color:oklch(var(--bc)) !important;opacity:1;isolation:isolate;box-shadow:0 28px 80px rgba(36,30,25,.3); }.profile-modal header { display:flex;justify-content:space-between;align-items:start; }.profile-modal header button { border:0;background:oklch(var(--b2));color:oklch(var(--bc));cursor:pointer; }.profile-editor-list { display:grid;gap:.6rem;margin:1.25rem 0; }.profile-editor,.new-profile>div { display:grid;grid-template-columns:44px 60px 1fr auto auto;gap:.5rem; }.profile-editor input,.new-profile input { min-width:0;padding:.65rem;border:1px solid oklch(var(--bc)/.24);border-radius:10px;background:oklch(var(--b2)) !important;color:oklch(var(--bc)) !important; }.profile-editor input[type=color],.new-profile input[type=color] { padding:4px; }.profile-editor button,.new-profile button { border:0;border-radius:10px;padding:.6rem .8rem;background:oklch(var(--p));color:oklch(var(--pc));cursor:pointer; }.profile-editor .delete { background:#a75548; }.new-profile,.share-calendar { margin-top:1.5rem;padding-top:1rem;border-top:1px solid oklch(var(--bc)/.18); }.new-profile>div { grid-template-columns:44px 60px 1fr auto; }.new-profile button { display:flex;align-items:center;gap:.3rem; }.share-calendar p { color:oklch(var(--bc)/.72);font-size:.85rem; }.share-calendar>div { display:flex;gap:.5rem; }.share-calendar input { flex:1;min-width:0;padding:.7rem;border:1px solid oklch(var(--bc)/.24);border-radius:10px;background:oklch(var(--b2)) !important;color:oklch(var(--bc)) !important; }.share-calendar button { padding:.7rem 1rem;border:0;border-radius:10px;background:oklch(var(--p));color:oklch(var(--pc));font-weight:700; }
	.profile-modal { color:#302f38; }
	/* Theme-safe semantic overrides for the custom travel UI. */
	.eyebrow,.profile-bar p,.atlas-heading>span,.loading-state,.share-calendar p { color:var(--tg-ink-muted); }
	.country-tile,.visit-check,.country-profile-actions button,.region-card,.region-name,.region-toggle,
	.profile-editor input,.new-profile input,.share-calendar input { background:var(--tg-surface);color:var(--tg-ink);border-color:var(--tg-border-strong); }
	.country-label>button:first-child,.country-profile-actions button strong,.region-name,.region-toggle { color:var(--tg-ink); }
	.country-profile-actions button small { color:var(--tg-ink-muted); }
	.country-inspector { background:oklch(var(--b1)) !important;color:oklch(var(--bc)) !important;opacity:1;isolation:isolate; }
	.profile-modal { background:var(--tg-surface-soft);color:var(--tg-ink); }
	.country-inspector h2,.profile-modal h2,.region-heading h3,.region-heading { color:var(--tg-ink-strong); }
	.close { background:var(--tg-surface);color:var(--tg-ink); }
	.details-link { color:var(--tg-ink);border-color:var(--tg-ink); }
	.profile-editor button,.new-profile button,.share-calendar button { background:var(--tg-action);color:var(--tg-action-text); }
	.profile-editor .delete { background:var(--tg-danger);color:#fff; }
	.new-profile,.share-calendar { border-color:var(--tg-border); }
	@media(max-width:900px){.hero{align-items:start}.hero-copy{width:100%}.journey-stat{display:none}.profile-bar{align-items:start;flex-direction:column}.flag-grid{grid-template-columns:repeat(auto-fill,minmax(115px,1fr))}.profile-editor{grid-template-columns:44px 52px 1fr auto}.profile-editor .delete{grid-column:3/5}}
	@media(max-width:560px){.dashboard{padding:.5rem}.hero{padding:1.25rem .5rem}.hero h1{font-size:3.2rem}.profile-bar p,.atlas-heading>span{display:none}.atlas-panel{padding:.65rem}.flag-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem}.flag-button{height:58px}.country-label{padding:.48rem}.country-label>button:first-child{font-size:.68rem}.state-grid{grid-template-columns:1fr}.history-form{grid-template-columns:1fr}.new-profile>div{grid-template-columns:44px 52px 1fr}.new-profile button{grid-column:3}.profile-editor{grid-template-columns:44px 52px 1fr}.profile-editor button{grid-column:auto}.profile-editor .delete{grid-column:3}}
</style>
