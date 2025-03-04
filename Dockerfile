FROM python:3.11-slim-buster

WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git && \
    apt-get install -y rsync

RUN pip install requests pygithub

COPY . .

CMD ["python", "main.py"]
