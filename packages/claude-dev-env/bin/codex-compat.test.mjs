import test from "node:test";
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildCommand, createHelpText, findPython, main } from "./codex-compat.mjs";

test("help describes both compatibility commands", () => {
    assert.match(createHelpText(), /materialize/);
    assert.match(createHelpText(), /bridge/);
});

test("missing required arguments returns a usage error", async () => {
    const messages = [];
    const originalWrite = process.stderr.write;
    process.stderr.write = (message) => messages.push(message);
    try { assert.equal(await main(["materialize"], { findPython: async () => "python" }), 2); } finally { process.stderr.write = originalWrite; }
    assert.equal(JSON.parse(messages.join("")).error.code, "invalid_command");
    assert.match(messages.join(""), /--source-root/);
});

test("unknown command returns structured error without running a child", async () => {
    const messages = [];
    let wasRun = false;
    const originalWrite = process.stderr.write;
    process.stderr.write = (message) => messages.push(message);
    try {
        const exitCode = await main(["unknown"], {
            findPython: async () => "python",
            runCommand: async () => { wasRun = true; return 0; },
        });
        assert.equal(exitCode, 2);
    } finally { process.stderr.write = originalWrite; }
    assert.equal(JSON.parse(messages.join("")).error.code, "invalid_command");
    assert.equal(wasRun, false);
});

test("commands use safe argv and forward dry-run and apply", () => {
    const dryRun = buildCommand("materialize", ["--source-root", "source root", "--target-root", "target;root"], "python");
    const apply = buildCommand("materialize", ["--source-root", "source", "--target-root", "target", "--apply"], "python");
    assert.equal(dryRun.arguments.at(-1), "target;root");
    assert.equal(apply.arguments.at(-1), "--apply");
});

test("bridge forwarding and child status use injected runners", async () => {
    let receivedCommand;
    const exitCode = await main(["bridge", "--surface", "TaskCreate", "--payload", '{"name":"ship","status":"pending"}'], {
        findPython: async () => "python-test",
        runCommand: async (command) => { receivedCommand = command; return 7; },
    });
    assert.equal(exitCode, 7);
    assert.equal(receivedCommand.executable, "python-test");
    assert.equal(receivedCommand.arguments.at(-1), '{"name":"ship","status":"pending"}');
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
        "CODEX_COMPAT_PYTHON",
        () => findPython(),
    );
    assert.equal(selectedName, "python");
});


test("no interpreter at the floor reports the floor and runs nothing", { skip: posixShellStubSkip }, async () => {
    let wasRun = false;
    const { exitCode, standardError } = await withStubPythons(
        { python3: "Python 3.9.0", python: "Python 3.10.4" },
        "CODEX_COMPAT_PYTHON",
        () => captureStandardError(() => main(["bridge", "--surface", "TaskCreate", "--payload", "{}"], {
            runCommand: async () => {
                wasRun = true;
                return 0;
            },
        })),
    );
    assert.equal(exitCode, 1);
    const errorRecord = JSON.parse(standardError).error;
    assert.equal(errorRecord.code, "python_unavailable");
    assert.match(errorRecord.message, /No usable Python 3\.11\+ interpreter found/);
    assert.equal(wasRun, false);
});


test("an explicit python override below the floor is still honored", { skip: posixShellStubSkip }, async () => {
    let receivedCommand;
    const exitCode = await withStubPythons(
        { python3: "Python 3.9.0" },
        "CODEX_COMPAT_PYTHON",
        (stubDirectory) => main(["bridge", "--python", path.join(stubDirectory, "python3"), "--surface", "TaskCreate", "--payload", "{}"], {
            runCommand: async (command) => {
                receivedCommand = command;
                return 0;
            },
        }),
    );
    assert.equal(exitCode, 0);
    assert.match(receivedCommand.executable, /python3$/);
});
