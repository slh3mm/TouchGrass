<script lang="ts">
	// @ts-ignore
	import Calendar from '@event-calendar/core';
	// @ts-ignore
	import TimeGrid from '@event-calendar/time-grid';
	// @ts-ignore
	import DayGrid from '@event-calendar/day-grid';
	// @ts-ignore
	import Interaction from '@event-calendar/interaction';
	import { t } from 'svelte-i18n';

	export let events: Array<{ id: string; start: string; end: string; title: string; backgroundColor?: string; extendedProps?: any }> = [];
	export let onEventClick: ((event: any) => void) | null = null;
	export let height: string = 'auto';
	export let view: string = 'dayGridMonth';
	export let dayMaxEvents: number = 4;
	export let initialDate: string | Date | null = null;

	const plugins = [TimeGrid, DayGrid, Interaction];
	$: options = {
		view,
		events,
		date: initialDate || undefined,
		headerToolbar: { start: 'prev,next today', center: 'title', end: 'dayGridMonth,timeGridWeek,timeGridDay' },
		buttonText: { today: $t('calendar.today'), dayGridMonth: $t('calendar.month'), timeGridWeek: $t('calendar.week'), timeGridDay: $t('calendar.day') },
		height,
		eventDisplay: 'block',
		dayMaxEvents,
		moreLinkText: (num: number) => `+${num} more`,
		eventClick: (info: any) => onEventClick?.(info.event),
		eventDidMount: (info: any) => {
			const colors = info.event?.extendedProps?.profileColors || [];
			if (!colors.length) return;
			if (colors.length === 1) {
				info.el.style.background = colors[0];
				return;
			}
			const stops = colors.flatMap((color: string, index: number) => [
				`${color} ${(index / colors.length) * 100}%`,
				`${color} ${((index + 1) / colors.length) * 100}%`
			]);
			info.el.style.background = `linear-gradient(90deg, ${stops.join(', ')})`;
		},
		eventMouseEnter: (info: any) => (info.el.style.cursor = 'pointer'),
		themeSystem: 'standard'
	};
</script>

<div class="skylight-calendar"><Calendar {plugins} {options} /></div>

<style>
	.skylight-calendar { overflow: hidden; }
	:global(.skylight-calendar .ec) { --ec-border-color: rgba(68,62,56,.12); --ec-today-bg-color: rgba(255,177,74,.08); font-family: 'DM Sans', sans-serif; }
	:global(.skylight-calendar .ec-toolbar) { min-height: 76px; padding: .7rem .25rem; }
	:global(.skylight-calendar .ec-title) { font-family: 'Ovo', Georgia, serif; font-size: clamp(1.5rem, 2.2vw, 2.4rem); font-weight: 400; }
	:global(.skylight-calendar .ec-button) { border: 0; border-radius: 999px; padding: .55rem .85rem; background: rgba(57,55,69,.09); color: #393745; font-weight: 600; box-shadow: none; }
	:global(.skylight-calendar .ec-button:hover) { background: rgba(57,55,69,.16); }
	:global(.skylight-calendar .ec-button.ec-active) { background: #393745; color: #fff; }
	:global(.skylight-calendar .ec-header) { padding: .8rem .25rem; color: #746f68; font-size: .78rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
	:global(.skylight-calendar .ec-day) { min-height: 112px; background: rgba(255,255,255,.25); }
	:global(.skylight-calendar .ec-day:hover) { background: rgba(255,255,255,.54); }
	:global(.skylight-calendar .ec-day-head) { padding: .6rem .7rem .25rem; }
	:global(.skylight-calendar .ec-day-head a) { color: #37333a; font-family: 'Ovo', Georgia, serif; font-size: 1.7rem; text-decoration: none; }
	:global(.skylight-calendar .ec-today .ec-day-head a) { display: inline-grid; min-width: 34px; height: 34px; place-items: center; border-radius: 8px; background: #f5a742; color: white; }
	:global(.skylight-calendar .ec-event) { margin: 2px 5px; border: 0 !important; border-radius: 8px; padding: .28rem .42rem; color: #353238 !important; font-size: .78rem; font-weight: 600; box-shadow: none; }
	:global(.skylight-calendar .ec-event:hover) { filter: saturate(1.15) brightness(.97); }
	:global(.skylight-calendar .ec-more) { color: #625e66; font-size: .72rem; font-weight: 700; }
	@media (max-width: 650px) {
		:global(.skylight-calendar .ec-toolbar) { align-items: flex-start; flex-wrap: wrap; gap: .5rem; }
		:global(.skylight-calendar .ec-title) { order: -1; width: 100%; }
		:global(.skylight-calendar .ec-button) { padding: .45rem .55rem; font-size: .72rem; }
		:global(.skylight-calendar .ec-day) { min-height: 82px; }
		:global(.skylight-calendar .ec-day-head a) { font-size: 1.15rem; }
		:global(.skylight-calendar .ec-event) { margin-inline: 2px; padding: .2rem; font-size: .65rem; }
	}
</style>
