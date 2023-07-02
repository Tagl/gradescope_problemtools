import yaml

class Limits:
    def __init__(self, **kwargs):
        self.time_multiplier = kwargs.get('time_multiplier', 5)
        self.time_safety_margin = kwargs.get('time_safety_margin', 2)
        self.memory = kwargs.get('memory', 1024)
        self.output = kwargs.get('output', 8)
        self.code = kwargs.get('code', 128)
        self.compilation_time = kwargs.get('compilation_time', 60)
        self.compilation_memory = kwargs.get('compilation_memory', 1024)
        self.validation_time = kwargs.get('validation_time', 60)
        self.validation_memory = kwargs.get('validation_memory', 1024)
        self.validation_output = kwargs.get('validation_output', 8)

class ProblemConfig:
    def __init__(self, *, name, **kwargs):
        self.name = name
        self.type = kwargs.get('type', 'pass-fail')
        validator_flags = kwargs.get('validator_flags', "")
        output_validator_flags = kwargs.get('output_validator_flags', "")
        if validator_flags is None:
            validator_flags = ""
        if output_validator_flags is None:
            output_validator_flags = ""
        self.validator_flags = validator_flags.split() + output_validator_flags.split()
        self.limits = Limits(**kwargs.get('limits', {}))

def load_problem_config(filename):
    config = {}
    with open(filename) as config_file:
        config = yaml.safe_load(config_file)
    
    return ProblemConfig(**config)
