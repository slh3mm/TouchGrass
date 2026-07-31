<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import TravelProfileMap from '$lib/components/map/TravelProfileMap.svelte';
	import type { Country, Region, TravelProfile } from '$lib/types';
	import type { PageData } from './$types';
	import { addToast } from '$lib/toasts';
	import MapIcon from '~icons/mdi/map-outline';
	import GridIcon from '~icons/mdi/view-grid-outline';
	import PlusIcon from '~icons/mdi/plus';
	import CloseIcon from '~icons/mdi/close';
	import CheckIcon from '~icons/mdi/check';
	import { ProfileChip } from '$lib/components/touchgrass';

	export let data: PageData;

	let countries: Country[] = data.props?.countries || [];
	let profiles: TravelProfile[] = data.props?.profiles || [];
	let allRegions: Region[] = data.props?.regions || [];
	let editingProfileId = profiles.find((profile) => profile.is_default)?.id || profiles[0]?.id || '';
	let selectedProfileIds = new Set(profiles.map((profile) => profile.id));
	let displayMode: 'atlas' | 'map' = $page.url.searchParams.get('view') === 'map' ? 'map' : 'atlas';
	let showProfiles = false;
	let selectedCountry: Country | null = null;
	let countryRegions: Region[] = [];
	let loadingRegions = false;
	let newProfile = { name: '', color: '#fb8072', avatar: '' };
	let savingProfile = false;
	let savingVisitKey = '';
	let shareUsername = '';
	let sharingCalendar = false;
	let requestedDisplayMode: 'atlas' | 'map' = 'atlas';
	$: requestedDisplayMode = $page.url.searchParams.get('view') === 'map' ? 'map' : 'atlas';
	$: if (displayMode !== requestedDisplayMode) displayMode = requestedDisplayMode;

	$: selectedProfiles = profiles.filter((profile) => selectedProfileIds.has(profile.id));
	$: primaryProfile = profiles.find((profile) => profile.id === editingProfileId) ?? profiles[0] ?? null;
	$: filteredCountries = countries;
	$: visitedCount = countries.filter((country) =>
		country.profile_ids.some((id) => selectedProfileIds.has(id))
	).length;

	function csrfToken() {
		return document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';
	}

	function profileGradient(profileIds: string[], muted = '#d5d0c8') {
		const colors = profiles.filter((profile) => profileIds.includes(profile.id)).map((profile) => profile.color);
		if (!colors.length) return muted;
		if (colors.length === 1) return colors[0];
		const stops = colors.flatMap((color, index) => {
			const start = (index / colors.length) * 100;
			const end = ((index + 1) / colors.length) * 100;
			return [`${color} ${start}%`, `${color} ${end}%`];
		});
		return `linear-gradient(90deg, ${stops.join(', ')})`;
	}

	function visibleProfileIds(country: Country) {
		return country.profile_ids.filter((id) => selectedProfileIds.has(id));
	}

	function editAs(profile: TravelProfile) {
		editingProfileId = profile.id;
	}

	async function shareCalendar() {
		if (!shareUsername.trim()) return;
		sharingCalendar = true;
		try {
			const response = await fetch('/api/travel-profiles/share/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify({ username: shareUsername.trim() })
			});
			const result = await response.json();
			if (!response.ok) return addToast('error', result.error || 'Could not share calendar');
			addToast('success', `Calendar shared with ${result.shared_with}`);
			shareUsername = '';
		} catch {
			addToast('error', 'Could not share calendar');
		} finally {
			sharingCalendar = false;
		}
	}

	async function toggleCountryVisit(country: Country, profile = primaryProfile) {
		if (!profile) return;
		if (savingVisitKey === `country-${country.country_code}-${profile.id}`) return;
		const visited = country.profile_ids.includes(profile.id);
		savingVisitKey = `country-${country.country_code}-${profile.id}`;
		try {
			const response = await fetch(`/api/travel-profiles/${profile.id}/countries/${country.country_code}/`, {
				method: visited ? 'DELETE' : 'PUT',
				headers: { 'X-CSRFToken': csrfToken() }
			});
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${country.name}`);
				return;
			}
			country.profile_ids = visited
				? country.profile_ids.filter((id) => id !== profile.id)
				: [...country.profile_ids, profile.id];
			countries = [...countries];
			if (visited) {
				allRegions = allRegions.map((region) => region.id.startsWith(`${country.country_code}-`)
					? { ...region, profile_ids: region.profile_ids.filter((id) => id !== profile.id) }
					: region);
				countryRegions = countryRegions.map((region) => ({
					...region,
					profile_ids: region.profile_ids.filter((id) => id !== profile.id)
				}));
			}
			addToast('success', `${country.name} ${visited ? 'removed from' : 'added to'} ${profile.name}`, 5000, profile.color);
		} catch {
			addToast('error', `Could not update ${country.name}`);
		} finally {
			savingVisitKey = '';
		}
	}

	async function openCountry(country: Country) {
		selectedCountry = country;
		countryRegions = [];
		loadingRegions = true;
		try {
			const response = await fetch(`/api/${country.country_code}/regions/`);
			if (response.ok) countryRegions = await response.json();
		} finally {
			loadingRegions = false;
		}
	}

	async function toggleRegionVisit(region: Region) {
		if (!primaryProfile) return;
		if (savingVisitKey === `region-${region.id}`) return;
		const visited = region.profile_ids.includes(primaryProfile.id);
		savingVisitKey = `region-${region.id}`;
		try {
			const response = await fetch(`/api/travel-profiles/${primaryProfile.id}/regions/${region.id}/`, {
				method: visited ? 'DELETE' : 'PUT',
				headers: { 'X-CSRFToken': csrfToken() }
			});
			if (!response.ok) {
				addToast('error', (await response.text()) || `Could not update ${region.name}`);
				return;
			}
			region.profile_ids = visited
				? region.profile_ids.filter((id) => id !== primaryProfile.id)
				: [...region.profile_ids, primaryProfile.id];
			countryRegions = [...countryRegions];
			const globalRegion = allRegions.find((item) => item.id === region.id);
			if (globalRegion && globalRegion !== region) globalRegion.profile_ids = [...region.profile_ids];
			allRegions = globalRegion ? [...allRegions] : [...allRegions, region];
			if (selectedCountry && !visited && !selectedCountry.profile_ids.includes(primaryProfile.id)) {
				selectedCountry.profile_ids = [...selectedCountry.profile_ids, primaryProfile.id];
				countries = [...countries];
			}
			addToast('success', `${region.name} updated for ${primaryProfile.name}`, 5000, primaryProfile.color);
		} catch {
			addToast('error', `Could not update ${region.name}`);
		} finally {
			savingVisitKey = '';
		}
	}

	async function createProfile() {
		if (!newProfile.name.trim()) return;
		savingProfile = true;
		try {
			const response = await fetch('/api/travel-profiles/', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
				body: JSON.stringify(newProfile)
			});
			if (!response.ok) return;
			const profile: TravelProfile = await response.json();
			profiles = [...profiles, profile];
			selectedProfileIds = new Set([...selectedProfileIds, profile.id]);
			newProfile = { name: '', color: '#fb8072', avatar: '' };
		} finally {
			savingProfile = false;
		}
	}

	async function updateProfile(profile: TravelProfile) {
		const response = await fetch(`/api/travel-profiles/${profile.id}/`, {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
			body: JSON.stringify({ name: profile.name, color: profile.color, avatar: profile.avatar })
		});
		if (response.ok) profiles = [...profiles];
	}

	async function deleteProfile(profile: TravelProfile) {
		if (profiles.length === 1 || !confirm(`Delete ${profile.name}? Their manual travel history will also be removed.`)) return;
		const response = await fetch(`/api/travel-profiles/${profile.id}/`, {
			method: 'DELETE', headers: { 'X-CSRFToken': csrfToken() }
		});
		if (response.ok) {
			profiles = profiles.filter((item) => item.id !== profile.id);
			selectedProfileIds.delete(profile.id);
			selectedProfileIds = new Set(selectedProfileIds);
		}
	}

	async function handleMapCountry(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) await toggleCountryVisit(country);
	}

	async function handleMapCountryInspect(event: CustomEvent<{ countryCode: string }>) {
		const country = countries.find((item) => item.country_code === event.detail.countryCode);
		if (country) await openCountry(country);
	}

	async function handleMapRegion(event: CustomEvent<{ regionId: string }>) {
		let region = allRegions.find((item) => item.id === event.detail.regionId)
			?? countryRegions.find((item) => item.id === event.detail.regionId);
		if (!region?.name) {
			const response = await fetch(`/api/regions/${event.detail.regionId}/`);
			if (response.ok) {
				const fullRegion: Region = await response.json();
				if (region) fullRegion.profile_ids = [...region.profile_ids];
				region = fullRegion;
			}
		}
		if (region) await toggleRegionVisit(region);
	}

	async function handleMapRegionInspect(event: CustomEvent<{ regionId: string }>) {
		const countryCode = event.detail.regionId?.split('-')[0];
		const country = countries.find((item) => item.country_code === countryCode);
		if (country) await openCountry(country);
	}
</script>

<svelte:head>
	<title>World Travel - TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
</svelte:head>

<main class="travel-shell">
	<div class="travel-backdrop"></div>
	<div class="dashboard">
		<header class="hero">
			<div><h1>Countries</h1></div>
			<div class="journey-stat"><strong>{visitedCount}</strong><span>of {countries.length} countries</span></div>
		</header>

		<section class="profile-bar">
			<div class="profile-list">
				{#each profiles as profile}
					<ProfileChip name={profile.name} color={profile.color} avatar={profile.avatar} active={editingProfileId === profile.id} on:select={() => editAs(profile)} />
				{/each}
				<button class="manage-profile" on:click={() => (showProfiles = true)}><PlusIcon /> Profiles</button>
			</div>
			<p>Editing visits for <strong>{primaryProfile?.name || 'no profile selected'}</strong></p>
		</section>

		{#if displayMode === 'map'}
			<section class="map-panel">
				<TravelProfileMap {countries} regions={allRegions} {profiles} {selectedProfileIds} on:countrySelect={handleMapCountry} on:countryInspect={handleMapCountryInspect} on:regionSelect={handleMapRegion} on:regionInspect={handleMapRegionInspect} />
			</section>
		{:else}
			<section class="atlas-panel">
				<div class="atlas-heading"><div><span class="eyebrow">Flag atlas</span><h2>{filteredCountries.length} destinations</h2></div><span>Click the check to update {primaryProfile?.name}</span></div>
				<div class="flag-grid">
					{#each filteredCountries as country}
						{@const visibleIds = visibleProfileIds(country)}
						<article class:unvisited={!visibleIds.length} class="country-tile">
							<button class="flag-button" on:click={() => openCountry(country)} aria-label={`Open ${country.name}`}>
								<img src={country.flag_url} alt={`${country.name} flag`} loading="lazy" />
								<span class="color-band" style={`background:${profileGradient(visibleIds)}`}></span>
							</button>
							<div class="country-label"><button on:click={() => openCountry(country)}>{country.name}</button><button disabled={savingVisitKey === `country-${country.country_code}-${primaryProfile?.id}`} class:checked={primaryProfile && country.profile_ids.includes(primaryProfile.id)} class="visit-check" on:click={() => toggleCountryVisit(country)} title={`Toggle ${primaryProfile?.name}'s visit`}><CheckIcon /></button></div>
						</article>
					{/each}
				</div>
			</section>
		{/if}
	</div>
</main>

{#if selectedCountry}
	<div class="inspector-backdrop" on:click={() => (selectedCountry = null)} role="presentation"></div>
	<aside class="country-inspector">
		<button class="close" on:click={() => (selectedCountry = null)}><CloseIcon /></button>
		<img src={selectedCountry.flag_url} alt={`${selectedCountry.name} flag`} />
		<span class="eyebrow">{selectedCountry.subregion}</span><h2>{selectedCountry.name}</h2>
		<div class="inspector-band" style={`background:${profileGradient(selectedCountry.profile_ids)}`}></div>
		<div class="country-profile-actions">{#each profiles as profile}<button disabled={savingVisitKey === `country-${selectedCountry.country_code}-${profile.id}`} class:visited={selectedCountry.profile_ids.includes(profile.id)} style={`--profile-color:${profile.color}`} on:click={() => selectedCountry && toggleCountryVisit(selectedCountry, profile)}><span>{profile.avatar || profile.name.slice(0,1).toUpperCase()}</span><strong>{profile.name}</strong><small>{selectedCountry.profile_ids.includes(profile.id) ? 'Remove visit' : 'Mark visited'}</small></button>{/each}</div>
		<div class="region-heading"><h3>{selectedCountry.country_code === 'US' ? 'States visited' : 'Regions visited'}</h3><span>{countryRegions.length}</span></div>
		{#if loadingRegions}<div class="loading-state">Loading regions…</div>{:else}<div class="state-grid">{#each countryRegions as region}<button disabled={savingVisitKey === `region-${region.id}`} class:visited={region.profile_ids.some((id) => selectedProfileIds.has(id))} on:click={() => toggleRegionVisit(region)} style={`--region-fill:${profileGradient(region.profile_ids)}`}><span></span>{region.name}</button>{/each}</div>{/if}
		<button class="details-link" on:click={() => goto(`/worldtravel/${selectedCountry?.country_code}`)}>Open full country details</button>
	</aside>
{/if}

{#if showProfiles}
	<div class="modal-backdrop" role="presentation" on:click={() => (showProfiles = false)}></div>
	<section class="profile-modal">
		<header><div><span class="eyebrow">Household</span><h2>Travel profiles</h2></div><button on:click={() => (showProfiles = false)}><CloseIcon /></button></header>
		<div class="profile-editor-list">{#each profiles as profile}<div class="profile-editor"><input type="color" bind:value={profile.color} aria-label={`${profile.name} color`} /><input bind:value={profile.avatar} maxlength="8" class="avatar-input" aria-label="Avatar" /><input bind:value={profile.name} aria-label="Profile name" /><button on:click={() => updateProfile(profile)}>Save</button><button class="delete" on:click={() => deleteProfile(profile)}>Delete</button></div>{/each}</div>
		<div class="share-calendar"><h3>Share this household calendar</h3><p>Enter another TouchGrass username to share profiles, calendar entries, and travel history.</p><div><input bind:value={shareUsername} placeholder="TouchGrass username" /><button disabled={sharingCalendar || !shareUsername.trim()} on:click={shareCalendar}>Share</button></div></div>
		<div class="new-profile"><h3>Add a profile</h3><div><input type="color" bind:value={newProfile.color} aria-label="New profile color" /><input bind:value={newProfile.avatar} maxlength="8" class="avatar-input" placeholder="🙂" /><input bind:value={newProfile.name} placeholder="Profile name" /><button disabled={savingProfile || !newProfile.name.trim()} on:click={createProfile}><PlusIcon /> Add</button></div></div>
	</section>
{/if}

<style>
	.travel-shell { position:relative;min-height:100vh;color:var(--tg-ink);font-family:var(--tg-font-body); }
	.travel-backdrop { position:fixed;inset:0;background:linear-gradient(120deg,color-mix(in srgb,var(--tg-canvas) 94%,transparent),color-mix(in srgb,var(--tg-canvas-deep) 86%,transparent)),url('/backgrounds/adventurelog_showcase_6.webp') center/cover; }
	.dashboard { position:relative;z-index:1;width:min(1800px,100%);margin:auto;padding:clamp(1rem,2vw,2.25rem); }
	.hero { display:flex;align-items:end;justify-content:space-between;gap:2rem;padding:1.5rem 1.5rem 2rem; }
	h1,h2 { margin:.1rem 0;font-family:'Ovo',Georgia,serif;font-weight:400; } h1 { font-size:clamp(3.2rem,5vw,6rem);line-height:1; } .hero p { margin:.6rem 0 0;color:#68635e; }
	.eyebrow { color:#7a746c;font-size:.7rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase; }
	.journey-stat { display:flex;align-items:baseline;gap:.6rem;white-space:nowrap; }.journey-stat strong { font-family:'Ovo',serif;font-size:4rem;font-weight:400; }
	.profile-bar,.toolbar,.atlas-panel,.map-panel { background:var(--tg-surface-glass);backdrop-filter:blur(var(--tg-blur-panel)); }
	.profile-bar { display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.25rem;border-radius:24px 24px 0 0;border-bottom:1px solid rgba(70,63,55,.1); }
	.profile-list { display:flex;align-items:center;gap:.65rem;flex-wrap:wrap; }.profile-list .manage-profile { min-height:var(--tg-touch-min);display:flex;align-items:center;gap:.5rem;border:0;border-radius:var(--tg-radius-control);padding:.72rem 1rem;background:var(--tg-action);color:var(--tg-action-text);font-weight:600;cursor:pointer; }.manage-profile :global(svg) { width:1rem; }
	.profile-bar p { margin:0;color:#746e68;font-size:.82rem; }
	.toolbar { display:flex;align-items:center;gap:.75rem;padding:1rem 1.25rem; }.search { display:flex;align-items:center;gap:.5rem;flex:1;min-width:220px;padding:.7rem 1rem;background:rgba(255,255,255,.8);border:1px solid #ded8d0;border-radius:999px; }.search input { width:100%;border:0;outline:0;background:none; }.toolbar select { padding:.7rem 1rem;border:1px solid #ded8d0;border-radius:999px;background:white; }.segmented,.view-toggle { display:flex;padding:3px;border-radius:999px;background:#e7e1d9; }.segmented button,.view-toggle button { border:0;border-radius:999px;padding:.55rem .85rem;background:none;cursor:pointer; }.segmented button.active,.view-toggle button.active { background:#393745;color:white; }.view-toggle :global(svg) { width:1.1rem;height:1.1rem; }
	.atlas-panel,.map-panel { border-radius:0 0 24px 24px;padding:1.25rem; }.map-panel { overflow:hidden; }.atlas-heading { display:flex;align-items:end;justify-content:space-between;margin-bottom:1rem; }.atlas-heading h2 { font-size:2.2rem; }.atlas-heading>span { color:#77716b;font-size:.8rem; }
	.flag-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:.85rem; }.country-tile { min-width:0;border:1px solid rgba(75,67,60,.12);border-radius:14px;background:rgba(255,255,255,.72);overflow:hidden;transition:transform .18s,box-shadow .18s; }.country-tile:hover { transform:translateY(-2px);box-shadow:0 10px 28px rgba(62,54,46,.12); }.flag-button { position:relative;display:block;width:100%;height:82px;padding:0;border:0;background:#eee;cursor:pointer;overflow:hidden; }.flag-button img { width:100%;height:100%;object-fit:cover; }.country-tile.unvisited img { filter:grayscale(1);opacity:.3; }.color-band { position:absolute;inset:auto 0 0;height:6px; }.country-label { display:flex;align-items:center;gap:.3rem;padding:.62rem .65rem; }.country-label>button:first-child { min-width:0;flex:1;overflow:hidden;border:0;background:none;text-align:left;text-overflow:ellipsis;white-space:nowrap;font-size:.78rem;font-weight:600;cursor:pointer; }.visit-check { display:grid;width:25px;height:25px;place-items:center;border:1px solid #d7d1ca;border-radius:50%;background:white;color:transparent;cursor:pointer; }.visit-check.checked { border-color:#393745;background:#393745;color:white; }.visit-check :global(svg) { width:.85rem; }
	.inspector-backdrop,.modal-backdrop { position:fixed;inset:0;z-index:70;background:rgba(30,27,25,.26);backdrop-filter:blur(3px); }.country-inspector { position:fixed;z-index:80;top:0;right:0;width:min(520px,100%);height:100vh;padding:2rem;background:#f7f2e9;color:#302f38;box-shadow:-20px 0 60px rgba(36,30,25,.2);overflow:auto;font-family:'DM Sans',sans-serif; }.country-inspector>img { width:110px;height:70px;margin-bottom:1.25rem;border-radius:10px;object-fit:cover;box-shadow:0 8px 24px rgba(0,0,0,.12); }.country-inspector h2,.profile-modal h2 { color:#25232a;font-size:3rem; }.country-inspector .eyebrow { color:#68615b; }.close { position:absolute;top:1.25rem;right:1.25rem;display:grid;width:40px;height:40px;place-items:center;border:0;border-radius:50%;background:white;color:#302f38;cursor:pointer; }.inspector-band { height:10px;margin:1rem 0;border-radius:999px; }.details-link { width:100%;padding:.85rem 1rem;border:0;border-radius:999px;background:#393745;color:white;font-weight:600;cursor:pointer; }.visit-check:disabled,.state-grid button:disabled { opacity:.55;cursor:wait; }.region-heading { display:flex;justify-content:space-between;align-items:center;margin:2rem 0 .75rem;color:#302f38; }.region-heading h3 { color:#25232a;font-weight:700; }.state-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem; }.state-grid button { display:flex;align-items:center;gap:.55rem;padding:.7rem;border:1px solid #cfc6bb;border-radius:10px;background:#fff;color:#2f2b28;font-weight:600;text-align:left;cursor:pointer; }.state-grid button span { width:8px;align-self:stretch;border-radius:99px;background:#aaa39b; }.state-grid button.visited span { background:var(--region-fill); }.loading-state { color:#514b45; }.details-link { margin-top:1.5rem;background:transparent;color:#302f38;border:1px solid #393745; }
	.country-profile-actions { display:grid;gap:.5rem;margin:1rem 0; }.country-profile-actions button { display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:.65rem;padding:.65rem .8rem;border:1px solid #cfc6bb;border-radius:12px;background:white;color:#302f38;text-align:left;cursor:pointer; }.country-profile-actions button>span { display:grid;width:34px;height:34px;place-items:center;border-radius:50%;background:color-mix(in srgb,var(--profile-color) 55%,white); }.country-profile-actions button small { color:#625c56;font-weight:700; }.country-profile-actions button.visited { border-color:var(--profile-color);box-shadow:inset 5px 0 var(--profile-color); }.country-profile-actions button:disabled { opacity:.55;cursor:wait; }
	.profile-modal { position:fixed;z-index:90;top:50%;left:50%;width:min(760px,calc(100% - 2rem));max-height:88vh;padding:1.5rem;transform:translate(-50%,-50%);overflow:auto;border-radius:24px;background:#f7f2e9;box-shadow:0 28px 80px rgba(36,30,25,.3); }.profile-modal header { display:flex;justify-content:space-between;align-items:start; }.profile-modal header button { border:0;background:none;cursor:pointer; }.profile-editor-list { display:grid;gap:.6rem;margin:1.25rem 0; }.profile-editor,.new-profile>div { display:grid;grid-template-columns:44px 60px 1fr auto auto;gap:.5rem; }.profile-editor input,.new-profile input { min-width:0;padding:.65rem;border:1px solid #ddd5cb;border-radius:10px;background:white; }.profile-editor input[type=color],.new-profile input[type=color] { padding:4px; }.profile-editor button,.new-profile button { border:0;border-radius:10px;padding:.6rem .8rem;background:#393745;color:white;cursor:pointer; }.profile-editor .delete { background:#a75548; }.new-profile,.share-calendar { margin-top:1.5rem;padding-top:1rem;border-top:1px solid #ddd5cb; }.new-profile>div { grid-template-columns:44px 60px 1fr auto; }.new-profile button { display:flex;align-items:center;gap:.3rem; }.share-calendar p { color:#68615b;font-size:.85rem; }.share-calendar>div { display:flex;gap:.5rem; }.share-calendar input { flex:1;min-width:0;padding:.7rem;border:1px solid #cfc6bb;border-radius:10px;background:white; }.share-calendar button { padding:.7rem 1rem;border:0;border-radius:10px;background:#393745;color:white;font-weight:700; }
	.profile-modal { color:#302f38; }
	/* Theme-safe semantic overrides for the custom travel UI. */
	.hero p,.eyebrow,.profile-bar p,.atlas-heading>span,.loading-state,.share-calendar p { color:var(--tg-ink-muted); }
	.country-tile,.visit-check,.country-profile-actions button,.state-grid button,
	.profile-editor input,.new-profile input,.share-calendar input { background:var(--tg-surface);color:var(--tg-ink);border-color:var(--tg-border-strong); }
	.country-label>button:first-child,.country-profile-actions button strong,.state-grid button { color:var(--tg-ink); }
	.country-profile-actions button small { color:var(--tg-ink-muted); }
	.country-inspector,.profile-modal { background:var(--tg-surface-soft);color:var(--tg-ink); }
	.country-inspector h2,.profile-modal h2,.region-heading h3,.region-heading { color:var(--tg-ink-strong); }
	.close { background:var(--tg-surface);color:var(--tg-ink); }
	.details-link { color:var(--tg-ink);border-color:var(--tg-ink); }
	.profile-editor button,.new-profile button,.share-calendar button { background:var(--tg-action);color:var(--tg-action-text); }
	.profile-editor .delete { background:var(--tg-danger);color:#fff; }
	.new-profile,.share-calendar { border-color:var(--tg-border); }
	@media(max-width:900px){.hero{align-items:start}.journey-stat{display:none}.profile-bar{align-items:start;flex-direction:column}.toolbar{flex-wrap:wrap}.search{flex-basis:100%}.flag-grid{grid-template-columns:repeat(auto-fill,minmax(115px,1fr))}.profile-editor{grid-template-columns:44px 52px 1fr auto}.profile-editor .delete{grid-column:3/5}}
	@media(max-width:560px){.dashboard{padding:.5rem}.hero{padding:1.25rem .5rem}.hero h1{font-size:3.2rem}.profile-bar p,.atlas-heading>span{display:none}.toolbar select{max-width:145px}.segmented button{padding:.5rem .6rem}.atlas-panel{padding:.65rem}.flag-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem}.flag-button{height:58px}.country-label{padding:.48rem}.country-label>button:first-child{font-size:.68rem}.state-grid{grid-template-columns:1fr}.new-profile>div{grid-template-columns:44px 52px 1fr}.new-profile button{grid-column:3}.profile-editor{grid-template-columns:44px 52px 1fr}.profile-editor button{grid-column:auto}.profile-editor .delete{grid-column:3}}
</style>
