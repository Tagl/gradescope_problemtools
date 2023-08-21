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

from problemtools.config import ConfigError
from problemtools.languages import load_language_config
from problemtools.run import get_program
from problemtools.verifyproblem import is_RTE, is_TLE
from problem_config import load_problem_config

from problemtools.verifyproblem import Problem

if sys.platform != "win32":
    import resource

PROBLEMS_DIR = Path('problems')
SUBMISSION_DIR = Path('/autograder/submission')
EXIT_AC = 42
EXIT_WA = 43
LANGUAGES = load_language_config()

class UnsupportedLanguage(Exception):
    def __init__(self, lang):
        self.lang = lang

    def __str__(self):
        return "Unsupported programming language {}".format(self.lang)

Verdict = Enum('Verdict', ['JE', 'CE', 'RTE', 'TLE', 'OLE', 'WA', 'AC'])

def verdict_to_str(verdict):
    if verdict == Verdict.JE:
        return 'Judge Error'
    if verdict == Verdict.CE:
        return 'Compile Error'
    if verdict == Verdict.RTE:
        return 'Run Time Error'
    if verdict == Verdict.TLE:
        return 'Time Limit Exceeded'
    if verdict == Verdict.OLE:
        return 'Output Limit Exceeded'
    if verdict == Verdict.WA:
        return 'Wrong Answer'
    if verdict == Verdict.AC:
        return 'Accepted'
    assert False

class TestResult:
    def __init__(self, verdict: Verdict, running_time: float, message: str = ""):
        self.verdict: Verdict = verdict
        self.running_time = running_time
        self.message = message

    def __str__(self):
        if self.message:
            return f"{verdict_to_str(self.verdict)} ({self.running_time:.4f}s)\n{self.message}"
        return f"{verdict_to_str(self.verdict)} ({self.running_time:.4f}s)"

def run_testcase(program, working_directory, time_limit, config, test_name: Path):
    test_name = Path(test_name)
    input_data, output, answer = "", "", ""

    input_filename = test_name.with_suffix('.in')
    with open(input_filename) as f:
        input_data = f.read()


    output_filename = Path(working_directory) / 'output'
    error_filename = Path(working_directory) / 'error'

    status, running_time = program.run(infile=str(input_filename),
                                       outfile=str(output_filename),
                                       errfile=str(error_filename),
                                       timelim=int(time_limit + 1.999),
                                       memlim=config.limits.memory)
    
    hint_filename = test_name.with_suffix('.hint')
    hint = ''
    if hint_filename.exists():
        with open(hint_filename) as f:
            hint = f"Hint:\n```\n{f.read()}```"

    if is_TLE(status) or running_time > time_limit:
        return TestResult(Verdict.TLE, running_time, hint)
    elif is_RTE(status):
        return TestResult(Verdict.RTE, running_time, f"Exit Code {status}\n{hint}")

    answer_filename = test_name.with_suffix('.ans')

    with open(output_filename) as f:
        output = f.read()

    output_bytes = output.encode()
    MEBIBYTE = 1024 * 1024
    if len(output_bytes) > config.limits.output * MEBIBYTE:
        return TestResult(Verdict.OLE, running_time)

    test_feedback_dir = tempfile.mkdtemp(prefix='feedback', dir=working_directory)
    compare_command = ('./default_validator', input_filename, answer_filename, str(test_feedback_dir)) + tuple(config.validator_flags)
    compare = subprocess.Popen(compare_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
    compare.communicate(output)

    if compare.returncode == EXIT_WA:
        return TestResult(Verdict.WA, running_time, hint)
    elif compare.returncode != EXIT_AC:
        return TestResult(Verdict.JE, running_time, "Something went horribly wrong, please contact the instructor regarding this error")
    return TestResult(Verdict.AC, running_time)

def grade_submission(problem, submission):
    time_limit_file = problem / '.timelimit'
    include = problem / 'include'
    problem_yaml = problem / 'problem.yaml'
    data = problem / 'data'
    sample = data / 'sample'
    secret = data / 'secret'

    tmpdir = tempfile.mkdtemp()
    config = load_problem_config(problem_yaml)
    with open(time_limit_file) as f:
        time_limit = float(f.readline())
    program = get_program(submission, LANGUAGES, tmpdir, include)
    if not config.language_allowed(program.language.lang_id):
        compile_result = (False, str(UnsupportedLanguage(program.language.lang_id)))
    else:
        compile_result = program.compile()

    final_verdict = Verdict.AC
    test_results = []
    highest_running_time = 0.0

    result = {
        "score": 0.0,
        "execution_time": 0.0,
        "output": "",
        "output_format": "md",
        "test_output_format": "md",
        "test_name_format": "md",
        "visibility": "visible",
        "stdout_visibility": "visible",
        "extra_data": {},
        "tests": []
    }

    result["tests"].append(
        {
            "name": "## Metadata",
            "status": "passed",
            "output": str(config)
        }
    )

    result["tests"].append(
        {
            "name": "## Compilation",
            "status": "passed" if compile_result[0] else "failed",
            "output": compile_result[1] or ""
        }
    )

    if compile_result[0]:
        samples = [s.with_suffix('') for s in sample.glob('*.in')]
        secrets = [s.with_suffix('') for s in secret.rglob('**/*.in')]
        for i, test in enumerate(sorted(samples) + sorted(secrets), 1):
            test_result = run_testcase(program, tmpdir, time_limit, config, test)
            test_results.append(test_result)
            if i < len(samples):
                name = f"### Sample {i} / {len(samples)}"
            else:
                name = f"### Testcase {i - len(samples)} / {len(secrets)}"
            result["tests"].append(
                {
                    "name": name,
                    "status": "passed" if test_result.verdict == Verdict.AC else "failed",
                    "output": str(test_result),
                }
            )
            if test_result.verdict != Verdict.AC:
                top_test_result = test_result
                final_verdict = test_result.verdict
                break

        if not test_results:
            final_verdict = Verdict.JE
        else:
            highest_running_time = max(test_results, key=lambda x: x.running_time).running_time

    else:
        final_verdict = Verdict.CE
        top_test_result = TestResult(final_verdict, 0.0)

    if final_verdict == Verdict.AC:
        result["score"] = 100.0
        result["execution_time"] = sum(x.running_time for x in test_results)
        top_test_result = max(test_results, key=lambda x: x.running_time)

    result["output"] = f"# {top_test_result}"

    print(json.dumps(result, indent=4))

def find_problem():
    for problem in Path('problems').iterdir():
        if problem.is_dir() and (problem / 'problem.yaml').exists():
            return problem

def main():
    problem = find_problem()
    grade_submission(problem, '/autograder/submission')

if __name__ == "__main__":
    main()
