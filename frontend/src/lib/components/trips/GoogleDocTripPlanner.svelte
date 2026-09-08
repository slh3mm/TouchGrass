<script lang="ts">
	import CalendarIcon from '~icons/mdi/calendar-range';
	import ExternalLinkIcon from '~icons/mdi/open-in-new';
	import FileDocumentIcon from '~icons/mdi/file-document-edit-outline';
	import LockIcon from '~icons/mdi/lock-outline';
	import PencilIcon from '~icons/mdi/pencil-outline';
	import TrashIcon from '~icons/mdi/trash-can-outline';
	import WebIcon from '~icons/mdi/web';
	import { addToast } from '$lib/toasts';
	import type { Collection, ContentImage } from '$lib/types';
	import TripPhotos from './TripPhotos.svelte';
	import { features } from '$lib/config';

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Destination = { id: string; country_name: string; region_name: string | null };
	type Trip = {
		id?: string;
		title?: string;
		start_date?: string;
		end_date?: string;
		profile_details: Profile[];
		destinations?: Destination[];
	};
	type PlannerView = 'planner' | 'photos';

	export let collection: Collection;
	export let trip: Trip;
	export let heroImages: ContentImage[] = [];
	export let canModify = false;

	const photosEnabled = features.tripPhotos;
	let currentView: PlannerView = 'planner';
	let editingLink = false;
	let saving = false;
	let documentUrl = collection.link || '';
	let linkError = '';

	$: documentId = parseDocumentId(collection.link || '');
	$: normalizedDocumentUrl = documentId
		? `https://docs.google.com/document/d/${documentId}/edit`
		: '';
	$: embeddedDocumentUrl = documentId ? `${normalizedDocumentUrl}?embedded=true` : '';
	$: destinations = (trip.destinations || [])
		.map((destination) => destination.region_name || destination.country_name)
		.filter(Boolean);
	$: profileGradient = buildProfileGradient(trip.profile_details || []);

	function csrf() {
		return (
			document.cookie
				.split('; ')
				.find((row) => row.startsWith('csrftoken='))
				?.split('=')[1] || ''
		);
	}

	function parseDocumentId(value: string) {
		if (!value.trim()) return '';
		try {
			const url = new URL(value.trim());
			if (url.protocol !== 'https:' || url.hostname !== 'docs.google.com') return '';
			const match = url.pathname.match(/^\/document\/(?:u\/\d+\/)?d\/([A-Za-z0-9_-]+)/);
			return match?.[1] || '';
		} catch {
			return '';
		}
	}

	function formatDate(value: string | null | undefined) {
		if (!value) return '';
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		}).format(new Date(`${value}T12:00:00`));
	}

	function profileText(color: string) {
		const hex = color.replace('#', '');
		if (!/^[0-9a-f]{6}$/i.test(hex)) return '#1f1c22';
		const [red, green, blue] = [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
		return (red * 299 + green * 587 + blue * 114) / 1000 > 150 ? '#1f1c22' : '#ffffff';
	}

	function buildProfileGradient(profiles: Profile[]) {
		const colors = profiles.map((profile) => profile.color).filter(Boolean);
		if (!colors.length) return 'linear-gradient(135deg,var(--tg-selected),var(--tg-canvas-deep))';
		if (colors.length === 1)
			return `linear-gradient(135deg,${colors[0]},color-mix(in srgb,${colors[0]} 35%,var(--tg-canvas)))`;
		const width = 100 / colors.length;
		const stops = colors.flatMap((color, index) => [
			`${color} ${index * width}%`,
			`${color} ${(index + 1) * width}%`
		]);
		return `linear-gradient(120deg,${stops.join(',')})`;
	}

	async function updateDocumentLink(nextLink: string) {
		saving = true;
		linkError = '';
		try {
			const response = await fetch(`/api/collections/${collection.id}/`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: JSON.stringify({ link: nextLink })
			});
			const result = await response.json().catch(() => null);
			if (!response.ok)
				throw new Error(result?.detail || result?.link?.[0] || 'Could not update the planner.');
			collection = { ...collection, link: result?.link || null };
			documentUrl = collection.link || '';
			editingLink = false;
			addToast('success', nextLink ? 'Google Doc connected' : 'Google Doc removed');
		} catch (error) {
			linkError = error instanceof Error ? error.message : 'Could not update the planner.';
			addToast('error', linkError);
		} finally {
			saving = false;
		}
	}

	async function saveDocument() {
		const id = parseDocumentId(documentUrl);
		if (!id) {
			linkError = 'Paste a standard Google Docs document URL.';
			return;
		}
		await updateDocumentLink(`https://docs.google.com/document/d/${id}/edit`);
	}

	async function removeDocument() {
		await updateDocumentLink('');
	}
</script>

<main class="trip-planner">
	<section
		class:with-photo={heroImages.length > 0}
		class="trip-hero"
		style={`--profile-gradient:${profileGradient}`}
	>
		{#if heroImages.length}
			<img src={heroImages[0].image} alt="" class="hero-photo" />
			<div class="photo-scrim"></div>
		{:else}
			<div class="map-texture" aria-hidden="true"></div>
		{/if}
		<div class="hero-content">
			<div class="hero-copy">
				<span class="eyebrow">Trip planner</span>
				<h1>{collection.name}</h1>
				{#if destinations.length}<p class="destination-line">{destinations.join(' · ')}</p>{/if}
				<div class="metadata">
					{#each trip.profile_details || [] as profile}
						<span
							class="profile"
							style={`--profile:${profile.color};--profile-ink:${profileText(profile.color)}`}
							>{profile.name}</span
						>
					{/each}
					<span class="dates"
						><CalendarIcon />{formatDate(collection.start_date)} – {formatDate(
							collection.end_date
						)}</span
					>
				</div>
				<span
					class="access"
					title={collection.is_public
						? 'Anyone with the TouchGrass link can view this trip.'
						: 'Only the trip owner and invited TouchGrass users can view this trip.'}
				>
					{#if collection.is_public}<WebIcon />{:else}<LockIcon />{/if}{collection.is_public
						? 'Public TouchGrass link'
						: 'Invited people only'}
				</span>
			</div>
		</div>
	</section>

	<section class="planner-shell">
		<nav aria-label="Trip content">
			<button
				class:active={currentView === 'planner'}
				type="button"
				on:click={() => (currentView = 'planner')}><FileDocumentIcon />Planner</button
			>
			{#if photosEnabled}<button
					class:active={currentView === 'photos'}
					type="button"
					on:click={() => (currentView = 'photos')}>Photos</button
				>{/if}
		</nav>

		{#if currentView === 'planner'}
			<div class="planner-heading">
				<div>
					<span class="eyebrow">Google Docs</span>
					<h2>Your shared plan</h2>
					<p>The document keeps its own Google sharing permissions.</p>
				</div>
				{#if documentId}
					<div class="planner-actions">
						<a class="primary" href={normalizedDocumentUrl} target="_blank" rel="noreferrer"
							><ExternalLinkIcon />Open in Google Docs</a
						>
						{#if canModify}<button
								class="secondary"
								type="button"
								on:click={() => {
									documentUrl = normalizedDocumentUrl;
									editingLink = !editingLink;
									linkError = '';
								}}><PencilIcon />Change</button
							>{/if}
					</div>
				{/if}
			</div>

			{#if canModify && editingLink}
				<div class="document-form">
					<label for="google-doc-url">Google Docs URL</label>
					<div>
						<input
							id="google-doc-url"
							type="url"
							bind:value={documentUrl}
							placeholder="https://docs.google.com/document/d/…/edit"
							aria-describedby="google-doc-help"
						/><button class="primary" type="button" disabled={saving} on:click={saveDocument}
							>{saving ? 'Saving…' : documentId ? 'Replace document' : 'Connect document'}</button
						>
					</div>
					<p id="google-doc-help">
						Share the document with each traveler’s Google account. TouchGrass cannot change Google
						permissions.
					</p>
					{#if linkError}<p class="error" role="alert">{linkError}</p>{/if}
					{#if documentId}<button
							class="remove"
							type="button"
							disabled={saving}
							on:click={removeDocument}><TrashIcon />Remove document</button
						>{/if}
				</div>
			{/if}

			{#if documentId}
				<div class="embed-frame">
					<iframe
						src={embeddedDocumentUrl}
						title={`${collection.name} Google Docs planner`}
						allow="clipboard-write"
						loading="eager"
					></iframe>
				</div>
				<p class="embed-help">
					If Google asks you to sign in or the editor does not load, use <a
						href={normalizedDocumentUrl}
						target="_blank"
						rel="noreferrer">Open in Google Docs</a
					>.
				</p>
			{:else if !canModify}
				<div class="empty-planner">
					<FileDocumentIcon />
					<h2>No Google Doc connected</h2>
					<p>A trip editor can connect the shared planner.</p>
				</div>
			{:else if !editingLink}
				<div class="empty-planner">
					<FileDocumentIcon />
					<h2>Connect your trip plan</h2>
					<p>Paste a Google Docs link to plan together without leaving TouchGrass.</p>
					<button class="primary" type="button" on:click={() => (editingLink = true)}
						>Add Google Doc</button
					>
				</div>
			{/if}
		{:else if currentView === 'photos' && photosEnabled && trip.id}
			<TripPhotos tripId={trip.id} {canModify} />
		{/if}
	</section>
</main>

<style>
	.trip-planner {
		min-height: calc(100dvh - var(--tg-navbar-height));
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	.trip-hero {
		position: relative;
		display: grid;
		min-height: clamp(260px, 34vh, 390px);
		overflow: hidden;
		background: var(--profile-gradient);
		isolation: isolate;
	}
	.trip-hero::after {
		content: '';
		position: absolute;
		inset: 0;
		z-index: -1;
		background: linear-gradient(
			180deg,
			color-mix(in srgb, var(--tg-canvas) 14%, transparent),
			color-mix(in srgb, var(--tg-canvas) 48%, transparent)
		);
	}
	.hero-photo,
	.photo-scrim,
	.map-texture {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.hero-photo {
		z-index: -3;
		object-fit: cover;
	}
	.photo-scrim {
		z-index: -2;
		background: linear-gradient(180deg, rgba(14, 18, 16, 0.12), rgba(14, 18, 16, 0.72));
	}
	.map-texture {
		z-index: -2;
		opacity: 0.34;
		background-image:
			radial-gradient(
				circle at 18% 35%,
				transparent 0 8%,
				color-mix(in srgb, var(--tg-ink) 18%, transparent) 8.3% 8.8%,
				transparent 9.1%
			),
			radial-gradient(
				circle at 74% 60%,
				transparent 0 12%,
				color-mix(in srgb, var(--tg-ink) 15%, transparent) 12.3% 12.8%,
				transparent 13.1%
			),
			repeating-linear-gradient(
				118deg,
				transparent 0 48px,
				color-mix(in srgb, var(--tg-ink) 8%, transparent) 49px 50px
			);
	}
	.hero-content {
		display: grid;
		width: min(100%, var(--tg-content-width));
		margin: auto;
		padding: clamp(2rem, 5vw, 5rem);
		place-items: center;
		text-align: center;
	}
	.hero-copy {
		max-width: 1000px;
	}
	.eyebrow {
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
		font-weight: 850;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	.with-photo .eyebrow,
	.with-photo .destination-line,
	.with-photo .access {
		color: rgba(255, 255, 255, 0.84);
	}
	h1,
	h2 {
		font-family: var(--tg-font-display);
		font-weight: 400;
	}
	h1 {
		margin: 0.2rem 0;
		font-size: clamp(3rem, 7vw, 6rem);
		line-height: 0.96;
		color: var(--tg-ink-strong);
	}
	.with-photo h1 {
		color: #fff;
		text-shadow: 0 3px 20px rgba(0, 0, 0, 0.4);
	}
	.destination-line {
		margin: 0.7rem 0;
		color: var(--tg-ink);
		font-size: clamp(0.95rem, 2vw, 1.2rem);
		font-weight: 750;
	}
	.metadata {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.5rem;
		margin-top: 1rem;
	}
	.metadata > span {
		display: inline-flex;
		min-height: 38px;
		align-items: center;
		gap: 0.35rem;
		padding: 0.4rem 0.75rem;
		border: 1px solid color-mix(in srgb, var(--tg-ink) 18%, transparent);
		border-radius: 999px;
		background: color-mix(in srgb, var(--tg-surface) 82%, transparent);
		color: var(--tg-ink);
		font-weight: 800;
		backdrop-filter: blur(12px);
	}
	.metadata .profile {
		border-color: var(--profile);
		background: var(--profile);
		color: var(--profile-ink);
	}
	.metadata :global(svg) {
		width: 18px;
	}
	.access {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		margin-top: 0.85rem;
		color: var(--tg-ink-muted);
		font-size: 0.76rem;
		font-weight: 750;
	}
	.access :global(svg) {
		width: 15px;
	}
	.planner-shell {
		width: min(calc(100% - 2rem), var(--tg-content-width));
		margin: 0 auto;
		padding: 1.25rem 0 3rem;
	}
	.planner-shell nav {
		display: flex;
		gap: 0.35rem;
		margin-bottom: 1.25rem;
		padding-bottom: 0.6rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.planner-shell nav button {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		gap: 0.4rem;
		padding: 0.6rem 0.9rem;
		border: 0;
		border-radius: 10px;
		background: transparent;
		color: var(--tg-ink-muted);
		font: inherit;
		font-weight: 800;
		cursor: pointer;
	}
	.planner-shell nav button.active {
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.planner-shell nav :global(svg) {
		width: 19px;
	}
	.planner-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.planner-heading h2 {
		margin: 0.15rem 0;
		font-size: clamp(2rem, 4vw, 3.1rem);
	}
	.planner-heading p {
		margin: 0;
		color: var(--tg-ink-muted);
	}
	.planner-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	.primary,
	.secondary,
	.remove {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		padding: 0.65rem 0.9rem;
		border-radius: 12px;
		font: inherit;
		font-weight: 800;
		text-decoration: none;
		cursor: pointer;
	}
	.primary {
		border: 1px solid var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.secondary {
		border: 1px solid var(--tg-border-strong);
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.remove {
		border: 0;
		background: transparent;
		color: var(--tg-danger);
	}
	button:disabled {
		cursor: wait;
		opacity: 0.62;
	}
	.document-form {
		margin-bottom: 1rem;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 16px;
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.document-form label {
		display: block;
		margin-bottom: 0.4rem;
		font-weight: 800;
	}
	.document-form > div {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 0.55rem;
	}
	.document-form input {
		min-width: 0;
		padding: 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		outline: none;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		font: inherit;
	}
	.document-form input:focus {
		border-color: var(--tg-action);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--tg-action) 18%, transparent);
	}
	.document-form > p {
		margin: 0.55rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	.document-form .error {
		color: var(--tg-danger);
	}
	.document-form .remove {
		margin-top: 0.5rem;
		padding-left: 0;
	}
	.embed-frame {
		height: max(620px, calc(100dvh - var(--tg-navbar-height) - 250px));
		overflow: hidden;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: #fff;
		box-shadow: var(--tg-shadow-card);
	}
	.embed-frame iframe {
		width: 100%;
		height: 100%;
		border: 0;
	}
	.embed-help {
		margin: 0.65rem 0;
		color: var(--tg-ink-muted);
		font-size: 0.82rem;
	}
	.embed-help a {
		color: var(--tg-action);
		font-weight: 800;
	}
	.empty-planner {
		display: grid;
		min-height: 380px;
		padding: 2rem;
		place-items: center;
		align-content: center;
		gap: 0.4rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		text-align: center;
		box-shadow: var(--tg-shadow-card);
	}
	.empty-planner :global(svg) {
		width: 52px;
		height: 52px;
		color: var(--tg-action);
	}
	.empty-planner h2,
	.empty-planner p {
		margin: 0;
	}
	.empty-planner p {
		color: var(--tg-ink-muted);
	}
	.empty-planner .primary {
		margin-top: 0.7rem;
	}
	@media (max-width: 700px) {
		.trip-hero {
			min-height: 300px;
		}
		.hero-content {
			padding: 2rem 1rem;
		}
		.planner-shell {
			width: min(calc(100% - 1rem), var(--tg-content-width));
		}
		.planner-heading {
			align-items: flex-start;
			flex-direction: column;
		}
		.planner-actions,
		.planner-actions a,
		.planner-actions button {
			width: 100%;
		}
		.document-form > div {
			grid-template-columns: 1fr;
		}
		.embed-frame {
			height: 70dvh;
			min-height: 520px;
		}
		.metadata {
			gap: 0.35rem;
		}
		.metadata > span {
			font-size: 0.78rem;
		}
	}
</style>
