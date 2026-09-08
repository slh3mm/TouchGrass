<script lang="ts">
	import { onMount } from 'svelte';
	import CalendarSyncIcon from '~icons/mdi/calendar-sync';
	import CheckIcon from '~icons/mdi/check';
	import LinkIcon from '~icons/mdi/link-variant';
	import LockIcon from '~icons/mdi/lock';
	import RefreshIcon from '~icons/mdi/refresh';
	import { addToast } from '$lib/toasts';
	import IntegrationCard from '$lib/components/settings/IntegrationCard.svelte';
	import SkylightProfileMappings from '$lib/components/trips/SkylightProfileMappings.svelte';
	import TripCard from '$lib/components/trips/TripCard.svelte';

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Mapping = {
		id: string;
		skylight_category_id: string;
		skylight_category_name: string;
		profile: string | null;
		profile_name: string | null;
		profile_color: string | null;
	};
	type Suggestion = {
		id: string;
		title: string;
		start_date: string;
		end_date: string;
		notes: string;
		location: string;
		detection_score: number;
		detection_reasons: string[];
		profiles: string[];
		profile_details: Profile[];
	};
	type Connection = {
		connected: boolean;
		frame_id: string | null;
		frame_name: string | null;
		connected_at: string | null;
		last_sync_at: string | null;
		last_sync_error: string | null;
		credential_storage: string;
		mappings: Mapping[];
		suggestions: Suggestion[];
	};

	export let initialConnection: Connection | null = null;
	export let mode: 'suggestions' | 'settings' = 'suggestions';
	export let profiles: Profile[] = [];

	let connection: Connection = initialConnection || {
		connected: false,
		frame_id: null,
		frame_name: null,
		connected_at: null,
		last_sync_at: null,
		last_sync_error: null,
		credential_storage: 'encrypted database credential',
		mappings: [],
		suggestions: []
	};
	let connecting = false;
	let completing = false;
	let syncing = false;
	let autoSyncStarted = false;
	let showCallback = false;
	let callbackUrl = '';
	let loginUrl = '';
	let skylightEmail = '';
	let skylightPassword = '';

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
		let result: any = null;
		if (response.status !== 204) {
			result = await response.json().catch(() => null);
		}
		if (!response.ok)
			throw new Error(result?.error || result?.detail || 'Skylight request failed.');
		return result;
	}

	async function connect() {
		connecting = true;
		try {
			const result = await api('/api/skylight/connect/', { method: 'POST' });
			loginUrl = result.login_url;
			showCallback = true;
			window.open(result.login_url, 'touchgrass-skylight', 'width=720,height=800');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not start Skylight login.');
		} finally {
			connecting = false;
		}
	}

	async function login() {
		if (!skylightEmail.trim() || !skylightPassword) {
			addToast('error', 'Enter your Skylight email and password.');
			return;
		}
		connecting = true;
		try {
			connection = await api('/api/skylight/login/', {
				method: 'POST',
				body: JSON.stringify({ email: skylightEmail.trim(), password: skylightPassword })
			});
			showCallback = false;
			addToast('success', 'Skylight connected securely');
			await runSync(false);
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not sign in to Skylight.');
		} finally {
			skylightPassword = '';
			connecting = false;
		}
	}

	async function complete() {
		if (!callbackUrl.trim()) {
			addToast('error', 'Paste the final Skylight welcome URL.');
			return;
		}
		completing = true;
		try {
			connection = await api('/api/skylight/complete/', {
				method: 'POST',
				body: JSON.stringify({ callback_url: callbackUrl.trim() })
			});
			callbackUrl = '';
			showCallback = false;
			addToast('success', 'Skylight connected securely');
			await runSync(false);
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not complete Skylight login.'
			);
		} finally {
			completing = false;
		}
	}

	async function runSync(showToast: boolean) {
		syncing = true;
		try {
			const result = await api('/api/skylight/sync/', {
				method: 'POST',
				body: JSON.stringify({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
			});
			connection = result.connection;
			if (showToast) {
				const reviewNotice = result.sync.needs_review
					? `; ${result.sync.needs_review} new event${result.sync.needs_review === 1 ? '' : 's'} sent to calendar review`
					: '';
				addToast(
					'success',
					`Skylight checked ${result.sync.events_seen} events; ${result.sync.created} new suggestion${result.sync.created === 1 ? '' : 's'}${reviewNotice}`
				);
			}
		} catch (error) {
			if (showToast)
				addToast('error', error instanceof Error ? error.message : 'Could not sync Skylight.');
		} finally {
			syncing = false;
		}
	}

	async function sync() {
		await runSync(true);
	}

	async function accept(suggestion: Suggestion) {
		try {
			await api(`/api/skylight/suggestions/${suggestion.id}/accept/`, { method: 'POST' });
			addToast('success', `${suggestion.title} added to Trips`);
			window.location.reload();
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not add this trip.');
		}
	}

	async function dismiss(suggestion: Suggestion) {
		try {
			await api(`/api/skylight/suggestions/${suggestion.id}/dismiss/`, { method: 'POST' });
			connection = {
				...connection,
				suggestions: connection.suggestions.filter((item) => item.id !== suggestion.id)
			};
			addToast('success', 'Suggestion dismissed');
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not dismiss this suggestion.'
			);
		}
	}

	async function disconnect() {
		if (!window.confirm('Disconnect Skylight and remove its encrypted credential and suggestions?'))
			return;
		try {
			await api('/api/skylight/disconnect/', { method: 'DELETE' });
			connection = { ...connection, connected: false, mappings: [], suggestions: [] };
			addToast('success', 'Skylight disconnected');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not disconnect Skylight.');
		}
	}

	function formatDateTime(value: string | null) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
					new Date(value)
				)
			: 'Not synced yet';
	}

	onMount(() => {
		if (mode !== 'suggestions' || !connection.connected || autoSyncStarted) return;
		autoSyncStarted = true;
		const lastSync = connection.last_sync_at ? new Date(connection.last_sync_at).getTime() : 0;
		const fifteenMinutes = 15 * 60 * 1000;
		if (!lastSync || Date.now() - lastSync > fifteenMinutes) void runSync(false);
	});
</script>

{#if mode === 'settings'}
	<IntegrationCard
		id="skylight"
		title="Skylight"
		description="Use your Skylight calendar to identify and organize trips."
		connected={connection.connected}
	>
		<svelte:fragment slot="icon"><CalendarSyncIcon /></svelte:fragment>
		{#if !connection.connected}
			<form class="credential-login" on:submit|preventDefault={login}>
				<label
					>Skylight email<input
						type="email"
						autocomplete="section-skylight username"
						bind:value={skylightEmail}
					/></label
				>
				<label
					>Skylight password<input
						type="password"
						autocomplete="section-skylight current-password"
						bind:value={skylightPassword}
					/></label
				>
				<button class="primary" type="submit" disabled={connecting}
					><LockIcon />{connecting ? 'Connecting…' : 'Connect securely'}</button
				>
				<p>
					Your password is sent directly to Skylight through TouchGrass and discarded immediately.
					Only the encrypted OAuth credential is retained.
				</p>
			</form>
			<div class="browser-fallback">
				<span>Does Skylight require device verification?</span><button
					class="quiet"
					type="button"
					disabled={connecting}
					on:click={connect}><LinkIcon />Use browser login instead</button
				>
			</div>
			{#if showCallback}
				<div class="callback">
					<strong>Finish the secure login</strong>
					<ol>
						<li>Sign in on the Skylight page that opened.</li>
						<li>After it reaches the Skylight welcome page, copy its complete address.</li>
						<li>Paste that address below.</li>
					</ol>
					{#if loginUrl}<a class="login-link" href={loginUrl} target="_blank" rel="noreferrer"
							>Open Skylight login again</a
						>{/if}
					<label
						>Final Skylight welcome URL<input
							bind:value={callbackUrl}
							placeholder="https://ourskylight.com/welcome?code=…&state=…"
						/></label
					>
					<button class="primary" type="button" disabled={completing} on:click={complete}
						>{completing ? 'Connecting…' : 'Complete connection'}</button
					>
				</div>
			{/if}
		{:else}
			<div class="connection-management">
				<span>Connection credentials are stored securely.</span><button
					class="disconnect"
					type="button"
					on:click={disconnect}>Disconnect Skylight</button
				>
			</div>
			<div class="mapping-wrap">
				<SkylightProfileMappings initialMappings={connection.mappings} {profiles} />
			</div>
		{/if}
	</IntegrationCard>
{:else}
	<section class="integration-banner">
		<div class="integration-identity">
			<span class="icon"><CalendarSyncIcon /></span>
			<div>
				<span class="eyebrow">Skylight integration</span>
				<h2>
					{connection.connected ? 'Connected Skylight calendar' : 'Skylight trip suggestions'}
				</h2>
				{#if connection.connected}
					<div class="connection-meta">
						<span><strong>Calendar:</strong> {connection.frame_name || 'Skylight Calendar'}</span
						><span>Last checked {formatDateTime(connection.last_sync_at)}</span>
					</div>
				{:else}
					<p>Connect Skylight in Settings to find likely trips in your calendar.</p>
				{/if}
			</div>
		</div>
		<div class="integration-side">
			{#if connection.connected}<span class="secure"><LockIcon />Encrypted</span>{/if}
			<div class="actions">
				{#if connection.connected}
					<button class="secondary" type="button" disabled={syncing} on:click={sync}
						><span class:spin={syncing}><RefreshIcon /></span>{syncing
							? 'Checking…'
							: 'Check for trips'}</button
					>
					<a class="review-link" href="/trips/skylight-review"
						><CalendarSyncIcon />Review calendar events</a
					>
				{/if}
				<a class="settings-link" href="/settings?tab=integrations#skylight">Integration settings</a>
			</div>
		</div>
	</section>

	{#if connection.last_sync_error}<p class="error standalone-error">
			{connection.last_sync_error}
		</p>{/if}

	{#if connection.connected}
		<section class="trip-suggestions">
			<div class="section-heading">
				<div>
					<span class="eyebrow">From Skylight</span>
					<h2>Trip suggestions</h2>
				</div>
				<strong>{connection.suggestions.length}</strong>
			</div>
			<div class="suggestion-grid">
				{#each connection.suggestions as suggestion (suggestion.id)}
					<TripCard
						title={suggestion.title}
						startDate={suggestion.start_date}
						endDate={suggestion.end_date}
						status="Suggested"
						profiles={suggestion.profile_details}
						locations={suggestion.location ? [suggestion.location] : []}
						notes={suggestion.detection_reasons.slice(0, 2).join(' · ')}
					>
						<svelte:fragment slot="actions">
							<button class="accept" type="button" on:click={() => accept(suggestion)}
								><CheckIcon />Add to trips</button
							>
							<button class="dismiss" type="button" on:click={() => dismiss(suggestion)}
								>Dismiss</button
							>
						</svelte:fragment>
					</TripCard>
				{:else}
					<div class="empty-sync">
						<CalendarSyncIcon /><strong>No suggestions waiting.</strong><span
							>Check Skylight whenever your plans change.</span
						>
					</div>
				{/each}
			</div>
		</section>
	{/if}
{/if}

<style>
	.integration-banner,
	.trip-suggestions,
	.standalone-error {
		max-width: var(--tg-content-width);
		margin-right: auto;
		margin-left: auto;
		color: var(--tg-ink);
	}
	.integration-banner {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 1.25rem;
		margin-bottom: 1.75rem;
		padding: 1rem 1.2rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.integration-identity {
		display: flex;
		align-items: center;
		gap: 0.85rem;
		min-width: 0;
	}
	.icon {
		display: grid;
		width: 48px;
		height: 48px;
		flex: 0 0 48px;
		place-items: center;
		border-radius: 50%;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.icon :global(svg) {
		width: 25px;
		height: 25px;
	}
	h2 {
		margin: 0.1rem 0;
		font-family: var(--tg-font-display);
		font-weight: 400;
		font-size: clamp(1.55rem, 2.5vw, 2.1rem);
	}
	.eyebrow {
		font-size: 0.72rem;
		font-weight: 800;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--tg-ink-muted);
	}
	.integration-identity p {
		margin: 0.25rem 0 0;
		color: var(--tg-ink-muted);
	}
	.connection-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		margin-top: 0.25rem;
		color: var(--tg-ink-muted);
		font-size: 0.84rem;
	}
	.connection-meta strong {
		color: var(--tg-ink);
	}
	.integration-side {
		display: grid;
		justify-items: end;
		gap: 0.55rem;
	}
	.secure {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.3rem 0.55rem;
		border-radius: 999px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
		font-size: 0.74rem;
		font-weight: 750;
	}
	.secure :global(svg) {
		width: 14px;
	}
	button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		min-height: 42px;
		padding: 0.65rem 0.9rem;
		border-radius: 12px;
		font: inherit;
		font-weight: 750;
		cursor: pointer;
	}
	.primary,
	.accept {
		border: 1px solid var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.secondary {
		border: 1px solid var(--tg-border-strong);
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.quiet,
	.dismiss {
		border: 0;
		background: transparent;
		color: var(--tg-ink-muted);
	}
	button:disabled {
		cursor: wait;
		opacity: 0.62;
	}
	.spin {
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		flex-wrap: wrap;
		gap: 0.45rem;
	}
	.review-link,
	.settings-link {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		min-height: 42px;
		padding: 0.65rem 0.9rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 750;
		text-decoration: none;
	}
	.review-link :global(svg) {
		width: 18px;
	}
	.settings-link {
		color: var(--tg-action);
	}
	.error {
		padding: 0.65rem 0.8rem;
		border-radius: 10px;
		background: color-mix(in srgb, var(--tg-danger) 12%, var(--tg-surface));
		color: var(--tg-ink);
	}
	.standalone-error {
		margin-bottom: 1rem;
	}
	.section-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		padding-bottom: 0.65rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.section-heading h2 {
		font-size: clamp(1.8rem, 3vw, 2.4rem);
	}
	.section-heading > strong {
		display: grid;
		min-width: 42px;
		height: 42px;
		place-items: center;
		border: 1px solid var(--tg-border);
		border-radius: 50%;
		background: var(--tg-surface);
		color: var(--tg-ink);
	}
	.suggestion-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	.accept,
	.dismiss {
		min-height: 44px;
		border-radius: 999px;
	}
	.dismiss {
		padding: 0.7rem 1rem;
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	.dismiss:hover {
		color: var(--tg-ink);
	}
	.empty-sync {
		display: grid;
		min-height: 190px;
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
	.empty-sync :global(svg) {
		width: 32px;
		height: 32px;
	}
	.empty-sync strong {
		color: var(--tg-ink);
	}
	.credential-login {
		display: grid;
		grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr) auto;
		align-items: end;
		gap: 0.75rem;
	}
	.credential-login > p {
		grid-column: 1/-1;
		margin: 0;
		color: var(--tg-ink-muted);
		font-size: 0.8rem;
	}
	.browser-fallback {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.25rem;
		margin-top: 0.4rem;
		color: var(--tg-ink-muted);
		font-size: 0.82rem;
	}
	.browser-fallback button {
		min-height: 34px;
		padding: 0.35rem 0.6rem;
		font-size: 0.82rem;
	}
	.callback {
		margin-top: 1rem;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 16px;
		background: var(--tg-overlay-surface);
	}
	.callback ol {
		margin: 0.65rem 0;
		padding-left: 1.25rem;
		color: var(--tg-ink-muted);
	}
	.login-link {
		display: inline-flex;
		margin-bottom: 0.75rem;
		color: var(--tg-action);
		font-weight: 750;
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	label {
		display: grid;
		gap: 0.4rem;
		color: var(--tg-ink);
		font-weight: 700;
	}
	input {
		width: 100%;
		box-sizing: border-box;
		padding: 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		font: inherit;
	}
	.callback .primary {
		margin-top: 0.75rem;
	}
	.connection-management {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		color: var(--tg-ink-muted);
		font-size: 0.85rem;
	}
	.disconnect {
		border: 1px solid color-mix(in srgb, var(--tg-danger) 48%, var(--tg-border));
		background: transparent;
		color: var(--tg-danger);
	}
	.mapping-wrap {
		margin-top: 1rem;
	}
	.mapping-wrap :global(.mappings) {
		max-width: none;
		margin: 0;
		background: var(--tg-canvas-deep);
		box-shadow: none;
	}
	@media (max-width: 1000px) {
		.integration-banner {
			grid-template-columns: 1fr;
		}
		.integration-side {
			justify-items: start;
		}
		.actions {
			justify-content: flex-start;
		}
	}
	@media (max-width: 700px) {
		.integration-identity {
			align-items: flex-start;
		}
		.connection-meta {
			flex-direction: column;
			gap: 0.15rem;
		}
		.integration-side {
			width: 100%;
			justify-items: stretch;
		}
		.actions,
		.actions button,
		.actions a,
		.credential-login button {
			width: 100%;
		}
		.actions {
			display: grid;
			grid-template-columns: 1fr;
		}
		.credential-login {
			grid-template-columns: 1fr;
		}
		.credential-login > p {
			grid-column: 1;
		}
		.browser-fallback,
		.connection-management {
			align-items: flex-start;
			flex-direction: column;
		}
		.suggestion-grid {
			grid-template-columns: 1fr;
		}
		.accept,
		.dismiss {
			width: 100%;
		}
	}
</style>
