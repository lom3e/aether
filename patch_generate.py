import os
import re

TEST_DIR = 'tests'

for root, dirs, files in os.walk(TEST_DIR):
    for file in files:
        if not file.endswith('.py'):
            continue
        filepath = os.path.join(root, file)
        
        with open(filepath, 'r') as f:
            content = f.read()

        new_content = ""
        lines = content.split('\n')
        
        for line in lines:
            # Fix response_format in test_planning
            if 'def generate(self, messages, tools=None, response_format=None):' in line:
                line = line.replace('response_format=None', 'output_schema=None')
            # Fix standard generate signatures
            elif 'def generate(self, messages, tools=None) -> ProviderResponse:' in line:
                line = line.replace('tools=None)', 'tools=None, output_schema=None)')
            elif 'def generate(self, messages, tools=None):' in line:
                line = line.replace('tools=None):', 'tools=None, output_schema=None):')
            elif 'def generate(self, messages: list, tools: list | None = None) -> ProviderResponse:' in line:
                line = line.replace('tools: list | None = None)', 'tools: list | None = None, output_schema=None)')
            elif 'def generate(self, messages: list[Message]) -> ProviderResponse:' in line:
                line = line.replace('messages: list[Message])', 'messages: list[Message], tools=None, output_schema=None)')
            
            new_content += line + '\n'
            
        # Strip trailing newline added by split if it wasn't there
        if not content.endswith('\n'):
            new_content = new_content[:-1]
            
        with open(filepath, 'w') as f:
            f.write(new_content)
