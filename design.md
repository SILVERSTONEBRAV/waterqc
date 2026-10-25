# QAD Shared Enterprise Design System

> Shared visual contract for the Django project and its applications. Palette tokens live in `core/static/core/css/theme.css`; theme selection and scheduling live in `core/static/core/js/theme.js`; compatibility mappings live in `core/static/core/css/ca-theme-bridge.css`.

## Design goals

- Use the familiar Django Admin blue and neutral surface palette as the default across the entire project.
- Keep every alternate palette within the same enterprise component, spacing, typography, and contrast system.
- Support continuous 24/7 use through automatic time-of-day and operating-system lighting preferences, with manual seasonal and lighting choices available.
- Keep app-specific CSS on semantic tokens instead of defining separate palettes.

## Theme choices

| Theme | Palette | Intended use |
|---|---|---|
| `auto` | Changes with local time and display preferences | Recommended for shared 24/7 workstations |
| `day` | Django Admin blue, white, and neutral gray | Standard enterprise daytime theme and default baseline |
| `dawn` | Warm neutral surfaces with muted amber | Early morning |
| `ocean` (`summer`) | Clear blue-green accent on bright cool surfaces | Bright daylight and summer palette |
| `emerald` (`spring`) | Restrained environmental green | Spring palette |
| `autumn` | Warm mineral surfaces and amber accent | Autumn palette |
| `winter` | Cool neutral surfaces with blue accent | Bright, reflective rooms and winter palette |
| `dusk` | Warm charcoal surfaces | Evening shifts |
| `night` | Neutral, low-glare dark surfaces | Night work and dark display preference |
| `aurora` | Cool midnight blue variation | Low-light environments |
| `emerald-dark` | Muted forest variation | Low-light environmental work |
| `high-contrast` (`contrast`) | High-contrast white and dark text | Glare, difficult displays, and accessibility needs |

Automatic mode follows the browser's local clock: dawn from 05:00–08:59, standard day from 09:00–16:59, dusk from 17:00–19:59, and night from 20:00–04:59. A dark operating-system preference selects a dark palette outside the dusk period; `prefers-contrast: more` selects high contrast. Manual selections remain active until the user cycles back to automatic mode. `ThemeEngine.resetAuto()` also returns to automatic mode.

The theme toggle cycles through automatic mode and all named palettes. The selection is shared by all applications on the same origin through `localStorage.qad_theme`.

## Typography and sizing

The shared font stack uses locally available system fonts (`system-ui`, Segoe UI, Roboto, and platform fallbacks), so the interface remains consistent without an external font request. Arabic text uses the Arabic system stack; identifiers and measurements use a monospace stack.

| Token | Size | Use |
|---|---:|---|
| `--font-size-2xs` | 11 px | Dense metadata only |
| `--font-size-xs` | 12 px | Labels, table headings, and status pills |
| `--font-size-sm` | 13 px | Controls, tabs, and compact table content |
| `--font-size-body` | 14 px | Default body copy |
| `--font-size-md` | 15 px | Panel headings and emphasized copy |
| `--font-size-lg` | 16 px | Section headings |
| `--font-size-xl` | 20 px | Page section titles |
| `--font-size-2xl` | 24 px | Page titles and key metrics |
| `--font-size-3xl` | 28 px | Large display headings |

Use `--font-weight-*`, `--line-height-*`, and `--tracking-*` for consistent hierarchy. Body copy uses a 1.5 line height; headings use the shared tight line height. Avoid reducing essential data below the 12 px label size.

## Shared semantic tokens

| Area | Tokens |
|---|---|
| Surfaces | `--theme-bg`, `--theme-surface`, `--theme-surface-strong`, `--theme-surface-muted` |
| Text | `--theme-text`, `--theme-text-secondary`, `--theme-muted` |
| Borders | `--theme-border`, `--theme-border-strong` |
| Actions | `--theme-accent`, `--theme-accent-hover`, `--theme-accent-soft`, `--theme-focus-ring` |
| Status | `--color-success`, `--color-warning`, `--color-danger`, `--color-info` |
| Typography | `--font-sans`, `--font-heading`, `--font-mono`, `--font-arabic`, `--font-size-*` |

Prefer shared components such as `.qad-panel`, `.qad-kpi`, `.qad-tab`, `.qad-pill`, `.qad-btn`, `.qad-table`, `.qad-input`, and `.qad-select`. The bridge also maps legacy CA, Bootstrap, and dashboard aliases to the same palette tokens.

```css
.my-panel {
  background: var(--theme-surface);
  color: var(--theme-text);
  border: 1px solid var(--theme-border);
}
```

Avoid hard-coded palette colors for surfaces, text, borders, and accents. Extend the shared semantic tokens when a new component needs a reusable role.

## Loading contract

Shared app shells, standalone dashboards, and the login page load `theme.js` before first paint, then `theme.css`; app shells load `ca-theme-bridge.css` after their app styles. The PWA manifests use the standard palette for their launch surface and browser chrome. Keep these shared references and cache versions aligned when changing the design system. Django Admin keeps its native page layout and uses the shared palette plus the customized project header.

## Review checklist

- [ ] Uses the shared system font stack and typography tokens.
- [ ] Uses semantic tokens for surfaces, text, borders, focus, and accents.
- [ ] Reads clearly in day, dusk, night, and high-contrast modes.
- [ ] Keeps controls, tables, labels, and status indicators at the shared type scale.
- [ ] Does not add an application-specific palette definition.
