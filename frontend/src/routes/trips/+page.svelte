<script lang="ts">
	import PlusIcon from '~icons/mdi/plus';
	import PencilIcon from '~icons/mdi/pencil';
	import CloseIcon from '~icons/mdi/close';
	import ArrowIcon from '~icons/mdi/arrow-right';
	import MapIcon from '~icons/mdi/map-outline';
	import CalendarIcon from '~icons/mdi/calendar-range';
	import TrashIcon from '~icons/mdi/trash-can-outline';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { addToast } from '$lib/toasts';
	import SkylightTripSync from '$lib/components/trips/SkylightTripSync.svelte';
	import TripCard from '$lib/components/trips/TripCard.svelte';
	import type { PageData } from './$types';

	export let data: PageData;

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Trip = {
		id: string;
		title: string;
		start_date: string;
		end_date: string;
		notes: string;
		profiles: string[];
		profile_details: Profile[];
		destinations: Array<{
			id: string;
			country: number;
			country_code: string;
			country_name: string;
			region: string | null;
			region_name: string | null;
		}>;
		planner_id: string;
		planner_url: string;
	};

	let trips: Trip[] = data.trips || [];
	let profiles: Profile[] = data.profiles || [];
	let editing: Trip | null = null;
	let editorOpen = false;
	let saving = false;
	let confirmingDelete = false;
	let form = { title: '', start_date: '', end_date: '', notes: '', profiles: [] as string[] };
	let pendingDestination: { country: number; region: string | null; place: string } | null = null;

	const currentDate = new Date();
	const today = [
		currentDate.getFullYear(),
		String(currentDate.getMonth() + 1).padStart(2, '0'),
		String(currentDate.getDate()).padStart(2, '0')
	].join('-');

	$: currentTrips = trips
		.filter((trip) => trip.end_date >= today)
		.sort((a, b) => a.start_date.localeCompare(b.start_date));
	$: pastTrips = trips
		.filter((trip) => trip.end_date < today)
		.sort((a, b) => b.start_date.localeCompare(a.start_date));

	function csrf() {
		return (
			document.cookie
				.split('; ')
				.find((row) => row.startsWith('csrftoken='))
				?.split('=')[1] || ''
		);
	}

	function newTrip() {
		editing = null;
		form = { title: '', start_date: today, end_date: today, notes: '', profiles: [] };
		confirmingDelete = false;
		editorOpen = true;
	}

	onMount(() => {
		if ($page.url.searchParams.get('new') !== '1') return;
		const country = Number($page.url.searchParams.get('country'));
		if (!Number.isFinite(country)) return;
		pendingDestination = {
			country,
			region: $page.url.searchParams.get('region'),
			place: $page.url.searchParams.get('place') || 'New destination'
		};
		newTrip();
		form.title = `Trip to ${pendingDestination.place}`;
		const profileId = $page.url.searchParams.get('profile');
		if (profileId && profiles.some((profile) => profile.id === profileId))
			form.profiles = [profileId];
	});

	function editTrip(trip: Trip) {
		editing = trip;
		form = {
			title: trip.title,
			start_date: trip.start_date,
			end_date: trip.end_date,
			notes: trip.notes,
			profiles: [...trip.profiles]
		};
		confirmingDelete = false;
		editorOpen = true;
	}

	function toggleProfile(id: string) {
		form.profiles = form.profiles.includes(id)
			? form.profiles.filter((value) => value !== id)
			: [...form.profiles, id];
	}

	function formatError(result: Record<string, unknown>) {
		if (typeof result.detail === 'string') return result.detail;
		const first = Object.values(result)[0];
		if (Array.isArray(first)) return String(first[0]);
		return 'Could not save this trip.';
	}

	async function save() {
		if (!form.title.trim() || !form.start_date || !form.end_date || !form.profiles.length) {
			addToast('error', 'Add a title, dates, and at least one profile.');
			return;
		}
		if (form.end_date < form.start_date) {
			addToast('error', 'The end date must be on or after the start date.');
			return;
		}

		saving = true;
		try {
			const response = await fetch(editing ? `/api/trips/${editing.id}/` : '/api/trips/', {
				method: editing ? 'PATCH' : 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: JSON.stringify({ ...form, title: form.title.trim() })
			});
			const result = await response.json();
			if (!response.ok) throw new Error(formatError(result));
			if (!editing && pendingDestination) {
				const destinationResponse = await fetch(`/api/trips/${result.id}/destinations/`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
					body: JSON.stringify(pendingDestination)
				});
				if (!destinationResponse.ok)
					throw new Error('Trip created, but the destination could not be attached.');
				const destination = await destinationResponse.json();
				result.destinations = [...(result.destinations || []), destination];
				pendingDestination = null;
				history.replaceState({}, '', '/trips');
			}
			trips = editing
				? trips.map((trip) => (trip.id === result.id ? result : trip))
				: [...trips, result];
			editorOpen = false;
			addToast('success', editing ? 'Trip updated' : 'Trip and planner created');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not save this trip.');
		} finally {
			saving = false;
		}
	}

	async function deleteTrip() {
		if (!editing || !confirmingDelete) {
			confirmingDelete = true;
			return;
		}
		saving = true;
		try {
			const response = await fetch(`/api/trips/${editing.id}/`, {
				method: 'DELETE',
				headers: { 'X-CSRFToken': csrf() }
			});
			if (!response.ok) {
				const result = await response.json().catch(() => ({}));
				throw new Error(formatError(result));
			}
			trips = trips.filter((trip) => trip.id !== editing?.id);
			editorOpen = false;
			confirmingDelete = false;
			addToast('success', 'Trip deleted');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not delete this trip.');
		} finally {
			saving = false;
		}
	}

	function profileText(color: string) {
		const hex = color.replace('#', '');
		if (!/^[0-9a-f]{6}$/i.test(hex)) return '#1f1c22';
		const [red, green, blue] = [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
		const brightness = (red * 299 + green * 587 + blue * 114) / 1000;
		return brightness > 150 ? '#1f1c22' : '#ffffff';
	}
</script>

<svelte:head><title>Trips - TouchGrass</title></svelte:head>
<svelte:window on:keydown={(event) => event.key === 'Escape' && (editorOpen = false)} />

<main>
	<header>
		<div>
			<span class="eyebrow">Shared journeys</span>
			<h1>Trips</h1>
			<p>Plan the details together, then keep the memories in one place.</p>
		</div>
		<button class="primary" type="button" on:click={newTrip}><PlusIcon />Add trip</button>
	</header>

	<SkylightTripSync initialConnection={data.skylight} />

	<section>
		<div class="section-heading">
			<div>
				<span class="eyebrow">On the horizon</span>
				<h2>Upcoming trips</h2>
			</div>
			<strong>{currentTrips.length}</strong>
		</div>
		<div class="grid">
			{#each currentTrips as trip (trip.id)}
				<TripCard
					title={trip.title}
					startDate={trip.start_date}
					endDate={trip.end_date}
					profiles={trip.profile_details}
					locations={trip.destinations?.map(
						(destination) => destination.region_name || destination.country_name
					) || []}
					notes={trip.notes}
				>
					<svelte:fragment slot="actions">
						<a class="planner-link" href={trip.planner_url || `/collections/${trip.planner_id}`}
							>Open planner <ArrowIcon /></a
						>
						<button
							class="edit"
							type="button"
							on:click={() => editTrip(trip)}
							aria-label={`Edit ${trip.title}`}><PencilIcon />Edit</button
						>
					</svelte:fragment>
				</TripCard>
			{:else}
				<div class="empty">
					<MapIcon /><strong>No upcoming trips yet.</strong><span
						>Add one when inspiration strikes.</span
					>
				</div>
			{/each}
		</div>
	</section>

	<section>
		<div class="section-heading">
			<div>
				<span class="eyebrow">Where you have been</span>
				<h2>Past trips</h2>
			</div>
			<strong>{pastTrips.length}</strong>
		</div>
		<div class="grid">
			{#each pastTrips as trip (trip.id)}
				<TripCard
					title={trip.title}
					startDate={trip.start_date}
					endDate={trip.end_date}
					profiles={trip.profile_details}
					locations={trip.destinations?.map(
						(destination) => destination.region_name || destination.country_name
					) || []}
					notes={trip.notes}
				>
					<svelte:fragment slot="actions">
						<a class="planner-link" href={trip.planner_url || `/collections/${trip.planner_id}`}
							>View memories <ArrowIcon /></a
						>
						<button
							class="edit"
							type="button"
							on:click={() => editTrip(trip)}
							aria-label={`Edit ${trip.title}`}><PencilIcon />Edit</button
						>
					</svelte:fragment>
				</TripCard>
			{:else}
				<div class="empty">
					<CalendarIcon /><strong>No past trips yet.</strong><span
						>Finished trips will move here automatically.</span
					>
				</div>
			{/each}
		</div>
	</section>
</main>

{#if editorOpen}
	<button
		class="backdrop"
		type="button"
		aria-label="Close trip editor"
		on:click={() => (editorOpen = false)}
	></button>
	<aside role="dialog" aria-modal="true" aria-label={editing ? 'Edit trip' : 'New trip'}>
		<button class="close" type="button" on:click={() => (editorOpen = false)} aria-label="Close"
			><CloseIcon /></button
		>
		<span class="eyebrow">Trip planner</span>
		<h2>{editing ? 'Edit trip' : 'New trip'}</h2>
		<p class="editor-intro">
			These basics create the planner. Open the trip afterward to build the itinerary.
		</p>
		<label>Trip name<input bind:value={form.title} placeholder="Summer in Italy" /></label>
		<div class="date-fields">
			<label>Starts<input type="date" bind:value={form.start_date} /></label>
			<label>Ends<input type="date" bind:value={form.end_date} min={form.start_date} /></label>
		</div>
		<fieldset>
			<legend>Who is going?</legend>
			<div class="choices">
				{#each profiles as profile}
					<button
						type="button"
						class:selected={form.profiles.includes(profile.id)}
						style={`--profile-color:${profile.color};--profile-ink:${profileText(profile.color)}`}
						on:click={() => toggleProfile(profile.id)}
						aria-pressed={form.profiles.includes(profile.id)}
					>
						<span>{profile.avatar || profile.name[0]}</span>{profile.name}
					</button>
				{/each}
			</div>
		</fieldset>
		<label
			>Notes<textarea
				rows="4"
				bind:value={form.notes}
				placeholder="The big-picture plan, flight ideas, or a favorite memory…"
			></textarea></label
		>
		<div class="editor-actions">
			{#if editing}
				<button
					class:confirm={confirmingDelete}
					class="danger"
					type="button"
					disabled={saving}
					on:click={deleteTrip}
				>
					<TrashIcon />{confirmingDelete ? 'Confirm delete trip' : 'Delete trip'}
				</button>
			{/if}
			<button class="primary save" type="button" disabled={saving} on:click={save}
				>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create trip & planner'}</button
			>
		</div>
	</aside>
{/if}

<style>
	main {
		min-height: calc(100dvh - var(--tg-navbar-height));
		padding: clamp(1.25rem, 3vw, 3rem);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	header,
	section {
		max-width: var(--tg-content-width);
		margin: 0 auto 1.75rem;
	}
	header {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 1rem;
	}
	h1,
	h2 {
		font-family: var(--tg-font-display);
		font-weight: 400;
	}
	h1 {
		margin: 0.1rem 0;
		font-size: clamp(3.4rem, 6vw, 5.5rem);
		line-height: 0.95;
	}
	h2 {
		margin: 0.1rem 0;
		font-size: clamp(1.8rem, 3vw, 2.4rem);
	}
	header p,
	.editor-intro {
		color: var(--tg-ink-muted);
	}
	header p {
		margin: 0.5rem 0 0;
		font-size: 1.05rem;
	}
	.eyebrow {
		font-size: 0.72rem;
		font-weight: 800;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--tg-ink-muted);
	}
	button,
	a {
		font: inherit;
	}
	.primary,
	.edit,
	.close,
	.planner-link {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.45rem;
		min-height: 44px;
		border-radius: 999px;
		padding: 0.7rem 1rem;
		font-weight: 750;
		text-decoration: none;
		cursor: pointer;
	}
	.primary {
		border: 1px solid var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.primary:hover {
		background: var(--tg-action-hover);
	}
	.section-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		padding-bottom: 0.65rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.section-heading > strong {
		display: grid;
		min-width: 42px;
		height: 42px;
		place-items: center;
		border-radius: 50%;
		background: var(--tg-surface);
		border: 1px solid var(--tg-border);
		color: var(--tg-ink);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	.empty {
		position: relative;
		display: grid;
		min-height: 190px;
		overflow: hidden;
		padding: 1.3rem;
		place-items: center;
		align-content: center;
		gap: 0.3rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		color: var(--tg-ink-muted);
		text-align: center;
		box-shadow: var(--tg-shadow-card);
	}
	.empty :global(svg) {
		width: 32px;
		height: 32px;
	}
	.empty strong {
		color: var(--tg-ink);
	}
	.planner-link {
		padding-left: 0;
		color: var(--tg-action);
	}
	.planner-link:hover {
		text-decoration: underline;
	}
	.edit {
		border: 1px solid var(--tg-border-strong);
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: calc(var(--tg-layer-sidebar) - 1);
		width: 100%;
		height: 100%;
		border: 0;
		background: var(--tg-scrim);
	}
	aside {
		position: fixed;
		z-index: var(--tg-layer-sidebar);
		top: 0;
		right: 0;
		width: min(580px, 100%);
		height: 100dvh;
		box-sizing: border-box;
		padding: clamp(1.4rem, 4vw, 2.4rem);
		overflow: auto;
		border-left: 1px solid var(--tg-border);
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		opacity: 1;
		isolation: isolate;
		box-shadow: var(--tg-shadow-overlay);
	}
	aside h2 {
		margin: 0.2rem 0;
		font-size: clamp(2.5rem, 6vw, 3.6rem);
	}
	.close {
		position: absolute;
		top: 1rem;
		right: 1rem;
		padding: 0.65rem;
		border: 1px solid var(--tg-border);
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
	}
	label,
	legend {
		display: grid;
		gap: 0.45rem;
		margin: 1.15rem 0;
		color: var(--tg-ink);
		font-weight: 750;
	}
	input,
	textarea {
		width: 100%;
		box-sizing: border-box;
		padding: 0.85rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		opacity: 1;
		outline: none;
	}
	input::placeholder,
	textarea::placeholder {
		color: var(--tg-ink-muted);
		opacity: 1;
	}
	input:focus,
	textarea:focus {
		border-color: var(--tg-action);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--tg-action) 20%, transparent);
	}
	.date-fields {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.8rem;
	}
	fieldset {
		margin: 0;
		padding: 0;
		border: 0;
	}
	.choices {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
	}
	.choices button {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		min-height: 46px;
		padding: 0.45rem 0.8rem;
		border: 2px solid transparent;
		border-radius: 999px;
		background: color-mix(in srgb, var(--profile-color) 68%, var(--tg-overlay-surface));
		color: var(--tg-ink);
		cursor: pointer;
	}
	.choices button span {
		display: grid;
		width: 28px;
		height: 28px;
		place-items: center;
		border-radius: 50%;
		background: var(--profile-color);
		color: var(--profile-ink);
		font-weight: 850;
	}
	.choices button.selected {
		border-color: var(--tg-ink);
		box-shadow: 0 0 0 2px var(--profile-color);
	}
	.save {
		width: 100%;
		margin-top: 0.4rem;
	}
	.save:disabled {
		cursor: wait;
		opacity: 0.65;
	}
	.editor-actions {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 0.65rem;
		margin-top: 0.4rem;
	}
	.danger {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		gap: 0.45rem;
		padding: 0.7rem 1rem;
		border: 1px solid color-mix(in srgb, var(--tg-danger) 60%, var(--tg-border));
		border-radius: 999px;
		background: transparent;
		color: var(--tg-danger);
		font: inherit;
		font-weight: 800;
		cursor: pointer;
	}
	.danger.confirm {
		background: var(--tg-danger);
		color: var(--tg-danger-text, white);
	}
	.danger:disabled {
		cursor: wait;
		opacity: 0.65;
	}
	@media (max-width: 700px) {
		header {
			align-items: start;
			flex-direction: column;
		}
		.date-fields {
			grid-template-columns: 1fr;
		}
		.grid {
			grid-template-columns: 1fr;
		}
		.planner-link,
		.edit {
			width: 100%;
		}
	}
</style>
