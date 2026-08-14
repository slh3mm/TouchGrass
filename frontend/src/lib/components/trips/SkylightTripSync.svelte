<script lang="ts">
	import { onMount } from 'svelte';
	import CalendarSyncIcon from '~icons/mdi/calendar-sync';
	import CheckIcon from '~icons/mdi/check';
	import CloseIcon from '~icons/mdi/close';
	import LinkIcon from '~icons/mdi/link-variant';
	import LockIcon from '~icons/mdi/lock';
	import RefreshIcon from '~icons/mdi/refresh';
	import { addToast } from '$lib/toasts';

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
		return document.cookie
			.split('; ')
			.find((row) => row.startsWith('csrftoken='))
			?.split('=')[1] || '';
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
		if (!response.ok) throw new Error(result?.error || result?.detail || 'Skylight request failed.');
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
			await sync();
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
			await sync();
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not complete Skylight login.');
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
				addToast(
					'success',
					`Skylight checked ${result.sync.events_seen} events; ${result.sync.created} new suggestion${result.sync.created === 1 ? '' : 's'}`
				);
			}
		} catch (error) {
			if (showToast) addToast('error', error instanceof Error ? error.message : 'Could not sync Skylight.');
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
			addToast('error', error instanceof Error ? error.message : 'Could not dismiss this suggestion.');
		}
	}

	async function disconnect() {
		if (!window.confirm('Disconnect Skylight and remove its encrypted credential and suggestions?')) return;
		try {
			await api('/api/skylight/disconnect/', { method: 'DELETE' });
			connection = { ...connection, connected: false, mappings: [], suggestions: [] };
			addToast('success', 'Skylight disconnected');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not disconnect Skylight.');
		}
	}

	function formatDate(value: string) {
		return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(
			new Date(`${value}T12:00:00`)
		);
	}

	function formatDateTime(value: string | null) {
		return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not synced yet';
	}

	onMount(() => {
		if (!connection.connected || autoSyncStarted) return;
		autoSyncStarted = true;
		const lastSync = connection.last_sync_at ? new Date(connection.last_sync_at).getTime() : 0;
		const fifteenMinutes = 15 * 60 * 1000;
		if (!lastSync || Date.now() - lastSync > fifteenMinutes) void runSync(false);
	});

</script>

<section class="skylight-panel">
	<div class="panel-heading">
		<div class="identity"><span class="icon"><CalendarSyncIcon /></span><div><span class="eyebrow">Calendar source</span><h2>Skylight trip suggestions</h2></div></div>
		{#if connection.connected}
			<span class="secure"><LockIcon />Encrypted</span>
		{/if}
	</div>

	{#if !connection.connected}
		<div class="connect-copy">
			<p>TouchGrass scores calendar events using destinations, trip wording, dates, recurrence, and local-event exclusions. Nothing becomes a trip until you approve it.</p>
		</div>
		<form class="credential-login" on:submit|preventDefault={login}>
			<label>Skylight email<input type="email" autocomplete="username" bind:value={skylightEmail} /></label>
			<label>Skylight password<input type="password" autocomplete="current-password" bind:value={skylightPassword} /></label>
			<button class="primary" type="submit" disabled={connecting}><LockIcon />{connecting ? 'Connecting…' : 'Connect securely'}</button>
			<p>Your password is sent directly through your TouchGrass backend to Skylight and discarded immediately. Only the encrypted, refreshable OAuth credential is retained.</p>
		</form>
		<div class="browser-fallback">
			<span>Does Skylight require device verification?</span>
			<button class="quiet" type="button" disabled={connecting} on:click={connect}><LinkIcon />Use browser login instead</button>
		</div>
		{#if showCallback}
			<div class="callback">
				<strong>Finish the secure login</strong>
				<ol><li>Sign in on the Skylight page that opened.</li><li>After it reaches the Skylight welcome page, copy its complete address.</li><li>Paste that address below.</li></ol>
				{#if loginUrl}<a class="login-link" href={loginUrl} target="_blank" rel="noreferrer">Open Skylight login again</a>{/if}
				<label>Final Skylight welcome URL<input bind:value={callbackUrl} placeholder="https://ourskylight.com/welcome?code=…&state=…" /></label>
				<button class="primary" type="button" disabled={completing} on:click={complete}>{completing ? 'Connecting…' : 'Complete connection'}</button>
			</div>
		{/if}
	{:else}
		<div class="connection-row">
			<div><strong>{connection.frame_name || 'Skylight Calendar'}</strong><span>Last checked {formatDateTime(connection.last_sync_at)}</span></div>
			<div class="actions"><a class="review-link" href="/trips/skylight-review"><CalendarSyncIcon />Review every event</a><button class="secondary" type="button" disabled={syncing} on:click={sync}><span class:spin={syncing}><RefreshIcon /></span>{syncing ? 'Checking…' : 'Check for trips'}</button><button class="quiet" type="button" on:click={disconnect}>Disconnect</button></div>
		</div>

		{#if connection.last_sync_error}<p class="error">{connection.last_sync_error}</p>{/if}

		<div class="suggestion-heading"><div><strong>Needs your review</strong><span>Only likely trips appear here.</span></div><b>{connection.suggestions.length}</b></div>
		<div class="suggestions">
			{#each connection.suggestions as suggestion (suggestion.id)}
				<article>
					<div class="suggestion-profiles">{#each suggestion.profile_details as profile}<i style={`--profile:${profile.color}`} title={profile.name}>{profile.avatar || profile.name[0]}</i>{/each}</div>
					<h3>{suggestion.title}</h3>
					<p class="dates">{formatDate(suggestion.start_date)} – {formatDate(suggestion.end_date)}</p>
					{#if suggestion.location}<p>{suggestion.location}</p>{/if}
					{#if suggestion.detection_reasons.length}<p class="reasons">{suggestion.detection_reasons.slice(0, 2).join(' · ')}</p>{/if}
					<div class="suggestion-actions"><button class="accept" type="button" on:click={() => accept(suggestion)}><CheckIcon />Add trip</button><button class="dismiss" type="button" on:click={() => dismiss(suggestion)}><CloseIcon />Not a trip</button></div>
				</article>
			{:else}
				<div class="empty-sync"><CalendarSyncIcon /><strong>No suggestions waiting.</strong><span>Check Skylight whenever your plans change.</span></div>
			{/each}
		</div>

	{/if}
</section>

<style>
	.skylight-panel{max-width:1500px;margin:0 auto 1.75rem;padding:1.2rem;border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass);box-shadow:var(--tg-shadow-card);color:var(--tg-ink)}
	.panel-heading,.connection-row,.suggestion-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.identity{display:flex;align-items:center;gap:.85rem}.icon{display:grid;width:48px;height:48px;place-items:center;border-radius:50%;background:var(--tg-canvas-deep);color:var(--tg-action)}.icon :global(svg){width:25px;height:25px}h2,h3{margin:.1rem 0;font-family:var(--tg-font-display);font-weight:400}h2{font-size:clamp(1.6rem,3vw,2.2rem)}h3{font-size:1.5rem}.eyebrow{font-size:.7rem;font-weight:800;letter-spacing:.15em;text-transform:uppercase;color:var(--tg-ink-muted)}.secure{display:inline-flex;align-items:center;gap:.3rem;padding:.35rem .6rem;border-radius:999px;background:var(--tg-canvas-deep);color:var(--tg-ink-muted);font-size:.76rem;font-weight:750}.secure :global(svg){width:15px}
	.connect-copy{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-top:1rem;padding-top:1rem;border-top:1px solid var(--tg-border)}.connect-copy p{max-width:780px;margin:0;color:var(--tg-ink-muted)}button{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;min-height:42px;padding:.65rem .9rem;border-radius:999px;font:inherit;font-weight:750;cursor:pointer}.primary,.accept{border:0;background:var(--tg-action);color:var(--tg-action-text)}.secondary{border:1px solid var(--tg-border-strong);background:var(--tg-surface);color:var(--tg-ink)}.quiet,.dismiss{border:0;background:transparent;color:var(--tg-ink-muted)}button:disabled{cursor:wait;opacity:.62}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
	.credential-login{display:grid;grid-template-columns:minmax(180px,1fr) minmax(180px,1fr) auto;align-items:end;gap:.75rem;margin-top:1rem;padding:1rem;border:1px solid var(--tg-border);border-radius:16px;background:var(--tg-overlay-surface)}.credential-login>p{grid-column:1/-1;margin:0;color:var(--tg-ink-muted);font-size:.8rem}.browser-fallback{display:flex;align-items:center;justify-content:flex-end;gap:.25rem;margin-top:.4rem;color:var(--tg-ink-muted);font-size:.82rem}.browser-fallback button{min-height:34px;padding:.35rem .6rem;font-size:.82rem}
	.callback{margin-top:1rem;padding:1rem;border:1px solid var(--tg-border);border-radius:16px;background:var(--tg-overlay-surface)}.callback ol{margin:.65rem 0;padding-left:1.25rem;color:var(--tg-ink-muted)}.login-link{display:inline-flex;margin-bottom:.75rem;color:var(--tg-action);font-weight:750;text-decoration:underline;text-underline-offset:3px}label{display:grid;gap:.4rem;color:var(--tg-ink);font-weight:700}input{width:100%;box-sizing:border-box;padding:.75rem;border:1px solid var(--tg-border-strong);border-radius:10px;background:var(--tg-overlay-field);color:var(--tg-ink);font:inherit}.callback .primary{margin-top:.75rem}
		.connection-row{margin-top:1rem;padding-top:1rem;border-top:1px solid var(--tg-border)}.connection-row>div:first-child{display:grid;gap:.15rem}.connection-row span,.suggestion-heading span{color:var(--tg-ink-muted);font-size:.88rem}.actions{display:flex;align-items:center;gap:.4rem}.review-link{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;min-height:42px;padding:.65rem .9rem;border:1px solid var(--tg-border-strong);border-radius:999px;background:var(--tg-surface);color:var(--tg-ink);font-weight:750;text-decoration:none}.review-link :global(svg){width:18px}.error{padding:.65rem .8rem;border-radius:10px;background:color-mix(in srgb,#c43c3c 12%,var(--tg-surface));color:var(--tg-ink)}.suggestion-heading{margin-top:1.2rem;padding-bottom:.65rem;border-bottom:1px solid var(--tg-border)}.suggestion-heading>div{display:grid}.suggestion-heading b{display:grid;min-width:38px;height:38px;place-items:center;border:1px solid var(--tg-border);border-radius:50%;background:var(--tg-surface)}
	.suggestions{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.75rem;margin-top:.8rem}.suggestions article,.empty-sync{min-height:170px;padding:1rem;border:1px solid var(--tg-border);border-radius:16px;background:var(--tg-surface)}.suggestions article>p{margin:.3rem 0;color:var(--tg-ink-muted)}.dates{font-weight:700}.reasons{font-size:.78rem}.suggestion-profiles{display:flex}.suggestion-profiles i{display:grid;width:30px;height:30px;margin-right:-5px;place-items:center;border:2px solid var(--tg-surface);border-radius:50%;background:var(--profile);color:#17151a;font-style:normal;font-weight:850}.suggestion-actions{display:flex;gap:.4rem;margin-top:1rem}.accept,.dismiss{min-height:38px;padding:.5rem .75rem}.dismiss{border:1px solid var(--tg-border)}.empty-sync{display:grid;place-items:center;align-content:center;gap:.25rem;color:var(--tg-ink-muted);text-align:center}.empty-sync :global(svg){width:30px;height:30px}.empty-sync strong{color:var(--tg-ink)}
		@media(max-width:700px){.panel-heading,.connection-row,.connect-copy{align-items:flex-start;flex-direction:column}.credential-login{grid-template-columns:1fr}.credential-login>p{grid-column:1}.browser-fallback{align-items:flex-start;flex-direction:column}.actions,.actions button,.actions .review-link,.credential-login button{width:100%}.actions{flex-wrap:wrap}.suggestions{grid-template-columns:1fr}}
</style>
