<script lang="ts">
	import { createEventDispatcher, onDestroy, onMount } from 'svelte';
	import { GeoJSON, FillLayer, LineLayer, Marker } from 'svelte-maplibre';
	import FullMap from './FullMap.svelte';
	import type { Country, Region, TravelProfile } from '$lib/types';

	export let countries: Country[] = [];
	export let regions: Region[] = [];
	export let profiles: TravelProfile[] = [];
	export let selectedProfileIds: Set<string> = new Set();

	let map: any;
	let rawCountries: any = null;
	let rawStates: any = null;
	let lakeData: any = null;
	let countryBaseData: any = null;
	let countryData: any = null;
	let stateData: any = null;
	let countryLabelData: any = null;
	let stateLabelData: any = null;
	let styleGeneration = 0;
	let patternsReady = false;
	let viewZoom = 1;
	let observedMap: any = null;
	let removeMapListeners: (() => void) | null = null;
	let lastGesture = { key: '', at: 0 };
	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let longPressTriggered = false;
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

	function polygonArea(rings: number[][][]) {
		const ring = rings[0] || [];
		let area = 0;
		for (let index = 0; index < ring.length; index += 1) {
			const current = ring[index];
			const next = ring[(index + 1) % ring.length];
			area += current[0] * next[1] - next[0] * current[1];
		}
		return Math.abs(area / 2);
	}

	function mainlandGeometry(geometry: any) {
		if (geometry?.type !== 'MultiPolygon' || !geometry.coordinates?.length) return geometry;
		const largest = geometry.coordinates.reduce((best: number[][][], candidate: number[][][]) =>
			polygonArea(candidate) > polygonArea(best) ? candidate : best
		);
		return { type: 'Polygon', coordinates: largest };
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
		for (const region of regions) {
			const visibleIds = region.profile_ids.filter((id) => selectedProfileIds.has(id));
			combinations.set(patternName(visibleIds), visibleIds);
		}
		for (const [name, ids] of combinations) {
			const pattern = makePattern(colorsFor(ids));
			if (map.hasImage(name)) map.updateImage(name, pattern);
			else map.addImage(name, pattern, { pixelRatio: 2 });
		}
		patternsReady = true;
	}

	function watchMapStyle(nextMap: any) {
		if (!nextMap || nextMap === observedMap) return;
		removeMapListeners?.();
		observedMap = nextMap;

		const handleStyleReady = () => {
			patternsReady = false;
			syncPatterns();
			styleGeneration += 1;
		};
		const handleMove = () => { viewZoom = nextMap.getZoom?.() ?? viewZoom; };

		nextMap.on?.('load', handleStyleReady);
		nextMap.on?.('style.load', handleStyleReady);
		nextMap.on?.('moveend', handleMove);
		removeMapListeners = () => {
			nextMap.off?.('load', handleStyleReady);
			nextMap.off?.('style.load', handleStyleReady);
			nextMap.off?.('moveend', handleMove);
		};

		if (nextMap.isStyleLoaded?.()) handleStyleReady();
		nextMap.setRenderWorldCopies?.(false);
	}

	function rebuildGeometry() {
		if (rawCountries) {
			countryBaseData = rawCountries;
			const byCode = new Map(countries.map((country) => [country.country_code, country]));
			const subdivisionCountries = new Set(
				(rawStates?.features || [])
					.map((feature: any) => feature.properties.iso_a2)
					.filter(Boolean)
			);
			const regionProfileIdsByCountry = new Map<string, Set<string>>();
			for (const region of regions) {
				const countryCode = region.id.split('-')[0];
				if (!regionProfileIdsByCountry.has(countryCode)) regionProfileIdsByCountry.set(countryCode, new Set());
				for (const profileId of region.profile_ids) {
					if (selectedProfileIds.has(profileId)) regionProfileIdsByCountry.get(countryCode)?.add(profileId);
				}
			}
			countryData = {
				...rawCountries,
				features: rawCountries.features.map((feature: any) => {
					const code = feature.properties.ISO_A2_EH || feature.properties.ISO_A2;
					const country = byCode.get(code);
					const ids = subdivisionCountries.has(code)
						? [...(regionProfileIdsByCountry.get(code) || [])]
						: country?.profile_ids.filter((id) => selectedProfileIds.has(id)) || [];
					return { ...feature, geometry: mainlandGeometry(feature.geometry), properties: { ...feature.properties, countryCode: code, pattern: patternName(ids), hasSubdivisions: subdivisionCountries.has(code) } };
				})
			};
			countryLabelData = {
				type: 'FeatureCollection',
				features: rawCountries.features
					.filter((feature: any) => Number.isFinite(feature.properties.LABEL_X) && Number.isFinite(feature.properties.LABEL_Y))
					.map((feature: any) => {
						const code = feature.properties.ISO_A2_EH || feature.properties.ISO_A2;
						const ids = subdivisionCountries.has(code)
							? [...(regionProfileIdsByCountry.get(code) || [])]
							: byCode.get(code)?.profile_ids.filter((id) => selectedProfileIds.has(id)) || [];
						return {
							type: 'Feature',
							geometry: { type: 'Point', coordinates: [feature.properties.LABEL_X, feature.properties.LABEL_Y] },
							properties: { code, visited: ids.length > 0, gradient: badgeGradient(ids) }
						};
					})
			};
		}
		if (rawStates) {
			const byId = new Map(regions.map((region) => [region.id, region]));
			stateData = {
				...rawStates,
				features: rawStates.features.filter((feature: any) => Boolean(feature.properties.iso_3166_2)).map((feature: any) => {
					const id = feature.properties.iso_3166_2;
					const region = byId.get(id);
					const ids = region?.profile_ids.filter((profileId) => selectedProfileIds.has(profileId)) || [];
					return { ...feature, properties: { ...feature.properties, regionId: id, pattern: patternName(ids) } };
				})
			};
			stateLabelData = {
				type: 'FeatureCollection',
				features: rawStates.features
					.filter((feature: any) => Number.isFinite(feature.properties.longitude) && Number.isFinite(feature.properties.latitude))
					.map((feature: any) => {
						const ids = byId.get(feature.properties.iso_3166_2)?.profile_ids.filter((id) => selectedProfileIds.has(id)) || [];
						return {
							type: 'Feature',
							geometry: { type: 'Point', coordinates: [feature.properties.longitude, feature.properties.latitude] },
							properties: { code: String(feature.properties.iso_3166_2 || '').split('-').pop(), countryCode: feature.properties.iso_a2, visited: ids.length > 0, gradient: badgeGradient(ids) }
						};
					})
			};
		}
		queueMicrotask(() => {
			syncPatterns();
			map?.getSource?.(`travel-country-polygons-${styleGeneration}`)?.setData?.(countryData);
			map?.getSource?.(`travel-state-polygons-${styleGeneration}`)?.setData?.(stateData);
			map?.getSource?.(`travel-country-labels-${styleGeneration}`)?.setData?.(countryLabelData);
			map?.getSource?.(`travel-state-labels-${styleGeneration}`)?.setData?.(stateLabelData);
		});
	}

	function featureFromEvent(event: CustomEvent<any>) {
		return event.detail?.feature ?? event.detail?.features?.[0] ?? event.detail;
	}

	onMount(async () => {
		const [countryResponse, stateResponse, lakeResponse] = await Promise.all([
			fetch('/geo/countries.geojson'), fetch('/geo/states-provinces.geojson'), fetch('/geo/lakes.geojson')
		]);
		rawCountries = await countryResponse.json();
		rawStates = await stateResponse.json();
		lakeData = await lakeResponse.json();
		rebuildGeometry();
	});

	$: countries, regions, profiles, selectedProfileIds, syncPatterns(), rebuildGeometry();
	$: watchMapStyle(map);
	$: if (map) {
		syncPatterns();
	}
	$: visitedCountryLabels = countryLabelData?.features?.filter((feature: any) => feature.properties.visited && feature.properties.code !== 'US' && /^[A-Z]{2}$/.test(feature.properties.code)) || [];
	$: visitedStateLabels = stateLabelData?.features?.filter((feature: any) => feature.properties.visited && feature.properties.countryCode === 'US' && /^[A-Z]{2}$/.test(feature.properties.code)) || [];

	onDestroy(() => removeMapListeners?.());
</script>

<FullMap bind:map mapStyle={skylightMapStyle} mapClass="h-[66vh] min-h-[560px]" showBasemapSelector={false} mapClickEnabled={false}>
	{#if countryBaseData}
		<GeoJSON id={`travel-country-land-${styleGeneration}`} data={countryBaseData}>
			<FillLayer filter={['!=', ['coalesce', ['get', 'ISO_A2_EH'], ['get', 'ISO_A2']], 'US']} paint={{ 'fill-color': '#d5d0c8', 'fill-opacity': .76, 'fill-antialias': false }} />
			<LineLayer paint={{ 'line-color': '#f8f3eb', 'line-width': .65, 'line-opacity': .75 }} />
		</GeoJSON>
	{/if}
	{#if countryData && patternsReady}
		<GeoJSON id={`travel-country-polygons-${styleGeneration}`} data={countryData}>
			<FillLayer maxzoom={2.3} filter={['!=', ['get', 'countryCode'], 'US']} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.72, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;if(!longPressTriggered) dispatchOnce('countrySelect',`country-${code}`,{countryCode:code});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('countryInspect', { countryCode: featureFromEvent(event)?.properties?.countryCode })} on:touchstart={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;beginLongPress('countryInspect',{countryCode:code}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer maxzoom={2.3} paint={{ 'line-color': '#f8f3eb', 'line-width': 0.8, 'line-opacity': 0.8 }} />
			<FillLayer minzoom={2.3} filter={['==', ['get', 'hasSubdivisions'], false]} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.82, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;if(!longPressTriggered) dispatchOnce('countrySelect',`country-${code}`,{countryCode:code});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('countryInspect', { countryCode: featureFromEvent(event)?.properties?.countryCode })} on:touchstart={(event) => { const code=featureFromEvent(event)?.properties?.countryCode;beginLongPress('countryInspect',{countryCode:code}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer minzoom={2.3} filter={['==', ['get', 'hasSubdivisions'], false]} paint={{ 'line-color': '#ffffff', 'line-width': 1, 'line-opacity': 0.85 }} />
		</GeoJSON>
	{/if}
	{#if stateData && patternsReady}
		<GeoJSON id={`travel-state-polygons-${styleGeneration}`} data={stateData}>
			<FillLayer maxzoom={2.3} filter={['==', ['get', 'iso_a2'], 'US']} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.9, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const id=featureFromEvent(event)?.properties?.regionId;if(!longPressTriggered) dispatchOnce('regionSelect',`region-${id}`,{regionId:id});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('regionInspect', { regionId: featureFromEvent(event)?.properties?.regionId })} on:touchstart={(event) => { const id=featureFromEvent(event)?.properties?.regionId;beginLongPress('regionInspect',{regionId:id}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer maxzoom={2.3} filter={['==', ['get', 'iso_a2'], 'US']} paint={{ 'line-color': '#ffffff', 'line-width': .75, 'line-opacity': .9 }} />
			<FillLayer minzoom={2.3} paint={{ 'fill-pattern': ['get', 'pattern'], 'fill-opacity': 0.88, 'fill-antialias': false }} hoverCursor="pointer" on:click={(event) => { const id=featureFromEvent(event)?.properties?.regionId;if(!longPressTriggered) dispatchOnce('regionSelect',`region-${id}`,{regionId:id});longPressTriggered=false; }} on:contextmenu={(event) => dispatch('regionInspect', { regionId: featureFromEvent(event)?.properties?.regionId })} on:touchstart={(event) => { const id=featureFromEvent(event)?.properties?.regionId;beginLongPress('regionInspect',{regionId:id}); }} on:touchend={endLongPress} on:touchcancel={endLongPress} />
			<LineLayer minzoom={2.3} paint={{ 'line-color': '#ffffff', 'line-width': 1.1, 'line-opacity': 0.9 }} />
		</GeoJSON>
	{/if}
	{#if lakeData}
		<GeoJSON id={`travel-lakes-${styleGeneration}`} data={lakeData}>
			<FillLayer paint={{ 'fill-color': '#dce8e6', 'fill-opacity': 1, 'fill-antialias': true }} />
			<LineLayer paint={{ 'line-color': '#c7d9d7', 'line-width': .7, 'line-opacity': .9 }} />
		</GeoJSON>
	{/if}
	{#if countryLabelData}
		{#each visitedCountryLabels as feature}
			<Marker lngLat={feature.geometry.coordinates} class="travel-name-marker">
				<div class="travel-badge" style={`--badge-fill:${feature.properties.gradient}`}>{feature.properties.code}</div>
			</Marker>
		{/each}
	{/if}
	{#if stateLabelData}
		{#each visitedStateLabels as feature}
			<Marker lngLat={feature.geometry.coordinates} class="travel-name-marker">
				<div class="travel-badge state" style={`--badge-fill:${feature.properties.gradient}`}>{feature.properties.code}</div>
			</Marker>
		{/each}
	{/if}
</FullMap>

<style>
	.travel-badge{pointer-events:none;display:grid;min-width:34px;height:26px;transform:translate(-50%,-50%);place-items:center;padding:0 .42rem;border:2px solid rgba(255,255,255,.96);border-radius:7px;background:var(--badge-fill);color:white;font:800 11px/1 var(--tg-font-body);letter-spacing:.08em;box-shadow:0 3px 10px rgba(25,25,25,.28);text-shadow:0 1px 3px rgba(0,0,0,.72)}
	.travel-badge.state{min-width:30px;height:23px;padding:0 .34rem;font-size:10px;border-radius:6px}
</style>
