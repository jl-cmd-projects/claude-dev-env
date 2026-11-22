"""Judge whether one shell step leaves the head, the branch and the repository as the gate read them.

::

    cd ../a, echo hi 2>&1, cat body.md       -> a settled step before a create
    git push ..., X=1, ./cat, echo > f        -> not settled
    cd .git, popd, echo "${T@P}"              -> not settled
    X=1 gh pr create --fill > pr.txt          -> a settled create
    env gh pr create, gh pr create > .git/x   -> not settled
    tail -5, tee out.txt                      -> a settled reader after a create in a pipeline

The rule lists what is settled, and every other shape is not. The folder
walk in ``create_folders`` calls these checks on each segment it reads, in
any nesting, and on the whole command text for process substitution, for
array subscript expansion and for heredoc bodies bash expands. It also
calls the unsettled expansion check on each level of text it reads.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import create_arguments
from blocking.merge_review_gate_parts.quoted_lines import expansion_marked_line, quote_aware_lines
from hooks_constants.followup_pr_dedupe_constants import WINDOWS_EXECUTABLE_SUFFIX
from hooks_constants.merge_review_gate_constants import (
    ALL_EXPANSION_OPENER_CHARACTERS,
    ALL_IGNORED_FOLDER_NAME_END_CHARACTERS,
    ALL_MANAGED_LAUNCHER_PATH_PARTS,
    FOLDER_PATH_SEPARATOR_PATTERN,
    FOLDER_STACK_ROTATION_PREFIX,
    ALL_OUTPUT_REDIRECT_OPERATORS,
    ALL_REDIRECT_OPERATORS,
    HOME_FOLDER,
    HOME_FOLDER_PREFIX,
    ALL_SETTLED_BEFORE_PROGRAMS,
    ALL_SETTLED_FOLDER_PROGRAMS,
    ALL_SETTLED_PIPE_READER_PROGRAMS,
    ALL_SETTLED_SUBSTITUTION_PROGRAMS,
    APPEND_ASSIGNMENT_MARK,
    ASSIGNMENT_SEPARATOR,
    ALL_UNSETTLED_WRITE_TARGET_CHARACTERS,
    CARRIAGE_RETURN,
    END_OF_OPTIONS_WORD,
    FILE_DESCRIPTOR_COPY_OPERATOR,
    FILE_DESCRIPTOR_COPY_TARGET_PATTERN,
    FUNCTION_DEFINITION_TOKEN,
    GH_PROGRAM_NAME,
    GIT_FOLDER_NAME,
    HEREDOC_OPERATOR_TOKEN,
    HOME_EXPANSION_MARK,
    HOME_VARIABLE_PATTERN,
    IS_POSIX_TOKENIZATION,
    LINE_FEED,
    LONE_LAUNCHER_CREATE_WORD,
    LONE_LAUNCHER_LEAD_WIDTH,
    LONE_LAUNCHER_PYTHON_PATTERN,
    MANAGED_LAUNCHER_HOME_PREFIX_PATTERN,
    MARKED_MANAGED_LAUNCHER_WORD,
    NULL_DEVICE_PATH,
    OPTION_PREFIX,
    PRINTF_PROGRAM_NAME,
    PRINTF_VARIABLE_OPTION_PREFIX,
    PROCESS_SUBSTITUTION_PATTERN,
    SUBSCRIPT_EXPANSION_PATTERN,
    TEE_PROGRAM_NAME,
    UNSETTLED_EXPANSION_PATTERN,
    UNSETTLED_PREFIX_NAME_PATTERN,
)
from hooks_constants.piped_pytest_blocker_constants import (
    HEREDOC_ESCAPE_GROUP,
    HEREDOC_OPENER_PATTERN,
    HEREDOC_QUOTE_GROUP,
)
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_pipeline import (
    PendingHeredoc,
    closes_the_heredoc,
    operator_aware_tokens,
    pending_heredoc_opened_by,
)
from hooks_constants.shell_command_segments import LEADING_ASSIGNMENT_PATTERN, token_basename
from hooks_constants.shell_command_substitution_constants import (
    DOUBLE_QUOTE,
    SHELL_ESCAPE_CHARACTER,
    SINGLE_QUOTE,
)
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


def holds_process_substitution(text: str) -> bool:
    """Return whether a command text holds ``<(`` or ``>(`` anywhere, quoted or not.

    ::

        cat <(git push ...) && gh pr create   -> True
        gh pr create --fill > >(git push ...)  -> True
        gh pr create --fill                    -> False

    Args:
        text: The whole shell command text.

    Returns:
        True when either opener appears.
    """
    return PROCESS_SUBSTITUTION_PATTERN.search(text) is not None


def holds_subscript_expansion(text: str) -> bool:
    """Return whether a command text holds an array subscript expansion anywhere, quoted or not.

    ::

        echo ${b[X]}; gh pr create        -> True
        gh pr create --title "${#b[0]}"   -> True
        echo ${b} $b[X]; gh pr create     -> False

    Bash reads the subscript of an indexed array as arithmetic. Arithmetic
    reads a variable's value as an expression, and a ``$(...)`` in that
    value runs, so a subscript can run a program the gate never sees.

    Args:
        text: The whole shell command text.

    Returns:
        True when some ``${name[`` opener appears.
    """
    return SUBSCRIPT_EXPANSION_PATTERN.search(text) is not None


def holds_unsettled_expansion(text: str) -> bool:
    """Return whether bash runs an expansion the gate cannot read somewhere in one level of shell text.

    ::

        gh pr create --title "$[PATH=0]"            -> True, PATH is 0 when gh starts
        echo $((HOME=1)); gh pr create              -> True
        gh pr create --title "${BASH_COMMAND@P}"    -> True, a prompt expansion runs $(...)
        gh pr create --title "${GH_REPO:=x}"        -> True, an assignment
        gh pr create --title '${BASH_COMMAND@P}'    -> False, single quotes keep it as written
        gh pr create --title "${T}" --body "${B:-x}" -> False

    A braced expansion is settled only as ``${name}`` or as ``${name:-word}``,
    ``${name:+word}`` or ``${name:?word}``, with or without the colon, where
    the name holds only letters, digits and underscores. Every other braced
    form, such as ``@P``, ``:=``, ``${!name}``, ``${#name}``, an offset, a
    pattern edit or a case change, counts, and so do ``$[`` and ``$((``.
    Arithmetic can assign PATH or HOME, and a prompt expansion runs text
    the gate never sees.

    The text is read in the lines bash reads, with heredoc bodies dropped,
    and an opener counts anywhere outside single quotes and backslash
    escapes. A text whose quotes do not close counts at any such opener.
    Each level of nesting, such as ``bash -c`` text, needs its own call.

    Args:
        text: One level of shell text.

    Returns:
        True when some such opener sits where bash expands it.
    """
    all_lines = quote_aware_lines(text)
    if all_lines is None:
        return UNSETTLED_EXPANSION_PATTERN.search(text) is not None
    return any(_holds_unsettled_expansion_in_line(each_line) for each_line in all_lines)


def _holds_unsettled_expansion_in_line(line: str) -> bool:
    quote = ""
    index = 0
    while index < len(line):
        character = line[index]
        if quote == SINGLE_QUOTE:
            quote = "" if character == SINGLE_QUOTE else quote
        elif character == SHELL_ESCAPE_CHARACTER:
            index += 1
        elif UNSETTLED_EXPANSION_PATTERN.match(line, index) is not None:
            return True
        elif character == DOUBLE_QUOTE:
            quote = "" if quote == DOUBLE_QUOTE else DOUBLE_QUOTE
        elif character == SINGLE_QUOTE and not quote:
            quote = SINGLE_QUOTE
        index += 1
    return False


def holds_expanding_heredoc(text: str) -> bool:
    """Return whether a command text holds a heredoc whose body bash expands and that holds ``$`` or a backtick.

    ::

        cat <<EOF / $(git push) / EOF        -> True
        cat <<'EOF' / $(git push) / EOF      -> False, a quoted delimiter
        cat <<EOF / plain text / EOF         -> False

    A delimiter with a quote or a backslash keeps the body as written. The
    body runs to the line that closes it, or to the end of the text.

    Args:
        text: The whole shell command text, heredoc bodies included.

    Returns:
        True when some such body holds ``$`` or a backtick.
    """
    for each_opener in HEREDOC_OPENER_PATTERN.finditer(text):
        if each_opener.group(HEREDOC_QUOTE_GROUP) or each_opener.group(HEREDOC_ESCAPE_GROUP):
            continue
        pending_heredoc = pending_heredoc_opened_by(each_opener.group(0))
        body_start = text.find(LINE_FEED, each_opener.end())
        if pending_heredoc is not None and body_start >= 0:
            if _is_expanding_body(text[body_start + 1 :], pending_heredoc):
                return True
    return False


def _is_expanding_body(text_after_opener_line: str, pending_heredoc: PendingHeredoc) -> bool:
    for each_line in text_after_opener_line.split(LINE_FEED):
        if closes_the_heredoc(each_line.rstrip(CARRIAGE_RETURN), pending_heredoc):
            return False
        if not ALL_EXPANSION_OPENER_CHARACTERS.isdisjoint(each_line):
            return True
    return False


def is_settled_step(
    all_tokens: list[str], is_in_create_words: bool, has_expanding_heredoc: bool
) -> bool:
    """Return whether a step that runs before a create, or in its words, leaves the head as read.

    ::

        cd ../a, pushd x, echo hi 2>/dev/null, head -n1 f         -> True
        cd "$X", ./cat, printf -v NAME x, echo a > f, X=1         -> False
        cd .git/refs, cd x.git, cd -, cd, popd, pushd +1          -> False
        printf $(echo -v) X y, printf ${Z:--v} X y, echo $X       -> False
        cat f, inside --body "$(...)"                             -> True
        head -n1 f, inside --body "$(...)"                        -> False

    Before a create, a step is ``cd`` or ``pushd`` with one plain folder word,
    or a bare-named ``cat``, ``echo``, ``printf``, ``head`` or ``tail``. The
    folder word, read past any redirect, starts with no ``-`` or ``+``, holds
    no ``$``, backtick, glob character or brace, and no ``~`` but a leading
    ``~`` or ``~/``, and no part of its path, in any case and with
    trailing dots or spaces dropped, ends in ``.git``, so a later write to
    ``HEAD`` or ``config`` lands in no repository folder. In the create's own
    words only ``cat``, ``echo``
    and ``printf`` run. The words bash reads for options, up to the first
    plain word that does not start with ``-`` or up to ``--``, hold no ``$``
    or backtick, so no expansion can turn into ``printf -v NAME``. A step
    that opens a substitution keeps its trailing ``$`` as a word here.
    Output goes only to /dev/null or a descriptor copy such as ``2>&1``.
    An empty step runs nothing.

    Args:
        all_tokens: The words of one simple command.
        is_in_create_words: True when the step runs in a substitution in a create's words.
        has_expanding_heredoc: True when the command holds a heredoc body bash expands.

    Returns:
        True when the step is one of the settled shapes.
    """
    if not all_tokens:
        return True
    if _holds_unsettled_token(all_tokens, has_expanding_heredoc):
        return False
    program = unquoted_token(all_tokens[0])
    all_programs = (
        ALL_SETTLED_SUBSTITUTION_PROGRAMS if is_in_create_words else ALL_SETTLED_BEFORE_PROGRAMS
    )
    if program not in all_programs or not _are_plain_option_words(all_tokens[1:]):
        return False
    if program in ALL_SETTLED_FOLDER_PROGRAMS and not _is_settled_folder_target(all_tokens[1:]):
        return False
    if program == PRINTF_PROGRAM_NAME and any(
        unquoted_token(each).startswith(PRINTF_VARIABLE_OPTION_PREFIX) for each in all_tokens[1:]
    ):
        return False
    return all(each_target == NULL_DEVICE_PATH for each_target in _write_targets(all_tokens))


def is_settled_create_segment(all_tokens: list[str], has_expanding_heredoc: bool) -> bool:
    """Return whether the words of a create's own segment leave the head as read.

    ::

        gh pr create --fill, X=1 gh pr create --fill          -> True
        gh pr create --fill 2>&1 > pr.txt                       -> True
        X=$(git push) gh pr create, GIT_DIR=x gh pr create      -> False
        env gh pr create, command gh pr create, then gh ...     -> False
        gh pr create --fill > .git/HEAD                         -> False
        ./gh pr create, /tmp/x/python3 pull_request.py create   -> False
        python3 <home>/.agents/skills/pull-request/scripts/pull_request.py create -> True
        uv run <home>/.agents/.../pull_request.py create                    -> False
        uv run ./pull_request.py create, python3 /x/pull_request.py create -> False
        X=1 python3 <home>/.agents/.../pull_request.py create              -> False
        env python3 <home>/.agents/..., nice <home>/.agents/...            -> False

    The first word that is not an assignment is the program, with no
    wrapper or compound word before it. A gh program is a bare word with no
    ``/`` or ``\\``, which bash finds on PATH. Its assignments hold values
    with no ``$`` or backtick, and names that are not ``GIT_``, ``LD_``,
    ``DYLD_``, ``XDG_``, ``UV_``, ``PYTHON``, ``HOME``, ``PATH``, or a
    ``GH_`` name but the repository one. Names match in any case, since
    Windows reads ``gh_repo`` as ``GH_REPO``, and only the upper case
    ``GH_REPO`` is kept.

    Any other create runs ``pull_request.py`` with no assignment before it.
    Its script word must be the managed launcher, alone or after a bare
    ``python`` or ``python3``, so no file in the working folder and no
    variable such as ``VIRTUAL_ENV`` picks the interpreter, and a script
    that could move the head after the gate read it never counts. A ``uv
    run`` lead reads ``pyproject.toml``, ``uv.toml``, ``.python-version`` and
    ``.venv`` from the working folder, so it never counts. Its home is
    written out only by ``with_launcher_home_written``, so a ``~`` left in
    the word never counts. Output goes only to /dev/null, a descriptor
    copy, or a plain path outside ``.git``: one with no ``$``, backtick,
    glob character, brace or ``~``.

    Args:
        all_tokens: The words of the segment that runs the create.
        has_expanding_heredoc: True when the command holds a heredoc body bash expands.

    Returns:
        True when the create's own words are settled.
    """
    if (
        _holds_unsettled_token(all_tokens, has_expanding_heredoc)
        or create_arguments(all_tokens) is None
    ):
        return False
    program_index = _program_index(all_tokens)
    if program_index >= len(all_tokens):
        return False
    if not all(_is_settled_prefix(each) for each in all_tokens[:program_index]):
        return False
    program_token = unquoted_token(all_tokens[program_index])
    program_word = token_basename(program_token).removesuffix(WINDOWS_EXECUTABLE_SUFFIX)
    if program_word != segment_program_and_arguments(all_tokens)[0]:
        return False
    if program_word.lower() == GH_PROGRAM_NAME:
        if FOLDER_PATH_SEPARATOR_PATTERN.search(program_token):
            return False
    elif program_index or not _runs_managed_launcher(all_tokens):
        return False
    return all(_is_kept_write_target(each_target) for each_target in _write_targets(all_tokens))


def with_managed_launcher_home(command: str) -> str:
    """Return the command with a home prefix on the managed launcher path written out as the home folder.

    Bash turns a leading ``~`` or ``$HOME`` into the home folder, and the
    gate runs with the same home::

        python3 ~/.agents/skills/pull-request/scripts/pull_request.py create ...
            -> python3 <home>/.agents/skills/pull-request/scripts/pull_request.py create ...
        $HOME/.agents/skills/pull-request/scripts/pull_request.py create ... -> <home>/.agents/...
        python3 ~/x/pull_request.py create ..., ~other/.agents/..., '~'/.agents/... -> unchanged

    Only the script word of the launcher changes, so any other ``~`` or
    ``$`` still makes the command not lone.

    Args:
        command: The shell command text.

    Returns:
        The command with the launcher's home prefix written out.
    """
    home_folder = shlex.quote(Path.home().as_posix())
    return MANAGED_LAUNCHER_HOME_PREFIX_PATTERN.sub(
        lambda each_match: each_match["lead"] + home_folder, command, count=1
    )


def is_managed_launcher(script_word: str) -> bool:
    """Return whether a script word names the launcher at ``~/.agents/skills/pull-request/scripts/pull_request.py``.

    ::

        <home>/.agents/skills/pull-request/scripts/pull_request.py           -> True
        <home>/.agents/skills/pull-request/scripts/../scripts/pull_request.py -> True
        pull_request.py, ./pull_request.py, scripts/pull_request.py            -> False
        /tmp/x/pull_request.py, /repo/.agents/skills/pull-request/...          -> False

    A relative word is never the launcher, since the gate cannot tell which
    folder bash runs it from. Both paths resolve links and letter case
    before the compare.

    Args:
        script_word: The script word with any home prefix written out.

    Returns:
        True when the word resolves to the managed launcher.
    """
    if not os.path.isabs(script_word):
        return False
    managed_launcher = Path.home().joinpath(*ALL_MANAGED_LAUNCHER_PATH_PARTS)
    return os.path.normcase(os.path.realpath(script_word)) == os.path.normcase(
        os.path.realpath(managed_launcher)
    )


def _runs_managed_launcher(all_program_tokens: list[str]) -> bool:
    """Return whether the words from the program on run ``create`` of the managed launcher.

    ::

        <home>/.agents/.../pull_request.py create, python3 <home>/.agents/.../pull_request.py create -> True
        python3 ~/.agents/.../pull_request.py create, python3 '<home>/.agents/...' create          -> False
        pull_request.py create, python3 ./pull_request.py create, py -3 <launcher> create          -> False

    The words are POSIX words, so the script word is compared as bash
    hands it over. A ``~`` or ``$HOME`` the walk left in it is one bash
    does not expand, and a quote left in it is part of the file name.
    """
    program_word = unquoted_token(all_program_tokens[0])
    is_interpreter = (
        FOLDER_PATH_SEPARATOR_PATTERN.search(program_word) is None
        and LONE_LAUNCHER_PYTHON_PATTERN.fullmatch(program_word) is not None
    )
    all_lead_words = all_program_tokens[int(is_interpreter) :][:LONE_LAUNCHER_LEAD_WIDTH]
    if len(all_lead_words) < LONE_LAUNCHER_LEAD_WIDTH:
        return False
    script_word, action_word = all_lead_words
    return unquoted_token(action_word) == LONE_LAUNCHER_CREATE_WORD and is_managed_launcher(script_word)


def with_launcher_home_written(line: str, all_tokens: list[str]) -> list[str]:
    """Return a line's POSIX words with each managed launcher word whose home bash expands written out.

    ::

        python3 ~/.agents/.../pull_request.py create       -> python3 <home>/.agents/.../pull_request.py create
        python3 "$HOME/.agents/.../pull_request.py" create -> python3 <home>/.agents/.../pull_request.py create
        python3 '~/.agents/...', "~/.agents/...", \\~/.agents/..., ~"/.agents/..." -> unchanged
        python3 '$HOME/.agents/...', \\$HOME/.agents/..., $"HOME"/.agents/...       -> unchanged

    The POSIX split drops quotes and backslashes, so the words alone cannot
    tell ``~/x`` from ``'~/x'``. The raw line can. A word-leading ``~``
    right before an unquoted ``/``, or a ``$HOME`` outside single quotes,
    is the home bash writes out. A line the marks cannot split one for one
    keeps its words, so its launcher word stays unread.

    Args:
        line: One logical line from ``quote_aware_lines``.
        all_tokens: The line's POSIX words.

    Returns:
        The words, with each launcher word whose home bash expands written as the home folder.
    """
    if HOME_EXPANSION_MARK in line:
        return all_tokens
    all_marked_tokens = operator_aware_tokens(_home_marked_line(line), IS_POSIX_TOKENIZATION)
    if all_marked_tokens is None or len(all_marked_tokens) != len(all_tokens):
        return all_tokens
    managed_launcher = Path.home().joinpath(*ALL_MANAGED_LAUNCHER_PATH_PARTS).as_posix()
    return [
        managed_launcher if each_marked_token == MARKED_MANAGED_LAUNCHER_WORD else each_token
        for each_token, each_marked_token in zip(all_tokens, all_marked_tokens, strict=True)
    ]


def _home_marked_line(line: str) -> str:
    expansion_line = expansion_marked_line(line)
    all_pieces: list[str] = []
    index = 0
    while index < len(line):
        home_width = _expanded_home_width(line, expansion_line, index)
        all_pieces.append(HOME_EXPANSION_MARK if home_width else line[index])
        index += home_width or 1
    return "".join(all_pieces)


def _expanded_home_width(line: str, expansion_line: str, index: int) -> int:
    if expansion_line[index] == line[index]:
        return 0
    if line.startswith(HOME_FOLDER_PREFIX, index):
        return len(HOME_FOLDER)
    home_variable = HOME_VARIABLE_PATTERN.match(line, index)
    return len(home_variable.group()) if home_variable else 0


def is_settled_pipe_reader(all_tokens: list[str], has_expanding_heredoc: bool) -> bool:
    """Return whether a pipeline member after a create only reads or copies its output.

    ::

        tail -5, grep -o 'a.*', tee out.txt, cat > log.txt   -> True
        git push ..., tee .gi?/HEAD, cat "$F", ( cat )       -> False

    The member is a bare-named ``cat``, ``head``, ``tail``, ``tee`` or
    ``grep`` whose words hold no ``$``, backtick or ``.git``, with output
    only to /dev/null, a descriptor copy, or a plain path outside ``.git``.
    The words of ``tee`` are paths it writes, so they also hold no glob
    character, brace or ``~``.

    Args:
        all_tokens: The words of the member, empty for a group.
        has_expanding_heredoc: True when the command holds a heredoc body bash expands.

    Returns:
        True when the member is a settled reader.
    """
    if not all_tokens or _holds_unsettled_token(all_tokens, has_expanding_heredoc):
        return False
    program = unquoted_token(all_tokens[0])
    if program not in ALL_SETTLED_PIPE_READER_PROGRAMS:
        return False
    is_word_kept = _is_kept_write_target if program == TEE_PROGRAM_NAME else _is_kept_reader_word
    if not all(is_word_kept(each) for each in all_tokens[1:]):
        return False
    return all(_is_kept_write_target(each_target) for each_target in _write_targets(all_tokens))


def _holds_unsettled_token(all_tokens: list[str], has_expanding_heredoc: bool) -> bool:
    if FUNCTION_DEFINITION_TOKEN in all_tokens:
        return True
    return has_expanding_heredoc and HEREDOC_OPERATOR_TOKEN in all_tokens


def _program_index(all_tokens: list[str]) -> int:
    for each_index, each_token in enumerate(all_tokens):
        if LEADING_ASSIGNMENT_PATTERN.match(unquoted_token(each_token)) is None:
            return each_index
    return len(all_tokens)


def _is_settled_prefix(token: str) -> bool:
    name, _, assigned_word = unquoted_token(token).partition(ASSIGNMENT_SEPARATOR)
    is_settled_name = (
        UNSETTLED_PREFIX_NAME_PATTERN.fullmatch(name.rstrip(APPEND_ASSIGNMENT_MARK)) is None
    )
    return is_settled_name and _is_plain_word(assigned_word)


def _is_plain_word(word: str) -> bool:
    return ALL_EXPANSION_OPENER_CHARACTERS.isdisjoint(word)


def _are_plain_option_words(all_words: list[str]) -> bool:
    for each_word in all_words:
        if each_word == END_OF_OPTIONS_WORD:
            return True
        if not _is_plain_word(each_word):
            return False
        if not each_word.startswith(OPTION_PREFIX):
            return True
    return True


def _is_settled_folder_target(all_words: list[str]) -> bool:
    all_folder_words = _words_without_redirects(all_words)
    if len(all_folder_words) != 1:
        return False
    target = unquoted_token(all_folder_words[0])
    if not target or target.startswith((OPTION_PREFIX, FOLDER_STACK_ROTATION_PREFIX)):
        return False
    if target == HOME_FOLDER or target.startswith(HOME_FOLDER_PREFIX):
        target = target[len(HOME_FOLDER) :]
    if not ALL_UNSETTLED_WRITE_TARGET_CHARACTERS.isdisjoint(target):
        return False
    return not any(
        each_part.rstrip(ALL_IGNORED_FOLDER_NAME_END_CHARACTERS).lower().endswith(GIT_FOLDER_NAME)
        for each_part in FOLDER_PATH_SEPARATOR_PATTERN.split(target)
    )


def _words_without_redirects(all_words: list[str]) -> list[str]:
    all_kept_words: list[str] = []
    is_redirect_target = False
    for each_index, each_word in enumerate(all_words):
        is_operator = each_word in ALL_REDIRECT_OPERATORS
        is_descriptor_number = (
            each_word.isdigit()
            and each_index + 1 < len(all_words)
            and all_words[each_index + 1] in ALL_REDIRECT_OPERATORS
        )
        if not (is_operator or is_descriptor_number or is_redirect_target):
            all_kept_words.append(each_word)
        is_redirect_target = is_operator
    return all_kept_words


def _is_kept_reader_word(word: str) -> bool:
    return _is_plain_word(word) and GIT_FOLDER_NAME not in word.lower()


def _is_kept_write_target(target: str) -> bool:
    if target == NULL_DEVICE_PATH:
        return True
    return (
        bool(target)
        and ALL_UNSETTLED_WRITE_TARGET_CHARACTERS.isdisjoint(target)
        and _is_kept_reader_word(target)
    )


def _write_targets(all_tokens: list[str]) -> list[str]:
    all_targets: list[str] = []
    for each_index, each_token in enumerate(all_tokens):
        if each_token not in ALL_OUTPUT_REDIRECT_OPERATORS:
            continue
        target = (
            unquoted_token(all_tokens[each_index + 1]) if each_index + 1 < len(all_tokens) else ""
        )
        is_descriptor_copy = (
            each_token == FILE_DESCRIPTOR_COPY_OPERATOR
            and FILE_DESCRIPTOR_COPY_TARGET_PATTERN.fullmatch(target) is not None
        )
        if not is_descriptor_copy:
            all_targets.append(target)
    return all_targets
