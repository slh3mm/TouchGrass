<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { t } from 'svelte-i18n';
	import { themes } from '$lib';

	// Icons
	import Account from '~icons/mdi/account';
	import MapMarker from '~icons/mdi/map-marker';
	import Shield from '~icons/mdi/shield-account';
	import Settings from '~icons/mdi/cog';
	import Logout from '~icons/mdi/logout';
	import Phone from '~icons/mdi/cellphone';

	import MobileQR from '$lib/components/MobileQR.svelte';

	export let user: any;

	let letter: string = user.first_name?.[0] || user.username?.[0] || '?';
	let showMobileQR = false;
	let showDevMobileLogin = false;
	let typedBuffer = '';
	let theme = 'light';
	let isProfileMenuOpen = false;
	const DEV_UNLOCK_KEYWORD = 'dev';

	// Get display name
	$: displayName = user.first_name
		? `${user.first_name} ${user.last_name || ''}`.trim()
		: user.username || 'User';

	// Get initials for fallback
	$: initials =
		user.first_name && user.last_name ? `${user.first_name[0]}${user.last_name[0]}` : letter;

	// Menu items for better organization
	const menuItems = [
		{
			path: `/profile/${user.username}`,
			icon: Account,
			label: 'navbar.profile',
			section: 'main'
		},
		{
			path: '/locations',
			icon: MapMarker,
			label: 'locations.my_locations',
			section: 'main'
		},
		{
			path: '/settings',
			icon: Settings,
			label: 'navbar.settings',
			section: 'secondary'
		}
	];

	// Add admin item if user is staff
	$: adminMenuItem = user.is_staff
		? {
				path: '/admin',
				icon: Shield,
				label: 'navbar.admin_panel',
				section: 'secondary'
			}
		: null;

	function openMobileQR() {
		showMobileQR = true;
	}

	function closeMobileQR() {
		showMobileQR = false;
	}

	onMount(() => {
		const storedTheme = localStorage.getItem('touchgrass-theme');
		theme = storedTheme && themes.some((option) => option.name === storedTheme)
			? storedTheme
			: document.documentElement.getAttribute('data-theme') || 'light';
		document.documentElement.setAttribute('data-theme', theme);
		const handleKeydown = (event: KeyboardEvent) => {
			if (event.metaKey || event.ctrlKey || event.altKey) return;
			if (event.key.length !== 1) return;

			typedBuffer = (typedBuffer + event.key.toLowerCase()).slice(-DEV_UNLOCK_KEYWORD.length);
			if (typedBuffer === DEV_UNLOCK_KEYWORD) {
				showDevMobileLogin = true;
			}
		};

		window.addEventListener('keydown', handleKeydown);

		return () => {
			window.removeEventListener('keydown', handleKeydown);
		};
	});

	function changeTheme(event: Event) {
		const nextTheme = (event.currentTarget as HTMLSelectElement).value;
		if (!themes.some((option) => option.name === nextTheme)) return;
		theme = nextTheme;
		document.documentElement.setAttribute('data-theme', nextTheme);
		localStorage.setItem('touchgrass-theme', nextTheme);
		document.cookie = `colortheme=${encodeURIComponent(nextTheme)}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
	}
</script>

<div class="profile-menu-root">
	<button
		type="button"
		class="btn btn-ghost btn-circle avatar hover:bg-base-200 transition-colors"
		aria-label="Open profile menu"
		aria-expanded={isProfileMenuOpen}
		on:click={() => (isProfileMenuOpen = !isProfileMenuOpen)}
	>
		<div class="w-10 rounded-full ring-2 ring-primary/20 hover:ring-primary/40 transition-all">
			{#if user.profile_pic}
				<img src={user.profile_pic} alt={$t('navbar.profile')} class="rounded-full object-cover" />
			{:else}
				<div
					class="touchgrass-avatar w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm"
				>
					{initials.toUpperCase()}
				</div>
			{/if}
		</div>
	</button>

	{#if isProfileMenuOpen}
	<button class="profile-menu-backdrop" type="button" aria-label="Close profile menu" on:click={() => (isProfileMenuOpen = false)}></button>
	<div
		class="profile-dropdown shadow-2xl border"
		role="dialog"
		aria-label="Profile menu"
	>
		<!-- User Info Header -->
		<div class="profile-header">
			<div class="flex items-center gap-3">
				<div class="avatar placeholder">
					<div class="w-12 rounded-full ring-2 ring-primary/20">
						{#if user.profile_pic}
							<img
								src={user.profile_pic}
								alt={$t('navbar.profile')}
								class="rounded-full object-cover"
							/>
						{:else}
							<div
								class="touchgrass-avatar w-12 h-12 rounded-full flex items-center justify-center font-semibold text-lg"
								style="line-height: 3rem;"
							>
								{initials.toUpperCase()}
							</div>
						{/if}
					</div>
				</div>
				<div class="flex-1 min-w-0">
					<p class="font-semibold text-base text-base-content truncate">
						{$t('navbar.greeting')}, {displayName}
					</p>
					<p class="text-sm text-base-content/60 truncate">
						@{user.username}
					</p>
				</div>
			</div>
		</div>

		<!-- Main Menu Items -->
		<div class="menu-section">
			{#each menuItems.filter((item) => item.section === 'main') as item}
				<div class="menu-item">
					<button
						class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl hover:bg-base-200"
						on:click={() => { isProfileMenuOpen = false; goto(item.path); }}
					>
						<svelte:component this={item.icon} class="w-5 h-5 text-base-content/70" />
						<span>{$t(item.label)}</span>
					</button>
				</div>
			{/each}
		</div>

		<div class="menu-divider"></div>

		<div class="theme-picker">
			<label for="profile-theme">{$t('navbar.theme_selection')}</label>
			<select id="profile-theme" bind:value={theme} on:change={changeTheme}>
				{#each themes as themeOption}
					<option value={themeOption.name}>{themeOption.label}</option>
				{/each}
			</select>
		</div>

		<div class="menu-divider"></div>

		<!-- Secondary Menu Items -->
		<div class="menu-section">
			{#if adminMenuItem}
				<div class="menu-item">
					<button
						class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl hover:bg-base-200"
						on:click={() => goto(adminMenuItem.path)}
					>
						<svelte:component this={adminMenuItem.icon} class="w-5 h-5 text-warning" />
						<span class="text-warning font-medium">{$t(adminMenuItem.label)}</span>
					</button>
				</div>
			{/if}

			{#if showDevMobileLogin}
				<!-- Mobile Login (dev unlock) -->
				<div class="menu-item">
					<button
						class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl hover:bg-base-200"
						on:click={openMobileQR}
					>
						<Phone class="w-5 h-5 text-base-content/70" />
						<span>{$t('navbar.mobile_login', { default: 'Mobile Login' })}</span>
					</button>
				</div>
			{/if}

			{#each menuItems.filter((item) => item.section === 'secondary') as item}
				<div class="menu-item">
					<button
						class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl hover:bg-base-200"
						on:click={() => goto(item.path)}
					>
						<svelte:component this={item.icon} class="w-5 h-5 text-base-content/70" />
						<span>{$t(item.label)}</span>
					</button>
				</div>
			{/each}
		</div>

		<div class="menu-divider"></div>

		<!-- Logout -->
		<form method="post" class="w-full">
			<div class="menu-item w-full">
				<button
					formaction="/?/logout"
					class="btn btn-ghost justify-start gap-3 w-full text-left rounded-xl hover:bg-error/10 hover:text-error transition-colors"
				>
					<Logout class="w-5 h-5" />
					<span>{$t('navbar.logout')}</span>
				</button>
			</div>
		</form>
	</div>
	{/if}
</div>

{#if showMobileQR}
	<MobileQR on:close={closeMobileQR} />
{/if}

<style>
	.touchgrass-avatar { background:var(--tg-action);color:var(--tg-action-text); }
	.profile-menu-root { position:relative;z-index:1001; }
	.profile-menu-backdrop { position:fixed;inset:0;z-index:9998;width:100vw;height:100vh;padding:0;border:0;border-radius:0;background:transparent !important;opacity:1;backdrop-filter:none !important;box-shadow:none;cursor:default; }
	.profile-dropdown { position:fixed;isolation:isolate;z-index:9999;top:4.5rem;right:.75rem;display:grid !important;gap:.25rem;width:min(320px,calc(100vw - 1.5rem));max-height:calc(100vh - 5.25rem);padding:.75rem !important;border-radius:18px;background-color:#f5f1e8 !important;border:1px solid #d5ccbc !important;color:#1d2320 !important;opacity:1 !important;backdrop-filter:none !important;filter:none !important;box-shadow:0 18px 50px rgba(0,0,0,.48) !important;overflow-y:auto; }
	.profile-dropdown::before { display:none !important;content:none !important; }
	.profile-dropdown :global(button),.profile-dropdown :global(span),.profile-dropdown :global(p),.profile-dropdown :global(label) { color:inherit !important; }
	:global(html[data-theme='light']) .profile-dropdown { background-color:#f5f1e8 !important;border-color:#d5ccbc !important;color:#1d2320 !important; }
	:global(html[data-theme='dark']) .profile-dropdown { background-color:#111713 !important;border-color:#38443c !important;color:#f4f0e8 !important; }
	:global(html[data-theme='dim']) .profile-dropdown { background-color:#1f2937 !important;border-color:#4b5563 !important;color:#f9fafb !important; }
	:global(html[data-theme='night']) .profile-dropdown { background-color:#0f1729 !important;border-color:#334155 !important;color:#e5e7eb !important; }
	:global(html[data-theme='forest']) .profile-dropdown { background-color:#171f17 !important;border-color:#3d513d !important;color:#f3f4f6 !important; }
	:global(html[data-theme='aqua']) .profile-dropdown { background-color:#193549 !important;border-color:#3f718b !important;color:#ffffff !important; }
	:global(html[data-theme='aestheticLight']) .profile-dropdown { background-color:#e9e7e7 !important;border-color:#b9b1b1 !important;color:#100f0f !important; }
	:global(html[data-theme='aestheticDark']) .profile-dropdown { background-color:#121212 !important;border-color:#3a3a3a !important;color:#e9e7e7 !important; }
	:global(html[data-theme='northernLights']) .profile-dropdown { background-color:#2e3440 !important;border-color:#59657a !important;color:#eceff4 !important; }
	.profile-header { padding:.65rem .55rem .8rem;border-bottom:0; }
	.menu-section { display:grid;gap:.25rem;margin:0; }
	.menu-item { display:block;margin:0;padding:0; }
	.menu-section :global(button) { min-height:44px;padding:.65rem .75rem; }
	.menu-divider { height:1px;margin:.4rem .3rem;background:currentColor;opacity:.18; }
	.theme-picker { display:grid;gap:.5rem;padding:.35rem .5rem; }
	.theme-picker label { color:inherit;font-size:.78rem;font-weight:700; }
	.theme-picker select { min-height:44px;width:100%;padding:0 .75rem;border:1px solid currentColor;border-radius:10px;background-color:#ffffff;color:#171717;font-weight:600; }
	:global(html[data-theme='dark']) .theme-picker select,
	:global(html[data-theme='dim']) .theme-picker select,
	:global(html[data-theme='night']) .theme-picker select,
	:global(html[data-theme='forest']) .theme-picker select,
	:global(html[data-theme='aqua']) .theme-picker select,
	:global(html[data-theme='aestheticDark']) .theme-picker select,
	:global(html[data-theme='northernLights']) .theme-picker select { background-color:#20252d;color:#ffffff; }
</style>
