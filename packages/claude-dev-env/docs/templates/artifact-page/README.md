# Artifact page template

`template.html` is the reference page for any artifact an agent builds: a tracker, a board, a review page, a dashboard. Start from it, keep its structure and house style, and replace the sample data and the parts the new page does not need.

## What it demonstrates

| Part | How the template does it |
|---|---|
| One file | The page, its styles, its script and its data live in one HTML file. It opens with no build step and no companion files. |
| Data block | The sample data sits in `<script type="application/json" id="tracker-data">`. Swap that block for new data. Escape every `</` inside it as `<\/`. |
| Board first | A board of colored lanes shows where every item stands. Each lane chip jumps to its card. |
| Picture cards | Each item is a card with a status band, a four-step progress track, a next-step line, a folded summary, links and a copy button. |
| Filters | Two tabs, a project filter row and a search box narrow the list. The tab and the filter persist per viewer through `localStorage`, wrapped in `try`. |
| Themes | Every color is a token on `:root`. Dark values apply under `prefers-color-scheme: dark` and under `data-theme="dark"`. |
| Phone width | One column, at most 640px wide, with a 16px side gutter and no horizontal scroll at 400px. |
| Readable text | Text is 16px or larger and uses the full text color. Gray stays on lines and borders only. Text holds a 7:1 contrast ratio against its background. |
| Touch targets | Buttons and chips are 40px or taller, with a visible focus ring. |
| Copy fallback | The copy button uses the clipboard API and falls back to a hidden text area, then says when the copy is blocked. |

## House rules for a page built from it

- A control that sends anything selects first, and a separate Send button confirms. A second tap on a picked answer clears it.
- A page that needs extra files publishes them beside the page through the Artifact `files` field, and links them by relative path.
- A page that needs live data or saved answers declares the matching runtime capability. `localStorage` holds only per-viewer conveniences.
- Render the page at 400px in light and dark, and exercise every control, before publishing.
