<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	export let name: string; export let color = 'var(--tg-profile-coral)'; export let avatar = ''; export let active = false; export let disabled = false;
	const dispatch = createEventDispatcher<{ select: void }>();

	function readableText(background: string) {
		if (!/^#[0-9a-f]{6}$/i.test(background)) return '#171717';
		const red = parseInt(background.slice(1, 3), 16);
		const green = parseInt(background.slice(3, 5), 16);
		const blue = parseInt(background.slice(5, 7), 16);
		const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
		return luminance > 0.52 ? '#171717' : '#ffffff';
	}
</script>
<button type="button" class:active {disabled} style={`--profile-color:${color};--profile-ink:${readableText(color)}`} aria-pressed={active} on:click={() => dispatch('select')}><span class="avatar" aria-hidden="true">{avatar || name.slice(0,1).toUpperCase()}</span><span class="name">{name}</span></button>
<style>
	button{min-height:var(--tg-touch-min);display:inline-flex;align-items:center;gap:var(--tg-space-2);padding:.35rem .9rem .35rem .35rem;border:2px solid color-mix(in srgb,var(--profile-color) 75%,#171717);border-radius:var(--tg-radius-control);background:var(--profile-color);color:var(--profile-ink);font:700 .9rem var(--tg-font-body);cursor:pointer;opacity:1;transition:box-shadow var(--tg-motion-fast),transform var(--tg-motion-fast)}button:hover{transform:translateY(-1px);box-shadow:0 3px 10px rgba(0,0,0,.24)}button.active{border-color:transparent;box-shadow:0 0 0 2px #ffffff,0 0 0 5px #171717,0 5px 14px rgba(0,0,0,.32);transform:translateY(-1px)}button:disabled{cursor:not-allowed;opacity:.48}.avatar{display:grid;width:32px;height:32px;flex:0 0 auto;place-items:center;border-radius:50%;background:rgba(255,255,255,.9);color:#171717;text-shadow:none}.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-shadow:0 1px 2px rgba(0,0,0,.22)}
</style>
