import os
import re

files_to_fix = [
    r"c:\Users\lazer\Nextcloud\cours réseau\Semestre 3\SAE\SAE 3.02- Développer une application communicante\src\simulation\moteur.py",
    r"c:\Users\lazer\Nextcloud\cours réseau\Semestre 3\SAE\SAE 3.02- Développer une application communicante\src\server_main.py"
]

for filepath in files_to_fix:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "import logging" not in content:
        content = "import logging\nlogger = logging.getLogger(__name__)\n\n" + content
        
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'print\(f?["\'].*(?:Erreur|Error|Crash).*["\'].*\)', line):
            # replace print with logger.error
            line = re.sub(r'print\((f?["\'].*(?:Erreur|Error|Crash).*["\'].*)\)', r'logger.error(\1, exc_info=True)', line)
            lines[i] = line
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
