<script lang="ts">
	import { onMount } from 'svelte';
	import ArrowLeftIcon from '~icons/mdi/arrow-left';
	import CalendarSearchIcon from '~icons/mdi/calendar-search';
	import CheckIcon from '~icons/mdi/check';
	import CloseIcon from '~icons/mdi/close';
	import RefreshIcon from '~icons/mdi/refresh';
	import SearchIcon from '~icons/mdi/magnify';
	import SaveIcon from '~icons/mdi/content-save-outline';
	import UndoIcon from '~icons/mdi/undo-variant';
	import { addToast } from '$lib/toasts';
	import type { PageData } from './$types';

	export let data: PageData;

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Label = 'unreviewed' | 'trip' | 'not_trip';
	type Review = {
		id: string;
		title: string;
		start_date: string;
		end_date: string;
		all_day: boolean;
		calendar_description: string;
		location: string;
		profile_details: Profile[];
		predicted_is_trip: boolean;
		detection_score: number;
		detection_reasons: string[];
		human_label: Label;
		reviewer_note: string;
	};
	type ReviewData = {
		connected: boolean;
		last_sync_at: string | null;
		future_cutoff: string | null;
		counts: Record<'all' | Label, number>;
		events: Review[];
	};

	let reviewData = data.reviewData as ReviewData;
	let searchQuery = '';
	let activeFilter: 'all' | Label = 'unreviewed';
	let page = 1;
	const pageSize = 40;
	let refreshing = false;
	let savingIds = new Set<string>();
	let savedNotes: Record<string, string> = Object.fromEntries(
		reviewData.events.map((event) => [event.id, event.reviewer_note])
	);

	$: normalizedQuery = searchQuery.trim().toLocaleLowerCase();
	$: filteredEvents = reviewData.events.filter((event) => {
		if (activeFilter !== 'all' && event.human_label !== activeFilter) return false;
		if (!normalizedQuery) return true;
		return [
			event.title,
			event.location,
			event.calendar_description,
			event.reviewer_note,
			...event.profile_details.map((profile) => profile.name)
		]
			.join(' ')
			.toLocaleLowerCase()
			.includes(normalizedQuery);
	});
	$: totalPages = Math.max(1, Math.ceil(filteredEvents.length / pageSize));
	$: if (page > totalPages) page = totalPages;
	$: visibleEvents = filteredEvents.slice((page - 1) * pageSize, page * pageSize);

	function csrf() {
		return (
			document.cookie
				.split('; ')
				.find((row) => row.startsWith('csrftoken='))
				?.split('=')[1] || ''
		);
	}

	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: {
				...(options.body ? { 'Content-Type': 'application/json' } : {}),
				'X-CSRFToken': csrf(),
				...(options.headers || {})
			}
		});
		const result = await response.json().catch(() => null);
		if (!response.ok)
			throw new Error(result?.error || result?.detail || 'The review could not be saved.');
		return result;
	}

	function setSaving(id: string, saving: boolean) {
		const next = new Set(savingIds);
		if (saving) next.add(id);
		else next.delete(id);
		savingIds = next;
	}

	function recalculateCounts(events: Review[]) {
		return {
			all: events.length,
			unreviewed: events.filter((event) => event.human_label === 'unreviewed').length,
			trip: events.filter((event) => event.human_label === 'trip').length,
			not_trip: events.filter((event) => event.human_label === 'not_trip').length
		};
	}

	function replaceEvent(updated: Review) {
		const events = reviewData.events.map((event) => (event.id === updated.id ? updated : event));
		reviewData = { ...reviewData, events, counts: recalculateCounts(events) };
	}

	async function saveEvent(
		event: Review,
		changes: Partial<Pick<Review, 'human_label' | 'reviewer_note'>>
	) {
		setSaving(event.id, true);
		try {
			// A label click also saves an in-progress note so choosing Yes/No can
			// never discard context the reviewer typed first.
			const payload =
				changes.human_label === undefined
					? changes
					: { ...changes, reviewer_note: event.reviewer_note };
			const updated = await api(`/api/skylight/events/${event.id}/`, {
				method: 'PATCH',
				body: JSON.stringify(payload)
			});
			replaceEvent(updated);
			if (payload.reviewer_note !== undefined)
				savedNotes = { ...savedNotes, [event.id]: updated.reviewer_note };
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'The review could not be saved.');
		} finally {
			setSaving(event.id, false);
		}
	}

	async function refreshEvents(showToast = true) {
		if (refreshing || !reviewData.connected) return;
		refreshing = true;
		try {
			const result = await api('/api/skylight/events/refresh/', {
				method: 'POST',
				body: JSON.stringify({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
			});
			reviewData = result.review_data;
			savedNotes = Object.fromEntries(
				reviewData.events.map((event) => [event.id, event.reviewer_note])
			);
			if (showToast)
				addToast('success', `Loaded ${result.sync.events_seen} Skylight calendar events`);
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Skylight could not be refreshed.'
			);
		} finally {
			refreshing = false;
		}
	}

	function chooseFilter(filter: 'all' | Label) {
		activeFilter = filter;
		page = 1;
	}
	function handleSearch() {
		page = 1;
	}
	function labelCopy(label: Label) {
		return label === 'trip' ? 'Trip' : label === 'not_trip' ? 'Not a trip' : 'Unreviewed';
	}
	function formatDateRange(start: string, end: string) {
		const formatter = new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
		const first = formatter.format(new Date(`${start}T12:00:00`));
		const last = formatter.format(new Date(`${end}T12:00:00`));
		return start === end ? first : `${first} – ${last}`;
	}
	function formatSync(value: string | null) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
					new Date(value)
				)
			: 'Not refreshed yet';
	}

	onMount(() => {
		if (reviewData.connected && reviewData.events.length === 0) void refreshEvents(false);
	});
</script>

<svelte:head><title>Skylight event review · TouchGrass</title></svelte:head>

<main class="review-page">
	<header class="hero">
		<a class="back" href="/trips"><ArrowLeftIcon />Trips</a>
		<div class="hero-row">
			<div>
				<span class="eyebrow">Temporary classification lab</span>
				<h1>Skylight event review</h1>
				<p>
					Teach TouchGrass which calendar events really were trips. Your decisions and notes remain
					untouched when Skylight refreshes.
				</p>
			</div>
			<button
				class="refresh"
				type="button"
				disabled={refreshing || !reviewData.connected}
				on:click={() => refreshEvents(true)}
				><span class:spin={refreshing}><RefreshIcon /></span>{refreshing
					? 'Refreshing…'
					: 'Refresh calendar'}</button
			>
		</div>
		<p class="last-sync">
			Last refreshed {formatSync(reviewData.last_sync_at)} · Showing all past events and events through
			{reviewData.future_cutoff
				? formatDateRange(reviewData.future_cutoff, reviewData.future_cutoff)
				: 'the next three months'}
		</p>
	</header>

	{#if !reviewData.connected}
		<section class="empty-state">
			<CalendarSearchIcon />
			<h2>Connect Skylight first</h2>
			<p>Return to Trips, connect the calendar, then come back here to build the training set.</p>
			<a href="/trips">Open Trips</a>
		</section>
	{:else}
		<section class="toolbar" aria-label="Review filters">
			<label class="search"
				><SearchIcon /><input
					bind:value={searchQuery}
					on:input={handleSearch}
					placeholder="Search titles, locations, profiles, and notes"
				/></label
			>
			<div class="filters">
				<button
					class:active={activeFilter === 'unreviewed'}
					type="button"
					on:click={() => chooseFilter('unreviewed')}
					>Unreviewed <b>{reviewData.counts.unreviewed}</b></button
				>
				<button
					class:active={activeFilter === 'trip'}
					type="button"
					on:click={() => chooseFilter('trip')}>Trips <b>{reviewData.counts.trip}</b></button
				>
				<button
					class:active={activeFilter === 'not_trip'}
					type="button"
					on:click={() => chooseFilter('not_trip')}
					>Not trips <b>{reviewData.counts.not_trip}</b></button
				>
				<button
					class:active={activeFilter === 'all'}
					type="button"
					on:click={() => chooseFilter('all')}>All <b>{reviewData.counts.all}</b></button
				>
			</div>
		</section>

		<div class="result-row">
			<strong>{filteredEvents.length} event{filteredEvents.length === 1 ? '' : 's'}</strong
			>{#if totalPages > 1}<span>Page {page} of {totalPages}</span>{/if}
		</div>
		<section class="event-list" aria-live="polite">
			{#each visibleEvents as event (event.id)}
				<article
					class:label-trip={event.human_label === 'trip'}
					class:label-not-trip={event.human_label === 'not_trip'}
				>
					<div class="event-main">
						<div class="event-heading">
							<div>
								<div class="profile-row">
									{#each event.profile_details as profile}<span
											class="profile"
											style={`--profile:${profile.color}`}
											>{profile.avatar || profile.name.slice(0, 1)} {profile.name}</span
										>{/each}{#if event.profile_details.length === 0}<span class="profile unmapped"
											>Unmapped calendar</span
										>{/if}
								</div>
								<h2>{event.title}</h2>
								<p class="date">
									{formatDateRange(event.start_date, event.end_date)}{event.all_day
										? ' · All day'
										: ''}
								</p>
								{#if event.location}<p class="location">{event.location}</p>{/if}
							</div>
							<span class:likely={event.predicted_is_trip} class="prediction"
								>{event.predicted_is_trip ? 'Predicted trip' : 'Predicted not trip'} · {event.detection_score}</span
							>
						</div>
						{#if event.calendar_description || event.detection_reasons.length}<details>
								<summary>Classifier context</summary>{#if event.calendar_description}<p>
										{event.calendar_description}
									</p>{/if}{#if event.detection_reasons.length}<ul>
										{#each event.detection_reasons as reason}<li>{reason}</li>{/each}
									</ul>{/if}
							</details>{/if}
					</div>
					<div class="human-review">
						<span class="current-label"
							>Ground truth: <strong>{labelCopy(event.human_label)}</strong></span
						>
						<div class="decision-buttons">
							<button
								class:selected={event.human_label === 'trip'}
								class="yes"
								type="button"
								disabled={savingIds.has(event.id)}
								on:click={() => saveEvent(event, { human_label: 'trip' })}
								><CheckIcon />Yes, trip</button
							>
							<button
								class:selected={event.human_label === 'not_trip'}
								class="no"
								type="button"
								disabled={savingIds.has(event.id)}
								on:click={() => saveEvent(event, { human_label: 'not_trip' })}
								><CloseIcon />No, not a trip</button
							>
							{#if event.human_label !== 'unreviewed'}<button
									class="reset"
									title="Return to unreviewed"
									type="button"
									disabled={savingIds.has(event.id)}
									on:click={() => saveEvent(event, { human_label: 'unreviewed' })}
									><UndoIcon /></button
								>{/if}
						</div>
						<label class="note"
							>Note for future classification<textarea
								bind:value={event.reviewer_note}
								rows="2"
								placeholder="Why was or wasn’t this a trip? Add any context the calendar title misses."
							></textarea></label
						>
						<button
							class="save-note"
							type="button"
							disabled={savingIds.has(event.id) || savedNotes[event.id] === event.reviewer_note}
							on:click={() => saveEvent(event, { reviewer_note: event.reviewer_note })}
							><SaveIcon />{savingIds.has(event.id)
								? 'Saving…'
								: savedNotes[event.id] === event.reviewer_note
									? 'Note saved'
									: 'Save note'}</button
						>
					</div>
				</article>
			{:else}
				<div class="empty-state compact">
					<CalendarSearchIcon />
					<h2>No matching events</h2>
					<p>Try another filter or search.</p>
				</div>
			{/each}
		</section>
		{#if totalPages > 1}<nav class="pagination" aria-label="Event pages">
				<button
					type="button"
					disabled={page === 1}
					on:click={() => {
						page -= 1;
						window.scrollTo({ top: 0, behavior: 'smooth' });
					}}>Previous</button
				><span>Page {page} of {totalPages}</span><button
					type="button"
					disabled={page === totalPages}
					on:click={() => {
						page += 1;
						window.scrollTo({ top: 0, behavior: 'smooth' });
					}}>Next</button
				>
			</nav>{/if}
	{/if}
</main>

<style>
	.review-page {
		min-height: calc(100dvh - var(--tg-navbar-height));
		margin: 0 auto;
		padding: clamp(1.2rem, 4vw, 3.25rem);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	.hero,
	.toolbar,
	.result-row,
	.event-list,
	.pagination,
	.empty-state {
		width: min(100%, var(--tg-content-width));
		margin-inline: auto;
	}
	.hero {
		padding-bottom: 1.25rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		color: var(--tg-ink-muted);
		font-weight: 750;
		text-decoration: none;
	}
	.back :global(svg) {
		width: 19px;
	}
	.hero-row {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1.5rem;
		margin-top: 1.1rem;
	}
	.eyebrow {
		font-size: 0.72rem;
		font-weight: 850;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--tg-action);
	}
	h1,
	h2 {
		font-family: var(--tg-font-display);
		font-weight: 400;
	}
	h1 {
		margin: 0.15rem 0;
		font-size: clamp(2.7rem, 7vw, 5.5rem);
		line-height: 0.95;
	}
	.hero p {
		max-width: 780px;
		margin: 0.65rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 1.02rem;
	}
	.last-sync {
		font-size: 0.78rem !important;
	}
	.refresh,
	.pagination button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		min-height: 44px;
		padding: 0.65rem 1rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font: inherit;
		font-weight: 800;
		white-space: nowrap;
		cursor: pointer;
	}
	.refresh :global(svg) {
		width: 19px;
	}
	.refresh:disabled,
	.pagination button:disabled {
		cursor: wait;
		opacity: 0.55;
	}
	.spin {
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.toolbar {
		position: sticky;
		top: 0;
		z-index: 4;
		display: grid;
		grid-template-columns: minmax(280px, 1fr) auto;
		gap: 1rem;
		margin: 1.25rem 0;
		padding: 0.75rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-overlay-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-overlay-field);
	}
	.search :global(svg) {
		flex: 0 0 auto;
		width: 21px;
		color: var(--tg-ink-muted);
	}
	.search input {
		width: 100%;
		min-height: 44px;
		border: 0;
		outline: 0;
		background: transparent;
		color: var(--tg-ink);
		font: inherit;
		font-weight: 650;
	}
	.search input::placeholder {
		color: var(--tg-ink-muted);
	}
	.filters {
		display: flex;
		gap: 0.35rem;
		overflow-x: auto;
	}
	.filters button {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		min-height: 44px;
		padding: 0.55rem 0.75rem;
		border: 1px solid transparent;
		border-radius: 999px;
		background: transparent;
		color: var(--tg-ink-muted);
		font: inherit;
		font-weight: 780;
		white-space: nowrap;
		cursor: pointer;
	}
	.filters button b {
		display: grid;
		min-width: 24px;
		height: 24px;
		padding: 0 0.25rem;
		place-items: center;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink);
		font-size: 0.72rem;
	}
	.filters button.active {
		border-color: var(--tg-border-strong);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.filters button.active b {
		background: color-mix(in srgb, var(--tg-surface) 88%, transparent);
	}
	.result-row {
		display: flex;
		justify-content: space-between;
		margin-top: 0.8rem;
		margin-bottom: 0.8rem;
		color: var(--tg-ink-muted);
		font-size: 0.85rem;
	}
	.event-list {
		display: grid;
		gap: 0.8rem;
	}
	.event-list article {
		display: grid;
		grid-template-columns: minmax(0, 1.25fr) minmax(300px, 0.75fr);
		overflow: hidden;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.event-list article.label-trip {
		border-left: 5px solid var(--tg-success);
	}
	.event-list article.label-not-trip {
		border-left: 5px solid var(--tg-danger);
	}
	.event-main,
	.human-review {
		padding: 1rem;
	}
	.human-review {
		border-left: 1px solid var(--tg-border);
		background: var(--tg-overlay-surface);
	}
	.event-heading {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	.event-heading h2 {
		margin: 0.4rem 0 0.15rem;
		font-size: clamp(1.35rem, 2vw, 1.8rem);
		line-height: 1.05;
	}
	.date,
	.location {
		margin: 0.25rem 0;
		color: var(--tg-ink-muted);
	}
	.date {
		font-weight: 750;
	}
	.profile-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}
	.profile {
		display: inline-flex;
		align-items: center;
		padding: 0.22rem 0.5rem;
		border-radius: 999px;
		background: color-mix(in srgb, var(--profile) 30%, var(--tg-surface));
		color: var(--tg-ink);
		font-size: 0.72rem;
		font-weight: 800;
	}
	.profile.unmapped {
		--profile: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
	}
	.prediction {
		flex: 0 0 auto;
		padding: 0.3rem 0.55rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
		font-weight: 800;
	}
	.prediction.likely {
		border-color: color-mix(in srgb, var(--tg-action) 45%, var(--tg-border));
		color: var(--tg-action);
	}
	details {
		margin-top: 0.75rem;
		padding-top: 0.65rem;
		border-top: 1px solid var(--tg-border);
		color: var(--tg-ink-muted);
		font-size: 0.82rem;
	}
	summary {
		color: var(--tg-ink);
		font-weight: 750;
		cursor: pointer;
	}
	details p,
	details ul {
		margin: 0.45rem 0;
	}
	.current-label {
		display: block;
		margin-bottom: 0.55rem;
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	.current-label strong {
		color: var(--tg-ink);
	}
	.decision-buttons {
		display: flex;
		gap: 0.4rem;
	}
	.decision-buttons button,
	.save-note {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
		min-height: 39px;
		padding: 0.5rem 0.7rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font: inherit;
		font-size: 0.82rem;
		font-weight: 800;
		cursor: pointer;
	}
	.decision-buttons button :global(svg),
	.save-note :global(svg) {
		width: 17px;
	}
	.decision-buttons .yes.selected {
		border-color: var(--tg-success);
		background: var(--tg-success);
		color: var(--tg-success-text);
	}
	.decision-buttons .no.selected {
		border-color: var(--tg-danger);
		background: var(--tg-danger);
		color: var(--tg-danger-text);
	}
	.decision-buttons .reset {
		width: 39px;
		padding: 0;
		color: var(--tg-ink-muted);
	}
	.decision-buttons button:disabled,
	.save-note:disabled {
		cursor: default;
		opacity: 0.58;
	}
	.note {
		display: grid;
		gap: 0.35rem;
		margin-top: 0.75rem;
		color: var(--tg-ink);
		font-size: 0.78rem;
		font-weight: 800;
	}
	.note textarea {
		resize: vertical;
		width: 100%;
		box-sizing: border-box;
		padding: 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		outline: 0;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		font: inherit;
		font-size: 0.86rem;
	}
	.note textarea:focus {
		border-color: var(--tg-action);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--tg-action) 18%, transparent);
	}
	.note textarea::placeholder {
		color: var(--tg-ink-muted);
	}
	.save-note {
		margin-top: 0.45rem;
	}
	.empty-state {
		display: grid;
		min-height: 300px;
		margin-top: 1.5rem;
		padding: 2rem;
		place-items: center;
		align-content: center;
		gap: 0.45rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-surface);
		text-align: center;
	}
	.empty-state.compact {
		min-height: 180px;
		margin: 0;
	}
	.empty-state :global(svg) {
		width: 38px;
		height: 38px;
		color: var(--tg-action);
	}
	.empty-state h2,
	.empty-state p {
		margin: 0;
	}
	.empty-state p {
		color: var(--tg-ink-muted);
	}
	.empty-state a {
		margin-top: 0.5rem;
		color: var(--tg-action);
		font-weight: 800;
	}
	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		margin-top: 1.2rem;
		color: var(--tg-ink-muted);
		font-weight: 750;
	}
	@media (max-width: 900px) {
		.hero-row {
			align-items: flex-start;
			flex-direction: column;
		}
		.toolbar {
			position: static;
			grid-template-columns: 1fr;
		}
		.event-list article {
			grid-template-columns: 1fr;
		}
		.human-review {
			border-top: 1px solid var(--tg-border);
			border-left: 0;
		}
	}
	@media (max-width: 560px) {
		.review-page {
			padding: 1rem;
		}
		.refresh {
			width: 100%;
		}
		.filters {
			display: grid;
			grid-template-columns: 1fr 1fr;
		}
		.filters button {
			justify-content: center;
		}
		.event-heading {
			flex-direction: column;
		}
		.prediction {
			order: -1;
		}
		.decision-buttons {
			display: grid;
			grid-template-columns: 1fr 1fr;
		}
		.decision-buttons .reset {
			width: auto;
			grid-column: 1/-1;
		}
		.pagination {
			justify-content: space-between;
		}
		.pagination span {
			font-size: 0.78rem;
		}
	}
</style>
