#!/usr/bin/env python3
#-*- coding: utf-8 -*-

import os, glob, pickle, PyPDF2, csv, copy
from parse import parse
from parse import compile
from lxml import etree
import utils.interface_xml as xml
from utils.parametres import filieres
from utils.parametres import nb_classes
from utils.classes import Fichier
# contient différentes fonctions utiles

############## Trouver le rang d'un candidat dans une liste de dossiers, selon un critère donné
def rang(cand, dossiers, fonction):
    rg = 1
    score_actu = fonction(cand)
    if dossiers:
        while (rg <= len(dossiers) and fonction(dossiers[rg-1]) > score_actu):
            rg+= 1
    return rg

############## Manipulation de répertoires
def efface_dest(chem):
    # Supprime le dossier pointé par le chemin chem
    for filename in os.listdir(chem):
        fich = os.path.join(chem, filename)
        if os.path.isdir(fich):
            efface_dest(fich) # appel récursif pour les sous-dossiers
        else:
            os.remove(fich) # on efface les fichiers
    os.rmdir(chem) # suppression du dossier vide

def restaure_virginite(chem): #  amélioration : shutil a une fonction qui supprime un répertoire non vide
    # Créé le répertoire pointé par chem ou le vide s'il existe
    # En gros, redonne une complète virginité à ce répertoire
    efface_dest(chem) # on efface chem (s'il existe)
    os.mkdir(chem) # on le (re)-créé

############## Découpage du fichier PDF (dossiers candidats)
def decoup(sourc, dest):
	"sourc: fichier source"
	"dest: dossier destination"
	# précompilation de la requête pour gagner en vitesse
	regex = compile('{}Dossier n°{id:d}{}Page {page:d}')
	pdfFileObj = open(sourc, 'rb')
	pdfReader = PyPDF2.PdfFileReader(pdfFileObj)
	page_deb = -1
	id_cand = -1
        # pour le candidat -1, au lieu de faire un cas particulier
	pdfWriter = PyPDF2.PdfFileWriter()
	for page in range(pdfReader.numPages):
                # récupération de la page courante
		pageObj = pdfReader.getPage(page)
                # puis de son texte brut
		txt = pageObj.extractText()
                # et enfin, numéro de dossier et page
		res = regex.parse(txt)
		if res or page == pdfReader.numPages-1:
                        # est-ce un changement de candidat?
			if (id_cand != res['id']
                            or page == pdfReader.numPages-1):
				nom = os.path.join (dest, 'docs_{}.pdf'.format(id_cand))
				pdfOutputFile = open(nom, 'wb')
                                # sinon il en manque un bout
				if page == pdfReader.numPages-1:
                                        pdfWriter.addPage(pageObj)
                                # écrasement de tout fichier existant!!
				pdfWriter.write(pdfOutputFile)
				pdfOutputFile.close()
				# réinitialisations
				pdfWriter = PyPDF2.PdfFileWriter()
				id_cand = res['id']
			pdfWriter.addPage(pageObj)
	os.remove(os.path.join(dest, 'docs_-1.pdf'))

############## Création des statistiques (nb candidatures par filière).
def stat():
    # Effectue des statistiques sur les candidats
    list_fich = [Fichier(fich) for fich in glob.glob(os.path.join(os.curdir, "data", "admin_*.xml"))]
    # Initialisation des compteurs
    # L'info de candidatures est stockée dans un nombre binaire où 1 bit 
    # correspond à 1 filière. Un dictionnaire 'candid' admet ces nombres binaires pour clés,
    # et les valeurs sont des nombres de candidats. 
    # candid = {'001' : 609, '011' : 245, ...} indique que 609 candidats ont demandé
    # le filière 1 et 245 ont demandé à la fois la filière 1 et la filière 2

    # Initialisation du dictionnaire stockant toutes les candidatures
    candid = {}
    for i in range(2**len(filieres)):
        candid[i] = 0

    # Recherche des candidatures
    # On stocke dans une liste les identifiants des candidats vus,
    # cela évite de les traiter 2 fois...
    deja_vu = set([])
    for fich in list_fich:  # pour chaque fichier (et donc filière !)
        for candi in fich:   # pour toutes les candidatures de la filière relative au fichier fich
            iden = xml.get_id(candi)
            # puis recherche du même candidat dans les autres filières,
            # création du nombre stockant les filières demandées
            # et incrémentation du compteur adéquat
            if not(iden in deja_vu): # candidat pas encore vu
                deja_vu.add(iden)
                # on récupère la liste des fichiers contenant ce candidat
                list_fich_candi = [f for f in list_fich if (candi in f)]
                # Liste des valeurs (2^bit) relatives à chacune de ces filières
                list_index = [2**filieres.index(f.filiere().lower()) for f in list_fich_candi]
                # OU exclusif sur tous les index
                cc = 0
                for k in list_index:
                    cc |= k # évite de compter 2 fois, même si deja_vu gère !
                ### statistiques
                if not('non validée' in xml.get_motifs(candi)):
                    candid[cc] += 1 # incrémentation du compteur candidatures multiples
                    print("j'incrémente {}, le candidat est : {}".format(cc, xml.get_nom(candi)))
                    for f in list_fich_candi:
                        # Incrémentation du compteur filière (sauf si déjà fait !) :
                        if cc != 2**filieres.index(f.filiere().lower()):
                            candid[2**filieres.index(f.filiere().lower())] += 1
                        # Écriture du noeud 'candidatures'
                        xml.set_candidatures(f.get_cand(candi), cc)
        # Sauvegarder
        fich.sauvegarde()
    
    # Écrire le fichier stat
    with open(os.path.join(os.curdir, "data", "stat"), 'wb') as stat_fich:
        pickle.dump(candid, stat_fich)

############## Générer les tableaux .csv bilans de la commission
def tableaux_bilan(list_fich):
    """ Cette fonction créé les tableaux dont a besoin l'admin pour la suite du recrutement"""
    # Un peu de ménage...
    dest = os.path.join(os.curdir, "tableaux")
    restaure_virginite(dest)
    # Pour chaque filière :
    for fich in list_fich:
        # 1er tableau : liste ordonnée des candidats retenus, pour l'admin
        nom = os.path.join(os.curdir, "tableaux", "") # chaîne vide pour avoir / à la fin du chemin...
        nom += fich.filiere()
        nom += '_retenus.csv'
        c = csv.writer(open(nom, 'w'))
        entetes = ['Rang brut', 'Rang final', 'Nom', 'Prénom', 'Date de naissance', 'score brut', 'correction', 
        'score final', 'jury', 'Observations']
        c.writerow(entetes)
        for cand in fich:
            a = (xml.get_scoref(cand) != 'NC')
            b = not(a) or (int(xml.get_rang_final(cand)) <= int(nb_classes[fich.filiere().lower()]))
            if a and b: # seulement les classés dont le rang est inférieur à la limite fixée
                data = [fonction(cand) for fonction in [xml.get_rang_brut, xml.get_rang_final, xml.get_nom, 
                xml.get_prenom, xml.get_naiss, xml.get_scoreb, xml.get_correc, xml.get_scoref, xml.get_jury, 
                xml.get_motifs]]
                c.writerow(data)
        # 2e tableau : liste ordonnée des candidats retenus, pour Bureau des élèves
        # Le même que pour l'admin, mais sans les notes, ni les rangs bruts...
        nom = os.path.join(os.curdir, "tableaux", "") # chaîne vide pour avoir / à la fin du chemin..
        nom += fich.filiere()
        nom += '_retenus(sans_note).csv'
        c = csv.writer(open(nom, 'w'))
        entetes = ['Rang final', 'Nom', 'Prénom', 'Date de naissance']
        c.writerow(entetes)
        for cand in fich:
            a = (xml.get_scoref(cand) != 'NC')
            b = not(a) or (int(xml.get_rang_final(cand)) <= int(nb_classes[fich.filiere().lower()]))
            if a and b: # seulement les classés dont le rang est inférieur à la limite fixée
                data = [fonction(cand) for fonction in [xml.get_rang_final , xml.get_nom, 
                xml.get_prenom, xml.get_naiss]]
                c.writerow(data)
        # 3e tableau : Liste alphabétique de tous les candidats avec le numéro dans le classement,
        # toutes les notes et qq infos administratives
        # Fichier destination
        nom = os.path.join(os.curdir, "tableaux", "") # chaîne vide pour avoir / à la fin du chemin...
        nom += fich.filiere()
        nom += '_alphabetique.csv'
        c = csv.writer(open(nom, 'w'))
        entetes = ['Rang brut', 'Rang final', 'Candidatures', 'Nom', 'Prénom', 'Date de naissance', 'Sexe', 
        'Nationalité', 'id_apb', 'Boursier', 'Classe actuelle', 'Etablissement', 'Commune Etablissement']
        # entêtes notes...
        matiere = {'M':'Mathématiques', 'P':'Physique/Chimie'}
        date = {'1':'trimestre 1', '2':'trimestre 2', '3':'trimestre 3'}
        classe = {'P':'Première', 'T':'Terminale'}
        entetes.extend([cl + mat + da for cl in classe for da in date for mat in matiere])
        entetes.extend(['F_écrit', 'F_oral', 'CPES_math', 'CPES_phys'])
        # la suite
        entetes.extend(['score brut', 'correction', 'score final', 'jury', 'Observations'])
        c.writerow(entetes)
        # Remplissage du fichier dest dans l'ordre alphabétique
        for cand in fich.ordonne('alpha'):
            data = [xml.get_rang_brut(cand), xml.get_rang_final(cand), xml.get_candidatures(cand)]
            data += [fonction(cand) for fonction in [xml.get_nom, xml.get_prenom, xml.get_naiss, xml.get_sexe,
            xml.get_nation, xml.get_id, xml.get_boursier, xml.get_clas_actu, xml.get_etab, xml.get_commune_etab]]
            # Les notes...
            for cl in classe:
                for da in date:
                    for mat in matiere:
                        key = cl + mat + da
                        note = '{}'.format(xml.get_note(cand, classe[cl], matiere[mat],date[da]))
                        data.append(note)
            data.extend([xml.get_ecrit_EAF(cand), xml.get_oral_EAF(cand)])
            cpes = 'cpes' in xml.get_clas_actu(cand).lower()
            data.extend([xml.get_CM1(cand, cpes), xml.get_CP1(cand, cpes)])
            # La suite
            data.extend([fonction(cand) for fonction in [xml.get_scoreb, xml.get_correc, xml.get_scoref,
            xml.get_jury, xml.get_motifs]])
            c.writerow(data)
