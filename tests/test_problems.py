import functools
import subprocess
import sys
import tempfile
import unittest
import yaml

from gradescope_utils.autograder_utils.decorators import weight, tags
from pathlib import Path

from problemtools.config import ConfigError
from problemtools.languages import Languages
from problemtools.run import get_program
from problemtools.verifyproblem import is_RTE, is_TLE
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

def load_config(configuration_file):
    """Load a problemtools configuration file.

    Args:
        configuration_file (str): name of configuration file.  Name is
        relative to config directory so typically just a file name
        without paths, e.g. "languages.yaml".
    """
    res = None

    path = Path(configuration_file)
    new_config = None
    if path.is_file():
        try:
            with open(path, 'r') as config:
                new_config = yaml.safe_load(config.read())
        except (yaml.parser.ParserError, yaml.parser.ScannerError) as err:
            raise ConfigError('Config file %s: failed to parse: %s' % (path, err))
    if res is None:
        if new_config is None:
            raise ConfigError('Base configuration file %s not found in %s'
                              % (configuration_file, path))
        res = new_config
    elif new_config is not None:
        __update_dict(res, new_config)

    return res

LANGUAGES = Languages(load_config('languages.yaml'))

class TestProblemMeta(type):
    def __new__(mcs, name, bases, dictionary, problem_name):
        SUBMISSION_DIR = Path('/autograder/submission').absolute()
        EXIT_AC = 42
        EXIT_WA = 43
        PROBLEMS_DIR = Path('problems')
        PROBLEM_DIR = PROBLEMS_DIR / problem_name
        INCLUDE_DIR = PROBLEM_DIR / 'include'
        PROBLEM_YAML = PROBLEM_DIR / 'problem.yaml'
        DATA_DIR = PROBLEM_DIR / 'data'
        SAMPLE_DIR = DATA_DIR / 'sample'
        SECRET_DIR = DATA_DIR / 'secret'
        FEEDBACK_DIR = Path('feedback') / problem_name
        TIME_LIMIT_IN_SECONDS = 1

        @classmethod
        def setUpClass(cls):
            cls.tmpdir = tempfile.mkdtemp()
            print(cls.tmpdir)
            cls.config = load_problem_config(PROBLEM_YAML)
            cls.program = get_program(str(SUBMISSION_DIR), LANGUAGES, cls.tmpdir, INCLUDE_DIR)
            cls.program.compile()

        dictionary['setUpClass'] = setUpClass

        def _run_testcase(self, test_name: Path):
            
            test_name = Path(test_name)
            input_data, output, answer = "", "", ""

            input_filename = test_name.with_suffix('.in')
            with open(input_filename) as f:
                input_data = f.read()

            
            output_filename = Path(self.tmpdir) / 'output'
            error_filename = Path(self.tmpdir) / 'error'

            status, runtime = self.program.run(infile=str(input_filename),
                                               outfile=str(output_filename),
                                               errfile=str(error_filename),
                                               timelim=int(TIME_LIMIT_IN_SECONDS + 1.999),
                                               memlim=self.config.limits.memory)
            
            print(f"Execution time: {runtime:.4f} / {TIME_LIMIT_IN_SECONDS} seconds")
            
            if is_TLE(status) or runtime > TIME_LIMIT_IN_SECONDS:
                print("Time Limit Exceeded")
                self.fail()
            elif is_RTE(status):
                print("Runtime Error (Exit Code {status})")
                self.fail()
            
            answer_filename = test_name.with_suffix('.ans')

            with open(output_filename) as f:
                output = f.read()

            output_bytes = output.encode()
            MEBIBYTE = 1024 * 1024
            if len(output_bytes) > self.config.limits.output * MEBIBYTE:
                self.fail(f"Output was {len(output_bytes)} bytes which exceeds limit of {OUTPUT_LIMIT_IN_BYTES} bytes.")

            test_feedback_dir = tempfile.mkdtemp(prefix='feedback', dir=self.tmpdir)
            compare_command = ('./default_validator', input_filename, answer_filename, str(test_feedback_dir)) + tuple(self.config.validator_flags)
            compare = subprocess.Popen(compare_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
            compare.communicate(output)

            if compare.returncode == EXIT_WA:
                print("Wrong Answer")
                self.fail()
            elif compare.returncode != EXIT_AC:
                print("Judge Error")
                self.fail()
            print("Accepted")

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
try:
    module.__delattr__('C')
except AttributeError:
    # fail silently
    pass
