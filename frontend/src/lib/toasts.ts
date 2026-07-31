import { writable } from 'svelte/store';

export const toasts = writable<{ type: any; message: any; id: number; duration?: number; color?: string }[]>([]);

export const addToast = (type: any, message: any, duration = 5000, color?: string) => {
	const id = Date.now();
	toasts.update((currentToasts) => {
		return [...currentToasts, { type, message, id, duration, color }];
	});
	setTimeout(() => {
		removeToast(id);
	}, duration);
};

export const removeToast = (id: number) => {
	toasts.update((currentToasts) => {
		return currentToasts.filter((toast) => toast.id !== id);
	});
};
