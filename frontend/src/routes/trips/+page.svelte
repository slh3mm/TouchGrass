<script lang="ts">
	import PlusIcon from '~icons/mdi/plus';
	import PencilIcon from '~icons/mdi/pencil';
	import CloseIcon from '~icons/mdi/close';
	import { addToast } from '$lib/toasts';
	import type { PageData } from './$types';
	export let data: PageData;
	type Profile = { id:string; name:string; color:string; avatar?:string };
	type Trip = { id:string; title:string; start_date:string; end_date:string; notes:string; profiles:string[]; profile_details:Profile[] };
	let trips: Trip[] = data.trips || [];
	let profiles: Profile[] = data.profiles || [];
	let editing: Trip | null = null;
	let open = false;
	let saving = false;
	let form = { title:'', start_date:'', end_date:'', notes:'', profiles:[] as string[] };
	$: today = new Date().toISOString().slice(0,10);
	$: futureTrips = trips.filter((trip) => trip.end_date >= today).sort((a,b) => a.start_date.localeCompare(b.start_date));
	$: pastTrips = trips.filter((trip) => trip.end_date < today).sort((a,b) => b.start_date.localeCompare(a.start_date));
	function csrf(){return document.cookie.split('; ').find((row)=>row.startsWith('csrftoken='))?.split('=')[1] || ''}
	function newTrip(){editing=null;form={title:'',start_date:today,end_date:today,notes:'',profiles:[]};open=true}
	function editTrip(trip:Trip){editing=trip;form={title:trip.title,start_date:trip.start_date,end_date:trip.end_date,notes:trip.notes,profiles:[...trip.profiles]};open=true}
	function toggleProfile(id:string){form.profiles=form.profiles.includes(id)?form.profiles.filter((value)=>value!==id):[...form.profiles,id]}
	async function save(){
		if(!form.title.trim() || !form.start_date || !form.end_date || !form.profiles.length) return addToast('error','Add a title, dates, and at least one profile.');
		saving=true;
		try{
			const response=await fetch(editing?`/api/trips/${editing.id}/`:'/api/trips/',{method:editing?'PATCH':'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(form)});
			const result=await response.json(); if(!response.ok) throw new Error(JSON.stringify(result));
			trips=editing?trips.map((trip)=>trip.id===result.id?result:trip):[...trips,result];open=false;addToast('success',editing?'Trip updated':'Trip created');
		}catch(error){addToast('error',error instanceof Error?error.message:'Could not save trip')}finally{saving=false}
	}
	function formatDate(value:string){return new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',year:'numeric'}).format(new Date(`${value}T12:00:00`))}
</script>
<svelte:head><title>Trips - TouchGrass</title></svelte:head>
<main><header><div><span>Household journeys</span><h1>Trips</h1><p>Plan what’s next and remember where you’ve been.</p></div><button class="primary" on:click={newTrip}><PlusIcon/>Add trip</button></header>
	<section><h2>Coming up</h2><div class="grid">{#each futureTrips as trip}<article style={`--trip-color:${trip.profile_details[0]?.color || '#4a90e2'}`}><div class="profiles">{#each trip.profile_details as profile}<i style={`background:${profile.color}`}>{profile.avatar || profile.name[0]}</i>{/each}</div><h3>{trip.title}</h3><p>{formatDate(trip.start_date)} – {formatDate(trip.end_date)}</p>{#if trip.notes}<small>{trip.notes}</small>{/if}<button class="edit" on:click={()=>editTrip(trip)}><PencilIcon/>Edit</button></article>{:else}<div class="empty">No future trips yet.</div>{/each}</div></section>
	<section><h2>Past trips</h2><div class="grid">{#each pastTrips as trip}<article style={`--trip-color:${trip.profile_details[0]?.color || '#4a90e2'}`}><div class="profiles">{#each trip.profile_details as profile}<i style={`background:${profile.color}`}>{profile.avatar || profile.name[0]}</i>{/each}</div><h3>{trip.title}</h3><p>{formatDate(trip.start_date)} – {formatDate(trip.end_date)}</p>{#if trip.notes}<small>{trip.notes}</small>{/if}<button class="edit" on:click={()=>editTrip(trip)}><PencilIcon/>Edit</button></article>{:else}<div class="empty">No past trips yet.</div>{/each}</div></section>
</main>
{#if open}<div class="backdrop" role="presentation" on:click={()=>open=false}></div><aside><button class="close" on:click={()=>open=false}><CloseIcon/></button><span>Trip planner</span><h2>{editing?'Edit trip':'New trip'}</h2><label>Trip name<input bind:value={form.title} placeholder="Summer in Italy"/></label><div class="dates"><label>Starts<input type="date" bind:value={form.start_date}/></label><label>Ends<input type="date" bind:value={form.end_date}/></label></div><fieldset><legend>Who’s going?</legend><div class="choices">{#each profiles as profile}<button class:selected={form.profiles.includes(profile.id)} style={`--profile-color:${profile.color}`} on:click={()=>toggleProfile(profile.id)}>{profile.avatar || profile.name[0]} {profile.name}</button>{/each}</div></fieldset><label>Notes<textarea rows="4" bind:value={form.notes} placeholder="Flights, ideas, memories…"></textarea></label><button class="primary save" disabled={saving} on:click={save}>{saving?'Saving…':editing?'Save changes':'Create trip'}</button></aside>{/if}
<style>
	main{min-height:100vh;padding:clamp(1rem,3vw,3rem);background:linear-gradient(135deg,var(--tg-canvas),var(--tg-canvas-deep));color:var(--tg-ink)}header,section{max-width:1500px;margin:0 auto 1.5rem}header{display:flex;align-items:end;justify-content:space-between;gap:1rem}h1,h2,h3{font-family:var(--tg-font-display);font-weight:400}h1{margin:.1rem 0;font-size:clamp(3rem,5vw,5rem)}h2{font-size:2rem}h3{margin:.4rem 0;font-size:1.6rem}p,small{color:var(--tg-ink-muted)}span{font-size:.7rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--tg-ink-muted)}button{cursor:pointer}.primary,.edit,.close{display:flex;align-items:center;gap:.4rem;min-height:44px;border:0;border-radius:999px;padding:.7rem 1rem}.primary{background:var(--tg-action);color:var(--tg-action-text);font-weight:700}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:1rem}article,.empty{padding:1.2rem;border:1px solid var(--tg-border);border-radius:var(--tg-radius-panel);background:var(--tg-surface-glass)}article{border-top:7px solid var(--trip-color)}.profiles{display:flex}.profiles i{display:grid;width:32px;height:32px;margin-right:-5px;place-items:center;border:2px solid white;border-radius:50%;font-style:normal;color:#25232a}.edit{margin-top:1rem;background:transparent;color:var(--tg-ink);border:1px solid var(--tg-border)}.empty{color:var(--tg-ink-muted)}.backdrop{position:fixed;inset:0;z-index:80;background:rgba(20,20,20,.35);backdrop-filter:blur(4px)}aside{position:fixed;z-index:90;top:0;right:0;width:min(560px,100%);height:100vh;padding:2rem;background:var(--tg-surface);color:var(--tg-ink);overflow:auto;box-shadow:var(--tg-shadow-overlay)}aside h2{font-size:3rem;margin:.2rem 0 1rem}.close{position:absolute;right:1rem;top:1rem;padding:.6rem;background:var(--tg-canvas-deep);color:var(--tg-ink)}label,legend{display:grid;gap:.4rem;margin:1rem 0;font-weight:700}input,textarea{width:100%;padding:.8rem;border:1px solid var(--tg-border-strong);border-radius:10px;background:var(--tg-surface);color:var(--tg-ink)}.dates{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}fieldset{border:0;padding:0}.choices{display:flex;flex-wrap:wrap;gap:.5rem}.choices button{min-height:44px;padding:.5rem .8rem;border:2px solid transparent;border-radius:999px;background:color-mix(in srgb,var(--profile-color) 50%,white);color:#25232a}.choices button.selected{border-color:var(--profile-color);box-shadow:0 0 0 2px var(--tg-ink)}.save{width:100%;justify-content:center}@media(max-width:650px){header{align-items:start;flex-direction:column}.dates{grid-template-columns:1fr}}
</style>
