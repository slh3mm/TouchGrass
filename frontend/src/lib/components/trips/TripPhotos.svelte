<script lang="ts">
	import { onMount } from 'svelte';
	import ImageMultiple from '~icons/mdi/image-multiple-outline';
	import VideoOutline from '~icons/mdi/video-outline';
	import { addToast } from '$lib/toasts';
	export let tripId: string;
	export let canModify = false;
	type Link = {
		id: string;
		trip_id: string;
		trip_title: string;
		origin: string;
		explanation: string;
	};
	type Asset = {
		id: string;
		filename: string;
		media_kind: string;
		captured_at: string | null;
		locality: string;
		available: boolean;
		profile_name: string;
		profile_color: string;
		preview_url: string;
		original_url: string;
		trip_links: Link[];
	};
	let assets: Asset[] = [];
	let trips: Array<{ id: string; title: string }> = [];
	let loading = true;
	let selectedTrip: Record<string, string> = {};
	$: grouped = assets.reduce(
		(result, asset) => {
			const key = asset.captured_at
				? new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(
						new Date(asset.captured_at)
					)
				: 'Date pending';
			(result[key] ??= []).push(asset);
			return result;
		},
		{} as Record<string, Asset[]>
	);
	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || 'Request failed');
		return data;
	}
	async function load() {
		loading = true;
		try {
			const [photoData, tripData] = await Promise.all([
				api(`/api/photo-assets/?trip=${tripId}&page_size=100`),
				api('/api/trips/?format=json')
			]);
			assets = photoData.results || photoData;
			trips = tripData.results || tripData;
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not load trip photos');
		} finally {
			loading = false;
		}
	}
	async function unlink(asset: Asset) {
		const link = asset.trip_links.find((item) => item.trip_id === tripId);
		if (!link) return;
		try {
			await api(`/api/photo-assets/${asset.id}/trip-links/${link.id}/`, { method: 'DELETE' });
			assets = assets.filter((item) => item.id !== asset.id);
			addToast('success', 'Media unlinked from this trip');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not unlink photo');
		}
	}
	async function move(asset: Asset) {
		const target = selectedTrip[asset.id];
		if (!target || target === tripId) return;
		try {
			await api(`/api/photo-assets/${asset.id}/link-trip/`, {
				method: 'POST',
				body: JSON.stringify({ trip: target })
			});
			await unlinkWithoutConfirm(asset);
			addToast('success', 'Media moved to another trip');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not move media');
		}
	}
	async function unlinkWithoutConfirm(asset: Asset) {
		const link = asset.trip_links.find((item) => item.trip_id === tripId);
		if (link)
			await api(`/api/photo-assets/${asset.id}/trip-links/${link.id}/`, { method: 'DELETE' });
		assets = assets.filter((item) => item.id !== asset.id);
	}
	onMount(load);
</script>

<section class="photos-shell">
	{#if loading}<div class="empty">Loading trip photos…</div>{:else if !assets.length}<div
			class="empty"
		>
			<ImageMultiple />
			<h2>No indexed media yet</h2>
			<p>Strong date-and-location matches from the iCloud poller will appear here automatically.</p>
			<a href="/photos">Open photo index</a>
		</div>{:else}{#each Object.entries(grouped) as [month, items]}<section class="month">
				<h2>{month}</h2>
				<div class="gallery">
					{#each items as asset}<article style={`--profile:${asset.profile_color}`}>
							<a
								class="photo"
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
							<div class="meta">
								<strong>{asset.filename}</strong>
								<p>
									{asset.locality || asset.profile_name}{#if !asset.available}
										· unavailable{/if}
								</p>
								{#if asset.trip_links[0]}<small
										>{asset.trip_links[0].origin} · {asset.trip_links[0].explanation}</small
									>{/if}{#if canModify}<div class="controls">
										<select bind:value={selectedTrip[asset.id]}
											><option value="">Move to…</option
											>{#each trips.filter((item) => item.id !== tripId) as trip}<option
													value={trip.id}>{trip.title}</option
												>{/each}</select
										><button on:click={() => move(asset)} disabled={!selectedTrip[asset.id]}
											>Move</button
										><button class="remove" on:click={() => unlink(asset)}>Unlink</button>
									</div>{/if}
							</div>
						</article>{/each}
				</div>
			</section>{/each}{/if}
</section>

<style>
	.photos-shell {
		min-height: 420px;
	}
	.month > h2 {
		margin: 1.5rem 0 0.7rem;
		font: 400 2rem/1 var(--tg-font-display);
	}
	.gallery {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: 0.8rem;
	}
	.gallery article {
		overflow: hidden;
		border: 1px solid var(--tg-border);
		border-bottom: 5px solid var(--profile);
		border-radius: 18px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.photo {
		position: relative;
		display: grid;
		aspect-ratio: 4/3;
		overflow: hidden;
		place-items: center;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
	}
	.photo img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.photo > i {
		position: absolute;
		display: grid;
		width: 46px;
		height: 46px;
		place-items: center;
		border-radius: 50%;
		background: rgba(0, 0, 0, 0.65);
		color: white;
	}
	.meta {
		padding: 0.8rem;
	}
	.meta strong {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.meta p,
	.meta small {
		display: block;
		margin: 0.25rem 0;
		color: var(--tg-ink-muted);
		font-size: 0.74rem;
	}
	.controls {
		display: grid;
		grid-template-columns: 1fr auto auto;
		gap: 0.35rem;
		margin-top: 0.65rem;
	}
	.controls select,
	.controls button,
	.empty a {
		min-height: 36px;
		padding: 0.4rem 0.55rem;
		border: 1px solid var(--tg-border);
		border-radius: 10px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-size: 0.7rem;
		font-weight: 800;
	}
	.controls .remove {
		color: var(--tg-danger);
	}
	.empty {
		display: grid;
		min-height: 380px;
		place-items: center;
		align-content: center;
		gap: 0.45rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		color: var(--tg-ink-muted);
		text-align: center;
	}
	.empty :global(svg) {
		width: 52px;
		height: 52px;
	}
	.empty h2,
	.empty p {
		margin: 0;
	}
	.empty a {
		margin-top: 0.5rem;
		text-decoration: none;
	}
	@media (max-width: 600px) {
		.gallery {
			grid-template-columns: 1fr 1fr;
		}
		.controls {
			grid-template-columns: 1fr;
		}
		.controls > * {
			width: 100%;
		}
	}
	@media (max-width: 420px) {
		.gallery {
			grid-template-columns: 1fr;
		}
	}
</style>
