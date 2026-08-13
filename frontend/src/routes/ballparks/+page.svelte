<script lang="ts">
	import { onMount } from 'svelte';
	import { addToast } from '$lib/toasts';
	import { mlbLogoUrl, mlbTeamMeta, type MlbTeamMeta } from '$lib/data/mlbTeams';
	import { ManageProfilesButton, ProfileChip } from '$lib/components/touchgrass';
	import CloseIcon from '~icons/mdi/close';
	import BaseballIcon from '~icons/mdi/baseball';
	import PlusIcon from '~icons/mdi/plus';
	import type { PageData } from './$types';

	export let data: PageData;

	type Profile = { id: string; name: string; color: string; avatar?: string; is_default?: boolean };
	type Visit = {
		id: string;
		profile: string;
		ballpark_id: string;
		first_visit_date: string | null;
		last_visit_date: string | null;
		visit_count: number;
		notes: string;
	};
	type BallparkFeature = {
		type: 'Feature';
		properties: { Team: string; Stadium: string; League: string; Division: string; Class: string };
		geometry: { type: 'Point'; coordinates: [number, number] };
	};
	type Ballpark = BallparkFeature & { meta: MlbTeamMeta };
	type AtlasRegion = { d: string; country: string; name: string };

	let profiles: Profile[] = data.profiles || [];
	let visits: Visit[] = data.visits || [];
	let visitLookup = new Map<string, Visit>();
	let selectedVisitedIds = new Set<string>();
	let ballparks: Ballpark[] = [];
	let selectedProfileId = profiles.find((profile) => profile.is_default)?.id || profiles[0]?.id || '';
	let loading = true;
	let savingVisitKeys = new Set<string>();
	let logoFailures = new Set<string>();
	let atlasRegions: AtlasRegion[] = [];
	let showProfiles = false;
	let savingProfile = false;
	let newProfile = { name: '', color: '#fb8072', avatar: '' };

	$: selectedProfile = (profiles || []).find((profile) => profile.id === selectedProfileId) || (profiles || [])[0];
	$: selectedProfileVisits = (visits || []).filter((visit) => visit.profile === selectedProfileId);
	$: selectedVisitedIds = new Set(selectedProfileVisits.map((visit) => visit.ballpark_id.toUpperCase()));
	$: visitedCount = selectedVisitedIds.size;
	$: visitLookup = new Map<string, Visit>(
		(visits || []).map((visit) => [
			`${visit.profile}:${visit.ballpark_id.toUpperCase()}`,
			visit
		] as [string, Visit])
	);

	onMount(() => {
		let mounted = true;

		async function loadBallparks() {
			try {
				const response = await fetch('/geo/mlb-ballparks.json');
				if (!response.ok) throw new Error('Ballpark locations could not be loaded.');
				const collection = await response.json();
				if (!mounted) return;
				ballparks = collection.features
					.map((feature: BallparkFeature) => {
						const meta = mlbTeamMeta[feature.properties.Team];
						return meta ? { ...feature, meta } : null;
					})
					.filter(Boolean) as Ballpark[];
			} catch (error) {
				addToast('error', error instanceof Error ? error.message : 'Ballpark locations could not be loaded.');
			} finally {
				if (mounted) loading = false;
			}
		}

		async function loadAtlas() {
			try {
				const response = await fetch('/geo/us-ca-admin1.compact.geojson');
				if (!response.ok) throw new Error('The ballpark map background could not be loaded.');
				const regions = await response.json();
				if (!mounted) return;
				atlasRegions = regions.features
					.map((feature: any) => ({
						d: geometryPath(feature.geometry),
						country: feature.properties.countryCode,
						name: feature.properties.name
					}))
					.filter((region: AtlasRegion) => region.d);
			} catch (error) {
				addToast('error', error instanceof Error ? error.message : 'The ballpark map background could not be loaded.');
			}
		}

		void loadBallparks();
		void loadAtlas();

		return () => {
			mounted = false;
		};
	});

	async function syncVisitsFromServer() {
		try {
			const response = await fetch(`/api/ballpark-visits/?refresh=${Date.now()}`, {
				cache: 'no-store'
			});
			if (!response.ok) return;
			const serverVisits: Visit[] = await response.json();
			// Never overwrite an optimistic click that is still being saved. The last
			// completed mutation will run another sync after all pending clicks settle.
			if (savingVisitKeys.size === 0) visits = serverVisits;
		} catch {
			// The mutation response already updated the local state. A later page load
			// will still read the persisted visit if this verification request fails.
		}
	}

	function csrf() {
		return document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';
	}

	async function createProfile() {
		if (!newProfile.name.trim() || savingProfile) return;
		savingProfile = true;
		try {
			const response = await fetch('/api/travel-profiles/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: JSON.stringify(newProfile)
			});
			if (!response.ok) throw new Error('The profile could not be created.');
			const profile: Profile = await response.json();
			profiles = [...profiles, profile];
			selectedProfileId = profile.id;
			newProfile = { name: '', color: '#fb8072', avatar: '' };
			showProfiles = false;
			addToast('success', `${profile.name} is ready for ballpark visits`, 5000, profile.color);
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'The profile could not be created.');
		} finally {
			savingProfile = false;
		}
	}

	async function toggleVisit(profile: Profile, ballpark: Ballpark) {
		const key = `${profile.id}:${ballpark.meta.id}`;
		if (savingVisitKeys.has(key)) return;
		const existing = visitLookup.get(key);
		const optimisticId = `pending:${key}`;
		savingVisitKeys = new Set([...savingVisitKeys, key]);

		if (existing) {
			visits = visits.filter((visit) => visit.id !== existing.id);
		} else {
			visits = [
				...visits,
				{
					id: optimisticId,
					profile: profile.id,
					ballpark_id: ballpark.meta.id,
					first_visit_date: null,
					last_visit_date: null,
					visit_count: 1,
					notes: ''
				}
			];
		}

		try {
			const response = await fetch(existing ? `/api/ballpark-visits/${existing.id}/` : '/api/ballpark-visits/', {
				method: existing ? 'DELETE' : 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: existing ? undefined : JSON.stringify({ profile: profile.id, ballpark_id: ballpark.meta.id, visit_count: 1 })
			});
			if (!response.ok) throw new Error('The ballpark passport could not be updated.');
			if (existing) {
				addToast('success', `${ballpark.properties.Stadium} removed for ${profile.name}`, 5000, profile.color);
			} else {
				const created: Visit = await response.json();
				visits = visits.map((visit) => visit.id === optimisticId ? created : visit);
				addToast('success', `${ballpark.properties.Stadium} added for ${profile.name}`, 5000, profile.color);
			}
		} catch (error) {
			if (existing) {
				if (!visits.some((visit) => visit.id === existing.id)) visits = [...visits, existing];
			} else {
				visits = visits.filter((visit) => visit.id !== optimisticId);
			}
			addToast('error', error instanceof Error ? error.message : 'The ballpark passport could not be updated.');
		} finally {
			savingVisitKeys = new Set([...savingVisitKeys].filter((savingKey) => savingKey !== key));
			if (savingVisitKeys.size === 0) void syncVisitsFromServer();
		}
	}

	function logoFailed(id: string) {
		logoFailures = new Set([...logoFailures, id]);
	}

	function project(coordinates: [number, number]) {
		const [longitude, latitude] = coordinates;
		return {
			x: ((longitude + 128) / 63) * 1000,
			y: ((50 - latitude) / 28) * 600
		};
	}

	function ringPath(ring: number[][]) {
		return ring
			.map((coordinate, index) => {
				const point = project([coordinate[0], coordinate[1]]);
				return `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`;
			})
			.join(' ') + ' Z';
	}

	function geometryPath(geometry: any) {
		if (!geometry?.coordinates) return '';
		if (geometry.type === 'Polygon') return geometry.coordinates.map(ringPath).join(' ');
		if (geometry.type === 'MultiPolygon') {
			return geometry.coordinates.flatMap((polygon: number[][][]) => polygon.map(ringPath)).join(' ');
		}
		return '';
	}
</script>

<svelte:head>
	<title>MLB Ballparks - TouchGrass</title>
</svelte:head>

<main class="ballpark-page">
	<header class="passport-header">
		<div>
			<span class="eyebrow">Ballpark passport</span>
			<h1>Major League ballparks</h1>
		</div>
		<div class="score-card">
			<strong>{visitedCount}<small>/30</small></strong>
			<span>parks visited</span>
		</div>
	</header>

	<section class="profile-row" aria-label="Choose the profile to edit">
		{#each profiles as profile}
			<ProfileChip
				name={profile.name}
				color={profile.color}
				avatar={profile.avatar}
				active={profile.id === selectedProfileId}
				on:select={() => (selectedProfileId = profile.id)}
			/>
		{/each}
		<ManageProfilesButton on:click={() => (showProfiles = true)} />
	</section>

	<section class="map-card">
		<div class="map-heading">
			<div>
				<h2>{selectedProfile?.name || 'Your household'}’s ballpark map</h2>
			</div>
		</div>

		<div class="map-frame" class:loading>
			<svg class="atlas" viewBox="0 0 1000 600" role="img" aria-label="Map of MLB ballparks in the United States and Toronto">
				<rect width="1000" height="600" class="sea" />
				{#each atlasRegions as region}
					<path d={region.d} class:canada={region.country === 'CA'}><title>{region.name}</title></path>
				{/each}
			</svg>
			<div class="callout-layer">
				{#each ballparks as ballpark}
					{@const point = project(ballpark.geometry.coordinates)}
					{@const savingKey = `${selectedProfileId}:${ballpark.meta.id}`}
					<div
						class="stadium-marker"
						style={`--dx:${ballpark.meta.offset[0]}px;--dy:${ballpark.meta.offset[1]}px;--team:${ballpark.meta.primary};--team-2:${ballpark.meta.secondary}`}
						style:left={`${point.x / 10}%`}
						style:top={`${point.y / 6}%`}
					>
						<svg class="leader" viewBox="-80 -80 160 160" aria-hidden="true">
							<line class="leader-halo" x1="0" y1="0" x2={ballpark.meta.offset[0]} y2={ballpark.meta.offset[1]} />
							<line class="leader-stroke" x1="0" y1="0" x2={ballpark.meta.offset[0]} y2={ballpark.meta.offset[1]} />
							<circle class="stadium-dot-halo" cx="0" cy="0" r="5" />
							<circle class="stadium-dot" cx="0" cy="0" r="3" />
						</svg>
						<button
							class="stadium-callout"
							class:visited={selectedVisitedIds.has(ballpark.meta.id)}
							class:saving={savingVisitKeys.has(savingKey)}
							disabled={!selectedProfile || savingVisitKeys.has(savingKey)}
							title={`${ballpark.properties.Team} — ${ballpark.properties.Stadium}`}
							aria-label={`${selectedVisitedIds.has(ballpark.meta.id) ? 'Remove' : 'Add'} ${ballpark.properties.Team}, ${ballpark.properties.Stadium}, for ${selectedProfile?.name || 'the selected profile'}`}
							on:click={() => selectedProfile && toggleVisit(selectedProfile, ballpark)}
						>
							<span
								class="logo-ring"
								style:background={selectedVisitedIds.has(ballpark.meta.id) ? selectedProfile?.color || '#b6b2ab' : '#b6b2ab'}
							>
								<span class="logo-disc">
									{#if logoFailures.has(ballpark.meta.id)}
										<b>{ballpark.meta.abbr}</b>
									{:else}
										<img src={mlbLogoUrl(ballpark.meta)} alt="" on:error={() => logoFailed(ballpark.meta.id)} />
									{/if}
								</span>
							</span>
						</button>
					</div>
				{/each}
			</div>
			{#if loading}
				<div class="loading-state"><BaseballIcon /><span>Setting the lineup…</span></div>
			{/if}
		</div>
	</section>

</main>

{#if showProfiles}
	<button class="profile-dismiss" aria-label="Close profile creator" on:click={() => (showProfiles = false)}></button>
	<aside class="profile-creator">
		<button class="close" aria-label="Close" on:click={() => (showProfiles = false)}><CloseIcon /></button>
		<span class="eyebrow">Household</span>
		<h2>Add a profile</h2>
		<p>Create another color-coded passport for your household.</p>
		<label>
			Profile name
			<input bind:value={newProfile.name} placeholder="Name" />
		</label>
		<div class="creator-options">
			<label>
				Color
				<input type="color" bind:value={newProfile.color} aria-label="New profile color" />
			</label>
			<label>
				Avatar
				<input bind:value={newProfile.avatar} maxlength="8" placeholder="🙂" aria-label="New profile avatar" />
			</label>
		</div>
		<button class="create-profile" disabled={savingProfile || !newProfile.name.trim()} on:click={createProfile}>
			<PlusIcon /> {savingProfile ? 'Adding…' : 'Add profile'}
		</button>
	</aside>
{/if}

<style>
	.ballpark-page{min-height:100vh;padding:clamp(1rem,3vw,3rem);background:linear-gradient(145deg,var(--tg-canvas),var(--tg-canvas-deep));color:var(--tg-ink)}
	.passport-header,.map-card,.profile-row{width:min(1500px,100%);margin-inline:auto}
	.passport-header{display:flex;align-items:end;justify-content:space-between;gap:2rem;margin-bottom:1rem}
	.eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:var(--tg-ink-muted)}
	h1,h2{margin:.15rem 0;font-family:var(--tg-font-display);font-weight:400}h1{font-size:clamp(2.7rem,5vw,5rem)}h2{font-size:clamp(1.7rem,3vw,2.6rem)}
	p{color:var(--tg-ink-muted)}.score-card{min-width:130px;padding:1rem 1.25rem;border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass);text-align:center;box-shadow:var(--tg-shadow-card)}
	.score-card strong{display:block;font:400 2.4rem/1 var(--tg-font-display)}.score-card small{font-size:1rem;color:var(--tg-ink-muted)}.score-card span{font-size:.76rem;color:var(--tg-ink-muted)}
	.profile-row{display:flex;align-items:center;gap:.65rem;padding:.55rem .4rem 1rem;overflow-x:auto;scroll-padding-inline:.4rem}
	.map-card{padding:clamp(.8rem,2vw,1.4rem);border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass);box-shadow:var(--tg-shadow-card)}
	.map-heading{display:flex;align-items:end;justify-content:space-between;gap:1rem;padding:.2rem .5rem 1rem}
	.map-frame{position:relative;aspect-ratio:5/3;overflow:hidden;border:1px solid var(--tg-border);border-radius:calc(var(--tg-radius-panel) - 8px);background:var(--tg-sea)}
	.atlas,.callout-layer{position:absolute;inset:0;width:100%;height:100%}.atlas .sea{fill:var(--tg-sea)}.atlas path{fill:oklch(var(--b1));stroke:oklch(var(--bc)/.28);stroke-width:1.05;vector-effect:non-scaling-stroke}.atlas path.canada{fill:oklch(var(--b3))}
	.callout-layer{pointer-events:none}.stadium-marker{position:absolute;width:1px;height:1px;overflow:visible;pointer-events:none}.stadium-callout{position:absolute;inset:0;width:1px;height:1px;padding:0;border:0;background:transparent;overflow:visible;cursor:pointer;pointer-events:auto}
	.leader{position:absolute;z-index:1;left:-80px;top:-80px;width:160px;height:160px;overflow:visible;pointer-events:none}.leader line{fill:none;stroke-linecap:round;opacity:.96}.leader-halo{stroke:#fff;stroke-width:6}.leader-stroke{stroke:#242321;stroke-width:2.6}.stadium-dot-halo{fill:#fff}.stadium-dot{fill:#242321}
	.logo-ring{position:absolute;z-index:2;left:calc(var(--dx) - 25px);top:calc(var(--dy) - 25px);display:grid;width:50px;height:50px;padding:3px;place-items:center;border-radius:50%;filter:grayscale(1);opacity:.86;box-shadow:0 5px 14px rgba(20,20,20,.25);transition:transform var(--tg-motion-fast),filter var(--tg-motion-fast),opacity var(--tg-motion-fast)}
	.logo-disc{display:grid;width:44px;height:44px;place-items:center;overflow:hidden;border:3px solid var(--tg-surface);border-radius:50%;background:white}.logo-disc img{width:38px;height:38px;object-fit:contain}.logo-disc b{font-size:.65rem;color:#222}
	.stadium-callout.visited .logo-ring,.stadium-callout:hover .logo-ring,.stadium-callout:focus-visible .logo-ring{filter:none;opacity:1;transform:scale(1.1)}
	.stadium-callout.saving .logo-ring{cursor:wait;animation:save-pulse .8s ease-in-out infinite alternate}.stadium-callout:disabled{cursor:wait}
	.loading-state{position:absolute;inset:0;display:grid;place-content:center;gap:.6rem;background:var(--tg-surface-soft);color:var(--tg-ink);text-align:center}.loading-state :global(svg){width:42px;height:42px;margin:auto;animation:spin 1.4s linear infinite}
	.profile-dismiss{position:fixed;inset:0;z-index:1090;border:0;background:transparent}.profile-creator{position:fixed;z-index:1100;top:0;right:0;width:min(480px,100%);height:100vh;padding:clamp(1.3rem,4vw,2.5rem);overflow:auto;border-left:1px solid oklch(var(--bc)/.2);background:oklch(var(--b1)) !important;color:oklch(var(--bc)) !important;opacity:1;isolation:isolate;box-shadow:-24px 0 64px rgba(20,20,20,.28)}
	.close{position:absolute;top:1rem;right:1rem;display:grid;width:44px;height:44px;place-items:center;border:0;border-radius:50%;background:oklch(var(--b2));color:oklch(var(--bc))}.profile-creator h2{font-size:3rem;line-height:1.05}
	.profile-creator>p{margin-bottom:1.5rem}.profile-creator label{display:grid;gap:.45rem;margin:1rem 0;color:oklch(var(--bc));font-weight:700}.profile-creator input{width:100%;min-height:48px;padding:.75rem;border:1px solid oklch(var(--bc)/.25);border-radius:12px;background:oklch(var(--b2));color:oklch(var(--bc))}.profile-creator input[type=color]{padding:.25rem}.creator-options{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.create-profile{display:flex;align-items:center;justify-content:center;gap:.5rem;width:100%;min-height:52px;margin-top:1.5rem;border:0;border-radius:999px;background:oklch(var(--p));color:oklch(var(--pc));font-weight:800}.create-profile:disabled{opacity:.55}
	@keyframes spin{to{transform:rotate(360deg)}}
	@keyframes save-pulse{to{transform:scale(.98);opacity:.72}}
	@media(max-width:750px){.passport-header{align-items:start}.score-card{min-width:104px}.map-heading{align-items:start;flex-direction:column}.map-frame{min-height:390px;aspect-ratio:auto}.logo-ring{transform:scale(.72)}.stadium-callout.visited .logo-ring,.stadium-callout:hover .logo-ring,.stadium-callout:focus-visible .logo-ring{transform:scale(.84)}.leader{transform:scale(.8)}}
</style>
