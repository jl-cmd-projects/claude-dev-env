const path = require('node:path');

require(path.join(__dirname, '..', 'skills', 'visual-plan', 'runtime', 'visualplan.js'));

const RUNTIME_DIRECTORY = path.join(__dirname, '..', 'skills', 'visual-plan', 'runtime');

/** Returns a page that lints clean, with each part replaceable by name. */
function page(parts = {}) {
  const pick = (name, fallback) => (name in parts ? parts[name] : fallback);
  return `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Test Plan</title>
<link rel="stylesheet" href="visualplan.css">
<script src="visualplan.js" defer></script>
<body>
<vp-plan>
${pick('header', '<header><h1>Flaky test cleanup in CI</h1></header>')}
<vp-grid cols="Problem | Fix | Count">
  <vp-band tone="ok" mark="+" label="Reproduced">
${pick('rows', `    <vp-row>
      <vp-cell face="Clock drift"><vp-flow><script type="text/plain">a > b [bad]</script></vp-flow></vp-cell>
      <vp-cell face="Frozen clock"></vp-cell>
      <vp-cell count="12"></vp-cell>
    </vp-row>`)}
  </vp-band>
</vp-grid>
<vp-decisions>
${pick('asks', `  <vp-ask id="approve" top>
    <p>Approve this plan?</p>
    <label><input type="radio" name="approve" value="yes"> Approve</label>
    <label><input type="radio" name="approve" value="no"> Not yet</label>
  </vp-ask>
  <vp-ask id="retries">
    <p>Retry a failed test once?</p>
    <label><input type="radio" name="retries" value="no" checked> No retries</label>
    <label><input type="radio" name="retries" value="once"> Retry once</label>
  </vp-ask>`)}
</vp-decisions>
</vp-plan>
</body>
</html>
`;
}

module.exports = { VisualPlan: globalThis.VisualPlan, page, RUNTIME_DIRECTORY };
