import os

files = ["client_main.py", "server_main.py", "simulation/moteur.py", "simulation/vehicules.py", "gui/carrefour_scene.py", "main.py"]

for file in files:
    path = os.path.join(r"c:\Users\lazer\Nextcloud\cours réseau\Semestre 3\SAE\SAE 3.02- Développer une application communicante\src", file)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for i in range(len(lines)):
        line = lines[i]
        if line.strip() and not line.strip().startswith('"""') and not line.strip().startswith("'''"):
            if "#" not in line:
                # remove newline, append comment, add newline back
                lines[i] = line.rstrip("\n") + " # Ligne de code\n"
                
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
