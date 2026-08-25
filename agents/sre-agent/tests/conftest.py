"""Les tests de garde-fous tournent sur une machine débranchée.

Le traçage est coupé ici plutôt que dans chaque test : un exporteur qui
cherche un collecteur absent transforme un échec de test en attente de
délai, et brouille la lecture du résultat.
"""

import os

os.environ.setdefault("SRE_TRACAGE", "0")
