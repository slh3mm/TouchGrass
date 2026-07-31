<script lang="ts">
	export let variant: 'glass' | 'solid' | 'soft' = 'glass';
	export let padding: 'none' | 'compact' | 'comfortable' = 'comfortable';
	export let className = '';
</script>
<section class={`touch-panel ${variant} ${padding} ${className}`}><slot /></section>
<style>
	.touch-panel{border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);color:var(--tg-ink)}
	.glass{background:var(--tg-surface-glass);backdrop-filter:blur(var(--tg-blur-panel))}.solid{background:var(--tg-surface)}.soft{background:var(--tg-surface-soft)}
	.none{padding:0}.compact{padding:var(--tg-space-4)}.comfortable{padding:clamp(var(--tg-space-4),2vw,var(--tg-space-6))}
</style>
