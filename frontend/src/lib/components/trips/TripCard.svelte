<script lang="ts">
	import CalendarIcon from '~icons/mdi/calendar-range';
	import MapMarkerIcon from '~icons/mdi/map-marker-outline';

	type Profile = { id: string; name: string; color: string; avatar?: string };

	export let title: string;
	export let startDate: string;
	export let endDate: string;
	export let status = '';
	export let profiles: Profile[] = [];
	export let locations: string[] = [];
	export let notes = '';

	function formatDate(value: string) {
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		}).format(new Date(`${value}T12:00:00`));
	}

	function profileGradient() {
		const colors = profiles.map((profile) => profile.color).filter(Boolean);
		if (!colors.length) return 'var(--tg-action)';
		if (colors.length === 1) return colors[0];
		const width = 100 / colors.length;
		const stops = colors.flatMap((color, index) => [
			`${color} ${index * width}%`,
			`${color} ${(index + 1) * width}%`
		]);
		return `linear-gradient(90deg, ${stops.join(', ')})`;
	}

	function profileText(color: string) {
		const hex = color.replace('#', '');
		if (!/^[0-9a-f]{6}$/i.test(hex)) return '#1f1c22';
		const [red, green, blue] = [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
		const brightness = (red * 299 + green * 587 + blue * 114) / 1000;
		return brightness > 150 ? '#1f1c22' : '#ffffff';
	}
</script>

<article style={`--trip-stripe:${profileGradient()}`}>
	{#if status}<div class="trip-status"><CalendarIcon />{status}</div>{/if}
	{#if profiles.length}
		<div class="profiles" aria-label="Travelers">
			{#each profiles as profile}
				<i
					style={`--profile-color:${profile.color};--profile-ink:${profileText(profile.color)}`}
					title={profile.name}>{profile.avatar || profile.name[0]}</i
				>
			{/each}
		</div>
	{/if}
	<h3>{title}</h3>
	<p class="dates">{formatDate(startDate)} – {formatDate(endDate)}</p>
	{#if locations.length}
		<div class="destinations">
			{#each locations as location}<span><MapMarkerIcon />{location}</span>{/each}
		</div>
	{/if}
	{#if notes}<p class="notes">{notes}</p>{/if}
	{#if $$slots.actions}<div class="card-actions"><slot name="actions" /></div>{/if}
</article>

<style>
	article {
		position: relative;
		display: flex;
		min-height: 245px;
		box-sizing: border-box;
		flex-direction: column;
		overflow: hidden;
		padding: 1.3rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
		color: var(--tg-ink);
	}
	article::before {
		content: '';
		position: absolute;
		inset: 0 0 auto;
		height: 8px;
		background: var(--trip-stripe);
	}
	.trip-status {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		width: max-content;
		margin-top: 0.2rem;
		padding: 0.35rem 0.6rem;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.trip-status :global(svg) {
		width: 15px;
	}
	.profiles {
		position: absolute;
		top: 1.2rem;
		right: 1.2rem;
		display: flex;
	}
	.profiles i {
		display: grid;
		width: 34px;
		height: 34px;
		margin-left: -7px;
		place-items: center;
		border: 2px solid var(--tg-surface);
		border-radius: 50%;
		background: var(--profile-color);
		color: var(--profile-ink);
		font-style: normal;
		font-weight: 850;
		box-shadow: var(--tg-shadow-control);
	}
	h3 {
		margin: 0.35rem 0 0.25rem;
		padding-right: 3.2rem;
		font: 400 1.8rem/1.08 var(--tg-font-display);
		color: var(--tg-ink-strong);
	}
	.dates {
		margin: 0.15rem 0 0.75rem;
		color: var(--tg-ink-muted);
		font-weight: 650;
	}
	.destinations {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin: 0.45rem 0;
	}
	.destinations span {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.32rem 0.55rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: color-mix(in srgb, var(--tg-surface) 92%, var(--tg-canvas));
		color: var(--tg-ink);
		font-size: 0.72rem;
		font-weight: 750;
	}
	.destinations :global(svg) {
		width: 14px;
		color: var(--tg-ink-muted);
	}
	.notes {
		display: -webkit-box;
		overflow: hidden;
		margin: 0.5rem 0;
		color: var(--tg-ink-muted);
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
	}
	.card-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem;
		margin-top: auto;
		padding-top: 1.2rem;
	}
	.card-actions :global(a),
	.card-actions :global(button) {
		font: inherit;
	}
	@media (max-width: 700px) {
		.profiles {
			position: static;
			margin-top: 0.4rem;
		}
		.profiles i {
			margin-right: -7px;
			margin-left: 0;
		}
		h3 {
			padding-right: 0;
		}
		.card-actions {
			align-items: stretch;
			flex-direction: column;
		}
		.card-actions :global(a),
		.card-actions :global(button) {
			width: 100%;
		}
	}
</style>
