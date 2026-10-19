# Visual contract

Give the viewer the changed behavior within a glance. Use the bundled visual style, and choose a composition for each PR.

Use a 1440 by 1020 SVG diagram with a cream background, dark teal text and icons, muted blue entry nodes, pale green processing nodes, lime outcomes, and orange conditional branches. Color must accompany a label or shape. A green route means implemented behavior. It says nothing about CI results.

Place the headline, one-sentence purpose, and before/after statements above the flow. Show the PR number and observed open or draft status. Keep the headline below 50 characters. Main labels normally fit two lines of 22 characters each. Use line icons in circles and diamonds for choices. Put the node center between x=60 and x=1380, y=200 and y=760. Keep labels and arrows apart.

Use the code's semantic structure. A linear dependency fix can have two lanes. A running sampler needs the next-pass loop and its finish transition. A compatibility change needs old and new input branches. A capture command needs repeated angles and a blocked outcome. Include only branches supported by source.

Use the lower strip for three brief interpretation notes when three fit the content. Every node opens a docked, nonmodal detail panel. Keep the map visible and usable beside it. At widths below 700 pixels, put the panel above the map. Give the map and panel independent scrolling within a bounded workspace.

Begin each detail view with a mini-diagram of that step's mechanism. Author its two to six labels from the reviewed code. Do not infer intermediate steps from the node title or force alternative branches into a sequence. Add related-step buttons from the main graph's neighboring nodes. Summary comparison and review notes also open a mini-diagram with navigation to the scene's nodes.

Put exact explanation and sources in a collapsed disclosure beneath the detail diagram. Reset the disclosure when changing detail views. Source excerpts and the original summary stay available in local output. Hosted output retains source links. Preserve focus on close and support Escape. Use a nonmodal complementary panel without a backdrop or a focus trap.

Scope CSS selectors and DOM queries to the widget root. Give SVG symbols and control IDs unique instance prefixes. A second widget on the same Page must not change the first widget or host styles.

Keep the widget in a light color scheme when its host uses a dark theme. Reset inherited text colors, button opacity, and text shadows within the root. Use explicit dark teal text and visible borders on light detail controls. Use dark teal focus outlines on light surfaces and lime focus outlines in the dark toolbar. Verify selected and unselected selector labels, close controls, and related-step labels under host theme overrides.

Verify the screenshot at the 1440 pixel desktop size with the panel both open and closed. Check every node, mini-diagram, related-step jump, disclosure reset, source link, title, and connection. Check the stacked panel on narrow screens. Verify two widget instances together and confirm host styles remain unchanged. Missing source or incomplete coverage must remain available in the review notes.

Use the shipping-flow hierarchy: compact navigation, one clear flow, and detail on demand. Keep the top dashboard to short PR selectors. A relevant flow-step card can contain a small chart. Its expansion shows the fuller chart, mechanism diagram, related steps, and collapsed evidence. Preserve the reference's line icons, restrained palette, spacious routing, and clear conditional paths. Avoid chart galleries, large preview tiles, and duplicated summary plots above the flow.
