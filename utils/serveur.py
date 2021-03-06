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
# en retour (par la fonction return), python renvoi le code --- sous la forme d'une chaine (immense) de caractères --- 
# d'une page html.
#
# Immmédiatement après la première connection au serveur, la page affichée est celle retournée par la méthode 'index'.
#

# L'objet serveur dispose :
# *** d'un attribut qui est une instance d'un objet 'Composeur'. C'est cet objet qui a la charge de fabriquer le code 
# html (voir commentaire dans le fichier qui définit cet objet).
# *** d'un attribut qui est un dictionnaire d'instances d'objets "Client". Chaque navigateur se connectant au serveur 
# est un client. Ce dictionnaire permet, en partenariat avec un cookie déposé sur chaque machine client, d'identifier 
# qui dépose telle ou telle requête.
#
# Les clients sont de 2 types : soit de type administrateur, soit de type jury. En fonctionnement standard 
# (commission.py non lancé avec l'option jury) le navigateur situé sur la machine qui exécute commission.py est 
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
    """ Classe générant les objets gestionnaires de requêtes HTTP """
    
    def __init__(self, jury, ip):
        """ constructeur des instances 'Serveur' """
        self.clients =  {}  # dictionnaire contenant les clients connectés {'client n' : objet_client }
        self.jury = jury  # booléen : si True, le client "local" sera jury.
        self.fichiers_utilises = {} # Utile pour que deux jurys ne choisissent pas le même fichier..
        self.sse_messages = set() # ensemble des messages SSE à envoyer
        self.sse_message_id = 0 # identifiant des messages SSE (sert à éviter les messages perdus entre 2 reconnections)
        self.html_compose = Composeur(entete) # instanciation d'un objet Composeur de page html.
        navi = webbrowser.get()  # Quel est le navigateur par défaut ?
        navi.open_new('http://'+ip+':8080')  # on ouvre le navigateur internet, avec la bonne url..

    def get_client_cour(self):
        """ renvoie le client courant en lisant le cookie de session """
        return self.clients[cherrypy.session["JE"]]

    def add_sse_message(self, event, data):
        """ ajoute un message dans l'ensemble des messages SSE à envoyer """
        # L'usage d'un ensemble évite les doublons..
        self.sse_messages.add("event: {}\ndata: {}\n\n".format(event, data))

    ########## Début des méthodes exposées au serveur ############
    # Toutes (sauf send_sse_message) renvoient une page html. 'index' est la méthode appelée
    # à la connection avec le serveur
    # (adresse = ip:8080 ; ip est 127.0.0.1 par défaut. voir programme principal)
    ###############################################################
    @cherrypy.expose
    def index(self):
        """ Retourne la page d'entrée du site web """
        # S'il n'y a pas déjà un cookie de session sur l'ordinateur client, on en créé un
        if cherrypy.session.get('JE', 'none') == 'none':
            key = 'client_{}'.format(len(self.clients) + 1) # clé d'identification du client
            cherrypy.session['JE'] = key # Cookie de session en place; stocké sur la machine client
            # Si option -jury ou client n'est pas sur la machine serveur,
            if self.jury or cherrypy.request.local.name != cherrypy.request.remote.ip:
                # Le client sera Jury
                self.clients[key] = Jury(key) # On créé un objet Jury associé à la clé key
            else:
                # Machine serveur et pas d'option -jury ==> c'est un Client Admin
                self.clients[key] = Admin(key) # On créé un objet Admin associé à la clé key
        else: # sinon,
            # on récupère la clé et le client
            key = cherrypy.session['JE']
            client = self.clients[key]
            if client.fichier: # le client a déjà sélectionné un fichier, mais il revient au menu
                self.fichiers_utilises.pop(client) # on fait du ménage, le fichier redevient disponible aux autres jurys
                self.add_sse_message('free', client.fichier.nom) # émission d'un SSE : un fichier se libère
                client.fichier = None
        # On affiche le menu du client
        return self.affiche_menu()

    @cherrypy.expose
    def send_sse_message(self, **kwargs):
        """ Rafraîchir un client suite à un évènement Server (SSE) """
        # Renvoie un générateur permettant de demander au client de rafraichir sa page 
        cherrypy.response.headers["content-type"] = "text/event-stream"
        cherrypy.response.headers["cache-control"] = "no-cache"
        cherrypy.response.headers["connection"] = "keep-alive"
        nb = len(self.sse_messages)
        if nb > 0:
            txt = ""
            for n in range(nb):
                self.sse_message_id += 1
                txt += "id: {}\n{}".format(self.sse_message_id, self.sse_messages.pop())
            return txt

    @cherrypy.expose
    def libere_fichier(self, **kwargs):
        """ Pendant la commission, l'administrateur peut rendre de nouveau accessible le fichier qu'un jury avait 
        préalablement choisi. Si un ordinateur plante, cela peut éviter un redémarrage du serveur """
        fichier = kwargs["fichier"]
        try: 
            # recherche du client concerné
            client = [cli for cli in self.fichiers_utilises.keys() if self.fichiers_utilises[cli] == fichier][0]
            self.fichiers_utilises.pop(client) # on fait du ménage, le fichier redevient disponible aux autres jurys
            client.fichier = None
        except:
            pass
        # Retour au menu
        return self.affiche_menu()
  
    @cherrypy.expose
    def affiche_menu(self):
        """ Retourne le menu principal du client """
        # Si client est jury, ce menu propose de choisir le fichier comm_XXX.xml que ce jury souhaite traiter.
        # Si client est admin, ce menu est le tableau de bord de l'admin (il change selon que la commission a eu
        # lieu ou pas : voir Composeur).
        # Admin revient à ce menu lorsqu'il appuie sur le bouton 'RETOUR'. Dans ce cas, on restitue des droits
        # "vierges" de toute référence à une filière (intervient dans l'entête de page html).
        client = self.get_client_cour() # quel client ?
        client.reset_droits() # on supprime la référence à une filière dans les droits (voir entête de page)
        # Le booléen comm_en_cours est mis-à-jour : True s'il y a des jurys connectés..
        comm_en_cours = self.fichiers_utilises != {}
        # on redéfinit le type de retour (nécessaire quand on a utilisé des SSE)
        # voir la méthode 'send_sse_message'.
        cherrypy.response.headers["content-type"] = "text/html"
        return self.html_compose.menu(client, self.fichiers_utilises, comm_en_cours)

    @cherrypy.expose
    def traiter_parcourssup(self, **kwargs):
        """ Appelée quand l'admin clique sur le bouton 'Traiter / Vérifier' qui se trouve dans son premier menu.  Lance 
        le traitement des fichiers *.csv et *.pdf en provenance de ParcoursSup, puis un décompte des candidatures 
        (fonction appel_stat). Cette méthode renvoie un générateur qui indique l'avancement de ce traitement. """
        admin = self.get_client_cour() # admin <-- qui est le demandeur ?
        # On construit la liste de tout ce qui doit être effectué : liste de couples
        # action [ (méthode (de type générateur) a appeler, 'chaîne à afficher sur la page d'avancement'), etc ]
        action = [
                (admin.traiter_csv, 'Traitement des fichiers csv'),
                (admin.traiter_pdf, 'Traitement des fichiers pdf'),
                (admin.appel_stat , 'Décompte des candidatures'),
                ]
        # On envoie ça au Composeur de page html; celui-ci se charge de fournir une page qui affiche l'état d'avancement 
        # du traitement..
        for mess in self.html_compose.page_progression(action):
            yield mess

    @cherrypy.expose
    def choix_comm(self, **kwargs):
        """ Appelée quand un jury sélectionne un fichier dans son menu. Retourne la page de traitement de ce dossier. 
        """
        # récupère le client
        client = self.get_client_cour() # quel jury ? (sur quel machine ? on le sait grâce au cookie)
        # Teste si le fichier n'a pas été choisi par un autre jury
        fichier = kwargs.get("fichier") # nom du fichier sélectionné par le jury
        a = fichier in self.fichiers_utilises.values()
        b = fichier != self.fichiers_utilises.get(client, 'rien')
        if (a and b):
            # Si oui, retour menu
            return self.affiche_menu()
        else:
            # sinon, mise à jour des attributs du client : l'attribut fichier du client va recevoir une instance d'un 
            # objet Fichier, construit à partir du nom de fichier.
            client.set_fichier(Fichier(fichier))
            # Mise à jour de la liste des fichiers utilisés
            self.fichiers_utilises[client] = fichier
            # On émet un message SSE : ajout d'un fichier à la liste des fichiers en cours de traitement
            self.add_sse_message('add', fichier)
            # mem_scroll initialisé : cookie qui stocke la position de l'ascenseur dans la liste des dossiers
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
        cherrypy.response.headers["content-type"] = "text/html" # rétablir l'entête après SSE (voir send_sse_message)
        return self.html_compose.page_dossier(self.get_client_cour(), cherrypy.session['mem_scroll'])
    
    @cherrypy.expose
    def traiter(self, **kwargs):
        """ Appelée quand un client valide un dossier un cliquant sur 'Classer' ou 'NC'. Retourne une page dossier. """
        # Cette méthode sert à mettre à jour le dossier du candidat...
        # C'est le travail du client courant à qui on passe tous les paramètres du formulaire html : dictionnaire kwargs
        self.get_client_cour().traiter(**kwargs)    # chaque client traite à sa manière !!
        # Si Jury, on émet un SSE (à destination de l'admin pour mise à jour du décompte des traitements)
        if isinstance(self.get_client_cour(), Jury):
            self.add_sse_message('refresh', None)
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
        return self.html_compose.page_impression(client)
