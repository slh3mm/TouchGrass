<script lang="ts">
	import { createEventDispatcher, onDestroy, onMount, tick } from 'svelte';
	import { GeoJSON, FillLayer, LineLayer, Marker } from 'svelte-maplibre';
	import FullMap from './FullMap.svelte';
	import type { Country, Region, TravelProfile } from '$lib/types';
	import type { TravelSearchItem } from '$lib/components/travel/travelSearch';

	export let countries: Country[] = [];
	export let regions: Region[] = [];
	export let profiles: TravelProfile[] = [];
	export let selectedProfileIds: Set<string> = new Set();
	export let focusTarget: TravelSearchItem | null = null;

	let map: any;
	let lakeData: any = null;
	let countryBaseData: any = null;
	let countryData: any = null;
	let stateData: any = null;
	let countryLabelSeeds: any[] = [];
	let stateLabelSeeds: any[] = [];
	let visitedCountryLabels: any[] = [];
	let visitedStateLabels: any[] = [];
	const patternSignatures = new Map<string, string>();
	let styleGeneration = 0;
	let patternsReady = false;
	let observedMap: any = null;
	let removeMapListeners: (() => void) | null = null;
	let styleReadyQueued = false;
	let lastGesture = { key: '', at: 0 };
	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let longPressTriggered = false;
	let lastFocusedTarget = '';
	const subdivisionCountryCodes = new Set(['US', 'CA']);
	const dispatch = createEventDispatcher<{
		countrySelect: { countryCode: string };
		countryInspect: { countryCode: string };
		regionSelect: { regionId: string };
		regionInspect: { regionId: string };
	}>();
	const skylightMapStyle = {
		version: 8 as const,
		name: 'Skylight Travel',
		glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
		sources: {},
		layers: [
			{ id: 'background', type: 'background' as const, paint: { 'background-color': '#dce8e6' } }
		]
	};

	function patternName(ids: string[]) {
		return ids.length ? `travel-${[...ids].sort().join('-')}` : 'travel-unvisited';
	}

	function hexRgb(hex: string) {
		return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
	}

	function makePattern(colors: string[]) {
		const palette = colors.length ? colors : ['#d5d0c8'];
		const width = 48;
		const height = 48;
		const data = new Uint8Array(width * height * 4);
		for (let y = 0; y < height; y += 1) {
			for (let x = 0; x < width; x += 1) {
				const stripe = Math.min(palette.length - 1, Math.floor((x / width) * palette.length));
				const [r, g, b] = hexRgb(palette[stripe]);
				const offset = (y * width + x) * 4;
				data[offset] = r; data[offset + 1] = g; data[offset + 2] = b; data[offset + 3] = 255;
			}
		}
		return { width, height, data };
	}

	function colorsFor(ids: string[]) {
		return profiles.filter((profile) => ids.includes(profile.id)).map((profile) => profile.color);
	}

	function badgeGradient(ids: string[]) {
		const colors = colorsFor(ids);
		if (!colors.length) return '#706a64';
		if (colors.length === 1) return colors[0];
		const stops = colors.flatMap((color, index) => {
			const start = (index / colors.length) * 100;
			const end = ((index + 1) / colors.length) * 100;
			return [`${color} ${start}%`, `${color} ${end}%`];
		});
		return `linear-gradient(90deg, ${stops.join(', ')})`;
	}

	function compactMainlandGeometry(feature: any) {
		const part = Number(feature.properties?.mainlandPart);
		if (feature.geometry?.type !== 'MultiPolygon' || part < 0) return feature.geometry;
		return { type: 'Polygon', coordinates: feature.geometry.coordinates[part] };
	}

	function geometryBounds(geometry: any) {
		const bounds: [[number, number], [number, number]] = [[Infinity, Infinity], [-Infinity, -Infinity]];
		const visit = (coordinates: any) => {
			if (typeof coordinates?.[0] === 'number' && typeof coordinates?.[1] === 'number') {
				bounds[0][0] = Math.min(bounds[0][0], coordinates[0]);
				bounds[0][1] = Math.min(bounds[0][1], coordinates[1]);
				bounds[1][0] = Math.max(bounds[1][0], coordinates[0]);
				bounds[1][1] = Math.max(bounds[1][1], coordinates[1]);
				return;
			}
			if (Array.isArray(coordinates)) coordinates.forEach(visit);
		};
		visit(geometry?.coordinates);
		return Number.isFinite(bounds[0][0]) ? bounds : null;
	}

	function focusMapTarget(target: TravelSearchItem | null) {
		if (!target) {
			lastFocusedTarget = '';
			return;
		}
		if (!map || !countryData || !stateData || target.id === lastFocusedTarget) return;
		const feature = target.kind === 'country'
			? countryData.features.find((item: any) => item.properties.countryCode === target.targetId)
			: stateData.features.find((item: any) => item.properties.regionId === target.targetId);
		const bounds = geometryBounds(feature?.geometry);
		if (!bounds) return;
		lastFocusedTarget = target.id;
		map.fitBounds?.(bounds, {
			padding: target.kind === 'country' ? 90 : 120,
			maxZoom: target.kind === 'country' ? 5.2 : 6.5,
			duration: 850
		});
	}

	function dispatchOnce(name: 'countrySelect' | 'regionSelect', key: string, detail: any) {
		const now = Date.now();
		if (lastGesture.key === key && now - lastGesture.at < 450) return;
		lastGesture = { key, at: now };
		dispatch(name, detail);
	}

	function beginLongPress(name: 'countryInspect' | 'regionInspect', detail: any) {
		if (longPressTimer) clearTimeout(longPressTimer);
		longPressTriggered = false;
		longPressTimer = setTimeout(() => {
			longPressTriggered = true;
			dispatch(name, detail);
		}, 650);
	}

	function endLongPress() {
		if (longPressTimer) clearTimeout(longPressTimer);
		longPressTimer = null;
	}

	function syncPatterns() {
		if (!map || !map.isStyleLoaded?.()) return;
		const combinations = new Map<string, string[]>();
		combinations.set('travel-unvisited', []);
		for (const country of countries) {
			const visibleIds = country.profile_ids.filter((id) => selectedProfileIds.has(id));
			combinations.set(patternName(visibleIds), visibleIds);
		}
		for (const region of regions.filter((item) => subdivisionCountryCodes.has(item.id.split('-')[0]))) {
			const visibleIds = region.profile_ids.filter((id) => selectedProfileIds.has(id));
			combinations.set(patternName(visibleIds), visibleIds);
		}
		for (const [name, ids] of combinations) {
			const colors = colorsFor(ids);
			const signature = colors.length ? colors.join('|') : '#d5d0c8';
			if (map.hasImage(name) && patternSignatures.get(name) === signature) continue;
			const pattern = makePattern(colors);
			if (map.hasImage(name)) map.updateImage(name, pattern);
			else map.addImage(name, pattern, { pixelRatio: 2 });
			patternSignatures.set(name, signature);
		}
		patternsReady = true;
	}

	function countrySourceId() {
		return `travel-country-polygons-${styleGeneration}`;
	}

	function stateSourceId() {
		return `travel-state-polygons-${styleGeneration}`;
	}

	function updateTravelState() {
		if (!countryData || !stateData) return;

		const countryIds = new Map(
			countries.map((country) => [
				country.country_code,
				country.profile_ids.filter((id) => selectedProfileIds.has(id))
			])
		);
		const regionIds = new Map<string, string[]>();
		const regionIdsByCountry = new Map<string, Set<string>>();
		for (const region of regions) {
			const countryCode = region.id.split('-')[0];
			if (!subdivisionCountryCodes.has(countryCode)) continue;
			const ids = region.profile_ids.filter((id) => selectedProfileIds.has(id));
			regionIds.set(region.id, ids);
			if (!regionIdsByCountry.has(countryCode)) regionIdsByCountry.set(countryCode, new Set());
			for (const id of ids) regionIdsByCountry.get(countryCode)?.add(id);
		}
		for (const code of subdivisionCountryCodes) {
			countryIds.set(code, [...(regionIdsByCountry.get(code) || [])]);
		}

		// Store the current pattern on each feature instead of racing feature-state
		// updates against asynchronously mounted MapLibre sources.
		countryData = {
			...countryData,
			features: countryData.features.map((feature: any) => {
				const code = feature.properties.countryCode;
				return {
					...feature,
					properties: {
						...feature.properties,
						pattern: patternName(countryIds.get(code) || [])
					}
				};
			})
		};
		stateData = {
			...stateData,
			features: stateData.features.map((feature: any) => {
				const id = feature.properties.regionId;
				return {
					...feature,
					properties: {
						...feature.properties,
						pattern: patternName(regionIds.get(id) || [])
					}
				};
			})
		};

		visitedCountryLabels = countryLabelSeeds
			.filter((feature) => {
				const code = feature.properties.code;
				return !subdivisionCountryCodes.has(code) && (countryIds.get(code)?.length || 0) > 0;
			})
			.map((feature) => ({
				...feature,
				properties: {
					...feature.properties,
					gradient: badgeGradient(countryIds.get(feature.properties.code) || [])
				}
			}));
		visitedStateLabels = stateLabelSeeds
			.filter((feature) => (regionIds.get(feature.properties.id)?.length || 0) > 0)
			.map((feature) => ({
				...feature,
				properties: {
					...feature.properties,
					gradient: badgeGradient(regionIds.get(feature.properties.id) || [])
				}
			}));

		syncPatterns();
	}

	function initializeGeometry(countryCollection: any, stateCollection: any) {
		countryBaseData = countryCollection;
		countryData = {
			type: 'FeatureCollection',
			features: countryCollection.features
				.filter((feature: any) => feature.properties?.canonical && feature.properties?.code)
				.map((feature: any) => ({
					type: 'Feature',
					id: feature.properties.code,
					geometry: compactMainlandGeometry(feature),
					properties: {
						countryCode: feature.properties.code,
						hasSubdivisions: subdivisionCountryCodes.has(feature.properties.code),
						pattern: 'travel-unvisited'
					}
				}))
		};
		stateData = {
			type: 'FeatureCollection',
			features: stateCollection.features.map((feature: any) => ({
				type: 'Feature',
				id: feature.properties.id,
				geometry: feature.geometry,
				properties: {
					regionId: feature.properties.id,
					countryCode: feature.properties.countryCode,
					pattern: 'travel-unvisited'
				}
			}))
		};

		countryLabelSeeds = countryCollection.features
			.filter((feature: any) =>
				feature.properties?.canonical &&
				feature.properties?.code &&
				Number.isFinite(feature.properties?.labelX) &&
				Number.isFinite(feature.properties?.labelY)
			)
			.map((feature: any) => ({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [feature.properties.labelX, feature.properties.labelY] },
				properties: { code: feature.properties.code }
			}));
		stateLabelSeeds = stateCollection.features
			.filter((feature: any) =>
				Number.isFinite(feature.properties?.labelX) && Number.isFinite(feature.properties?.labelY)
			)
			.map((feature: any) => ({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [feature.properties.labelX, feature.properties.labelY] },
				properties: {
					id: feature.properties.id,
					code: feature.properties.code,
					countryCode: feature.properties.countryCode
				}
			}));
	}

	function watchMapStyle(nextMap: any) {
		if (!nextMap || nextMap === observedMap) return;
		removeMapListeners?.();
		observedMap = nextMap;

		const handleStyleReady = () => {
			if (styleReadyQueued) return;
			styleReadyQueued = true;
			queueMicrotask(async () => {
				styleReadyQueued = false;
				patternsReady = false;
				patternSignatures.clear();
				styleGeneration += 1;
				syncPatterns();
				await tick();
			});
		};

		nextMap.on?.('style.load', handleStyleReady);
		removeMapListeners = () => {
			nextMap.off?.('style.load', handleStyleReady);
		};

		if (nextMap.isStyleLoaded?.()) handleStyleReady();
		nextMap.setRenderWorldCopies?.(false);
	}

	function featureFromEvent(event: CustomEvent<any>) {
		return event.detail?.feature ?? event.detail?.features?.[0] ?? event.detail;
	}

	function supportedRegionIdFromEvent(event: CustomEvent<any>) {
		const id = String(featureFromEvent(event)?.properties?.regionId || '');
		return subdivisionCountryCodes.has(id.split('-')[0]) ? id : '';
	}

	function selectRegionFromEvent(event: CustomEvent<any>) {
		const id = supportedRegionIdFromEvent(event);
		if (id && !longPressTriggered) dispatchOnce('regionSelect', `region-${id}`, { regionId: id });
		longPressTriggered = false;
	}

	function inspectRegionFromEvent(event: CustomEvent<any>) {
		const id = supportedRegionIdFromEvent(event);
		if (id) dispatch('regionInspect', { regionId: id });
	}

	function beginRegionLongPress(event: CustomEvent<any>) {
		const id = supportedRegionIdFromEvent(event);
		if (id) beginLongPress('regionInspect', { regionId: id });
	}

	onMount(async () => {
		const [countryResponse, stateResponse] = await Promise.all([
			fetch('/geo/countries.compact.geojson'), fetch('/geo/us-ca-admin1.compact.geojson')
		]);
		if (!countryResponse.ok || !stateResponse.ok) return;
		const [countryCollection, stateCollection] = await Promise.all([
			countryResponse.json(),
			stateResponse.json()
		]);
		initializeGeometry(countryCollection, stateCollection);
		updateTravelState();
		const loadLakes = async () => {
			const lakeResponse = await fetch('/geo/lakes.compact.geojson');
			if (lakeResponse.ok) lakeData = await lakeResponse.json();
		};
		if ('requestIdleCallback' in window) {
			(window as any).requestIdleCallback(loadLakes, { timeout: 2500 });
		} else {
			setTimeout(loadLakes, 0);
		}
	});

	$: countries, regions, profiles, selectedProfileIds, updateTravelState();
	$: watchMapStyle(map);
	$: focusMapTarget(focusTarget);

	onDestroy(() => removeMapListeners?.());
</script>

<FullMap bind:map mapStyle={skylightMapStyle} mapClass="h-[66vh] min-h-[560px]" showBasemapSelector={false} mapClickEnabled={false}>
	{#if countryBaseData}
		<GeoJSON id={`travel-country-land-${styleGeneration}`} data={countryBaseData}>
			<FillLayer filter={['all', ['!=', ['get', 'code'], 'US'], ['!=', ['get', 'code'], 'CA']]} paint={{ 'fill-color': '#d5d0c8', 'fill-opacity': .76, 'fill-antialias': false }} />
			<LineLayer paint={{ 'line-color': '#f8f3eb', 'line-width': .65, 'line-opacity': .75 }} />
		</GeoJSON>
	{/if}
	{#if countryData && patternsReady}
		<GeoJSON id={countrySourceId()} data={countryData} promoteId="countryCode">
			<FillLayer maxzoom={2.3} filter={['all', ['!=', ['get', 'countryCode'], 'US'], ['!=', ['get', 'countryCode'], 'CA']]} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.72, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;if(!longPressTriggered) dispatchOnce('countrySelect',`country-${code}`,{countryCode:code});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('countryInspect', { countryCode: featureFromEvent(event)?.properties?.countryCode })} on:touchstart={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;beginLongPress('countryInspect',{countryCode:code}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer maxzoom={2.3} paint={{ 'line-color': '#f8f3eb', 'line-width': 0.8, 'line-opacity': 0.8 }} />
			<FillLayer minzoom={2.3} filter={['==', ['get', 'hasSubdivisions'], false]} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.82, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;if(!longPressTriggered) dispatchOnce('countrySelect',`country-${code}`,{countryCode:code});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('countryInspect', { countryCode: featureFromEvent(event)?.properties?.countryCode })} on:touchstart={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;beginLongPress('countryInspect',{countryCode:code}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer minzoom={2.3} filter={['==', ['get', 'hasSubdivisions'], false]} paint={{ 'line-color': '#ffffff', 'line-width': 1, 'line-opacity': 0.85 }} />
			{#if focusTarget?.kind === 'country'}
				<LineLayer filter={['==', ['get', 'countryCode'], focusTarget.targetId]} paint={{ 'line-color': '#245c49', 'line-width': 4, 'line-opacity': 1, 'line-blur': .35 }} />
			{/if}
		</GeoJSON>
	{/if}
	{#if stateData && patternsReady}
		<GeoJSON id={stateSourceId()} data={stateData} promoteId="regionId">
			<FillLayer maxzoom={2.3} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.9, 'fill-antialias': false }} hoverCursor="pointer" on:click={selectRegionFromEvent} on:contextmenu={inspectRegionFromEvent} on:touchstart={beginRegionLongPress} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer maxzoom={2.3} paint={{ 'line-color': '#ffffff', 'line-width': .75, 'line-opacity': .9 }} />
			<FillLayer minzoom={2.3} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.88, 'fill-antialias': false }} hoverCursor="pointer" on:click={selectRegionFromEvent} on:contextmenu={inspectRegionFromEvent} on:touchstart={beginRegionLongPress} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer minzoom={2.3} paint={{ 'line-color': '#ffffff', 'line-width': 1.1, 'line-opacity': 0.9 }} />
			{#if focusTarget && focusTarget.kind !== 'country'}
				<LineLayer filter={['==', ['get', 'regionId'], focusTarget.targetId]} paint={{ 'line-color': '#245c49', 'line-width': 4, 'line-opacity': 1, 'line-blur': .35 }} />
			{/if}
		</GeoJSON>
	{/if}
	{#if lakeData}
		<GeoJSON id={`travel-lakes-${styleGeneration}`} data={lakeData}>
			<FillLayer paint={{ 'fill-color': '#dce8e6', 'fill-opacity': 1, 'fill-antialias': true }} />
			<LineLayer paint={{ 'line-color': '#c7d9d7', 'line-width': .7, 'line-opacity': .9 }} />
		</GeoJSON>
	{/if}
	{#each visitedCountryLabels as feature}
		<Marker lngLat={feature.geometry.coordinates} class="travel-name-marker">
			<div class="travel-badge" style={`--badge-fill:${feature.properties.gradient}`}>{feature.properties.code}</div>
		</Marker>
	{/each}
	{#each visitedStateLabels as feature}
		<Marker lngLat={feature.geometry.coordinates} class="travel-name-marker">
			<div class="travel-badge state" style={`--badge-fill:${feature.properties.gradient}`}>{feature.properties.code}</div>
		</Marker>
	{/each}
</FullMap>

<style>
	.travel-badge{pointer-events:none;display:grid;min-width:34px;height:26px;transform:translate(-50%,-50%);place-items:center;padding:0 .42rem;border:2px solid rgba(255,255,255,.96);border-radius:7px;background:var(--badge-fill);color:white;font:800 11px/1 var(--tg-font-body);letter-spacing:.08em;box-shadow:0 3px 10px rgba(25,25,25,.28);text-shadow:0 1px 3px rgba(0,0,0,.72)}
	.travel-badge.state{min-width:30px;height:23px;padding:0 .34rem;font-size:10px;border-radius:6px}
</style>
