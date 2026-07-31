<script lang="ts">
	import { browser } from '$app/environment';
	import { register, init, locale, waitLocale } from 'svelte-i18n';
	export let data;

	// Register your translations for each locale
	register('en', () => import('../locales/en.json'));
	register('es', () => import('../locales/es.json'));
	register('fr', () => import('../locales/fr.json'));
	register('de', () => import('../locales/de.json'));
	register('it', () => import('../locales/it.json'));
	register('zh', () => import('../locales/zh.json'));
	register('nl', () => import('../locales/nl.json'));
	register('sv', () => import('../locales/sv.json'));
	register('pl', () => import('../locales/pl.json'));
	register('ko', () => import('../locales/ko.json'));
	register('no', () => import('../locales/no.json'));
	register('ru', () => import('../locales/ru.json'));
	register('ja', () => import('../locales/ja.json'));
	register('ar', () => import('../locales/ar.json'));
	register('pt-br', () => import('../locales/pt-br.json'));
	register('ro', () => import('../locales/ro.json'));
	register('sk', () => import('../locales/sk.json'));
	register('tr', () => import('../locales/tr.json'));
	register('uk', () => import('../locales/uk.json'));
	register('hu', () => import('../locales/hu.json'));

	let locales = [
		'en',
		'es',
		'fr',
		'de',
		'it',
		'zh',
		'nl',
		'sv',
		'pl',
		'ko',
		'no',
		'ru',
		'ja',
		'ar',
		'pt-br',
		'ro',
		'sk',
		'tr',
		'uk',
		'hu'
	];

	if (browser) {
		init({
			fallbackLocale: locales.includes(navigator.language.split('-')[0])
				? navigator.language.split('-')[0]
				: 'en',
			initialLocale: data.locale
		});
		// get the locale cookie if it exists and set it as the initial locale if it exists
		const localeCookie = document.cookie
			.split(';')
			.find((cookie) => cookie.trim().startsWith('locale='));
		if (localeCookie) {
			const localeValue = localeCookie.split('=')[1];
			locale.set(localeValue);
		}
	}

	import Navbar from '$lib/components/Navbar.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import 'tailwindcss/tailwind.css';
	import '$lib/styles/touchgrass-tokens.css';

	// Create a promise that resolves when the locale is ready
	export const localeLoaded = browser ? waitLocale() : Promise.resolve();
</script>

{#await localeLoaded}
	<!-- You can add a loading indicator here if needed -->
{:then}
	<Navbar {data} />
	<Toast />
	<slot />
{/await}

<svelte:head>
	<title>TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
	<meta
		name="description"
		content="Plan together, explore, and remember with TouchGrass."
	/>
</svelte:head>

<style>
	/* Prevent unwanted horizontal scroll and ensure single scrollbar */
	:global(html) {
		overflow-x: hidden;
		overflow-y: auto;
	}

	:global(body) {
		overflow: hidden;
		margin: 0;
		background: var(--tg-canvas);
		color: var(--tg-ink);
		font-family: var(--tg-font-body);
	}

	:global(.card), :global(.modal-box) {
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		box-shadow: var(--tg-shadow-card);
		color: hsl(var(--bc));
	}

	:global(.btn) { min-height: var(--tg-touch-min); border-radius: var(--tg-radius-control); text-transform: none; }
	:global(h1), :global(h2) { font-family: var(--tg-font-display); letter-spacing: -.02em; }
	:global(.drawer-side > div), :global(.drawer-side .bg-base-100) {
		background: var(--tg-surface-soft) !important;
		color: var(--tg-ink) !important;
	}
	:global(.drawer-side h2), :global(.drawer-side h3), :global(.drawer-side .label-text),
	:global(.drawer-side .stat-title), :global(.drawer-side .stat-value) {
		color: var(--tg-ink) !important;
	}
	:global(.drawer-side .card) { background: var(--tg-surface) !important; }
	:global(input), :global(select), :global(textarea) { color: var(--tg-ink); }
	:global(input::placeholder), :global(textarea::placeholder) { color: var(--tg-ink-muted); opacity: .82; }
	:global(.label-text), :global(.stat-title), :global(.stat-value) { color: var(--tg-ink); }
	:global(.dropdown-content), :global(.menu), :global(.table), :global(.tabs),
	:global(.form-control), :global(.card-body), :global(.modal-box) { color: hsl(var(--bc)); }
	:global(.dropdown-content input), :global(.dropdown-content select),
	:global(.dropdown-content textarea) { background-color: hsl(var(--b2)); color: hsl(var(--bc)); }

	/* Ensure slot content doesn't create nested scrollbars */
	:global(body > div) {
		overflow: visible;
	}
</style>
