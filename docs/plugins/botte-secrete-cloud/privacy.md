# Botte Secrète cloud — confidentialité

Dernière mise à jour : 31 octobre 2026.
Ce document couvre le service HTTPS Botte Secrète cloud ; il ne décrit pas tous
les skills ni les plugins installés séparément sur un ordinateur.

## Éditeur et contact

Botte Secrète est un projet de Sylvain Galliez. Pour une question ou une demande
relative aux données, utiliser le support du projet :
https://github.com/zedarvates/botte-secrete/issues.
Ne publier aucun contenu confidentiel dans une issue. Demander d'abord un canal
privé adapté si la demande exige de communiquer des données personnelles.

## Données traitées et finalités

Les outils traitent les contenus que vous choisissez de fournir : requêtes de
recherche de skills, textes, JSON, lignes de logs, séries de nombres, rapports,
paramètres de recherche et éléments de preuve GitHub. Ces contenus peuvent
contenir des données personnelles si vous en incluez ; fournissez uniquement
les extraits nécessaires et autorisés, après anonymisation quand elle est possible.

Ces données servent à rechercher des descriptions, compacter les contenus,
calculer des statistiques, résumer des éléments fournis et préparer des plans
de recherche ou de traitement. Les résultats ne constituent pas une vérification
indépendante des rapports, une autorisation d'exécution ou une mesure de facturation.

L'accès aux fonctions protégées utilise l'identifiant transmis par la plateforme
d'hébergement après authentification. Le service vérifie cet identifiant pour
autoriser l'appel ; le code examiné ne lit pas l'adresse électronique du compte.
Ne transmettre aucun mot de passe, jeton,
clé API, code de connexion ou autre secret comme argument d'un outil.

## Destinataires et fonctionnement

Les arguments et résultats circulent entre votre client conversationnel et le
service hébergé avec OpenAI Sites. Le code applicatif s'exécute dans un Worker
Cloudflare fourni par cette plateforme. Sa configuration examinée ne déclare
ni base de données D1 ni stockage de fichiers R2.

OpenAI et les prestataires nécessaires à cette plateforme traitent également les
données techniques nécessaires à l'authentification, à l'hébergement et à la
sécurité. Les conditions et informations de confidentialité applicables à votre
compte déterminent ces traitements indépendants du code Botte Secrète :
https://openai.com/policies/eu-privacy-policy/ et
https://openai.com/policies/row-privacy-policy/.

Les opérations examinées du service travaillent sur les contenus fournis. Elles
ne donnent pas accès à votre disque local et ne lancent pas les skills locaux,
un shell ou un modèle. La consultation de descriptions de skills ou la préparation
de recherches ne prouve pas l'exécution d'une opération externe.

La lecture des présentes pages sur GitHub relève également du fonctionnement de
GitHub : https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement.

## Conservation

Le code applicatif n'enregistre pas les arguments et résultats dans une base,
un fichier ou un historique de documents. Les contenus sont utilisés en mémoire
pendant le traitement de la demande et le résultat est renvoyé au client ; aucune
durée de conservation durable supplémentaire n'est mise en œuvre par l'application.
Cette description ne promet pas un effacement physique instantané de la mémoire
de l'environnement d'exécution.

Les demandes et réponses peuvent cependant
être conservées dans votre conversation et dans les journaux techniques de la
plateforme selon leurs propres règles. Cela ne constitue pas une promesse
d'absence de journalisation ou de suppression immédiate par l'infrastructure.

La configuration accessible de ce Site ne fournit pas de délai propre aux
journaux gérés par l'hébergeur. Nous n'annonçons donc pas de durée chiffrée que
nous ne pouvons pas vérifier. Consultez les règles de conservation et les
contrôles du fournisseur correspondant à votre offre. La politique OpenAI
destinée aux particuliers ne remplace pas les accords applicables aux offres
professionnelles ; un administrateur d'organisation peut aussi appliquer ses
propres règles aux conversations.

## Vos choix et demandes

Vous choisissez les contenus transmis et pouvez cesser d'utiliser ou déconnecter
le plugin. Les contrôles du client permettent de gérer les conversations selon
ses propres règles. Pour une demande concernant des données détenues par l'éditeur,
utiliser le contact ci-dessus ; les demandes relevant de l'hébergement ou du client
doivent également être adressées au fournisseur concerné. Vous pouvez notamment
demander l'accès, la correction ou l'effacement des données qui vous concernent,
ou exercer les autres droits prévus par le droit applicable. Une demande est
traitée en fonction des données effectivement détenues et des obligations
applicables ; l'éditeur ne peut pas effacer lui-même les journaux d'un fournisseur.

La licence MIT du code ne remplace pas cette information sur les données.
