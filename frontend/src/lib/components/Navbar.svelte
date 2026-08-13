<script lang="ts">
	import { goto } from '$app/navigation';
	export let data: any;

	import Calendar from '~icons/mdi/calendar';
	import AccountMultiple from '~icons/mdi/account-multiple';
	import MapMarker from '~icons/mdi/map-marker';
	import FormatListBulletedSquare from '~icons/mdi/format-list-bulleted-square';
	import Map from '~icons/mdi/map';
	import FlagVariant from '~icons/mdi/flag-variant';
	import Airplane from '~icons/mdi/airplane';
	import Baseball from '~icons/mdi/baseball';
	import Menu from '~icons/mdi/menu';
	import Avatar from './Avatar.svelte';
	import { page } from '$app/stores';
	import { t } from 'svelte-i18n';


	// Navigation items for better organization
	// Keep AdventureLog's broader feature set available without exposing it on the
	// family display. Flip this single flag when those sections are wanted again.
	const ENABLE_LEGACY_NAVIGATION = false;
	const coreNavigationItems = [
		{ path: '/worldtravel', icon: FlagVariant, text: 'Countries' },
		{ path: '/travel-map', icon: Map, text: 'Travel Map' },
		{ path: '/trips', icon: Airplane, text: 'Trips' }
		,{ path: '/ballparks', icon: Baseball, text: 'Ballparks' }
	];
	let currentDate = '';
	$: currentDate = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' }).format(new Date());
	const legacyNavigationItems = [
		{ path: '/locations', icon: MapMarker, text: 'Locations' },
		{ path: '/collections', icon: FormatListBulletedSquare, text: 'Collections' },
		{ path: '/calendar', icon: Calendar, text: 'Calendar' },
		{ path: '/users', icon: AccountMultiple, text: 'Users' },
		{ path: '/map', icon: Map, text: 'Adventure Map' }
	];
	const navigationItems = ENABLE_LEGACY_NAVIGATION
		? [...coreNavigationItems, ...legacyNavigationItems]
		: coreNavigationItems;
	function isNavigationActive(path: string, currentPathname: string, currentView: string) {
		const target = new URL(path, 'http://local');
		if (target.pathname === '/worldtravel') {
			return currentPathname.startsWith('/worldtravel') && currentView !== 'map';
		}
		if (target.pathname === '/travel-map') {
			return currentPathname.startsWith('/travel-map') || (currentPathname === '/worldtravel' && currentView === 'map');
		}
		if (target.pathname === '/trips') {
			return currentPathname.startsWith('/trips') || currentPathname.startsWith('/collections/');
		}
		return currentPathname === target.pathname || currentPathname.startsWith(`${target.pathname}/`);
	}
</script>

<div class="navbar skylight-navbar top-0 z-[999] relative">
	<div class="navbar-start">
		<!-- Mobile Menu -->
		<div class="dropdown z-[999]">
			<div tabindex="0" role="button" class="btn btn-ghost btn-square lg:hidden">
				<Menu class="h-5 w-5" />
			</div>
			<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
			<ul
				tabindex="-1"
				class="menu dropdown-content mt-3 z-[999] p-4 shadow-2xl bg-base-100 border border-base-300 rounded-2xl gap-2 w-80 max-h-[80vh] overflow-y-auto"
			>
				{#if data.user}
					<!-- Navigation Items -->
					<div class="mb-4">
						<h3
							class="text-sm font-semibold text-base-content/60 uppercase tracking-wide mb-2 px-2"
						>
							{$t('navbar.navigation')}
						</h3>
						{#each navigationItems as item}
							<li>
								<a
									href={item.path}
									class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl"
									class:btn-active={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '')}
									class:active-nav={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '')}
									class:text-primary={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '')}
								>
									<svelte:component this={item.icon} class="w-5 h-5" />
									{item.text}
								</a>
							</li>
						{/each}
					</div>

					<div class="divider my-2"></div>

				{:else}
					<!-- Auth Buttons -->
					<div class="space-y-2">
						<li>
							<button class="btn btn-primary w-full" on:click={() => goto('/login')}>
								{$t('auth.login')}
							</button>
						</li>
						<li>
							<button class="btn btn-outline w-full" on:click={() => goto('/signup')}>
								{$t('auth.signup')}
							</button>
						</li>
					</div>
				{/if}
			</ul>
		</div>

		<!-- Logo -->
		<a class="btn btn-ghost hover:bg-transparent p-2 text-2xl font-bold tracking-tight" href="/">
			<div class="flex items-center gap-3">
				<img src="/favicon.png" alt="TouchGrass" class="w-10 h-10" />
				<span class="hidden sm:inline mb-1"> TouchGrass </span>
			</div>
		</a>
		<span class="nav-date hidden md:inline">{currentDate}</span>
	</div>

	<!-- Desktop Navigation -->
	<div class="navbar-center hidden lg:flex">
		{#if data.user}
			<ul class="menu menu-horizontal gap-1">
				{#each navigationItems as item}
					<li>
						<a
							href={item.path}
							class="nav-link btn btn-ghost gap-2 rounded-xl transition-all duration-200 hover:bg-base-200"
							class:active-nav={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '')}
							class:text-primary={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '')}
							aria-current={isNavigationActive(item.path, $page.url.pathname, $page.url.searchParams.get('view') || '') ? 'page' : undefined}
						>
							<svelte:component this={item.icon} class="w-4 h-4" />
							<span class="hidden xl:inline">{item.text}</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="navbar-end gap-3">

		<!-- Auth Buttons (Desktop) -->
		{#if !data.user}
			<div class="hidden lg:flex gap-2">
				<button class="btn btn-primary btn-sm" on:click={() => goto('/login')}>
					{$t('auth.login')}
				</button>
				<button class="btn btn-neutral btn-sm" on:click={() => goto('/signup')}>
					{$t('auth.signup')}
				</button>
			</div>
		{/if}

		<!-- User Avatar -->
		{#if data.user}
			<Avatar user={data.user} />
		{/if}

	</div>
</div>

<style>
	.skylight-navbar {
		--nav-active-color:oklch(var(--p));
		background:#f7f2e9;
		background:color-mix(in srgb,hsl(var(--b1)) 96%,transparent);
		backdrop-filter: blur(18px);
		border-bottom: 1px solid rgba(75, 67, 60, .14);
		color: var(--tg-ink);
		box-shadow: 0 5px 20px rgba(62, 54, 46, .06);
	}
	.skylight-navbar :global(.dropdown-content) { color:hsl(var(--bc)) !important;border-color:hsl(var(--bc)/.2) !important; }
	.skylight-navbar :global(.dropdown-content button),
	.skylight-navbar :global(.dropdown-content span),
	.skylight-navbar :global(.dropdown-content h3),
	.skylight-navbar :global(.dropdown-content label) { color:var(--tg-ink) !important; }
	.skylight-navbar :global(.active-nav) { background:transparent !important;color:var(--nav-active-color) !important;box-shadow:none !important;font-weight:700; }
	.skylight-navbar :global(.active-nav span),.skylight-navbar :global(.active-nav svg) { color:var(--nav-active-color) !important; }
	.nav-link { position:relative;overflow:visible; }
	.nav-link::after { content:'';position:absolute;left:.75rem;right:.75rem;bottom:.2rem;height:3px;border-radius:999px;background:currentColor;opacity:0;transform:scaleX(.45);transform-origin:center;transition:opacity var(--tg-motion-fast),transform var(--tg-motion-fast);pointer-events:none; }
	.nav-link:hover::after,.nav-link:focus-visible::after { opacity:.5;transform:scaleX(1); }
	.nav-link.active-nav::after { opacity:1;transform:scaleX(1); }
	.nav-date { padding-left:.85rem;border-left:1px solid var(--tg-border);color:var(--tg-ink-muted);font-family:var(--tg-font-display);font-size:1.05rem;white-space:nowrap; }
</style>
