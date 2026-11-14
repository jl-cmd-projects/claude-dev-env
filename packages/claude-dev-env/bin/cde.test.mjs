import { EventEmitter } from "node:events";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import {
    buildLintCommand,
    buildVerifyCommand,
    createHelpText,
    findPython,
    main,
    pythonInterpreterNames,
    runLintCommand,
} from "./cde.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lintScriptPath = path.join(packageRoot, "scripts", "cde_lint.py");
const packageManifest = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
);


function createFakeChild() {
    const childProcess = new EventEmitter();
    childProcess.kill = (signalName) => {
        childProcess.lastSignalName = signalName;
    };
    return childProcess;
}


test("package exposes cde through its bin map", () => {
    assert.equal(packageManifest.bin.cde, "bin/cde.mjs");
});


test("help describes lint source modes", () => {
    const helpText = createHelpText();
    assert.match(helpText, /cde lint/);
    assert.match(helpText, /--files/);
    assert.match(helpText, /--staged/);
    assert.match(helpText, /--base/);
    assert.match(helpText, /--repository/);
    assert.match(helpText, /--text-as/);
    assert.match(helpText, /cde verify/);
    assert.match(helpText, /--manifest/);
});


test("prefers py then python on Windows and python3 then python on POSIX", () => {
    assert.deepEqual(pythonInterpreterNames("win32"), ["py", "python"]);
    assert.deepEqual(pythonInterpreterNames("linux"), ["python3", "python"]);
    assert.deepEqual(pythonInterpreterNames("darwin"), ["python3", "python"]);
});


test("falls back to the next interpreter when the first cannot run", () => {
    const selectedName = findPython(["py", "python"], (commandName) => commandName === "python");
    assert.equal(selectedName, "python");
});


test("forwards lint arguments to the python command without a shell", () => {
    const command = buildLintCommand("python-test", ["--files", "a.py", "--format", "json"]);
    assert.equal(command.executable, "python-test");
    assert.equal(command.arguments[0], lintScriptPath);
    assert.deepEqual(command.arguments.slice(1), ["--files", "a.py", "--format", "json"]);
});


test("forwards verification arguments to the authoritative python command", () => {
    const command = buildVerifyCommand("python-test", [
        "--manifest",
        "manifest with spaces.json",
        "--repo",
        "repo with spaces",
        "--base",
        "base-sha",
        "--output",
        "report.json",
    ]);
    assert.equal(command.executable, "python-test");
    assert.match(command.arguments[0], /scripts[\\/]local_verification[\\/]cli\.py$/);
    assert.deepEqual(command.arguments.slice(1), [
        "--manifest",
        "manifest with spaces.json",
        "--repo",
        "repo with spaces",
        "--base",
        "base-sha",
        "--output",
        "report.json",
    ]);
});


test("dispatches verify without changing forwarded arguments", async () => {
    let receivedCommand;
    const exitCode = await main(
        ["verify", "--python", "python-test", "--manifest", "manifest.json"],
        {
            findPython: async () => "unused-python",
            runCommand: async (command) => {
                receivedCommand = command;
                return 0;
            },
        },
    );
    assert.equal(exitCode, 0);
    assert.equal(receivedCommand.executable, "python-test");
    assert.match(receivedCommand.arguments[0], /local_verification[\\/]cli\.py$/);
    assert.deepEqual(receivedCommand.arguments.slice(1), ["--manifest", "manifest.json"]);
});


test("strips the launcher python override from forwarded arguments", async () => {
    let receivedCommand;
    const exitCode = await main(["lint", "--python", "python-test", "--staged"], {
        findPython: async () => "unused-python",
        runCommand: async (command) => {
            receivedCommand = command;
            return 0;
        },
    });
    assert.equal(exitCode, 0);
    assert.equal(receivedCommand.executable, "python-test");
    assert.deepEqual(receivedCommand.arguments, [lintScriptPath, "--staged"]);
});


test("unknown command returns invalid input without spawning", async () => {
    let wasRun = false;
    const messages = [];
    const originalWrite = process.stderr.write;
    process.stderr.write = (message) => messages.push(message);
    try {
        const exitCode = await main(["not-lint"], {
            findPython: async () => "python",
            runCommand: async () => {
                wasRun = true;
                return 0;
            },
        });
        assert.equal(exitCode, 2);
    } finally {
        process.stderr.write = originalWrite;
    }
    assert.equal(wasRun, false);
    assert.match(messages.join(""), /lint/);
});


test("missing python override value returns invalid input without spawning", async () => {
    let wasRun = false;
    const exitCode = await main(["lint", "--python"], {
        findPython: async () => "python",
        runCommand: async () => {
            wasRun = true;
            return 0;
        },
    });
    assert.equal(exitCode, 2);
    assert.equal(wasRun, false);
});


test("missing interpreter returns invalid input without spawning", async () => {
    let wasRun = false;
    const originalWrite = process.stderr.write;
    process.stderr.write = () => true;
    try {
        const exitCode = await main(["lint", "--staged"], {
            findPython: async () => undefined,
            runCommand: async () => {
                wasRun = true;
                return 0;
            },
        });
        assert.equal(exitCode, 2);
    } finally {
        process.stderr.write = originalWrite;
    }
    assert.equal(wasRun, false);
});


test("forwards child exit status", async () => {
    const childProcess = createFakeChild();
    const exitPromise = runLintCommand(
        { executable: "python", arguments: [lintScriptPath] },
        {
            runChild: () => childProcess,
        },
    );
    childProcess.emit("close", 3, null);
    assert.equal(await exitPromise, 3);
});


test("forwards SIGINT to the child and never enables a shell", async () => {
    const childProcess = createFakeChild();
    const processEmitter = new EventEmitter();
    let spawnOptions;
    const exitPromise = runLintCommand(
        { executable: "python", arguments: [lintScriptPath, "--staged"] },
        {
            processEmitter,
            runChild: (_executable, _allArguments, options) => {
                spawnOptions = options;
                return childProcess;
            },
        },
    );
    processEmitter.emit("SIGINT");
    childProcess.emit("close", 0, null);
    assert.equal(await exitPromise, 0);
    assert.equal(childProcess.lastSignalName, "SIGINT");
    assert.equal(spawnOptions.shell, false);
});


test("tolerates forwarding a signal to a dead child", async () => {
    const childProcess = createFakeChild();
    childProcess.kill = () => {
        throw new Error("child already exited");
    };
    const processEmitter = new EventEmitter();
    const exitPromise = runLintCommand(
        { executable: "python", arguments: [lintScriptPath] },
        { processEmitter, runChild: () => childProcess },
    );
    processEmitter.emit("SIGTERM");
    childProcess.emit("close", 0, null);
    assert.equal(await exitPromise, 0);
});


test("reports a child start failure as invalid input", async () => {
    const childProcess = createFakeChild();
    const processEmitter = new EventEmitter();
    const messages = [];
    processEmitter.stderr = { write: (message) => messages.push(message) };
    const exitPromise = runLintCommand(
        { executable: "missing-python", arguments: [lintScriptPath] },
        { processEmitter, runChild: () => childProcess },
    );
    childProcess.emit("error", new Error("not found"));
    assert.equal(await exitPromise, 2);
    assert.deepEqual(messages, ["Unable to start the policy linter.\n"]);
});


test("reports a synchronous child start failure as invalid input", async () => {
    const processEmitter = new EventEmitter();
    const messages = [];
    processEmitter.stderr = { write: (message) => messages.push(message) };
    const exitCode = await runLintCommand(
        { executable: "missing-python", arguments: [lintScriptPath] },
        {
            processEmitter,
            runChild: () => {
                throw new Error("not found");
            },
        },
    );
    assert.equal(exitCode, 2);
    assert.deepEqual(messages, ["Unable to start the policy linter.\n"]);
});


test("dispatches followup to the follow-up ledger command", async () => {
    let receivedCommand;
    const exitCode = await main(
        ["followup", "--python", "python-test", "list"],
        {
            findPython: async () => "unused-python",
            runCommand: async (command) => {
                receivedCommand = command;
                return 0;
            },
        },
    );
    assert.equal(exitCode, 0);
    assert.equal(receivedCommand.executable, "python-test");
    assert.match(receivedCommand.arguments[0], /followup_cli\.py$/);
    assert.deepEqual(receivedCommand.arguments.slice(1), ["list"]);
});


test("help names the followup command", () => {
    assert.match(createHelpText(), /cde <lint\|verify\|followup>/);
    assert.match(createHelpText(), /cde followup count/);
    assert.match(createHelpText(), /cde followup dedupe +Give each finding its own file, once/);
});


const posixShellStubSkip = process.platform === "win32" ? "the Python stubs are POSIX shell scripts" : false;


async function withStubPythons(versionByName, overrideEnvironmentName, action) {
    const stubDirectory = mkdtempSync(path.join(tmpdir(), "launcher-python-stub-"));
    for (const [eachName, eachVersion] of Object.entries(versionByName)) {
        const stubPath = path.join(stubDirectory, eachName);
        writeFileSync(stubPath, `#!/bin/sh\necho "${eachVersion}"\n`);
        chmodSync(stubPath, 0o755);
    }
    const originalPath = process.env.PATH;
    const originalOverride = process.env[overrideEnvironmentName];
    process.env.PATH = stubDirectory;
    delete process.env[overrideEnvironmentName];
    try {
        return await action(stubDirectory);
    } finally {
        process.env.PATH = originalPath;
        if (originalOverride !== undefined) process.env[overrideEnvironmentName] = originalOverride;
        rmSync(stubDirectory, { recursive: true, force: true });
    }
}


async function captureStandardError(action) {
    const allMessages = [];
    const originalWrite = process.stderr.write;
    process.stderr.write = (message) => {
        allMessages.push(String(message));
        return true;
    };
    try {
        const exitCode = await action();
        return { exitCode, standardError: allMessages.join("") };
    } finally {
        process.stderr.write = originalWrite;
    }
}


test("findPython skips a python3 below the floor and picks the next interpreter at the floor", { skip: posixShellStubSkip }, async () => {
    const selectedName = await withStubPythons(
        { python3: "Python 3.9.0", python: "Python 3.11.0" },
        "CDE_PYTHON",
        () => findPython(),
    );
    assert.equal(selectedName, "python");
});


test("no interpreter at the floor prints the floor and runs nothing", { skip: posixShellStubSkip }, async () => {
    let wasRun = false;
    const { exitCode, standardError } = await withStubPythons(
        { python3: "Python 3.9.0", python: "Python 3.10.4" },
        "CDE_PYTHON",
        () => captureStandardError(() => main(["lint", "--staged"], {
            runCommand: async () => {
                wasRun = true;
                return 0;
            },
        })),
    );
    assert.equal(exitCode, 2);
    assert.match(standardError, /No usable Python 3\.11\+ interpreter found/);
    assert.equal(wasRun, false);
});


test("an explicit python override below the floor is still honored", { skip: posixShellStubSkip }, async () => {
    let receivedCommand;
    const exitCode = await withStubPythons(
        { python3: "Python 3.9.0" },
        "CDE_PYTHON",
        (stubDirectory) => main(["lint", "--python", path.join(stubDirectory, "python3"), "--staged"], {
            runCommand: async (command) => {
                receivedCommand = command;
                return 0;
            },
        }),
    );
    assert.equal(exitCode, 0);
    assert.match(receivedCommand.executable, /python3$/);
});
