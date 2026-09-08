<script lang="ts">
	import type { PageData } from './$types';
	import { t } from 'svelte-i18n';
	import AirplaneIcon from '~icons/mdi/airplane';
	import BaseballIcon from '~icons/mdi/baseball';
	import CityIcon from '~icons/mdi/city-variant-outline';
	import FlagIcon from '~icons/mdi/flag-checkered-variant';
	import MapIcon from '~icons/mdi/map-outline';
	import RegionIcon from '~icons/mdi/map-marker-star-outline';

	export let data: PageData;

	const user = data.user;
	const stats = data.props?.stats || {
		visited_country_count: 0,
		visited_region_count: 0,
		visited_city_count: 0
	};
	const totalCountries = 250;
	$: completionPercentage = Math.round((stats.visited_country_count / totalCountries) * 100);

	const destinations = [
		{
			href: '/worldtravel',
			label: 'Passport',
			copy: 'Browse countries, states, provinces, flags, and visit history.',
			icon: FlagIcon
		},
		{
			href: '/travel-map',
			label: 'Travel Map',
			copy: 'See every household profile together on the world map.',
			icon: MapIcon
		},
		{
			href: '/trips',
			label: 'Trips',
			copy: 'Plan what is next and keep completed journeys organized.',
			icon: AirplaneIcon
		},
		{
			href: '/ballparks',
			label: 'Ballparks',
			copy: 'Track all 30 Major League parks on one stadium map.',
			icon: BaseballIcon
		}
	];
</script>

<svelte:head>
	<title>Home | TouchGrass</title>
	<meta name="description" content="Your shared TouchGrass travel home." />
</svelte:head>

<main class="dashboard-page">
	<div class="dashboard-inner">
		<header>
			<div>
				<span class="eyebrow">Household travel</span>
				<h1>{$t('dashboard.welcome_back')}, {user?.first_name || user?.username}!</h1>
				<p>Pick up where you left off, add a trip, or explore your shared map.</p>
			</div>
		</header>

		<section class="summary-grid" aria-label="Travel summary">
			<article>
				<div>
					<span>{$t('dashboard.countries_visited')}</span><strong
						>{stats.visited_country_count}</strong
					><small>{completionPercentage}% of the passport</small>
				</div>
				<i><FlagIcon /></i>
				<progress
					value={stats.visited_country_count}
					max={totalCountries}
					aria-label={`${completionPercentage}% of countries visited`}
				></progress>
			</article>
			<article>
				<div>
					<span>{$t('dashboard.total_visited_regions')}</span><strong
						>{stats.visited_region_count}</strong
					><small>States and provinces</small>
				</div>
				<i><RegionIcon /></i>
			</article>
			<article>
				<div>
					<span>{$t('dashboard.total_visited_cities')}</span><strong
						>{stats.visited_city_count}</strong
					><small>Dated places and memories</small>
				</div>
				<i><CityIcon /></i>
			</article>
		</section>

		<section class="feature-hub">
			<div class="section-heading">
				<span class="eyebrow">TouchGrass</span>
				<h2>Where to next?</h2>
			</div>
			<div class="feature-grid">
				{#each destinations as destination}
					<a href={destination.href}>
						<i><svelte:component this={destination.icon} /></i>
						<div><strong>{destination.label}</strong><span>{destination.copy}</span></div>
					</a>
				{/each}
			</div>
		</section>
	</div>
</main>

<style>
	.dashboard-page {
		min-height: calc(100dvh - var(--tg-navbar-height));
		padding: clamp(1.25rem, 4vw, 3.5rem) var(--tg-page-gutter);
		background: var(--tg-canvas);
		color: var(--tg-ink);
	}
	.dashboard-inner {
		width: min(100%, var(--tg-content-width));
		margin-inline: auto;
	}
	header {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 2rem;
		margin-bottom: 2rem;
	}
	h1,
	h2 {
		margin: 0.15rem 0;
		font-family: var(--tg-font-display);
		font-weight: 400;
		line-height: 1;
	}
	h1 {
		font-size: clamp(3rem, 6vw, 5.4rem);
	}
	h2 {
		font-size: clamp(2.2rem, 4vw, 3.4rem);
	}
	header p {
		max-width: 62ch;
		margin: 0.65rem 0 0;
		color: var(--tg-ink-muted);
		font-size: 1.05rem;
	}
	.eyebrow {
		color: var(--tg-ink-muted);
		font-size: 0.72rem;
		font-weight: 800;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	.summary-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
	}
	.summary-grid article {
		position: relative;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		min-height: 168px;
		padding: 1.25rem;
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.summary-grid article span,
	.summary-grid article small {
		display: block;
		color: var(--tg-ink-muted);
	}
	.summary-grid article span {
		font-weight: 750;
	}
	.summary-grid article strong {
		display: block;
		margin: 0.15rem 0;
		font: 400 2.8rem/1 var(--tg-font-display);
	}
	.summary-grid article small {
		font-size: 0.78rem;
	}
	.summary-grid article i,
	.feature-grid i {
		display: grid;
		width: 50px;
		height: 50px;
		place-items: center;
		border-radius: 16px;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
		font-style: normal;
	}
	.summary-grid article i :global(svg),
	.feature-grid i :global(svg) {
		width: 26px;
		height: 26px;
	}
	.summary-grid progress {
		position: absolute;
		right: 1.25rem;
		bottom: 1.2rem;
		left: 1.25rem;
		width: calc(100% - 2.5rem);
		height: 6px;
		overflow: hidden;
		border: 0;
		border-radius: 999px;
		background: var(--tg-canvas-deep);
	}
	.summary-grid progress::-webkit-progress-bar {
		background: var(--tg-canvas-deep);
	}
	.summary-grid progress::-webkit-progress-value {
		background: var(--tg-action);
	}
	.summary-grid progress::-moz-progress-bar {
		background: var(--tg-action);
	}
	.feature-hub {
		margin-top: 2rem;
		padding: clamp(1.2rem, 3vw, 2rem);
		border: 1px solid var(--tg-border);
		border-radius: var(--tg-radius-panel);
		background: var(--tg-surface);
		box-shadow: var(--tg-shadow-card);
	}
	.section-heading {
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--tg-border);
	}
	.feature-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
		margin-top: 1rem;
	}
	.feature-grid a {
		display: flex;
		align-items: center;
		gap: 1rem;
		min-height: 104px;
		padding: 1rem;
		border: 1px solid var(--tg-border);
		border-radius: 18px;
		background: var(--tg-overlay-field);
		color: var(--tg-ink);
		text-decoration: none;
		transition:
			transform var(--tg-motion-fast),
			border-color var(--tg-motion-fast),
			box-shadow var(--tg-motion-fast);
	}
	.feature-grid a:hover {
		transform: translateY(-2px);
		border-color: var(--tg-border-strong);
		box-shadow: var(--tg-shadow-control);
	}
	.feature-grid strong,
	.feature-grid span {
		display: block;
	}
	.feature-grid strong {
		font-size: 1.05rem;
	}
	.feature-grid span {
		margin-top: 0.2rem;
		color: var(--tg-ink-muted);
		font-size: 0.86rem;
		line-height: 1.4;
	}
	@media (max-width: 900px) {
		header {
			align-items: start;
			flex-direction: column;
		}
		.summary-grid {
			grid-template-columns: 1fr;
		}
		.summary-grid article {
			min-height: 142px;
		}
		.feature-grid {
			grid-template-columns: 1fr;
		}
	}
	@media (max-width: 560px) {
		.dashboard-page {
			padding: 1.1rem;
		}
		.summary-grid article {
			min-height: 132px;
		}
		.feature-hub {
			padding: 1rem;
		}
		.feature-grid a {
			align-items: flex-start;
		}
		.feature-grid i {
			flex: 0 0 auto;
		}
	}
</style>
