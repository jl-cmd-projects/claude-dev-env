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

import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import create_arguments
from blocking.merge_review_gate_parts.quoted_lines import quote_aware_lines
from hooks_constants.followup_pr_dedupe_constants import WINDOWS_EXECUTABLE_SUFFIX
from hooks_constants.merge_review_gate_constants import (
    ALL_EXPANSION_OPENER_CHARACTERS,
    ALL_IGNORED_FOLDER_NAME_END_CHARACTERS,
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
    GIT_FOLDER_NAME,
    HEREDOC_OPERATOR_TOKEN,
    LAUNCHER_SCRIPT_FILE_NAME,
    LINE_FEED,
    NULL_DEVICE_PATH,
    OPTION_PREFIX,
    PRINTF_PROGRAM_NAME,
    PRINTF_VARIABLE_OPTION_PREFIX,
    PROCESS_SUBSTITUTION_PATTERN,
    ALL_SETTLED_CREATE_LAUNCHER_WORDS,
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

    The words before the program are assignments whose values hold no ``$``
    or backtick, and whose names are not ``GIT_``, ``LD_``, ``DYLD_``,
    ``XDG_``, ``HOME``, ``PATH``, or a ``GH_`` name but the repository one. The first other word
    is the program, with no wrapper or compound word before it but a bare
    ``uv run``, as in ``uv run pull_request.py create``. The program is a
    bare word with no ``/`` or ``\\``, which bash finds on PATH, unless it
    is the ``pull_request.py`` script itself. Names match in any
    case, since Windows reads ``gh_repo`` as ``GH_REPO``, and only the upper
    case ``GH_REPO`` is kept. Output goes only to /dev/null, a descriptor
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
    launcher_width = len(ALL_SETTLED_CREATE_LAUNCHER_WORDS)
    all_launcher_words = tuple(
        unquoted_token(each) for each in all_tokens[program_index : program_index + launcher_width]
    )
    if (
        all_launcher_words == ALL_SETTLED_CREATE_LAUNCHER_WORDS
        and program_index + launcher_width < len(all_tokens)
    ):
        program_index += launcher_width
    program_token = unquoted_token(all_tokens[program_index])
    program_word = token_basename(program_token).removesuffix(WINDOWS_EXECUTABLE_SUFFIX)
    if program_word != segment_program_and_arguments(all_tokens)[0]:
        return False
    if FOLDER_PATH_SEPARATOR_PATTERN.search(program_token) and program_word != LAUNCHER_SCRIPT_FILE_NAME:
        return False
    return all(_is_kept_write_target(each_target) for each_target in _write_targets(all_tokens))


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
