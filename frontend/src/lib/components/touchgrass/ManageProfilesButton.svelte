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
		gap: .4rem;
		flex: 0 0 auto;
		border: 0;
		border-radius: var(--tg-radius-control);
		padding: .72rem .55rem;
		background: transparent;
		color: var(--tg-ink);
		font: 800 .9rem var(--tg-font-body);
		cursor: pointer;
		transition: background var(--tg-motion-fast), color var(--tg-motion-fast);
	}

	button:hover,
	button:focus-visible {
		background: var(--tg-surface-soft);
		color: var(--tg-action);
	}

	button:focus-visible {
		outline: 2px solid var(--tg-action);
		outline-offset: 2px;
	}

	button :global(svg) {
		width: 1rem;
		height: 1rem;
	}
</style>
