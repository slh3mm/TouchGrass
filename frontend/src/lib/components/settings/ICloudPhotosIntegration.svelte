<script lang="ts">
	import IntegrationCard from './IntegrationCard.svelte';
	import ImageMultiple from '~icons/mdi/image-multiple-outline';
	import { onMount } from 'svelte';
	import { addToast } from '$lib/toasts';

	export let profiles: Array<{ id: string; name: string; color: string }> = [];
	type Source = {
		id: string;
		name: string;
		profile: string;
		profile_name: string;
		profile_color: string;
		status: string;
		last_report_at: string | null;
		last_scan_at: string | null;
		backlog_count: number;
		error_count: number;
		indexed_count: number;
		ready_count: number;
		unavailable_count: number;
		mount_available: boolean;
		newly_discovered_count: number;
		historical_progress: number;
	};
	type Provisioning = {
		url: string;
		reconcile_url: string;
		username: string;
		token: string;
		root_alias: string;
	};
	let sources: Source[] = [];
	let provisioning: Provisioning | null = null;
	let profile = '';
	let loading = true;
	let busy = false;
	$: if (!profile && profiles.length)
		profile = profiles.find((item) => item.name.toLowerCase() === 'spencer')?.id || profiles[0].id;
	$: activeSources = sources.filter((source) => source.status !== 'revoked');
	$: revokedSources = sources.filter((source) => source.status === 'revoked');
	$: connected = activeSources.some(
		(source) => !['waiting', 'authentication failure'].includes(source.status)
	);
	$: provisioningCommand = provisioning ? command(provisioning) : '';

	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || 'Request failed');
		return data;
	}
	async function refresh(silent = false) {
		if (!silent) loading = true;
		try {
			const data = await api('/api/photo-sources/');
			sources = data.results || data;
		} catch (error) {
			if (!silent)
				addToast('error', error instanceof Error ? error.message : 'Could not load iCloud status');
		} finally {
			if (!silent) loading = false;
		}
	}
	async function pair() {
		busy = true;
		try {
			const data = await api('/api/photo-sources/pair/', {
				method: 'POST',
				body: JSON.stringify({ profile, name: 'iCloud Photos', root_alias: 'icloud-photos' })
			});
			provisioning = data.provisioning;
			sources = [data.source, ...sources];
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not pair poller');
		} finally {
			busy = false;
		}
	}
	async function action(
		source: Source,
		name: 'pause' | 'resume' | 'revoke' | 'scan-now' | 'retry-errors'
	) {
		if (
			name === 'revoke' &&
			!confirm('Revoke this poller? It will need new credentials to reconnect.')
		)
			return;
		busy = true;
		try {
			await api(`/api/photo-sources/${source.id}/${name}/`, { method: 'POST', body: '{}' });
			await refresh();
			addToast('success', name === 'scan-now' ? 'Scan requested' : 'Photo source updated');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not update photo source');
		} finally {
			busy = false;
		}
	}
	function date(value: string | null) {
		return value
			? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
					new Date(value)
				)
			: 'Never';
	}
	function command(item: Provisioning) {
		return `py tools\\icloud-poller\\icloud_poller.py setup --root "C:\\Users\\spenc\\iCloudPhotos\\Photos" --url "${item.url}" --reconcile-url "${item.reconcile_url}" --username "${item.username}" --token "${item.token}"`;
	}
	async function copy(value: string) {
		await navigator.clipboard.writeText(value);
		addToast('success', 'Command copied');
	}
	onMount(() => {
		refresh();
		const statusPoll = setInterval(() => refresh(true), 10000);
		return () => clearInterval(statusPoll);
	});
</script>

<IntegrationCard
	title="iCloud Photos"
	description="Indexes photo and video metadata from your Windows iCloud folder without copying originals."
	{connected}
	id="icloud-photos"
>
	<svelte:fragment slot="icon"><ImageMultiple /></svelte:fragment>
	{#if loading}<p class="muted">Loading photo-index status…</p>
	{:else}
		{#if !activeSources.length}
			<div class="pair-row">
				<label
					>Photo owner<select bind:value={profile}
						>{#each profiles as item}<option value={item.id}>{item.name}</option>{/each}</select
					></label
				><button class="primary" disabled={busy || !profile} on:click={pair}
					>Pair Windows poller</button
				>
			</div>
			<p class="notice">
				Generate a new one-time credential for the Windows poller. The historical scan will
				gradually hydrate cloud-only files; originals remain untouched.
			</p>
		{/if}
		{#if activeSources.length}<div class="sources">
				{#each activeSources as source}<article>
						<div class="source-heading">
							<span style={`--profile:${source.profile_color}`}></span>
							<div>
								<strong>{source.name}</strong>
								<p>{source.profile_name} · Last report {date(source.last_report_at)}</p>
							</div>
							<b>{source.status}</b>
						</div>
						<div class="metrics">
							<span><strong>{source.indexed_count}</strong>Indexed</span><span
								><strong>{source.ready_count}</strong>Metadata ready</span
							><span><strong>{source.backlog_count}</strong>Estimated remaining</span><span
								><strong>{source.newly_discovered_count}</strong>New this scan</span
							><span><strong>{source.unavailable_count}</strong>Unavailable</span><span
								><strong>{source.error_count}</strong>Errors</span
							>
						</div>
						<div class="scan-progress">
							<div>
								<span>Historical metadata scan</span><strong>{source.historical_progress}%</strong>
							</div>
							<progress max="100" value={source.historical_progress}
								>{source.historical_progress}%</progress
							>
						</div>
						{#if !source.mount_available}<div class="diagnostic bad">
								Photo access needs attention. TouchGrass will keep the index and resume
								automatically when the photo library is available.
							</div>{/if}
						<div class="actions">
							{#if source.status === 'paused'}<button on:click={() => action(source, 'resume')}
									>Resume</button
								>{:else if source.status !== 'revoked'}<button
									on:click={() => action(source, 'pause')}>Pause</button
								>{/if}{#if source.status !== 'revoked'}<button
									on:click={() => action(source, 'scan-now')}>Scan now</button
								><button on:click={() => action(source, 'retry-errors')}>Retry errors</button
								><button class="danger" on:click={() => action(source, 'revoke')}>Revoke</button
								>{/if}<a href="/photos">Open photo index</a>
						</div>
					</article>{/each}
			</div>{/if}
		{#if revokedSources.length}<details class="revoked">
				<summary>Previously revoked pollers ({revokedSources.length})</summary
				>{#each revokedSources as source}<p>
						{source.name} · {source.profile_name} · revoked
					</p>{/each}
			</details>{/if}
	{/if}
	{#if provisioning}<section class="provisioning" aria-live="polite">
			<strong>Finish connecting this Windows computer</strong>
			<p>
				This is the one-time Windows security handoff. After it runs, scanning, retries, startup,
				and credential rotation happen automatically.
			</p>
			<pre>{provisioningCommand}</pre>
			<button on:click={() => copy(provisioningCommand)}>Copy one-time setup</button><button
				class="quiet"
				on:click={() => (provisioning = null)}>Done</button
			>
		</section>{/if}
</IntegrationCard>

<style>
	.muted,
	.notice,
	.source-heading p,
	.provisioning p {
		color: var(--tg-ink-muted);
		font-size: 0.84rem;
	}
	.pair-row {
		display: grid;
		grid-template-columns: minmax(180px, 1fr) auto;
		gap: 0.7rem;
		align-items: end;
	}
	label {
		display: grid;
		gap: 0.35rem;
		color: var(--tg-ink-muted);
		font-size: 0.75rem;
		font-weight: 850;
	}
	select {
		min-height: 44px;
		padding: 0.6rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-input-bg);
		color: var(--tg-input-text);
	}
	button,
	.actions a {
		display: inline-flex;
		min-height: 40px;
		align-items: center;
		justify-content: center;
		padding: 0.55rem 0.8rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
		text-decoration: none;
	}
	.primary {
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.danger {
		color: var(--tg-danger);
	}
	.quiet {
		border-color: transparent;
		background: transparent;
	}
	.notice,
	.diagnostic {
		margin-top: 0.8rem;
		padding: 0.7rem;
		border-radius: 12px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.sources {
		display: grid;
		gap: 0.8rem;
	}
	.sources article {
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 16px;
		background: var(--tg-overlay-field);
	}
	.source-heading {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: 0.6rem;
		align-items: center;
	}
	.source-heading > span {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--profile);
	}
	.source-heading p {
		margin: 0.2rem 0;
	}
	.source-heading b {
		text-transform: capitalize;
	}
	.metrics {
		display: grid;
		grid-template-columns: repeat(6, 1fr);
		gap: 0.5rem;
		margin: 0.8rem 0;
	}
	.metrics span {
		display: grid;
		padding: 0.55rem;
		border-radius: 10px;
		background: var(--tg-surface);
		color: var(--tg-ink-muted);
		font-size: 0.68rem;
		font-weight: 800;
		text-transform: uppercase;
	}
	.metrics strong {
		color: var(--tg-ink);
		font-size: 1.2rem;
	}
	.scan-progress {
		margin: 0.75rem 0;
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
		font-weight: 800;
	}
	.scan-progress > div {
		display: flex;
		justify-content: space-between;
	}
	.scan-progress progress {
		width: 100%;
		height: 7px;
		margin-top: 0.3rem;
		accent-color: var(--tg-action);
	}
	.diagnostic {
		font-size: 0.76rem;
	}
	.diagnostic.bad {
		background: color-mix(in srgb, var(--tg-danger) 15%, var(--tg-surface));
		color: var(--tg-danger);
	}
	.actions {
		display: flex;
		gap: 0.45rem;
		flex-wrap: wrap;
		margin-top: 0.8rem;
	}
	.revoked {
		margin-top: 0.8rem;
		padding: 0.7rem;
		border-top: 1px solid var(--tg-border);
		color: var(--tg-ink-muted);
		font-size: 0.76rem;
	}
	.revoked summary {
		cursor: pointer;
		font-weight: 800;
	}
	.revoked p {
		margin: 0.35rem 0;
	}
	.provisioning {
		display: grid;
		gap: 0.6rem;
		margin-top: 1rem;
		padding: 1rem;
		border: 1px solid var(--tg-action);
		border-radius: 16px;
		background: var(--tg-overlay-field);
	}
	pre {
		overflow: auto;
		margin: 0;
		padding: 0.7rem;
		border-radius: 10px;
		background: var(--tg-canvas-deep);
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		font-size: 0.72rem;
	}
	@media (max-width: 700px) {
		.pair-row {
			grid-template-columns: 1fr;
		}
		.metrics {
			grid-template-columns: 1fr 1fr;
		}
		.source-heading {
			grid-template-columns: auto 1fr;
		}
		.source-heading b {
			grid-column: 2;
		}
		.actions > * {
			flex: 1;
		}
	}
</style>
