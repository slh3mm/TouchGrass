<script lang="ts">
	import { toasts, removeToast } from '$lib/toasts';
	let toastList: any[] = [];

	toasts.subscribe((value) => {
		toastList = value;
	});

	function getIconSvg(type: string) {
		switch (type) {
			case 'success':
				return `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>`;
			case 'error':
				return `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>`;
			case 'warning':
				return `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
			case 'info':
				return `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
			default:
				return `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
		}
	}
</script>

<div class="toast-region" aria-live="polite" aria-relevant="additions removals">
	{#each toastList as { type, message, id, color }}
		<div
			class="toast-card toast-{type} animate-in"
			class:profile-toast={Boolean(color)}
			style={color ? `--toast-profile-color:${color}` : ''}
			role="alert"
		>
			<div class="toast-content">
				<!-- Icon -->
				<div class="toast-icon">
					{@html getIconSvg(type)}
				</div>

				<!-- Message -->
				<div class="toast-message">
					<p>{message}</p>
				</div>

				<!-- Close Button -->
				<button
					class="toast-close"
					on:click={() => removeToast(id)}
					aria-label="Close notification"
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2.5"
							d="M6 18L18 6M6 6l12 12"
						></path>
					</svg>
				</button>
			</div>
		</div>
	{/each}
</div>

<style>
	@keyframes slide-in-from-right-5 {
		from {
			transform: translateX(1.25rem);
		}
		to {
			transform: translateX(0);
		}
	}

	@keyframes fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	.animate-in {
		animation:
			slide-in-from-right-5 0.3s ease-out,
			fade-in 0.3s ease-out;
	}
	.toast-region {
		position: fixed;
		z-index: var(--tg-layer-toast);
		top: calc(var(--tg-navbar-height) + 1rem);
		right: 1rem;
		display: grid;
		gap: 0.65rem;
		width: min(26rem, calc(100vw - 2rem));
		pointer-events: none;
	}
	.profile-toast {
		border-left: 8px solid var(--toast-profile-color);
	}
	.profile-toast .toast-icon {
		background: var(--toast-profile-color);
		color: #171717;
	}
	.toast-card {
		position: relative;
		width: 100%;
		min-height: 64px;
		padding: 0.75rem 3.75rem 0.75rem 0.75rem;
		border: 1px solid var(--tg-border);
		border-left: 6px solid var(--tg-info);
		border-radius: 16px;
		background: var(--tg-overlay-surface);
		color: var(--tg-ink);
		box-shadow: var(--tg-shadow-overlay);
		pointer-events: auto;
	}
	.toast-success {
		border-left-color: var(--tg-success);
	}
	.toast-error {
		border-left-color: var(--tg-danger);
	}
	.toast-warning {
		border-left-color: var(--tg-warning);
	}
	.toast-info {
		border-left-color: var(--tg-info);
	}
	.toast-content {
		display: grid;
		grid-template-columns: 40px minmax(0, 1fr);
		align-items: center;
		gap: 0.75rem;
		min-width: 0;
	}
	.toast-icon {
		display: grid;
		width: 40px;
		height: 40px;
		place-items: center;
		border-radius: 50%;
		background: var(--tg-selected);
		color: var(--tg-selected-text);
	}
	.toast-message {
		min-width: 0;
	}
	.toast-message p {
		margin: 0;
		font-size: 0.88rem;
		font-weight: 650;
		line-height: 1.4;
		overflow-wrap: anywhere;
	}
	.toast-close {
		position: absolute;
		top: 50%;
		right: 0.9rem;
		display: grid;
		width: 34px;
		height: 34px;
		min-height: 34px;
		padding: 0;
		place-items: center;
		border: 0;
		border-radius: 50%;
		background: transparent;
		color: var(--tg-ink-muted);
		transform: translateY(-50%);
		cursor: pointer;
	}
	.toast-close:hover {
		background: var(--tg-surface-soft);
		color: var(--tg-ink);
	}
	@media (max-width: 560px) {
		.toast-region {
			top: calc(var(--tg-navbar-height) + 0.65rem);
			right: 0.65rem;
			width: calc(100vw - 1.3rem);
		}
	}
</style>
