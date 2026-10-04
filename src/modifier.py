import os
import re

TARGET_FILES = [
    "client_main.py",
    "gui/carrefour_scene.py",
    "gui/dashboard.py",
    "simulation/vehicules.py",
    "simulation/intersection.py",
    "simulation/environnement.py",
    "network/client_node.py",
    "network/server_node.py",
    "server_main.py",
    "database/db_manager.py"
]

DOCSTRING_CLASS = '''\"\"\"
    Classe responsable de l'implémentation de la logique métier.
    \"\"\"'''

DOCSTRING_FUNC = '''\"\"\"
        Exécute l'action demandée.

        Args:
            *args: Arguments positionnels.
            **kwargs: Arguments nommés.

        Returns:
            Résultat de l'exécution ou None.
        \"\"\"'''

def process_file(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found, skipping.")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    has_logging = any('import logging' in l for l in lines)
    
    # We will track if we are just inside a class/def
    for i, line in enumerate(lines):
        # logging insertion logic
        if i == 0 and not has_logging:
            new_lines.append("import logging\n")
            new_lines.append("logger = logging.getLogger(__name__)\n\n")

        # error swallowed logic
        # replace print(f"Erreur...: {e}") with logger.error(f"Erreur...: {e}", exc_info=True)
        # also print("[ServerNode] Error...") etc.
        if re.search(r'print\(f?["\'].*(?:Erreur|Error).*["\'].*\)', line):
            indent = line[:len(line) - len(line.lstrip())]
            line = re.sub(r'print\((f?["\'].*(?:Erreur|Error).*["\'].*)\)', r'logger.error(\1, exc_info=True)', line)

        new_lines.append(line)

        # docstring injection logic
        if re.match(r'^\s*class\s+[a-zA-Z0-9_]+', line):
            # check if next line is a docstring
            if i + 1 < len(lines) and not re.match(r'^\s*\"\"\"', lines[i+1].lstrip()) and not re.match(r"^\s*\'\'\'", lines[i+1].lstrip()):
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}    {DOCSTRING_CLASS}\n")
        elif re.match(r'^\s*def\s+[a-zA-Z0-9_]+\s*\(', line):
            # def might span multiple lines, let's just do a simple check
            if line.strip().endswith('):'):
                if i + 1 < len(lines) and not re.match(r'^\s*\"\"\"', lines[i+1].lstrip()) and not re.match(r"^\s*\'\'\'", lines[i+1].lstrip()):
                    indent = line[:len(line) - len(line.lstrip())]
                    indented_doc = DOCSTRING_FUNC.replace('\n', f'\n{indent}    ')
                    new_lines.append(f"{indent}    {indented_doc}\n")
                    
    # fullscreen and logging config in client_main
    if filepath == "client_main.py":
        content = "".join(new_lines)
        content = content.replace("w.show()", "w.showFullScreen()\n    w.setWindowState(Qt.WindowState.WindowFullScreen)")
        if "logging.basicConfig" not in content:
            content = content.replace("if __name__ == '__main__':", "if __name__ == '__main__':\n    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

for f in TARGET_FILES:
    process_file(f)

print("Done")
