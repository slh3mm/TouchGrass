<script lang="ts">
	export let title: string;
	export let description: string;
	export let connected = false;
	export let id: string | undefined = undefined;
</script>

<section {id} class="integration-card">
	<header>
		<div class="identity">
			<span class="icon"><slot name="icon" /></span>
			<div>
				<h3>{title}</h3>
				<p>{description}</p>
			</div>
		</div>
		<span class:connected class="status" role="status"
			>{connected ? 'Connected' : 'Disconnected'}</span
		>
	</header>
	{#if $$slots.default}<div class="integration-body"><slot /></div>{/if}
</section>

<style>
	.integration-card {
		margin-bottom: 1rem;
		padding: 1.2rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-card);
	}
	header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	.identity {
		display: flex;
		align-items: center;
		gap: 0.85rem;
		min-width: 0;
	}
	.icon {
		display: grid;
		width: 48px;
		height: 48px;
		flex: 0 0 48px;
		place-items: center;
		border-radius: 14px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.icon :global(svg),
	.icon :global(img) {
		width: 27px;
		height: 27px;
		object-fit: contain;
	}
	h3 {
		margin: 0;
		color: var(--tg-ink-strong);
		font: 400 1.65rem/1.05 var(--tg-font-display);
	}
	p {
		margin: 0.25rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 0.88rem;
	}
	.status {
		display: inline-flex;
		min-height: 30px;
		align-items: center;
		padding: 0.3rem 0.65rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
		font-size: 0.75rem;
		font-weight: 800;
		white-space: nowrap;
	}
	.status.connected {
		border-color: color-mix(in srgb, var(--tg-success) 48%, var(--tg-border));
		background: color-mix(in srgb, var(--tg-success) 16%, var(--tg-surface));
		color: color-mix(in srgb, var(--tg-success) 72%, var(--tg-ink));
	}
	.integration-body {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--tg-border);
	}
	@media (max-width: 640px) {
		.integration-card {
			padding: 1rem;
		}
		header {
			align-items: stretch;
			flex-direction: column;
		}
		.status {
			width: max-content;
			margin-left: 3.9rem;
		}
		.identity {
			align-items: flex-start;
		}
	}
</style>
