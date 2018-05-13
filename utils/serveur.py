#!/usr/bin/env python3
#-*- coding: utf-8 -*-

""" Cet objet est instancié par le programme principal. Il est l'interface entre les navigateurs connectés et 
l'application. """

# Comment serveur et navigateur discutent :

# navigateur --> serveur :
# par l'intermédiaire des formulaires html. Dans la déclaration d'un formulaire,
# un choix method = POST (ou GET) action = nom_d_une_méthode_python (décorée par @cherrypy.expose) qui sera exécutée dès 
# la validation du formulaire.
# Les éléments du formulaire sont accessibles dans le dictionnaire kwargs...
# Une méthode n'est 'visible' par le navigateur que si elle est précédée par @cherrypy.expose
#
# serveur --> navigateur :
# en retour (par la fonction return), le code python renvoi le code --- sous la forme d'une chaine (immense) de 
# caractères --- d'une page html.
#
# Immmédiatement après la connection au serveur, la page affichée est celle retournée par la méthode 'index'.
#

# L'objet serveur dispose :
# *** d'un attribut qui est une instance d'un objet 'Composeur'. C'est cet objet qui a la charge de fabriquer le code 
# html (voir commentaire dans le fichier qui définit cet objet).
# *** d'un attribut qui est un dictionnaire d'instances d'objets "Client". Chaque navigateur se connectant au serveur 
# est un client. Ce dictionnaire permet, en partenariat avec un cookie déposé sur chaque machine client, d'identifier 
# qui dépose telle ou telle requête.
#
# Les clients sont de 2 types : soit de type administrateur, soit de type jury. En fonctionnement standard 
# (commission.py non lancée en mode test) le navigateur situé sur la machine qui exécute commission.py est 
# administrateur et les navigateurs extérieurs sont jurys.

import os, cherrypy, glob, webbrowser
from utils.parametres import entete
# Chargement de toutes les classes dont le serveur a besoin
from utils.clients import Jury, Admin
from utils.fichier import Fichier
from utils.composeur import Composeur


########################################################################
#                        Class Serveur                                 #
########################################################################

class Serveur(): # Objet lancé par cherrypy dans le __main__
    "Classe générant les objets gestionnaires de requêtes HTTP"
    
    def __init__(self, test, ip):
        """ constructeur des instances 'Serveur' """
        self.clients =  {}  # dictionnaire contenant les clients connectés
        self.test = test  # booléen : version test (avec un menu "Admin or Jury ?")
        self.rafraich = False  # booléen qui sert à activer ou nom la fonction refresh
        self.comm_en_cours = (ip != '127.0.0.1')  # booléen True pendant la commission --> menu ad hoc
        self.fichiers_utilises = [] # Utile pour que deux jurys ne choisissent pas le même fichier..
        self.html_compose = Composeur(entete) # instanciation d'un objet Composeur de page html.
        navi = webbrowser.get()  # Quel est le navigateur par défaut ?
        navi.open_new('http://'+ip+':8080')  # on ouvre le navigateur internet, avec la bonne url..

    def set_rafraich(self, bool = False):
        """ Booléen : si un évènement qqc doit être suivi d'un rafraichissement de page, se booléen sera True """
        self.rafraich = bool

    def get_rafraich(self):
        """ renvoie 'self.refraich' """
        return self.rafraich

    @cherrypy.expose
    def refresh(self, **kwargs):
        """ Rafraîchir un client suite à un évènement Server (SSE) """
        # Renvoie un générateur permettant de demander au client de rafraichir sa page si 'self.rafraich' == True
        # 'retry : 5000' demande au navigateur de guetter toutes les 5 secondes si une telle demande est faite.
        cherrypy.response.headers["content-type"] = "text/event-stream"
        def msg():
            yield "retry: 5000\n\n"
            if self.get_rafraich():
                self.set_rafraich(False) # On ne rafraîchit qu'une fois à la fois !
                yield "event: message\ndata: ok\n\n"
        return msg()

    def get_client_cour(self):
        """ renvoie le client courant en lisant le cookie de session """
        return self.clients[cherrypy.session["JE"]]

    ########## Début des méthodes exposées au serveur ########
    # Toutes renvoient une page html. 'index' est la méthode appelée à la connection avec le serveur
    # (adresse = ip:8080 ; ip est 127.0.0.1 par défaut. voir programme principal)
    #
    @cherrypy.expose
    def index(self):
        """ Retourne la page d'entrée du site web """
        # S'il n'y a pas déjà un cookie de session sur l'ordinateur client, on en créé un
        if cherrypy.session.get('JE', 'none') == 'none':
            key = 'client_{}'.format(len(self.clients) + 1) # clé d'identification du client
        else: # sinon,
            # on récupère la clé
            key = cherrypy.session['JE']
            # et on vire l'objet client associé
            self.clients.pop(key, '') # supprime l'entrée correspondante à ce client dans self.clients
            # Supprimer cet objet permet de libérer le fichier traité précédemment : il redevient
            # accessible aux autres jurys... Pour qu'il reste verrouillé, il suffit de ne pas retourner
            # sur la page d'accueil !
        cherrypy.session['JE'] = key # Cookie de session en place; stocké sur la machine client
        ##### suite
        # Le client est-il sur la machine serveur ?
        if cherrypy.request.local.name == cherrypy.request.remote.ip:
            # Si oui, en mode TEST on affiche un menu de choix : "login Admin ou login Commission ?"
            # Si oui, en mode "normal", ce client est Admin
            if self.test: # Mode TEST ou pas ?
                return self.html_compose.menu()
            else:
                # Machine serveur et Mode normal ==> c'est un Client Admin
                # On créé un objet Admin associé à la clé key
                self.clients[key] = Admin(key)
        else:
            # Si non, c'est un Client Jury (peu importe qu'on soit en mode TEST)
            # On créé un objet Jury associé à la clé key
            self.clients[key] = Jury(key)
        # On affiche le menu du client
        return self.affiche_menu()

    @cherrypy.expose
    def identification(self, **kwargs):
        """ Appelée quand un choix est fait dans le menu du mode test; reçoit ce choix : Admin/Jury. Retourne la page 
        menu adéquat. """
        key = cherrypy.session['JE'] # quel client ?
        if kwargs.get('acces', '') == "Accès administrateur": # pourquoi 'acces' n'existe-t-il parfois pas ?!
            self.clients[key] = Admin(key) # création d'une instance admin
        else:
            self.clients[key] = Jury(key) # création d'une instance jury
        return self.affiche_menu() # Affichage du menu adéquat
  
    @cherrypy.expose
    def affiche_menu(self):
        """ Retourne le menu principal du client """
        # Si client est jury, ce menu propose de choisir le fichier comm_XXX.xml que ce jury souhaite traiter.
        # Si client est admin, ce menu est le tableau de bord de l'admin (il change selon que la commission a eu
        # lieu ou pas : voir Composeur).
        # Admin revient à ce menu lorsqu'il appuie sur le bouton 'RETOUR'. Dans ce cas, on restitue des droits
        # "vierges" de toute référence à une filière (intervient dans l'entête de page html).
        client = self.get_client_cour() # quel client ?
        client.set_droits('') # on supprime la référence à une filière dans les droits (voir entête de page)
        if client.fichier: # le client a déjà sélectionné un fichier, mais il revient au menu
            self.fichiers_utilises.remove(client.fichier.nom) # on fait du ménage
            client.fichier = None
        # on redéfinit le type de retour (nécessaire quand on a utilisé des SSE)
        # voir la méthode 'refresh'.
        cherrypy.response.headers["content-type"] = "text/html"
        return self.html_compose.menu(client, self.fichiers_utilises, self.comm_en_cours)

    @cherrypy.expose
    def traiter_parcourssup(self, **kwargs):
        """ Appelée quand l'admin clique sur le bouton 'Traiter / Vérifier' qui se trouve dans son premier menu.  Lance 
        le traitement des fichiers *.csv et *.pdf en provenance de ParcoursSup, puis un décompte des candidatures 
        (fonction stat). Retourne une page de type 'event-stream' qui indique l'avancement de ce traitement. """
        cherrypy.response.headers["content-type"] = "text/event-stream" # type de retour 'event-stream'
        admin = self.get_client_cour() # admin <-- qui est le demandeur ?
        def contenu(): # générateur fournissant au navigateur, au compte-goutte, le contenu de la page.
            yield "Début du Traitement\n\n"
            ## Traitement des csv ##
            generateur = admin.traiter_csv() # la fonction traiter_csv (voir classe Admin) est également un générateur
            for txt in generateur: # générateur qu'on sollicite jusqu'à épuisement.
                yield txt
            ## Fin du traitement des csv ##
            ## Traitement des pdf ##
            generateur = admin.traiter_pdf() # On reproduit ce fonctionnement avec traiter_pdf..
            for txt in generateur:
                yield txt
            # Fin du traitement pdf#
            # Faire des statistiques
            yield "\n     Décompte des candidatures\n\n"
            list_fich = [Fichier(fich) for fich in glob.glob(os.path.join(os.curdir, "data", "admin_*.xml"))]
            admin.stat(list_fich) # combien de demande par filière, et multi-candidatures..
            # Fin : retour au menu
            self.set_rafraich(True) # utile ? à tester.
            yield "\n\nTRAITEMENT TERMINÉ.      --- VEUILLEZ CLIQUER SUR 'PAGE PRÉCÉDENTE' POUR REVENIR AU MENU  ---"
        return contenu()

    @cherrypy.expose
    def choix_comm(self, **kwargs):
        """ Appelée quand un jury sélectionne un fichier dans son menu. Retourne la page de traitement de ce dossier. 
        """
        self.set_rafraich(True) # On rafraîchit les menus des Jurys... (ce fichier n'est plus disponible)
        cherrypy.response.headers["content-type"] = "text/html"
        # récupère le client
        client = self.get_client_cour() # quel jury ? (sur quel machine ? on le sait grâce au cookie)
        # Teste si le fichier n'a pas été choisi par un autre jury
        if kwargs["fichier"] in self.fichiers_utilises:
            # Si oui, retour menu
            self.affiche_menu()
        else:
            # sinon, mise à jour des attributs du client : l'attribut fichier du client va recevoir une instance d'un 
            # objet Fichier, construit à partir du nom de fichier.
            client.set_fichier(Fichier(kwargs["fichier"]))
            # Mise à jour de la liste des fichiers utilisés
            self.fichiers_utilises.append(client.fichier.nom)
            ## Initialisation des paramètres
            # mem_scroll : cookie qui stocke la position de l'ascenseur dans la liste des dossiers
            cherrypy.session['mem_scroll'] = '0'
            # Affichage de la page de gestion des dossiers
            return self.affi_dossier()
    
    @cherrypy.expose
    def choix_admin(self, **kwargs):
        """ Appelée quand l'admin sélectionne un fichier 'admin_XXX.xml' dans son premier menu. Retourne la page de 
        traitement de ce dossier. """
        cherrypy.response.headers["content-type"] = "text/html"
        # récupère le client
        client = self.get_client_cour() # quel client ? (sur quel machine ? on le sait grâce au cookie)
        # Mise à jour des attributs du client : l'attribut fichier du client va recevoir une instance d'un objet 
        # Fichier, construit à partir du nom de fichier.
        client.set_fichier(Fichier(kwargs["fichier"]))
        self.fichiers_utilises.append(client.fichier.nom)
        ## Initialisation des paramètres
        # mem_scroll : cookie qui stocke la position de l'ascenseur dans la liste des dossiers
        cherrypy.session['mem_scroll'] = '0'
        # Affichage de la page de gestion des dossiers
        return self.affi_dossier()      
    
    @cherrypy.expose
    def affi_dossier(self):
        """ Retourne la page de traitement d'un dossier. Page maîtresse de toute l'application. """
        # On transmets le client et le cookie de mémorisation de position d'ascenseur à l'instance Composeur qui se 
        # charge de tout..
        return self.html_compose.page_dossier(self.get_client_cour(), cherrypy.session['mem_scroll'])
    
    @cherrypy.expose
    def traiter(self, **kwargs):
        """ Appelée quand un client valide un dossier un cliquant sur 'Classer' ou 'NC'. Retourne une page dossier. """
        # Cette méthode sert à mettre à jour le dossier du candidat...
        # C'est le travail du client courant à qui on passe tous les paramètres du formulaire html : dictionnaire kwargs
        self.get_client_cour().traiter(**kwargs)    # chaque client traite à sa manière !!
        # Si Jury, on rafraîchit la page menu de l'admin (mise à jour du décompte des traitements)
        if isinstance(self.get_client_cour(), Jury):
            self.set_rafraich(True)
        # Et on retourne à la page dossier
        return self.affi_dossier()
        
    @cherrypy.expose
    def click_list(self, **kwargs):
        """ Appelée lors d'un click dans la liste de dossiers (à droite dans la page de traitement des dossiers).  
        Retourne la page dossier du candidat choisi. """
        # Mémorisation de la position de l'ascenseur (cette position est donnée dans les paramètres du formulaire html)
        cherrypy.session["mem_scroll"] = kwargs['scroll_mem']
        # On récupère l'argument num (numéro du dossier indiqué juste avant le nom du candidat)
        txt = kwargs['num']
        # dont on extrait le numéro de dossier (3 premiers caractères) : ce numéro indique l'index du candidat dans le 
        # fichier courant..
        self.get_client_cour().num_doss = int(txt[:3])-1 # mise à jour de l'attribut 'num_doss' du client courant.
        return self.affi_dossier()
    
    @cherrypy.expose
    def genere_fichiers_comm(self):
        """ Appelée par l'admin (1er menu). Lance la création des fichiers comm_XXX.xml. Retourne la page menu; mais 
        après génération des fichiers comm, celle-ci sera le 2e menu admin. """
        self.get_client_cour().generation_comm() # c'est le boulot de l'admin courant.
        # Et on retourne au menu
        return self.affiche_menu()

    @cherrypy.expose
    def clore_commission(self):
        """ Appelée par l'admin (2e menu, bouton 'Récolter'). Lance la récolte du travail des jurys; fabrique les fiches 
        bilan et les tableaux récapitulatifs. """
        self.get_client_cour().clore_commission() # C'est le boulot de l'admin courant
        # Et on retourne au menu
        return self.affiche_menu()
    
    @cherrypy.expose
    def page_impression(self, **kwargs):
        """ Appelée par l'admin (2e menu, clique sur un fichier class_XXX.xml). Lance le menu d'impression des fiches 
        bilan de commission. Retourne la page impression (elle ne contient que le bouton 'RETOUR' (merci le css). """
        client = self.get_client_cour() # récupère le client (c'est un admin !)
        # Mise à jour des attributs du client
        client.set_fichier(Fichier(kwargs["fichier"])) # son fichier courant devient celui qu'il vient de choisir
        self.fichiers_utilises.append(client.fichier.nom) # peu utile !
        return self.html_compose.page_impression(client)