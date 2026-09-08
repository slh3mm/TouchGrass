type VisibilityCallback = () => void;

const callbacks = new WeakMap<Element, VisibilityCallback>();
let observer: IntersectionObserver | null = null;
let observedCount = 0;

function getObserver() {
	if (observer) return observer;
	observer = new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				if (!entry.isIntersecting) continue;
				const callback = callbacks.get(entry.target);
				observer?.unobserve(entry.target);
				callbacks.delete(entry.target);
				observedCount = Math.max(0, observedCount - 1);
				callback?.();
			}
			if (observedCount === 0) {
				observer?.disconnect();
				observer = null;
			}
		},
		{ rootMargin: '220px 0px' }
	);
	return observer;
}

export function observeVisibility(element: Element, callback: VisibilityCallback) {
	if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
		callback();
		return () => {};
	}

	callbacks.set(element, callback);
	getObserver().observe(element);
	observedCount += 1;

	return () => {
		if (!callbacks.has(element)) return;
		observer?.unobserve(element);
		callbacks.delete(element);
		observedCount = Math.max(0, observedCount - 1);
		if (observedCount === 0) {
			observer?.disconnect();
			observer = null;
		}
	};
}
