import sys
import time
from PyQt6.QtCore import QCoreApplication
from simulation.moteur import MoteurSimulation
from simulation.vehicules import Vehicule, TypeVehicule

app = QCoreApplication(sys.argv)

moteur = MoteurSimulation()

def on_tick(entites, inter):
    # Just to confirm the tick is working
    pass

moteur.tick_simulation.connect(on_tick)
moteur.demarrer()

start_time = time.time()
while time.time() - start_time < 3.0:
    app.processEvents()
    time.sleep(0.01)

moteur.arreter()
print("SUCCESS")
