import math
from dataclasses import dataclass


@dataclass
class ObstacleDetecte:
    entite: object
    distance: float
    angle_relatif: float


def normaliser_angle(angle: float) -> float:
    """Ramène un angle dans l'intervalle [-pi, pi]."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def objet_dans_secteur(
    x_v: float,
    y_v: float,
    cap: float,
    x_objet: float,
    y_objet: float,
    portee: float = 15.0,
    angle_ouverture: float = math.pi / 2,
) -> bool:
    """Indique si un objet est dans le secteur devant le véhicule."""

    dx = x_objet - x_v
    dy = y_objet - y_v

    distance = math.hypot(dx, dy)

    if distance > portee:
        return False

    # Un objet exactement à la position du véhicule
    # est considéré comme détecté.
    if distance < 1e-9:
        return True

    angle_objet = math.atan2(dy, dx)
    angle_relatif = normaliser_angle(angle_objet - cap)

    return abs(angle_relatif) <= angle_ouverture / 2.0


def detecter_obstacles(
    vehicule,
    entites,
    portee: float = 15.0,
    angle_ouverture: float = math.pi / 2,
) -> list[ObstacleDetecte]:
    """
    Détecte tous les types d'entités dans le secteur du véhicule.

    Ne décide ni de la priorité, ni du freinage.
    """

    obstacles = []

    for autre in entites:
        if autre is vehicule:
            continue

        dx = autre.pos_x - vehicule.pos_x
        dy = autre.pos_y - vehicule.pos_y
        distance = math.hypot(dx, dy)

        if objet_dans_secteur(
            vehicule.pos_x,
            vehicule.pos_y,
            vehicule.cap,
            autre.pos_x,
            autre.pos_y,
            portee,
            angle_ouverture,
        ):
            angle_relatif = normaliser_angle(
                math.atan2(dy, dx) - vehicule.cap
            )

            obstacles.append(
                ObstacleDetecte(
                    entite=autre,
                    distance=distance,
                    angle_relatif=angle_relatif,
                )
            )

    return obstacles
