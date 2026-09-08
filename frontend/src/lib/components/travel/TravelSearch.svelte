<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import SearchIcon from '~icons/mdi/magnify';
	import CloseIcon from '~icons/mdi/close';
	import type { TravelSearchItem } from './travelSearch';
	import { normalizeTravelSearch, travelSearchSuggestions } from './travelSearch';

	export let items: TravelSearchItem[] = [];
	export let query = '';
	export let label = 'Search travel locations';
	export let placeholder = 'Search countries';

	let open = false;
	let activeIndex = 0;
	let closeTimer: ReturnType<typeof setTimeout> | null = null;
	const listboxId = `travel-search-${label.toLocaleLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
	const dispatch = createEventDispatcher<{
		select: TravelSearchItem;
		clear: void;
		dismiss: void;
	}>();

	$: rankedSuggestions = travelSearchSuggestions(items, query);
	$: suggestionGroups = (['country', 'state', 'province'] as const)
		.map((kind) => ({ kind, items: rankedSuggestions.filter((item) => item.kind === kind) }))
		.filter((group) => group.items.length);
	$: suggestions = suggestionGroups.flatMap((group) => group.items);
	$: if (activeIndex >= suggestions.length) activeIndex = Math.max(0, suggestions.length - 1);

	function choose(item: TravelSearchItem) {
		query = item.label;
		open = false;
		dispatch('select', item);
	}

	function clear() {
		query = '';
		open = false;
		activeIndex = 0;
		dispatch('clear');
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' && suggestions.length) {
			event.preventDefault();
			open = true;
			activeIndex = (activeIndex + 1) % suggestions.length;
		} else if (event.key === 'ArrowUp' && suggestions.length) {
			event.preventDefault();
			open = true;
			activeIndex = (activeIndex - 1 + suggestions.length) % suggestions.length;
		} else if (event.key === 'Enter' && open && suggestions[activeIndex]) {
			event.preventDefault();
			choose(suggestions[activeIndex]);
		} else if (event.key === 'Escape') {
			open = false;
			dispatch('dismiss');
		}
	}

	function handleBlur() {
		closeTimer = setTimeout(() => (open = false), 120);
	}

	function handleFocus() {
		if (closeTimer) clearTimeout(closeTimer);
		open = Boolean(normalizeTravelSearch(query));
	}

	function matchParts(labelText: string) {
		const directIndex = labelText.toLocaleLowerCase().indexOf(query.trim().toLocaleLowerCase());
		if (directIndex < 0 || !query.trim()) return [labelText, '', ''];
		return [
			labelText.slice(0, directIndex),
			labelText.slice(directIndex, directIndex + query.trim().length),
			labelText.slice(directIndex + query.trim().length)
		];
	}
</script>

<div class="travel-search" on:focusin={handleFocus} on:focusout={handleBlur}>
	<label for={listboxId}>{label}</label>
	<div class="input-shell">
		<SearchIcon aria-hidden="true" />
		<input
			id={listboxId}
			bind:value={query}
			{placeholder}
			role="combobox"
			aria-autocomplete="list"
			aria-expanded={open && suggestions.length > 0}
			aria-controls={`${listboxId}-options`}
			aria-activedescendant={open && suggestions[activeIndex]
				? `${listboxId}-option-${activeIndex}`
				: undefined}
			on:input={() => {
				open = Boolean(normalizeTravelSearch(query));
				activeIndex = 0;
			}}
			on:keydown={handleKeydown}
		/>
		{#if query}
			<button class="clear" type="button" aria-label="Clear search" on:click={clear}
				><CloseIcon /></button
			>
		{/if}
	</div>

	{#if open && suggestions.length}
		<div
			class="suggestions"
			id={`${listboxId}-options`}
			role="listbox"
			aria-label="Suggested locations"
		>
			{#each suggestionGroups as group}
				<div class="suggestion-group" role="presentation">
					{group.kind === 'country'
						? 'Countries'
						: group.kind === 'state'
							? 'US states'
							: 'Canadian provinces'}
				</div>
				{#each group.items as item (item.id)}
					{@const index = suggestions.indexOf(item)}
					{@const parts = matchParts(item.label)}
					<button
						id={`${listboxId}-option-${index}`}
						type="button"
						role="option"
						aria-selected={index === activeIndex}
						class:active={index === activeIndex}
						on:mouseenter={() => (activeIndex = index)}
						on:mousedown|preventDefault
						on:click={() => choose(item)}
					>
						<span class="result-icon">
							{#if item.flagUrl}<img
									src={item.flagUrl}
									alt=""
									width="36"
									height="24"
									decoding="async"
								/>{:else}<strong>{item.code}</strong>{/if}
						</span>
						<span class="result-copy">
							<strong
								>{parts[0]}{#if parts[1]}<mark>{parts[1]}</mark>{/if}{parts[2]}</strong
							>
							<small>{item.subtitle}</small>
						</span>
						<span class="result-meta"
							><small>{item.kind}</small>{#if item.colors.length}<span class="swatches"
									>{#each item.colors.slice(0, 4) as color}<i style={`--swatch:${color}`}
										></i>{/each}</span
								>{/if}</span
						>
					</button>
				{/each}
			{/each}
		</div>
	{:else if open && normalizeTravelSearch(query)}
		<div class="suggestions empty" role="status">No matching locations</div>
	{/if}
</div>

<style>
	.travel-search {
		position: relative;
		width: min(520px, 100%);
		font-family: var(--tg-font-body);
		z-index: 30;
	}
	.travel-search > label {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
	.input-shell {
		display: grid;
		grid-template-columns: 22px minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.55rem;
		min-height: 48px;
		padding: 0 0.55rem 0 0.9rem;
		border: 1px solid var(--tg-border-strong);
		border-radius: 999px;
		background: var(--tg-overlay-field, var(--tg-surface));
		color: var(--tg-ink);
		box-shadow: 0 4px 14px rgba(30, 26, 22, 0.06);
	}
	.input-shell:focus-within {
		border-color: var(--tg-action);
		box-shadow:
			0 0 0 3px color-mix(in srgb, var(--tg-action) 18%, transparent),
			0 7px 22px rgba(30, 26, 22, 0.1);
	}
	.input-shell > :global(svg) {
		width: 20px;
		height: 20px;
		color: var(--tg-ink-muted);
	}
	input {
		width: 100%;
		min-width: 0;
		border: 0;
		outline: 0;
		background: transparent;
		color: var(--tg-ink);
		font: 650 0.92rem var(--tg-font-body);
	}
	input::placeholder {
		color: var(--tg-ink-muted);
		opacity: 0.9;
	}
	.clear {
		display: grid;
		width: 36px;
		height: 36px;
		place-items: center;
		border: 0;
		border-radius: 50%;
		background: transparent;
		color: var(--tg-ink-muted);
		cursor: pointer;
	}
	.clear:hover {
		background: var(--tg-canvas-deep);
		color: var(--tg-ink);
	}
	.suggestions {
		position: absolute;
		z-index: 40;
		top: calc(100% + 0.45rem);
		left: 0;
		right: 0;
		display: grid;
		max-height: min(420px, 60vh);
		padding: 0.4rem;
		overflow: auto;
		border: 1px solid var(--tg-border-strong);
		border-radius: 18px;
		background: var(--tg-overlay-surface, var(--tg-surface));
		box-shadow: 0 18px 45px rgba(31, 27, 24, 0.22);
	}
	.suggestions > button {
		display: grid;
		grid-template-columns: 42px minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.65rem;
		min-height: 54px;
		padding: 0.48rem 0.6rem;
		border: 0;
		border-radius: 12px;
		background: transparent;
		color: var(--tg-ink);
		text-align: left;
		cursor: pointer;
	}
	.suggestions > button:hover,
	.suggestions > button.active {
		background: var(--tg-canvas-deep);
	}
	.suggestion-group {
		padding: 0.55rem 0.65rem 0.25rem;
		color: var(--tg-ink-muted);
		font-size: 0.62rem;
		font-weight: 850;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	.result-icon {
		display: grid;
		width: 38px;
		height: 30px;
		place-items: center;
		overflow: hidden;
		border: 1px solid var(--tg-border);
		border-radius: 7px;
		background: var(--tg-surface);
	}
	.result-icon img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.result-icon strong {
		font-size: 0.7rem;
		letter-spacing: 0.05em;
	}
	.result-copy {
		min-width: 0;
	}
	.result-copy strong,
	.result-copy small {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.result-copy strong {
		font-size: 0.88rem;
	}
	.result-copy small {
		margin-top: 0.12rem;
		color: var(--tg-ink-muted);
		font-size: 0.68rem;
	}
	mark {
		padding: 0;
		background: transparent;
		color: var(--tg-action);
		font-weight: 900;
	}
	.result-meta {
		display: grid;
		justify-items: end;
		gap: 0.3rem;
	}
	.result-meta > small {
		color: var(--tg-ink-muted);
		font-size: 0.58rem;
		font-weight: 850;
		letter-spacing: 0.09em;
		text-transform: uppercase;
	}
	.swatches {
		display: flex;
	}
	.swatches i {
		width: 10px;
		height: 10px;
		margin-left: -2px;
		border: 1px solid var(--tg-overlay-surface, #fff);
		border-radius: 50%;
		background: var(--swatch);
	}
	.empty {
		padding: 1rem;
		color: var(--tg-ink-muted);
		font-size: 0.82rem;
		text-align: center;
	}
	@media (max-width: 560px) {
		.suggestions {
			position: fixed;
			z-index: 1110;
			top: auto;
			right: 0.5rem;
			bottom: 0.5rem;
			left: 0.5rem;
			max-height: 52vh;
			border-radius: 22px;
			padding: 0.55rem;
		}
		.suggestions > button {
			min-height: 58px;
		}
		.travel-search {
			z-index: 1111;
		}
	}
</style>
