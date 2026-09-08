<script lang="ts">
	import { onMount } from 'svelte';
	import ImageMultiple from '~icons/mdi/image-multiple-outline';
	import VideoOutline from '~icons/mdi/video-outline';
	import Magnify from '~icons/mdi/magnify';
	import { addToast } from '$lib/toasts';
	type Link = {
		id: string;
		trip_id: string;
		trip_title: string;
		origin: string;
		confidence: number;
		explanation: string;
	};
	type Candidate = { id: string; title: string };
	type Suggestion = {
		id: string;
		reason: string;
		confidence: number;
		candidate_trips: Candidate[];
	};
	type Asset = {
		id: string;
		filename: string;
		media_kind: 'image' | 'video';
		captured_at: string | null;
		locality: string;
		available: boolean;
		processing_state: string;
		error_message: string;
		profile_name: string;
		profile_color: string;
		preview_url: string;
		original_url: string;
		trip_links: Link[];
		duration_seconds: number | null;
		match_suggestion: Suggestion | null;
	};
	let assets: Asset[] = [];
	let total = 0;
	let page = 1;
	let search = '';
	let mediaKind = '';
	let availability = '';
	let state = '';
	let loading = true;
	let timer: ReturnType<typeof setTimeout>;
	let initialized = false;
	let selectedTrip: Record<string, string> = {};
	$: if (initialized) {
		clearTimeout(timer);
		search;
		mediaKind;
		availability;
		state;
		page;
		timer = setTimeout(load, 250);
	}
	async function load() {
		loading = true;
		const params = new URLSearchParams({ page: String(page), page_size: '48' });
		if (search.trim()) params.set('search', search.trim());
		if (mediaKind) params.set('media_kind', mediaKind);
		if (availability) params.set('availability', availability);
		if (state) params.set('state', state);
		try {
			const response = await fetch(`/api/photo-assets/?${params}`);
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail || 'Could not load photo index');
			assets = data.results || data;
			total = data.count ?? assets.length;
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not load photo index');
		} finally {
			loading = false;
		}
	}
	async function mutate(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || 'Request failed');
		return data;
	}
	async function linkSuggestion(asset: Asset) {
		const trip = selectedTrip[asset.id] || asset.match_suggestion?.candidate_trips[0]?.id;
		if (!trip) return;
		try {
			await mutate(`/api/photo-assets/${asset.id}/link-trip/`, {
				method: 'POST',
				body: JSON.stringify({ trip })
			});
			addToast('success', 'Media linked to trip');
			await load();
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not link media');
		}
	}
	async function dismissSuggestion(asset: Asset) {
		try {
			await mutate(`/api/photo-assets/${asset.id}/dismiss-match/`, { method: 'POST' });
			asset.match_suggestion = null;
			assets = [...assets];
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not dismiss match');
		}
	}
	function date(value: string | null) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
					new Date(value)
				)
			: 'Capture time pending';
	}
	onMount(() => {
		initialized = true;
		load();
	});
</script>

<svelte:head><title>Photo index · TouchGrass</title></svelte:head>
<main>
	<header>
		<div>
			<p class="eyebrow">Path-backed media</p>
			<h1>Photo index</h1>
			<p>
				Originals stay in iCloud. Opening a preview may download a cloud-only file on the Windows
				host.
			</p>
		</div>
		<strong>{total}<small>indexed items</small></strong>
	</header>
	<section class="toolbar">
		<label
			><Magnify /><input
				bind:value={search}
				placeholder="Search filenames, places, or trips"
			/></label
		><select bind:value={mediaKind}
			><option value="">Photos and videos</option><option value="image">Photos</option><option
				value="video">Videos</option
			></select
		><select bind:value={availability}
			><option value="">Every availability</option><option value="available">Available</option
			><option value="unavailable">Unavailable</option></select
		><select bind:value={state}
			><option value="">Every processing state</option><option value="ready">Metadata ready</option
			><option value="discovered">Pending</option><option value="error">Errors</option></select
		>
	</section>
	{#if loading}<div class="empty">
			<span></span>Loading indexed media…
		</div>{:else if !assets.length}<div class="empty">
			<ImageMultiple />
			<h2>No matching media</h2>
		</div>{:else}<section class="grid">
			{#each assets as asset}<article
					class:unavailable={!asset.available}
					style={`--profile:${asset.profile_color}`}
				>
					<a
						class="preview"
						href={asset.available ? asset.original_url : undefined}
						target="_blank"
						rel="noreferrer"
						>{#if asset.available}<img
								src={asset.preview_url}
								alt={asset.filename}
								loading="lazy"
							/>{:else}<ImageMultiple />{/if}{#if asset.media_kind === 'video'}<i
								><VideoOutline /></i
							>{/if}</a
					>
					<div class="copy">
						<div>
							<h2>{asset.filename}</h2>
							<b>{asset.processing_state}</b>
						</div>
						<p>{date(asset.captured_at)}</p>
						<p>
							{asset.locality || asset.profile_name}{#if !asset.available}
								· Original unavailable{/if}
						</p>
						{#if asset.trip_links.length}<div class="links">
								{#each asset.trip_links as link}<span title={link.explanation}
										>{link.trip_title} · {link.origin}</span
									>{/each}
							</div>{/if}{#if asset.match_suggestion}<div class="suggestion">
								<strong>Trip match needs review</strong><small
									>{asset.match_suggestion.reason}</small
								><select
									bind:value={selectedTrip[asset.id]}
									aria-label={`Choose a trip for ${asset.filename}`}
									><option value="">Choose trip…</option
									>{#each asset.match_suggestion.candidate_trips as trip}<option value={trip.id}
											>{trip.title}</option
										>{/each}</select
								>
								<div>
									<button
										on:click={() => linkSuggestion(asset)}
										disabled={!selectedTrip[asset.id] && !asset.match_suggestion.candidate_trips[0]}
										>Link</button
									><button class="quiet" on:click={() => dismissSuggestion(asset)}>Dismiss</button>
								</div>
							</div>{/if}{#if asset.error_message}<p class="error">{asset.error_message}</p>{/if}
					</div>
				</article>{/each}
		</section>
		{#if total > 48}<nav>
				<button disabled={page === 1} on:click={() => page--}>Previous</button><span
					>Page {page} of {Math.ceil(total / 48)}</span
				><button disabled={page >= Math.ceil(total / 48)} on:click={() => page++}>Next</button>
			</nav>{/if}{/if}
</main>

<style>
	main {
		min-height: calc(100dvh - var(--tg-navbar-height));
		padding: clamp(1rem, 4vw, 3.5rem);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	header {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 2rem;
		max-width: 1800px;
		margin: auto;
	}
	.eyebrow {
		margin: 0;
		color: var(--tg-action);
		font-size: 0.72rem;
		font-weight: 900;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	h1 {
		margin: 0.2rem 0;
		font: 400 clamp(3.5rem, 7vw, 6.5rem)/0.9 var(--tg-font-display);
		color: var(--tg-ink-strong);
	}
	header p {
		color: var(--tg-ink-muted);
	}
	header > strong {
		display: grid;
		font: 400 3rem/1 var(--tg-font-display);
		text-align: right;
	}
	header small {
		font: 800 0.7rem/1.4 var(--tg-font-body);
		text-transform: uppercase;
		color: var(--tg-ink-muted);
	}
	.toolbar {
		display: grid;
		grid-template-columns: minmax(280px, 2fr) repeat(3, minmax(150px, 1fr));
		gap: 0.6rem;
		max-width: 1800px;
		margin: 2rem auto;
		padding: 0.8rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.toolbar label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.toolbar input,
	.toolbar select {
		width: 100%;
		min-height: 44px;
		padding: 0.6rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-input-bg);
		color: var(--tg-input-text);
	}
	.toolbar label input {
		border: 0;
		background: transparent;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: 0.9rem;
		max-width: 1800px;
		margin: auto;
	}
	.grid article {
		overflow: hidden;
		border: 1px solid var(--tg-border);
		border-bottom: 5px solid var(--profile);
		border-radius: 18px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.preview {
		position: relative;
		display: grid;
		aspect-ratio: 4/3;
		place-items: center;
		overflow: hidden;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
	}
	.preview img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.preview > i {
		position: absolute;
		display: grid;
		width: 48px;
		height: 48px;
		place-items: center;
		border-radius: 50%;
		background: rgba(0, 0, 0, 0.62);
		color: #fff;
	}
	.unavailable .preview {
		opacity: 0.55;
	}
	.copy {
		padding: 0.85rem;
	}
	.copy > div {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.copy h2 {
		overflow: hidden;
		margin: 0;
		font-size: 1rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.copy b {
		font-size: 0.62rem;
		text-transform: uppercase;
		color: var(--tg-ink-muted);
	}
	.copy p {
		margin: 0.3rem 0;
		color: var(--tg-ink-muted);
		font-size: 0.76rem;
	}
	.links {
		display: flex;
		gap: 0.35rem;
		flex-wrap: wrap;
		margin-top: 0.5rem;
	}
	.links span {
		padding: 0.3rem 0.5rem;
		border-radius: 999px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
		font-size: 0.68rem;
		font-weight: 800;
	}
	.suggestion {
		display: grid !important;
		gap: 0.35rem;
		margin-top: 0.65rem;
		padding: 0.6rem;
		border-radius: 12px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.suggestion small {
		color: inherit;
	}
	.suggestion select,
	.suggestion button {
		min-height: 34px;
		border: 1px solid var(--tg-border-strong);
		border-radius: 9px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
	}
	.suggestion > div {
		display: flex !important;
		gap: 0.35rem;
	}
	.suggestion button {
		padding: 0.35rem 0.65rem;
	}
	.suggestion .quiet {
		border-color: transparent;
		background: transparent;
	}
	.copy .error {
		color: var(--tg-danger);
	}
	.empty {
		display: grid;
		min-height: 300px;
		place-items: center;
		align-content: center;
		gap: 0.5rem;
		color: var(--tg-ink-muted);
	}
	.empty :global(svg) {
		width: 52px;
		height: 52px;
	}
	nav {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 1rem;
		margin: 1.5rem;
	}
	nav button {
		padding: 0.6rem 0.9rem;
		border: 1px solid var(--tg-border);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
	}
	@media (max-width: 800px) {
		header {
			align-items: start;
			flex-direction: column;
		}
		.toolbar {
			grid-template-columns: 1fr;
		}
		.grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@media (max-width: 480px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
