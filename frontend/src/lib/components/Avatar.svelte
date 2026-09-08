<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { t } from 'svelte-i18n';
	import { themes } from '$lib';

	// Icons
	import Account from '~icons/mdi/account';
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
		theme =
			storedTheme && themes.some((option) => option.name === storedTheme)
				? storedTheme
				: document.documentElement.getAttribute('data-theme') || 'light';
		document.documentElement.setAttribute('data-theme', theme);
		const handleKeydown = (event: KeyboardEvent) => {
			if (event.key === 'Escape' && isProfileMenuOpen) {
				isProfileMenuOpen = false;
				return;
			}
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
		aria-haspopup="menu"
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
		<button
			class="profile-menu-backdrop"
			type="button"
			aria-label="Close profile menu"
			on:click={() => (isProfileMenuOpen = false)}
		></button>
		<div class="profile-dropdown" role="menu" aria-label="Profile menu">
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
							class="menu-action"
							on:click={() => {
								isProfileMenuOpen = false;
								goto(item.path);
							}}
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
							class="menu-action warning"
							on:click={() => {
								isProfileMenuOpen = false;
								goto(adminMenuItem.path);
							}}
						>
							<svelte:component this={adminMenuItem.icon} class="w-5 h-5 text-warning" />
							<span class="text-warning font-medium">{$t(adminMenuItem.label)}</span>
						</button>
					</div>
				{/if}

				{#if showDevMobileLogin}
					<!-- Mobile Login (dev unlock) -->
					<div class="menu-item">
						<button class="menu-action" on:click={openMobileQR}>
							<Phone class="w-5 h-5 text-base-content/70" />
							<span>{$t('navbar.mobile_login', { default: 'Mobile Login' })}</span>
						</button>
					</div>
				{/if}

				{#each menuItems.filter((item) => item.section === 'secondary') as item}
					<div class="menu-item">
						<button
							class="menu-action"
							on:click={() => {
								isProfileMenuOpen = false;
								goto(item.path);
							}}
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
					<button formaction="/?/logout" class="menu-action danger">
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
	.touchgrass-avatar {
		background: var(--tg-action);
		color: var(--tg-action-text);
	}
	.profile-menu-root {
		position: relative;
		z-index: calc(var(--tg-layer-nav) + 3);
	}
	.profile-menu-backdrop {
		position: fixed;
		inset: 0;
		z-index: calc(var(--tg-layer-dropdown) - 1);
		width: 100vw;
		height: 100vh;
		padding: 0;
		border: 0;
		border-radius: 0;
		background: transparent;
		box-shadow: none;
		cursor: default;
	}
	.profile-dropdown {
		position: fixed;
		isolation: isolate;
		z-index: var(--tg-layer-dropdown);
		top: calc(var(--tg-navbar-height) + 0.5rem);
		right: 0.75rem;
		display: grid;
		gap: 0.25rem;
		width: min(320px, calc(100vw - 1.5rem));
		max-height: calc(100dvh - var(--tg-navbar-height) - 1.25rem);
		padding: 0.75rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		opacity: 1;
		box-shadow: var(--tg-shadow-overlay);
		overflow-y: auto;
	}
	.profile-header {
		padding: 0.65rem 0.55rem 0.8rem;
		border-bottom: 0;
	}
	.menu-section {
		display: grid;
		gap: 0.25rem;
		margin: 0;
	}
	.menu-item {
		display: block;
		margin: 0;
		padding: 0;
	}
	.menu-action {
		display: flex;
		width: 100%;
		min-height: 44px;
		align-items: center;
		justify-content: flex-start;
		gap: 0.75rem;
		padding: 0.65rem 0.75rem;
		border: 0;
		border-radius: 12px;
		background: transparent;
		color: var(--tg-ink);
		font: 650 0.9rem var(--tg-font-body);
		text-align: left;
		cursor: pointer;
		transition:
			background var(--tg-motion-fast),
			color var(--tg-motion-fast);
	}
	.menu-action:hover {
		background: var(--tg-surface-soft);
		color: var(--tg-action);
	}
	.menu-action.warning {
		color: var(--tg-warning);
	}
	.menu-action.danger {
		color: var(--tg-danger);
	}
	.menu-action.danger:hover {
		background: color-mix(in srgb, var(--tg-danger) 12%, var(--tg-surface));
	}
	.menu-divider {
		height: 1px;
		margin: 0.4rem 0.3rem;
		background: currentColor;
		opacity: 0.18;
	}
	.theme-picker {
		display: grid;
		gap: 0.5rem;
		padding: 0.35rem 0.5rem;
	}
	.theme-picker label {
		color: inherit;
		font-size: 0.78rem;
		font-weight: 700;
	}
	.theme-picker select {
		min-height: 44px;
		width: 100%;
		padding: 0 0.75rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 10px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		font: 600 0.9rem var(--tg-font-body);
	}
	@media (max-width: 560px) {
		.profile-dropdown {
			top: calc(var(--tg-navbar-height) + 0.35rem);
			right: 0.5rem;
			width: calc(100vw - 1rem);
		}
	}
</style>
