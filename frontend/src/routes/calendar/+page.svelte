<script lang="ts">
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import CalendarPlusIcon from '~icons/mdi/calendar-plus';
	import DownloadIcon from '~icons/mdi/download';
	import SearchIcon from '~icons/mdi/magnify';
	import ClearIcon from '~icons/mdi/close';
	import CalendarComponent from '$lib/components/calendar/Calendar.svelte';
	import EventDetailsModal from '$lib/components/calendar/EventDetailsModal.svelte';

	export let data: PageData;

	const allDates = data.props.dates;
	const categoryColors = ['#fb8072', '#fdbf6f', '#a6cee3', '#cab2d6', '#80b1d3', '#b3de69'];
	const categories = Array.from(
		new Set(allDates.map((event) => event.extendedProps?.category || 'Adventure'))
	);

	let searchFilter = '';
	let activeCategories = new Set(categories);
	let now = new Date();
	let selectedEvent: any = null;
	let showEventModal = false;
	let eventDetails: Record<string, { description?: string | null; location?: string | null }> = {};
	let loadingDetailIds = new Set<string>();
	let isLoadingDetails = false;
	let detailsError = '';
	let isDownloadingIcs = false;

	$: filteredDates = allDates.filter((event) => {
		const query = searchFilter.trim().toLowerCase();
		const matchesSearch =
			!query ||
			event.extendedProps?.adventureName?.toLowerCase().includes(query) ||
			event.extendedProps?.location?.toLowerCase().includes(query);
		const matchesCategory = activeCategories.has(event.extendedProps?.category || 'Adventure');
		return matchesSearch && matchesCategory;
	});

	$: selectedAdventureDetails = selectedEvent?.extendedProps?.adventureId
		? eventDetails[selectedEvent.extendedProps.adventureId]
		: null;
	$: currentLocation = selectedEvent?.extendedProps
		? (selectedAdventureDetails?.location ?? selectedEvent.extendedProps.location)
		: '';
	$: descriptionToShow = selectedEvent?.extendedProps
		? (selectedAdventureDetails?.description ?? selectedEvent.extendedProps.description)
		: '';

	onMount(() => {
		const timer = window.setInterval(() => (now = new Date()), 60_000);
		return () => window.clearInterval(timer);
	});

	function toggleCategory(category: string) {
		const next = new Set(activeCategories);
		next.has(category) ? next.delete(category) : next.add(category);
		activeCategories = next;
	}

	function handleEventClick(event: any) {
		selectedEvent = event;
		showEventModal = true;
		detailsError = '';
		if (event?.extendedProps?.adventureId) fetchEventDetails(event.extendedProps.adventureId);
	}

	function closeModal() {
		showEventModal = false;
		selectedEvent = null;
		detailsError = '';
	}

	async function fetchEventDetails(adventureId: string) {
		if (eventDetails[adventureId] || loadingDetailIds.has(adventureId)) return;
		loadingDetailIds.add(adventureId);
		isLoadingDetails = true;
		try {
			const response = await fetch(`/api/locations/${adventureId}/`);
			if (!response.ok) throw new Error('Failed to load event details');
			const detail = await response.json();
			eventDetails = {
				...eventDetails,
				[adventureId]: { description: detail.description, location: detail.location ?? '' }
			};
		} catch {
			detailsError = 'Unable to load event details right now.';
		} finally {
			loadingDetailIds.delete(adventureId);
			isLoadingDetails = loadingDetailIds.size > 0;
		}
	}

	async function downloadIcs() {
		if (isDownloadingIcs) return;
		isDownloadingIcs = true;
		try {
			const response = await fetch('/api/ics-calendar/generate/');
			if (!response.ok) throw new Error('Unable to generate calendar');
			const url = URL.createObjectURL(await response.blob());
			const link = document.createElement('a');
			link.href = url;
			link.download = 'adventures.ics';
			link.click();
			URL.revokeObjectURL(url);
		} finally {
			isDownloadingIcs = false;
		}
	}
</script>

<svelte:head>
	<title>Calendar - TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<main class="skylight-shell">
	<div class="backdrop"></div>
	<div class="calendar-dashboard">
		<header class="glance-header">
			<div class="date-block">
				<p>{now.toLocaleDateString(undefined, { weekday: 'long' })}</p>
				<h1>
					{now.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
				</h1>
			</div>
			<div class="time-block">
				{now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
			</div>
			<div class="summary-block">
				<span class="summary-kicker">TouchGrass</span>
				<strong>{filteredDates.length} upcoming moments</strong>
				<span>Plan less. Go outside more.</span>
			</div>
		</header>

		<section class="calendar-controls" aria-label="Calendar controls">
			<div class="title-row">
				<div>
					<span class="eyebrow">Shared schedule</span>
					<h2>My Calendar</h2>
				</div>
				<div class="action-group">
					<label class="search-box">
						<SearchIcon />
						<input
							bind:value={searchFilter}
							placeholder="Find an adventure"
							aria-label="Search calendar"
						/>
						{#if searchFilter}
							<button on:click={() => (searchFilter = '')} aria-label="Clear search"
								><ClearIcon /></button
							>
						{/if}
					</label>
					<button
						class="icon-button"
						on:click={downloadIcs}
						disabled={isDownloadingIcs}
						title="Download calendar"
					>
						<DownloadIcon />
					</button>
					<a class="add-button" href="/locations"><CalendarPlusIcon /> Add adventure</a>
				</div>
			</div>

			{#if categories.length}
				<div class="category-pills">
					{#each categories as category, index}
						<button
							class:inactive={!activeCategories.has(category)}
							style={`--category-color: ${categoryColors[index % categoryColors.length]}`}
							on:click={() => toggleCategory(category)}
						>
							<span>{category.slice(0, 1).toUpperCase()}</span>{category}
						</button>
					{/each}
				</div>
			{/if}
		</section>

		<section class="calendar-panel">
			<CalendarComponent events={filteredDates} onEventClick={handleEventClick} dayMaxEvents={4} />
		</section>
	</div>
</main>

<EventDetailsModal
	show={showEventModal}
	event={selectedEvent}
	{isLoadingDetails}
	{detailsError}
	location={currentLocation}
	description={descriptionToShow}
	onClose={closeModal}
/>

<style>
	.skylight-shell {
		position: relative;
		min-height: 100vh;
		overflow: hidden;
		color: var(--tg-ink);
		font-family: var(--tg-font-body);
	}
	.backdrop {
		position: fixed;
		inset: 0;
		background:
			linear-gradient(
				120deg,
				color-mix(in srgb, var(--tg-canvas) 90%, transparent),
				color-mix(in srgb, var(--tg-canvas-deep) 76%, transparent)
			),
			url('/backgrounds/adventurelog_showcase_6.webp') center/cover;
	}
	.calendar-dashboard {
		position: relative;
		z-index: 1;
		width: min(1780px, 100%);
		margin: auto;
		padding: clamp(1rem, 2vw, 2.25rem);
	}
	.glance-header {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		gap: 2rem;
		min-height: 170px;
		padding: 1rem 2.5rem;
	}
	.date-block p,
	.date-block h1,
	.summary-block span {
		margin: 0;
	}
	.date-block p {
		font-size: 1.05rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
	}
	.date-block h1,
	.time-block,
	.calendar-controls h2 {
		font-family: 'Ovo', Georgia, serif;
		font-weight: 400;
	}
	.date-block h1 {
		margin-top: 0.25rem;
		font-size: clamp(2rem, 3vw, 3.5rem);
	}
	.time-block {
		font-size: clamp(3.5rem, 6vw, 6.5rem);
		line-height: 1;
		white-space: nowrap;
	}
	.summary-block {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		text-align: right;
		gap: 0.25rem;
	}
	.summary-kicker,
	.eyebrow {
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	.calendar-controls,
	.calendar-panel {
		background: var(--tg-surface-glass);
		backdrop-filter: blur(var(--tg-blur-panel));
	}
	.calendar-controls {
		border-radius: 24px 24px 0 0;
		padding: 1.5rem 1.75rem 1rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.title-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
	}
	.calendar-controls h2 {
		margin: 0.1rem 0 0;
		font-size: 2.25rem;
	}
	.action-group,
	.category-pills {
		display: flex;
		align-items: center;
		gap: 0.7rem;
	}
	.search-box {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		height: 44px;
		padding: 0 0.8rem;
		border: 1px solid var(--tg-border);
		border-radius: 999px;
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.search-box :global(svg),
	.icon-button :global(svg),
	.add-button :global(svg) {
		width: 1.15rem;
		height: 1.15rem;
	}
	.search-box input {
		width: 150px;
		border: 0;
		outline: 0;
		background: transparent;
	}
	.search-box button {
		display: grid;
		border: 0;
		padding: 0;
		background: none;
		cursor: pointer;
	}
	.icon-button,
	.add-button {
		display: inline-flex;
		height: 44px;
		align-items: center;
		justify-content: center;
		border: 0;
		border-radius: 999px;
		cursor: pointer;
	}
	.icon-button {
		width: 44px;
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.add-button {
		gap: 0.45rem;
		padding: 0 1.2rem;
		background: var(--tg-action);
		color: var(--tg-action-text);
		font-weight: 600;
		text-decoration: none;
	}
	.category-pills {
		flex-wrap: wrap;
		margin-top: 1.2rem;
	}
	.category-pills button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border: 0;
		border-radius: 999px;
		padding: 0.38rem 0.8rem 0.38rem 0.4rem;
		background: color-mix(in srgb, var(--category-color) 65%, white);
		color: #353238;
		font-weight: 600;
		cursor: pointer;
		transition:
			opacity 0.2s,
			filter 0.2s;
	}
	.category-pills button span {
		display: grid;
		width: 28px;
		height: 28px;
		place-items: center;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.72);
	}
	.category-pills button.inactive {
		opacity: 0.42;
		filter: grayscale(0.85);
	}
	.calendar-panel {
		min-height: 580px;
		padding: 0 1.25rem 1.25rem;
		border-radius: 0 0 24px 24px;
	}

	@media (max-width: 850px) {
		.glance-header {
			grid-template-columns: 1fr auto;
			min-height: 130px;
			padding: 1rem;
		}
		.summary-block {
			display: none;
		}
		.title-row {
			align-items: flex-start;
			flex-direction: column;
		}
		.action-group {
			width: 100%;
			flex-wrap: wrap;
		}
		.search-box {
			flex: 1;
		}
		.search-box input {
			width: 100%;
		}
	}
	@media (max-width: 520px) {
		.calendar-dashboard {
			padding: 0.5rem;
		}
		.glance-header {
			display: block;
			min-height: 0;
			padding: 1.25rem 0.5rem;
		}
		.date-block h1 {
			font-size: 1.7rem;
		}
		.time-block {
			margin-top: 0.3rem;
			font-size: 3rem;
		}
		.add-button {
			padding: 0 0.8rem;
		}
		.calendar-controls {
			padding: 1.1rem 0.8rem 0.8rem;
		}
		.calendar-panel {
			padding: 0 0.35rem 0.75rem;
		}
	}
</style>
