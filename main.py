# -*- coding: utf-8 -*-
"""SITADELO HISSABI — version téléphone (Kivy)."""
import os, sys, ast, math, json, re, hmac, hashlib, base64, operator, uuid
from fractions import Fraction
from datetime import datetime
from typing import List, Dict, Optional, Any

# ==============================================================================
# MODULE : CALCUL UNIVERSITAIRE ET ÉVALUATEUR SCIENTIFIQUE
# ==============================================================================

# ---------------------------------------------------------------------------
# Paramètres de validation (configurables depuis l'écran Paramètres)
# ---------------------------------------------------------------------------
class ReglesValidation:
    """Règles de validation configurables (persistées via sauvegarde.py)."""

    def __init__(self):
        self.note_minimale_validation = 10.0   # note finale >= 10 => matière validée
        self.moyenne_minimale_decision = 10.0  # moyenne générale >= 10 => validé

    def to_dict(self) -> dict:
        return {
            "note_minimale_validation": self.note_minimale_validation,
            "moyenne_minimale_decision": self.moyenne_minimale_decision,
        }

    def from_dict(self, data: dict):
        if not data:
            return
        self.note_minimale_validation = float(data.get(
            "note_minimale_validation", self.note_minimale_validation))
        self.moyenne_minimale_decision = float(data.get(
            "moyenne_minimale_decision", self.moyenne_minimale_decision))


REGLES = ReglesValidation()


# ---------------------------------------------------------------------------
# Fonctions utilitaires de conversion sécurisée
# ---------------------------------------------------------------------------
def to_float_securise(valeur, defaut: Optional[float] = None) -> Optional[float]:
    """
    Convertit une valeur texte en float sans jamais lever d'exception.
    Retourne `defaut` si la conversion est impossible.
    """
    if valeur is None:
        return defaut
    if isinstance(valeur, (int, float)):
        return float(valeur)
    texte = str(valeur).strip().replace(",", ".")
    if texte == "":
        return defaut
    try:
        return float(texte)
    except ValueError:
        return defaut


def mention_depuis_note(note: float) -> str:
    """Retourne la mention universitaire correspondant à une note /20."""
    if note is None:
        return "--"
    if note >= 16:
        return "Très Bien"
    if note >= 14:
        return "Bien"
    if note >= 12:
        return "Assez Bien"
    if note >= 10:
        return "Passable"
    return "Insuffisant"


# ---------------------------------------------------------------------------
# Calcul d'une matière
# ---------------------------------------------------------------------------
MSG_ET2_INUTILE = "Vous avez déjà la moyenne en ET1. Le rattrapage n'est pas nécessaire."


def _lire_cellule(valeur):
    """Distingue cellule VIDE, nombre valide (0 compris) et texte invalide.
    Retourne (etat, nombre) avec etat in {"vide", "ok", "invalide"}."""
    if valeur is None:
        return "vide", None
    if isinstance(valeur, bool):
        return "invalide", None
    if isinstance(valeur, (int, float)):
        return ("ok", float(valeur)) if math.isfinite(valeur) else ("invalide", None)
    texte = str(valeur).strip().replace(",", ".")
    if texte == "":
        return "vide", None
    try:
        v = float(texte)
    except ValueError:
        return "invalide", None
    return ("ok", v) if math.isfinite(v) else ("invalide", None)


def note_examen_retenue(et1, et2):
    """Règle ET1/ET2 (et1, et2 : float ou None). Retourne (note_retenue, source, et2_bloque)."""
    if et1 is None:
        return None, None, False
    if et1 >= 10:
        return et1, "ET1", et2 is not None          # ET2 interdit si ET1 >= 10
    if et2 is not None and et2 > et1:
        return et2, "ET2", False
    return et1, "ET1", False


def calculer_matiere(cc, session, coefficient, td=None, et2=None) -> Dict:
    """
    Calcule le résultat d'une matière. `session` = ET1 (clé conservée pour ne
    pas casser les données déjà enregistrées) ; `et2` = rattrapage.
    - CC et TD renseignés : (CC+TD)/2 compte pour 30 %, l'examen retenu pour 70 % ;
    - un seul des deux : cette note compte telle quelle pour 30 % ;
    - aucun des deux : l'examen compte pour 100 % ;
    - une cellule vide n'est JAMAIS un zéro ; un 0 saisi reste une note valide.
    Ne lève jamais d'exception.
    """
    resultat = {
        "note_finale": None, "moyenne_cc_td": None, "note_examen": None,
        "source_examen": None, "et2_ignore": False, "moy_cr": None,
        "credits_obtenus": 0.0, "resultat": "--", "mention": "--", "erreur": None,
        "avertissement": None,
    }
    e_cc, cc_val = _lire_cellule(cc)
    e_td, td_val = _lire_cellule(td)
    e_et1, et1_val = _lire_cellule(session)
    e_et2, et2_val = _lire_cellule(et2)
    coef_val = to_float_securise(coefficient)

    if "invalide" in (e_cc, e_td, e_et1, e_et2):
        resultat["erreur"] = "Veuillez entrer une valeur valide."
        return resultat
    if e_et1 == "vide":
        resultat["erreur"] = ("Veuillez entrer la note ET1." if e_et2 == "vide"
                              else "ET2 ne peut pas être saisi sans ET1.")
        return resultat
    if coef_val is None or coef_val <= 0:
        resultat["erreur"] = "Veuillez vérifier le coefficient/crédit."
        return resultat
    for v in (cc_val, td_val, et1_val, et2_val):
        if v is not None and not (0 <= v <= 20):
            resultat["erreur"] = "Veuillez vérifier les notes saisies (0 à 20)."
            return resultat

    retenue, source, et2_bloque = note_examen_retenue(et1_val, et2_val)
    if et2_bloque:
        resultat["et2_ignore"] = True
        resultat["avertissement"] = MSG_ET2_INUTILE

    if cc_val is not None and td_val is not None:
        controle = (cc_val + td_val) / 2.0
    elif cc_val is not None:
        controle = cc_val
    elif td_val is not None:
        controle = td_val
    else:
        controle = None

    if controle is None:
        brut = retenue                       # examen à 100 %
    else:
        brut = controle * 0.30 + retenue * 0.70
    note_finale = round(brut + 1e-9, 2)
    valide = note_finale >= REGLES.note_minimale_validation

    resultat["moyenne_cc_td"] = None if controle is None else round(controle, 2)
    resultat["note_examen"] = retenue
    resultat["source_examen"] = source
    resultat["note_finale"] = note_finale
    resultat["moy_cr"] = round(note_finale * coef_val, 2)     # points pondérés (pas une note /20)
    resultat["credits_obtenus"] = coef_val if valide else 0.0
    resultat["resultat"] = "Validée" if valide else "Non validée"
    resultat["mention"] = mention_depuis_note(note_finale)
    return resultat


# ---------------------------------------------------------------------------
# Compensation des matières
# ---------------------------------------------------------------------------
COULEURS_GROUPES_COMPENSATION = [
    "#1E88E5", "#8E24AA", "#00ACC1", "#F4511E",
    "#6D4C41", "#3949AB", "#D81B60", "#5E35B1",
]


def appliquer_compensation(lignes: List[Dict]) -> List[Dict]:
    """
    Règle de compensation :
      - une matière validée (note >= 10) a un "surplus" = (note - 10) x crédit ;
      - une matière non validée (note < 10) a un "déficit" = (10 - note) x crédit ;
      - PRIORITÉ AU CRÉDIT ÉGAL : une matière est d'abord aidée par une matière
        validée de MÊME crédit (son « frère ») dont le surplus couvre son déficit.
        Le plus grand crédit n'intervient que si aucun frère n'a la force de l'aider.
        Vaut pour tous les crédits (1, 2, 3, 4...) ;
      - à défaut, un crédit plus grand (le plus proche d'abord) prend le relais ;
      - une même matière peut compenser plusieurs matières tant que son
        surplus restant le permet (ex. Français 14 -> Arabe 9 et Anglais 8).
    Chaque matière donneuse reçoit une couleur automatique ; elle est reprise
    sur toutes les matières qu'elle compense (soulignement de même couleur).
    """
    seuil = REGLES.note_minimale_validation
    for ligne in lignes:
        ligne["compensation"] = False
        ligne["compensee_par"] = []
        ligne["compense"] = False
        ligne["compense_matieres"] = []
        ligne["compense_details"] = []
        ligne["couleur_compensation"] = None

    donneurs = []
    receveurs = []
    for ligne in lignes:
        note = ligne.get("note_finale")
        credit = ligne.get("coefficient") or 0.0
        if ligne.get("erreur") or note is None or credit <= 0:
            continue
        if note >= seuil:
            surplus = round((note - seuil) * credit, 6)
            if surplus > 0:
                donneurs.append({"ligne": ligne, "surplus": surplus})
        else:
            deficit = round((seuil - note) * credit, 6)
            if deficit > 0:
                receveurs.append({"ligne": ligne, "deficit": deficit})

    # Les plus gros crédits d'abord (ils ont le moins de donneurs possibles),
    # puis les plus petits déficits : on compense ainsi un maximum de matières.
    receveurs.sort(key=lambda r: (-(r["ligne"].get("coefficient") or 0.0), r["deficit"]))
    for receveur in receveurs:
        cible = receveur["ligne"]
        credit_cible = cible.get("coefficient") or 0.0
        capables = [
            d for d in donneurs
            if (d["ligne"].get("coefficient") or 0.0) >= credit_cible - 1e-9
            and d["surplus"] + 1e-9 >= receveur["deficit"]
        ]
        if not capables:
            continue
        # 1) le « frère » (même crédit) qui a la force -> il aide, le grand crédit n'est pas touché
        freres = [d for d in capables
                  if abs((d["ligne"].get("coefficient") or 0.0) - credit_cible) < 1e-9]
        if freres:
            donneur = min(freres, key=lambda d: d["surplus"])
        else:
            # 2) sinon le crédit supérieur le plus proche (puis le surplus le plus juste)
            donneur = min(capables, key=lambda d: (d["ligne"].get("coefficient") or 0.0,
                                                   d["surplus"]))
        donneur["surplus"] -= receveur["deficit"]
        source = donneur["ligne"]
        source["compense"] = True
        source.setdefault("_cibles", []).append(cible)
        cible["resultat"] = "Compensée"
        cible["compensation"] = True
        cible["compensee_par"] = [source.get("nom", "")]
        cible["credits_obtenus"] = credit_cible
        cible["mention"] = "Compensation"

    # Noms dans l'ordre du tableau + couleur automatique par matière donneuse.
    indice_groupe = 0
    for ligne in lignes:
        cibles = ligne.pop("_cibles", None)
        if not cibles:
            continue
        couleur = COULEURS_GROUPES_COMPENSATION[indice_groupe % len(COULEURS_GROUPES_COMPENSATION)]
        indice_groupe += 1
        cibles.sort(key=lambda c: c.get("n", 0))
        ligne["compense_matieres"] = [c.get("nom", "") for c in cibles]
        # Nom + crédit de chaque matière compensée (ex. Anglais 4 crédits)
        ligne["compense_details"] = [
            {"nom": c.get("nom", ""), "credit": c.get("coefficient") or 0.0}
            for c in cibles
        ]
        ligne["couleur_compensation"] = couleur
        for c in cibles:
            c["couleur_compensation"] = couleur
    return lignes


# ---------------------------------------------------------------------------
# Calcul global (moyenne générale, crédits, décision)
# ---------------------------------------------------------------------------
def calculer_bilan(matieres: List[Dict]) -> Dict:
    """
    matieres : liste de dicts { nom, cc, session, coefficient }
    Retourne un bilan complet, robuste face aux lignes vides ou incorrectes.
    """
    bilan = {
        "lignes": [],
        "moyenne_generale": None,
        "total_credits": 0.0,
        "total_points": 0.0,
        "credits_obtenus": 0.0,
        "credits_total_acquis": 0.0,
        "credits_valides": 0.0,
        "credits_compenses": 0.0,
        "credits_non_valides": 0.0,
        "nb_validees": 0,
        "nb_compensees": 0,
        "nb_non_validees": 0,
        "non_compensees": [],
        "mention": "--",
        "decision": "--",
        "erreurs": [],
    }

    if not matieres:
        bilan["erreurs"].append("Veuillez ajouter au moins une matière.")
        return bilan

    somme_ponderee = 0.0
    somme_coefficients = 0.0

    for i, m in enumerate(matieres, start=1):
        nom = (m.get("nom") or "").strip()
        if nom == "":
            bilan["erreurs"].append(f"Ligne {i} : nom de matière manquant.")

        res = calculer_matiere(m.get("cc"), m.get("session"), m.get("coefficient"), m.get("td"), m.get("et2"))
        ligne = {
            "n": i,
            "nom": nom if nom else f"Matière {i}",
            "cc": m.get("cc"),
            "td": m.get("td"),
            "session": m.get("session"),
            "et2": m.get("et2"),
            "coefficient": to_float_securise(m.get("coefficient"), 0.0),
            **res,
        }
        bilan["lignes"].append(ligne)

        if res["erreur"]:
            bilan["erreurs"].append(f"{ligne['nom']} : {res['erreur']}")
            continue

        coef = ligne["coefficient"] or 0.0
        somme_ponderee += res["note_finale"] * coef
        somme_coefficients += coef
        bilan["total_credits"] += coef
        bilan["total_points"] += res["moy_cr"]
        bilan["credits_obtenus"] += res["credits_obtenus"]

    # Compensation après calcul des notes individuelles.
    bilan["lignes"] = appliquer_compensation(bilan["lignes"])
    def _credits(resultat):
        return round(sum(
            (l.get("coefficient", 0.0) or 0.0)
            for l in bilan["lignes"] if l.get("resultat") == resultat
        ), 2)

    def _nombre(resultat):
        return sum(1 for l in bilan["lignes"] if l.get("resultat") == resultat)

    # Synthèse des UE : crédits validés + crédits compensés = crédits obtenus
    # (ex. 20 validés + 10 compensés = 30 crédits).
    bilan["credits_valides"] = _credits("Validée")
    bilan["nb_validees"] = _nombre("Validée")
    bilan["credits_compenses"] = _credits("Compensée")
    bilan["nb_compensees"] = _nombre("Compensée")
    bilan["credits_non_valides"] = _credits("Non validée")
    bilan["nb_non_validees"] = _nombre("Non validée")
    bilan["credits_obtenus"] = round(
        bilan["credits_valides"] + bilan["credits_compenses"], 2)
    bilan["credits_total_acquis"] = bilan["credits_obtenus"]
    bilan["non_compensees"] = [
        {"nom": l.get("nom", ""), "credit": l.get("coefficient") or 0.0,
         "note": l.get("note_finale")}
        for l in bilan["lignes"] if l.get("resultat") == "Non validée"
    ]

    if somme_coefficients > 0:
        moyenne = round(somme_ponderee / somme_coefficients, 2)
        bilan["moyenne_generale"] = moyenne
        bilan["total_points"] = round(bilan["total_points"], 2)
        bilan["mention"] = mention_depuis_note(moyenne)
        bilan["decision"] = (
            "Validé(e)" if moyenne >= REGLES.moyenne_minimale_decision else "Invalidé(e)"
        )

    return bilan


# ---------------------------------------------------------------------------
# Évaluateur sécurisé pour la calculatrice scientifique (CALC SIMPLE)
# ---------------------------------------------------------------------------
_OPERATEURS_AUTORISES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Mode d'angle de la calculatrice : "DEG" (degrés) ou "RAD" (radians)
_ETAT_CALCULATRICE = {"angle": "DEG"}
_LIMITE_PUISSANCE = 10000


class ErreurCalculScientifique(Exception):
    pass


def _angle_vers_radians(x):
    return math.radians(x) if _ETAT_CALCULATRICE["angle"] == "DEG" else x


def _radians_vers_angle(x):
    return math.degrees(x) if _ETAT_CALCULATRICE["angle"] == "DEG" else x


def _f_sin(x):
    return math.sin(_angle_vers_radians(x))


def _f_cos(x):
    return math.cos(_angle_vers_radians(x))


def _f_tan(x):
    r = _angle_vers_radians(x)
    if abs(math.cos(r)) < 1e-12:
        raise ErreurCalculScientifique("Tangente non définie pour cet angle.")
    return math.tan(r)


def _f_asin(x):
    if not -1 <= x <= 1:
        raise ErreurCalculScientifique("Valeur hors de l'intervalle [-1 ; 1].")
    return _radians_vers_angle(math.asin(x))


def _f_acos(x):
    if not -1 <= x <= 1:
        raise ErreurCalculScientifique("Valeur hors de l'intervalle [-1 ; 1].")
    return _radians_vers_angle(math.acos(x))


def _f_atan(x):
    return _radians_vers_angle(math.atan(x))


def _f_log(x):
    if x <= 0:
        raise ErreurCalculScientifique("Logarithme d'un nombre négatif ou nul impossible.")
    return math.log10(x)


def _f_ln(x):
    if x <= 0:
        raise ErreurCalculScientifique("Logarithme d'un nombre négatif ou nul impossible.")
    return math.log(x)


def _f_sqrt(x):
    if x < 0:
        raise ErreurCalculScientifique("Racine carrée d'un nombre négatif impossible.")
    return math.sqrt(x)


def _f_cbrt(x):
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def _f_fact(x):
    if x != int(x) or x < 0:
        raise ErreurCalculScientifique("La factorielle demande un entier positif.")
    if x > 170:
        raise ErreurCalculScientifique("Nombre trop grand.")
    return math.factorial(int(x))


_FONCTIONS_AUTORISEES = {
    "sqrt": _f_sqrt, "racine": _f_sqrt, "cbrt": _f_cbrt, "abs": abs,
    "fact": _f_fact, "factorielle": _f_fact,
    "sin": _f_sin, "cos": _f_cos, "tan": _f_tan,
    "asin": _f_asin, "acos": _f_acos, "atan": _f_atan,
    "log": _f_log, "ln": _f_ln, "exp": math.exp,
}

_CONSTANTES = {"pi": math.pi, "e": math.e}


def _evaluer_noeud(noeud, ans=None):
    if isinstance(noeud, ast.Expression):
        return _evaluer_noeud(noeud.body, ans)
    if isinstance(noeud, ast.Constant):
        if isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool):
            return noeud.value
        raise ErreurCalculScientifique("Valeur non numérique.")
    if isinstance(noeud, ast.Name):
        if noeud.id in _CONSTANTES:
            return _CONSTANTES[noeud.id]
        if noeud.id == "ans":
            if ans is None:
                raise ErreurCalculScientifique("Aucune réponse précédente (ANS).")
            return ans
        raise ErreurCalculScientifique(f"Symbole inconnu : {noeud.id}")
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPERATEURS_AUTORISES:
        gauche = _evaluer_noeud(noeud.left, ans)
        droite = _evaluer_noeud(noeud.right, ans)
        if isinstance(noeud.op, (ast.Div, ast.Mod)) and droite == 0:
            raise ErreurCalculScientifique("Division par zéro.")
        if isinstance(noeud.op, ast.Pow) and abs(droite) > _LIMITE_PUISSANCE:
            raise ErreurCalculScientifique("Puissance trop grande.")
        return _OPERATEURS_AUTORISES[type(noeud.op)](gauche, droite)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _OPERATEURS_AUTORISES:
        return _OPERATEURS_AUTORISES[type(noeud.op)](_evaluer_noeud(noeud.operand, ans))
    if isinstance(noeud, ast.Call):
        nom = getattr(noeud.func, "id", None)
        if nom not in _FONCTIONS_AUTORISEES or noeud.keywords:
            raise ErreurCalculScientifique("Fonction non autorisée.")
        if len(noeud.args) != 1:
            raise ErreurCalculScientifique("Il manque un nombre dans la parenthèse.")
        argument = _evaluer_noeud(noeud.args[0], ans)
        return _FONCTIONS_AUTORISEES[nom](argument)
    raise ErreurCalculScientifique("Expression non valide.")


def preparer_expression(expression: str):
    """
    Transforme ce que la personne tape (√9, 2(3+4), 5!, 50%, x², π, virgules,
    parenthèses non fermées...) en expression que l'évaluateur comprend.
    Retourne (texte, erreur).
    """
    t = str(expression).strip().lower().replace(" ", "")
    t = (t.replace("×", "*").replace("÷", "/").replace("−", "-")
          .replace("²", "^2").replace("³", "^3").replace("π", "pi").replace(",", "."))
    # √9  ->  sqrt(9)   ;   √(...)  ->  sqrt(...)
    t = re.sub(r"√(\d+(?:\.\d+)?|pi|ans)", r"sqrt(\1)", t)
    t = t.replace("√", "sqrt")
    # Pourcentage : 50% -> (50/100)
    t = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", t)
    t = t.replace("%", "/100")
    # Factorielle : 5! ou (3+2)!
    while "!" in t:
        i = t.index("!")
        if i == 0:
            return None, "Factorielle mal placée."
        if t[i - 1] == ")":
            profondeur, j = 0, i - 1
            while j >= 0:
                if t[j] == ")":
                    profondeur += 1
                elif t[j] == "(":
                    profondeur -= 1
                    if profondeur == 0:
                        break
                j -= 1
            if j < 0:
                return None, "Parenthèses incorrectes."
            t = t[:j] + "fact" + t[j:i] + t[i + 1:]
        else:
            m = re.search(r"(\d+(?:\.\d+)?|pi|ans)$", t[:i])
            if not m:
                return None, "Factorielle mal placée."
            t = t[:m.start()] + "fact(" + m.group(1) + ")" + t[i + 1:]
    t = t.replace("^", "**")
    # Zéros inutiles au début d'un nombre : 007 -> 7 (Python les refuse)
    t = re.sub(r"(?<![\d.])0+(?=\d)", "", t)
    # Multiplication implicite : 2(3+4), 2sin(30), (1+2)(3+4), (2)3, 2pi
    t = re.sub(r"(?<=[\d\)])(?=\()", "*", t)
    t = re.sub(r"(?<=[\d\)])(?=[a-z])", "*", t)
    t = re.sub(r"(?<=\))(?=\d)", "*", t)
    t = re.sub(r"\b(pi|e|ans)\b(?=\()", r"\1*", t)
    # Parenthèses : on referme automatiquement celles qui manquent
    ouvertes, fermees = t.count("("), t.count(")")
    if fermees > ouvertes:
        return None, "Parenthèse fermante en trop."
    t += ")" * (ouvertes - fermees)
    return t, None


def evaluer_expression_securisee(expression: str, ans=None):
    """
    Évalue une expression mathématique de façon sécurisée (jamais d'eval()).
    Supporte + - * / % ^ ( ) x² √ ! π e ANS, sin cos tan asin acos atan,
    log ln exp abs cbrt. `ans` = dernier résultat pour la touche ANS.
    Retourne (resultat, erreur). L'un des deux vaut toujours None.
    """
    if not expression or not expression.strip():
        return None, "Veuillez entrer une expression valide."
    texte, erreur = preparer_expression(expression)
    if erreur:
        return None, erreur
    try:
        arbre = ast.parse(texte, mode="eval")
        resultat = _evaluer_noeud(arbre, ans)
        if isinstance(resultat, complex):
            return None, "Résultat non réel."
        resultat = float(resultat)
        if math.isnan(resultat) or math.isinf(resultat):
            return None, "Résultat non défini."
        return round(resultat, 10), None
    except ZeroDivisionError:
        return None, "Division par zéro."
    except ErreurCalculScientifique as e:
        return None, str(e)
    except OverflowError:
        return None, "Nombre trop grand."
    except (RecursionError, MemoryError):
        return None, "Expression trop complexe."
    except Exception:
        return None, "Expression invalide."


def formater_nombre(valeur) -> str:
    """Affiche 5.0 -> 5, 0.1000000 -> 0.1 (jamais de zéros inutiles)."""
    if valeur is None:
        return "--"
    valeur = float(valeur)
    if valeur == 0:
        return "0"
    if abs(valeur) >= 1e15 or abs(valeur) < 1e-9:
        return f"{valeur:.10g}"
    texte = f"{valeur:.10f}".rstrip("0").rstrip(".")
    return "0" if texte in ("-0", "") else texte

# ==============================================================================
# MODULE : ALGÈBRE (CALC SIMPLE)
#   monômes, binômes, trinômes, polynômes, parenthèses, Δ (discriminant),
#   développement et factorisation automatiques.
#   Ex. : a+a -> 2a ; a+b -> a+b ; a/a -> 1 ; a*b -> ab ; (x+1)² -> x²+2x+1
# ==============================================================================

class ErreurAlgebre(Exception):
    pass


# Monôme = tuple trié de (lettre, exposant) ; polynôme = {monôme: coefficient}
def _mono_norm(d):
    return tuple(sorted((v, e) for v, e in d.items() if e))


def _mono_mul(m1, m2):
    d = dict(m1)
    for v, e in m2:
        d[v] = d.get(v, 0) + e
    return _mono_norm(d)


def _mono_div(m1, m2):
    """m1 / m2 ; None si m2 ne divise pas m1."""
    d = dict(m1)
    for v, e in m2:
        r = d.get(v, 0) - e
        if r < 0:
            return None
        d[v] = r
    return _mono_norm(d)


def _mono_deg(m):
    return sum(e for _, e in m)


def _vec(m, vs):
    d = dict(m)
    return tuple(d.get(v, 0) for v in vs)


class Poly:
    __slots__ = ("t",)

    def __init__(self, t=None):
        self.t = {m: c for m, c in (t or {}).items() if c != 0}

    @staticmethod
    def const(c):
        return Poly({(): Fraction(c)})

    @staticmethod
    def var(v, e=1):
        return Poly({((v, e),): Fraction(1)})

    def est_nul(self):
        return not self.t

    def est_const(self):
        return all(m == () for m in self.t)

    def val_const(self):
        return self.t.get((), Fraction(0))

    def variables(self):
        return sorted({v for m in self.t for v, _ in m})

    def degre(self, v):
        return max((dict(m).get(v, 0) for m in self.t), default=0)

    def scale(self, k):
        return Poly({m: c * k for m, c in self.t.items()})

    def __add__(self, o):
        t = dict(self.t)
        for m, c in o.t.items():
            t[m] = t.get(m, 0) + c
        return Poly(t)

    def __neg__(self):
        return self.scale(-1)

    def __sub__(self, o):
        return self + (-o)

    def __mul__(self, o):
        if len(self.t) * len(o.t) > 20000:
            raise ErreurAlgebre("Expression trop grande.")
        t = {}
        for m1, c1 in self.t.items():
            for m2, c2 in o.t.items():
                m = _mono_mul(m1, m2)
                t[m] = t.get(m, 0) + c1 * c2
        return Poly(t)

    def __pow__(self, n):
        r = Poly.const(1)
        for _ in range(n):
            r = r * self
        return r

    def __eq__(self, o):
        return isinstance(o, Poly) and self.t == o.t

    def __hash__(self):
        return hash(frozenset(self.t.items()))


UN = Poly.const(1)


def _lead(P, vs):
    m = max(P.t, key=lambda k: _vec(k, vs))
    return m, P.t[m]


def _div_exacte(P, D):
    """Q tel que P = Q x D (division par ordre lexicographique) ; None si non exacte."""
    if D.est_nul():
        return None
    if P.est_nul():
        return Poly()
    vs = sorted(set(P.variables()) | set(D.variables()))
    md, cd = _lead(D, vs)
    Q, R = {}, Poly(P.t)
    for _ in range(5000):
        if R.est_nul():
            return Poly(Q)
        mr, cr = _lead(R, vs)
        m = _mono_div(mr, md)
        if m is None:
            return None
        c = cr / cd
        Q[m] = Q.get(m, 0) + c
        R = R - Poly({m: c}) * D
    return None


def _pgcd_monomes(polys):
    g = None
    for P in polys:
        for m in P.t:
            d = dict(m)
            g = dict(d) if g is None else {v: min(e, d.get(v, 0)) for v, e in g.items()}
    return _mono_norm(g or {})


def _div_mono(P, g):
    return Poly({_mono_div(m, g): c for m, c in P.t.items()})


def _contenu_primitif(P):
    """P = c x Q ; Q à coefficients entiers premiers entre eux, coefficient de tête > 0."""
    L = 1
    for c in P.t.values():
        L = L * c.denominator // math.gcd(L, c.denominator)
    g = 0
    for c in P.t.values():
        g = math.gcd(g, int(c * L))
    c = Fraction(g, L)
    Q = P.scale(1 / c)
    _, cl = _lead(Q, P.variables())
    if cl < 0:
        c, Q = -c, -Q
    return c, Q


# ---- polynômes à une seule lettre (listes de coefficients, degré croissant) ----
def _uni(P, v):
    d = {}
    for m, c in P.t.items():
        md = dict(m)
        e = md.pop(v, 0)
        if md:
            return None
        d[e] = c
    n = max(d) if d else 0
    return [d.get(i, Fraction(0)) for i in range(n + 1)]


def _de_uni(coefs, v):
    return Poly({(((v, i),) if i else ()): c for i, c in enumerate(coefs) if c})


def _uni_reste(a, b):
    a = list(a)
    while a and a[-1] == 0:
        a.pop()
    while b and b[-1] == 0:
        b = b[:-1]
    while len(a) >= len(b) > 0:
        k = a[-1] / b[-1]
        s = len(a) - len(b)
        for i, c in enumerate(b):
            a[s + i] -= k * c
        while a and a[-1] == 0:
            a.pop()
    return a


def _uni_pgcd(a, b):
    a = [c for c in a]
    b = [c for c in b]
    while b and any(b):
        a, b = b, _uni_reste(a, b)
    while a and a[-1] == 0:
        a.pop()
    return [c / a[-1] for c in a] if a else a


# ---- fraction rationnelle : numérateur / dénominateur, toujours simplifiée ----
def _normaliser(n, d):
    if d.est_nul():
        raise ErreurAlgebre("Division par zéro.")
    if n.est_nul():
        return Poly(), UN
    for _ in range(4):
        if d.est_const():
            return n.scale(1 / d.val_const()), UN
        q = _div_exacte(n, d)
        if q is not None:
            return q, UN
        change = False
        if not n.est_const():
            q = _div_exacte(d, n)
            if q is not None:
                n, d, change = UN, q, True
                continue
        g = _pgcd_monomes([n, d])
        if g:
            n, d, change = _div_mono(n, g), _div_mono(d, g), True
        vs = sorted(set(n.variables()) | set(d.variables()))
        if len(vs) == 1:
            a, b = _uni(n, vs[0]), _uni(d, vs[0])
            if a and b:
                gc = _uni_pgcd(a, b)
                if len(gc) > 1:
                    G = _de_uni(gc, vs[0])
                    n, d, change = _div_exacte(n, G), _div_exacte(d, G), True
        if not change:
            break
    c, dp = _contenu_primitif(d)
    return n.scale(1 / c), dp


class Rat:
    __slots__ = ("n", "d")

    def __init__(self, n, d=None):
        self.n, self.d = _normaliser(n, d if d is not None else UN)

    @staticmethod
    def const(c):
        return Rat(Poly.const(c))

    @staticmethod
    def var(v):
        return Rat(Poly.var(v))

    def __add__(s, o):
        return Rat(s.n * o.d + o.n * s.d, s.d * o.d)

    def __neg__(s):
        return Rat(-s.n, s.d)

    def __sub__(s, o):
        return s + (-o)

    def __mul__(s, o):
        return Rat(s.n * o.n, s.d * o.d)

    def __truediv__(s, o):
        if o.n.est_nul():
            raise ErreurAlgebre("Division par zéro.")
        return Rat(s.n * o.d, s.d * o.n)

    def __pow__(s, k):
        if k >= 0:
            return Rat(s.n ** k, s.d ** k)
        if s.n.est_nul():
            raise ErreurAlgebre("Division par zéro.")
        return Rat(s.d ** (-k), s.n ** (-k))

    def entier(s):
        if s.n.est_const() and s.d.est_const():
            v = s.n.val_const() / s.d.val_const()
            if v.denominator == 1 and abs(v) <= 60:
                return int(v)
        raise ErreurAlgebre("L'exposant doit être un entier (de -60 à 60).")


# ---- lecture de l'expression ---------------------------------------------------
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_FONCTIONS_NUMERIQUES = ("sqrt", "racine", "cbrt", "abs", "fact", "factorielle", "sin", "cos",
                         "tan", "asin", "acos", "atan", "log", "ln", "exp")
_MOTS_NUMERIQUES = set(_FONCTIONS_NUMERIQUES) | {"pi", "e", "ans"}


def _nettoyer_algebre(expression):
    t = str(expression).lower()
    t = re.sub(r"\bfois\b", "*", t)
    t = (t.replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", "."))
    t = re.sub(r"[" + _SUPERSCRIPTS + r"]+",
               lambda m: "^" + "".join(str(_SUPERSCRIPTS.index(ch)) for ch in m.group(0)), t)
    return t.replace(" ", "")


def est_expression_algebrique(expression):
    """Vrai si l'expression contient des lettres qui sont des inconnues (x, a, b...)."""
    t = _nettoyer_algebre(expression)
    mots = re.findall(r"[a-zπ]+", t)
    return any(m not in _MOTS_NUMERIQUES for m in mots)


def extraire_delta(expression):
    """Si l'expression commence par Δ (ou « delta »), retourne le reste ; sinon None."""
    m = re.match(r"^\s*(?:Δ|δ|delta)\s*[:=]?\s*(.*)$", str(expression), re.IGNORECASE)
    return m.group(1) if m else None


def _tokeniser(t):
    tokens, i = [], 0
    while i < len(t):
        ch = t[i]
        m = re.match(r"\d+(?:\.\d+)?|\.\d+", t[i:])
        if m:
            tokens.append(("num", Fraction(m.group(0))))
            i += m.end()
        elif ch.isalpha():
            tokens.append(("var", ch))
            i += 1
        elif ch in "+-*/^()":
            tokens.append((ch, None))
            i += 1
        else:
            raise ErreurAlgebre(f"Symbole non pris en charge en algèbre : {ch}")
    return tokens


class _Parseur:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def suivant(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self):
        v = self.terme()
        while self.peek() in ("+", "-"):
            op = self.suivant()[0]
            w = self.terme()
            v = v + w if op == "+" else v - w
        return v

    def terme(self):
        v = self.unaire()
        while True:
            p = self.peek()
            if p in ("*", "/"):
                self.suivant()
                w = self.unaire()
                v = v * w if p == "*" else v / w
            elif p in ("num", "var", "("):          # multiplication implicite : 2x, ab, 2(x+1)
                v = v * self.puissance()
            else:
                return v

    def unaire(self):
        if self.peek() in ("+", "-"):
            op = self.suivant()[0]
            v = self.unaire()
            return -v if op == "-" else v
        return self.puissance()

    def puissance(self):
        base = self.atome()
        if self.peek() == "^":
            self.suivant()
            base = base ** self.unaire().entier()
        return base

    def atome(self):
        p = self.peek()
        if p == "num":
            return Rat.const(self.suivant()[1])
        if p == "var":
            return Rat.var(self.suivant()[1])
        if p == "(":
            self.suivant()
            v = self.expr()
            if self.peek() == ")":
                self.suivant()
            elif self.peek() is not None:
                raise ErreurAlgebre("Parenthèses incorrectes.")
            return v
        raise ErreurAlgebre("Expression incomplète.")


def lire_rat(expression, ans=None):
    t = _nettoyer_algebre(expression)
    if re.search(r"(?:" + "|".join(_FONCTIONS_NUMERIQUES) + r")\(", t) or "√" in t or "!" in t or "%" in t:
        raise ErreurAlgebre("Les fonctions (sin, ln, √, !, %...) ne se mélangent pas avec des lettres.")
    if ans is not None:
        t = re.sub(r"(?<![a-z])ans(?![a-z])", "(" + formater_nombre(ans) + ")", t)
    if t == "":
        raise ErreurAlgebre("Veuillez entrer une expression valide.")
    p = _Parseur(_tokeniser(t))
    r = p.expr()
    if p.peek() is not None:
        raise ErreurAlgebre("Parenthèse fermante en trop." if p.peek() == ")" else "Expression invalide.")
    return r


# ---- affichage -------------------------------------------------------------------
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _sup(n):
    return "" if n == 1 else str(n).translate(_SUP)


def _mono_txt(m):
    return "".join(v + _sup(e) for v, e in m)


def _fr(c):
    c = Fraction(c)
    return str(c.numerator) if c.denominator == 1 else f"{c.numerator}/{c.denominator}"


def _par(c):
    c = Fraction(c)
    return f"({_fr(c)})" if (c < 0 or c.denominator != 1) else _fr(c)


def _poly_txt(P):
    if P.est_nul():
        return "0"
    vs = P.variables()
    ordre = sorted(P.t, key=lambda m: (_mono_deg(m), _vec(m, vs)), reverse=True)
    out = ""
    for k, m in enumerate(ordre):
        c = P.t[m]
        a, mt = abs(c), _mono_txt(m)
        if mt:
            corps = ("" if a.numerator == 1 else str(a.numerator)) + mt
            if a.denominator != 1:
                corps += "/" + str(a.denominator)
        else:
            corps = _fr(a)
        out += ("-" if c < 0 else ("+" if k else "")) + corps
    return out


def _rat_txt(R):
    if R.d.est_const():
        return _poly_txt(R.n)
    nt, dt = _poly_txt(R.n), _poly_txt(R.d)
    if len(R.n.t) > 1:
        nt = "(" + nt + ")"
    termes_d = list(R.d.t.items())
    simple = len(termes_d) == 1 and termes_d[0][1] == 1 and len(termes_d[0][0]) <= 1
    if not simple:
        dt = "(" + dt + ")"
    return nt + "/" + dt


def _nature(P):
    vs = P.variables()
    if not vs:
        return None
    k = len(P.t)
    nom = {1: "monôme", 2: "binôme", 3: "trinôme"}.get(k, f"polynôme de {k} termes")
    deg = max(_mono_deg(m) for m in P.t)
    if len(vs) == 1:
        return f"{nom} du {deg}{'er' if deg == 1 else 'e'} degré en {vs[0]}"
    return f"{nom} de degré {deg} en {', '.join(vs)}"


# ---- factorisation -----------------------------------------------------------------
def _diviseurs(n):
    res = set()
    for i in range(1, math.isqrt(n) + 1):
        if n % i == 0:
            res.add(i)
            res.add(n // i)
    return sorted(res)


def _racine_rationnelle(coefs):
    L = 1
    for c in coefs:
        L = L * c.denominator // math.gcd(L, c.denominator)
    ent = [int(c * L) for c in coefs]
    a0, an = abs(ent[0]), abs(ent[-1])
    if a0 == 0 or a0 > 10 ** 9 or an > 10 ** 9:
        return None
    for p in _diviseurs(a0):
        for q in _diviseurs(an):
            if math.gcd(p, q) != 1:
                continue
            for s in (1, -1):
                r = Fraction(s * p, q)
                v = Fraction(0)
                for c in reversed(coefs):
                    v = v * r + c
                if v == 0:
                    return r
    return None


def _racine_fraction(c):
    c = Fraction(c)
    if c < 0:
        return None
    rn, rd = math.isqrt(c.numerator), math.isqrt(c.denominator)
    if rn * rn == c.numerator and rd * rd == c.denominator:
        return Fraction(rn, rd)
    return None


def _racine_carree_poly(P):
    """S tel que S² = P, ou None."""
    if P.est_nul():
        return Poly()
    vs = P.variables()
    m, c = _lead(P, vs)
    rc = _racine_fraction(c)
    if rc is None or any(e % 2 for _, e in m):
        return None
    m1 = tuple((v, e // 2) for v, e in m)
    S = Poly({m1: rc})
    for _ in range(len(P.t) + 6):
        R = P - S * S
        if R.est_nul():
            return S
        mr, cr = _lead(R, vs)
        tm = _mono_div(mr, m1)
        if tm is None:
            return None
        S = S + Poly({tm: cr / (2 * rc)})
    return None


def _coefs_en(P, v):
    res = {}
    for m, c in P.t.items():
        md = dict(m)
        e = md.pop(v, 0)
        res.setdefault(e, Poly())
        res[e] = res[e] + Poly({_mono_norm(md): c})
    return res


def _irreductibles(Q):
    """Facteurs irréductibles (sur Q) d'un polynôme primitif sans facteur monôme."""
    if Q.est_const():
        return []
    vs = Q.variables()
    if len(vs) == 1:
        v = vs[0]
        cur, facteurs = _uni(Q, v), []
        while len(cur) > 2:
            r = _racine_rationnelle(cur)
            if r is None:
                break
            facteurs.append(Poly({((v, 1),): Fraction(r.denominator), (): Fraction(-r.numerator)}))
            nouveau, reste = [Fraction(0)] * (len(cur) - 1), Fraction(0)
            for i in range(len(cur) - 1, 0, -1):     # division synthétique par (x - r)
                reste = cur[i] + reste * r
                nouveau[i - 1] = reste
            cur = nouveau
        R = _contenu_primitif(_de_uni(cur, v))[1]
        if not R.est_const():
            facteurs.append(R)
        return facteurs
    for v in vs:
        d = Q.degre(v)
        co = _coefs_en(Q, v)
        if d == 1:
            A, B = co.get(1, Poly()), co.get(0, Poly())
            if not A.est_const():
                q = _div_exacte(B, A)
                if q is not None:
                    return _irreductibles(_contenu_primitif(A)[1]) + [Poly.var(v) + q]
            if not B.est_const():
                q = _div_exacte(A, B)
                if q is not None:
                    return _irreductibles(_contenu_primitif(B)[1]) + [Poly.var(v) * q + UN]
        elif d == 2:
            A, B, C = co.get(2, Poly()), co.get(1, Poly()), co.get(0, Poly())
            S = _racine_carree_poly(B * B - A * C.scale(4))
            if S is not None:
                base = A * Poly.var(v).scale(2) + B
                g1, g2 = _contenu_primitif(base - S)[1], _contenu_primitif(base + S)[1]
                if not g1.est_const() and not g2.est_const():
                    prod = g1 * g2
                    vt = sorted(set(Q.variables()) | set(prod.variables()))
                    mq, cq = _lead(Q, vt)
                    mp, cp = _lead(prod, vt)
                    if mq == mp and prod.scale(cq / cp) == Q:
                        return _irreductibles(g1) + _irreductibles(g2)
    return [Q]


def factoriser(P):
    """Retourne (constante, [(facteur, exposant), ...]) avec P = constante x produit."""
    if P.est_nul():
        return Fraction(0), []
    if P.est_const():
        return P.val_const(), []
    c, Q = _contenu_primitif(P)
    g = _pgcd_monomes([Q])
    monomes = [Poly.var(v) for v, e in g for _ in range(e)]
    if g:
        Q = _div_mono(Q, g)
    liste = monomes + _irreductibles(Q)
    compte = {}
    for F in liste:
        compte[F] = compte.get(F, 0) + 1
    facteurs = sorted(compte.items(), key=lambda fe: (
        0 if len(fe[0].t) == 1 else 1, max(_mono_deg(m) for m in fe[0].t), _poly_txt(fe[0])))
    prod = Poly.const(1)
    for F, e in facteurs:
        prod = prod * (F ** e)
    vt = P.variables()
    mp, cp = _lead(P, vt)
    mq, cq = _lead(prod, vt)
    k = cp / cq if mp == mq else None
    if k is None or prod.scale(k) != P:
        return Fraction(1), [(P, 1)]
    return k, facteurs


def _facto_txt(k, facteurs):
    if k == 1 and len(facteurs) == 1 and facteurs[0][1] == 1:
        return _poly_txt(facteurs[0][0])
    parts = []
    for F, e in facteurs:
        t = _poly_txt(F)
        parts.append(("(" + t + ")" if len(F.t) > 1 else t) + _sup(e))
    corps = "".join(parts)
    if k == 1:
        pre = ""
    elif k == -1:
        pre = "-"
    else:
        pre = _fr(k) if k.denominator == 1 else "(" + _fr(k) + ")"
    return (pre + corps) or "1"


def _facto_rat_txt(R):
    cn, fn = factoriser(R.n)
    if R.d.est_const():
        return _facto_txt(cn, fn)
    cd, fd = factoriser(R.d)
    num, den = _facto_txt(cn / cd, fn), _facto_txt(Fraction(1), fd)
    if not re.fullmatch(r"[a-zπ]|\([^()]*\)[⁰¹²³⁴⁵⁶⁷⁸⁹]*", den):
        den = "(" + den + ")"
    return num + "/" + den


# ---- discriminant Δ -----------------------------------------------------------------
def _sqrt_simplifiee(n):
    k, r, i = 1, n, 2
    while n <= 10 ** 12 and i * i <= r:
        while r % (i * i) == 0:
            r //= i * i
            k *= i
        i += 1
    return k, r


def analyser_delta(P):
    """Étapes du discriminant d'un trinôme ax²+bx+c. Retourne (Δ, lignes)."""
    vs = P.variables()
    if len(vs) != 1:
        raise ErreurAlgebre("Δ demande un trinôme à une seule lettre : ax²+bx+c (ex. x²-3x+2).")
    v = vs[0]
    co = _uni(P, v)
    if len(co) != 3:
        raise ErreurAlgebre("Δ demande un polynôme du 2e degré : ax²+bx+c.")
    c, b, a = co
    delta = b * b - 4 * a * c
    x1, x2 = f"{v}₁", f"{v}₂"
    lignes = [
        f"Forme ax²+bx+c : a = {_fr(a)}, b = {_fr(b)}, c = {_fr(c)}",
        f"Δ = b² - 4ac = {_par(b)}² - 4×{_par(a)}×{_par(c)} = {_fr(delta)}",
    ]
    if delta > 0:
        s = _racine_fraction(delta)
        if s is not None:
            r1, r2 = (-b - s) / (2 * a), (-b + s) / (2 * a)
            lignes.append("Δ > 0 : deux racines réelles distinctes")
            lignes.append(f"{x1} = (-b - √Δ)/2a = {_fr(r1)}   et   {x2} = (-b + √Δ)/2a = {_fr(r2)}")
        else:
            val = math.sqrt(float(delta))
            r1, r2 = (float(-b) - val) / float(2 * a), (float(-b) + val) / float(2 * a)
            lignes.append("Δ > 0 : deux racines réelles distinctes")
            if delta.denominator == 1 and b.denominator == 1 and a.denominator == 1:
                k, r = _sqrt_simplifiee(int(delta))
                g = math.gcd(math.gcd(abs(int(b)), k), abs(int(2 * a)))
                sig = 1 if a > 0 else -1
                nb, kk, den = sig * int(-b) // g, k // g, abs(int(2 * a)) // g

                def _forme(signe):
                    rac = (str(kk) if kk != 1 else "") + f"√{r}"
                    haut = (str(nb) if nb else "") + (" + " if signe > 0 else " - ") + rac if nb else \
                        (rac if signe > 0 else "-" + rac)
                    if den == 1:
                        return haut
                    return f"({haut})/{den}" if nb else f"{haut}/{den}"
                lignes.append(f"{x1} = (-b - √Δ)/2a = {_forme(-sig)}   et   {x2} = {_forme(sig)}")
            lignes.append(f"{x1} ≈ {r1:.6g}   et   {x2} ≈ {r2:.6g}")
    elif delta == 0:
        lignes.append("Δ = 0 : une racine double")
        lignes.append(f"{v}₀ = -b/2a = {_fr(-b / (2 * a))}")
    else:
        lignes.append("Δ < 0 : aucune racine réelle")
        s2 = _racine_fraction(-delta)
        if s2 is not None:
            lignes.append(f"Racines complexes : {v} = {_fr(-b / (2 * a))} ± {_fr(abs(s2 / (2 * a)))}i")
        else:
            lignes.append(f"Racines complexes : {v} = (-b ± i√{_fr(-delta)})/2a")
    return delta, lignes


# ---- points d'entrée pour la calculatrice ------------------------------------------------
def calcul_algebrique(expression, ans=None):
    """Retourne (résultat_développé, lignes_de_détails). Lève ErreurAlgebre si impossible."""
    R = lire_rat(expression, ans)
    resultat = _rat_txt(R)
    details = []
    if R.d.est_const():
        nat = _nature(R.n)
        if nat:
            details.append("Nature : " + nat)
    else:
        details.append("Nature : fraction rationnelle")
    facto = _facto_rat_txt(R)
    if facto != resultat and not R.n.est_const():
        details.append("Factorisé : " + facto)
    if R.d.est_const() and len(R.n.variables()) == 1 and R.n.degre(R.n.variables()[0]) == 2:
        try:
            details.extend(analyser_delta(R.n)[1])
        except ErreurAlgebre:
            pass
    return resultat, details


def calcul_delta(expression, ans=None):
    """Bouton Δ : retourne (texte_Δ, lignes)."""
    R = lire_rat(expression, ans)
    if not R.d.est_const():
        raise ErreurAlgebre("Δ demande un trinôme ax²+bx+c (pas une fraction).")
    delta, lignes = analyser_delta(R.n)
    facto = _facto_rat_txt(R)
    if facto == _rat_txt(R):
        lignes.append("Factorisé : " + facto + "  (pas de racine rationnelle)")
    else:
        lignes.append("Factorisé : " + facto)
    return _fr(delta), lignes



PALETTES = {
    "Bleu Hissabi": "#0B3D91", "Bleu ciel": "#2196F3", "Ardoise": "#607D8B",
    "Rouge": "#C62828", "Violet": "#6A1B9A", "Vert": "#2E7D32",
    "Orange": "#EF6C00", "Jaune": "#F9A825", "Turquoise": "#00897B",
    "Noir": "#212121", "Rose": "#D81B60", "Indigo": "#283593",
    "Marron": "#5D4037", "Citron vert": "#7CB342", "Cyan": "#00ACC1",
    "Bordeaux": "#880E4F", "Olive": "#827717", "Corail": "#FF7043",
    "Lavande": "#7E57C2", "Or": "#B8860B",
}

ORDRE_PALETTES = list(PALETTES.keys())

def _hex_vers_rgb(couleur_hex: str):
    couleur_hex = couleur_hex.lstrip("#")
    return tuple(int(couleur_hex[i:i + 2], 16) for i in (0, 2, 4))

def _rgb_vers_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)

def ajuster_luminosite(couleur_hex: str, luminosite: float) -> str:
    """
    luminosite : 0.5 (plus sombre) -> 1.5 (plus clair). 1.0 = inchangé.
    """
    r, g, b = _hex_vers_rgb(couleur_hex)
    r = r * luminosite
    g = g * luminosite
    b = b * luminosite
    return _rgb_vers_hex((r, g, b))

LANGUES_5 = ["Français", "English", "العربية", "Türkçe", "Español"]

TRADUCTIONS = {
    "bienvenue": ["Bienvenue", "Welcome", "مرحبا", "Hoş geldiniz", "Bienvenido"],
    "choisir": ["Choisissez une option", "Choose an option", "اختر خيارا", "Bir seçenek seçin", "Elija una opción"],
    "opt1": ["Calculatrice de note universitaire", "University grade calculator", "حاسبة الدرجات الجامعية", "Üniversite not hesaplayıcı", "Calculadora de notas universitarias"],
    "opt2": ["Calculatrice simple", "Simple calculator", "آلة حاسبة بسيطة", "Basit hesap makinesi", "Calculadora simple"],
    "opt3": ["Calculatrice de date", "Date calculator", "حاسبة التاريخ", "Tarih hesaplayıcı", "Calculadora de fechas"],
    "opt4": ["Calculatrice d'unités", "Unit calculator", "محول الوحدات", "Birim hesaplayıcı", "Calculadora de unidades"],
    "opt5": ["Paramètres de langues", "Language settings", "إعدادات اللغة", "Dil ayarları", "Ajustes de idioma"],
    "accueil": ["Accueil", "Home", "الرئيسية", "Ana sayfa", "Inicio"],
    "langue_active": ["Langue active", "Active language", "اللغة الحالية", "Etkin dil", "Idioma activo"],
    "calculer": ["Calculer", "Calculate", "احسب", "Hesapla", "Calcular"],
    "de": ["De", "From", "من", "Kimden", "De"],
    "vers": ["Vers", "To", "إلى", "Nereye", "A"],
    "valeur": ["Valeur", "Value", "القيمة", "Değer", "Valor"],
    "resultat": ["Résultat", "Result", "النتيجة", "Sonuç", "Resultado"],
}

def lire_date(texte):
    texte = (texte or "").strip().replace("-", "/").replace(".", "/")
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    return None

def ajouter_mois(d, n):
    import calendar
    m = d.month - 1 + n
    a = d.year + m // 12
    m = m % 12 + 1
    j = min(d.day, calendar.monthrange(a, m)[1])
    return d.replace(year=a, month=m, day=j)

def difference_dates(d1, d2):
    """Retourne (années, mois, jours, total_jours) entre deux dates."""
    if d1 > d2:
        d1, d2 = d2, d1
    total = (d2 - d1).days
    annees = d2.year - d1.year
    mois = d2.month - d1.month
    jours = d2.day - d1.day
    if jours < 0:
        mois -= 1
        prec = ajouter_mois(d2.replace(day=1), -1)
        import calendar
        jours += calendar.monthrange(prec.year, prec.month)[1]
    if mois < 0:
        annees -= 1
        mois += 12
    return annees, mois, jours, total

UNITES = {
    "Poids / Masse": {"base": "kg", "u": {"mg": 1e-6, "g": 1e-3, "kg": 1, "tonne": 1000, "quintal": 100,
                      "livre (lb)": 0.45359237, "once (oz)": 0.028349523125, "carat": 0.0002}},
    "Longueur": {"base": "m", "u": {"mm": 1e-3, "cm": 1e-2, "m": 1, "km": 1000, "pouce (in)": 0.0254,
                 "pied (ft)": 0.3048, "yard (yd)": 0.9144, "mile": 1609.344, "mille marin": 1852}},
    "Taille et dimensions": {"base": "cm", "u": {"mm": 0.1, "cm": 1, "dm": 10, "m": 100, "pouce (in)": 2.54,
                             "pied (ft)": 30.48, "pouce → taille en pieds" : 30.48}},
    "Surface": {"base": "m²", "u": {"mm²": 1e-6, "cm²": 1e-4, "m²": 1, "hectare": 10000, "km²": 1e6,
                "acre": 4046.8564224, "pied²": 0.09290304, "pouce²": 0.00064516}},
    "Volume": {"base": "L", "u": {"mL": 1e-3, "cL": 1e-2, "L": 1, "m³": 1000, "cm³": 1e-3,
               "gallon US": 3.785411784, "gallon UK": 4.54609, "pinte US": 0.473176473}},
    "Vitesse": {"base": "m/s", "u": {"m/s": 1, "km/h": 1 / 3.6, "mph": 0.44704, "nœud": 0.514444, "Mach": 340.29,
                "pied/s": 0.3048}},
    "Temps": {"base": "s", "u": {"milliseconde": 1e-3, "seconde": 1, "minute": 60, "heure": 3600,
              "jour": 86400, "semaine": 604800, "mois (30 j)": 2592000, "année (365 j)": 31536000}},
    "Lumière": {"base": "lux", "u": {"lux": 1, "lumen/m²": 1, "phot": 10000, "foot-candle": 10.7639104,
                "candela/m² (≈ lux/π)": 3.14159265}},
    "Énergie": {"base": "J", "u": {"joule": 1, "kJ": 1000, "calorie": 4.184, "kcal": 4184, "Wh": 3600,
                "kWh": 3.6e6, "BTU": 1055.056, "eV": 1.602176634e-19}},
    "Puissance": {"base": "W", "u": {"watt": 1, "kW": 1000, "MW": 1e6, "cheval-vapeur (ch)": 735.49875,
                  "horsepower (hp)": 745.69987}},
    "Pression": {"base": "Pa", "u": {"pascal": 1, "kPa": 1000, "bar": 1e5, "atm": 101325, "mmHg": 133.322,
                 "psi": 6894.757}},
    "Angle": {"base": "°", "u": {"degré": 1, "radian": 57.29577951308232, "grade (gon)": 0.9, "tour": 360}},
    "Données": {"base": "octet", "u": {"bit": 0.125, "octet": 1, "Ko": 1e3, "Mo": 1e6, "Go": 1e9, "To": 1e12,
                "Kio": 1024, "Mio": 1048576, "Gio": 1073741824}},
    "Température": {"base": "°C", "u": {"°C": None, "°F": None, "K": None}},
    "Monnaie": {"base": "USD", "u": {}},
}

ORDRE_UNITES = list(UNITES.keys())

TAUX_HORS_LIGNE = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "XAF": 605.0, "XOF": 605.0, "CHF": 0.88, "CAD": 1.36, "AUD": 1.52,
    "JPY": 150.0, "CNY": 7.25, "INR": 83.0, "RUB": 92.0, "BRL": 5.0, "MXN": 17.0, "ZAR": 18.5, "NGN": 1500.0,
    "GHS": 14.0, "KES": 130.0, "EGP": 48.0, "MAD": 10.0, "DZD": 135.0, "TND": 3.1, "SAR": 3.75, "AED": 3.67,
    "QAR": 3.64, "KWD": 0.31, "TRY": 33.0, "PLN": 4.0, "SEK": 10.5, "NOK": 10.6, "DKK": 6.9, "CZK": 23.0,
    "HUF": 360.0, "KRW": 1340.0, "SGD": 1.34, "HKD": 7.8, "THB": 36.0, "MYR": 4.7, "IDR": 15800.0,
    "PHP": 56.0, "VND": 25000.0, "PKR": 280.0, "BDT": 117.0, "ILS": 3.7, "CDF": 2800.0, "RWF": 1300.0,
    "UGX": 3750.0, "TZS": 2600.0, "ETB": 57.0, "GNF": 8600.0, "MRU": 39.0, "BIF": 2850.0, "MGA": 4500.0,
    "NZD": 1.65, "ARS": 900.0, "CLP": 930.0, "COP": 3900.0, "PEN": 3.75, "UAH": 40.0, "IRR": 42000.0,
}

_taux_en_ligne = {"charge": False, "taux": None}

def obtenir_taux():
    """Taux de change (en ligne si possible, sinon valeurs indicatives intégrées)."""
    if not _taux_en_ligne["charge"]:
        _taux_en_ligne["charge"] = True
        try:
            import urllib.request
            with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=4) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("result") == "success" and data.get("rates"):
                _taux_en_ligne["taux"] = {k: float(v) for k, v in data["rates"].items()}
        except Exception:
            _taux_en_ligne["taux"] = None
    return _taux_en_ligne["taux"] or TAUX_HORS_LIGNE

def convertir_unite(categorie, valeur, u_de, u_vers):
    if categorie == "Monnaie":
        t = obtenir_taux()
        return valeur / t[u_de] * t[u_vers]
    if categorie == "Température":
        c = {"°C": valeur, "°F": (valeur - 32) * 5 / 9, "K": valeur - 273.15}[u_de]
        return {"°C": c, "°F": c * 9 / 5 + 32, "K": c + 273.15}[u_vers]
    f = UNITES[categorie]["u"]
    return valeur * f[u_de] / f[u_vers]

def mention_bac(note):
    if note is None:
        return "--"
    if note >= 16: return "Très Bien"
    if note >= 14: return "Bien"
    if note >= 12: return "Assez Bien"
    if note >= 10: return "Passable"
    return "Insuffisant"

def appreciation_note(note):
    if note is None: return "--"
    if note >= 16: return "Excellent"
    if note >= 14: return "Très bien"
    if note >= 12: return "Bien"
    if note >= 10: return "Passable"
    if note >= 8: return "Insuffisant"
    return "Faible"

def observation_generale(moy):
    """Observation selon l'effort : félicitations, honneur, encouragements, avertissement, blâme."""
    if moy is None: return "--"
    if moy >= 16: return "FÉLICITATIONS : l'élève a beaucoup travaillé."
    if moy >= 14: return "TABLEAU D'HONNEUR : l'élève a fait mieux."
    if moy >= 10: return "ENCOURAGEMENTS : résultats corrects, l'élève peut encore progresser."
    if moy >= 7: return "AVERTISSEMENT : l'élève ne travaille pas assez."
    return "BLÂME : l'élève ne travaille carrément pas."

def _xml(t):
    from xml.sax.saxutils import escape
    return escape(str(t))

def ecrire_docx(chemin, titre, infos, entetes, lignes, synthese):
    """Crée un fichier Word (.docx) minimal sans dépendance externe."""
    import zipfile

    def para(texte, gras=False, taille=22):
        rpr = f'<w:rPr>{"<w:b/>" if gras else ""}<w:sz w:val="{taille}"/></w:rPr>'
        return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{_xml(texte)}</w:t></w:r></w:p>'

    def cellule(t, gras=False):
        return f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{para(t, gras, 18)}</w:tc>'

    corps = [para("SITADELO HISSABI", True, 36), para(titre, True, 28)]
    corps += [para(f"{k} : {v}") for k, v in infos if str(v).strip()]
    tbl = '<w:tbl><w:tblPr><w:tblBorders>' + "".join(
        f'<w:{b} w:val="single" w:sz="4" w:color="808080"/>' for b in ("top", "left", "bottom", "right", "insideH", "insideV")
    ) + '</w:tblBorders></w:tblPr>'
    tbl += "<w:tr>" + "".join(cellule(h, True) for h in entetes) + "</w:tr>"
    for l in lignes:
        tbl += "<w:tr>" + "".join(cellule(v) for v in l) + "</w:tr>"
    tbl += "</w:tbl>"
    corps.append(tbl)
    corps += [para(t, True) for t in synthese]
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(corps) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>')
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
    return True

def _lire_note(texte, maxi=20.0):
    v = to_float_securise(texte)
    return v if v is not None and 0 <= v <= maxi else None

PRIX_LICENCE_XAF = 1500

NUMERO_AIRTEL = "+23560696394"

NUMERO_MOOV = "+23594157876"

NUMERO_WHATSAPP = "+23560696394"

CLE_SECRETE_LICENCE = "7578d8f37656782b2cf607646c6627e9"

def normaliser_id_appareil(texte) -> str:
    return re.sub(r"[^0-9A-F]", "", str(texte).upper())

def calculer_code_licence(prefixe, id_appareil) -> str:
    """Code du type ali.k4m7qz3d : lié à l'identifiant de l'appareil."""
    prefixe = re.sub(r"[^a-z0-9]", "", str(prefixe).lower())[:20] or "client"
    message = f"{prefixe}|{normaliser_id_appareil(id_appareil)}".encode("utf-8")
    signature = hmac.new(CLE_SECRETE_LICENCE.encode("utf-8"), message, hashlib.sha256).digest()
    etiquette = base64.b32encode(signature).decode("ascii")[:8].lower()
    return f"{prefixe}.{etiquette}"

def verifier_code_licence(code, id_appareil) -> bool:
    code = str(code).strip().lower()
    prefixe, point, etiquette = code.rpartition(".")
    if not point or not re.fullmatch(r"[a-z0-9]{1,20}", prefixe) \
            or not re.fullmatch(r"[a-z2-7]{8}", etiquette):
        return False
    return hmac.compare_digest(calculer_code_licence(prefixe, id_appareil), code)



# ==============================================================================
#  SITADELO HISSABI — VERSION TÉLÉPHONE (Kivy)  |  Python 3.12 / Pydroid 3
#  Installation (Pydroid 3 > Pip) :  kivy      (rien d'autre n'est nécessaire)
#  Lancement : ouvrir ce fichier dans Pydroid 3 puis appuyer sur ▶
# ==============================================================================
import threading
import urllib.parse
from kivy.config import Config
Config.set("kivy", "exit_on_escape", "0")
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.graphics import Color, Ellipse, Rectangle, Line, RoundedRectangle, PushMatrix, PopMatrix, Translate
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex, platform

TRADUCTIONS.update({
    "accueil":   ["Accueil", "Home", "الرئيسية", "Ana sayfa", "Inicio"],
    "ajouter":   ["Ajouter une ligne", "Add a row", "إضافة سطر", "Satır ekle", "Añadir fila"],
    "nouveau":   ["Nouveau", "New", "جديد", "Yeni", "Nuevo"],
    "annuler":   ["Annuler", "Undo", "تراجع", "Geri al", "Deshacer"],
    "refaire":   ["Refaire", "Redo", "إعادة", "Yinele", "Rehacer"],
    "param":     ["Paramètres", "Settings", "الإعدادات", "Ayarlar", "Ajustes"],
    "theme":     ["Thème de couleur (20)", "Colour theme (20)", "لون التطبيق (20)", "Renk teması (20)", "Tema de color (20)"],
    "sombre":    ["Mode sombre", "Dark mode", "الوضع الداكن", "Karanlık mod", "Modo oscuro"],
    "clavier":   ["Clavier visuel", "On-screen keypad", "لوحة المفاتيح", "Ekran klavyesi", "Teclado visual"],
    "historique": ["Historique", "History", "السجل", "Geçmiş", "Historial"],
    "mespdf":    ["Mes PDF", "My PDFs", "ملفات PDF", "PDF'lerim", "Mis PDF"],
    "bienvenue2": ["Bienvenue", "Welcome", "مرحبا", "Hoş geldiniz", "Bienvenido"],
})
TRADUCTIONS.update({
    "et2_inutile": ["Vous avez déjà la moyenne en ET1. Le rattrapage n'est pas nécessaire.",
                    "You already have the pass mark in ET1. The resit is not needed.",
                    "لديك المعدل في ET1 بالفعل. الاستدراك غير ضروري.",
                    "ET1'de zaten geçer notunuz var. Telafi sınavı gerekmiyor.",
                    "Ya tienes el aprobado en ET1. La recuperación no es necesaria."],
    "moycr_opt": ["Afficher Moy.CR", "Show Moy.CR", "إظهار Moy.CR", "Moy.CR göster", "Mostrar Moy.CR"],
    "exam_retenu": ["Examen retenu", "Exam kept", "امتحان محتسب", "Geçerli sınav", "Examen retenido"],
    "note_finale": ["Note finale", "Final mark", "العلامة النهائية", "Final notu", "Nota final"],
    "total_points": ["TOTAL POINTS PONDÉRÉS", "TOTAL WEIGHTED POINTS", "مجموع النقاط المرجحة",
                     "AĞIRLIKLI PUAN TOPLAMI", "TOTAL PUNTOS PONDERADOS"],
})
LANGUE_ACTIVE = {"idx": 0}


# ARABE-DEBUT ---------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# ARABE : lettres liées (formes de présentation) + sens droite -> gauche, sans aucun module externe
# ------------------------------------------------------------------------------
# lettre : (isolée, finale, initiale, médiane) ; None = ne se lie pas dans ce sens
_FORMES_AR = {
    "\u0621": ("\uFE80", None, None, None),
    "\u0622": ("\uFE81", "\uFE82", None, None), "\u0623": ("\uFE83", "\uFE84", None, None),
    "\u0624": ("\uFE85", "\uFE86", None, None), "\u0625": ("\uFE87", "\uFE88", None, None),
    "\u0626": ("\uFE89", "\uFE8A", "\uFE8B", "\uFE8C"), "\u0627": ("\uFE8D", "\uFE8E", None, None),
    "\u0628": ("\uFE8F", "\uFE90", "\uFE91", "\uFE92"), "\u0629": ("\uFE93", "\uFE94", None, None),
    "\u062A": ("\uFE95", "\uFE96", "\uFE97", "\uFE98"), "\u062B": ("\uFE99", "\uFE9A", "\uFE9B", "\uFE9C"),
    "\u062C": ("\uFE9D", "\uFE9E", "\uFE9F", "\uFEA0"), "\u062D": ("\uFEA1", "\uFEA2", "\uFEA3", "\uFEA4"),
    "\u062E": ("\uFEA5", "\uFEA6", "\uFEA7", "\uFEA8"), "\u062F": ("\uFEA9", "\uFEAA", None, None),
    "\u0630": ("\uFEAB", "\uFEAC", None, None), "\u0631": ("\uFEAD", "\uFEAE", None, None),
    "\u0632": ("\uFEAF", "\uFEB0", None, None), "\u0633": ("\uFEB1", "\uFEB2", "\uFEB3", "\uFEB4"),
    "\u0634": ("\uFEB5", "\uFEB6", "\uFEB7", "\uFEB8"), "\u0635": ("\uFEB9", "\uFEBA", "\uFEBB", "\uFEBC"),
    "\u0636": ("\uFEBD", "\uFEBE", "\uFEBF", "\uFEC0"), "\u0637": ("\uFEC1", "\uFEC2", "\uFEC3", "\uFEC4"),
    "\u0638": ("\uFEC5", "\uFEC6", "\uFEC7", "\uFEC8"), "\u0639": ("\uFEC9", "\uFECA", "\uFECB", "\uFECC"),
    "\u063A": ("\uFECD", "\uFECE", "\uFECF", "\uFED0"), "\u0640": ("\u0640", "\u0640", "\u0640", "\u0640"),
    "\u0641": ("\uFED1", "\uFED2", "\uFED3", "\uFED4"), "\u0642": ("\uFED5", "\uFED6", "\uFED7", "\uFED8"),
    "\u0643": ("\uFED9", "\uFEDA", "\uFEDB", "\uFEDC"), "\u0644": ("\uFEDD", "\uFEDE", "\uFEDF", "\uFEE0"),
    "\u0645": ("\uFEE1", "\uFEE2", "\uFEE3", "\uFEE4"), "\u0646": ("\uFEE5", "\uFEE6", "\uFEE7", "\uFEE8"),
    "\u0647": ("\uFEE9", "\uFEEA", "\uFEEB", "\uFEEC"), "\u0648": ("\uFEED", "\uFEEE", None, None),
    "\u0649": ("\uFEEF", "\uFEF0", None, None), "\u064A": ("\uFEF1", "\uFEF2", "\uFEF3", "\uFEF4"),
}
_LAM_ALEF = {"\u0622": ("\uFEF5", "\uFEF6"), "\u0623": ("\uFEF7", "\uFEF8"),
             "\u0625": ("\uFEF9", "\uFEFA"), "\u0627": ("\uFEFB", "\uFEFC")}


def _est_marque(ch):
    return "\u064B" <= ch <= "\u065F" or ch == "\u0670" or "\u06D6" <= ch <= "\u06ED"


def _lie_apres(ch):    # la lettre peut se lier à la lettre SUIVANTE
    f = _FORMES_AR.get(ch)
    return bool(f and f[2])


def _lie_avant(ch):    # la lettre peut se lier à la lettre PRÉCÉDENTE
    f = _FORMES_AR.get(ch)
    return bool(f and f[1])


def contient_arabe(texte):
    return any("\u0600" <= ch <= "\u06FF" for ch in str(texte))


def _relier_arabe(ligne):
    """Remplace les lettres arabes par leur forme isolée / finale / initiale / médiane (ordre logique conservé)."""
    chars = list(ligne)
    sortie = []
    i, n = 0, len(chars)
    prec = None                       # dernière lettre non-marque
    while i < n:
        ch = chars[i]
        if _est_marque(ch):
            sortie.append(ch)
            i += 1
            continue
        if ch not in _FORMES_AR:
            sortie.append(ch)
            prec = None
            i += 1
            continue
        j = i + 1
        while j < n and _est_marque(chars[j]):
            j += 1
        suiv = chars[j] if j < n else None
        lie_prec = prec is not None and _lie_apres(prec) and _lie_avant(ch)
        if ch == "\u0644" and suiv in _LAM_ALEF:       # ligature lam-alef
            iso, fin = _LAM_ALEF[suiv]
            sortie.append(fin if lie_prec else iso)
            sortie.extend(chars[i + 1:j])
            prec = None
            i = j + 1
            continue
        lie_suiv = suiv is not None and _lie_apres(ch) and _lie_avant(suiv)
        f = _FORMES_AR[ch]
        if lie_prec and lie_suiv and f[3]:
            forme = f[3]
        elif lie_prec and f[1]:
            forme = f[1]
        elif lie_suiv and f[2]:
            forme = f[2]
        else:
            forme = f[0]
        sortie.append(forme)
        prec = ch
        i += 1
    return "".join(sortie)


def _type_bidi(ch):
    if "\u0600" <= ch <= "\u06FF" and not ("\u0660" <= ch <= "\u0669") or "\uFB50" <= ch <= "\uFDFF" or "\uFE70" <= ch <= "\uFEFF":
        return "R"
    if ch.isalnum():
        return "L"           # lettres latines et chiffres (y compris arabes-indiens) : de gauche à droite
    return "N"


_MIROIR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«"}


def _ordre_visuel(ligne):
    """Réordonne une ligne en ordre visuel (paragraphe droite -> gauche)."""
    types = [_type_bidi(c) for c in ligne]
    n = len(ligne)
    # les neutres : entre deux « L » ils restent « L » ; sinon ils prennent le sens du paragraphe (R)
    i = 0
    while i < n:
        if types[i] != "N":
            i += 1
            continue
        j = i
        while j < n and types[j] == "N":
            j += 1
        av = types[i - 1] if i > 0 else "R"
        ap = types[j] if j < n else "R"
        # un point/une virgule collé à un nombre reste dans le nombre
        r = "L" if (av == "L" and ap == "L") else "R"
        for k in range(i, j):
            types[k] = r
        i = j
    # marques combinantes : même type que la lettre de base
    for k in range(n):
        if _est_marque(ligne[k]) and k > 0:
            types[k] = types[k - 1]
    # groupes
    groupes, cur, ct = [], [], None
    for c, t in zip(ligne, types):
        if t != ct and cur:
            groupes.append((ct, "".join(cur)))
            cur = []
        ct = t
        cur.append(c)
    if cur:
        groupes.append((ct, "".join(cur)))
    res = []
    for t, g in reversed(groupes):
        if t == "R":
            # inverser par « clusters » (lettre + marques) pour garder les marques derrière leur lettre
            clusters = []
            for c in g:
                if _est_marque(c) and clusters:
                    clusters[-1] += c
                else:
                    clusters.append(c)
            res.append("".join(_MIROIR.get(cl, cl) if len(cl) == 1 else cl for cl in reversed(clusters)))
        else:
            res.append(g)
    return "".join(res)


def affichage_arabe(texte):
    """Texte logique -> texte prêt à être dessiné par Kivy (liaison des lettres + ordre visuel)."""
    texte = str(texte)
    if not contient_arabe(texte):
        return texte
    return "\n".join(_ordre_visuel(_relier_arabe(l)) if contient_arabe(l) else l for l in texte.split("\n"))


_POLICE_AR = {"nom": None, "cherchee": False}


def police_arabe():
    """Enregistre (une seule fois) une police qui contient les lettres arabes. Retourne son nom ou None."""
    if _POLICE_AR["cherchee"]:
        return _POLICE_AR["nom"]
    _POLICE_AR["cherchee"] = True
    import glob
    from kivy.core.text import LabelBase
    dossiers = [os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."]
    try:
        dossiers.append(App.get_running_app().user_data_dir)
    except Exception:
        pass
    reguliers, gras = [], []
    for d in dossiers:               # 1) une police déposée à côté de l'application (prioritaire)
        for nom in ("arabic.ttf", "arabe.ttf", "NotoNaskhArabic-Regular.ttf", "NotoSansArabic-Regular.ttf",
                    "Amiri-Regular.ttf", "Cairo-Regular.ttf"):
            reguliers.append(os.path.join(d, nom))
        for nom in ("arabic-bold.ttf", "NotoNaskhArabic-Bold.ttf", "NotoSansArabic-Bold.ttf"):
            gras.append(os.path.join(d, nom))
    if platform == "android":          # 2) polices Arabes du système Android
        for nom in ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabicUI-Regular.ttf", "NotoSansArabic-Regular.ttf",
                    "NotoSansArabicUI-Regular.ttf", "DroidSansArabic.ttf"):
            reguliers.append("/system/fonts/" + nom)
        for nom in ("NotoNaskhArabic-Bold.ttf", "NotoNaskhArabicUI-Bold.ttf", "NotoSansArabic-Bold.ttf",
                    "NotoSansArabicUI-Bold.ttf"):
            gras.append("/system/fonts/" + nom)
        for motif in ("/system/fonts/*Arabic*.ttf", "/system/fonts/*Arabic*.otf", "/system/fonts/*Arab*.ttf",
                      "/product/fonts/*Arabic*.ttf", "/system_ext/fonts/*Arabic*.ttf"):
            reguliers.extend(sorted(glob.glob(motif)))
    else:                              # 3) ordinateur (tests)
        reguliers += ["C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
                      "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial Unicode.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"]
        gras += ["C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    reg = next((p for p in reguliers if os.path.isfile(p)), None)
    if not reg:
        return None
    bold = next((p for p in gras if os.path.isfile(p)), reg)
    try:
        LabelBase.register(name="ArabeSH", fn_regular=reg, fn_bold=bold)
        _POLICE_AR["nom"] = "ArabeSH"
    except Exception:
        _POLICE_AR["nom"] = None
    return _POLICE_AR["nom"]


class ArabeAuto:
    """Mixin pour Label / Button : si le texte contient de l'arabe, on applique la police arabe, la liaison des
    lettres, le sens droite -> gauche et l'alignement à droite.  Sinon, rien ne change."""
    ALIGNER_DROITE = True

    def init_arabe(self):
        self._police0 = self.font_name
        self._align0 = self.halign
        self._arabe_actif = False
        self._garde_arabe = False
        self.bind(text=self._maj_arabe)
        self._maj_arabe()

    def _maj_arabe(self, *_):
        if self._garde_arabe:
            return
        t = self.text or ""
        self._garde_arabe = True
        try:
            if contient_arabe(t):
                nom = police_arabe()
                if nom:
                    self.font_name = nom
                self.text = affichage_arabe(t)
                if self.ALIGNER_DROITE and self._align0 == "left":
                    self.halign = "right"
                self._arabe_actif = True
            elif not any("\uFB50" <= ch <= "\uFDFF" or "\uFE70" <= ch <= "\uFEFF" for ch in t):
                # texte ordinaire (non arabe) : on rend la police et l'alignement d'origine
                if self._arabe_actif or self.font_name != self._police0:
                    self.font_name = self._police0
                    self.halign = self._align0
                    self._arabe_actif = False
        finally:
            self._garde_arabe = False
# ARABE-FIN -----------------------------------------------------------------------------------------


def tr(cle):
    """Texte traduit (ordre logique). La mise en forme arabe est faite par les widgets (ArabeAuto)."""
    try:
        return TRADUCTIONS[cle][LANGUE_ACTIVE["idx"]]
    except Exception:
        return cle


# ------------------------------------------------------------------------------
# Utilitaires : fichiers, URL, appareil
# ------------------------------------------------------------------------------
def lire_json(chemin, defaut):
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire_json(chemin, data):
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def ouvrir_url(url):
    """Ouvre un lien (WhatsApp, tel:, sms:) avec Android si possible."""
    if platform == "android":
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            for nom in ("org.kivy.android.PythonActivity", "ru.iiec.pydroid3.activity.PydroidActivity"):
                try:
                    act = autoclass(nom).mActivity
                    if act is not None:
                        act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        return True
                except Exception:
                    continue
        except Exception:
            pass
    try:
        import webbrowser
        return webbrowser.open(url)
    except Exception:
        return False


# ------------------------------------------------------------------------------
# Enregistrement dans le stockage PUBLIC du téléphone (application Fichiers / Gestionnaire de fichiers)
#   Android 10+ : MediaStore (Documents/SITADELO_HISSABI/...), aucune permission nécessaire
#   Android 9-  : dossier Documents classique (permission de stockage demandée au démarrage)
# ------------------------------------------------------------------------------
MIMES = {"pdf": "application/pdf",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
DOSSIER_PUBLIC = "SITADELO_HISSABI"


def _activite_android():
    try:
        from jnius import autoclass
    except Exception:
        return None
    for nom in ("org.kivy.android.PythonActivity", "ru.iiec.pydroid3.activity.PydroidActivity"):
        try:
            act = autoclass(nom).mActivity
            if act is not None:
                return act
        except Exception:
            continue
    return None


def _sdk_android():
    try:
        from jnius import autoclass
        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:
        return 0


def demander_permissions_stockage():
    """Nécessaire uniquement sur Android 9 et moins."""
    if platform != "android":
        return
    sdk = _sdk_android()
    if 0 < sdk < 29:
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
        except Exception:
            pass


def _publier_android(chemin, zone, ext):
    """Copie le fichier dans Documents/SITADELO_HISSABI/<zone>. Retourne un dict ou None."""
    from jnius import autoclass
    act = _activite_android()
    if act is None:
        return None
    nom = os.path.basename(chemin)
    mime = MIMES.get(ext, "application/octet-stream")
    relatif = f"Documents/{DOSSIER_PUBLIC}/{zone}"
    if _sdk_android() >= 29:
        ContentValues = autoclass("android.content.ContentValues")
        Files = autoclass("android.provider.MediaStore$Files")
        res = act.getContentResolver()
        cv = ContentValues()
        cv.put("_display_name", nom)
        cv.put("mime_type", mime)
        cv.put("relative_path", relatif)
        uri = res.insert(Files.getContentUri("external"), cv)
        if uri is None:
            return None
        flux = res.openOutputStream(uri)
        try:
            with open(chemin, "rb") as f:
                flux.write(f.read())
            flux.flush()
        finally:
            flux.close()
        return {"uri": str(uri.toString()), "affiche": f"{relatif}/{nom}", "public": True}
    # Android 9 et moins : écriture directe + indexation pour que le fichier apparaisse dans Fichiers
    import shutil
    Env = autoclass("android.os.Environment")
    base = Env.getExternalStoragePublicDirectory(Env.DIRECTORY_DOCUMENTS).getAbsolutePath()
    d = os.path.join(base, DOSSIER_PUBLIC, zone)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, nom)
    shutil.copyfile(chemin, dest)
    try:
        autoclass("android.media.MediaScannerConnection").scanFile(act, [dest], [mime], None)
    except Exception:
        pass
    return {"uri": "", "chemin": dest, "affiche": f"{relatif}/{nom}", "public": True}


def ouvrir_fichier(entree):
    """Ouvre un PDF / Word avec l'application du téléphone (lecteur PDF, Word, WPS...)."""
    ext = entree.get("ext") or "pdf"
    mime = MIMES.get(ext, "*/*")
    cible = entree.get("uri") or entree.get("chemin") or ""
    if not cible:
        return False
    if platform == "android":
        try:
            from jnius import autoclass
            act = _activite_android()
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            if cible.startswith("content://"):
                uri = Uri.parse(cible)
            else:
                try:   # Android 7-9 : autoriser le lien file://
                    StrictMode = autoclass("android.os.StrictMode")
                    Builder = autoclass("android.os.StrictMode$VmPolicy$Builder")
                    StrictMode.setVmPolicy(Builder().build())
                except Exception:
                    pass
                uri = Uri.fromFile(autoclass("java.io.File")(cible))
            it = Intent(Intent.ACTION_VIEW)
            it.setDataAndType(uri, mime)
            drap = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK
            it.addFlags(drap)
            choix = Intent.createChooser(it, "Ouvrir avec")
            choix.addFlags(drap)
            act.startActivity(choix)
            return True
        except Exception:
            return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(cible)
            return True
        import subprocess
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", cible])
        return True
    except Exception:
        return False


def _source_identifiant(dossier):
    if platform == "android":
        try:
            from jnius import autoclass
            Secure = autoclass("android.provider.Settings$Secure")
            for nom in ("org.kivy.android.PythonActivity", "ru.iiec.pydroid3.activity.PydroidActivity"):
                try:
                    act = autoclass(nom).mActivity
                    v = Secure.getString(act.getContentResolver(), Secure.ANDROID_ID)
                    if v:
                        return str(v)
                except Exception:
                    continue
        except Exception:
            pass
    f = os.path.join(dossier, "id_appareil.txt")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            v = fh.read().strip()
            if v:
                return v
    except Exception:
        pass
    v = uuid.uuid4().hex
    try:
        os.makedirs(dossier, exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(v)
    except Exception:
        pass
    return v


def identifiant_appareil(dossier):
    emp = hashlib.sha256(("SITADELO|" + _source_identifiant(dossier)).encode("utf-8")).hexdigest()[:12].upper()
    return "-".join(emp[i:i + 4] for i in (0, 4, 8))


# ------------------------------------------------------------------------------
# Générateur PDF intégré (aucune bibliothèque externe nécessaire)
# ------------------------------------------------------------------------------
def _rgbf(h):
    r, g, b = _hex_vers_rgb(h)
    return f"{r / 255:.3f} {g / 255:.3f} {b / 255:.3f}"


# Largeurs des caractères Helvetica (1/1000 em) pour centrer / couper le texte avec précision
_LARG_HELV = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333, "*": 389,
    "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
    "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278, "J": 500,
    "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556, "`": 333,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556, "h": 556, "i": 222, "j": 222, "k": 500,
    "l": 222, "m": 833, "n": 556, "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500,
    "w": 722, "x": 500, "y": 500, "z": 500, "{": 334, "|": 260, "}": 334, "~": 584,
}
for _c in "0123456789":
    _LARG_HELV[_c] = 556
_FACT_POLICE = {"F1": 1.0, "F2": 1.07, "F3": 0.97, "F4": 1.0}


def largeur_texte(txt, taille, police="F1"):
    f = _FACT_POLICE.get(police, 1.0)
    return sum(_LARG_HELV.get(ch, 556) for ch in str(txt)) * taille / 1000.0 * f


def ajuster_texte(txt, taille, police, maxw):
    """Coupe le texte avec « … » s'il dépasse la largeur disponible."""
    txt = str(txt)
    if largeur_texte(txt, taille, police) <= maxw:
        return txt
    while txt and largeur_texte(txt + "…", taille, police) > maxw:
        txt = txt[:-1]
    return (txt + "…") if txt else ""


class PDFMin:
    """Générateur PDF A4 sans bibliothèque.  Polices : F1 Helvetica, F2 Helvetica-Bold, F3 Times-Bold, F4 Helvetica-Oblique."""
    W, H = 595.0, 842.0

    def __init__(self):
        self.pages = []
        self.nouvelle_page()

    def nouvelle_page(self):
        self.cur = []
        self.pages.append(self.cur)

    @staticmethod
    def _op_rect(x, y, w, h, hexc):
        return f"{_rgbf(hexc)} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f"

    def rect(self, x, y, w, h, hexc):
        self.cur.append(self._op_rect(x, y, w, h, hexc))

    def contour(self, x, y, w, h, hexc, epais=0.6):
        self.cur.append(f"{_rgbf(hexc)} RG {epais:.2f} w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def ligne(self, x1, y1, x2, y2, hexc, epais=0.5):
        self.cur.append(f"{_rgbf(hexc)} RG {epais:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def cercle(self, cx, cy, r, hexc):
        k = 0.5523 * r
        self.cur.append(
            f"{_rgbf(hexc)} rg {cx + r:.2f} {cy:.2f} m "
            f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c "
            f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c "
            f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c "
            f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c f")

    def degrade(self, x, y, w, h, c_haut, c_bas, pas=24):
        """Dégradé vertical (bandes fines)."""
        hb = h / pas
        r1, g1, b1 = _hex_vers_rgb(c_haut)
        r2, g2, b2 = _hex_vers_rgb(c_bas)
        for i in range(pas):
            t = i / max(1, pas - 1)
            col = _rgb_vers_hex((r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t))
            self.rect(x, y + h - (i + 1) * hb, w, hb + 0.4, col)

    def texte(self, x, y, txt, taille=10, gras=False, hexc="#000000", centre_w=None, police=None, droite_x=None):
        police = police or ("F2" if gras else "F1")
        if centre_w:
            x = x + (centre_w - largeur_texte(txt, taille, police)) / 2
        if droite_x is not None:
            x = droite_x - largeur_texte(txt, taille, police)
        b = str(txt).encode("cp1252", "replace")
        b = b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        self.cur.append(f"BT /{police} {taille} Tf {_rgbf(hexc)} rg {x:.2f} {y:.2f} Td "
                        + "(" + b.decode("latin-1") + ") Tj ET")

    def texte_ombre(self, x, y, txt, taille, hexc, hexc_ombre, police):
        self.texte(x + 0.9, y - 0.9, txt, taille, False, hexc_ombre, None, police)
        self.texte(x, y, txt, taille, False, hexc, None, police)

    def logo(self, cx, cy, r, couleur, fond="#FFFFFF"):
        self.cercle(cx, cy, r, couleur)
        w, h = r * 0.95, r * 1.35
        self.rect(cx - w / 2, cy - h / 2, w, h, fond)
        self.rect(cx - w / 2 + r * .08, cy + h / 2 - r * .42, w - r * .16, r * .34, couleur)
        for rr in range(3):
            for cc in range(3):
                self.rect(cx - w / 2 + r * .12 + cc * r * .28, cy - h / 2 + r * .15 + rr * r * .27, r * .2, r * .17, couleur)

    def enregistrer(self, chemin):
        objs = []

        def add(c):
            objs.append(c)
            return len(objs)

        add(b"<< /Type /Catalog /Pages 2 0 R >>")
        add(b"")  # pages (remplacé)
        for base in ("Helvetica", "Helvetica-Bold", "Times-Bold", "Helvetica-Oblique"):
            add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>".encode())
        ids = []
        for ops in self.pages:
            flux = "\n".join(ops).encode("latin-1", "replace")
            c = add(b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream")
            p = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.W:.0f} {self.H:.0f}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >> /Contents {c} 0 R >>".encode())
            ids.append(p)
        objs[1] = ("<< /Type /Pages /Kids [" + " ".join(f"{i} 0 R" for i in ids) + f"] /Count {len(ids)} >>").encode()
        out = bytearray(b"%PDF-1.4\n")
        pos = []
        for i, o in enumerate(objs, 1):
            pos.append(len(out))
            out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for p in pos:
            out += f"{p:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
        with open(chemin, "wb") as f:
            f.write(bytes(out))
        return True


def pdf_tableau(chemin, titre, etablissement, infos, entetes, lignes, synthese, couleur_hex, couleurs_lignes=None):
    """PDF A4 soigné : bandeau dégradé en relief, cartouche d'informations, tableau 3D (ombre, en-tête brillant,
    lignes fines, zébrures aux couleurs du thème), panneau de synthèse, pied de page numéroté."""
    try:
        P = PDFMin()
        W, H, M = P.W, P.H, 40.0
        date = datetime.now().strftime("%d/%m/%Y %H:%M")
        FONCE = _teinte(couleur_hex, .55)
        CLAIR = _teinte(couleur_hex, 1.9)
        GRILLE = "#C5CDD8"
        RH = 21.0

        def bandeau():
            P.degrade(0, H - 100, W, 100, _teinte(couleur_hex, 1.22), _teinte(couleur_hex, .82))
            P.rect(0, H - 103.5, W, 3.5, FONCE)
            P.rect(0, H - 106, W, 2.5, "#D3D8DF")
            P.rect(0, H - 101.2, W, 1.2, _teinte(couleur_hex, 1.5))
            P.cercle(73, H - 52, 36, FONCE)
            P.cercle(72, H - 50, 35, "#FFFFFF")
            P.logo(72, H - 50, 31, couleur_hex)
            nom = ajuster_texte((etablissement or "SITADELO HISSABI").upper(), 20, "F3", W - 130 - M)
            P.texte_ombre(124, H - 46, nom, 20, "#FFFFFF", FONCE, "F3")
            P.ligne(124, H - 55, W - M, H - 55, _teinte(couleur_hex, 1.5), 0.8)
            P.texte(124, H - 72, titre, 12, False, "#FFFFFF", None, "F4")
            P.texte(124, H - 88, "SITADELO HISSABI", 8, True, _teinte(couleur_hex, 1.7))

        bandeau()
        y = H - 106 - 26

        # ---- cartouche d'informations --------------------------------------------------------
        vis = [(k, v) for k, v in infos if str(v).strip()]
        if vis:
            nb = (len(vis) + 1) // 2
            hh = nb * 17 + 12
            P.rect(M + 2.5, y - hh + 2.5 - 12, W - 2 * M, hh, "#D9DEE5")
            P.rect(M, y - hh - 12, W - 2 * M, hh, CLAIR)
            P.contour(M, y - hh - 12, W - 2 * M, hh, GRILLE, 0.6)
            P.rect(M, y - hh - 12, 5, hh, couleur_hex)
            yy = y - 12 - 15
            for i in range(0, len(vis), 2):
                for j, (k, v) in enumerate(vis[i:i + 2]):
                    x0 = M + 16 + j * ((W - 2 * M) / 2)
                    lab = f"{k} : "
                    P.texte(x0, yy, lab, 9.5, True, FONCE)
                    P.texte(x0 + largeur_texte(lab, 9.5, "F2") + 3, yy,
                            ajuster_texte(v, 10, "F1", (W - 2 * M) / 2 - 24 - largeur_texte(lab, 9.5, "F2")),
                            10, False, "#1A1A1A")
                yy -= 17
            y = y - hh - 12 - 22

        # ---- colonnes -----------------------------------------------------------------------
        poids, gauche = [], []
        for j, e in enumerate(entetes):
            vals = [str(l[j]) for l in lignes if j < len(l)]
            m = max([len(str(e))] + [len(v) for v in vals])
            poids.append(min(max(m, 3), 26) + 3)
            texte_long = sum(1 for v in vals if len(v) > 9 and not v.replace(".", "").replace(",", "").isdigit())
            gauche.append(texte_long >= max(1, len(vals) // 2) and m > 9)
        total = sum(poids)
        tw = W - 2 * M
        larg = [tw * p / total for p in poids]
        xs = [M]
        for w_ in larg:
            xs.append(xs[-1] + w_)

        seg = {"idx": 0, "haut": 0.0}

        def entete_tab(y0):
            """Dessine l'en-tête (haut = y0) et renvoie le y de la 1re ligne."""
            seg["idx"] = len(P.cur)
            seg["haut"] = y0
            yb = y0 - RH
            P.degrade(M, yb, tw, RH, _teinte(couleur_hex, 1.3), _teinte(couleur_hex, .85), 10)
            P.rect(M, yb, tw, 1.6, FONCE)
            P.rect(M, y0 - 1.2, tw, 1.2, _teinte(couleur_hex, 1.6))
            for j, e in enumerate(entetes):
                if j:
                    P.ligne(xs[j], yb + 3, xs[j], y0 - 3, _teinte(couleur_hex, 1.45), 0.6)
                t = ajuster_texte(e, 8.8, "F2", larg[j] - 8)
                if gauche[j]:
                    P.texte(xs[j] + 5, yb + 7, t, 8.8, True, "#FFFFFF")
                else:
                    P.texte(xs[j], yb + 7, t, 8.8, True, "#FFFFFF", larg[j])
            return yb

        def fin_segment(y_bas):
            """Ombre portée + cadre du tableau pour le segment de page courant."""
            h = seg["haut"] - y_bas
            P.cur.insert(seg["idx"], PDFMin._op_rect(M + 3, y_bas - 3, tw, h, "#BFC6D0"))
            P.cur.insert(seg["idx"] + 1, PDFMin._op_rect(M + 1.5, y_bas - 1.5, tw, h, "#D6DBE3"))
            P.contour(M, y_bas, tw, h, FONCE, 1.3)
            P.ligne(M, y_bas, M + tw, y_bas, FONCE, 2.0)

        y = entete_tab(y)
        for n, l in enumerate(lignes):
            if y - RH < 62:
                fin_segment(y)
                P.nouvelle_page()
                y = entete_tab(H - 50)
            yb = y - RH
            P.rect(M, yb, tw, RH, CLAIR if n % 2 == 0 else "#FFFFFF")
            P.ligne(M, yb, M + tw, yb, GRILLE, 0.5)
            for j in range(1, len(xs) - 1):
                P.ligne(xs[j], yb, xs[j], y, GRILLE, 0.5)
            coul = (couleurs_lignes[n] if couleurs_lignes and n < len(couleurs_lignes) else "#1A1A1A")
            for j, v in enumerate(l):
                if j >= len(larg):
                    break
                gras = (j == len(l) - 1 or j == len(l) - 2) and bool(couleurs_lignes)
                pol = "F2" if gras else "F1"
                t = ajuster_texte(v, 8.8, pol, larg[j] - 8)
                if gauche[j]:
                    P.texte(xs[j] + 5, yb + 7, t, 8.8, gras, coul)
                else:
                    P.texte(xs[j], yb + 7, t, 8.8, gras, coul, larg[j])
            y = yb
        fin_segment(y)
        y -= 30

        # ---- synthèse ---------------------------------------------------------------------------
        lignes_s = []
        for ligne in synthese:
            cur = ""
            for m in str(ligne).split(" "):
                if largeur_texte((cur + " " + m).strip(), 10.5, "F2") > tw - 36:
                    lignes_s.append(cur)
                    cur = m
                else:
                    cur = (cur + " " + m).strip()
            if cur:
                lignes_s.append(cur)
        hp = len(lignes_s) * 16 + 16
        if y - hp - 26 < 50:
            P.nouvelle_page()
            y = H - 50
        P.texte(M, y, "SYNTHÈSE", 14, False, FONCE, None, "F3")
        P.ligne(M, y - 5, M + tw, y - 5, couleur_hex, 1.4)
        y -= 14
        P.rect(M + 3, y - hp - 3, tw, hp, "#BFC6D0")
        P.rect(M, y - hp, tw, hp, CLAIR)
        P.contour(M, y - hp, tw, hp, couleur_hex, 0.9)
        P.rect(M, y - hp, 6, hp, couleur_hex)
        yy = y - 18
        for t in lignes_s:
            P.texte(M + 18, yy, t, 10.5, True, "#1A1A1A")
            yy -= 16

        # ---- pied de page numéroté -------------------------------------------------------------
        nbp = len(P.pages)
        for i, ops in enumerate(P.pages, 1):
            P.cur = ops
            P.ligne(M, 38, W - M, 38, couleur_hex, 0.8)
            P.texte(M, 24, "Document généré par SITADELO HISSABI — " + date, 8, False, "#6B7280", None, "F4")
            P.texte(0, 24, f"Page {i} / {nbp}", 8.5, True, FONCE, None, "F2", droite_x=W - M)
        return P.enregistrer(chemin)
    except Exception:
        return False


# ------------------------------------------------------------------------------
# Thème
# ------------------------------------------------------------------------------
STATE = {"theme": "Bleu Hissabi", "sombre": False, "moycr": True}


def couleurs():
    acc = PALETTES.get(STATE["theme"], "#0B3D91")
    if STATE["sombre"]:
        return {"accent": acc, "fond": "#121212", "panneau": "#1E1E1E", "panneau2": "#2A2A2A", "texte": "#F2F2F2",
                "texte2": "#B0B0B0", "bordure": "#333333"}
    return {"accent": acc, "fond": "#F4F6F8", "panneau": "#FFFFFF", "panneau2": "#E3E8EE", "texte": "#1A1A1A",
            "texte2": "#555555", "bordure": "#DDDDDD"}


def rgba(h, a=1.0):
    c = get_color_from_hex(h)
    return [c[0], c[1], c[2], a]


def texte_sur(h):
    r, g, b = _hex_vers_rgb(h)
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 170 else "#FFFFFF"


VERT, JAUNE, ROUGE = "#2E7D32", "#F2A900", "#C62828"


# ------------------------------------------------------------------------------
# Widgets de base
# ------------------------------------------------------------------------------
class Fond(BoxLayout):
    def __init__(self, couleur, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._c = Color(*rgba(couleur))
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *_):
        self._r.pos, self._r.size = self.pos, self.size


class Texte(ArabeAuto, Label):
    def __init__(self, texte="", taille=14, gras=False, couleur=None, align="left", **kw):
        c = couleurs()
        kw.setdefault("size_hint_y", None)
        super().__init__(text=texte, font_size=sp(taille), bold=gras, halign=align, valign="middle",
                         color=rgba(couleur or c["texte"]), markup=False, **kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)),
                  texture_size=lambda *_: setattr(self, "height", max(dp(22), self.texture_size[1] + dp(6))))
        self.init_arabe()


def _teinte(hexc, f):
    """f < 1 : assombrit | f > 1 : éclaircit (mélange avec du blanc)."""
    r, g, b = _hex_vers_rgb(hexc)
    if f <= 1:
        return _rgb_vers_hex((r * f, g * f, b * f))
    k = f - 1
    return _rgb_vers_hex((r + (255 - r) * k, g + (255 - g) * k, b + (255 - b) * k))


class Face3D:
    """Rend un bouton Kivy en relief : base sombre (épaisseur), face colorée, reflet brillant, liseré clair.
    À l'appui, la face s'enfonce et le texte descend avec elle."""
    PROF = 5      # épaisseur du relief (dp)

    def init3d(self, couleur, texte=True, rayon=10):
        self._ray0 = dp(rayon)
        self._txt3 = texte
        with self.canvas.before:
            Color(*rgba(_teinte(couleur, .5)))
            self._r_base = RoundedRectangle()
            Color(*rgba(couleur))
            self._r_face = RoundedRectangle()
            Color(1, 1, 1, .20)
            self._r_gloss = RoundedRectangle()
            Color(*rgba(_teinte(couleur, 1.35), .75))
            self._l_bord = Line(width=1.0)
            if texte:
                PushMatrix()
                self._tr = Translate(0, 0)
        if texte:
            with self.canvas.after:
                PopMatrix()
        self.bind(pos=self.maj3d, size=self.maj3d, state=self.maj3d)
        self.maj3d()

    def maj3d(self, *_):
        x, y = self.pos
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        d = dp(self.PROF)
        de = d * .3 if self.state == "down" else d
        hf = max(dp(8), h - d)
        r = max(dp(3), min(self._ray0, hf / 2.2))
        self._r_base.pos, self._r_base.size, self._r_base.radius = (x, y), (w, max(dp(8), h - dp(1))), [r]
        self._r_face.pos, self._r_face.size, self._r_face.radius = (x, y + de), (w, hf), [r]
        self._r_gloss.pos = (x + dp(3), y + de + hf * .52)
        self._r_gloss.size = (max(0, w - dp(6)), hf * .42)
        self._r_gloss.radius = [r * .8]
        self._l_bord.rounded_rectangle = (x + .5, y + de + .5, w - 1, hf - 1, r)
        if self._txt3:
            self._tr.y = de - d / 2.0


class Bouton(ArabeAuto, Face3D, Button):
    def __init__(self, texte, cmd=None, principal=True, couleur=None, taille=14, **kw):
        c = couleurs()
        bg = couleur or (c["accent"] if principal else c["panneau2"])
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(46))
        super().__init__(text=texte, background_normal="", background_down="", background_color=[0, 0, 0, 0],
                         color=rgba(texte_sur(bg) if (principal or couleur) else c["texte"]), bold=True,
                         font_size=sp(taille), halign="center", **kw)
        self.init3d(bg)
        self.bind(size=lambda *_: setattr(self, "text_size", (self.width - dp(8), None)))
        self.init_arabe()
        if cmd:
            self.bind(on_release=lambda *_: cmd())


class Selecteur(Face3D, Spinner):
    """Liste déroulante en relief (écran Unités)."""
    def __init__(self, **kw):
        c = couleurs()
        super().__init__(background_normal="", background_down="", background_color=[0, 0, 0, 0], **kw)
        self.init3d(c["panneau2"])


def filtre_num(sous, undo):
    return "".join(ch for ch in sous if ch in "0123456789.,")


class Champ(TextInput):
    def __init__(self, hint="", texte="", numerique=False, manage=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        if manage:
            kw["keyboard_mode"] = "managed"
        kw.setdefault("font_size", sp(14))
        super().__init__(hint_text=hint, text=texte, multiline=False, write_tab=False,
                         background_normal="", background_active="", background_color=[1, 1, 1, 1],
                         foreground_color=[.07, .07, .07, 1], hint_text_color=[.5, .5, .5, 1],
                         cursor_color=[.1, .1, .1, 1], padding=[dp(6), dp(10), dp(6), dp(6)], **kw)
        if numerique:
            self.input_type = "number"
            self.input_filter = filtre_num


class Logo(Widget):
    def __init__(self, couleur, fond="#FFFFFF", **kw):
        super().__init__(**kw)
        self.couleur, self.fond = couleur, fond
        self.bind(pos=self.dessiner, size=self.dessiner)
        Clock.schedule_once(self.dessiner, 0)

    def dessiner(self, *_):
        self.canvas.clear()
        s = min(self.width, self.height)
        if s <= 0:
            return
        x, y = self.center_x - s / 2, self.center_y - s / 2
        with self.canvas:
            Color(*rgba(self.couleur))
            Ellipse(pos=(x, y), size=(s, s))
            Color(*rgba(self.fond))
            Rectangle(pos=(x + .27 * s, y + .17 * s), size=(.46 * s, .66 * s))
            Color(*rgba(self.couleur))
            Rectangle(pos=(x + .31 * s, y + .63 * s), size=(.38 * s, .16 * s))
            for r in range(3):
                for c in range(3):
                    Rectangle(pos=(x + .31 * s + c * .1267 * s + .01 * s, y + .21 * s + r * .14 * s),
                              size=(.1067 * s, .095 * s))


class Hamburger(Face3D, Button):
    """Bouton à trois traits ≡ (dessiné, aucun symbole spécial nécessaire)."""
    def __init__(self, couleur="#FFFFFF", fond="#0B3D91", **kw):
        super().__init__(background_normal="", background_down="", background_color=[0, 0, 0, 0], **kw)
        self.couleur = couleur
        self.init3d(fond, texte=False)
        self.bind(pos=self.dessiner, size=self.dessiner, state=self.dessiner)

    def dessiner(self, *_):
        self.canvas.after.clear()
        with self.canvas.after:
            Color(*rgba(self.couleur))
            w, h = self.width * .5, dp(3)
            cy = self.center_y + (dp(2.5) if self.state != "down" else dp(.5))
            for k in (-1, 0, 1):
                Rectangle(pos=(self.center_x - w / 2, cy + k * dp(8) - h / 2), size=(w, h))


class TroisPoints(Hamburger):
    def dessiner(self, *_):
        self.canvas.after.clear()
        with self.canvas.after:
            Color(*rgba(self.couleur))
            d = dp(6)
            cy = self.center_y + (dp(2.5) if self.state != "down" else dp(.5))
            for k in (-1, 0, 1):
                Ellipse(pos=(self.center_x - d / 2, cy + k * dp(9) - d / 2), size=(d, d))


def popup_info(titre, message, largeur=.9):
    c = couleurs()
    boite = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    boite.add_widget(Texte(message, 13, couleur=c["texte"]))
    p = Popup(title=titre, content=boite, size_hint=(largeur, None), height=dp(260), auto_dismiss=True)
    boite.add_widget(Bouton("OK", p.dismiss))
    p.open()
    return p


def popup_fichier(app, entree):
    """Confirmation d'enregistrement avec ouverture immédiate."""
    boite = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    if entree.get("public"):
        msg = ("Fichier enregistré dans votre téléphone.\n\n"
               "Ouvrez l'application Fichiers (gestionnaire de fichiers) > Documents > "
               f"{DOSSIER_PUBLIC} > {entree.get('zone', '')}\n\n{entree.get('nom', '')}")
    else:
        msg = ("Le fichier est enregistré dans l'application (Mes PDF), mais le stockage du téléphone "
               f"n'a pas autorisé la copie dans Fichiers.\n\n{entree.get('nom', '')}")
    boite.add_widget(Texte(msg, 13))
    p = Popup(title="Enregistré", content=boite, size_hint=(.92, None), height=dp(330))

    def ouvrir():
        if not app.ouvrir_entree(entree):
            popup_info("Fichier", "Aucune application pour ouvrir ce fichier.\nOuvrez-le depuis Fichiers :\n"
                       + (entree.get("affiche") or entree.get("nom", "")))

    ligne = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
    ligne.add_widget(Bouton("Ouvrir", lambda: (p.dismiss(), ouvrir()), taille=13))
    ligne.add_widget(Bouton("Mes PDF", lambda: (p.dismiss(), app.aller("PDF")), principal=False, taille=13))
    ligne.add_widget(Bouton("OK", p.dismiss, principal=False, taille=13))
    boite.add_widget(ligne)
    p.open()


def popup_confirmer(titre, message, si_oui):
    boite = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    boite.add_widget(Texte(message, 13))
    ligne = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
    p = Popup(title=titre, content=boite, size_hint=(.9, None), height=dp(240))
    ligne.add_widget(Bouton("Non", p.dismiss, principal=False))
    ligne.add_widget(Bouton("Oui", lambda: (p.dismiss(), si_oui())))
    boite.add_widget(ligne)
    p.open()


def defilant(spacing=6, padding=10):
    sv = ScrollView(do_scroll_x=False, bar_width=dp(4))
    g = GridLayout(cols=1, size_hint_y=None, spacing=dp(spacing), padding=dp(padding))
    g.bind(minimum_height=g.setter("height"))
    sv.add_widget(g)
    return sv, g



# ==============================================================================
# ÉCRANS
# ==============================================================================
ZONES = [("PDF_Universitaire", "PDF universitaire"), ("PDF_BAC", "PDF BAC"), ("PDF_Ecole_Bulletin", "PDF école / bulletin")]


class TitreBarre(ArabeAuto, Button):
    ALIGNER_DROITE = False


class BarreHaut(Fond):
    def __init__(self, app, sous_cle, **kw):
        c = couleurs()
        super().__init__(c["accent"], orientation="horizontal", size_hint_y=None, height=dp(58),
                         padding=[dp(8), dp(5)], spacing=dp(6), **kw)
        fg = texte_sur(c["accent"])
        self.app = app
        self.add_widget(Logo(fg, c["accent"], size_hint_x=None, width=dp(46)))
        sous = tr(sous_cle) if sous_cle else ""
        titre = TitreBarre(text="SITADELO HISSABI" + (("\n" + sous) if sous else ""), halign="left", valign="middle",
                           background_normal="", background_down="", background_color=rgba(c["accent"]),
                           color=rgba(fg), bold=True, font_size=sp(14))
        titre.init_arabe()
        titre.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, w.height)))
        titre.bind(on_release=lambda *_: app.aller("MENU"))
        self.add_widget(titre)
        mb = TroisPoints(fg, c["accent"], size_hint_x=None, width=dp(44))
        mb.bind(on_release=lambda b: self._menu(b))
        self.add_widget(mb)

    def _menu(self, ancre):
        dd = DropDown(auto_width=False, width=dp(230))
        elems = [(tr("accueil"), "MENU"), ("1. Calc BAC", "BAC"), ("2. Bulletin", "BULLETIN"),
                 ("3. " + tr("mespdf"), "PDF"), ("4. " + tr("historique"), "HISTORIQUE"),
                 ("5. " + tr("param"), "PARAM")]
        for txt, nom in elems:
            b = Bouton(txt, principal=False, height=dp(46))
            b.bind(on_release=lambda w, n=nom: (dd.dismiss(), self.app.aller(n)))
            dd.add_widget(b)
        b = Bouton(tr("clavier"), principal=False, height=dp(46))
        b.bind(on_release=lambda w: (dd.dismiss(), self.app.basculer_clavier()))
        dd.add_widget(b)
        dd.open(ancre)


class ClavierNum(GridLayout):
    def __init__(self, ecran, **kw):
        super().__init__(cols=4, size_hint_y=None, height=dp(4 * 44 + 3 * 3 + 12), spacing=dp(3),
                         padding=[dp(4), dp(4)], **kw)
        self.ecran = ecran
        for t in ["7", "8", "9", "DEL", "4", "5", "6", "<", "1", "2", "3", ">", ".", "0", ",", "OK"]:
            self.add_widget(Bouton(t, lambda t=t: self.appui(t), principal=t in "DEL<>OK" and t not in "..,", height=dp(44)))

    def appui(self, t):
        e = self.ecran
        ch = e.dernier
        if t == "OK":
            e.app.basculer_clavier()
        elif t in ("<", ">"):
            champs = e.champs_suivi
            if ch in champs:
                i = champs.index(ch) + (1 if t == ">" else -1)
                if 0 <= i < len(champs):
                    champs[i].focus = True
        elif ch is not None:
            if t == "DEL":
                ch.do_backspace()
            else:
                ch.insert_text("." if t == "," else t)


class Ecran(Screen):
    NOM = ""
    SOUS = ""
    AVEC_CLAVIER = False

    def __init__(self, app, **kw):
        super().__init__(name=self.NOM, **kw)
        self.app = app
        self.sale = True
        self.champs_suivi = []
        self.dernier = None

    def on_pre_enter(self, *a):
        if self.sale:
            self.sale = False
            self.reconstruire()

    def reconstruire(self):
        self.avant_reconstruire()
        self.clear_widgets()
        self.champs_suivi = []
        c = couleurs()
        racine = Fond(c["fond"], orientation="vertical")
        racine.add_widget(BarreHaut(self.app, self.SOUS))
        corps = BoxLayout(orientation="vertical")
        racine.add_widget(corps)
        self.add_widget(racine)
        self.construire(corps)
        if self.app.clavier_visible and self.AVEC_CLAVIER:
            racine.add_widget(ClavierNum(self))

    def avant_reconstruire(self):
        pass

    def construire(self, corps):
        pass

    def champ(self, hint="", texte="", numerique=False, **kw):
        if self.app.clavier_visible and self.AVEC_CLAVIER:
            kw["manage"] = True
            kw["unfocus_on_touch"] = False
        ch = Champ(hint, texte, numerique, **kw)
        ch.bind(focus=lambda w, f: setattr(self, "dernier", w) if f else None)
        ch.bind(on_text_validate=lambda w: self.suivant(w))
        self.champs_suivi.append(ch)
        return ch

    def suivant(self, w):
        if w in self.champs_suivi:
            i = self.champs_suivi.index(w) + 1
            if i < len(self.champs_suivi):
                self.champs_suivi[i].focus = True

    def sur_texte_modifie(self):
        pass


class Trait(Widget):
    def __init__(self, **kw):
        super().__init__(size_hint_y=None, height=dp(4), **kw)
        with self.canvas:
            self._c = Color(0, 0, 0, 0)
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *_):
        self._r.pos, self._r.size = self.pos, self.size

    def colorer(self, hexc):
        self._c.rgba = rgba(hexc) if hexc else [0, 0, 0, 0]


# ------------------------------------------------------------------------------
# MENU PRINCIPAL
# ------------------------------------------------------------------------------
class EcranMenu(Ecran):
    NOM = "MENU"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(8, 14)
        g.add_widget(Widget(size_hint_y=None, height=dp(6)))
        lg = BoxLayout(size_hint_y=None, height=dp(96))
        lg.add_widget(Widget())
        lg.add_widget(Logo(c["accent"], "#FFFFFF", size_hint_x=None, width=dp(96)))
        lg.add_widget(Widget())
        g.add_widget(lg)
        nom = self.app.nom_utilisateur()
        g.add_widget(Texte(f"{tr('bienvenue')} {nom}".strip(), 22, True, c["accent"], "center"))
        g.add_widget(Texte(tr("choisir"), 13, False, c["texte2"], "center"))
        for i, (cle, cible) in enumerate([("opt1", "NOTES"), ("opt2", "SIMPLE"), ("opt3", "DATE"),
                                          ("opt4", "UNITES"), ("opt5", "LANGUES")], 1):
            g.add_widget(Bouton(f"{i}   {tr(cle)}", lambda n=cible: self.app.aller(n), taille=15, height=dp(54)))
        corps.add_widget(sv)


# ------------------------------------------------------------------------------
# CALCULATRICE DE NOTE UNIVERSITAIRE
# ------------------------------------------------------------------------------
CHAMPS_ETU = [("nom", "Nom"), ("prenom", "Prénom"), ("universite", "Université ou Institut"),
              ("faculte", "Faculté"), ("annee", "Année universitaire"), ("niveau", "Niveau")]


class LigneNote(GridLayout):
    def __init__(self, ecran, d=None, **kw):
        super().__init__(cols=1, size_hint_y=None, spacing=dp(1), **kw)
        self.bind(minimum_height=self.setter("height"))
        d = d or {}
        self.ecran = ecran
        l1 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(3))
        s = lambda v: "" if v is None else str(v)
        self.nom = ecran.champ("Matière", s(d.get("nom")), size_hint_x=.25)
        self.cc = ecran.champ("CC", s(d.get("cc")), True, size_hint_x=.11)
        self.td = ecran.champ("TD", s(d.get("td")), True, size_hint_x=.11)
        self.session = ecran.champ("ET1", s(d.get("session")), True, size_hint_x=.12)
        self.et2 = ecran.champ("ET2", s(d.get("et2")), True, size_hint_x=.12)
        self.coef = ecran.champ("Crédit", s(d.get("coefficient")), True, size_hint_x=.13)
        for ch in (self.nom, self.cc, self.td, self.session, self.et2, self.coef):
            l1.add_widget(ch)
            ch.bind(text=lambda *_: ecran.sur_texte_modifie())
        l1.add_widget(Bouton("X", lambda: ecran.supprimer(self), couleur=ROUGE, size_hint_x=.09, height=dp(40)))
        # ET2 : réservé aux étudiants qui n'ont pas la moyenne en ET1
        self.session.bind(text=lambda *_: self.maj_et2())
        self.et2.bind(focus=self._focus_et2)
        self.maj_et2()
        self.add_widget(l1)
        self.res = Texte("", 11)
        self.trait = Trait()
        self.add_widget(self.res)
        self.add_widget(self.trait)

    def et2_bloque(self):
        etat, v = _lire_cellule(self.session.text)
        return etat == "ok" and v >= 10

    def maj_et2(self):
        """ET1 >= 10 : ET2 est verrouillé et vidé ; sinon (ET1 < 10, vide ou effacé) il est libre."""
        bloque = self.et2_bloque()
        if bloque and self.et2.text.strip():
            self.et2.text = ""
        self.et2.readonly = bloque
        self.et2.opacity = .45 if bloque else 1

    def _focus_et2(self, champ, focus):
        if focus and self.et2_bloque():
            champ.focus = False
            popup_info("ET2", tr("et2_inutile"))

    def donnees(self):
        return {"nom": self.nom.text, "cc": self.cc.text, "td": self.td.text,
                "session": self.session.text, "et2": self.et2.text, "coefficient": self.coef.text}

    def vide(self):
        return not any(v.strip() for v in self.donnees().values())

    def afficher(self, l):
        if l.get("erreur"):
            self.res.text, self.res.color = "Erreur : " + l["erreur"], rgba(ROUGE)
            self.trait.colorer(None)
            return
        r = l.get("resultat", "--")
        coul = VERT if r == "Validée" else (JAUNE if r == "Compensée" else ROUGE)
        morceaux = [f"{tr('exam_retenu')} {formater_nombre(l.get('note_examen'))} ({l.get('source_examen')})",
                    f"{tr('note_finale')} {formater_nombre(l.get('note_finale'))}/20"]
        if STATE.get("moycr", True):
            morceaux.append(f"Moy.CR {formater_nombre(l.get('moy_cr'))}")   # points pondérés, pas une note /20
        morceaux += [r, str(l.get("mention"))]
        self.res.text = "  |  ".join(morceaux)
        if l.get("et2_ignore"):
            self.res.text += "\n" + tr("et2_inutile")
        self.res.color = rgba(coul)
        self.trait.colorer(l.get("couleur_compensation"))

    def effacer_resultat(self):
        self.res.text = ""
        self.trait.colorer(None)


class EcranNotes(Ecran):
    NOM = "NOTES"
    SOUS = "opt1"
    AVEC_CLAVIER = True

    def __init__(self, app, **kw):
        super().__init__(app, **kw)
        self.lignes, self.champs_etu = [], {}
        self.bilan = None
        self.pile_undo, self.pile_redo = [], []
        self._restauration = False
        self._minuteur = None
        self.initial = app.charger_brouillon()

    # -- cycle de vie -------------------------------------------------------
    def avant_reconstruire(self):
        if self.lignes or self.champs_etu:
            self.initial = self.collecter()

    def collecter(self):
        return {"etudiant": self.etudiant(), "matieres": [l.donnees() for l in self.lignes]}

    def etudiant(self):
        return {k: self.champs_etu[k].text for k, _ in CHAMPS_ETU if k in self.champs_etu}

    def on_leave(self, *a):
        self.app.sauver_brouillon(self.collecter())

    def construire(self, corps):
        c = couleurs()
        self.lignes, self.champs_etu = [], {}
        sv, g = defilant(5, 8)
        self.grille = g
        g.add_widget(Texte(tr("opt1"), 17, True, c["accent"]))
        g.add_widget(Texte("Formation", 13, True, c["texte2"]))
        etu = (self.initial or {}).get("etudiant", {})
        for k, lib in CHAMPS_ETU:
            ch = self.champ(lib, etu.get(k, ""))
            ch.bind(text=lambda *_: self.sur_texte_modifie())
            self.champs_etu[k] = ch
            g.add_widget(ch)
        b1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        b1.add_widget(Bouton(tr("ajouter"), self.ajouter_ligne, taille=12))
        b1.add_widget(Bouton("Calculer", self.calculer, taille=13))
        g.add_widget(b1)
        b2 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        b2.add_widget(Bouton(tr("annuler"), self.annuler, principal=False, taille=12, height=dp(40)))
        b2.add_widget(Bouton(tr("refaire"), self.refaire, principal=False, taille=12, height=dp(40)))
        b2.add_widget(Bouton(tr("nouveau"), self.nouveau, principal=False, taille=12, height=dp(40)))
        g.add_widget(b2)
        ent = BoxLayout(size_hint_y=None, height=dp(24))
        for t, p in (("Matière", .25), ("CC", .11), ("TD", .11), ("ET1", .12), ("ET2", .12), ("Crédit", .13), ("", .09)):
            ent.add_widget(Texte(t, 9, True, c["texte2"], "center", size_hint_x=p))
        g.add_widget(ent)
        self.zone_lignes = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
        self.zone_lignes.bind(minimum_height=self.zone_lignes.setter("height"))
        g.add_widget(self.zone_lignes)
        mats = (self.initial or {}).get("matieres") or [{}, {}, {}]
        self._restauration = True
        for d in mats:
            self.ajouter_ligne(d)
        self._restauration = False
        # décision générale
        g.add_widget(Texte("Décision générale", 14, True, c["accent"]))
        self.panneau = Fond(c["accent"], orientation="vertical", size_hint_y=None, height=dp(9 * 28 + 12),
                            padding=dp(6))
        fg = texte_sur(c["accent"])
        self.lab = {}
        for k in ("moyenne", "acquis", "compense", "total_acquis", "total", "points", "mention", "decision"):
            t = Texte("", 12, True, fg)
            self.lab[k] = t
            self.panneau.add_widget(t)
        g.add_widget(self.panneau)
        self.compens = Texte("", 12, False, c["texte"])
        g.add_widget(self.compens)
        b3 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        b3.add_widget(Bouton("PDF", self.exporter_pdf))
        b3.add_widget(Bouton("Word", self.exporter_word))
        g.add_widget(b3)
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))
        corps.add_widget(sv)
        self.afficher_decision(None)
        if not self.pile_undo:
            self.snapshot()

    # -- lignes -----------------------------------------------------------------
    def ajouter_ligne(self, d=None):
        if not isinstance(d, dict):
            d = None
        l = LigneNote(self, d)
        self.lignes.append(l)
        self.zone_lignes.add_widget(l)

    def supprimer(self, l):
        if len(self.lignes) <= 1:
            popup_info("Information", "Au moins une matière doit rester dans le tableau.")
            return
        self.lignes.remove(l)
        self.zone_lignes.remove_widget(l)
        self.sur_texte_modifie()

    # -- calcul --------------------------------------------------------------------
    def calculer(self, enregistrer=True):
        actives = [(l, l.donnees()) for l in self.lignes if not l.vide()]
        if not actives:
            popup_info("Information", "Veuillez ajouter au moins une matière.")
            return None
        bilan = calculer_bilan([d for _, d in actives])
        for (l, _), lb in zip(actives, bilan["lignes"]):
            l.afficher(lb)
        for l in self.lignes:
            if l.vide():
                l.effacer_resultat()
        self.bilan = bilan
        self.afficher_decision(bilan)
        self.afficher_compensations(bilan)
        if bilan.get("moyenne_generale") is not None and enregistrer:
            self.app.ajouter_historique(bilan, self.collecter())
            self.app.sauver_brouillon(self.collecter())
        return bilan

    def afficher_decision(self, b):
        f = formater_nombre
        if not b or b.get("moyenne_generale") is None:
            t = {"moyenne": "MOYENNE GÉNÉRALE : -- / 20", "acquis": "CRÉDITS ACQUIS : --", "compense": "CRÉDITS COMPENSÉS : --",
                 "total_acquis": "CRÉDIT TOTAL ACQUIS : --", "total": "CRÉDIT TOTAL : --", "points": f"{tr('total_points')} : --", "mention": "MENTION : --",
                 "decision": "DÉCISION : --"}
        else:
            t = {"moyenne": f"MOYENNE GÉNÉRALE : {f(b['moyenne_generale'])} / 20",
                 "acquis": f"CRÉDITS ACQUIS : {f(b['credits_valides'])}",
                 "compense": f"CRÉDITS COMPENSÉS : {f(b['credits_compenses'])}",
                 "total_acquis": f"CRÉDIT TOTAL ACQUIS : {f(b['credits_valides'] + b['credits_compenses'])}",
                 "total": f"CRÉDIT TOTAL : {f(b['total_credits'])}",
                 "points": f"{tr('total_points')} : {f(b['total_points'])}", "mention": f"MENTION : {b['mention']}",
                 "decision": f"DÉCISION : {b['decision']}"}
        for k, v in t.items():
            self.lab[k].text = v

    def afficher_compensations(self, b):
        morceaux = []
        for l in b["lignes"]:
            if l.get("compense_matieres"):
                morceaux.append(f"{l['nom']} a compensé : {', '.join(l['compense_matieres'])}")
        for n in b.get("non_compensees", []):
            morceaux.append(f"{n['nom']} : non validée")
        self.compens.text = "\n".join(morceaux)

    # -- nouveau / annuler / refaire --------------------------------------------------------
    def nouveau(self):
        popup_confirmer("Nouveau calcul", "Effacer toute la saisie ?", self._vider)

    def _vider(self):
        self.initial = {"etudiant": {}, "matieres": [{}, {}, {}]}
        self.bilan = None
        self.lignes, self.champs_etu = [], {}
        self.reconstruire()
        self.snapshot()

    def reinitialiser(self):
        for l in self.lignes:
            l.effacer_resultat()
        self.afficher_decision(None)
        self.compens.text = ""

    def sur_texte_modifie(self):
        if self._restauration:
            return
        if self._minuteur:
            self._minuteur.cancel()
        self._minuteur = Clock.schedule_once(lambda dt: self.snapshot(), .7)

    def snapshot(self):
        if not self.lignes:
            return
        etat = json.dumps(self.collecter(), sort_keys=True)
        if not self.pile_undo or self.pile_undo[-1] != etat:
            self.pile_undo = (self.pile_undo + [etat])[-100:]
            self.pile_redo = []
        self.app.sauver_brouillon(self.collecter())

    def _appliquer(self, etat):
        self.initial = json.loads(etat)
        self.lignes, self.champs_etu = [], {}
        self.reconstruire()

    def annuler(self):
        self.snapshot()
        if len(self.pile_undo) > 1:
            self.pile_redo.append(self.pile_undo.pop())
            self._appliquer(self.pile_undo[-1])

    def refaire(self):
        if self.pile_redo:
            etat = self.pile_redo.pop()
            self.pile_undo.append(etat)
            self._appliquer(etat)

    def charger(self, data):
        self.initial = data
        self.lignes, self.champs_etu = [], {}
        self.sale = True
        self.pile_undo, self.pile_redo = [], []

    # -- exports -------------------------------------------------------------------------------
    def _donnees_export(self, bilan):
        e = self.etudiant()
        infos = [("Nom", e.get("nom")), ("Prénom", e.get("prenom")), ("Université ou Institut", e.get("universite")),
                 ("Faculté", e.get("faculte")), ("Année universitaire", e.get("annee")), ("Niveau", e.get("niveau"))]
        lignes, couls = [], []
        for l in bilan["lignes"]:
            ligne = [l["n"], l["nom"], l.get("cc") or "", l.get("td") or "", l.get("session") or "",
                     "" if l.get("et2_ignore") else (l.get("et2") or ""),
                     formater_nombre(l.get("note_examen")) if l.get("note_examen") is not None else "--",
                     formater_nombre(l.get("note_finale")) if l.get("note_finale") is not None else "--",
                     formater_nombre(l.get("coefficient"))]
            if STATE.get("moycr", True):
                ligne.append(formater_nombre(l.get("moy_cr")) if l.get("moy_cr") is not None else "--")
            lignes.append(ligne + [l.get("resultat"), l.get("mention")])
            r = l.get("resultat")
            couls.append("#2E7D32" if r == "Validée" else ("#B07A00" if r == "Compensée" else "#C62828"))
        f = formater_nombre
        synth = [f"Moyenne générale : {f(bilan['moyenne_generale'])} / 20",
                 f"Crédits acquis : {f(bilan['credits_valides'])} | Crédits compensés : {f(bilan['credits_compenses'])} | "
                 f"Crédit total acquis : {f(bilan['credits_valides'] + bilan['credits_compenses'])} sur {f(bilan['total_credits'])}",
                 f"Total des points pondérés : {f(bilan['total_points'])}",
                 f"Mention : {bilan['mention']} | Décision : {bilan['decision']}"]
        for l in bilan["lignes"]:
            if l.get("compense_matieres"):
                synth.append(f"{l['nom']} a compensé : {', '.join(l['compense_matieres'])}")
        return e, infos, (["N°", "Matière", "CC", "TD", "ET1", "ET2", "Exam retenu", "Moyenne", "Crédit"]
                          + (["Moy.CR"] if STATE.get("moycr", True) else []) + ["Résultat", "Mention"]), lignes, synth, couls

    def exporter_pdf(self):
        b = self.calculer(False)
        if not b or b.get("moyenne_generale") is None:
            return popup_info("Impossible d'exporter", "Corrigez d'abord les erreurs du tableau.")
        e, infos, ent, lignes, synth, couls = self._donnees_export(b)
        chemin = self.app.chemin_sortie("PDF_Universitaire", "pdf")
        ok = pdf_tableau(chemin, "Calculatrice de note universitaire", e.get("universite"), infos, ent, lignes, synth,
                         PALETTES.get(STATE["theme"], "#0B3D91"), couls)
        self.app.fin_export("PDF_Universitaire", chemin, ok, "PDF")

    def exporter_word(self):
        b = self.calculer(False)
        if not b or b.get("moyenne_generale") is None:
            return popup_info("Impossible d'exporter", "Corrigez d'abord les erreurs du tableau.")
        e, infos, ent, lignes, synth, _ = self._donnees_export(b)
        chemin = self.app.chemin_sortie("PDF_Universitaire", "docx")
        try:
            ok = ecrire_docx(chemin, "Calculatrice de note universitaire", infos, ent, lignes, synth)
        except Exception:
            ok = False
        self.app.fin_export("PDF_Universitaire", chemin, ok, "Word")


# ------------------------------------------------------------------------------
# CALCULATRICE SIMPLE
# ------------------------------------------------------------------------------
TOUCHES_SIMPLES = [
    ["DEG", "sin", "cos", "tan", "log"],
    ["ln", "√", "x²", "x^y", "n!"],
    ["x", "y", "a", "b", "|x|"],
    ["(", ")", "π", "e", "Δ"],
    ["7", "8", "9", "÷", "⌫"],
    ["4", "5", "6", "×", "C"],
    ["1", "2", "3", "-", "1/x"],
    ["0", ".", "ANS", "+", "="],
]
INSERT_SIMPLE = {"sin": "sin(", "cos": "cos(", "tan": "tan(", "ln": "ln(", "log": "log(", "√": "√(", "x²": "^2",
                 "x^y": "^", "n!": "!", "|x|": "abs(", "ANS": "ans", "÷": "/", "×": "*"}


class EcranSimple(Ecran):
    NOM = "SIMPLE"
    SOUS = "opt2"

    def __init__(self, app, **kw):
        super().__init__(app, **kw)
        self.derniere = None
        self.apres_egal = False
        self.texte_init = ""

    def avant_reconstruire(self):
        if hasattr(self, "expr"):
            self.texte_init = self.expr.text

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(4, 8)
        self.expr = Champ("Tapez une opération…", self.texte_init, height=dp(54), manage=True, font_size=sp(20))
        self.expr.unfocus_on_touch = False
        self.expr.bind(on_text_validate=lambda *_: self.calculer())
        g.add_widget(self.expr)
        self.resultat = Texte("= --", 22, True, c["accent"], "right")
        g.add_widget(self.resultat)
        self.details = Texte("", 11, False, c["texte2"])
        g.add_widget(self.details)
        grille = GridLayout(cols=5, size_hint_y=None, spacing=dp(3), height=dp(8 * 48 + 7 * 3))
        for ligne in TOUCHES_SIMPLES:
            for t in ligne:
                num = t in "0123456789."
                if t == "DEG":
                    t = _ETAT_CALCULATRICE["angle"]
                b = Bouton(t, lambda t=t: self.appui(t), principal=t in ("=", "C", "⌫", "RAD", "DEG"),
                           couleur=(c["panneau"] if num else None), height=dp(48), taille=14)
                if num:
                    b.color = rgba(c["texte"])
                grille.add_widget(b)
        g.add_widget(grille)
        g.add_widget(Bouton(tr("historique"), self.voir_historique, principal=False))
        g.add_widget(Widget(size_hint_y=None, height=dp(20)))
        corps.add_widget(sv)

    def inserer(self, s):
        if self.apres_egal and s and s[0] in "+-*/^!":
            self.expr.text = "ans"
            self.expr.cursor = (3, 0)
        self.apres_egal = False
        self.expr.insert_text(s)

    def appui(self, t):
        if t == "C":
            self.expr.text = ""
            self.resultat.text, self.details.text = "= --", ""
            self.apres_egal = False
        elif t == "⌫":
            self.apres_egal = False
            self.expr.do_backspace()
        elif t == "=":
            self.calculer()
        elif t == "Δ":
            self.delta()
        elif t in ("DEG", "RAD"):
            _ETAT_CALCULATRICE["angle"] = "RAD" if _ETAT_CALCULATRICE["angle"] == "DEG" else "DEG"
            self.sale = True
            self.reconstruire()
        elif t == "1/x":
            ex = "ans" if self.apres_egal else self.expr.text.strip()
            self.apres_egal = False
            self.expr.text = f"1/({ex})" if ex else "1/("
        else:
            self.inserer(INSERT_SIMPLE.get(t, t))

    def _erreur(self, m):
        self.resultat.text, self.resultat.color = f"Erreur : {m}", rgba(ROUGE)
        self.details.text = ""

    def delta(self):
        texte = self.expr.text
        reste = extraire_delta(texte)
        reste = texte if reste is None else reste
        if not reste.strip():
            return self._erreur("tapez un trinôme (ex. x²-3x+2) puis Δ.")
        try:
            td, lignes = calcul_delta(reste, self.derniere)
        except ErreurAlgebre as e:
            return self._erreur(str(e))
        except (RecursionError, MemoryError, OverflowError):
            return self._erreur("Expression trop complexe.")
        self.resultat.text, self.resultat.color = f"Δ = {td}", rgba(couleurs()["accent"])
        self.details.text = "\n".join(lignes)
        self.app.ajouter_simple("Δ " + reste.strip(), td)

    def calculer(self):
        expression = self.expr.text
        reste = extraire_delta(expression)
        if reste is not None:
            return self.delta()
        acc = rgba(couleurs()["accent"])
        if est_expression_algebrique(expression):
            try:
                res, det = calcul_algebrique(expression, self.derniere)
            except ErreurAlgebre as e:
                return self._erreur(str(e))
            except (RecursionError, MemoryError, OverflowError):
                return self._erreur("Expression trop complexe.")
            self.resultat.text, self.resultat.color = f"= {res}", acc
            self.details.text = "\n".join(det)
            self.app.ajouter_simple(expression, res)
            self.apres_egal = False
            return
        self.details.text = ""
        res, err = evaluer_expression_securisee(expression, self.derniere)
        if err:
            return self._erreur(err)
        t = formater_nombre(res)
        self.derniere = res
        self.resultat.text, self.resultat.color = f"= {t}", acc
        self.app.ajouter_simple(expression, t)
        self.apres_egal = True

    def voir_historique(self):
        boite = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        sv, g = defilant(4, 2)
        p = Popup(title=tr("historique"), content=boite, size_hint=(.94, .8))
        for e in self.app.simple[:60]:
            g.add_widget(Bouton(f"{e['expression']} = {e['resultat']}", lambda e=e, p=p: (p.dismiss(), self._charger(e)),
                                principal=False, height=dp(42), taille=12))
        if not self.app.simple:
            g.add_widget(Texte("Aucun calcul.", 13))
        boite.add_widget(sv)
        boite.add_widget(Bouton("Fermer", p.dismiss))
        p.open()

    def _charger(self, e):
        self.expr.text = e["expression"]
        self.apres_egal = False



# ------------------------------------------------------------------------------
# CALCULATRICE DE DATE
# ------------------------------------------------------------------------------
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class EcranDate(Ecran):
    NOM = "DATE"
    SOUS = "opt3"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(6, 10)
        aujourdhui = datetime.now().strftime("%d/%m/%Y")
        g.add_widget(Texte(tr("opt3"), 17, True, c["accent"]))
        # 1) différence
        g.add_widget(Texte("Différence entre deux dates (JJ/MM/AAAA)", 13, True))
        self.d1 = self.champ("Du", aujourdhui)
        self.d2 = self.champ("Au", aujourdhui)
        g.add_widget(self.d1); g.add_widget(self.d2)
        g.add_widget(Bouton(tr("calculer"), self.diff))
        self.r1 = Texte("", 14, True, c["accent"]); g.add_widget(self.r1)
        # 2) ajouter / retirer
        g.add_widget(Texte("Ajouter ou retirer à une date", 13, True))
        self.base = self.champ("Date", aujourdhui)
        g.add_widget(self.base)
        ligne = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.j = self.champ("Jours", "0", True); self.m = self.champ("Mois", "0", True); self.a = self.champ("Années", "0", True)
        for w in (self.j, self.m, self.a):
            ligne.add_widget(w)
        g.add_widget(ligne)
        l2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        l2.add_widget(Bouton("+  Ajouter", lambda: self.ajout(1)))
        l2.add_widget(Bouton("−  Retirer", lambda: self.ajout(-1)))
        g.add_widget(l2)
        self.r2 = Texte("", 14, True, c["accent"]); g.add_widget(self.r2)
        # 3) âge
        g.add_widget(Texte("Âge à partir d'une date de naissance", 13, True))
        self.nais = self.champ("Naissance (JJ/MM/AAAA)", "")
        g.add_widget(self.nais)
        g.add_widget(Bouton(tr("calculer"), self.age))
        self.r3 = Texte("", 14, True, c["accent"]); g.add_widget(self.r3)
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))
        corps.add_widget(sv)

    def diff(self):
        d1, d2 = lire_date(self.d1.text), lire_date(self.d2.text)
        if not d1 or not d2:
            self.r1.text = "Date invalide. Format : JJ/MM/AAAA"
            return
        a, m, j, t = difference_dates(d1, d2)
        self.r1.text = f"{a} an(s), {m} mois, {j} jour(s)\nTotal : {t} jours ({t // 7} semaines et {t % 7} jours)"

    def ajout(self, signe):
        from datetime import timedelta
        d = lire_date(self.base.text)
        try:
            j, m, a = int(self.j.text or 0), int(self.m.text or 0), int(self.a.text or 0)
        except ValueError:
            self.r2.text = "Entrez des nombres entiers."
            return
        if not d:
            self.r2.text = "Date invalide. Format : JJ/MM/AAAA"
            return
        try:
            r = ajouter_mois(d, signe * (a * 12 + m)) + timedelta(days=signe * j)
            self.r2.text = f"{r.strftime('%d/%m/%Y')} ({JOURS[r.weekday()]})"
        except (OverflowError, ValueError):
            self.r2.text = "Date hors limites."

    def age(self):
        d = lire_date(self.nais.text)
        if not d:
            self.r3.text = "Date invalide. Format : JJ/MM/AAAA"
            return
        a, m, j, t = difference_dates(d, datetime.now().date())
        self.r3.text = f"{a} an(s), {m} mois, {j} jour(s)\n{t} jours vécus"


# ------------------------------------------------------------------------------
# CALCULATRICE D'UNITÉS (menu à trois traits, 15 catégories)
# ------------------------------------------------------------------------------
def charger_taux_en_arriere_plan(rappel=None):
    def tache():
        try:
            obtenir_taux()
        except Exception:
            pass
        if rappel:
            Clock.schedule_once(lambda dt: rappel(), 0)
    threading.Thread(target=tache, daemon=True).start()


class EcranUnites(Ecran):
    NOM = "UNITES"
    SOUS = "opt4"

    def __init__(self, app, **kw):
        super().__init__(app, **kw)
        self.cat = ORDRE_UNITES[0]

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(6, 10)
        haut = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        haut.add_widget(Hamburger(c["accent"] if not STATE["sombre"] else "#FFFFFF", c["fond"], size_hint_x=None, width=dp(52),
                                  on_release=lambda *_: self.menu_categories()))
        haut.add_widget(Texte(self.cat, 17, True, c["accent"], size_hint_y=1))
        g.add_widget(haut)
        taux = _taux_en_ligne["taux"] or TAUX_HORS_LIGNE
        unites = sorted(taux.keys()) if self.cat == "Monnaie" else list(UNITES[self.cat]["u"].keys())
        g.add_widget(Texte(tr("valeur"), 12, False, c["texte2"]))
        self.val = self.champ("1", "1", True, height=dp(48), font_size=sp(18))
        g.add_widget(self.val)

        def spin(defaut):
            return Selecteur(text=defaut, values=unites, size_hint_y=None, height=dp(48),
                             color=rgba(c["texte"]), font_size=sp(14), bold=True)
        d1 = "USD" if self.cat == "Monnaie" else unites[0]
        d2 = "XAF" if self.cat == "Monnaie" else unites[min(1, len(unites) - 1)]
        g.add_widget(Texte(tr("de"), 12, False, c["texte2"]))
        self.de = spin(d1); g.add_widget(self.de)
        g.add_widget(Texte(tr("vers"), 12, False, c["texte2"]))
        self.vers = spin(d2); g.add_widget(self.vers)
        g.add_widget(Bouton(tr("calculer"), self.calculer))
        self.res = Texte("", 22, True, c["accent"]); g.add_widget(self.res)
        self.note = Texte("", 11, False, c["texte2"]); g.add_widget(self.note)
        if self.cat == "Monnaie":
            self.note.text = ("Taux en ligne" if _taux_en_ligne["taux"]
                              else "Taux indicatifs hors ligne (connectez-vous à Internet puis rouvrez cet écran)")
        for w in (self.val,):
            w.bind(text=lambda *_: self.calculer())
        self.de.bind(text=lambda *_: self.calculer()); self.vers.bind(text=lambda *_: self.calculer())
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))
        corps.add_widget(sv)
        self.calculer()

    def menu_categories(self):
        boite = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        sv, g = defilant(4, 2)
        p = Popup(title="Catégories", content=boite, size_hint=(.9, .85))
        for n in ORDRE_UNITES:
            g.add_widget(Bouton(n, lambda n=n, p=p: (p.dismiss(), self.choisir(n)), principal=(n == self.cat), height=dp(46)))
        boite.add_widget(sv)
        boite.add_widget(Bouton("Fermer", p.dismiss, principal=False))
        p.open()

    def choisir(self, n):
        self.cat = n
        self.sale = True
        self.reconstruire()
        self.sale = False
        if n == "Monnaie" and not _taux_en_ligne["taux"]:
            charger_taux_en_arriere_plan(lambda: (setattr(self, "sale", True), self.reconstruire(), setattr(self, "sale", False))
                                         if self.app.sm.current == "UNITES" and self.cat == "Monnaie" else None)

    def calculer(self):
        v = to_float_securise(self.val.text)
        if v is None:
            self.res.text = "Valeur invalide"
            return
        try:
            r = convertir_unite(self.cat, v, self.de.text, self.vers.text)
            self.res.text = f"{formater_nombre(round(r, 8))} {self.vers.text}"
        except Exception:
            self.res.text = "Conversion impossible"


# ------------------------------------------------------------------------------
# LANGUES (5 langues, changement immédiat sur la même page)
# ------------------------------------------------------------------------------
class EcranLangues(Ecran):
    NOM = "LANGUES"
    SOUS = "opt5"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(8, 14)
        g.add_widget(Texte(tr("opt5"), 19, True, c["accent"], "center"))
        g.add_widget(Texte(f"{tr('langue_active')} : {LANGUES_5[LANGUE_ACTIVE['idx']]}", 14, False, c["texte"], "center"))
        if LANGUE_ACTIVE["idx"] == 2 and not police_arabe():
            g.add_widget(Texte("Arabic font not found. Copy a font file named arabic.ttf (e.g. NotoNaskhArabic-Regular.ttf) "
                               "into the app folder, then restart.", 12, False, ROUGE))
        for i, nom in enumerate(LANGUES_5):
            actif = i == LANGUE_ACTIVE["idx"]
            g.add_widget(Bouton(("[OK]  " if actif else "") + nom, lambda k=i: self.app.changer_langue(k),
                                principal=actif, height=dp(54), taille=16))
        corps.add_widget(sv)


# ------------------------------------------------------------------------------
# CALC BAC et BULLETIN
# ------------------------------------------------------------------------------
class LigneTable(GridLayout):
    def __init__(self, ecran, d=None, **kw):
        super().__init__(cols=1, size_hint_y=None, spacing=dp(1), **kw)
        self.bind(minimum_height=self.setter("height"))
        d = d or {}
        self.champs = {}
        l1 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(3))
        for cle, hint, poids in ecran.SAISIE:
            ch = ecran.champ(hint, str(d.get(cle, "")), cle != "matiere", size_hint_x=poids)
            self.champs[cle] = ch
            l1.add_widget(ch)
        l1.add_widget(Bouton("X", lambda: ecran.supprimer(self), couleur=ROUGE, size_hint_x=.1, height=dp(40)))
        self.add_widget(l1)
        self.res = Texte("", 11)
        self.add_widget(self.res)

    def val(self, cle):
        return self.champs[cle].text

    def donnees(self):
        return {k: v.text for k, v in self.champs.items()}


class EcranTable(Ecran):
    AVEC_CLAVIER = True
    ZONE = ""
    TITRE = ""
    ENTETE = []
    SAISIE = []

    def __init__(self, app, **kw):
        super().__init__(app, **kw)
        self.lignes, self.champs_entete = [], {}
        self.initial = {"entete": {}, "lignes": [{}, {}, {}, {}]}
        self.resume = None

    def avant_reconstruire(self):
        if self.lignes:
            self.initial = {"entete": {k: v.text for k, v in self.champs_entete.items()},
                            "lignes": [l.donnees() for l in self.lignes]}

    def construire(self, corps):
        c = couleurs()
        self.lignes, self.champs_entete = [], {}
        sv, g = defilant(5, 8)
        g.add_widget(Texte(self.TITRE, 17, True, c["accent"]))
        for cle, lib in self.ENTETE:
            ch = self.champ(lib, self.initial["entete"].get(cle, ""))
            self.champs_entete[cle] = ch
            g.add_widget(ch)
        ent = BoxLayout(size_hint_y=None, height=dp(24))
        for _, hint, poids in self.SAISIE:
            ent.add_widget(Texte(hint, 9, True, c["texte2"], "center", size_hint_x=poids))
        ent.add_widget(Texte("", 9, size_hint_x=.1))
        g.add_widget(ent)
        self.zone = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
        self.zone.bind(minimum_height=self.zone.setter("height"))
        g.add_widget(self.zone)
        for d in self.initial["lignes"]:
            self.ajouter(d)
        b = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        b.add_widget(Bouton(tr("ajouter"), self.ajouter, taille=12))
        b.add_widget(Bouton(tr("calculer"), self.calculer, taille=13))
        g.add_widget(b)
        self.synthese = Texte("", 13, True, c["accent"])
        g.add_widget(self.synthese)
        b2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        b2.add_widget(Bouton("PDF", self.exporter_pdf))
        b2.add_widget(Bouton("Word", self.exporter_word))
        b2.add_widget(Bouton(tr("nouveau"), self.nouveau, principal=False))
        g.add_widget(b2)
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))
        corps.add_widget(sv)

    def ajouter(self, d=None):
        if not isinstance(d, dict):
            d = None
        l = LigneTable(self, d)
        self.lignes.append(l)
        self.zone.add_widget(l)

    def supprimer(self, l):
        if len(self.lignes) > 1:
            self.lignes.remove(l)
            self.zone.remove_widget(l)

    def nouveau(self):
        self.initial = {"entete": {}, "lignes": [{}, {}, {}, {}]}
        self.lignes = []
        self.reconstruire()

    def infos(self):
        return [(lib, self.champs_entete[cle].text) for cle, lib in self.ENTETE]

    def etablissement(self):
        ch = self.champs_entete.get("etablissement")
        return ch.text if ch else ""

    def calculer(self):
        raise NotImplementedError

    def donnees_export(self):
        raise NotImplementedError

    def exporter_pdf(self):
        if self.calculer() is None:
            return popup_info("Impossible d'exporter", "Saisissez au moins une matière avec ses notes.")
        ent, lignes, synth = self.donnees_export()
        chemin = self.app.chemin_sortie(self.ZONE, "pdf")
        ok = pdf_tableau(chemin, self.TITRE, self.etablissement(), self.infos(), ent, lignes, synth,
                         PALETTES.get(STATE["theme"], "#0B3D91"))
        self.app.fin_export(self.ZONE, chemin, ok, "PDF")

    def exporter_word(self):
        if self.calculer() is None:
            return popup_info("Impossible d'exporter", "Saisissez au moins une matière avec ses notes.")
        ent, lignes, synth = self.donnees_export()
        chemin = self.app.chemin_sortie(self.ZONE, "docx")
        try:
            ok = ecrire_docx(chemin, self.TITRE, self.infos(), ent, lignes, synth)
        except Exception:
            ok = False
        self.app.fin_export(self.ZONE, chemin, ok, "Word")


class EcranBac(EcranTable):
    NOM = "BAC"
    SOUS = ""
    ZONE = "PDF_BAC"
    TITRE = "Calc BAC"
    ENTETE = [("nom", "Nom"), ("prenom", "Prénom"), ("etablissement", "Établissement"), ("serie", "Série"), ("annee", "Année")]
    SAISIE = [("matiere", "Matière", .5), ("note", "Note", .2), ("coef", "Coef", .2)]

    def calculer(self):
        pts = cf = 0.0
        self._lignes_ok = []
        for i, l in enumerate(self.lignes, 1):
            n, k = _lire_note(l.val("note")), to_float_securise(l.val("coef"))
            if n is None or k is None or k <= 0:
                l.res.text = ""
                continue
            ok = n >= 10
            l.res.text = f"Moy coef {formater_nombre(round(n * k, 2))}  |  {mention_bac(n)}  |  {'Validée' if ok else 'Non validée'}"
            l.res.color = rgba(VERT if ok else ROUGE)
            pts += n * k
            cf += k
            self._lignes_ok.append([i, l.val("matiere"), l.val("note"), l.val("coef"), formater_nombre(round(n * k, 2)),
                                    mention_bac(n), "Validée" if ok else "Non validée"])
        if not cf:
            self.synthese.text = "Saisissez des notes (0 à 20) et des coefficients."
            return None
        moy = round(pts / cf, 2)
        dec = "ADMIS(E)" if moy >= 10 else ("SESSION DE RATTRAPAGE (second groupe)" if moy >= 8 else "AJOURNÉ(E)")
        self.resume = (moy, mention_bac(moy), dec, pts, cf)
        self.synthese.text = f"MOYGEN : {formater_nombre(moy)} / 20\nMENTION : {mention_bac(moy)}\nDÉCISION : {dec}"
        return moy

    def donnees_export(self):
        moy, men, dec, pts, cf = self.resume
        f = formater_nombre
        return (["N°", "Matière", "Note", "Coef", "Moy coef", "Mention", "Décision"], self._lignes_ok,
                [f"Total des points : {f(round(pts, 2))} | Total des coefficients : {f(cf)}",
                 f"MOYGEN : {f(moy)} / 20 | MENTION : {men} | DÉCISION : {dec}"])


class EcranBulletin(EcranTable):
    NOM = "BULLETIN"
    SOUS = ""
    ZONE = "PDF_Ecole_Bulletin"
    TITRE = "Bulletin"
    ENTETE = [("nom", "Nom"), ("prenom", "Prénom"), ("etablissement", "Établissement"), ("classe", "Classe"),
              ("annee", "Année scolaire"), ("periode", "Trimestre / Période")]
    SAISIE = [("matiere", "Matière", .34), ("coef", "Coef", .14), ("devoir", "Moy devoir", .17), ("compo", "Moy compo", .17)]

    def calculer(self):
        pts = cf = 0.0
        self._lignes_ok = []
        for i, l in enumerate(self.lignes, 1):
            k = to_float_securise(l.val("coef"))
            dv, cp = _lire_note(l.val("devoir")), _lire_note(l.val("compo"))
            if k is None or k <= 0 or dv is None or cp is None:
                l.res.text = ""
                continue
            mg = round((dv + cp) / 2, 2)
            l.res.text = f"Moygen {formater_nombre(mg)}  |  Moy coef {formater_nombre(round(mg * k, 2))}  |  {appreciation_note(mg)}"
            l.res.color = rgba(VERT if mg >= 10 else ROUGE)
            pts += mg * k
            cf += k
            self._lignes_ok.append([i, l.val("matiere"), l.val("coef"), l.val("devoir"), l.val("compo"),
                                    formater_nombre(mg), formater_nombre(round(mg * k, 2)), appreciation_note(mg)])
        if not cf:
            self.synthese.text = "Saisissez coefficients, moyennes de devoir et de composition (0 à 20)."
            return None
        moy = round(pts / cf, 2)
        obs = observation_generale(moy)
        self.resume = (moy, obs, pts, cf)
        self.synthese.text = f"MOYENNE GÉNÉRALE : {formater_nombre(moy)} / 20\nOBSERVATION GÉNÉRALE : {obs}"
        return moy

    def donnees_export(self):
        moy, obs, pts, cf = self.resume
        f = formater_nombre
        return (["N°", "Matière", "Coef", "Moy devoir", "Moy compo", "Moygen", "Moy coef", "Appréciation"], self._lignes_ok,
                [f"SYNTHÈSE | Total des points : {f(round(pts, 2))} | Total des coefficients : {f(cf)}",
                 f"Moyenne générale : {f(moy)} / 20", f"Observation générale : {obs}"])


# ------------------------------------------------------------------------------
# MES PDF (3 zones), HISTORIQUE, PARAMÈTRES
# ------------------------------------------------------------------------------
class EcranPDF(Ecran):
    NOM = "PDF"
    SOUS = "mespdf"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(5, 8)
        g.add_widget(Texte(f"Fichiers > Documents > {DOSSIER_PUBLIC}", 11, False, c["texte2"]))
        for dossier, titre in ZONES:
            g.add_widget(Fond(c["accent"], size_hint_y=None, height=dp(34), padding=dp(6)))
            g.children[0].add_widget(Texte(titre, 14, True, texte_sur(c["accent"])))
            entrees = self.app.liste_fichiers(dossier)
            if not entrees:
                g.add_widget(Texte("Aucun fichier.", 12, False, c["texte2"]))
            for e in entrees[:60]:
                etiquette = ("[W]  " if e.get("ext") == "docx" else "[PDF]  ") + e["nom"]
                g.add_widget(Bouton(etiquette, lambda e=e: self.ouvrir(e), principal=False, height=dp(44), taille=11))
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))
        corps.add_widget(sv)

    def ouvrir(self, entree):
        if not self.app.ouvrir_entree(entree):
            popup_info("Fichier", "Impossible d'ouvrir ce fichier (aucune application compatible ou fichier supprimé).\n"
                       f"Emplacement : {entree.get('affiche') or entree.get('chemin') or entree.get('nom')}")


class EcranHistorique(Ecran):
    NOM = "HISTORIQUE"
    SOUS = "historique"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(5, 8)
        g.add_widget(Texte(tr("historique"), 17, True, c["accent"]))
        if not self.app.historique:
            g.add_widget(Texte("Aucun calcul enregistré.", 13, False, c["texte2"]))
        for e in self.app.historique[:100]:
            g.add_widget(Bouton(f"{e['date']}  |  Moy {e['moyenne']}  |  {e['decision']}",
                                lambda e=e: self.app.charger_calcul(e), principal=False, height=dp(44), taille=12))
        corps.add_widget(sv)


class EcranParam(Ecran):
    NOM = "PARAM"
    SOUS = "param"

    def construire(self, corps):
        c = couleurs()
        sv, g = defilant(6, 10)
        g.add_widget(Texte(tr("param"), 18, True, c["accent"]))
        g.add_widget(Texte(tr("theme"), 13, True))
        grille = GridLayout(cols=4, size_hint_y=None, spacing=dp(4), height=dp(5 * 50 + 4 * 4))
        for nom in ORDRE_PALETTES:
            hexc = PALETTES[nom]
            b = Bouton(("[OK]" if nom == STATE["theme"] else ""), lambda n=nom: self.app.choisir_theme(n), couleur=hexc, height=dp(50))
            grille.add_widget(b)
        g.add_widget(grille)
        g.add_widget(Texte(STATE["theme"], 12, False, c["texte2"], "center"))
        g.add_widget(Bouton(tr("sombre") + " : " + ("ON" if STATE["sombre"] else "OFF"), self.app.basculer_sombre))
        g.add_widget(Bouton(tr("moycr_opt") + " : " + ("ON" if STATE["moycr"] else "OFF"), self.app.basculer_moycr))
        g.add_widget(Bouton("Couleur suivante (Ctrl+B)", self.app.couleur_suivante, principal=False))
        g.add_widget(Bouton(tr("clavier") + " : " + ("ON" if self.app.clavier_visible else "OFF"), self.app.basculer_clavier, principal=False))
        g.add_widget(Texte("SITADELO HISSABI — version téléphone", 11, False, c["texte2"], "center"))
        corps.add_widget(sv)


# ------------------------------------------------------------------------------
# SPLASH et LICENCE
# ------------------------------------------------------------------------------
class EcranSplash(Ecran):
    NOM = "SPLASH"

    def reconstruire(self):
        self.clear_widgets()
        c = couleurs()
        fg = texte_sur(c["accent"])
        racine = Fond(c["accent"], orientation="vertical", padding=dp(24), spacing=dp(8))
        racine.add_widget(Widget())
        lg = BoxLayout(size_hint_y=None, height=dp(130))
        lg.add_widget(Widget())
        lg.add_widget(Logo(fg, c["accent"], size_hint_x=None, width=dp(130)))
        lg.add_widget(Widget())
        racine.add_widget(lg)
        racine.add_widget(Texte(tr("bienvenue").upper() + " DANS", 14, False, fg, "center"))
        racine.add_widget(Texte("SITADELO HISSABI", 26, True, fg, "center"))
        racine.add_widget(Texte(tr("opt1"), 13, False, fg, "center"))
        racine.add_widget(Widget(size_hint_y=None, height=dp(20)))
        self.cadre = Widget(size_hint_y=None, height=dp(6))
        with self.cadre.canvas:
            Color(*rgba(fg, .3))
            self._fond_b = Rectangle(pos=self.cadre.pos, size=self.cadre.size)
            Color(*rgba(fg))
            self._prog = Rectangle(pos=self.cadre.pos, size=(0, dp(6)))
        self.cadre.bind(pos=self._maj_b, size=self._maj_b)
        racine.add_widget(self.cadre)
        racine.add_widget(Widget())
        self.add_widget(racine)
        self._t = 0.0
        self._ev = Clock.schedule_interval(self._anim, 1 / 30)

    def _maj_b(self, *_):
        self._fond_b.pos, self._fond_b.size = self.cadre.pos, self.cadre.size
        self._prog.pos = self.cadre.pos

    def _anim(self, dt):
        self._t += dt
        self._prog.size = (self.cadre.width * min(1.0, self._t / 5.0), dp(6))
        if self._t >= 5.0:
            self._ev.cancel()
            self.app.apres_splash()


class EcranLicence(Ecran):
    NOM = "LICENCE"

    def reconstruire(self):
        self.clear_widgets()
        c = couleurs()
        racine = Fond(c["fond"], orientation="vertical")
        sv, g = defilant(6, 12)
        racine.add_widget(sv)
        self.add_widget(racine)
        idd = self.app.id_appareil
        lg = BoxLayout(size_hint_y=None, height=dp(80))
        lg.add_widget(Widget()); lg.add_widget(Logo(c["accent"], "#FFFFFF", size_hint_x=None, width=dp(80))); lg.add_widget(Widget())
        g.add_widget(lg)
        g.add_widget(Texte("SITADELO HISSABI", 20, True, c["accent"], "center"))
        g.add_widget(Texte(f"Licence à vie : {PRIX_LICENCE_XAF} FCFA", 15, True, c["texte"], "center"))
        g.add_widget(Texte("Un code = un seul appareil. Paiement unique, valable à vie.", 12, False, c["texte2"], "center"))
        g.add_widget(Texte(
            "1. Appuyez sur « Envoyer mon identifiant sur WhatsApp ».\n"
            f"2. Payez {PRIX_LICENCE_XAF} FCFA :\n    Airtel Money : {NUMERO_AIRTEL}\n    Moov Money : {NUMERO_MOOV}\n"
            "3. Après vérification, vous recevez votre mot de passe de connexion sur WhatsApp.\n"
            "4. Saisissez-le ci-dessous puis appuyez sur « Activer ».", 12))
        g.add_widget(Texte("Identifiant de cet appareil :", 12, True))
        ligne = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        ligne.add_widget(Texte(idd, 18, True, c["accent"], size_hint_y=1))
        ligne.add_widget(Bouton("Copier", lambda: Clipboard.copy(idd), principal=False, size_hint_x=.4))
        g.add_widget(ligne)
        msg = urllib.parse.quote(f"Bonjour SITADELO, je veux SITADELO HISSABI ({PRIX_LICENCE_XAF} FCFA, licence à vie).\n"
                                 f"Voici mon identifiant d'appareil, merci de créer mon mot de passe de connexion :\n{idd}")
        g.add_widget(Bouton("1. Envoyer mon identifiant sur WhatsApp",
                            lambda: ouvrir_url(f"https://wa.me/{NUMERO_WHATSAPP.replace('+', '')}?text={msg}"),
                            couleur="#25D366"))
        l2 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        l2.add_widget(Bouton("Copier n° Airtel", lambda: Clipboard.copy(NUMERO_AIRTEL), principal=False, height=dp(40), taille=12))
        l2.add_widget(Bouton("Copier n° Moov", lambda: Clipboard.copy(NUMERO_MOOV), principal=False, height=dp(40), taille=12))
        g.add_widget(l2)
        g.add_widget(Texte("Mot de passe de connexion reçu après le paiement :", 12, True))
        self.code = Champ("ex. jean.k4m7qz3d", "", height=dp(46))
        self.code.bind(on_text_validate=lambda *_: self.activer())
        g.add_widget(self.code)
        g.add_widget(Bouton("ACTIVER LA LICENCE", self.activer, height=dp(50)))
        l3 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        l3.add_widget(Bouton("Appeler", lambda: ouvrir_url(f"tel:{NUMERO_WHATSAPP}"), couleur="#1976D2"))
        l3.add_widget(Bouton("Message", lambda: ouvrir_url(f"sms:{NUMERO_WHATSAPP}"), couleur="#00897B"))
        g.add_widget(l3)
        g.add_widget(Texte(f"WhatsApp : {NUMERO_WHATSAPP}", 12, False, c["texte2"], "center"))
        g.add_widget(Texte("PARRAINAGE : apportez ou identifiez 10 clients et recevez 10 % de commission OU une licence gratuite.",
                           12, True, c["accent"], "center"))
        g.add_widget(Widget(size_hint_y=None, height=dp(30)))

    def activer(self):
        ok, message = self.app.activer_licence(self.code.text)
        if ok:
            popup_info("Licence activée", message)
            self.app.aller("MENU")
        else:
            popup_info("Activation", message)



# ==============================================================================
# APPLICATION
# ==============================================================================
class HissabiApp(App):
    title = "SITADELO HISSABI"

    def build(self):
        self.dir = self.user_data_dir
        p = lire_json(os.path.join(self.dir, "parametres.json"), {})
        if p.get("theme") in PALETTES:
            STATE["theme"] = p["theme"]
        STATE["sombre"] = bool(p.get("sombre", False))
        STATE["moycr"] = bool(p.get("moycr", True))
        try:
            LANGUE_ACTIVE["idx"] = int(p.get("langue", 0)) % len(LANGUES_5)
        except Exception:
            LANGUE_ACTIVE["idx"] = 0
        self.clavier_visible = False
        self.historique = lire_json(os.path.join(self.dir, "historique.json"), [])
        self.simple = lire_json(os.path.join(self.dir, "simple.json"), [])
        self.fichiers = lire_json(os.path.join(self.dir, "fichiers.json"), [])
        demander_permissions_stockage()
        self.id_appareil = identifiant_appareil(self.dir)
        Window.clearcolor = rgba(couleurs()["fond"])
        try:
            Window.softinput_mode = "below_target"
        except Exception:
            pass
        self.sm = ScreenManager(transition=NoTransition())
        self.ecrans = {}
        for cls in (EcranSplash, EcranLicence, EcranMenu, EcranNotes, EcranSimple, EcranDate, EcranUnites,
                    EcranLangues, EcranBac, EcranBulletin, EcranPDF, EcranHistorique, EcranParam):
            e = cls(self)
            self.ecrans[cls.NOM] = e
            self.sm.add_widget(e)
        Window.bind(on_key_down=self.touche, on_keyboard=self.retour)
        charger_taux_en_arriere_plan()
        return self.sm

    def on_pause(self):
        return True

    def on_stop(self):
        try:
            self.ecrans["NOTES"].on_leave()
        except Exception:
            pass

    # -- navigation ---------------------------------------------------------------
    def aller(self, nom):
        e = self.ecrans.get(nom)
        if e is None:
            return
        if self.sm.current == nom:
            if e.sale:
                e.on_pre_enter()
            return
        self.sm.current = nom

    def invalider(self):
        for e in self.ecrans.values():
            e.sale = True
        cur = self.sm.current_screen
        if cur is not None and cur.name != "SPLASH":
            cur.on_pre_enter()

    def apres_splash(self):
        self.aller("MENU" if self.licence() else "LICENCE")

    # -- paramètres ---------------------------------------------------------------------
    def sauver_params(self):
        ecrire_json(os.path.join(self.dir, "parametres.json"),
                    {"theme": STATE["theme"], "sombre": STATE["sombre"], "moycr": STATE["moycr"], "langue": LANGUE_ACTIVE["idx"]})

    def choisir_theme(self, nom):
        STATE["theme"] = nom
        self.sauver_params()
        Window.clearcolor = rgba(couleurs()["fond"])
        self.invalider()

    def couleur_suivante(self):
        i = ORDRE_PALETTES.index(STATE["theme"]) if STATE["theme"] in ORDRE_PALETTES else -1
        self.choisir_theme(ORDRE_PALETTES[(i + 1) % len(ORDRE_PALETTES)])

    def basculer_moycr(self):
        STATE["moycr"] = not STATE["moycr"]
        self.sauver_params()
        self.invalider()

    def basculer_sombre(self):
        STATE["sombre"] = not STATE["sombre"]
        self.sauver_params()
        Window.clearcolor = rgba(couleurs()["fond"])
        self.invalider()

    def changer_langue(self, idx):
        LANGUE_ACTIVE["idx"] = idx
        self.sauver_params()
        self.invalider()

    def basculer_clavier(self):
        self.clavier_visible = not self.clavier_visible
        self.invalider()

    # -- licence ------------------------------------------------------------------------------
    def _fichiers_licence(self):
        return [os.path.join(self.dir, "licence.json"), os.path.join(os.path.expanduser("~"), ".sitadelo_licence.json")]

    def licence(self):
        for f in self._fichiers_licence():
            d = lire_json(f, None)
            if d and d.get("active") is True and verifier_code_licence(d.get("code", ""), self.id_appareil):
                return d
        return None

    def activer_licence(self, code):
        code = str(code).strip().lower()
        if not code:
            return False, "Veuillez saisir votre mot de passe de connexion."
        if not verifier_code_licence(code, self.id_appareil):
            return False, ("Mot de passe refusé.\n\nUn mot de passe n'est valable que pour UN SEUL appareil : celui "
                           "pour lequel il a été délivré. Contactez SITADELO sur WhatsApp.")
        d = {"active": True, "code": code, "device_id": self.id_appareil,
             "date_activation": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "prix_xaf": PRIX_LICENCE_XAF, "type": "A_VIE"}
        ok = [ecrire_json(f, d) for f in self._fichiers_licence()]
        if any(ok):
            return True, "Activation réussie. Votre licence est valable à vie sur cet appareil."
        return False, "Impossible d'enregistrer la licence sur cet appareil."

    def nom_utilisateur(self):
        try:
            code = (self.licence() or {}).get("code", "")
            return code.rpartition(".")[0].replace("_", " ").replace("-", " ").title()
        except Exception:
            return ""

    # -- données ------------------------------------------------------------------------------------
    def charger_brouillon(self):
        return lire_json(os.path.join(self.dir, "brouillon.json"), None)

    def sauver_brouillon(self, data):
        ecrire_json(os.path.join(self.dir, "brouillon.json"), data)

    def ajouter_historique(self, bilan, data):
        self.historique.insert(0, {"date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                   "moyenne": formater_nombre(bilan.get("moyenne_generale")),
                                   "decision": bilan.get("decision", "--"), "data": data})
        self.historique = self.historique[:200]
        ecrire_json(os.path.join(self.dir, "historique.json"), self.historique)

    def charger_calcul(self, e):
        self.ecrans["NOTES"].charger(e["data"])
        self.aller("NOTES")

    def ajouter_simple(self, expression, resultat):
        self.simple.insert(0, {"expression": expression, "resultat": str(resultat)})
        self.simple = self.simple[:200]
        ecrire_json(os.path.join(self.dir, "simple.json"), self.simple)

    # -- fichiers de sortie (PDF / Word) -------------------------------------------------------------------
    def dossier_prive(self, zone):
        d = os.path.join(self.dir, "fichiers", zone)
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def chemin_sortie(self, zone, ext):
        """Chemin de travail (privé, toujours inscriptible). Le fichier est ensuite copié dans Fichiers par publier()."""
        return os.path.join(self.dossier_prive(zone),
                            f"SITADELO_HISSABI_{zone}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")

    def _sauver_index(self):
        ecrire_json(os.path.join(self.dir, "fichiers.json"), self.fichiers[:300])

    def publier(self, chemin, zone):
        """Copie le fichier dans le stockage public (Fichiers / Gestionnaire de fichiers) et l'ajoute à « Mes PDF »."""
        ext = chemin.rsplit(".", 1)[-1].lower()
        e = {"nom": os.path.basename(chemin), "zone": zone, "ext": ext, "local": chemin, "uri": "", "chemin": "",
             "affiche": "", "public": False, "date": datetime.now().strftime("%d/%m/%Y %H:%M")}
        try:
            if platform == "android":
                r = _publier_android(chemin, zone, ext)
                if r:
                    e.update(r)
            else:
                import shutil
                d = os.path.join(os.path.expanduser("~"), DOSSIER_PUBLIC, zone)
                os.makedirs(d, exist_ok=True)
                dest = os.path.join(d, e["nom"])
                shutil.copyfile(chemin, dest)
                e.update({"chemin": dest, "affiche": dest, "public": True})
        except Exception:
            pass
        if not e["public"]:
            e["chemin"], e["affiche"] = chemin, chemin
        self.fichiers = [x for x in self.fichiers if x.get("nom") != e["nom"]]
        self.fichiers.insert(0, e)
        self._sauver_index()
        return e

    def fin_export(self, zone, chemin, ok, genre):
        if not ok or not os.path.exists(chemin):
            return popup_info(genre, "La génération du fichier a échoué.")
        popup_fichier(self, self.publier(chemin, zone))

    def ouvrir_entree(self, e):
        # fichier resté en privé (ancienne version ou copie impossible) : on tente de le publier d'abord
        if platform == "android" and not e.get("uri") and not e.get("public"):
            loc = e.get("local") or e.get("chemin")
            if loc and os.path.exists(loc):
                e = self.publier(loc, e.get("zone") or "PDF_Universitaire")
        return ouvrir_fichier(e)

    def liste_fichiers(self, zone):
        res = [x for x in self.fichiers if x.get("zone") == zone]
        vus = {x["nom"] for x in res}
        dossiers = [self.dossier_prive(zone)]
        if platform != "android":
            dossiers.insert(0, os.path.join(os.path.expanduser("~"), DOSSIER_PUBLIC, zone))
        else:
            dossiers.append("/storage/emulated/0/Documents/" + DOSSIER_PUBLIC + "/" + zone)
        for d in dossiers:
            try:
                for n in sorted(os.listdir(d), reverse=True):
                    if n.lower().endswith((".pdf", ".docx")) and n not in vus:
                        res.append({"nom": n, "zone": zone, "ext": n.rsplit(".", 1)[-1].lower(), "chemin": os.path.join(d, n),
                                    "local": os.path.join(d, n), "uri": "", "affiche": os.path.join(d, n), "public": False})
                        vus.add(n)
            except Exception:
                continue
        return res

    # -- clavier physique (Ctrl + touche) et bouton retour ------------------------------------------------------
    def touche(self, win, key, scancode, codepoint, modifiers):
        if "ctrl" not in modifiers:
            if key == 278 and self.sm.current == "MENU":      # Home : quitter
                self.stop()
                return True
            return False
        ch = (codepoint or (chr(key) if 32 <= key < 127 else "")).lower()
        e = self.sm.current_screen

        def appel(nom, repli=None):
            f = getattr(e, nom, None) or (getattr(e, repli, None) if repli else None)
            if f:
                f()
        actions = {
            "s": lambda: appel("exporter_pdf"), "w": lambda: appel("exporter_word"), "n": lambda: appel("nouveau"),
            "z": lambda: appel("annuler"), "y": lambda: appel("refaire"), "p": lambda: self.aller("PARAM"),
            "r": lambda: appel("reinitialiser", "nouveau"), "h": lambda: self.aller("HISTORIQUE"),
            "b": self.couleur_suivante, "k": self.basculer_clavier, "d": lambda: self.aller("PDF"),
            "1": lambda: self.aller("NOTES"), "2": lambda: self.aller("SIMPLE"),
            "3": lambda: self.aller("DATE"), "4": lambda: self.aller("UNITES"),
        }
        if ch in actions:
            actions[ch]()
            return True
        return False

    def retour(self, win, key, *args):
        if key == 27:
            if self.sm.current not in ("MENU", "SPLASH", "LICENCE"):
                self.aller("MENU")
                return True
        return False


if __name__ == "__main__":
    HissabiApp().run()
