import functools
import json
import subprocess
import sys
import tempfile
import unittest
import yaml

from enum import Enum
from gradescope_utils.autograder_utils.decorators import weight, tags
from pathlib import Path
from typing import List

from problemtools.config import ConfigError, load_config
from problemtools.languages import load_language_config
from problemtools.run import get_program, BuildRun
from problemtools.verifyproblem import is_RTE, is_TLE
from problem_config import load_problem_config

from problemtools.verifyproblem import Problem

if sys.platform != "win32":
    import resource

PROBLEMS_DIR = Path("problems")
SUBMISSION_DIR = Path("/autograder/submission")
EXIT_AC = 42
EXIT_WA = 43
LANGUAGES = load_language_config()
EPS = 1e-9


class UnsupportedLanguage(Exception):
    def __init__(self, lang):
        self.lang = lang

    def __str__(self):
        return "Unsupported programming language {}".format(self.lang)


class Verdict(Enum):
    AC = 0
    WA = 1
    OLE = 2
    TLE = 3
    RTE = 4
    CE = 5
    JE = 6

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


VerdictAggregation = Enum(
    "VerdictAggregation", ["WORST_ERROR", "FIRST_ERROR", "ALWAYS_ACCEPT"]
)
ScoreAggregation = Enum("ScoreAggregation", ["SUM", "MIN"])


def verdict_to_str(verdict):
    if verdict == Verdict.JE:
        return "Judge Error"
    if verdict == Verdict.CE:
        return "Compile Error"
    if verdict == Verdict.RTE:
        return "Run Time Error"
    if verdict == Verdict.TLE:
        return "Time Limit Exceeded"
    if verdict == Verdict.OLE:
        return "Output Limit Exceeded"
    if verdict == Verdict.WA:
        return "Wrong Answer"
    if verdict == Verdict.AC:
        return "Accepted"
    assert False


class TestResult:
    def __init__(
        self,
        verdict: Verdict,
        score: int,
        running_time: float,
        message: str = "",
        privileged_message: str = "",
    ):
        self.verdict: Verdict = verdict
        self.score: int = score
        self.running_time: float = running_time
        self.message: str = message
        self.privileged_message: str = privileged_message

    def get_privileged_feedback(self):
        return TestResult(
            self.verdict, self.score, self.running_time, self.privileged_message
        )

    def __str__(self):
        if self.message:
            return f"{verdict_to_str(self.verdict)} ({self.running_time:.4f}s)\n{self.message}"
        return f"{verdict_to_str(self.verdict)} ({self.running_time:.4f}s)"


class TestdataConfig:
    def __init__(self, problem_config, **kwargs):
        self.on_reject = kwargs.get("on_reject", "break")
        self.grading = kwargs.get("grading", "default")
        self.grader_flags = kwargs.get("grader_flags", "")
        self.input_validator_flags = kwargs.get("input_validator_flags", "")
        self.output_validator_flags = kwargs.get("output_validator_flags", "")
        self.accept_score = int(kwargs.get("accept_score", 1))
        self.reject_score = int(kwargs.get("reject_score", 0))
        self.range = kwargs.get("range", "-inf inf" if problem_config.type == "scoring" else "0 1")
        self.min_score, self.max_score = map(float, self.range.split())

        flags = self.grader_flags.split()
        if "always_accept" in flags:
            self.verdict_aggregation = VerdictAggregation.ALWAYS_ACCEPT
        elif "first_error" in flags:
            self.verdict_aggregation = VerdictAggregation.FIRST_ERROR
        else:
            self.verdict_aggregation = VerdictAggregation.WORST_ERROR

        if "min" in flags or problem_config.type == "pass-fail":
            self.score_aggregation = ScoreAggregation.MIN
        else:
            self.score_aggregation = ScoreAggregation.SUM

        self.ignore_sample = "ignore_sample" in flags
        self.accept_if_any_accepted = "accept_if_any_accepted" in flags


def aggregate_results(config: TestdataConfig, results: List[TestResult]):
    if not results:
        return TestResult(
            Verdict.JE,
            config.reject_score,
            0.0,
            "Something went wrong. There are no test results to aggregate.",
        )
    verdict = None
    results = [result for result in results if result is not None]
    if config.accept_if_any_accepted and any(
        result.verdict == Verdict.AC for result in results
    ):
        verdict = Verdict.AC
    elif config.verdict_aggregation == VerdictAggregation.FIRST_ERROR:
        verdict = next(
            (result.verdict for result in results if result.verdict != Verdict.AC),
            Verdict.AC,
        )
    elif config.verdict_aggregation == VerdictAggregation.WORST_ERROR:
        verdict = max(result.verdict for result in results)
    else:
        verdict = Verdict.AC

    score = config.reject_score
    if verdict == Verdict.AC:
        if config.score_aggregation == ScoreAggregation.MIN:
            score = min(result.score for result in results)
        else:
            score = sum(result.score for result in results)

    return TestResult(verdict, score, max(result.running_time for result in results))


def load_testdata_config(path: Path, problem_config, parent_config=None):
    if path.is_file():
        with open(path) as f:
            return TestdataConfig(problem_config, **yaml.safe_load(f))
    elif parent_config:
        return parent_config
    return TestdataConfig(problem_config)


def read_file(path):
    result = None
    if path.exists():
        with open(path) as f:
            result = f.read()
    return result

def truncate_string(s, n):
    if len(s) > n:
        return f"{s[:n]}... (string truncated)"
    return s


def get_feedback_message(
    show_privileged,
    input_data,
    output,
    answer,
    judge_message="",
    team_message="",
    hint="",
    desc="",
    error="",
):
    lines = []
    max_length = 5*10**3
    if show_privileged:
        lines.extend([
            "#### Input:",
            "```",
            f"{truncate_string(input_data, max_length)}",
            "```",
            "#### Your program's output:",
            "```",
            f"{truncate_string(output, max_length)}",
            "```",
            "#### Correct output:",
            "```",
            f"{truncate_string(answer, max_length)}",
            "```"
        ])

        if error:
            lines.extend([
                "#### Your program's error:",
                "```",
                f"{truncate_string(error, max_length)}",
                "```"
            ])

        if judge_message:
            lines.extend(["#### Validator output:", "```", f"{judge_message}", "```"])
        if desc:
            lines.extend(["#### Testcase description:", "```", f"{desc}", "```"])
    if team_message:
        lines.extend(["#### Validator message:", "```", f"{team_message}", "```"])
    if hint:
        lines.extend(["#### Hint:", "```", f"{hint}", "```"])
    return "\n".join(lines)


def run_testcase(
    program,
    validator,
    working_directory,
    time_limit,
    config,
    grading_config,
    test_name: Path,
    is_sample=False,
):
    test_name = Path(test_name)

    input_filename = test_name.with_suffix(".in")
    input_data = read_file(input_filename)

    answer_filename = test_name.with_suffix(".ans")
    answer = read_file(answer_filename)

    output_filename = Path(working_directory) / "output"
    error_filename = Path(working_directory) / "error"

    status, running_time = program.run(
        infile=str(input_filename),
        outfile=str(output_filename),
        errfile=str(error_filename),
        timelim=int(time_limit + 1.999),
        memlim=config.limits.memory,
        set_work_dir=True,
    )

    hint_filename = test_name.with_suffix(".hint")
    hint = read_file(hint_filename)

    desc_filename = test_name.with_suffix(".desc")
    desc = read_file(desc_filename)

    output = read_file(output_filename)

    if is_TLE(status) or running_time > time_limit:
        message = get_feedback_message(is_sample, input_data, output, answer, "", "", hint, desc)
        privileged_message = get_feedback_message(True, input_data, output, answer, "", "", hint, desc)
        return TestResult(
            Verdict.TLE,
            grading_config.reject_score,
            running_time,
            message,
            privileged_message,
        )
    if is_RTE(status):
        error = read_file(error_filename)
        message = get_feedback_message(
            is_sample, input_data, output, answer, "", "", hint, desc, error
        )
        privileged_message = get_feedback_message(
            True, input_data, output, answer, "", "", hint, desc, error
        )
        return TestResult(
            Verdict.RTE,
            grading_config.reject_score,
            running_time,
            f"#### Exit Code {status}\n{message}",
            f"#### Exit Code {status}\n{privileged_message}",
        )

    output_bytes = output.encode()
    MEBIBYTE = 1024 * 1024
    if len(output_bytes) > config.limits.output * MEBIBYTE:
        return TestResult(Verdict.OLE, grading_config.reject_score, running_time)

    test_feedback_dir = Path(tempfile.mkdtemp(prefix="feedback", dir=working_directory))
    compare_command = (
        *validator.get_runcmd(),
        input_filename,
        answer_filename,
        str(test_feedback_dir),
        *config.validator_flags,
        *grading_config.output_validator_flags.split()
    )
    compare = subprocess.Popen(
        compare_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf8"
    )
    compare.communicate(output)

    judge_message_filename = test_feedback_dir / "judgemessage.txt"
    judge_message = read_file(judge_message_filename)

    team_message_filename = test_feedback_dir / "teammessage.txt"
    team_message = read_file(team_message_filename)

    if compare.returncode == EXIT_WA:
        message = get_feedback_message(
            is_sample,
            input_data,
            output,
            answer,
            judge_message,
            team_message,
            hint,
            desc,
        )
        privileged_message = get_feedback_message(
            True, input_data, output, answer, judge_message, team_message, hint, desc
        )
        return TestResult(
            Verdict.WA,
            grading_config.reject_score,
            running_time,
            message,
            privileged_message,
        )
    elif compare.returncode != EXIT_AC:
        privileged_message = get_feedback_message(
            True, input_data, output, answer, judge_message, team_message, hint, desc
        )
        return TestResult(
            Verdict.JE,
            grading_config.reject_score,
            running_time,
            "Something went horribly wrong, please contact the instructor regarding this error",
            privileged_message,
        )
    privileged_message = get_feedback_message(
        True, input_data, output, answer, judge_message, team_message, hint, desc
    )

    final_score = grading_config.accept_score
    score_filename = test_feedback_dir / "score.txt"
    score_contents = read_file(score_filename)
    if score_contents is not None:
        final_score = float(score_contents)
    return TestResult(
        Verdict.AC, final_score, running_time, "", privileged_message
    )


def process_test_group(
    path: Path,
    display_prefix,
    program,
    validator,
    tmpdir,
    time_limit,
    config,
    parent_config,
    result,
    is_sample=False,
):
    if not path.exists():
        # Ignore result
        return None

    subgroups = []
    testcases = []
    testdata_path = path / "testdata.yaml"

    grading_config = load_testdata_config(testdata_path, config, parent_config)

    for subpath in sorted(path.iterdir()):
        if subpath.is_dir():
            subgroups.append(subpath)
        elif subpath.suffix == ".in":
            testcases.append(subpath.with_suffix(""))

    results = []

    group_results = []
    for i, test in enumerate(testcases, 1):
        test_result = run_testcase(
            program, validator, tmpdir, time_limit, config, grading_config, test, is_sample
        )
        name = f"## {display_prefix} - {i} / {len(testcases)}"
        # Instructor feedback
        print(name)
        print(test_result.get_privileged_feedback())
        print()
        result["tests"].append(
            {
                "name": name,
                "status": "passed" if test_result.verdict == Verdict.AC else "failed",
                "output": f"### {test_result}",
            }
        )
        group_results.append(test_result)
        if grading_config.on_reject == "break" and test_result.verdict != Verdict.AC:
            break
    else:
        for i, subgroup in enumerate(subgroups, 1):
            subgroup_prefix = f"{display_prefix} - Test Group {i}"
            subgroup_result = process_test_group(
                subgroup,
                subgroup_prefix,
                program,
                validator,
                tmpdir,
                time_limit,
                config,
                grading_config,
                result,
                is_sample,
            )

            group_results.append(subgroup_result)
            if (
                grading_config.on_reject == "break"
                and subgroup_result.verdict != Verdict.AC
            ):
                break

    group_result = aggregate_results(grading_config, group_results)

    name = f"## {display_prefix} ({group_result.score:.2f} / {grading_config.max_score:.2f})"
    print(name)
    print(group_result.get_privileged_feedback())
    print()
    result["tests"].append(
        {
            "name": name,
            "status": "passed"
            if abs(group_result.score - grading_config.max_score) < EPS
            else "failed",
            "output": f"### {group_result}",
        }
    )

    return group_result


def prepare_program(config, program_path, tmpdir, include=None):
    program = get_program(str(program_path), LANGUAGES, str(tmpdir), str(include))
    if program is None:
        compile_result = (
            False,
            "Unable to determine programming language.\n"
            "Ensure your submitted files have the correct file extensions.\n"
            "For example, 'program.py' instead of 'program' for Python 3.",
        )
    elif not config.language_allowed(program.language.lang_id):
        compile_result = (False, str(UnsupportedLanguage(program.language.lang_id)))
    else:
        compile_result = program.compile()
    return program, compile_result


def grade_submission(problem, submission):
    time_limit_file = problem / ".timelimit"
    include = problem / "include"
    problem_yaml = problem / "problem.yaml"
    data = problem / "data"
    sample = data / "sample"
    secret = data / "secret"

    tmpdir = tempfile.mkdtemp()
    config = load_problem_config(problem_yaml)
    with open(time_limit_file) as f:
        time_limit = float(f.readline())
    program, compile_result = prepare_program(config, submission, tmpdir, include)

    if config.validation == "default":
        output_validator, validator_compile_result = prepare_program(config, 'default_validator', tmpdir)
    else:
        output_validators = problem / "output_validators"
        validator_path = next(output_validators.iterdir())
        output_validator, validator_compile_result = prepare_program(config, validator_path, tmpdir)

    result = {
        "output_format": "md",
        "test_output_format": "md",
        "test_name_format": "md",
        "visibility": "visible",
        "stdout_visibility": "hidden",
        "extra_data": {},
        "tests": [],
    }

    result["tests"].append(
        {"name": "## Metadata", "status": "passed", "output": str(config)}
    )

    result["tests"].append(
        {
            "name": "## Compilation",
            "status": "passed" if compile_result[0] else "failed",
            "output": f"```\n{compile_result[1]}\n```" if compile_result[1] else "",
        }
    )

    final_result: TestResult = None

    grading_config = load_testdata_config(data / "testdata.yaml", config, None)

    if compile_result[0]:
        test_results = []

        sample_result = process_test_group(
            sample,
            "Sample testcases",
            program,
            output_validator,
            tmpdir,
            time_limit,
            config,
            grading_config,
            result,
            True,
        )

        run_secret = True
        if not grading_config.ignore_sample:
            test_results.append(sample_result)
            if (
                sample_result is not None
                and sample_result.verdict != Verdict.AC
                and grading_config.on_reject == "break"
            ):
                run_secret = False

        if run_secret:
            secret_result = process_test_group(
                secret,
                "Secret testcases",
                program,
                output_validator,
                tmpdir,
                time_limit,
                config,
                grading_config,
                result,
            )
            test_results.append(secret_result)

        final_result = aggregate_results(grading_config, test_results)
    else:
        final_result = TestResult(Verdict.CE, grading_config.reject_score, 0.0)

    if final_result.verdict == Verdict.AC:
        result["execution_time"] = final_result.running_time

    if config.type == "scoring":
        result["score"] = final_result.score
        result["max_score"] = grading_config.max_score
    else:
        result["score"] = 100.0 if final_result.verdict == Verdict.AC else 0.0
        result["max_score"] = 100.0

    result["output"] = f"# {final_result}"

    with open("/autograder/results/results.json", "w") as results_file:
        results_file.write(
            json.dumps(result, indent=4, ensure_ascii=False).encode("utf8").decode()
        )


def find_problem():
    for problem in Path("problems").iterdir():
        if problem.is_dir() and (problem / "problem.yaml").exists():
            return problem


def main():
    problem = find_problem()
    grade_submission(problem, "/autograder/submission")


if __name__ == "__main__":
    main()
