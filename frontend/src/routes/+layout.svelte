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
	import { onNavigate } from '$app/navigation';
	import 'tailwindcss/tailwind.css';
	import '$lib/styles/touchgrass-tokens.css';

	const NAVIGATION_PROGRESS_DURATION_MS = 450;
	const NAVIGATION_PROGRESS_PATHS = new Set([
		'/dashboard',
		'/worldtravel',
		'/travel-map',
		'/trips',
		'/ballparks'
	]);
	let navigationProgressActive = false;
	let navigationSequence = 0;

	onNavigate((navigation) => {
		if (
			navigation.willUnload ||
			navigation.to?.route.id == null ||
			!NAVIGATION_PROGRESS_PATHS.has(navigation.to.url.pathname)
		)
			return;

		const sequence = ++navigationSequence;
		navigationProgressActive = true;

		return new Promise<() => void>((resolve) => {
			window.setTimeout(() => {
				resolve(() => {
					if (sequence === navigationSequence) navigationProgressActive = false;
				});
			}, NAVIGATION_PROGRESS_DURATION_MS);
		});
	});

	// Create a promise that resolves when the locale is ready
	export const localeLoaded = browser ? waitLocale() : Promise.resolve();
</script>

{#await localeLoaded}
	<!-- You can add a loading indicator here if needed -->
{:then}
	<Navbar {data} />
	{#if navigationProgressActive}
		<div
			class="navigation-progress"
			role="progressbar"
			aria-label="Loading page"
			style={`--navigation-progress-duration:${NAVIGATION_PROGRESS_DURATION_MS}ms`}
		>
			<span class="navigation-progress-bar navigation-progress-primary">
				<span class="navigation-progress-bar-inner"></span>
			</span>
		</div>
	{/if}
	<Toast />
	<slot />
{/await}

<svelte:head>
	<title>TouchGrass</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link
		href="https://fonts.googleapis.com/css2?family=Ovo&family=DM+Sans:wght@400;500;600;700&display=swap"
		rel="stylesheet"
	/>
	<meta name="description" content="Plan together, explore, and remember with TouchGrass." />
</svelte:head>

<style>
	/* Prevent unwanted horizontal scroll and ensure single scrollbar */
	:global(html) {
		overflow-x: hidden;
		overflow-y: auto;
		min-height: 100%;
	}

	:global(body) {
		overflow-x: hidden;
		overflow-y: auto;
		min-height: 100%;
		margin: 0;
		background: var(--tg-canvas);
		color: var(--tg-ink);
		font-family: var(--tg-font-body);
	}

	:global(*),
	:global(*::before),
	:global(*::after) {
		box-sizing: border-box;
	}

	:global(.card),
	:global(.modal-box) {
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		box-shadow: var(--tg-shadow-card);
		background: var(--tg-surface);
		color: var(--tg-ink);
	}

	:global(.btn) {
		min-height: var(--tg-touch-min);
		border-radius: var(--tg-radius-control);
		text-transform: none;
	}
	:global(h1),
	:global(h2) {
		font-family: var(--tg-font-display);
		letter-spacing: -0.02em;
	}
	:global(.drawer-side > div),
	:global(.drawer-side .bg-base-100) {
		background: var(--tg-surface-soft) !important;
		color: var(--tg-ink) !important;
	}
	:global(.drawer-side h2),
	:global(.drawer-side h3),
	:global(.drawer-side .label-text),
	:global(.drawer-side .stat-title),
	:global(.drawer-side .stat-value) {
		color: var(--tg-ink) !important;
	}
	:global(.drawer-side .card) {
		background: var(--tg-surface) !important;
	}
	:global(input),
	:global(select),
	:global(textarea) {
		color: var(--tg-ink);
	}
	:global(input::placeholder),
	:global(textarea::placeholder) {
		color: var(--tg-ink-muted);
		opacity: 0.82;
	}
	:global(input:-webkit-autofill),
	:global(input:-webkit-autofill:hover),
	:global(input:-webkit-autofill:focus) {
		-webkit-text-fill-color: var(--tg-ink);
		caret-color: var(--tg-ink);
		box-shadow: inset 0 0 0 1000px var(--tg-overlay-field);
		transition: background-color 9999s ease-out 0s;
	}
	:global(.label-text),
	:global(.stat-title),
	:global(.stat-value) {
		color: var(--tg-ink);
	}
	:global(.dropdown-content),
	:global(.menu),
	:global(.table),
	:global(.tabs),
	:global(.form-control),
	:global(.card-body),
	:global(.modal-box) {
		color: var(--tg-ink);
	}
	:global(.dropdown-content input),
	:global(.dropdown-content select),
	:global(.dropdown-content textarea) {
		background-color: var(--tg-overlay-field);
		color: var(--tg-ink);
	}

	/* Ensure slot content doesn't create nested scrollbars */
	:global(body > div) {
		overflow: visible;
		min-height: 100vh;
	}

	.navigation-progress {
		position: fixed;
		z-index: calc(var(--tg-layer-nav) + 5);
		top: calc(var(--tg-navbar-height) - 4px);
		left: 0;
		width: 100%;
		height: 4px;
		overflow: hidden;
		background: color-mix(in srgb, var(--tg-action) 20%, transparent);
		pointer-events: none;
		transform: translateZ(0);
	}
	.navigation-progress-bar {
		position: absolute;
		inset: 0;
		width: 100%;
	}
	.navigation-progress-bar-inner {
		position: absolute;
		display: inline-block;
		width: 100%;
		height: 100%;
		background: var(--tg-action);
		will-change: clip-path;
	}
	/* This requested navigation cue remains animated even when the global
	   reduced-motion rule suppresses nonessential motion elsewhere. */
	.navigation-progress-primary > .navigation-progress-bar-inner {
		animation: tg-progress-indeterminate var(--navigation-progress-duration) infinite linear !important;
	}
	@keyframes tg-progress-indeterminate {
		0% {
			animation-timing-function: cubic-bezier(0.5, 0, 0.7, 0.5);
			clip-path: inset(0 100% 0 0);
		}
		20% {
			animation-timing-function: cubic-bezier(0.3, 0.38, 0.55, 0.96);
			clip-path: inset(0 76% 0 2%);
		}
		55% {
			animation-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
			clip-path: inset(0 24% 0 18%);
		}
		78% {
			animation-timing-function: cubic-bezier(0.4, 0, 0.6, 1);
			clip-path: inset(0 6% 0 62%);
		}
		100% {
			clip-path: inset(0 0 0 100%);
		}
	}
</style>
