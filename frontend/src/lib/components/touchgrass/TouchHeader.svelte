<script lang="ts">
	export let eyebrow = '';
	export let title: string;
	export let subtitle = '';
	export let level: 1 | 2 = 1;
</script>
<header><div>{#if eyebrow}<span>{eyebrow}</span>{/if}{#if level === 1}<h1>{title}</h1>{:else}<h2>{title}</h2>{/if}{#if subtitle}<p>{subtitle}</p>{/if}</div><div class="actions"><slot name="actions" /></div></header>
<style>
	header{display:flex;align-items:end;justify-content:space-between;gap:var(--tg-space-6)}h1,h2{margin:var(--tg-space-1) 0 0;color:var(--tg-ink-strong);font-family:var(--tg-font-display);font-weight:400;line-height:1.04;letter-spacing:-.02em}h1{font-size:clamp(3rem,5vw,6rem)}h2{font-size:clamp(2rem,3vw,3rem)}p{max-width:65ch;margin:var(--tg-space-2) 0 0;color:var(--tg-ink-muted)}span{color:var(--tg-ink-muted);font-size:.7rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase}.actions:empty{display:none}@media(max-width:700px){header{align-items:start}}
</style>
