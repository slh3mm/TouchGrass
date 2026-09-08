<script lang="ts">
	export let label = 'Choose a profile';
	export let helper = '';
</script>

<section class="profile-bar" aria-label={label}>
	<div class="profile-list"><slot /></div>
	{#if helper}<p>{helper}</p>{/if}
</section>

<style>
	.profile-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-width: 0;
		padding: 0.65rem 0.4rem 1rem;
	}

	.profile-list {
		display: flex;
		box-sizing: border-box;
		min-width: 0;
		align-items: center;
		gap: 0.65rem;
		overflow-x: auto;
		padding: 0.85rem 0.9rem;
		scroll-padding-inline: 0.9rem;
		scrollbar-width: thin;
	}

	p {
		flex: 0 0 auto;
		margin: 0;
		color: var(--tg-ink-muted);
		font-size: 0.82rem;
		font-weight: 650;
	}

	@media (max-width: 700px) {
		.profile-bar {
			align-items: stretch;
			flex-direction: column;
			padding-inline: 0;
		}
		p {
			padding-inline: 0.25rem;
		}
	}
</style>
