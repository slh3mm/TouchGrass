// vite.config.js
import { defineConfig } from 'vite';
import { sveltekit } from '@sveltejs/kit/vite';
import Icons from 'unplugin-icons/vite';

const usePolling = process.env.VITE_USE_POLLING === 'true';
const pollingInterval = Number(process.env.VITE_POLLING_INTERVAL || 1200);

export default defineConfig({
	plugins: [
		sveltekit(),
		Icons({
			compiler: 'svelte'
		})
	],
	server: {
		watch: {
			// Native events are substantially cheaper and work once the checkout is no
			// longer synchronized by OneDrive. Polling remains an opt-in fallback for
			// Docker Desktop installations that do not forward filesystem events.
			usePolling,
			interval: usePolling ? pollingInterval : undefined,
			ignored: [
				'**/.git/**',
				'**/.svelte-kit/**',
				'**/build/**',
				'**/node_modules/**',
				'**/static/geo/**'
			]
		}
	}
});
