<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import MapMarkerRadius from '~icons/mdi/map-marker-radius';
	import Magnify from '~icons/mdi/magnify';
	import Close from '~icons/mdi/close';
	import CalendarRange from '~icons/mdi/calendar-range';
	import LinkVariant from '~icons/mdi/link-variant';
	import { addToast } from '$lib/toasts';

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Visit = {
		id: string;
		start_date: string | null;
		end_date: string | null;
		source: string;
		trip: string | null;
		trip_title: string | null;
		profile_details: Profile[];
	};
	type Place = {
		id: string;
		name: string;
		description?: string;
		locality: string;
		location?: string;
		status: 'visited' | 'upcoming' | 'saved';
		category?: { name: string; icon: string };
		profiles: Profile[];
		visits: Visit[];
		visit_count: number;
		most_recent_visit: string | null;
		cover: string | null;
		latitude: number | null;
		longitude: number | null;
	};
	type Suggestion = {
		id: string;
		type: 'place' | 'trip';
		suggested_name?: string;
		title?: string;
		locality?: string;
		arrived_at?: string;
		departed_at?: string;
		started_at?: string;
		ended_at?: string;
		confidence: number;
		evidence?: Record<string, any>;
		profile_name?: string;
		profile_color?: string;
		profile_details?: Profile[];
		stops?: any[];
	};
	let places: Place[] = [];
	let profiles: Profile[] = [];
	let geographicSuggestions: string[] = [];
	let suggestions: Suggestion[] = [];
	let facets = {
		total: 0,
		visited: 0,
		upcoming: 0,
		saved: 0,
		needs_review: 0,
		categories: [] as any[]
	};
	let selected: Place | null = null;
	let loading = true;
	let search = '';
	let debouncedSearch = '';
	let status = '';
	let profile = '';
	let category = '';
	let sort = 'recent';
	let page = 1;
	let total = 0;
	let timer: ReturnType<typeof setTimeout>;

	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || data.error || 'Request failed');
		return data;
	}

	async function loadPlaces() {
		loading = true;
		const params = new URLSearchParams({ page: String(page), page_size: '24', sort });
		if (debouncedSearch) params.set('search', debouncedSearch);
		if (status) params.set('status', status);
		if (profile) params.set('profile', profile);
		if (category) params.set('category', category);
		try {
			const data = await api(`/api/places/?${params}`);
			places = data.results || data;
			total = data.count ?? places.length;
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not load Places');
		} finally {
			loading = false;
		}
	}

	async function loadSupporting() {
		try {
			const [facetData, profileData, suggestionData, countryData, subdivisionData] =
				await Promise.all([
					api('/api/places/facets/'),
					api('/api/travel-profiles/'),
					api('/api/location-suggestions/?status=pending'),
					api('/api/countries/'),
					fetch('/geo/us-ca-admin1.compact.geojson').then((response) =>
						response.ok ? response.json() : { features: [] }
					)
				]);
			facets = facetData;
			profiles = profileData.results || profileData;
			suggestions = suggestionData.results || [];
			geographicSuggestions = [
				...new Set([
					...(countryData.results || countryData).map((item: any) => item.name),
					...(subdivisionData.features || [])
						.map((item: any) => item.properties?.name)
						.filter(Boolean)
				])
			].sort() as string[];
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not load Place filters');
		}
	}

	$: {
		clearTimeout(timer);
		timer = setTimeout(() => {
			debouncedSearch = search.trim();
			page = 1;
		}, 250);
	}
	$: if (browser) {
		debouncedSearch;
		status;
		profile;
		category;
		sort;
		page;
		loadPlaces();
	}

	async function decide(item: Suggestion, action: 'accept' | 'dismiss' | 'always-ignore') {
		try {
			if (item.type === 'trip' && action === 'always-ignore') action = 'dismiss';
			const path = item.type === 'trip' ? 'journey-candidates' : 'stay-candidates';
			const body =
				action === 'accept' && item.type === 'place'
					? { name: item.suggested_name || item.locality || 'Saved place' }
					: action === 'accept'
						? { title: item.title || 'Detected trip' }
						: {};
			await api(`/api/${path}/${item.id}/${action}/`, {
				method: 'POST',
				body: JSON.stringify(body)
			});
			suggestions = suggestions.filter((candidate) => candidate.id !== item.id);
			await Promise.all([loadPlaces(), loadSupporting()]);
			addToast(
				'success',
				action === 'accept' ? 'Added after your approval' : 'Suggestion dismissed'
			);
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not update suggestion');
		}
	}

	function formatDate(value: string | null | undefined) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
			: 'Date not recorded';
	}

	onMount(loadSupporting);
</script>

<svelte:head
	><title>Places · TouchGrass</title><meta
		name="description"
		content="Accepted places and location suggestions"
	/></svelte:head
>

<main class="places-page">
	<header class="page-heading">
		<div>
			<p class="eyebrow">Your world, remembered</p>
			<h1>Places</h1>
			<p>Only places and visits you approve appear here or color the map.</p>
		</div>
		<div class="stats" aria-label="Place statistics">
			<span><strong>{facets.total}</strong>Total</span><span
				><strong>{facets.visited}</strong>Visited</span
			><span><strong>{facets.upcoming}</strong>Upcoming</span><span
				><strong>{facets.needs_review}</strong>Review</span
			>
		</div>
	</header>

	<section class="toolbar" aria-label="Search and filter Places">
		<label class="search"
			><Magnify /><input
				bind:value={search}
				list="place-search-suggestions"
				placeholder="Search places, cities, states, provinces, countries, or trips"
			/><datalist id="place-search-suggestions"
				>{#each [...new Set( [...places.map((place) => place.name), ...geographicSuggestions] )].slice(0, 400) as suggestion}<option
						value={suggestion}
					></option>{/each}</datalist
			></label
		>
		<select bind:value={profile} aria-label="Profile"
			><option value="">Every profile</option>{#each profiles as item}<option value={item.id}
					>{item.name}</option
				>{/each}</select
		>
		<select bind:value={status} aria-label="Status"
			><option value="">Every status</option><option value="visited">Visited</option><option
				value="upcoming">Upcoming</option
			><option value="saved">Saved</option></select
		>
		<select bind:value={category} aria-label="Category"
			><option value="">Every category</option>{#each facets.categories as item}<option
					value={item.id}>{item.display_name}</option
				>{/each}</select
		>
		<select bind:value={sort} aria-label="Sort"
			><option value="recent">Most recent</option><option value="oldest">Oldest visit</option
			><option value="name">Name</option><option value="most_visited">Most visited</option></select
		>
	</section>

	{#if suggestions.length}
		<section class="review-section">
			<div class="section-heading">
				<div>
					<p class="eyebrow">Your approval required</p>
					<h2>Location suggestions</h2>
				</div>
				<span>{suggestions.length}</span>
			</div>
			<div class="suggestion-grid">
				{#each suggestions as item}
					<article
						class="suggestion-card"
						style={`--profile:${item.profile_color || item.profile_details?.[0]?.color || 'var(--tg-action)'}`}
					>
						<div class="suggestion-profile">
							{item.type === 'trip' ? 'Potential trip' : 'Potential place'}
						</div>
						<h3>{item.title || item.suggested_name || item.locality || 'Possible place'}</h3>
						<p class="dates">
							{formatDate(item.started_at || item.arrived_at)} – {formatDate(
								item.ended_at || item.departed_at
							)}
						</p>
						<p>
							{item.evidence?.reason ||
								'TouchGrass detected a meaningful stay. Nothing changes until you approve it.'}
						</p>
						<div class="confidence">
							<span style={`width:${Math.round(item.confidence * 100)}%`}></span>
						</div>
						<footer>
							<button class="primary" on:click={() => decide(item, 'accept')}
								>{item.type === 'trip' ? 'Create trip' : 'Save place'}</button
							><button on:click={() => decide(item, 'dismiss')}>Dismiss</button
							>{#if item.type === 'place'}<button
									class="quiet"
									on:click={() => decide(item, 'always-ignore')}>Always ignore</button
								>{/if}
						</footer>
					</article>
				{/each}
			</div>
		</section>
	{/if}

	<section class="atlas">
		<div class="section-heading">
			<div>
				<p class="eyebrow">Accepted places</p>
				<h2>{total} {total === 1 ? 'place' : 'places'}</h2>
			</div>
		</div>
		{#if loading}<div class="empty">
				<span class="spinner"></span>
				<p>Loading Places…</p>
			</div>
		{:else if !places.length}<div class="empty">
				<MapMarkerRadius />
				<h3>No matching places</h3>
				<p>Change the filters, add a place manually, or review a location suggestion.</p>
			</div>
		{:else}
			<div class="place-grid">
				{#each places as place}
					<button
						class="place-card"
						on:click={() => (selected = place)}
						aria-label={`Open ${place.name}`}
					>
						<div
							class="cover"
							class:has-image={!!place.cover}
							style={place.cover
								? `background-image:url(${place.cover})`
								: `--blend:${place.profiles[0]?.color || 'var(--tg-action)'}`}
						>
							<span>{place.category?.icon || '⌖'}</span>
						</div>
						<div class="card-body">
							<div class="title-row">
								<h3>{place.name}</h3>
								<span class={`place-status ${place.status}`}>{place.status}</span>
							</div>
							<p>{place.locality || 'Location details pending'}</p>
							<footer>
								<span>{place.category?.name || 'Place'}</span><span
									>{place.visit_count} {place.visit_count === 1 ? 'visit' : 'visits'}</span
								>
							</footer>
						</div>
						<div class="profile-strip">
							{#each place.profiles as item}<i style={`--profile:${item.color}`}></i>{/each}
						</div>
					</button>
				{/each}
			</div>
			{#if total > 24}<nav class="pagination" aria-label="Places pages">
					<button disabled={page === 1} on:click={() => page--}>Previous</button><span
						>Page {page} of {Math.ceil(total / 24)}</span
					><button disabled={page >= Math.ceil(total / 24)} on:click={() => page++}>Next</button>
				</nav>{/if}
		{/if}
	</section>
</main>

{#if selected}
	<button class="sheet-scrim" aria-label="Close place preview" on:click={() => (selected = null)}
	></button>
	<aside class="place-sheet" aria-label={`${selected.name} details`}>
		<header>
			<div>
				<p class="eyebrow">{selected.status}</p>
				<h2>{selected.name}</h2>
				<p>{selected.locality}</p>
			</div>
			<button class="icon-button" aria-label="Close" on:click={() => (selected = null)}
				><Close /></button
			>
		</header>
		<div class="sheet-scroll">
			<section class="profile-list">
				{#each selected.profiles as item}<span style={`--profile:${item.color}`}
						><i></i>{item.name}</span
					>{/each}
			</section>
			{#if selected.description}<p class="description">{selected.description}</p>{/if}
			<section>
				<h3>Visit history</h3>
				{#if selected.visits.length}<div class="visit-list">
						{#each selected.visits as visit}<article>
								<CalendarRange />
								<div>
									<strong
										>{formatDate(
											visit.start_date
										)}{#if visit.end_date && visit.end_date !== visit.start_date}
											– {formatDate(visit.end_date)}{/if}</strong
									>
									<p>{visit.trip_title || 'Unlinked visit'} · {visit.source.replace('_', ' ')}</p>
								</div>
							</article>{/each}
					</div>{:else}<p class="muted">No completed visit yet.</p>{/if}
			</section>
			{#if selected.latitude != null && selected.longitude != null}<a
					class="external-map"
					href={`https://www.google.com/maps/search/?api=1&query=${selected.latitude},${selected.longitude}`}
					target="_blank"
					rel="noreferrer"><LinkVariant />Open in maps</a
				>{/if}
			<a class="detail-link" href={`/places/${selected.id}`}>Open full place details</a>
		</div>
	</aside>
{/if}

<style>
	.places-page {
		min-height: calc(100vh - var(--tg-nav-height, 84px));
		padding: clamp(1.2rem, 4vw, 3.5rem);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	.page-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 2rem;
		max-width: 1800px;
		margin: auto;
	}
	.eyebrow {
		margin: 0 0 0.45rem;
		color: var(--tg-action);
		font-size: 0.72rem;
		font-weight: 900;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	.page-heading h1 {
		margin: 0;
		color: var(--tg-ink-strong);
		font: 400 clamp(4rem, 8vw, 7.5rem)/0.82 var(--tg-font-display);
	}
	.page-heading > div > p:last-child {
		color: var(--tg-ink-muted);
	}
	.stats {
		display: flex;
		gap: 1.8rem;
		padding: 1rem 1.2rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.stats span {
		display: grid;
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
		font-weight: 800;
		text-transform: uppercase;
	}
	.stats strong {
		color: var(--tg-ink-strong);
		font: 400 2rem/1 var(--tg-font-display);
	}
	.toolbar {
		display: grid;
		grid-template-columns: minmax(320px, 2fr) repeat(4, minmax(130px, auto));
		gap: 0.65rem;
		max-width: 1800px;
		margin: 2rem auto;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.65rem;
	}
	.search :global(svg) {
		width: 22px;
	}
	.toolbar input,
	.toolbar select {
		min-width: 0;
		width: 100%;
		min-height: 46px;
		padding: 0.65rem 0.8rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 13px;
		background: var(--tg-input-bg);
		color: var(--tg-input-text);
	}
	.search input {
		border: 0;
		background: transparent;
		outline: 0;
	}
	.review-section,
	.atlas {
		max-width: 1800px;
		margin: 2rem auto;
	}
	.section-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.section-heading h2 {
		margin: 0;
		color: var(--tg-ink-strong);
		font: 400 clamp(2rem, 4vw, 3.4rem)/1 var(--tg-font-display);
	}
	.section-heading > span {
		display: grid;
		width: 42px;
		height: 42px;
		place-items: center;
		border-radius: 50%;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
		font-weight: 900;
	}
	.suggestion-grid,
	.place-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	.suggestion-card {
		display: flex;
		min-height: 300px;
		flex-direction: column;
		padding: 1.2rem;
		border: 1px solid var(--tg-border);
		border-top: 8px solid var(--profile);
		border-radius: 20px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.suggestion-profile {
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
		font-weight: 900;
		text-transform: uppercase;
	}
	.suggestion-card h3 {
		margin: 0.65rem 0 0.3rem;
		font: 400 2rem/1 var(--tg-font-display);
	}
	.suggestion-card p {
		color: var(--tg-ink-muted);
	}
	.suggestion-card .dates {
		font-weight: 800;
	}
	.confidence {
		height: 5px;
		margin-top: auto;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
	}
	.confidence span {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: var(--profile);
	}
	.suggestion-card footer {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		margin-top: 1rem;
	}
	.suggestion-card button,
	.pagination button {
		min-height: 40px;
		padding: 0.55rem 0.8rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
	}
	.suggestion-card button.primary {
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.suggestion-card button.quiet {
		padding-inline: 0.25rem;
		border-color: transparent;
		background: transparent;
		color: var(--tg-ink-muted);
		font-size: 0.75rem;
	}
	.place-card {
		position: relative;
		display: flex;
		min-width: 0;
		min-height: 300px;
		overflow: hidden;
		flex-direction: column;
		padding: 0;
		border: 1px solid var(--tg-border);
		border-radius: 20px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-card);
		text-align: left;
		transition:
			transform var(--tg-motion-fast),
			box-shadow var(--tg-motion-fast);
	}
	.place-card:hover {
		transform: translateY(-3px);
		box-shadow: var(--tg-shadow-panel);
	}
	.cover {
		display: grid;
		min-height: 160px;
		place-items: center;
		background: linear-gradient(
			135deg,
			color-mix(in srgb, var(--blend) 55%, var(--tg-canvas)),
			var(--tg-canvas-deep)
		);
		background-size: cover;
		background-position: center;
	}
	.cover span {
		font-size: 2.6rem;
	}
	.cover.has-image span {
		display: none;
	}
	.card-body {
		display: flex;
		flex: 1;
		flex-direction: column;
		padding: 1rem;
	}
	.title-row {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.card-body h3 {
		margin: 0;
		font: 400 1.7rem/1 var(--tg-font-display);
	}
	.card-body p {
		margin: 0.35rem 0;
		color: var(--tg-ink-muted);
	}
	.card-body footer {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: auto;
		padding-top: 1rem;
		color: var(--tg-ink-muted);
		font-size: 0.76rem;
		font-weight: 800;
	}
	.place-status {
		padding: 0.25rem 0.5rem;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		font-size: 0.65rem;
		font-weight: 900;
		text-transform: uppercase;
	}
	.place-status.visited {
		background: color-mix(in srgb, var(--tg-success) 16%, var(--tg-surface));
		color: var(--tg-success);
	}
	.place-status.upcoming {
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.profile-strip {
		position: absolute;
		inset: auto 0 0;
		display: flex;
		height: 5px;
	}
	.profile-strip i {
		flex: 1;
		background: var(--profile);
	}
	.empty {
		display: grid;
		min-height: 260px;
		place-items: center;
		align-content: center;
		color: var(--tg-ink-muted);
		text-align: center;
	}
	.empty :global(svg) {
		width: 48px;
		height: 48px;
	}
	.empty h3 {
		margin: 0.75rem 0 0;
		color: var(--tg-ink-strong);
	}
	.spinner {
		width: 34px;
		height: 34px;
		border: 3px solid var(--tg-border);
		border-top-color: var(--tg-action);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		margin-top: 1.5rem;
	}
	.pagination button:disabled {
		opacity: 0.45;
	}
	.sheet-scrim {
		position: fixed;
		inset: 0;
		z-index: 80;
		border: 0;
		background: color-mix(in srgb, var(--tg-ink-strong) 26%, transparent);
	}
	.place-sheet {
		position: fixed;
		z-index: 81;
		inset: var(--tg-nav-height, 84px) 0 0 auto;
		display: flex;
		width: min(520px, 100%);
		overflow: hidden;
		flex-direction: column;
		border-left: 1px solid var(--tg-border);
		background: var(--tg-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-panel);
	}
	.place-sheet > header {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 1rem;
		padding: 1.4rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.place-sheet h2 {
		margin: 0;
		font: 400 2.8rem/1 var(--tg-font-display);
	}
	.place-sheet header p {
		margin: 0.3rem 0;
		color: var(--tg-ink-muted);
	}
	.icon-button {
		display: grid;
		width: 42px;
		height: 42px;
		place-items: center;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.sheet-scroll {
		min-height: 0;
		overflow-y: auto;
		padding: 1.4rem;
	}
	.profile-list {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.profile-list span {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 0.65rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
		font-weight: 800;
	}
	.profile-list i {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--profile);
	}
	.description,
	.muted {
		color: var(--tg-ink-muted);
	}
	.sheet-scroll h3 {
		margin-top: 1.6rem;
	}
	.visit-list {
		display: grid;
		gap: 0.55rem;
	}
	.visit-list article {
		display: flex;
		gap: 0.7rem;
		padding: 0.8rem;
		border: 1px solid var(--tg-border);
		border-radius: 14px;
		background: var(--tg-overlay-field);
	}
	.visit-list :global(svg) {
		width: 22px;
		flex: 0 0 auto;
	}
	.visit-list p {
		margin: 0.25rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	.external-map,
	.detail-link {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		min-height: 46px;
		margin-top: 1rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 13px;
		color: var(--tg-ink);
		font-weight: 850;
		text-decoration: none;
	}
	.detail-link {
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	@media (max-width: 1200px) {
		.toolbar {
			grid-template-columns: 2fr 1fr 1fr;
		}
		.toolbar select:nth-last-child(-n + 2) {
			grid-column: auto;
		}
		.stats {
			gap: 1rem;
		}
	}
	@media (max-width: 760px) {
		.places-page {
			padding: 1rem;
		}
		.page-heading {
			align-items: start;
			flex-direction: column;
		}
		.page-heading h1 {
			font-size: 4.2rem;
		}
		.stats {
			width: 100%;
			overflow-x: auto;
		}
		.toolbar {
			grid-template-columns: 1fr;
		}
		.suggestion-card footer {
			align-items: stretch;
			flex-direction: column;
		}
		.place-sheet {
			inset: 10vh 0 0;
			width: 100%;
			border-top: 1px solid var(--tg-border);
			border-left: 0;
			border-radius: 24px 24px 0 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.place-card {
			transition: none;
		}
		.spinner {
			animation: none;
		}
	}
</style>
