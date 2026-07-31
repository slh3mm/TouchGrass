<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	export let options: Array<{ value: string; label: string }> = []; export let value = ''; export let label = 'Choose an option';
	const dispatch = createEventDispatcher<{ change: string }>(); function select(next: string){value=next;dispatch('change',next)}
</script>
<div role="group" aria-label={label}>{#each options as option}<button type="button" class:active={value === option.value} aria-pressed={value === option.value} on:click={() => select(option.value)}>{option.label}</button>{/each}</div>
<style>
	div{display:inline-flex;padding:3px;border-radius:var(--tg-radius-control);background:var(--tg-canvas-deep)}button{min-height:38px;padding:.5rem .85rem;border:0;border-radius:var(--tg-radius-control);background:transparent;color:var(--tg-ink-muted);font:600 .85rem var(--tg-font-body);cursor:pointer}button.active{background:var(--tg-action);color:var(--tg-action-text)}
</style>
