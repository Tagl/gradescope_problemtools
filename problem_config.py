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
        self.time_limit = None

    def __str__(self):
        lines = []
        if self.time_limit:
            lines.append(f"- Time Limit: {self.time_limit} seconds")
        lines.append(f"- Memory Limit: {self.memory} MiB")
        lines.append(f"- Output Limit: {self.output} KiB")
        lines.append(f"- Code Limit: {self.code} KiB")
        lines.append(f"- Compilation Time Limit: {self.compilation_time} seconds")
        return '\n'.join(lines)

class ProblemConfig:
    def __init__(self, *, name, **kwargs):
        self.name = name
        self.license = kwargs.get('license', 'unknown')
        self.rights_owner = kwargs.get('rights_owner', kwargs.get('author', "") or kwargs.get('source', ""))
        self.author = kwargs.get('author', "")
        self.source = kwargs.get('source', "")
        self.type = kwargs.get('type', 'pass-fail')
        validator_flags = kwargs.get('validator_flags', "")
        output_validator_flags = kwargs.get('output_validator_flags', "")
        if validator_flags is None:
            validator_flags = ""
        if output_validator_flags is None:
            output_validator_flags = ""
        self.validator_flags = validator_flags.split() + output_validator_flags.split()
        self.languages = kwargs.get('languages', None)
        if self.languages is not None:
            self.languages = set(self.languages.split())
        self.limits = Limits(**kwargs.get('limits', {}))

    def language_allowed(self, language_id):
        return self.languages is None or language_id in self.languages

    def __str__(self):
        lines = []
        if self.name:
            lines.append(f"- Name: {self.name}")
        if self.rights_owner and self.rights_owner != self.author and self.rights_owner != self.source:
            lines.append(f"- Rights owner: {self.rights_owner}")
        if self.source:
            lines.append(f"- Source: {self.source}")
        if self.author:
            authors = self.author.split()
            if len(self.author) == 1:
                lines.append(f"- Author: {authors[0]}")
            else:
                lines.append(f"- Authors:")
                for author in authors:
                    lines.append(f"    - {author}")

        lines.append(str(self.limits))

        return '\n'.join(lines)


def load_problem_config(filename):
    config = {}
    with open(filename) as config_file:
        config = yaml.safe_load(config_file)
    
    return ProblemConfig(**config)
