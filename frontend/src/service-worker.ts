/// <reference types="@sveltejs/kit" />

import { build, files, version } from '$service-worker';

const CACHE = `touchgrass-static-${version}`;
const ASSETS = [...build, ...files];

self.addEventListener('install', (event) => {
	event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
			)
	);
});

self.addEventListener('fetch', (event) => {
	if (event.request.method !== 'GET') return;
	const url = new URL(event.request.url);
	// Authentication, telemetry, Places, and other private API responses are
	// deliberately never written to the PWA cache.
	if (
		url.origin !== self.location.origin ||
		url.pathname.startsWith('/api/') ||
		url.pathname.startsWith('/auth/')
	)
		return;
	if (ASSETS.includes(url.pathname)) {
		event.respondWith(
			caches
				.open(CACHE)
				.then((cache) => cache.match(url.pathname))
				.then((hit) => hit || fetch(event.request))
		);
	}
});
