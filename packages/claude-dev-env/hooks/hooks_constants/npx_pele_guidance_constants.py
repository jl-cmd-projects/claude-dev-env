"""Names and guidance text for the npx_pele_guidance PreToolUse hook."""

from __future__ import annotations

__all__ = [
    "ABSENT_GUIDANCE_TEMPLATE",
    "ALL_NPM_EXEC_SUBCOMMANDS",
    "ALL_NPX_PROGRAM_NAMES",
    "ALL_PELE_ENTRY_PATH_PARTS",
    "COMMAND_INPUT_KEY",
    "FLAG_PREFIX",
    "INSTALLED_GUIDANCE_TEMPLATE",
    "NODE_MODULES_DIRECTORY_NAME",
    "NPM_PROGRAM_NAME",
    "NPX_PELE_FAILURE_SENTENCE",
    "PACKAGE_MANIFEST_NAME",
    "PACKAGE_VERSION_SEPARATOR",
    "PELE_PACKAGE_NAME",
    "PELE_TOOLS_DIRECTORY_NAME",
]

COMMAND_INPUT_KEY = "command"
ALL_NPX_PROGRAM_NAMES = ("npx", "npx.cmd")
NPM_PROGRAM_NAME = "npm"
ALL_NPM_EXEC_SUBCOMMANDS = ("exec", "x")
FLAG_PREFIX = "-"
PACKAGE_VERSION_SEPARATOR = "@"
PELE_PACKAGE_NAME = "pele"
PELE_TOOLS_DIRECTORY_NAME = "tools"
NODE_MODULES_DIRECTORY_NAME = "node_modules"
PACKAGE_MANIFEST_NAME = "package.json"
ALL_PELE_ENTRY_PATH_PARTS = ("dist", "pele.js")
NPX_PELE_FAILURE_SENTENCE = (
    "`npx pele` cannot run: pele is a library with no command, so npx stops with"
    ' "could not determine executable to run".'
)
INSTALLED_GUIDANCE_TEMPLATE = (
    NPX_PELE_FAILURE_SENTENCE
    + " Pele {version} is installed at {package_directory}. Render Mermaid from Node instead."
    " Save the diagram as a .mmd file, save this script as pele-render.mjs in the same folder, and"
    " run `node pele-render.mjs <diagram.mmd>`. It writes the SVG next to the diagram.\n\n"
    "```js\n"
    "import {{ readFileSync, writeFileSync }} from 'node:fs';\n"
    "import {{ pathToFileURL }} from 'node:url';\n\n"
    "const [inputPath] = process.argv.slice(2);\n"
    "const {{ render }} = await import(pathToFileURL({package_entry}).href);\n"
    "const {{ svg }} = render(readFileSync(inputPath, 'utf8'));\n"
    "const outputPath = inputPath.replace(/\\.mmd$/, '') + '.svg';\n"
    "writeFileSync(outputPath, svg);\n"
    "console.log('svg bytes:', svg.length);\n"
    "```"
)
ABSENT_GUIDANCE_TEMPLATE = (
    NPX_PELE_FAILURE_SENTENCE
    + " No usable Pele package was found at {package_directory}. This hook checks only the Claude home,"
    " so a copy kept elsewhere, such as one from an install run with --target, is not seen."
    " Render the Mermaid text in the playground at pele.run instead, which needs no install."
)
