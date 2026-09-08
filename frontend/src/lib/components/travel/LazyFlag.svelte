<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { observeVisibility } from './sharedVisibilityObserver';

	export let src: string;
	export let alt: string;
	export let countryCode: string;
	export let eager = false;

	let host: HTMLElement;
	let visible = eager;
	let failed = false;
	let stopObserving: (() => void) | null = null;

	function flagEmoji(code: string) {
		return code
			.toUpperCase()
			.replace(/[A-Z]/g, (letter) => String.fromCodePoint(127397 + letter.charCodeAt(0)));
	}

	onMount(() => {
		if (visible) {
			visible = true;
			return;
		}
		stopObserving = observeVisibility(host, () => {
			visible = true;
			stopObserving = null;
		});
	});

	onDestroy(() => stopObserving?.());
</script>

<span class="lazy-flag" bind:this={host}>
	{#if failed}
		<span class="fallback" role="img" aria-label={alt}>{flagEmoji(countryCode)}</span>
	{:else if visible}
		<img
			{src}
			{alt}
			width="180"
			height="120"
			loading={eager ? 'eager' : 'lazy'}
			decoding="async"
			fetchpriority={eager ? 'high' : 'low'}
			on:error={() => (failed = true)}
		/>
	{:else}
		<span class="skeleton" class:animated={eager} aria-hidden="true"></span>
	{/if}
</span>

<style>
	.lazy-flag,
	.lazy-flag img,
	.fallback,
	.skeleton {
		display: block;
		width: 100%;
		height: 100%;
	}
	.lazy-flag img {
		object-fit: cover;
	}
	.fallback {
		display: grid;
		place-items: center;
		background: var(--tg-overlay-field, #f7f2e9);
		font-size: 2.4rem;
		line-height: 1;
	}
	.skeleton {
		background: var(--tg-canvas-deep);
	}
	.skeleton.animated {
		background: linear-gradient(
			100deg,
			var(--tg-canvas-deep) 20%,
			var(--tg-surface) 42%,
			var(--tg-canvas-deep) 64%
		);
		background-size: 220% 100%;
		animation: shimmer 1.4s ease-in-out infinite;
	}
	@keyframes shimmer {
		to {
			background-position: -220% 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.skeleton {
			animation: none;
		}
	}
</style>
