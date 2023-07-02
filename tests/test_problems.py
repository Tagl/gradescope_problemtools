import functools
import subprocess
import sys
import unittest

from gradescope_utils.autograder_utils.decorators import weight, tags
from pathlib import Path

from problem_config import load_problem_config

if sys.platform != "win32":
    import resource

class ProblemException(Exception):
    pass

class UnsupportedLanguage(ProblemException):
    def __init__(self, f):
        self.f = f
    
    def __str__(self):
        return "Submitted code file {} is in an unsupported language.".format(self.f)

def get_program_metavariables(source_path) :
    if isinstance(source_path, str):
        source_path = Path(source_path)
    submitted_files = [f for f in source_path.iterdir()]
    res = {}
    res['path'] = source_path
    res['files'] = (str(x) for x in submitted_files)
    for f in submitted_files:
        if f.suffix != '.py':
            raise UnsupportedLanguage(f.relative_to(source_path))
    if len(submitted_files) == 1:
        res['mainfile'] = str(submitted_files[0])
    else:
        main_matches = list(source_path.glob("[mM][aA][iI][nN].*"))
        if len(main_matches) > 0:
            res['mainfile'] = main_matches[0]
        else:
            res['mainfile'] = sorted(self.files)[0]
    res['mainclass'] = Path(res['mainfile']).with_suffix('').stem
    res['Mainclass'] = res['mainclass'].capitalize()
    res['binary'] = str(source_path / 'program')
    return res

def limit_virtual_memory(memory_limit):
    # The tuple below is of the form (soft limit, hard limit). Limit only
    # the soft part so that the limit can be increased later (setting also
    # the hard limit would prevent that).
    # When the limit cannot be changed, setrlimit() raises ValueError.
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, resource.RLIM_INFINITY))

class TestProblemMeta(type):
    def __new__(mcs, name, bases, dictionary, problem_name):
        SUBMISSION_DIR = f"/autograder/submission/"
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

        @classmethod
        def setUpClass(cls):
            cls.config = load_problem_config(PROBLEM_YAML)
            cls.metavariables = get_program_metavariables(SUBMISSION_DIR)
            compile_command = ('/usr/bin/python3', '-m', 'py_compile', *cls.metavariables['files'])
            limit_mem = None
            MEBIBYTE = 1024 * 1024
            if sys.platform != "win32":
                limit_mem = lambda: limit_virtual_memory(cls.config.limits.compilation_memory * MEBIBYTE)
            try:
                compile_process = subprocess.Popen(compile_command,
                                                   stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE,
                                                   encoding='utf8',
                                                   preexec_fn=limit_mem)
                output, err = compile_process.communicate('', cls.config.limits.compilation_time)
                compile_process.terminate()
            except subprocess.TimeoutExpired:
                cls.fail(cls, f"Compile time limit of {COMPILE_TIME_LIMIT_IN_SECONDS} seconds exceeded.")
            except subprocess.CalledProcessError:
                cls.fail(cls, "Compile error")
            except Exception:
                cls.fail(cls, "Unknown error compiling submission, contact the instructor")
            if compile_process.returncode != 0:
                cls.fail(cls, "Compile error")

        dictionary['setUpClass'] = setUpClass

        def _run_testcase(self, test_name: Path):
            test_name = Path(test_name)
            input_data, output, answer = "", "", ""

            input_filename = test_name.with_suffix('.in')
            with open(input_filename) as f:
                input_data = f.read()

            answer_filename = test_name.with_suffix('.ans')
            with open(answer_filename) as f:
                answer = f.read()

            run_command = (x.format(**self.metavariables) for x in ('/usr/bin/python3', '{mainfile}'))
            limit_mem = None
            MEBIBYTE = 1024 * 1024
            if sys.platform != "win32":
                limit_mem = lambda: limit_virtual_memory(self.config.limits.memory * MEBIBYTE)
            try:
                run_process = subprocess.Popen(run_command,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        encoding='utf8',
                                        preexec_fn=lambda: limit_mem)
                output, err = run_process.communicate(input_data, TIME_LIMIT_IN_SECONDS)
                run_process.terminate()
            except subprocess.TimeoutExpired:
                self.fail(f"Time limit of {TIME_LIMIT_IN_SECONDS} seconds exceeded.")
            except subprocess.CalledProcessError:
                self.fail("Runtime error when executing submission")
            except Exception:
                self.fail("Unknown error judging submission, contact the instructor")
            if run_process.returncode != 0:
                self.fail("Runtime error when executing submission")
            
            output_bytes = output.encode()
            if len(output_bytes) > self.config.limits.output * MEBIBYTE:
                self.fail(f"Output was {len(output_bytes)} bytes which exceeds limit of {OUTPUT_LIMIT_IN_BYTES} bytes.")

            test_feedback_dir = FEEDBACK_DIR / test_name.stem
            test_feedback_dir.mkdir(parents=True, exist_ok=True)
            compare_command = ('./default_validator', input_filename, answer_filename, str(test_feedback_dir)) + tuple(self.config.validator_flags)
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
            
            @weight(100.0/len(secrets))
            @tags("input/output")
            def f(self, test=secret):
                _run_testcase(self, test)

            dictionary[function_name] = f

        return type.__new__(mcs, name, bases, dictionary)

module = sys.modules[__name__]
for problem in Path('problems').iterdir():
    if problem.is_dir():
        class C(unittest.TestCase, metaclass=TestProblemMeta,
                problem_name=problem.stem):
            pass
        class_name = f'TestProblem_{problem.stem}'
        C.__name__ = class_name
        C.__qualname__ = class_name
        module.__setattr__(class_name, C)
        break # only support one problem each autograder

# The dynamically created class will reside in the module
# after the loop and needs to be manually deleted
module.__delattr__('C')
