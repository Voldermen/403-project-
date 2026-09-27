INSIDE OF SKELETON REPO 
1. Create a virtual env to download dependencies
    a. run "python -m venv venv" to create the venv
    b. activate the venv
        run "source venv/bin/activate" for mac/Linux
        run "venv/Scripts/activate for windows
    c. run "pip install -r requirements.txt"


Current thought process:
1. Flask acts as the framework/logic of the app or backend

2. gunicorn runs the flask app and listens for web requests and serves the flask info

        host with:
        "gunicorn app:app"
            (file name):(flask object name)  
        and you can look at the website locally

#################
3. We can have gunicorn handle public requests but its recommended to use
    a reverse proxy like "Nginx" to handle public requests

    so then it goes:
    public request -> Nginx -> gunicorn -> flask

    If we use nginx on the server we would have gunicorn run locally with
    "gunicorn --bind 127.0.0.1:8000 app:app" (or whatever port you want)
    then nginx would reverse proxy requests locally to gunicorn
#################


