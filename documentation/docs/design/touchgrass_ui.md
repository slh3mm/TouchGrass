# TouchGrass UI system

This document is the implementation contract for TouchGrass screens. New UI should reuse these rules before adding page-specific CSS.

## Product character

TouchGrass combines Skylight-like clarity with a travel scrapbook feel: oversized editorial headings, friendly profile colors, calm neutral surfaces, and controls that remain obvious on a wall display, desktop, or phone. The interface should feel spacious without hiding important actions below decorative copy.

## Source of truth

- Design tokens and shared primitives: `frontend/src/lib/styles/touchgrass-tokens.css`
- Authentication composition: `frontend/src/lib/styles/touchgrass-auth.css`
- App shell and destination navigation: `frontend/src/lib/components/Navbar.svelte`
- Profile selector: `frontend/src/lib/components/touchgrass/ProfileBar.svelte`
- Profile controls: `ProfileChip.svelte` and `ManageProfilesButton.svelte`
- Notifications: `frontend/src/lib/components/Toast.svelte`

Do not copy values out of the token file into route styles. Use the semantic token that describes the role, not a hard-coded color that happens to look correct in one theme.

## Semantic tokens

- Canvas and surfaces: `--tg-canvas`, `--tg-surface`, `--tg-surface-strong`, `--tg-surface-subtle`
- Text: `--tg-ink`, `--tg-ink-strong`, `--tg-ink-muted`
- Borders and focus: `--tg-border`, `--tg-border-strong`, `--tg-focus`
- Actions and states: `--tg-action`, `--tg-action-hover`, `--tg-selected`, `--tg-info`, `--tg-success`, `--tg-warning`, `--tg-danger`
- Layout: `--tg-navbar-height`, `--tg-content-width`, `--tg-page-gutter`
- Layers: `--tg-z-nav`, `--tg-z-overlay`, `--tg-z-popover`, `--tg-z-toast`
- Motion: `--tg-motion-fast`, `--tg-motion-normal`

All supported themes must define readable ink, border, and action combinations. DaisyUI colors should be consumed through the mapped TouchGrass tokens rather than referenced directly in feature CSS.

## Layout rules

1. Wrap routes in `.tg-page`, with `.tg-page-inner` for the centered content column.
2. Keep primary actions and profile selection near the page title; avoid introductory paragraphs that delay interaction.
3. Use `.tg-panel` for grouped content. Panels are opaque and bordered; overlays must never inherit page transparency.
4. On narrow screens, retain the same information hierarchy. Profile rows scroll horizontally and should not wrap into an unpredictable grid.
5. Maps may extend wider than text content, but their controls, search, and overlays must use the same tokens and z-index system.

## Navigation and selection

- The active top-level destination uses the current theme action color and a small status dot. It does not use a background pill or hover-only underline.
- The selected travel profile uses its own color plus a high-contrast outer ring. Other profiles remain visible because their visit data is still part of the shared view.
- The `+ Profiles` control is deliberately transparent and text-like. Do not turn it into a colored profile bubble.
- Profile selection edits the active profile immediately. Do not ask the user to select the same profile again inside an item action.

## Forms and overlays

- Inputs use `.tg-field`; buttons use `.tg-button` and an appropriate modifier.
- Every icon-only button requires an accessible label and a visible keyboard focus state.
- Drawers, dialogs, menus, and suggestion lists use opaque `--tg-surface-strong` backgrounds.
- Use `--tg-scrim` only when focus isolation is needed. A profile dropdown must not darken the page.
- Toast close buttons are positioned independently of message length so they never shift.

## Responsive and wall-display behavior

- Touch targets should be at least 44px on touch-oriented layouts.
- Large editorial headings scale with `clamp()` and must not force horizontal scrolling.
- The desktop shell favors a wide, glanceable layout; mobile stacks secondary information while preserving primary actions.
- Important counts remain near their page titles. Explanatory copy is secondary and may be shortened at mobile widths.

## Performance rules

- Lazy-loaded flags share one intersection observer; do not create one observer per card.
- Offscreen placeholders do not animate. The atlas initially renders a bounded batch and progressively appends the rest.
- Route loaders should fetch only data used by that route. Legacy destinations remain behind `features.legacyNavigation` in `frontend/src/lib/config.ts`.
- Prefer CSS and derived state over duplicate listeners. Heavy map modules stay route-scoped.
- The dev compose file enables polling by default because this workspace lives under OneDrive; override `VITE_USE_POLLING=false` only when native file watching is reliable.

## Review checklist

Before shipping a frontend change:

- Check the default light theme, a dark theme, and one colored theme.
- Check desktop and a narrow phone viewport.
- Verify active navigation, profile selection, hover, keyboard focus, disabled, loading, success, and error states.
- Open every affected dropdown, drawer, dialog, suggestion list, and toast; verify opacity, contrast, stacking, and close behavior.
- Confirm the page does not introduce horizontal overflow or a permanent scrollbar in a chip row.
- Run `svelte-check` and inspect the affected route in the browser.
