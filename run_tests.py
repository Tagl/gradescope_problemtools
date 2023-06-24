import unittest
from gradescope_utils.autograder_utils.json_test_runner import JSONTestRunner

results_json_file = '/autograder/results/results.json'
#results_json_file = 'results.json'

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover('tests')
    with open(results_json_file, 'w') as f:
        JSONTestRunner(visibility='visible', stream=f).run(suite)
