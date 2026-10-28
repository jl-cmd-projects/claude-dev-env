"""Pattern, names, and guidance text for the npx_pele_guidance PreToolUse hook."""

from __future__ import annotations

import re

__all__ = [
    "ABSENT_GUIDANCE_TEMPLATE",
    "ALL_PELE_ENTRY_PATH_PARTS",
    "COMMAND_INPUT_KEY",
    "INSTALLED_GUIDANCE_TEMPLATE",
    "NODE_MODULES_DIRECTORY_NAME",
    "NPX_PELE_COMMAND_PATTERN",
    "PACKAGE_MANIFEST_NAME",
    "PELE_PACKAGE_NAME",
    "PELE_TOOLS_DIRECTORY_NAME",
]

NPX_PELE_COMMAND_PATTERN = re.compile(
    r"(?:^|[;&|(\n])\s*(?:npx(?:\.cmd)?|npm\s+(?:exec|x))\s+(?:-\S+\s+)*pele(?:@\S*)?(?=$|[\s;&|)])"
)
COMMAND_INPUT_KEY = "command"
PELE_PACKAGE_NAME = "pele"
PELE_TOOLS_DIRECTORY_NAME = "tools"
NODE_MODULES_DIRECTORY_NAME = "node_modules"
PACKAGE_MANIFEST_NAME = "package.json"
ALL_PELE_ENTRY_PATH_PARTS = ("dist", "pele.js")
INSTALLED_GUIDANCE_TEMPLATE = (
    "`npx pele` cannot run: pele is a library with no command, so npx stops with"
    ' "could not determine executable to run". Pele {version} is installed at'
    " {package_directory}. Render Mermaid from Node instead. Save the diagram as"
    " chain.mmd, save this script as render.mjs in the same folder, and run"
    " `node render.mjs`. It writes chain.svg.\n\n"
    "```js\n"
    "import {{ readFileSync, writeFileSync }} from 'node:fs';\n"
    "import {{ pathToFileURL }} from 'node:url';\n\n"
    "const {{ render }} = await import(pathToFileURL({package_entry}).href);\n"
    "const {{ svg }} = render(readFileSync('chain.mmd', 'utf8'));\n"
    "writeFileSync('chain.svg', svg);\n"
    "console.log('svg bytes:', svg.length);\n"
    "```"
)
ABSENT_GUIDANCE_TEMPLATE = (
    "`npx pele` cannot run: pele is a library with no command, so npx stops with"
    ' "could not determine executable to run". Pele is not installed at'
    " {package_directory}, so no local copy can render this diagram. Render the"
    " Mermaid text in the playground at pele.run instead, which needs no install."
    " Auto mode denies `npm install pele`, so skip that step."
)
