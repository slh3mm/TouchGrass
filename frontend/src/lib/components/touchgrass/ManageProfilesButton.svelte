<script lang="ts">
	import PlusIcon from '~icons/mdi/plus';

	export let label = 'Profiles';
</script>

<button type="button" on:click>
	<PlusIcon />
	<span>{label}</span>
</button>

<style>
	button {
		min-height: var(--tg-touch-min);
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		flex: 0 0 auto;
		border: 0;
		border-radius: var(--tg-radius-control);
		padding: 0.72rem 0.55rem;
		background: transparent;
		color: var(--tg-ink);
		font: 800 0.9rem var(--tg-font-body);
		cursor: pointer;
		transition:
			background var(--tg-motion-fast),
			color var(--tg-motion-fast);
	}

	button:hover,
	button:focus-visible {
		background: transparent;
		color: var(--tg-action);
		text-decoration: underline;
		text-decoration-thickness: 2px;
		text-underline-offset: 4px;
	}

	button:focus-visible {
		outline: 0;
		box-shadow: inset 0 -2px var(--tg-action);
		border-radius: 0;
	}

	button :global(svg) {
		width: 1rem;
		height: 1rem;
	}
</style>
