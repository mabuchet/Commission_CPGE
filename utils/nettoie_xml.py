from lxml import etree
from utils.fichier import Fichier

# Le résultat de la reconnaissance des données sur ParcoursSup est
# parfois un peu brut : on procède à l'assainissement.

#
# FONCTIONS DE POST-TRAITEMENT
#
# Variables globales
series_valides = ["Scientifique", "Préparation au bac Européen"]
series_non_valides = ["Sciences et Technologies de l'Industrie et du Développement Durable",
        "Economique et social", "Littéraire", "Sciences et technologie de laboratoire",
        "Professionnelle"]

# certains bulletins sont très vides : on nettoie.

def elague_bulletins_triviaux(candidat, test = False):

    # on trouve la liste des bulletins sans note:
    probs = candidat.xpath('bulletins/bulletin[matières[not(matière)]]')
    for prob in probs:
        candidat.xpath('bulletins')[0].remove(prob)

    return candidat

def filtre(candidat, test = False):
    prefixe = ''
    commentaire = ''
    # Candidature validée ?
    if candidat.xpath('synoptique/établissement/candidature_validée')[0].text.lower() != 'oui':
        commentaire = 'Candidature non validée sur ParcoursSup'
        Fichier.set(candidat, 'Correction', 'NC')
        Fichier.set(candidat, 'Jury', 'Admin')
    else: # si validée,
        # on récupère la série
        serie = ''
        probs = candidat.xpath('bulletins/bulletin[classe="Terminale"]')
        for prob in probs: # fausse boucle (normalement)
            serie = prob.xpath('série')[0].text
        # Si série non valide, on exclut
        if serie in series_non_valides:
            commentaire = 'Série {}'.format(serie)
            Fichier.set(candidat, 'Correction', 'NC')
            Fichier.set(candidat, 'Jury', 'Admin')
        else: # sinon, on alerte Admin sur certaines anomalies rencontrées
            prefixe = '- Alerte :'
            # 1/ Série reconnue ?
            if not(serie in series_valides):
                commentaire += ' | Vérifier la série |'
            # 2/ Le dossier est-il complet (toutes les notes présentes + classe actuelle)
            if not(Fichier.is_complet(candidat)):
                commentaire += ' Dossier incomplet |'
    if commentaire != '':
        Fichier.set(candidat, 'Motifs', '{} {}'.format(prefixe, commentaire))
    else: # si aucune remarque, on calcule le score brut
        Fichier.calcul_scoreb(candidat)
    # Fin des filtres; on retourne un candidat mis à jour
    return candidat


#
# FONCTION PRINCIPALE
#

def nettoie(candidats, test = False):
    res = [elague_bulletins_triviaux(candidat, test)
           for candidat in candidats]
    res = [filtre(candidat, test) for candidat in candidats]
    return candidats
