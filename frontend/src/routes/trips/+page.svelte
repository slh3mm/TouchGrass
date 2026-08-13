<script lang="ts">
	import PlusIcon from '~icons/mdi/plus';
	import PencilIcon from '~icons/mdi/pencil';
	import CloseIcon from '~icons/mdi/close';
	import ArrowIcon from '~icons/mdi/arrow-right';
	import MapIcon from '~icons/mdi/map-outline';
	import CalendarIcon from '~icons/mdi/calendar-range';
	import { addToast } from '$lib/toasts';
	import type { PageData } from './$types';

	export let data: PageData;

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Trip = {
		id: string;
		title: string;
		start_date: string;
		end_date: string;
		notes: string;
		profiles: string[];
		profile_details: Profile[];
		planner_id: string;
		planner_url: string;
	};

	let trips: Trip[] = data.trips || [];
	let profiles: Profile[] = data.profiles || [];
	let editing: Trip | null = null;
	let editorOpen = false;
	let saving = false;
	let form = { title: '', start_date: '', end_date: '', notes: '', profiles: [] as string[] };

	const currentDate = new Date();
	const today = [
		currentDate.getFullYear(),
		String(currentDate.getMonth() + 1).padStart(2, '0'),
		String(currentDate.getDate()).padStart(2, '0')
	].join('-');

	$: currentTrips = trips
		.filter((trip) => trip.end_date >= today)
		.sort((a, b) => a.start_date.localeCompare(b.start_date));
	$: pastTrips = trips
		.filter((trip) => trip.end_date < today)
		.sort((a, b) => b.start_date.localeCompare(a.start_date));

	function csrf() {
		return document.cookie
			.split('; ')
			.find((row) => row.startsWith('csrftoken='))
			?.split('=')[1] || '';
	}

	function newTrip() {
		editing = null;
		form = { title: '', start_date: today, end_date: today, notes: '', profiles: [] };
		editorOpen = true;
	}

	function editTrip(trip: Trip) {
		editing = trip;
		form = {
			title: trip.title,
			start_date: trip.start_date,
			end_date: trip.end_date,
			notes: trip.notes,
			profiles: [...trip.profiles]
		};
		editorOpen = true;
	}

	function toggleProfile(id: string) {
		form.profiles = form.profiles.includes(id)
			? form.profiles.filter((value) => value !== id)
			: [...form.profiles, id];
	}

	function formatError(result: Record<string, unknown>) {
		if (typeof result.detail === 'string') return result.detail;
		const first = Object.values(result)[0];
		if (Array.isArray(first)) return String(first[0]);
		return 'Could not save this trip.';
	}

	async function save() {
		if (!form.title.trim() || !form.start_date || !form.end_date || !form.profiles.length) {
			addToast('error', 'Add a title, dates, and at least one profile.');
			return;
		}
		if (form.end_date < form.start_date) {
			addToast('error', 'The end date must be on or after the start date.');
			return;
		}

		saving = true;
		try {
			const response = await fetch(editing ? `/api/trips/${editing.id}/` : '/api/trips/', {
				method: editing ? 'PATCH' : 'POST',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: JSON.stringify({ ...form, title: form.title.trim() })
			});
			const result = await response.json();
			if (!response.ok) throw new Error(formatError(result));
			trips = editing
				? trips.map((trip) => (trip.id === result.id ? result : trip))
				: [...trips, result];
			editorOpen = false;
			addToast('success', editing ? 'Trip updated' : 'Trip and planner created');
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not save this trip.');
		} finally {
			saving = false;
		}
	}

	function formatDate(value: string) {
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		}).format(new Date(`${value}T12:00:00`));
	}

	function statusLabel(trip: Trip) {
		if (trip.start_date <= today && trip.end_date >= today) return 'Happening now';
		return trip.start_date === trip.end_date ? 'Day trip' : 'Coming up';
	}

	function profileGradient(trip: Trip) {
		const colors = trip.profile_details.map((profile) => profile.color).filter(Boolean);
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

<svelte:head><title>Trips - TouchGrass</title></svelte:head>
<svelte:window on:keydown={(event) => event.key === 'Escape' && (editorOpen = false)} />

<main>
	<header>
		<div>
			<span class="eyebrow">Shared journeys</span>
			<h1>Trips</h1>
			<p>Plan the details together, then keep the memories in one place.</p>
		</div>
		<button class="primary" type="button" on:click={newTrip}><PlusIcon />Add trip</button>
	</header>

	<div class="planner-callout">
		<div class="callout-icon"><MapIcon /></div>
		<div>
			<strong>The full AdventureLog planner is now connected.</strong>
			<p>Add places, a day-by-day itinerary, lodging, transportation, notes, checklists, maps, costs, and sharing inside any trip.</p>
		</div>
	</div>

	<section>
		<div class="section-heading">
			<div><span class="eyebrow">On the horizon</span><h2>Now &amp; next</h2></div>
			<strong>{currentTrips.length}</strong>
		</div>
		<div class="grid">
			{#each currentTrips as trip (trip.id)}
				<article style={`--trip-stripe:${profileGradient(trip)}`}>
					<div class="trip-status"><CalendarIcon />{statusLabel(trip)}</div>
					<div class="profiles" aria-label="Travelers">
						{#each trip.profile_details as profile}
							<i style={`--profile-color:${profile.color};--profile-ink:${profileText(profile.color)}`} title={profile.name}>{profile.avatar || profile.name[0]}</i>
						{/each}
					</div>
					<h3>{trip.title}</h3>
					<p class="dates">{formatDate(trip.start_date)} – {formatDate(trip.end_date)}</p>
					{#if trip.notes}<p class="notes">{trip.notes}</p>{/if}
					<div class="card-actions">
						<a class="planner-link" href={trip.planner_url || `/collections/${trip.planner_id}`}>Open planner <ArrowIcon /></a>
						<button class="edit" type="button" on:click={() => editTrip(trip)} aria-label={`Edit ${trip.title}`}><PencilIcon />Edit</button>
					</div>
				</article>
			{:else}
				<div class="empty"><MapIcon /><strong>No upcoming trips yet.</strong><span>Add one when inspiration strikes.</span></div>
			{/each}
		</div>
	</section>

	<section>
		<div class="section-heading">
			<div><span class="eyebrow">Where you have been</span><h2>Past trips</h2></div>
			<strong>{pastTrips.length}</strong>
		</div>
		<div class="grid">
			{#each pastTrips as trip (trip.id)}
				<article style={`--trip-stripe:${profileGradient(trip)}`}>
					<div class="trip-status"><CalendarIcon />Completed</div>
					<div class="profiles" aria-label="Travelers">
						{#each trip.profile_details as profile}
							<i style={`--profile-color:${profile.color};--profile-ink:${profileText(profile.color)}`} title={profile.name}>{profile.avatar || profile.name[0]}</i>
						{/each}
					</div>
					<h3>{trip.title}</h3>
					<p class="dates">{formatDate(trip.start_date)} – {formatDate(trip.end_date)}</p>
					{#if trip.notes}<p class="notes">{trip.notes}</p>{/if}
					<div class="card-actions">
						<a class="planner-link" href={trip.planner_url || `/collections/${trip.planner_id}`}>View memories <ArrowIcon /></a>
						<button class="edit" type="button" on:click={() => editTrip(trip)} aria-label={`Edit ${trip.title}`}><PencilIcon />Edit</button>
					</div>
				</article>
			{:else}
				<div class="empty"><CalendarIcon /><strong>No past trips yet.</strong><span>Finished trips will move here automatically.</span></div>
			{/each}
		</div>
	</section>
</main>

{#if editorOpen}
	<button class="backdrop" type="button" aria-label="Close trip editor" on:click={() => (editorOpen = false)}></button>
	<aside role="dialog" aria-modal="true" aria-label={editing ? 'Edit trip' : 'New trip'}>
		<button class="close" type="button" on:click={() => (editorOpen = false)} aria-label="Close"><CloseIcon /></button>
		<span class="eyebrow">Trip planner</span>
		<h2>{editing ? 'Edit trip' : 'New trip'}</h2>
		<p class="editor-intro">These basics create the planner. Open the trip afterward to build the itinerary.</p>
		<label>Trip name<input bind:value={form.title} placeholder="Summer in Italy" /></label>
		<div class="date-fields">
			<label>Starts<input type="date" bind:value={form.start_date} /></label>
			<label>Ends<input type="date" bind:value={form.end_date} min={form.start_date} /></label>
		</div>
		<fieldset>
			<legend>Who is going?</legend>
			<div class="choices">
				{#each profiles as profile}
					<button
						type="button"
						class:selected={form.profiles.includes(profile.id)}
						style={`--profile-color:${profile.color};--profile-ink:${profileText(profile.color)}`}
						on:click={() => toggleProfile(profile.id)}
						aria-pressed={form.profiles.includes(profile.id)}
					>
						<span>{profile.avatar || profile.name[0]}</span>{profile.name}
					</button>
				{/each}
			</div>
		</fieldset>
		<label>Notes<textarea rows="4" bind:value={form.notes} placeholder="The big-picture plan, flight ideas, or a favorite memory…"></textarea></label>
		<button class="primary save" type="button" disabled={saving} on:click={save}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create trip & planner'}</button>
	</aside>
{/if}

<style>
	main{min-height:100vh;padding:clamp(1.25rem,3vw,3rem);background:linear-gradient(135deg,var(--tg-canvas),var(--tg-canvas-deep));color:var(--tg-ink)}
	header,section,.planner-callout{max-width:1500px;margin:0 auto 1.75rem}header{display:flex;align-items:end;justify-content:space-between;gap:1rem}
	h1,h2,h3{font-family:var(--tg-font-display);font-weight:400}h1{margin:.1rem 0;font-size:clamp(3.4rem,6vw,5.5rem);line-height:.95}h2{margin:.1rem 0;font-size:clamp(1.8rem,3vw,2.4rem)}h3{margin:.5rem 0 .25rem;font-size:1.8rem;line-height:1.08}
	header p,.planner-callout p,.notes,.dates,.editor-intro{color:var(--tg-ink-muted)}header p{margin:.5rem 0 0;font-size:1.05rem}.eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.15em;text-transform:uppercase;color:var(--tg-ink-muted)}button,a{font:inherit}.primary,.edit,.close,.planner-link{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;min-height:44px;border-radius:999px;padding:.7rem 1rem;font-weight:750;text-decoration:none;cursor:pointer}.primary{border:0;background:var(--tg-action);color:var(--tg-action-text)}
	.planner-callout{display:flex;align-items:center;gap:1rem;padding:1rem 1.2rem;border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass);box-shadow:var(--tg-shadow-card)}.planner-callout p{margin:.2rem 0 0}.callout-icon{display:grid;flex:0 0 48px;height:48px;place-items:center;border-radius:50%;background:var(--tg-canvas-deep);color:var(--tg-action)}.callout-icon :global(svg){width:25px;height:25px}
	.section-heading{display:flex;align-items:end;justify-content:space-between;padding-bottom:.65rem;border-bottom:1px solid var(--tg-border)}.section-heading>strong{display:grid;min-width:42px;height:42px;place-items:center;border-radius:50%;background:var(--tg-surface);border:1px solid var(--tg-border);color:var(--tg-ink)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:1rem;margin-top:1rem}
	article,.empty{position:relative;overflow:hidden;min-height:245px;padding:1.3rem;border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass);box-shadow:var(--tg-shadow-card)}article::before{content:'';position:absolute;inset:0 0 auto;height:8px;background:var(--trip-stripe)}.trip-status{display:flex;align-items:center;gap:.35rem;width:max-content;margin-top:.2rem;padding:.35rem .6rem;border-radius:999px;background:var(--tg-canvas-deep);color:var(--tg-ink-muted);font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em}.trip-status :global(svg){width:15px}.profiles{position:absolute;top:1.2rem;right:1.2rem;display:flex}.profiles i{display:grid;width:34px;height:34px;margin-left:-7px;place-items:center;border:2px solid var(--tg-surface);border-radius:50%;background:var(--profile-color);color:var(--profile-ink);font-style:normal;font-weight:850;box-shadow:0 2px 7px rgb(0 0 0/.14)}.dates{margin:.15rem 0 .75rem;font-weight:650}.notes{display:-webkit-box;overflow:hidden;margin:.5rem 0;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2}.card-actions{display:flex;align-items:center;justify-content:space-between;gap:.6rem;margin-top:1.2rem}.planner-link{padding-left:0;color:var(--tg-action)}.planner-link:hover{text-decoration:underline}.edit{border:1px solid var(--tg-border-strong);background:var(--tg-surface);color:var(--tg-ink)}.empty{display:grid;min-height:190px;place-items:center;align-content:center;gap:.3rem;color:var(--tg-ink-muted);text-align:center}.empty :global(svg){width:32px;height:32px}.empty strong{color:var(--tg-ink)}
	.backdrop{position:fixed;inset:0;z-index:1090;width:100%;height:100%;border:0;background:rgb(20 18 22/.08)}aside{position:fixed;z-index:1100;top:0;right:0;width:min(580px,100%);height:100dvh;box-sizing:border-box;padding:clamp(1.4rem,4vw,2.4rem);overflow:auto;border-left:1px solid var(--tg-border);background:var(--tg-overlay-surface,#fff)!important;color:var(--tg-ink,#302f38)!important;opacity:1;isolation:isolate;box-shadow:-20px 0 60px rgb(36 30 25/.22)}aside h2{margin:.2rem 0;font-size:clamp(2.5rem,6vw,3.6rem)}.close{position:absolute;top:1rem;right:1rem;padding:.65rem;border:1px solid var(--tg-border);background:var(--tg-overlay-field,#f7f2e9);color:var(--tg-ink,#302f38)}label,legend{display:grid;gap:.45rem;margin:1.15rem 0;color:var(--tg-ink,#302f38);font-weight:750}input,textarea{width:100%;box-sizing:border-box;padding:.85rem;border:1px solid var(--tg-border-strong);border-radius:12px;background:var(--tg-overlay-field,#f7f2e9)!important;color:var(--tg-ink,#302f38)!important;opacity:1;outline:none}input::placeholder,textarea::placeholder{color:var(--tg-ink-muted,#68615b);opacity:1}input:focus,textarea:focus{border-color:var(--tg-action);box-shadow:0 0 0 3px color-mix(in srgb,var(--tg-action) 20%,transparent)}.date-fields{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}fieldset{margin:0;padding:0;border:0}.choices{display:flex;flex-wrap:wrap;gap:.55rem}.choices button{display:flex;align-items:center;gap:.45rem;min-height:46px;padding:.45rem .8rem;border:2px solid transparent;border-radius:999px;background:color-mix(in srgb,var(--profile-color) 68%,var(--tg-overlay-surface,#fff));color:var(--tg-ink,#302f38);cursor:pointer}.choices button span{display:grid;width:28px;height:28px;place-items:center;border-radius:50%;background:var(--profile-color);color:var(--profile-ink);font-weight:850}.choices button.selected{border-color:var(--tg-ink);box-shadow:0 0 0 2px var(--profile-color)}.save{width:100%;margin-top:.4rem}.save:disabled{cursor:wait;opacity:.65}
	@media(max-width:700px){header{align-items:start;flex-direction:column}.planner-callout{align-items:start}.date-fields{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.profiles{position:static;margin-top:.8rem}.profiles i{margin-right:-7px;margin-left:0}.card-actions{align-items:stretch;flex-direction:column}.planner-link,.edit{width:100%}}
</style>
