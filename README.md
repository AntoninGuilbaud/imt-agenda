# Agenda REX dynamique

Ce service expose une URL iCalendar que Google Agenda peut consulter :

```text
https://VOTRE-APP.onrender.com/agenda.ics?token=VOTRE_AGENDA_TOKEN
```

Le service se connecte à REX à la demande et conserve le résultat pendant
60 minutes. Google Agenda décide toutefois de sa propre fréquence de
rafraîchissement ; une mise à jour exactement toutes les heures ne peut pas
être garantie.

## Déploiement Render

1. Créez un dépôt GitHub privé et ajoutez ces fichiers.
2. Sur Render, créez un **Web Service** depuis ce dépôt.
3. Configurez :
   - Build command : `pip install -r requirements.txt`
   - Start command : `gunicorn app:app`
4. Ajoutez les variables d’environnement :
   - `REX_BASE_URL`
   - `REX_IDENTIFIANT`
   - `REX_MOT_DE_PASSE`
   - `AGENDA_TOKEN` (une valeur longue et aléatoire)
   - `CACHE_MINUTES=60`
   - `REX_TLS_VERIFY=false` (nécessaire tant que le certificat intermédiaire
     du serveur REX n'est pas correctement publié)
5. Dans Google Agenda : **Autres agendas → À partir de l'URL**, collez
   l'URL complète avec `?token=...`.

Ne publiez jamais `.env` ni le mot de passe dans le dépôt. Si le mot de passe
REX change, mettez uniquement la variable Render à jour.
