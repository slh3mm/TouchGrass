<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import ArrowLeft from '~icons/mdi/arrow-left';
	import CalendarPlus from '~icons/mdi/calendar-plus';
	import { addToast } from '$lib/toasts';
	let place: any = null;
	let profiles: any[] = [];
	let trips: any[] = [];
	let loading = true;
	let showVisit = false;
	let editingId = '';
	let startDate = '';
	let endDate = '';
	let selectedProfiles: string[] = [];
	let trip = '';
	let notes = '';

	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || data.error || 'Request failed');
		return data;
	}
	async function load() {
		loading = true;
		try {
			const [placeData, profileData, tripData] = await Promise.all([
				api(`/api/places/${$page.params.id}/`),
				api('/api/travel-profiles/'),
				api('/api/trips/')
			]);
			place = placeData;
			profiles = profileData.results || profileData;
			trips = tripData.results || tripData;
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not load place');
		} finally {
			loading = false;
		}
	}
	function localValue(value: string | null) {
		return value ? new Date(value).toISOString().slice(0, 16) : '';
	}
	function beginEdit(visit: any = null) {
		editingId = visit?.id || '';
		startDate = localValue(visit?.start_date || null);
		endDate = localValue(visit?.end_date || null);
		selectedProfiles = visit?.profiles || place.profiles.map((item: any) => item.id);
		trip = visit?.trip || '';
		notes = visit?.notes || '';
		showVisit = true;
	}
	async function saveVisit() {
		try {
			const body: any = {
				start_date: new Date(startDate).toISOString(),
				end_date: endDate ? new Date(endDate).toISOString() : new Date(startDate).toISOString(),
				profiles: selectedProfiles,
				trip: trip || null,
				notes,
				source: 'manual'
			};
			if (editingId) body.id = editingId;
			await api(`/api/places/${place.id}/visits/`, {
				method: editingId ? 'PATCH' : 'POST',
				body: JSON.stringify(body)
			});
			showVisit = false;
			await load();
			addToast('success', editingId ? 'Visit updated' : 'Visit added');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not save visit');
		}
	}
	async function deleteVisit() {
		if (!editingId) return;
		try {
			await api(`/api/places/${place.id}/visits/`, {
				method: 'DELETE',
				body: JSON.stringify({ id: editingId })
			});
			showVisit = false;
			await load();
			addToast('success', 'Visit removed');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not remove visit');
		}
	}
	function format(value: string | null) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'long', timeStyle: 'short' }).format(
					new Date(value)
				)
			: 'Not recorded';
	}
	onMount(load);
</script>

<svelte:head><title>{place?.name || 'Place'} · TouchGrass</title></svelte:head>
<main class="detail-page">
	<a class="back" href="/places"><ArrowLeft />Places</a>
	{#if loading}<div class="loading">Loading place…</div>
	{:else if place}
		<header class="hero" style={`--blend:${place.profiles[0]?.color || 'var(--tg-action)'}`}>
			<div>
				<p>{place.status}</p>
				<h1>{place.name}</h1>
				<span>{place.locality || place.location}</span>
			</div>
			<div class="profiles">
				{#each place.profiles as item}<span style={`--profile:${item.color}`}
						><i></i>{item.name}</span
					>{/each}
			</div>
		</header>
		<div class="content-grid">
			<section class="panel">
				<div class="panel-heading">
					<div>
						<p>Travel record</p>
						<h2>Visit history</h2>
					</div>
					<button class="primary" on:click={() => beginEdit()}><CalendarPlus />Add visit</button>
				</div>
				{#if place.visits.length}<div class="visits">
						{#each place.visits as visit}<button on:click={() => beginEdit(visit)}
								><div>
									<strong>{format(visit.start_date)}</strong><span
										>{visit.end_date ? `through ${format(visit.end_date)}` : 'One-day visit'}</span
									>
								</div>
								<div>
									<span>{visit.trip_title || 'No linked trip'}</span><small
										>{visit.source.replace('_', ' ')}</small
									>
								</div></button
							>{/each}
					</div>{:else}<p class="empty">
						No visits recorded. Saved and upcoming places do not color Passport or Travel Map.
					</p>{/if}
			</section>
			<aside class="panel facts">
				<p>Place details</p>
				<h2>{place.category?.icon} {place.category?.name || 'Place'}</h2>
				{#if place.description}<p>{place.description}</p>{/if}
				<dl>
					<dt>Status</dt>
					<dd>{place.status}</dd>
					<dt>Visits</dt>
					<dd>{place.visit_count}</dd>
					<dt>Most recent</dt>
					<dd>{place.most_recent_visit ? format(place.most_recent_visit) : 'None'}</dd>
				</dl>
				{#if place.latitude != null}<a
						href={`https://www.google.com/maps/search/?api=1&query=${place.latitude},${place.longitude}`}
						target="_blank"
						rel="noreferrer">Open in maps</a
					>{/if}
			</aside>
		</div>
	{/if}
</main>

{#if showVisit}
	<button class="scrim" aria-label="Close visit editor" on:click={() => (showVisit = false)}
	></button>
	<aside class="editor">
		<header>
			<div>
				<p>{editingId ? 'Edit' : 'Add'} visit</p>
				<h2>{place.name}</h2>
			</div>
			<button on:click={() => (showVisit = false)}>×</button>
		</header>
		<div class="form">
			<label>Arrival<input type="datetime-local" bind:value={startDate} /></label><label
				>Departure<input type="datetime-local" bind:value={endDate} min={startDate} /></label
			>
			<fieldset>
				<legend>Who visited?</legend>{#each profiles as item}<label class="check"
						><input type="checkbox" value={item.id} bind:group={selectedProfiles} /><i
							style={`--profile:${item.color}`}
						></i>{item.name}</label
					>{/each}
			</fieldset>
			<label
				>Trip<select bind:value={trip}
					><option value="">No linked trip</option>{#each trips as item}<option value={item.id}
							>{item.title}</option
						>{/each}</select
				></label
			><a class="create-trip" href={`/trips?new=1&place=${encodeURIComponent(place.name)}`}
				>Create a new trip for this visit</a
			><label>Notes<textarea bind:value={notes} rows="4"></textarea></label><button
				class="primary save"
				disabled={!startDate || !selectedProfiles.length}
				on:click={saveVisit}>{editingId ? 'Save changes' : 'Add visit'}</button
			>{#if editingId}<button class="delete-visit" on:click={deleteVisit}>Delete visit</button>{/if}
		</div>
	</aside>
{/if}

<style>
	.detail-page {
		min-height: 100vh;
		padding: clamp(1rem, 4vw, 3rem);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin-bottom: 1rem;
		color: var(--tg-ink);
		font-weight: 800;
		text-decoration: none;
	}
	.back :global(svg) {
		width: 20px;
	}
	.hero {
		position: relative;
		display: flex;
		min-height: 300px;
		align-items: end;
		justify-content: space-between;
		gap: 2rem;
		overflow: hidden;
		padding: clamp(1.4rem, 4vw, 3rem);
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background:
			radial-gradient(
				circle at 85% 20%,
				color-mix(in srgb, var(--blend) 60%, transparent),
				transparent 35%
			),
			linear-gradient(
				135deg,
				color-mix(in srgb, var(--blend) 26%, var(--tg-surface)),
				var(--tg-surface)
			);
		box-shadow: var(--tg-shadow-panel);
	}
	.hero:after {
		position: absolute;
		inset: 0;
		content: '';
		opacity: 0.16;
		background-image: radial-gradient(var(--tg-ink-muted) 0.8px, transparent 0.8px);
		background-size: 18px 18px;
		mask-image: linear-gradient(90deg, transparent, #000);
	}
	.hero > div {
		position: relative;
		z-index: 1;
	}
	.hero p,
	.panel-heading p,
	.facts > p,
	.editor header p {
		margin: 0;
		color: var(--tg-action);
		font-size: 0.72rem;
		font-weight: 900;
		letter-spacing: 0.15em;
		text-transform: uppercase;
	}
	.hero h1 {
		margin: 0.4rem 0;
		color: var(--tg-ink-strong);
		font: 400 clamp(3.6rem, 8vw, 7rem)/0.86 var(--tg-font-display);
	}
	.profiles {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.profiles span {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.45rem 0.7rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
		background: var(--tg-overlay-field);
		font-weight: 800;
	}
	.profiles i {
		width: 11px;
		height: 11px;
		border-radius: 50%;
		background: var(--profile);
	}
	.content-grid {
		display: grid;
		grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
		gap: 1rem;
		margin-top: 1rem;
	}
	.panel {
		padding: clamp(1rem, 3vw, 2rem);
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.panel-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 1rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.panel h2,
	.editor h2 {
		margin: 0.25rem 0 0;
		font: 400 2.3rem/1 var(--tg-font-display);
	}
	button.primary {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		padding: 0.65rem 0.9rem;
		border: 1px solid var(--tg-action);
		border-radius: 13px;
		background: var(--tg-action);
		color: var(--tg-action-text);
		font-weight: 850;
	}
	.visits {
		display: grid;
		gap: 0.65rem;
		margin-top: 1rem;
	}
	.visits button {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 15px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		text-align: left;
	}
	.visits button div {
		display: grid;
	}
	.visits span,
	.visits small,
	.empty,
	.facts p {
		color: var(--tg-ink-muted);
	}
	.facts dl {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.6rem;
	}
	.facts dt {
		color: var(--tg-ink-muted);
	}
	.facts dd {
		margin: 0;
		font-weight: 800;
	}
	.facts a {
		display: flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		margin-top: 1rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 13px;
		color: var(--tg-ink);
		font-weight: 800;
		text-decoration: none;
	}
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 90;
		border: 0;
		background: color-mix(in srgb, var(--tg-ink) 25%, transparent);
	}
	.editor {
		position: fixed;
		z-index: 91;
		inset: var(--tg-nav-height, 84px) 0 0 auto;
		display: flex;
		width: min(500px, 100%);
		overflow: hidden;
		flex-direction: column;
		border-left: 1px solid var(--tg-border);
		background: var(--tg-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-panel);
	}
	.editor header {
		display: flex;
		align-items: start;
		justify-content: space-between;
		padding: 1.3rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.editor header button {
		width: 40px;
		height: 40px;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-size: 1.5rem;
	}
	.form {
		display: grid;
		gap: 1rem;
		min-height: 0;
		overflow-y: auto;
		padding: 1.3rem;
	}
	.form > label {
		display: grid;
		gap: 0.35rem;
		color: var(--tg-ink-muted);
		font-size: 0.75rem;
		font-weight: 850;
	}
	.form input,
	.form select,
	.form textarea {
		min-height: 44px;
		padding: 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-input-bg);
		color: var(--tg-input-text);
	}
	fieldset {
		display: flex;
		gap: 0.6rem;
		flex-wrap: wrap;
		padding: 0;
		border: 0;
	}
	legend {
		margin-bottom: 0.5rem;
		color: var(--tg-ink-muted);
		font-size: 0.75rem;
		font-weight: 850;
	}
	.check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 0.65rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
	}
	.check i {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--profile);
	}
	.save {
		width: 100%;
	}
	.create-trip {
		color: var(--tg-action);
		font-size: 0.8rem;
		font-weight: 800;
	}
	.delete-visit {
		min-height: 42px;
		border: 1px solid color-mix(in srgb, var(--tg-danger) 45%, var(--tg-border));
		border-radius: 12px;
		background: transparent;
		color: var(--tg-danger);
		font-weight: 850;
	}
	@media (max-width: 760px) {
		.hero {
			min-height: 240px;
			align-items: start;
			flex-direction: column;
			justify-content: end;
		}
		.content-grid {
			grid-template-columns: 1fr;
		}
		.panel-heading {
			align-items: start;
			flex-direction: column;
		}
		.editor {
			inset: 8vh 0 0;
			border: 0;
			border-radius: 24px 24px 0 0;
		}
		.visits button {
			align-items: start;
			flex-direction: column;
		}
	}
</style>
