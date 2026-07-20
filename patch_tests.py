import os
import re

TEST_DIR = 'tests'

# Find all python files in tests directory
for root, dirs, files in os.walk(TEST_DIR):
    for file in files:
        if not file.endswith('.py'):
            continue
        filepath = os.path.join(root, file)
        
        with open(filepath, 'r') as f:
            content = f.read()

        needs_import = False
        new_content = ""
        
        # We look for `class X(AIProvider):` and inject the property if not there
        lines = content.split('\n')
        for i, line in enumerate(lines):
            new_content += line + '\n'
            match = re.search(r'^(\s*)class \w+\(AIProvider\):', line)
            if match:
                indent = match.group(1)
                
                # Check if it already has capabilities
                # (Simple check: if the next 10 lines don't have 'def capabilities')
                has_cap = False
                for j in range(1, 15):
                    if i + j < len(lines):
                        if 'def capabilities' in lines[i+j]:
                            has_cap = True
                            break
                        if 'class ' in lines[i+j] and not lines[i+j].startswith(indent + ' '):
                            break
                
                if not has_cap:
                    new_content += indent + '    @property\n'
                    new_content += indent + '    def capabilities(self):\n'
                    new_content += indent + '        from aether.providers.capabilities import ProviderCapabilities\n'
                    new_content += indent + '        return ProviderCapabilities()\n'
                    new_content += indent + '\n'
                    
        with open(filepath, 'w') as f:
            f.write(new_content)
