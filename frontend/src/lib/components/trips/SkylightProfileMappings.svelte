<script lang="ts">
	import { addToast } from '$lib/toasts';

	type Profile = { id: string; name: string; color: string; avatar?: string };
	type Mapping = {
		id: string;
		skylight_category_id: string;
		skylight_category_name: string;
		profile: string | null;
		profile_name: string | null;
		profile_color: string | null;
	};

	export let initialMappings: Mapping[] = [];
	export let profiles: Profile[] = [];

	let mappings = [...initialMappings];

	function csrf() {
		return document.cookie
			.split('; ')
			.find((row) => row.startsWith('csrftoken='))
			?.split('=')[1] || '';
	}

	async function updateMapping(mapping: Mapping, event: Event) {
		const profileId = (event.currentTarget as HTMLSelectElement).value;
		try {
			const response = await fetch(`/api/skylight/mappings/${mapping.id}/`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
				body: JSON.stringify({ profile: profileId || null })
			});
			const updated = await response.json().catch(() => null);
			if (!response.ok) throw new Error(updated?.error || updated?.detail || 'Could not update mapping.');
			mappings = mappings.map((item) => (item.id === mapping.id ? updated : item));
			addToast('success', `${mapping.skylight_category_name} mapping saved`);
		} catch (error) {
			addToast('error', error instanceof Error ? error.message : 'Could not update mapping.');
		}
	}
</script>

{#if mappings.length}
	<details class="mappings">
		<summary><strong>Who is who</strong><span>Calendar profile mapping</span></summary>
		<p>Skylight “Joint” maps only to the Joint TouchGrass profile.</p>
		<div class="mapping-grid">
			{#each mappings as mapping}
				<label>
					<span>{mapping.skylight_category_name}</span>
					<select value={mapping.profile || ''} on:change={(event) => updateMapping(mapping, event)}>
						<option value="">Ignore this category</option>
						{#each profiles as profile}<option value={profile.id}>{profile.name}</option>{/each}
					</select>
				</label>
			{/each}
		</div>
	</details>
{/if}

<style>
	.mappings{max-width:1500px;margin:0 auto;padding:1rem;border:1px solid var(--tg-border);border-radius:16px;background:var(--tg-surface-glass);box-shadow:var(--tg-shadow-card);color:var(--tg-ink)}
	.mappings summary{display:flex;align-items:center;justify-content:space-between;gap:1rem;cursor:pointer;list-style:none}
	.mappings summary::-webkit-details-marker{display:none}
	.mappings summary::after{content:'+';font-size:1.25rem;font-weight:500;color:var(--tg-ink-muted)}
	.mappings[open] summary::after{content:'−'}
	.mappings summary span,.mappings>p{color:var(--tg-ink-muted);font-size:.82rem}
	.mappings>p{margin:.65rem 0 0}
	.mapping-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem;margin-top:.8rem}
	label{display:grid;gap:.4rem;color:var(--tg-ink);font-weight:700}
	label span{font-size:.82rem}
	select{width:100%;box-sizing:border-box;padding:.75rem;border:1px solid var(--tg-border-strong);border-radius:10px;background:var(--tg-overlay-field);color:var(--tg-ink);font:inherit}
</style>
