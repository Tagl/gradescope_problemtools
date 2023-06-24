import functools
import subprocess
import sys
import unittest

from gradescope_utils.autograder_utils.decorators import weight, tags
from pathlib import Path

if sys.platform != "win32":
    import resource


def clean_output(x):
    x_list = [i.strip() for i in x.split('\n') if len(i.strip()) > 0]
    return x_list

def compare_output(x,y):
    n = len(y)
    all_correct = True
    if len(x) != len(y):
        print(f'ERROR: Output does not have the correct number of lines, got {len(x)}, should be {len(y)}')
        all_correct = False

    for i in range(n):
        if i >= len(x):
            print(f'ERROR: Line {i}:')
            print(f'  Yours: <missing>')
            print(f'  Solution: "{y[i]}"')
            all_correct = False
        elif x[i] == y[i]:
            print(f'Line {i} ok: {x[i]}')
        else:
            print(f'ERROR: Line {i}:')
            print(f'  Yours:    "{x[i]}"')
            print(f'  Solution: "{y[i]}"')
            all_correct = False
    return all_correct

def limit_virtual_memory(memory_limit):
    # The tuple below is of the form (soft limit, hard limit). Limit only
    # the soft part so that the limit can be increased later (setting also
    # the hard limit would prevent that).
    # When the limit cannot be changed, setrlimit() raises ValueError.
    if sys.platform == "win32":
        return
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, resource.RLIM_INFINITY))

class TestProblemMeta(type):
    def __new__(mcs, name, bases, dictionary, problem_name, submission_file):
        EXIT_AC = 42
        EXIT_WA = 43
        PROBLEMS_DIR = Path('problems')
        PROBLEM_DIR = PROBLEMS_DIR / problem_name
        PROBLEM_YAML = PROBLEM_DIR / 'problem.yaml'
        DATA_DIR = PROBLEM_DIR / 'data'
        SAMPLE_DIR = DATA_DIR / 'sample'
        SECRET_DIR = DATA_DIR / 'secret'
        FEEDBACK_DIR = Path('feedback') / problem_name
        TIME_LIMIT_IN_SECONDS = 1
        MEMORY_LIMIT_IN_BYTES = 64 * 1024 * 1024
        OUTPUT_LIMIT_IN_BYTES = 128 * 1024

        def _run_testcase(self, test_name: Path):
            test_name = Path(test_name)
            input_data, output, answer = "", "", ""
            input_filename = test_name.with_suffix('.in')
            with open(input_filename) as f:
                input_data = f.read()
            answer_filename = test_name.with_suffix('.ans')
            with open(answer_filename) as f:
                answer = f.read()

            try:
                command = ('python3', '-u', submission_file)

                calc = subprocess.Popen(command,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        encoding='utf8',
                                        preexec_fn=(lambda: limit_virtual_memory(MEMORY_LIMIT_IN_BYTES)) if sys.platform != "win32" else None)
                output, err = calc.communicate(input_data, TIME_LIMIT_IN_SECONDS)
                calc.terminate()
            except subprocess.TimeoutExpired:
                self.fail(f"Time limit of {TIME_LIMIT_IN_SECONDS} seconds exceeded.")
            except subprocess.CalledProcessError:
                self.fail("Runtime error when executing submission")
            except Exception:
                self.fail("Unknown error judging submission, contact the instructor")
            
            output_bytes = output.encode()
            if len(output_bytes) > OUTPUT_LIMIT_IN_BYTES:
                self.fail(f"Output was {len(output_bytes)} bytes which exceeds limit of {OUTPUT_LIMIT_IN_BYTES} bytes.")

            test_feedback_dir = FEEDBACK_DIR / test_name.stem
            test_feedback_dir.mkdir(parents=True, exist_ok=True)
            compare_command = ('./default_validator', input_filename, answer_filename, str(test_feedback_dir))
            compare = subprocess.Popen(compare_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
            compare.communicate(output)
            if compare.returncode == EXIT_WA:
                self.fail(f"Wrong answer")
            elif compare.returncode != EXIT_AC:
                self.fail(f"Judge error")

        samples = [sample.with_suffix('') for sample in SAMPLE_DIR.glob('*.in')]
        secrets = [secret.with_suffix('') for secret in SECRET_DIR.rglob('**/*.in')]
        for sample in sorted(samples):
            function_name = f'test_sample_{sample.stem}'
            
            @weight(0)
            @tags("input/output")
            def f(self, test=sample):
                _run_testcase(self, test)

            dictionary[function_name] = f

        for secret in secrets:
            function_name = f'test_secret_{secret.stem}'
            
            @weight(1)
            @tags("input/output")
            def f(self, test=secret):
                _run_testcase(self, test)

            dictionary[function_name] = f

        return type.__new__(mcs, name, bases, dictionary)

module = sys.modules[__name__]
for problem in Path('problems').iterdir():
    if problem.is_dir():
        class C(unittest.TestCase, metaclass=TestProblemMeta,
                problem_name=problem.stem,
                submission_file='problems/area/submissions/accepted/sol.py'):
            pass
        module.__setattr__(f'TestProblem_{problem.stem}', C)

# The dynamically created class will reside in the module
# after the loop and needs to be manually deleted
module.__delattr__('C')