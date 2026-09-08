<script lang="ts">
	import { onMount } from 'svelte';
	import QRCode from 'qrcode';
	import IntegrationCard from './IntegrationCard.svelte';
	import MapMarkerPath from '~icons/mdi/map-marker-path';
	import { addToast } from '$lib/toasts';

	export let profiles: Array<{ id: string; name: string; color: string }> = [];
	type Device = {
		id: string;
		name: string;
		profile: string;
		profile_name: string;
		profile_color: string;
		status: string;
		last_report_at: string | null;
		last_processed_at: string | null;
	};
	type Provisioning = { url: string; username: string; token: string; tracker_id: string };
	let devices: Device[] = [];
	let zones: Array<{
		id: string;
		name: string;
		is_home: boolean;
		radius_m: number;
		configured: boolean;
	}> = [];
	let loading = true;
	let busy = false;
	let provisioning: Provisioning | null = null;
	let qrCode = '';
	let deviceName = 'My iPhone';
	let profile = '';
	let latitude = '';
	let longitude = '';
	let radius = 500;
	let trackingPreset: 'battery' | 'balanced' | 'detailed' = 'balanced';
	let zoneName = '';
	let zoneLatitude = '';
	let zoneLongitude = '';
	let zoneRadius = 500;
	let historyDevice = '';
	let historyStart = '';
	let historyEnd = '';

	$: connected = devices.some(
		(device) => device.status === 'connected' || device.status === 'delayed'
	);
	$: if (!profile && profiles.length) profile = profiles[0].id;

	async function api(path: string, options: RequestInit = {}) {
		const response = await fetch(path, {
			...options,
			headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.detail || data.error || 'Request failed');
		return data;
	}

	async function refresh() {
		loading = true;
		try {
			[devices, zones] = await Promise.all([
				api('/api/location-devices/'),
				api('/api/privacy-zones/')
			]);
			devices = Array.isArray(devices) ? devices : (devices as any).results || [];
			zones = Array.isArray(zones) ? zones : (zones as any).results || [];
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not load location tracking'
			);
		} finally {
			loading = false;
		}
	}

	async function createHome() {
		busy = true;
		try {
			await api('/api/privacy-zones/', {
				method: 'POST',
				body: JSON.stringify({
					name: 'Home',
					latitude: Number(latitude),
					longitude: Number(longitude),
					radius_m: radius,
					is_home: true,
					enabled: true
				})
			});
			latitude = '';
			longitude = '';
			await refresh();
			addToast(
				'success',
				'Home privacy zone configured. Exact coordinates will not be shown or stored in trip history.'
			);
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not create Home privacy zone'
			);
		} finally {
			busy = false;
		}
	}

	async function createPrivacyZone() {
		busy = true;
		try {
			await api('/api/privacy-zones/', {
				method: 'POST',
				body: JSON.stringify({
					name: zoneName.trim(),
					latitude: Number(zoneLatitude),
					longitude: Number(zoneLongitude),
					radius_m: zoneRadius,
					is_home: false,
					enabled: true
				})
			});
			zoneName = '';
			zoneLatitude = '';
			zoneLongitude = '';
			await refresh();
			addToast('success', 'Privacy zone added');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not add privacy zone');
		} finally {
			busy = false;
		}
	}

	async function removePrivacyZone(id: string, name: string) {
		if (
			!confirm(`Remove the ${name} privacy zone? New reports there will retain their coordinates.`)
		)
			return;
		try {
			await api(`/api/privacy-zones/${id}/`, { method: 'DELETE' });
			await refresh();
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not remove privacy zone');
		}
	}

	function configFor(item: Provisioning) {
		const tuning =
			trackingPreset === 'battery'
				? { locatorDisplacement: 250, locatorInterval: 900 }
				: trackingPreset === 'detailed'
					? { locatorDisplacement: 50, locatorInterval: 180 }
					: { locatorDisplacement: 100, locatorInterval: 300 };
		return {
			_type: 'configuration',
			mode: 3,
			auth: true,
			url: item.url,
			username: item.username,
			password: item.token,
			deviceId: item.tracker_id,
			monitoring: 1,
			adapt: 10,
			...tuning
		};
	}

	async function pair() {
		busy = true;
		try {
			const data = await api('/api/location-devices/pair/', {
				method: 'POST',
				body: JSON.stringify({
					name: deviceName,
					profile,
					device_identifier:
						deviceName
							.toLowerCase()
							.replace(/[^a-z0-9]+/g, '-')
							.replace(/^-|-$/g, '') || 'iphone'
				})
			});
			provisioning = data.provisioning;
			const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(configFor(provisioning!)))));
			const configUrl = `owntracks:///config?inline=${encoded}`;
			qrCode = await QRCode.toDataURL(configUrl, { width: 260, margin: 1 });
			devices = [data.device, ...devices];
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not pair phone');
		} finally {
			busy = false;
		}
	}

	async function deviceAction(
		device: Device,
		action: 'pause' | 'resume' | 'revoke' | 'process',
		skipConfirm = false
	) {
		if (
			action === 'revoke' &&
			!skipConfirm &&
			!confirm(`Revoke ${device.name}? It will need new credentials to reconnect.`)
		)
			return;
		busy = true;
		try {
			await api(`/api/location-devices/${device.id}/${action}/`, { method: 'POST', body: '{}' });
			await refresh();
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not update device');
		} finally {
			busy = false;
		}
	}

	async function reconfigure(device: Device) {
		if (!confirm(`Reconfigure ${device.name}? Its current token will be revoked first.`)) return;
		await deviceAction(device, 'revoke', true);
		deviceName = device.name;
		profile = device.profile;
		addToast('success', 'Old credentials revoked. Generate a new one-time setup above.');
	}

	async function purge(scope: 'raw' | 'candidates' | 'all') {
		const label =
			scope === 'raw'
				? 'raw samples'
				: scope === 'candidates'
					? 'unaccepted suggestions'
					: 'all location-tracking data and paired devices';
		if (!confirm(`Delete ${label}? Accepted Places, Visits, and Trips will remain.`)) return;
		try {
			await api(`/api/location-devices/purge/?scope=${scope}`, {
				method: 'DELETE',
				body: JSON.stringify({ confirm: 'DELETE' })
			});
			await refresh();
			addToast('success', `Deleted ${label}`);
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not delete tracking data');
		}
	}

	async function purgeRawRange() {
		if (!historyDevice || (!historyStart && !historyEnd)) return;
		if (
			!confirm(
				'Delete raw samples for this device and date range? Accepted Trips, Places, and Visits will remain.'
			)
		)
			return;
		const params = new URLSearchParams();
		if (historyStart) params.set('start', new Date(`${historyStart}T00:00:00`).toISOString());
		if (historyEnd) params.set('end', new Date(`${historyEnd}T23:59:59.999`).toISOString());
		try {
			const result = await api(`/api/location-devices/${historyDevice}/raw-history/?${params}`, {
				method: 'DELETE'
			});
			addToast('success', `Deleted ${result.deleted || 0} raw tracking records`);
		} catch (error) {
			addToast(
				'error',
				error instanceof Error ? error.message : 'Could not delete raw tracking history'
			);
		}
	}

	function relativeDate(value: string | null) {
		if (!value) return 'Waiting for first report';
		return `Last report ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))}`;
	}

	onMount(refresh);
</script>

<IntegrationCard
	title="Automatic location tracking"
	description="OwnTracks privately sends phone coordinates to TouchGrass. It creates review suggestions—not trips or map fills."
	{connected}
	id="owntracks"
>
	<svelte:fragment slot="icon"><MapMarkerPath /></svelte:fragment>
	{#if loading}<p class="muted">Loading tracking status…</p>
	{:else}
		{#if !zones.some((zone) => zone.is_home)}
			<section class="setup-block">
				<div>
					<strong>1. Protect Home</strong>
					<p>
						Required. Coordinates received inside this radius are discarded and replaced with
						enter/leave evidence.
					</p>
				</div>
				<div class="home-grid">
					<label
						>Latitude<input
							type="number"
							step="any"
							bind:value={latitude}
							placeholder="38.8977"
						/></label
					>
					<label
						>Longitude<input
							type="number"
							step="any"
							bind:value={longitude}
							placeholder="-77.0365"
						/></label
					>
					<label
						>Radius<select bind:value={radius}
							><option value={300}>300 m</option><option value={500}>500 m</option><option
								value={750}>750 m</option
							><option value={1000}>1 km</option></select
						></label
					>
					<button class="primary" disabled={busy || !latitude || !longitude} on:click={createHome}
						>Save private Home zone</button
					>
				</div>
			</section>
		{:else}
			<section class="setup-block">
				<div>
					<strong>Pair an iPhone</strong>
					<p>Each phone maps to one individual profile. Never map a phone directly to Joint.</p>
				</div>
				<div class="pair-grid">
					<label>Device name<input bind:value={deviceName} /></label>
					<label
						>Profile<select bind:value={profile}
							>{#each profiles as item}<option value={item.id}>{item.name}</option>{/each}</select
						></label
					>
					<label
						>Tracking detail<select bind:value={trackingPreset}
							><option value="battery">Battery saver</option><option value="balanced"
								>Balanced (recommended)</option
							><option value="detailed">Detailed travel</option></select
						></label
					>
					<button class="primary" disabled={busy || !profile} on:click={pair}
						>Generate one-time setup</button
					>
				</div>
				<p class="notice">
					OwnTracks 26.2.2+ disables external configuration by default. In OwnTracks Settings,
					explicitly allow configuration links before scanning. Keep Always Location enabled and do
					not force-quit OwnTracks. Add a Home region: use Significant mode at Home, switch to Move
					mode after leaving, and return to Significant mode on entering.
				</p>
			</section>
		{/if}

		{#if provisioning}
			<section class="provisioning" aria-live="polite">
				<div>
					<strong>Save this now—credentials are shown once</strong>
					<p>Scan with the iPhone camera, or enter the values manually in OwnTracks HTTP mode.</p>
				</div>
				{#if qrCode}<img src={qrCode} alt="One-time OwnTracks configuration QR code" />{/if}
				<dl>
					<dt>HTTPS URL</dt>
					<dd>{provisioning.url}</dd>
					<dt>Username</dt>
					<dd>{provisioning.username}</dd>
					<dt>Token</dt>
					<dd>{provisioning.token}</dd>
				</dl>
				<button
					class="quiet"
					on:click={() => {
						provisioning = null;
						qrCode = '';
					}}>I saved it</button
				>
			</section>
		{/if}

		{#if devices.length}
			<div class="device-list">
				{#each devices as device}
					<article>
						<span class="profile-dot" style={`--profile:${device.profile_color}`}></span>
						<div>
							<strong>{device.name}</strong>
							<p>{device.profile_name} · {relativeDate(device.last_report_at)}</p>
						</div>
						<span class:good={device.status === 'connected'} class="device-status"
							>{device.status}</span
						>
						<div class="actions">
							{#if device.status === 'paused'}<button
									on:click={() => deviceAction(device, 'resume')}
									disabled={busy}>Resume</button
								>{:else if device.status !== 'revoked'}<button
									on:click={() => deviceAction(device, 'pause')}
									disabled={busy}>Pause</button
								>{/if}
							{#if device.status !== 'revoked'}<button
									on:click={() => deviceAction(device, 'process')}
									disabled={busy}>Process now</button
								><button on:click={() => reconfigure(device)} disabled={busy}>Reconfigure</button
								><button
									class="danger"
									on:click={() => deviceAction(device, 'revoke')}
									disabled={busy}>Revoke</button
								>{/if}
						</div>
					</article>
				{/each}
			</div>
			<p class="notice">
				<strong>Test:</strong> open OwnTracks and tap the upload arrow. A successful report changes the
				device from “waiting” to “connected.” Offline reports are queued by OwnTracks and retain their
				original capture time.
			</p>
		{/if}
		<details class="privacy-tools">
			<summary>Privacy zones and deletion</summary>
			<p>
				Coordinates inside a privacy zone are discarded. Deleting telemetry never removes accepted
				Trips, Places, or Visits.
			</p>
			<div class="zone-list">
				{#each zones as zone}
					<span
						>{zone.name} · {zone.radius_m} m {zone.is_home
							? '(Home)'
							: ''}{#if !zone.is_home}<button
								class="text-action"
								on:click={() => removePrivacyZone(zone.id, zone.name)}>Remove</button
							>{/if}</span
					>
				{/each}
			</div>
			<div class="zone-grid">
				<label>Name<input bind:value={zoneName} placeholder="Work or family" /></label>
				<label>Latitude<input type="number" step="any" bind:value={zoneLatitude} /></label>
				<label>Longitude<input type="number" step="any" bind:value={zoneLongitude} /></label>
				<label
					>Radius<select bind:value={zoneRadius}
						><option value={300}>300 m</option><option value={500}>500 m</option><option value={750}
							>750 m</option
						><option value={1000}>1 km</option></select
					></label
				>
				<button
					disabled={busy || !zoneName.trim() || !zoneLatitude || !zoneLongitude}
					on:click={createPrivacyZone}>Add privacy zone</button
				>
			</div>
			{#if devices.length}
				<div class="history-grid">
					<label
						>Device<select bind:value={historyDevice}
							><option value="">Choose device</option
							>{#each devices.filter((item) => item.status !== 'revoked') as device}<option
									value={device.id}>{device.name}</option
								>{/each}</select
						></label
					>
					<label>From<input type="date" bind:value={historyStart} /></label>
					<label>Through<input type="date" bind:value={historyEnd} /></label>
					<button
						on:click={purgeRawRange}
						disabled={!historyDevice || (!historyStart && !historyEnd)}>Delete date range</button
					>
				</div>
			{/if}
			<div>
				<button on:click={() => purge('raw')}>Delete all raw history</button><button
					on:click={() => purge('candidates')}>Delete unaccepted candidates</button
				><button class="danger" on:click={() => purge('all')}>Delete all tracking data</button>
			</div>
		</details>
	{/if}
</IntegrationCard>

<style>
	.setup-block,
	.provisioning {
		display: grid;
		gap: 1rem;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-overlay-field);
	}
	.setup-block p,
	.provisioning p,
	.muted,
	.device-list p,
	.notice {
		margin: 0.25rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 0.86rem;
		line-height: 1.45;
	}
	.home-grid,
	.pair-grid,
	.zone-grid,
	.history-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 0.75rem;
		align-items: end;
	}
	label {
		display: grid;
		gap: 0.35rem;
		color: var(--tg-ink-muted);
		font-size: 0.76rem;
		font-weight: 800;
	}
	input,
	select {
		width: 100%;
		min-height: 44px;
		padding: 0.65rem 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-input-bg);
		color: var(--tg-input-text);
	}
	button {
		min-height: 40px;
		padding: 0.55rem 0.85rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 12px;
		background: var(--tg-surface);
		color: var(--tg-ink);
		font-weight: 800;
	}
	button.primary {
		min-height: 44px;
		border-color: var(--tg-action);
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	button.quiet {
		width: max-content;
	}
	button.danger {
		color: var(--tg-danger);
	}
	button:disabled {
		opacity: 0.55;
	}
	.notice {
		padding: 0.75rem;
		border-radius: 12px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.provisioning {
		margin-top: 1rem;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: start;
		border-color: var(--tg-action);
	}
	.provisioning img {
		grid-row: 1/4;
		grid-column: 2;
		width: 190px;
		border-radius: 12px;
	}
	.provisioning dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 0.35rem 0.75rem;
		margin: 0;
	}
	.provisioning dt {
		font-weight: 800;
	}
	.provisioning dd {
		margin: 0;
		overflow-wrap: anywhere;
		font-family: monospace;
	}
	.device-list {
		display: grid;
		gap: 0.65rem;
		margin-top: 1rem;
	}
	.device-list article {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto auto;
		gap: 0.75rem;
		align-items: center;
		padding: 0.85rem;
		border: 1px solid var(--tg-border);
		border-radius: 15px;
		background: var(--tg-surface);
	}
	.privacy-tools {
		margin-top: 1rem;
		padding: 0.8rem;
		border-top: 1px solid var(--tg-border);
	}
	.privacy-tools summary {
		cursor: pointer;
		font-weight: 850;
	}
	.privacy-tools > div {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 0.75rem;
	}
	.privacy-tools .zone-grid,
	.privacy-tools .history-grid {
		display: grid;
	}
	.zone-list span {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.35rem 0.55rem;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		font-size: 0.78rem;
	}
	.text-action {
		min-height: unset;
		padding: 0;
		border: 0;
		background: transparent;
		color: var(--tg-action);
		font-size: 0.72rem;
	}
	.profile-dot {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--profile);
	}
	.device-status {
		padding: 0.3rem 0.55rem;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
		font-size: 0.7rem;
		font-weight: 900;
		text-transform: capitalize;
	}
	.device-status.good {
		background: color-mix(in srgb, var(--tg-success) 16%, var(--tg-surface));
		color: var(--tg-success);
	}
	.actions {
		display: flex;
		gap: 0.4rem;
	}
	.actions button {
		min-height: 34px;
		padding: 0.35rem 0.6rem;
		font-size: 0.72rem;
	}
	@media (max-width: 900px) {
		.home-grid,
		.pair-grid,
		.zone-grid,
		.history-grid {
			grid-template-columns: 1fr 1fr;
		}
		.device-list article {
			grid-template-columns: auto 1fr auto;
		}
		.actions {
			grid-column: 2/4;
			flex-wrap: wrap;
		}
	}
	@media (max-width: 600px) {
		.home-grid,
		.pair-grid,
		.zone-grid,
		.history-grid {
			grid-template-columns: 1fr;
		}
		.provisioning {
			grid-template-columns: 1fr;
		}
		.provisioning img {
			grid-row: auto;
			grid-column: auto;
			width: min(100%, 260px);
			justify-self: center;
		}
		.device-list article {
			grid-template-columns: auto 1fr;
		}
		.device-status {
			grid-column: 2;
		}
		.actions {
			grid-column: 1/3;
		}
	}
</style>
